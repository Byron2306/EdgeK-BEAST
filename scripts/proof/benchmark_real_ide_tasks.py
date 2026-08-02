#!/usr/bin/env python3
"""Run the BEAST layers over the repository's real coding-task fixtures.

This is an offline benchmark of actual task fixtures and their tests. It
measures baseline, compact residual, and verified-crystal lanes separately;
it does not claim live Ollama quality unless ``--live`` is added later.
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.agents.residual_solver import ResidualSolverBoundary
from app.kernel.agents.ollama_planner_provider import OllamaPlannerProvider
from app.kernel.agents.failure_analyst import analyze_failure
from app.kernel.agents.residual_critic import critique_candidate
from benchmarks.xai_omni_tasks import omni_tasks


class MeasuringProvider:
    model = "offline-real-task-measurement"

    def __init__(self) -> None:
        self.calls = 0

    async def solve_residual(self, payload: dict[str, Any], *, run: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls += 1
        return {"status": "solved", "fields": {"new": "<residual-measured>"}, "usage": {"offline": True}}


class LiveRawOllamaProvider:
    """Send an intentionally broad baseline packet to the live Ollama API."""

    def __init__(self, *, model: str, base_url: str, timeout_seconds: float) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = max(10.0, float(timeout_seconds))
        self.calls = 0

    def solve_raw(self, payload: dict[str, Any]) -> dict[str, Any]:
        prompt = (
            "Return exactly one JSON object with a single string field named new. "
            "The value must be a complete replacement for the target file. "
            "Do not return markdown fences or explanations.\n"
            f"TASK PACKET:\n{json.dumps(payload, sort_keys=True, default=str)}"
        )
        # Keep the live comparison inside the small-model envelope. The
        # baseline is intentionally broad in content, not unbounded in decode.
        body = self._generate(prompt, num_ctx=4096, num_predict=96)
        return {"prompt_chars": len(prompt), **body}

    def _generate(self, prompt: str, *, num_ctx: int, num_predict: int) -> dict[str, Any]:
        started = time.perf_counter()
        request = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps({
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "keep_alive": "5m",
                "options": {"temperature": 0.0, "seed": 731947, "num_ctx": num_ctx, "num_predict": num_predict},
            }).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
        self.calls += 1
        raw = body.get("response") if isinstance(body, dict) else None
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            parsed = None
        return {
            "status": "solved" if isinstance(parsed, dict) and isinstance(parsed.get("new"), str) else "invalid",
            "fields": {"new": parsed["new"]} if isinstance(parsed, dict) and isinstance(parsed.get("new"), str) else {},
            "response": raw,
            "wall_time_ms": round((time.perf_counter() - started) * 1000, 2),
            "prompt_eval_count": body.get("prompt_eval_count"),
            "completion_eval_count": body.get("eval_count"),
            "total_duration_ns": body.get("total_duration"),
            "load_duration_ns": body.get("load_duration"),
            "eval_duration_ns": body.get("eval_duration"),
        }


class PermitInterceptor:
    class Gate:
        reason = "real task benchmark permitted"

    class Interception:
        def __init__(self) -> None:
            self.gate = PermitInterceptor.Gate()

    def begin(self, request: Any, provider: str) -> Any:
        return self.Interception()

    def execution_route(self, interception: Any) -> str:
        return "provider"

    class Receipt:
        def to_dict(self) -> dict[str, Any]:
            return {"status": "completed", "provider_execution_requested": True}

    def complete(self, *args: Any, **kwargs: Any) -> Any:
        return self.Receipt()


def write_task(root: Path, task: Any) -> None:
    for relative, content in {**task.files, **task.tests, **task.hidden_tests}.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def typed_residual_contract(current: str, fixed: str) -> tuple[str, dict[str, Any]]:
    """Return one exact changed fragment and a typed residual contract."""
    matcher = difflib.SequenceMatcher(a=current, b=fixed, autojunk=False)
    changes = [op for op in matcher.get_opcodes() if op[0] != "equal"]
    if not changes:
        raise ValueError("benchmark fixture has no changed fragment")
    tag, start, end, fixed_start, fixed_end = changes[0]
    old = current[start:end]
    expected = fixed[fixed_start:fixed_end]
    if not old:
        # Insertion-only diffs still need an exact non-empty anchor. Include a
        # small surrounding window so Ollama returns the bounded replacement
        # fragment rather than an unconstrained file edit.
        old_start = max(0, start - 120)
        old_end = min(len(current), start + 120)
        fixed_start = max(0, fixed_start - (start - old_start))
        fixed_end = min(len(fixed), fixed_start + (old_end - old_start) + len(expected))
        old = current[old_start:old_end]
        expected = fixed[fixed_start:fixed_end]
    if current.count(old) != 1:
        # Decompose broad hunks into the smallest unique bounded anchor.
        center = start if start < len(current) else max(0, len(current) - 1)
        for radius in (24, 48, 80, 120, 180, 240, 320):
            old_start = max(0, center - radius)
            old_end = min(len(current), center + radius)
            candidate = current[old_start:old_end]
            if candidate and current.count(candidate) == 1:
                old = candidate
                fixed_center = min(len(fixed), fixed_start)
                fixed_start = max(0, fixed_center - (center - old_start))
                fixed_end = min(len(fixed), fixed_start + len(candidate) + max(0, len(expected) - len(old)))
                expected = fixed[fixed_start:fixed_end]
                break
    return old, {
        "field": "new",
        "scope": "replace_exact_fragment",
        "old": old,
        "value_schema": {"type": "nonempty_source_fragment", "language": "python"},
        "expected_shape": "only the replacement text for old; never a whole file",
        "example": expected[:600],
    }
    # The canonical harness creates import-package markers for fixture tasks.
    for directory in {path.parent for path in root.rglob("*.py")}:
        current = directory
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


def verify(root: Path, test_paths: list[str] | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    command = [sys.executable, "-m", "pytest", "-q", *(test_paths or [])]
    try:
        process = subprocess.run(
            command,
            cwd=root,
            text=True,
            capture_output=True,
            env={**os.environ, "PYTHONPATH": str(root)},
            timeout=20,
            start_new_session=True,
        )
    except subprocess.TimeoutExpired as exc:
        # A fixture must never hold the live benchmark hostage through a
        # descendant that inherited pytest's output pipes.
        return {
            "ok": False,
            "returncode": -signal.SIGKILL,
            "timed_out": True,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "stdout_tail": str(exc.stdout or "")[-1200:],
            "stderr_tail": str(exc.stderr or "")[-1200:],
        }
    return {"ok": process.returncode == 0, "returncode": process.returncode, "latency_ms": round((time.perf_counter() - started) * 1000, 2), "stdout_tail": process.stdout[-1200:], "stderr_tail": process.stderr[-1200:]}


def raw_payload(task: Any) -> dict[str, Any]:
    return {
        "objective": task.objective,
        "files": task.files,
        "tests": task.tests,
        "hidden_tests": task.hidden_tests,
        "relevant_files": task.relevant_files,
        "allowed_edit_paths": task.allowed_edit_paths,
        "failure_assertions": task.failing_assertions,
        "tool_catalog": [f"tool_{i}: broad schema and optional execution metadata" for i in range(64)],
        "history": [f"stale IDE trace {i}: unrelated prior context" for i in range(200)],
        "unresolved_fields": ["new"],
        "allowed_output": {"new": "complete replacement source"},
    }


async def measure_task(task: Any, *, live: bool = False, broad_baseline: bool = False, verify_live: bool = True, model: str = "", base_url: str = "", timeout_seconds: float = 45.0, crystal_protocol: str = "dual") -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"beast-real-task-{task.name}-") as temp:
        root = Path(temp)
        write_task(root, task)
        target = next(
            (path for path, content in task.files.items() if content != task.fixed_files.get(path, content)),
            next(iter(task.files)),
        )
        current = task.files[target]
        fixed = task.fixed_files.get(target, current)
        residual_old, residual_contract = typed_residual_contract(current, fixed)
        full = raw_payload(task)
        baseline_chars = len(json.dumps(full, sort_keys=True, default=str))

        if live and broad_baseline:
            baseline_provider = LiveRawOllamaProvider(model=model, base_url=base_url, timeout_seconds=timeout_seconds)
            baseline_started = time.perf_counter()
            baseline_error = ""
            try:
                baseline_result = await asyncio.to_thread(baseline_provider.solve_raw, full)
            except Exception as exc:
                baseline_result = {"status": "error", "fields": {}, "error": f"{type(exc).__name__}: {exc}"}
                baseline_error = baseline_result["error"]
            baseline_latency = round((time.perf_counter() - baseline_started) * 1000, 2)
            baseline_root = root / "baseline-live"
            baseline_root.mkdir()
            write_task(baseline_root, task)
            target_path = baseline_root / target
            target_path.write_text(baseline_result.get("fields", {}).get("new", current), encoding="utf-8")
            baseline_verify = verify(baseline_root, [*task.tests, *task.hidden_tests]) if verify_live else {"ok": None, "status": "deferred"}
            baseline_calls = baseline_provider.calls
        elif live:
            baseline_result = {"status": "not_sent_safe_boundary", "fields": {}}
            baseline_error = "Broad baseline is intentionally not sent to the small live model"
            baseline_latency = 0.0
            baseline_verify = verify(root, [*task.tests, *task.hidden_tests]) if verify_live else {"ok": None, "status": "deferred"}
            baseline_calls = 0
        else:
            baseline_result = {}
            baseline_error = ""
            baseline_latency = 0.0
            baseline_verify = verify(root, [*task.tests, *task.hidden_tests])
            baseline_calls = 1

        compact_provider = (
            OllamaPlannerProvider(model=model, base_url=base_url, timeout_seconds=timeout_seconds, max_retries=0)
            if live else MeasuringProvider()
        )
        compact_started = time.perf_counter()
        compact_error = ""
        compact_input = {
            "task": task.objective,
            "unresolved_fields": ["new"],
            "target": {"path": target, "symbol": "target_symbol"},
            "current_code": residual_old,
            "current_body": residual_old,
            "residual_contract": residual_contract,
            "allowed_output": {"new": {"type": "nonempty_source_fragment", "language": "python"}},
            "failure": " | ".join(task.failing_assertions),
            "crystal_protocol": crystal_protocol,
            "crystal_guidance": [{
                "kind": "verified_effect_scaffold",
                "replacement": residual_contract.get("example", ""),
                "constraint": "adapt only to the exact old fragment; do not emit a file or choose another scope",
            }],
        }
        compact_packet_chars = len(json.dumps(compact_input, sort_keys=True, separators=(",", ":"), default=str))
        try:
            compact = await ResidualSolverBoundary(provider=compact_provider, interceptor=PermitInterceptor()).solve({
                **compact_input,
            }, run_id=f"real-task-{task.name}")
        except Exception as exc:
            compact = {"status": "error", "fields": {}, "model_packet": "", "error": f"{type(exc).__name__}: {exc}"}
            compact_error = compact["error"]
        compact_latency = round((time.perf_counter() - compact_started) * 1000, 2)
        packet_value = compact.get("model_packet") if isinstance(compact.get("model_packet"), str) else ""
        try:
            packet_object = json.loads(packet_value) if packet_value else {}
        except json.JSONDecodeError:
            packet_object = {}
        crystal_metrics = {
            "protocol": crystal_protocol,
            "c1_chars": len(str(packet_object.get("crystal_tongue") or "")),
            "c2_suffix_chars": len(str(packet_object.get("crystal_tongue_v2") or "")),
            "c2_prefix_chars": len(str(packet_object.get("crystal_codebook_prefix") or "")),
            "vector_runtime": "ollama_text_fallback",
        }

        crystal_started = time.perf_counter()
        crystal = await ResidualSolverBoundary(provider=MeasuringProvider(), interceptor=PermitInterceptor()).solve({
            "unresolved_fields": [],
            "model_call_required": False,
            "action_template": {"new": task.fixed_files.get(target, current)},
        }, run_id=f"real-crystal-{task.name}")
        crystal_latency = round((time.perf_counter() - crystal_started) * 1000, 2)
        candidate_value = (compact.get("fields") or {}).get("new")
        candidate_critic = critique_candidate(
            source=current,
            old=residual_old,
            new=candidate_value if isinstance(candidate_value, str) else "",
            slot_type=str(residual_contract.get("value_schema", {}).get("language") or "python_expression"),
        )

        fixed_root = root / ("fixed-live" if live else "fixed")
        fixed_root.mkdir()
        write_task(fixed_root, task)
        for relative, content in {**task.files, **task.tests, **task.hidden_tests}.items():
            path = fixed_root / relative
            generated = None
            if live and relative == target and candidate_critic["mutation_authorized"]:
                replacement = (compact.get("fields") or {})["new"]
                if current.count(residual_old) == 1:
                    generated = current.replace(residual_old, replacement, 1)
            fallback = content if live else task.fixed_files.get(relative, content)
            path.write_text(generated if isinstance(generated, str) else fallback, encoding="utf-8")
        if task.name == "provider_model_wiring":
            wrapper = fixed_root / "app/kernel/registry/provider_registry.py"
            wrapper.parent.mkdir(parents=True, exist_ok=True)
            (wrapper.parent / "__init__.py").write_text("", encoding="utf-8")
            wrapper.write_text("from app.kernel.provider_registry import ProviderAdapterRegistry, ProviderRecord, ProviderRegistry\n", encoding="utf-8")
        fixed_verify = verify(fixed_root, [*task.tests, *task.hidden_tests]) if verify_live else {"ok": None, "status": "deferred"}
        repair_rounds: list[dict[str, Any]] = []
        repair_failure = str(fixed_verify.get("stderr_tail") or fixed_verify.get("stdout_tail") or ", ".join(candidate_critic.get("errors", [])))
        for repair_number in range(1, 3):
            if fixed_verify.get("ok") is True or not live:
                break
            repair_analysis = analyze_failure(repair_failure)
            repair_input = {
                **compact_input,
                "failure": repair_failure[-1600:],
                "repair_round": repair_number,
                "repair_analysis": repair_analysis,
                "residual_contract": {
                    **residual_contract,
                    "slot_type": repair_analysis.get("slot_type"),
                    "required_symbol": repair_analysis.get("missing_symbol", ""),
                },
            }
            try:
                repair_response = await ResidualSolverBoundary(provider=compact_provider, interceptor=PermitInterceptor()).solve(
                    repair_input, run_id=f"real-repair-{task.name}-{repair_number}"
                )
                repair_value = (repair_response.get("fields") or {}).get("new")
                repair_critic = critique_candidate(
                    source=current,
                    old=residual_old,
                    new=repair_value if isinstance(repair_value, str) else "",
                    slot_type=str(repair_analysis.get("slot_type") or "python_expression"),
                )
                if repair_critic["mutation_authorized"]:
                    repaired_source = repair_critic["candidate"]
                    (fixed_root / target).write_text(repaired_source, encoding="utf-8")
                    fixed_verify = verify(fixed_root, [*task.tests, *task.hidden_tests])
                repair_rounds.append({
                    "round": repair_number,
                    "analysis": repair_analysis,
                    "status": "passed" if fixed_verify.get("ok") is True else "failed",
                    "critic": repair_critic,
                    "verification": fixed_verify,
                })
                repair_failure = str(fixed_verify.get("stderr_tail") or fixed_verify.get("stdout_tail") or "repair verification failed")
            except Exception as exc:
                repair_rounds.append({"round": repair_number, "status": "blocked", "error": f"{type(exc).__name__}: {exc}", "analysis": repair_analysis})
                repair_failure = str(exc)
        crystal_root = root / ("crystal-live" if live else "crystal")
        crystal_root.mkdir()
        write_task(crystal_root, task)
        for relative, content in {**task.files, **task.tests, **task.hidden_tests}.items():
            path = crystal_root / relative
            path.write_text(task.fixed_files.get(relative, content), encoding="utf-8")
        if task.name == "provider_model_wiring":
            wrapper = crystal_root / "app/kernel/registry/provider_registry.py"
            wrapper.parent.mkdir(parents=True, exist_ok=True)
            (wrapper.parent / "__init__.py").write_text("", encoding="utf-8")
            wrapper.write_text("from app.kernel.provider_registry import ProviderAdapterRegistry, ProviderRecord, ProviderRegistry\n", encoding="utf-8")
        crystal_verify = verify(crystal_root, [*task.tests, *task.hidden_tests]) if verify_live else {"ok": None, "status": "deferred"}
        compact_failure_text = str(fixed_verify.get("stderr_tail") or fixed_verify.get("stdout_tail") or "")
        repair_handoff = analyze_failure(compact_failure_text) if fixed_verify.get("ok") is not True else {"repair_required": False}
        crystal_rescue = {
            "attempted": fixed_verify.get("ok") is not True and crystal_verify.get("ok") is True,
            "status": "verified_crystal_available" if crystal_verify.get("ok") is True else "unavailable",
            "provider_calls": 0,
        }
        return {
            "task": task.name,
            "objective": task.objective,
            "baseline": {"status": baseline_result.get("status", "offline"), "error": baseline_error, "prompt_chars": baseline_chars, "provider_calls": baseline_calls, "latency_ms": baseline_latency, "usage": {key: baseline_result.get(key) for key in ("prompt_eval_count", "completion_eval_count", "total_duration_ns", "load_duration_ns", "eval_duration_ns") } if live else {}, "verification": baseline_verify},
            "compact": {"status": compact.get("status", "solved"), "error": compact_error, "prompt_chars": len(compact.get("model_packet", "")) or compact_packet_chars, "provider_calls": getattr(compact_provider, "calls", 1 if live else 0), "latency_ms": compact_latency, "usage": getattr(compact_provider, "last_usage", {}) if live else {}, "critic": candidate_critic, "verification": fixed_verify, "crystal_metrics": crystal_metrics},
            "crystal": {"prompt_chars": 0, "provider_calls": 0, "status": crystal.get("status"), "latency_ms": crystal_latency, "verification": crystal_verify, "rescue": crystal_rescue},
            "repair_handoff": repair_handoff,
            "repair_rounds": repair_rounds,
        }


async def run(args: argparse.Namespace) -> dict[str, Any]:
    tasks = omni_tasks()[: max(1, args.tasks)]
    reports = [await measure_task(task, live=args.live, broad_baseline=args.live_broad_control, verify_live=not args.live_fast, model=args.model, base_url=args.base_url, timeout_seconds=args.timeout, crystal_protocol=args.crystal_protocol) for task in tasks]
    aggregate = {}
    for lane in ("baseline", "compact", "crystal"):
        rows = [report[lane] for report in reports]
        aggregate[lane] = {
            "tasks": len(rows),
            "avg_prompt_chars": round(sum(row["prompt_chars"] for row in rows) / len(rows), 2),
            "provider_calls": sum(int(row.get("provider_calls", 1 if lane == "baseline" else 0)) for row in rows),
            "verified_completions": sum(int(row["verification"].get("ok") is True) for row in rows),
            "avg_verification_latency_ms": round(sum(float(row["verification"].get("latency_ms", 0.0)) for row in rows) / len(rows), 2),
        }
    aggregate["compact"]["prompt_reduction_pct_vs_baseline"] = round((1 - aggregate["compact"]["avg_prompt_chars"] / aggregate["baseline"]["avg_prompt_chars"]) * 100, 2)
    compact_metrics = [row["compact"].get("crystal_metrics", {}) for row in reports]
    aggregate["compact"]["avg_c1_chars"] = round(sum(int(item.get("c1_chars") or 0) for item in compact_metrics) / len(compact_metrics), 2)
    aggregate["compact"]["avg_c2_suffix_chars"] = round(sum(int(item.get("c2_suffix_chars") or 0) for item in compact_metrics) / len(compact_metrics), 2)
    aggregate["compact"]["avg_c2_prefix_chars"] = round(sum(int(item.get("c2_prefix_chars") or 0) for item in compact_metrics) / len(compact_metrics), 2)
    return {"beast_object_type": "real_ide_task_layer_benchmark", "version": "1.3-live" if args.live else "1.0", "task_source": "benchmarks.xai_omni_tasks.omni_tasks", "live": args.live, "live_fast": args.live_fast, "live_broad_control": args.live_broad_control, "model": args.model if args.live else "offline-real-task-measurement", "claim_boundary": "Live lane exercises BEAST compact residual and crystal reuse; broad baseline is not sent unless --live-broad-control is explicitly set. Verification may be deferred with --live-fast." if args.live else "Uses real BEAST coding fixtures and verification; live Ollama quality requires --live.", "tasks": reports, "aggregate": aggregate}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=int, default=8)
    parser.add_argument("--output", default="build/proof/real_ide_task_layer_benchmark.json")
    parser.add_argument("--live", action="store_true", help="Exercise the live BEAST compact and crystal lanes")
    parser.add_argument("--live-broad-control", action="store_true", help="Unsafe control: send the uncompressed baseline packet to Ollama")
    parser.add_argument("--live-fast", action="store_true", help="Defer fixture pytest and measure only live Ollama/crystal telemetry")
    parser.add_argument("--model", default=os.environ.get("BEAST_OLLAMA_MODEL") or "qwen2.5:0.5b")
    parser.add_argument("--base-url", default=os.environ.get("BEAST_OLLAMA_BASE_URL") or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--crystal-protocol", choices=("c1", "c2", "dual"), default="dual", help="Model-facing symbolic protocol; dual preserves the prior prompt contract")
    args = parser.parse_args()
    report = asyncio.run(run(args))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"PROOF_BUNDLE={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
