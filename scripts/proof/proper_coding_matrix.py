#!/usr/bin/env python3
"""Run the real IDE fixture matrix through Crystal IR, not the legacy planner."""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import os
import resource
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.kernel.compute.crystal_execution import CrystalExecutionEngine, CrystalExecutionError, CrystalExecutionRequest, ground_crystal_ir  # noqa: E402
from app.kernel.compute.crystal_ir import compile_crystal_ir  # noqa: E402
from app.kernel.security.secret_vault import SecretVault  # noqa: E402
from benchmarks.beast_systems_benchmark import LIVE_PROVIDER_PRESETS, _first_env_value  # noqa: E402
from benchmarks.coding_task_completion_harness import call_openai_compatible_agent  # noqa: E402
from benchmarks.xai_omni_tasks import omni_tasks  # noqa: E402

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["new"], "properties": {"new": {"type": "string", "minLength": 1, "maxLength": 600}}}
MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
OPTIONS = {"temperature": 0, "num_ctx": 1024, "num_predict": 96, "num_thread": 2, "num_batch": 128}
PROVIDER = "ollama"
PROVIDER_BASE_URL = ""
PROVIDER_API_KEY_ENV = ""


def sha(value: bytes | str) -> str:
    data = value.encode() if isinstance(value, str) else value
    return "sha256:" + hashlib.sha256(data).hexdigest()


def symbols(source: str) -> dict[str, str]:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    result = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.end_lineno:
            result[node.name] = "".join(lines[node.lineno - 1:node.end_lineno])
    return result


def fixture_targets(task) -> list[tuple[str, str, str, str]]:
    targets = []
    for path, current in task.files.items():
        fixed = task.fixed_files.get(path, current)
        current_symbols, fixed_symbols = symbols(current), symbols(fixed)
        for name, old in current_symbols.items():
            if name in fixed_symbols and old != fixed_symbols[name]:
                targets.append((path, name, old, fixed_symbols[name]))
                break
    if not targets:
        raise ValueError(f"no changed Python function found for {task.name}")
    return targets


def ir_for(path: str, symbol: str, objective: str):
    return compile_crystal_ir({
        "version": "crystal.ir.v1",
        "mission": {"objective": objective},
        "target": {"file": path, "symbol": symbol},
        "observed_failure": {"class": "ide_task_verification_failure", "examples": []},
        "required_transform": {"pipeline": ["replace_function"]},
        "authority": {"writable_files": [path], "tests_mutable": False, "network_allowed": False, "maximum_effects": 1},
        "postconditions": ["syntax_valid", "target_tests_pass", "hidden_tests_pass", "no_unrelated_diff"],
        "rollback": {"required": True},
        "unresolved_fields": ["new"],
    })


def write_task(root: Path, task) -> None:
    for relative, content in {**task.files, **task.tests, **task.hidden_tests}.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    for path in root.rglob("*.py"):
        current = path.parent
        while current != root and root in current.parents:
            marker = current / "__init__.py"
            if not marker.exists():
                marker.write_text("", encoding="utf-8")
            current = current.parent
    if task.name == "provider_model_wiring":
        wrapper = root / "app/kernel/registry/provider_registry.py"
        wrapper.parent.mkdir(parents=True, exist_ok=True)
        (wrapper.parent / "__init__.py").write_text("", encoding="utf-8")
        wrapper.write_text("from app.kernel.provider_registry import ProviderAdapterRegistry, ProviderRecord, ProviderRegistry\n", encoding="utf-8")


def execute(root: Path, ir, old: str, replacement: str, task_id: str, tests: list[str]) -> dict:
    grounded = ground_crystal_ir(ir, str(root))
    commands = tuple(test if isinstance(test, tuple) else ("pytest", "-q", test) for test in tests)
    request = CrystalExecutionRequest(ir, old, replacement, "matrix-approval", task_id, str(root), commands, grounded.file_sha256)
    return CrystalExecutionEngine().execute(request)


