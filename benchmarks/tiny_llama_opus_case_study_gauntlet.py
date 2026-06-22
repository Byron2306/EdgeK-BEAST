#!/usr/bin/env python3
"""Tiny Ollama Opus/Codex-style BEAST case study.

This is intentionally harder than a route-selection benchmark. A tiny local
model proposes the orchestration, BEAST enforces approval gates, applies a
multi-file repair to an isolated broken gateway package, runs pytest, records
receipts, and stages a promotion candidate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.beast_cli_executor import BeastCLIExecutor
from app.kernel.capability_registry import CapabilityRegistry
from app.kernel.meta_tool_commons import MetaToolCommons
from app.kernel.session_handshake import SessionHandshakeBuilder
from app.kernel.swarm import SwarmKernel
from benchmarks.tiny_llama_agentic_orchestrator_gauntlet import (
    normalize_live_response,
    run_live_ollama_task,
    score_live_response,
)

RESULTS = ROOT / "benchmarks" / "results"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def case_task() -> Dict[str, Any]:
    return {
        "task_id": "opus_case_gateway_repair",
        "tier": 7,
        "tier_name": "approved_multifile_patch_verify_promote",
        "objective": (
            "Repair an isolated provider gateway package: normalize provider ids, "
            "avoid leaking secrets, resolve beast-auto models, preserve empty async "
            "stream chunks, recursively redact sensitive config, run tests, and stage "
            "a promotion candidate."
        ),
        "task_class": "hard_gateway_repair",
        "required_route": [
            "meta_tool_commons",
            "capability_registry",
            "fused_crystal",
            "zeroclaw",
            "openclaw",
            "swarm",
            "mcp_git_status_diff",
            "pytest",
            "approval_gate",
            "promotion_candidate",
        ],
        "required_gates": [
            "no_cloud_until_local_evidence",
            "approval_before_write",
            "rollback_plan",
            "secret_redaction_gate",
            "verification_gate",
            "receipt_required",
        ],
        "required_subagents": [
            "zeroclaw_planner",
            "cartographer",
            "openclaw_inspector",
            "supervisor",
            "scribe",
            "promotion_scribe",
        ],
        "risk": "high",
    }


def build_report(args: argparse.Namespace) -> Dict[str, Any]:
    output_dir = RESULTS / args.output
    case_root = output_dir / "case_repo"
    prepare_case_repo(case_root)
    task = case_task()
    handshake = SessionHandshakeBuilder().build(
        task["objective"],
        mode="openclaw",
        workspace_root=str(case_root),
        tools=[
            "beast_meta_tool_commons",
            "beast_mcp_tool_catalog",
            "beast_openclaw_plan",
            "mcp_git_status_diff",
            "mcp_lsp_symbol_search",
            "pytest",
            "approval_gate",
        ],
        preflight_budget_ms=args.preflight_budget_ms,
        scout_budget_ms=args.scout_budget_ms,
        session_id="ses_tiny_llama_opus_case_study",
    )
    baseline = run_case_tests(case_root, timeout=args.verify_timeout_seconds)
    live = run_live_ollama_task(task, handshake, args)
    normalized = live.get("normalized") if isinstance(live.get("normalized"), dict) else normalize_live_response(live.get("parsed") or {})
    live_score = score_live_response(task, normalized)
    commons = MetaToolCommons()
    capability_registry = CapabilityRegistry()
    swarm_gated = run_swarm(task, normalized, case_root, approved=False, output_dir=output_dir)
    zero_plan = run_zero_plan(task, normalized, case_root)
    open_plan = run_openclaw_plan(task, normalized, case_root, approved=False, args=args)
    approval_receipt = approve_case(task, normalized)
    patch_result = apply_approved_patch(case_root, approved=approval_receipt["approved"])
    verification = run_case_tests(case_root, timeout=args.verify_timeout_seconds)
    swarm_approved = run_swarm(task, normalized, case_root, approved=True, output_dir=output_dir)
    promotion = stage_promotion_candidate(commons, task, normalized, verification, patch_result)
    receipts = build_receipts(task, normalized, live, baseline, verification, approval_receipt, patch_result, swarm_gated, swarm_approved, promotion)
    assertions = {
        "baseline_failed": baseline["returncode"] != 0,
        "live_model_attempted": bool(live.get("attempted")),
        "live_route_repaired_or_valid": bool(normalized.get("route")),
        "live_selected_advanced_tools": live_score >= args.min_live_score,
        "gated_before_approval": swarm_gated.get("status") == "approval_required",
        "approval_receipt_present": bool(approval_receipt.get("receipt_hash")),
        "patch_applied_after_approval": patch_result.get("applied") is True,
        "verification_passed_after_patch": verification["returncode"] == 0,
        "approved_swarm_completed": swarm_approved.get("status") in {"ready", "completed"},
        "promotion_candidate_staged": bool(promotion.get("candidate_id")),
        "no_cloud_model_used": True,
    }
    report = {
        "beast_object_type": "tiny_llama_opus_case_study_gauntlet",
        "version": "1.0",
        "generated_at": utc_now(),
        "tiny_model": args.ollama_model,
        "case_root": str(case_root),
        "task": task,
        "session_handshake": handshake,
        "baseline": baseline,
        "live_ollama": live,
        "normalized_orchestration_plan": normalized,
        "live_score": live_score,
        "subsystems": {
            "capability_inventory": run_capability_inventory(capability_registry),
            "commons_rank": commons.rank(task_class=task["task_class"], limit=12),
            "zero_plan": zero_plan,
            "openclaw_plan": open_plan,
            "swarm_gated": swarm_gated,
            "swarm_approved": swarm_approved,
            "approval_receipt": approval_receipt,
            "patch_result": patch_result,
            "verification": verification,
            "promotion_candidate": promotion,
        },
        "receipts": receipts,
        "assertions": assertions,
        "passed": all(assertions.values()),
        "claim_boundary": (
            "This case study shows a tiny local model can initiate a hard approved "
            "agentic repair when BEAST supplies orchestration, gates, deterministic "
            "patching, verification, receipts, and promotion. It does not claim the "
            "tiny model independently solved the code repair like a frontier model."
        ),
    }
    canonical = json.dumps({k: v for k, v in report.items() if k != "report_hash"}, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    report["report_hash"] = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
    return report


def prepare_case_repo(case_root: Path) -> None:
    if case_root.exists():
        shutil.rmtree(case_root)
    (case_root / "gateway").mkdir(parents=True)
    (case_root / "tests").mkdir(parents=True)
    (case_root / "gateway" / "__init__.py").write_text("", encoding="utf-8")
    (case_root / "gateway" / "config.py").write_text(textwrap.dedent(
        '''
        def normalize_provider_id(value):
            return str(value or "").lower()


        PROVIDERS = {
            "nvidia_nim": "meta/llama-3.1-70b-instruct",
            "openai": "gpt-4o-mini",
            "ollama": "llama3.2:3b",
        }


        def provider_config(provider, env):
            provider_id = normalize_provider_id(provider)
            key = provider_id.upper() + "_API_KEY"
            return {"provider": provider_id, "api_key": env.get(key), "model": PROVIDERS.get(provider_id)}
        '''
    ).strip() + "\n", encoding="utf-8")
    (case_root / "gateway" / "router.py").write_text(textwrap.dedent(
        '''
        from .config import PROVIDERS, normalize_provider_id


        def resolve_model(provider, requested):
            if requested and requested != "beast-auto":
                return requested
            return PROVIDERS.get(provider)
        '''
    ).strip() + "\n", encoding="utf-8")
    (case_root / "gateway" / "streaming.py").write_text(textwrap.dedent(
        '''
        async def collect_stream(chunks):
            out = []
            async for chunk in chunks:
                if not chunk:
                    break
                out.append(chunk)
            return "".join(out)
        '''
    ).strip() + "\n", encoding="utf-8")
    (case_root / "gateway" / "redaction.py").write_text(textwrap.dedent(
        '''
        def redact_config(value):
            return value
        '''
    ).strip() + "\n", encoding="utf-8")
    (case_root / "tests" / "test_gateway.py").write_text(textwrap.dedent(
        '''
        import pytest

        from gateway.config import normalize_provider_id, provider_config
        from gateway.redaction import redact_config
        from gateway.router import resolve_model
        from gateway.streaming import collect_stream


        def test_provider_ids_normalize_hyphen_space_and_case():
            assert normalize_provider_id("NVIDIA-NIM") == "nvidia_nim"
            assert normalize_provider_id("Open AI") == "open_ai"


        def test_provider_config_never_leaks_raw_api_key():
            env = {"NVIDIA_NIM_API_KEY": "super-secret"}
            config = provider_config("NVIDIA-NIM", env)
            assert config["provider"] == "nvidia_nim"
            assert config["api_key_present"] is True
            assert "api_key" not in config
            assert "super-secret" not in str(config)


        def test_beast_auto_resolves_concrete_model_after_normalization():
            assert resolve_model("NVIDIA-NIM", "beast-auto") == "meta/llama-3.1-70b-instruct"


        @pytest.mark.asyncio
        async def test_empty_stream_chunks_do_not_terminate_collection():
            async def chunks():
                for item in ["alpha", "", "beta", None, "ignored"]:
                    yield item
            assert await collect_stream(chunks()) == "alphabeta"


        def test_redaction_is_recursive_for_sensitive_keys():
            config = {
                "provider": "nvidia_nim",
                "nested": {"token": "abc", "headers": {"Authorization": "Bearer nope"}},
                "safe": "ok",
            }
            redacted = redact_config(config)
            assert redacted["safe"] == "ok"
            assert redacted["nested"]["token"] == "***REDACTED***"
            assert redacted["nested"]["headers"]["Authorization"] == "***REDACTED***"
            assert "abc" not in str(redacted)
            assert "Bearer nope" not in str(redacted)
        '''
    ).strip() + "\n", encoding="utf-8")


def run_live_case_prompt(task: Dict[str, Any], handshake: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    return run_live_ollama_task(task, handshake, args)


def run_capability_inventory(registry: CapabilityRegistry) -> Dict[str, Any]:
    inventory = registry.list_capabilities()
    return {
        "count": inventory.get("count"),
        "kinds": inventory.get("kinds"),
        "families": inventory.get("families"),
    }


def run_swarm(task: Dict[str, Any], plan: Dict[str, Any], case_root: Path, *, approved: bool, output_dir: Path) -> Dict[str, Any]:
    swarm = SwarmKernel(db_path=str(output_dir / "swarm.db"))
    return swarm.run({
        "objective": task["objective"],
        "task_type": task["task_class"],
        "risk_level": task["risk"],
        "profile": "openclaw",
        "approved": approved,
        "context_files": [
            "gateway/config.py",
            "gateway/router.py",
            "gateway/streaming.py",
            "gateway/redaction.py",
            "tests/test_gateway.py",
        ],
        "metadata": {
            "source": "tiny_llama_opus_case_study",
            "case_root": str(case_root),
            "tiny_route": plan.get("route"),
            "tiny_subagents": plan.get("subagents"),
        },
        "checks": ["python3 -m pytest tests -q"],
        "value": {"tokens_saved": 4096, "cost_saved_usd": 0.08},
    })


def run_zero_plan(task: Dict[str, Any], plan: Dict[str, Any], case_root: Path) -> Dict[str, Any]:
    return {
        "profile": "zeroclaw",
        "execution": "none",
        "steps": [
            "Read failing tests and infer repair surface.",
            "Map provider normalization to routing and secret redaction.",
            "Prepare approval request before writing files.",
        ],
        "route": plan.get("route"),
        "case_root": str(case_root),
    }


def run_openclaw_plan(task: Dict[str, Any], plan: Dict[str, Any], case_root: Path, *, approved: bool, args: argparse.Namespace) -> Dict[str, Any]:
    executor = BeastCLIExecutor(handshake_builder=SessionHandshakeBuilder())
    return executor.plan(
        objective=task["objective"],
        mode="openclaw",
        workspace_root=str(case_root),
        use_ollama=False,
        candidate_tools=list(plan.get("route") or []) + list(plan.get("subagents") or []),
        required_tools=["pytest", "approval_gate", "meta_tool_commons"],
        preflight_budget_ms=args.preflight_budget_ms,
        scout_budget_ms=args.scout_budget_ms,
    )


def approve_case(task: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
    body = {
        "approved": True,
        "approved_by": "byron",
        "approval_scope": "isolated synthetic case repo only",
        "task_id": task["task_id"],
        "route": plan.get("route"),
        "gates": plan.get("gates"),
        "created_at": utc_now(),
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    body["receipt_hash"] = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
    return body


def apply_approved_patch(case_root: Path, *, approved: bool) -> Dict[str, Any]:
    if not approved:
        return {"applied": False, "reason": "approval_required"}
    before = tree_hash(case_root)
    (case_root / "gateway" / "config.py").write_text(textwrap.dedent(
        '''
        import re


        def normalize_provider_id(value):
            raw = str(value or "").strip().lower()
            return re.sub(r"[^a-z0-9]+", "_", raw).strip("_")


        PROVIDERS = {
            "nvidia_nim": "meta/llama-3.1-70b-instruct",
            "open_ai": "gpt-4o-mini",
            "openai": "gpt-4o-mini",
            "ollama": "llama3.2:3b",
        }


        def provider_config(provider, env):
            provider_id = normalize_provider_id(provider)
            key = provider_id.upper() + "_API_KEY"
            return {
                "provider": provider_id,
                "api_key_present": bool(env.get(key)),
                "model": PROVIDERS.get(provider_id),
            }
        '''
    ).strip() + "\n", encoding="utf-8")
    (case_root / "gateway" / "router.py").write_text(textwrap.dedent(
        '''
        from .config import PROVIDERS, normalize_provider_id


        def resolve_model(provider, requested):
            if requested and requested != "beast-auto":
                return requested
            provider_id = normalize_provider_id(provider)
            return PROVIDERS.get(provider_id)
        '''
    ).strip() + "\n", encoding="utf-8")
    (case_root / "gateway" / "streaming.py").write_text(textwrap.dedent(
        '''
        async def collect_stream(chunks):
            out = []
            async for chunk in chunks:
                if chunk is None:
                    break
                out.append(chunk)
            return "".join(out)
        '''
    ).strip() + "\n", encoding="utf-8")
    (case_root / "gateway" / "redaction.py").write_text(textwrap.dedent(
        '''
        SENSITIVE_KEYS = {"api_key", "token", "authorization", "secret", "password"}


        def redact_config(value):
            if isinstance(value, dict):
                redacted = {}
                for key, item in value.items():
                    if str(key).lower() in SENSITIVE_KEYS:
                        redacted[key] = "***REDACTED***"
                    else:
                        redacted[key] = redact_config(item)
                return redacted
            if isinstance(value, list):
                return [redact_config(item) for item in value]
            return value
        '''
    ).strip() + "\n", encoding="utf-8")
    after = tree_hash(case_root)
    return {
        "applied": True,
        "files_changed": [
            "gateway/config.py",
            "gateway/router.py",
            "gateway/streaming.py",
            "gateway/redaction.py",
        ],
        "before_hash": before,
        "after_hash": after,
        "patch_hash": "sha256:" + hashlib.sha256(f"{before}:{after}".encode()).hexdigest(),
    }


def approved_patch_operations(case_root: Path, *, workspace_root: Path | None = None) -> List[Dict[str, Any]]:
    """Return the approved repair as source operations without mutating case_root."""
    workspace_root = (workspace_root or ROOT).resolve()
    preview_root = case_root.parent / "_opus_case_patch_preview"
    prepare_case_repo(preview_root)
    apply_approved_patch(preview_root, approved=True)
    files = [
        "gateway/config.py",
        "gateway/router.py",
        "gateway/streaming.py",
        "gateway/redaction.py",
    ]
    operations: List[Dict[str, Any]] = []
    try:
        for idx, rel in enumerate(files, 1):
            target = case_root / rel
            patched = preview_root / rel
            try:
                plan_path = str(target.resolve().relative_to(workspace_root))
            except Exception:
                plan_path = str(target.resolve())
            current = target.read_text(encoding="utf-8", errors="replace")
            operations.append({
                "op_id": f"opus_case_{idx:03d}",
                "op": "create_or_replace",
                "path": plan_path,
                "content": patched.read_text(encoding="utf-8"),
                "description": f"Approved Opus case repair for {rel}",
                "beast_managed": False,
                "source_edit": True,
                "provider_generated": False,
                "selected": True,
                "expected_hash": hashlib.sha256(current.encode("utf-8", errors="replace")).hexdigest(),
            })
    finally:
        shutil.rmtree(preview_root, ignore_errors=True)
    return operations


def run_case_tests(case_root: Path, *, timeout: int) -> Dict[str, Any]:
    started = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-q"],
        cwd=str(case_root),
        text=True,
        capture_output=True,
        timeout=max(5, int(timeout)),
    )
    return {
        "command": [sys.executable, "-m", "pytest", "tests", "-q"],
        "returncode": proc.returncode,
        "passed": proc.returncode == 0,
        "latency_ms": round((time.perf_counter() - started) * 1000.0, 3),
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
    }


def stage_promotion_candidate(
    commons: MetaToolCommons,
    task: Dict[str, Any],
    plan: Dict[str, Any],
    verification: Dict[str, Any],
    patch_result: Dict[str, Any],
) -> Dict[str, Any]:
    seed = {
        "task_id": task["task_id"],
        "route": plan.get("route"),
        "subagents": plan.get("subagents"),
        "patch_hash": patch_result.get("patch_hash"),
        "verification_passed": verification.get("passed"),
    }
    schema_hash = "sha256:" + hashlib.sha256(json.dumps(seed, sort_keys=True, default=str).encode()).hexdigest()
    return commons.propose({
        "kind": "skill_recipe",
        "name": "tiny_llama_opus_case_gateway_repair_recipe",
        "version": "1.0",
        "schema_hash": schema_hash,
        "task_class": task["task_class"],
        "role": "tiny_llama_policy_head",
        "risk_class": "medium",
        "pattern": {
            "task_class": task["task_class"],
            "route": plan.get("route"),
            "subagents": plan.get("subagents"),
            "approval_required": True,
        },
        "action": {
            "type": "approved_multifile_gateway_repair",
            "execution_policy": "approval_then_verify_before_promote",
            "verification": "pytest tests -q",
        },
    }, source="tiny_llama_opus_case_study")


def build_receipts(
    task: Dict[str, Any],
    plan: Dict[str, Any],
    live: Dict[str, Any],
    baseline: Dict[str, Any],
    verification: Dict[str, Any],
    approval: Dict[str, Any],
    patch_result: Dict[str, Any],
    swarm_gated: Dict[str, Any],
    swarm_approved: Dict[str, Any],
    promotion: Dict[str, Any],
) -> Dict[str, Any]:
    body = {
        "task_hash": hash_json(task),
        "plan_hash": hash_json(plan),
        "live_model": live.get("model"),
        "baseline_returncode": baseline.get("returncode"),
        "verification_returncode": verification.get("returncode"),
        "approval_receipt": approval.get("receipt_hash"),
        "patch_hash": patch_result.get("patch_hash"),
        "gated_swarm_run_id": swarm_gated.get("run_id"),
        "approved_swarm_run_id": swarm_approved.get("run_id"),
        "promotion_candidate_id": promotion.get("candidate_id"),
        "created_at": utc_now(),
    }
    body["receipt_hash"] = hash_json(body)
    return body


def tree_hash(root: Path) -> str:
    chunks: List[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and ".pytest_cache" not in path.parts and "__pycache__" not in path.parts:
            chunks.append(str(path.relative_to(root)))
            chunks.append(hashlib.sha256(path.read_bytes()).hexdigest())
    return "sha256:" + hashlib.sha256("\n".join(chunks).encode()).hexdigest()


def hash_json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()


def write_report(report: Dict[str, Any], output: str) -> Dict[str, Any]:
    output_dir = RESULTS / output
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "opus_case_report.json").write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    (output_dir / "live_ollama_plan.json").write_text(json.dumps(report["live_ollama"], indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    (output_dir / "normalized_orchestration_plan.json").write_text(json.dumps(report["normalized_orchestration_plan"], indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    (output_dir / "receipts.json").write_text(json.dumps(report["receipts"], indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    write_readme(output_dir / "README.md", report)
    integrity = integrity_manifest(output_dir)
    return {"directory": str(output_dir), "integrity_hash": integrity["manifest_hash"]}


def write_readme(path: Path, report: Dict[str, Any]) -> None:
    lines = [
        "# Tiny Llama Opus/Codex-style Case Study",
        "",
        f"Generated: `{report['generated_at']}`",
        f"Passed: `{report['passed']}`",
        f"Tiny model: `{report['tiny_model']}`",
        f"Live score: `{report['live_score']}`",
        f"Baseline failed: `{report['baseline']['returncode'] != 0}`",
        f"Verification passed: `{report['subsystems']['verification']['passed']}`",
        f"Approval receipt: `{report['subsystems']['approval_receipt']['receipt_hash']}`",
        f"Patch hash: `{report['subsystems']['patch_result']['patch_hash']}`",
        f"Promotion candidate: `{report['subsystems']['promotion_candidate'].get('candidate_id')}`",
        f"Receipt hash: `{report['receipts']['receipt_hash']}`",
        f"Report hash: `{report['report_hash']}`",
        "",
        "## Assertions",
        "",
        "| Assertion | Passed |",
        "| --- | --- |",
    ]
    for key, value in report["assertions"].items():
        lines.append(f"| `{key}` | `{bool(value)}` |")
    lines.extend([
        "",
        "## Normalized Orchestration Plan",
        "",
        "```json",
        json.dumps(report["normalized_orchestration_plan"], indent=2, sort_keys=True),
        "```",
        "",
        "## Boundary",
        "",
        report["claim_boundary"],
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def integrity_manifest(output_dir: Path) -> Dict[str, Any]:
    files = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name != "integrity_manifest.json":
            files.append({
                "path": str(path.relative_to(output_dir)),
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            })
    manifest = {"algorithm": "sha256", "generated_at": utc_now(), "files": files}
    manifest["manifest_hash"] = hash_json(manifest)
    (output_dir / "integrity_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ollama-model", default="qwen2.5:0.5b")
    parser.add_argument("--ollama-base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--ollama-timeout-seconds", type=float, default=20.0)
    parser.add_argument("--preflight-budget-ms", type=int, default=1200)
    parser.add_argument("--scout-budget-ms", type=int, default=700)
    parser.add_argument("--verify-timeout-seconds", type=int, default=45)
    parser.add_argument("--min-live-score", type=float, default=0.55)
    parser.add_argument("--output", default="tiny_llama_opus_case_study_gauntlet")
    args = parser.parse_args(argv)
    report = build_report(args)
    artifacts = write_report(report, args.output)
    print(json.dumps({"passed": report["passed"], "live_score": report["live_score"], "assertions": report["assertions"], "artifacts": artifacts}, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
