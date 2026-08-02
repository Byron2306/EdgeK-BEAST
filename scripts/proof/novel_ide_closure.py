#!/usr/bin/env python3
"""End-to-end novel IDE task: Ollama residual -> bounded edit -> proof."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.kernel.compute.crystal_execution import CrystalExecutionEngine, CrystalExecutionError, CrystalExecutionRequest, ground_crystal_ir  # noqa: E402
from app.kernel.compute.crystal_ir import CRYSTAL_IR_TRANSLATOR_SCHEMA, compile_crystal_ir, translator_prompt  # noqa: E402


RESIDUAL_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["new"], "properties": {"new": {"type": "string", "minLength": 1, "maxLength": 240}}}
MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
OPTIONS = {"temperature": 0, "num_ctx": 1024, "num_predict": 64, "num_thread": 2, "num_batch": 128}


def sha(value: bytes | str) -> str:
    data = value.encode() if isinstance(value, str) else value
    return "sha256:" + hashlib.sha256(data).hexdigest()


def request_ollama(prompt: str, schema: dict, *, timeout: float) -> tuple[dict, dict]:
    payload = {"model": MODEL, "prompt": prompt, "stream": False, "format": schema, "options": OPTIONS, "keep_alive": "30m"}
    endpoint = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/generate"
    request = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode())
    raw = body.get("response") or "{}"
    candidate = json.loads(raw) if isinstance(raw, str) else raw
    telemetry = {"latency_ms": round((time.perf_counter() - started) * 1000, 2), "prompt_eval_count": body.get("prompt_eval_count"), "eval_count": body.get("eval_count"), "total_duration_ns": body.get("total_duration"), "load_duration_ns": body.get("load_duration"), "prompt_eval_duration_ns": body.get("prompt_eval_duration"), "eval_duration_ns": body.get("eval_duration"), "provider_called": True}
    return candidate if isinstance(candidate, dict) else {}, telemetry


def crystal_ir() -> object:
    return compile_crystal_ir({
        "version": "crystal.ir.v1",
        "mission": {"objective": "Add the on alias to boolean configuration parsing"},
        "target": {"file": "app/config.py", "symbol": "parse_bool"},
        "observed_failure": {"class": "configuration_schema_failure", "examples": [{"input": "on", "expected": True}]},
        "required_transform": {"pipeline": ["replace_function"]},
        "authority": {"writable_files": ["app/config.py"], "tests_mutable": False, "network_allowed": False, "maximum_effects": 1},
        "postconditions": ["syntax_valid", "target_tests_pass", "no_unrelated_diff"],
        "rollback": {"required": True},
        "unresolved_fields": ["new"],
    })


def write_fixture(root: Path) -> None:
    (root / "app").mkdir()
    (root / "tests").mkdir()
    (root / "app/config.py").write_text('def parse_bool(value):\n    return str(value).strip().lower() in {"true", "1", "yes"}\n', encoding="utf-8")
    (root / "tests/test_config.py").write_text('from app.config import parse_bool\n\ndef test_parse_bool_aliases():\n    assert parse_bool("on") is True\n    assert parse_bool("yes") is True\n    assert parse_bool("off") is False\n', encoding="utf-8")
    (root / "app/__init__.py").write_text("", encoding="utf-8")


def write_pack(output: Path, receipt: dict) -> Path:
    pack = output.with_name(output.stem + "_pack")
    pack.mkdir(parents=True, exist_ok=True)
    (pack / "closure_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    (pack / "README.md").write_text("# Novel IDE Closure Evidence\n\nThis bundle records one grounded Ollama residual, bounded execution, targeted verification, conditional repair handling, raw-model comparison, and deterministic crystal reuse. It does not claim general coding capability.\n", encoding="utf-8")
    files = {path.name: sha(path.read_bytes()) for path in sorted(pack.iterdir()) if path.is_file()}
    manifest = {"beast_object_type": "novel_ide_closure_integrity_manifest", "version": "1.0", "files": files}
    manifest["manifest_hash"] = sha(json.dumps(manifest, sort_keys=True))
    (pack / "integrity_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    archive = pack.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(pack.iterdir()):
            if path.is_file():
                bundle.write(path, path.name)
    return pack


def run_verified_edit(root: Path, ir: object, new: str, task_id: str) -> dict:
    grounded = ground_crystal_ir(ir, str(root))
    replacement = grounded.old.replace('    return str(value).strip().lower() in {"true", "1", "yes"}', f"    {new}", 1)
    request = CrystalExecutionRequest(ir, grounded.old, replacement, "novel-ide-approval", task_id, str(root), (("python", "-m", "py_compile", "app/config.py"), ("pytest", "-q", "tests/test_config.py")), grounded.file_sha256)
    return CrystalExecutionEngine().execute(request)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="benchmarks/results/novel_ide_closure.json")
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()
    started = time.perf_counter()
    cpu_start = resource.getrusage(resource.RUSAGE_SELF)
    task = {"objective": "The boolean configuration parser must accept the common on/off aliases while preserving existing true/false/yes behavior.", "target_menu": {"T0": {"file": "app/config.py", "symbol": "parse_bool"}}, "target_id": "T0"}
    ir = crystal_ir()
    results: dict[str, object] = {"task": task, "model": MODEL, "options": OPTIONS, "provider_calls": 0}
    with tempfile.TemporaryDirectory(prefix="beast-novel-ide-") as tmp:
        root = Path(tmp)
        write_fixture(root)
        grounded = ground_crystal_ir(ir, str(root))
        results["cartographer_grounding"] = {"target_id": "T0", "path": grounded.path, "symbol": grounded.symbol, "old_sha256": sha(grounded.old), "file_sha256": grounded.file_sha256}
        raw_prompt = "Return the complete contents of app/config.py for this task. Add support for on/off aliases. Do not explain."
        try:
            raw_candidate, raw_telemetry = request_ollama(raw_prompt, {"type": "string"}, timeout=args.timeout)
            results["raw_ollama"] = {"candidate_type": type(raw_candidate).__name__, "telemetry": raw_telemetry, "mutation_performed": False}
            results["provider_calls"] = int(results["provider_calls"]) + 1
        except Exception as exc:
            results["raw_ollama"] = {"error": f"{type(exc).__name__}: {exc}", "mutation_performed": False}
        residual_prompt = translator_prompt(task["objective"], target_file="app/config.py", context="Cartographer target_id=T0; target symbol=parse_bool. Return a bounded residual only. The unresolved field new must be one complete Python return statement. Existing function: return str(value).strip().lower() in {\"true\", \"1\", \"yes\"}. Required new behavior: \"on\" is true and \"off\" is false. Never return a whole file.")
        residual_prompt += "\nReturn exactly this bounded shape: {\"new\": \"one complete Python return statement\"}."
        try:
            candidate, telemetry = request_ollama(residual_prompt, RESIDUAL_SCHEMA, timeout=args.timeout)
            results["provider_calls"] = int(results["provider_calls"]) + 1
            new = str(candidate.get("new") or "").strip()
            results["live_residual"] = {"candidate": candidate, "telemetry": telemetry, "bounded_field": new.startswith("return ") and "\n" not in new, "mutation_performed": False}
        except Exception as exc:
            candidate, new = {}, ""
            results["live_residual"] = {"error": f"{type(exc).__name__}: {exc}", "mutation_performed": False}
        repair_attempt = None
        live_receipt = None
        try:
            if not new.startswith("return ") or "\n" in new:
                raise CrystalExecutionError("residual must be one return statement")
            live_receipt = run_verified_edit(root, ir, new, "novel-live")
        except Exception as exc:
            repair_prompt = residual_prompt + f"\nVerifier failure: {exc}\nReturn only corrected JSON under the same bounded schema."
            try:
                repaired, repair_telemetry = request_ollama(repair_prompt, RESIDUAL_SCHEMA, timeout=args.timeout)
                results["provider_calls"] = int(results["provider_calls"]) + 1
                repair_attempt = {"attempted": True, "candidate": repaired, "telemetry": repair_telemetry}
                live_receipt = run_verified_edit(root, ir, str(repaired.get("new") or ""), "novel-repair")
            except Exception as repair_exc:
                repair_attempt = {"attempted": True, "error": f"{type(repair_exc).__name__}: {repair_exc}"}
        results["live_verified_edit"] = live_receipt or {"status": "failed"}
        results["repair"] = repair_attempt or {"attempted": False}
        crystal_root = root / "crystal"
        crystal_root.mkdir()
        write_fixture(crystal_root)
        crystal_receipt = run_verified_edit(crystal_root, ir, 'return str(value).strip().lower() in {"true", "1", "yes", "on"}', "crystal-reuse")
        results["deterministic_crystal_reuse"] = {"receipt": crystal_receipt, "provider_calls": 0}
    cpu_end = resource.getrusage(resource.RUSAGE_SELF)
    results["cpu_seconds"] = round((cpu_end.ru_utime - cpu_start.ru_utime) + (cpu_end.ru_stime - cpu_start.ru_stime), 6)
    results["wall_seconds"] = round(time.perf_counter() - started, 3)
    results["claim_boundary"] = "This proves one bounded local edit path, not general coding capability or model-weight improvement."
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    results["evidence_pack"] = str(output.with_name(output.stem + "_pack"))
    results["receipt_hash"] = sha(json.dumps(results, sort_keys=True, default=str))
    output.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_pack(output, results)
    print(json.dumps({"path": str(output), "receipt_hash": results["receipt_hash"], "provider_calls": results["provider_calls"], "live_status": (results.get("live_verified_edit") or {}).get("status"), "crystal_status": (results.get("deterministic_crystal_reuse") or {}).get("receipt", {}).get("status")}, indent=2, sort_keys=True))
    return 0 if (results.get("live_verified_edit") or {}).get("status") == "verified" and (results.get("deterministic_crystal_reuse") or {}).get("receipt", {}).get("status") == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