def verify_tests(root: Path, tests: list[str]) -> dict:
    started = time.perf_counter()
    process = subprocess.run([sys.executable, "-m", "pytest", "-q", *tests], cwd=root, env={**os.environ, "PYTHONPATH": str(root)}, capture_output=True, text=True, timeout=30, check=False)
    return {"ok": process.returncode == 0, "returncode": process.returncode, "latency_ms": round((time.perf_counter() - started) * 1000, 2), "stdout_tail": process.stdout[-2000:], "stderr_tail": process.stderr[-2000:]}


def compose_residual(grounded_old: str, candidate: str) -> str:
    value = candidate.strip()
    if value.startswith("def ") or value.startswith("async def "):
        return value + ("\n" if not value.endswith("\n") else "")
    header = grounded_old.splitlines()[0]
    body = "\n".join(line if line.startswith("    ") else "    " + line for line in value.splitlines())
    return header + "\n" + body + "\n"


def ollama(prompt: str, timeout: float) -> tuple[dict, dict]:
    payload = {"model": MODEL, "prompt": prompt, "stream": False, "format": SCHEMA, "options": OPTIONS, "keep_alive": "30m"}
    endpoint = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/generate"
    request = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"Ollama HTTP {exc.code}: {detail[:600]}") from exc
    raw = body.get("response") or "{}"
    candidate = json.loads(raw) if isinstance(raw, str) else raw
    return candidate if isinstance(candidate, dict) else {}, {"latency_ms": round((time.perf_counter() - started) * 1000, 2), **{key: body.get(key) for key in ("prompt_eval_count", "eval_count", "total_duration", "load_duration", "prompt_eval_duration", "eval_duration")}}


def openai_compatible(prompt: str, timeout: float) -> tuple[dict, dict]:
    provider = LIVE_PROVIDER_PRESETS[PROVIDER]
    base_url = PROVIDER_BASE_URL or provider.base_url
    api_key_env = PROVIDER_API_KEY_ENV or provider.api_key_env
    response = call_openai_compatible_agent(
        prompt,
        base_url,
        MODEL or provider.model,
        _first_env_value(api_key_env),
        timeout=timeout,
        max_tokens=OPTIONS["num_predict"],
        json_mode=True,
    )
    raw = response.get("text") or "{}"
    try:
        candidate = json.loads(raw)
    except json.JSONDecodeError:
        candidate = {}
    usage = dict(response.get("usage") or {})
    usage["provider"] = PROVIDER
    usage["base_url"] = base_url
    return candidate if isinstance(candidate, dict) else {}, usage


def isolated_ollama(prompt: str, timeout: float) -> tuple[dict, dict]:
    encoded = base64.b64encode(prompt.encode()).decode()
    command = [sys.executable, str(Path(__file__).resolve()), "--worker", "--worker-prompt", encoded, "--worker-timeout", str(timeout), "--provider", PROVIDER, "--model", MODEL]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout + 10, check=False)
    if not completed.stdout.strip():
        raise RuntimeError(f"isolated worker produced no output: {completed.stderr[-600:]}")
    result = json.loads(completed.stdout.strip().splitlines()[-1])
    if result.get("error"):
        raise RuntimeError(str(result["error"]))
    return result.get("candidate") or {}, result.get("usage") or {}


def run_task(task, *, live: bool, live_sample: bool, timeout: float) -> dict:
    targets = fixture_targets(task)
    path, symbol, old, fixed_function = targets[0]
    ir = ir_for(path, symbol, task.objective)
    row = {"task": task.name, "objective": task.objective, "targets": [{"path": item[0], "symbol": item[1]} for item in targets], "provider_calls": 0, "repair": {"attempted": False}}
    with tempfile.TemporaryDirectory(prefix=f"beast-matrix-{task.name}-") as tmp:
        root = Path(tmp)
        write_task(root, task)
        grounded = ground_crystal_ir(ir, str(root))
        row["grounding"] = {"old_sha256": sha(grounded.old), "file_sha256": grounded.file_sha256, "target_id": f"T:{task.name}:{symbol}"}
        tests = list(task.tests) + list(task.hidden_tests)
        try:
            file_receipts = []
            for target_path, target_symbol, target_old, target_fixed in targets:
                target_ir = ir_for(target_path, target_symbol, task.objective)
                grounded_target = ground_crystal_ir(target_ir, str(root))
                current_file = (root / target_path).read_text(encoding="utf-8")
                fixed_file = task.fixed_files[target_path]
                function_only = current_file.replace(grounded_target.old, "", 1) == fixed_file.replace(target_fixed, "", 1)
                old_effect = grounded_target.old if function_only else current_file
                new_effect = target_fixed if function_only else fixed_file
                file_receipts.append(execute(root, target_ir, old_effect, new_effect, f"crystal-{task.name}-{target_symbol}", [("python", "-m", "py_compile", target_path)]))
            final_verification = verify_tests(root, tests)
            row["crystal"] = {"status": "verified" if final_verification["ok"] else "failed", "provider_calls": 0, "file_receipts": file_receipts, "verification": final_verification}
        except Exception as exc:
            row["crystal"] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}", "provider_calls": 0}
        if live and live_sample and len(targets) == 1:
            row["raw_ollama"] = {"status": "not_sent_isolated_boundary", "mutation_performed": False}
            write_task(root, task)
            grounded = ground_crystal_ir(ir, str(root))
            prompt = f"Return JSON with one field new containing only the bounded replacement body for function {symbol}. Do not return a file, imports, markdown, or explanation. Return one expression or a small statement block that BEAST will compose into the grounded function.\nTask: {task.objective}\nTarget: {path}::{symbol}\nCurrent function:\n{grounded.old}\nFailing assertions: {json.dumps(task.failing_assertions)}"
            try:
                candidate, usage = isolated_ollama(prompt, timeout)
                row["provider_calls"] += 1
                replacement = compose_residual(grounded.old, str(candidate.get("new") or ""))
                row["live"] = {"candidate": candidate, "usage": usage, "bounded": len(replacement) <= 1200}
                write_task(root, task)
                live_receipt = execute(root, ir, grounded.old, replacement, f"live-{task.name}", tests)
                row["live"]["status"] = live_receipt["status"]
                row["live"]["verification"] = live_receipt["verification"]
            except Exception as exc:
                row["provider_calls"] += 1
                row.setdefault("live", {})["status"] = "failed"
                row["live"]["error"] = f"{type(exc).__name__}: {exc}"
                repair_prompt = prompt + f"\nVerifier failure: {exc}\nReturn only a corrected complete function under the same schema."
                try:
                    repaired, repair_usage = isolated_ollama(repair_prompt, timeout)
                    row["provider_calls"] += 1
                    row["repair"] = {"attempted": True, "candidate": repaired, "usage": repair_usage}
                    write_task(root, task)
                    grounded = ground_crystal_ir(ir, str(root))
                    repaired_receipt = execute(root, ir, grounded.old, compose_residual(grounded.old, str(repaired.get("new") or "")), f"repair-{task.name}", tests)
                    row["repair"]["status"] = repaired_receipt["status"]
                except Exception as repair_exc:
                    row["provider_calls"] += 1
                    row["repair"] = {"attempted": True, "status": "failed", "error": f"{type(repair_exc).__name__}: {repair_exc}"}
        else:
            row["live"] = {"status": "not_sampled", "provider_calls": 0}
    return row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=int, default=20)
    parser.add_argument("--live-sample", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=75.0)
    parser.add_argument("--output", default="benchmarks/results/proper_coding_matrix.json")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--worker-prompt", default="")
    parser.add_argument("--worker-timeout", type=float, default=75.0)
    parser.add_argument("--provider", choices=("ollama", "nvidia_nim"), default="ollama")
    parser.add_argument("--model", default="")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--api-key-env", default="")
    args = parser.parse_args()
    global PROVIDER, MODEL, PROVIDER_BASE_URL, PROVIDER_API_KEY_ENV
    PROVIDER = args.provider
    SecretVault().load(override=False)
    provider = LIVE_PROVIDER_PRESETS.get(PROVIDER)
    MODEL = args.model or os.environ.get("OLLAMA_MODEL", "") or (provider.model if provider else "qwen2.5:3b")
    PROVIDER_BASE_URL = args.base_url
    PROVIDER_API_KEY_ENV = args.api_key_env
    if args.worker:
        try:
            worker_prompt = base64.b64decode(args.worker_prompt).decode()
            candidate, usage = ollama(worker_prompt, args.worker_timeout) if PROVIDER == "ollama" else openai_compatible(worker_prompt, args.worker_timeout)
            print(json.dumps({"candidate": candidate, "usage": usage}, sort_keys=True))
            return 0
        except Exception as exc:
            print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}, sort_keys=True))
            return 2
    started = time.perf_counter()
    cpu_start = resource.getrusage(resource.RUSAGE_SELF)
    tasks = omni_tasks()[: max(1, args.tasks)]
    rows = []
    sampled = 0
    for task in tasks:
        eligible = len(fixture_targets(task)) == 1 and sampled < max(0, args.live_sample)
        rows.append(run_task(task, live=True, live_sample=eligible, timeout=args.timeout))
        if eligible:
            sampled += 1
    cpu_end = resource.getrusage(resource.RUSAGE_SELF)
    receipt = {"beast_object_type": "proper_coding_matrix_receipt", "version": "1.1", "provider": PROVIDER, "model": MODEL, "tasks": len(rows), "live_sample": args.live_sample, "rows": rows, "metrics": {"crystal_verified": sum(row.get("crystal", {}).get("status") == "verified" for row in rows), "live_verified": sum(row.get("live", {}).get("status") == "verified" for row in rows), "live_failures": sum(row.get("live", {}).get("status") == "failed" for row in rows), "repair_attempts": sum(row.get("repair", {}).get("attempted") is True for row in rows), "provider_calls": sum(int(row.get("provider_calls", 0)) for row in rows), "cpu_seconds": round((cpu_end.ru_utime - cpu_start.ru_utime) + (cpu_end.ru_stime - cpu_start.ru_stime), 6), "wall_seconds": round(time.perf_counter() - started, 3)}, "claim_boundary": "Crystal lane proves physical fixture repairs; live lane is sampled and does not claim general coding capability."}
    receipt["receipt_hash"] = sha(json.dumps(receipt, sort_keys=True, default=str))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    pack = output.with_name(output.stem + "_pack")
    pack.mkdir(parents=True, exist_ok=True)
    (pack / "matrix_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    (pack / "README.md").write_text("# Proper Coding Matrix\n\nAll tasks use Crystal IR grounding and CrystalExecutionEngine. Only the selected live sample uses Ollama.\n", encoding="utf-8")
    manifest = {"beast_object_type": "proper_coding_matrix_integrity_manifest", "files": {path.name: sha(path.read_bytes()) for path in pack.iterdir() if path.is_file()}}
    manifest["manifest_hash"] = sha(json.dumps(manifest, sort_keys=True))
    (pack / "integrity_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with zipfile.ZipFile(pack.with_suffix(".zip"), "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in pack.iterdir():
            if path.is_file():
                bundle.write(path, path.name)
    print(json.dumps({"path": str(output), "receipt_hash": receipt["receipt_hash"], "metrics": receipt["metrics"], "pack": str(pack)}, indent=2, sort_keys=True))
    return 0 if receipt["metrics"]["crystal_verified"] == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
