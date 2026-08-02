#!/usr/bin/env python3
"""Canonical BEAST AgentRun closure gauntlet using live Ollama planning."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from app.kernel.agents.ollama_planner_provider import OllamaPlannerProvider
from app.kernel.agents.planner_runtime import AgentPlannerRuntime
from app.kernel.agents.promotion_engine import PromotionEngine
from app.kernel.agents.run_engine import AgentRunCancelled, AgentRunEngine


def run(cmd: list[str], cwd: Path, *, check: bool = True, timeout: float = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=check, timeout=timeout)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_fixture(root: Path) -> None:
    (root / "calculator.py").write_text(
        '"""Invoice calculation domain."""\n\n'
        'from pricing import apply_discount\n\n'
        'def invoice_total(subtotal: float, discount_percent: float) -> float:\n'
        '    discounted = apply_discount(subtotal, discount_percent)\n'
        '    return round(discounted, 2)\n',
        encoding="utf-8",
    )
    (root / "pricing.py").write_text(
        '"""Pricing helpers."""\n\n'
        "def apply_discount(amount: float, percent: float) -> float:\n"
        "    # BUG: percent is treated as currency instead of a percentage.\n"
        "    return amount - percent\n",
        encoding="utf-8",
    )
    (root / "validation.py").write_text(
        '"""Input validation."""\n\n'
        "def validate_discount(percent: float) -> None:\n"
        "    if percent < 0:\n"
        '        raise ValueError("discount must be non-negative")\n',
        encoding="utf-8",
    )
    (root / "test_invoice.py").write_text(
        "import pytest\n\n"
        "from calculator import invoice_total\n"
        "from validation import validate_discount\n\n"
        "def test_percentage_discount():\n"
        "    assert invoice_total(200.0, 15.0) == 170.0\n\n"
        "def test_zero_discount():\n"
        "    assert invoice_total(80.0, 0.0) == 80.0\n\n"
        "def test_discount_above_100_is_rejected():\n"
        "    with pytest.raises(ValueError):\n"
        "        validate_discount(120.0)\n",
        encoding="utf-8",
    )
    run(["git", "init", "-q"], root)
    run(["git", "config", "user.email", "beast@example.test"], root)
    run(["git", "config", "user.name", "BEAST Closure"], root)
    run(["git", "add", "."], root)
    run(["git", "commit", "-qm", "seed canonical AgentRun defect"], root)


def create_run_approval(engine: AgentRunEngine, run_id: str) -> str:
    approval_id = "canonical-agent-tools"
    engine.store.create_approval(
        run_id,
        {
            "request_id": approval_id,
            "kind": "bounded_agent_tool_authority",
            "capabilities": [{"id": "worktree_mutation"}, {"id": "worktree_verification"}],
        },
    )
    engine.store.resolve_approval(
        run_id,
        approval_id,
        {"approved": True, "scope": "run", "resolved_by": "operator:canonical-closure"},
    )
    return approval_id


async def main_mission(root: Path, model: str, max_turns: int, ollama_url: str) -> dict[str, Any]:
    engine = AgentRunEngine(root)
    objective = (
        "Repair the invoice discount defect. Inspect the repository before editing. "
        "Create an isolated worktree, then run the existing pytest suite BEFORE any mutation "
        "to establish the failing baseline. Use that verifier output to diagnose, edit, and "
        "repair until all tests pass. Then inspect the diff and create a SourcePlan draft. "
        "Never promote it."
    )
    created = engine.create_run(
        session_id="canonical-ollama-closure",
        objective=objective,
        mode="agent",
        provider="ollama",
        model=model,
        request={"proof": "canonical_agent_run_ollama_v1"},
        budget={"max_turns": max_turns, "max_repair_cycles": 3},
    )
    run_id = created["run_id"]
    approval_id = create_run_approval(engine, run_id)
    provider = OllamaPlannerProvider(model=model, base_url=ollama_url, default_approval_id=approval_id, max_retries=3)
    probe = await provider.probe()
    if not probe["ok"]:
        raise RuntimeError(f"Ollama model not available: {model}; installed={probe['models']}")
    operator_baseline = {
        name: sha256_file(root / name) for name in ("calculator.py", "pricing.py", "validation.py", "test_invoice.py")
    }
    final = await AgentPlannerRuntime(engine, provider, max_turns=max_turns, max_repair_cycles=3).run(run_id)
    checkpoint = dict(final.get("checkpoint") or {})
    planner = dict(checkpoint.get("planner") or {})
    events = engine.store.events(run_id, after=0, limit=100000)
    event_types = [str(e.get("event_type") or "") for e in events]
    observations = planner.get("observations") if isinstance(planner.get("observations"), list) else []
    tool_ids = [str(o.get("tool_id") or "") for o in observations if isinstance(o, dict)]
    failed_verify = [
        o for o in observations if isinstance(o, dict) and o.get("tool_id") == "worktree.verify" and o.get("status") != "completed"
    ]
    passed_verify = [
        o for o in observations if isinstance(o, dict) and o.get("tool_id") == "worktree.verify" and o.get("status") == "completed"
    ]
    assertions = {
        "run_completed": final.get("state") == "completed",
        "ollama_was_provider": final.get("provider") == "ollama",
        "inspected_before_mutation": any(
            t.startswith("workspace.")
            for t in tool_ids[: max(1, tool_ids.index("worktree.bind") if "worktree.bind" in tool_ids else 1)]
        ),
        "worktree_bound": bool(checkpoint.get("worktree_root")),
        "no_operator_workspace_mutation_before_promotion": all(
            sha256_file(root / name) == digest for name, digest in operator_baseline.items()
        ),
        "verification_passed": bool(checkpoint.get("verification", {}).get("ok")) and bool(passed_verify),
        "repair_cycle_observed": bool(failed_verify) and int(planner.get("repair_cycles") or 0) >= 1,
        "sourceplan_ready": bool(checkpoint.get("sourceplan", {}).get("plan_id")),
        "event_chain_valid": bool(engine.store.verify_chain(run_id).get("ok")),
        "repair_event_present": "agent.repair.required" in event_types,
        "sourceplan_event_present": "agent.sourceplan.ready" in event_types,
    }
    if not all(assertions.values()):
        raise AssertionError(
            json.dumps(
                {"assertions": assertions, "tool_ids": tool_ids, "state": final.get("state"), "planner": planner},
                indent=2,
                default=str,
            )
        )

    promotion = PromotionEngine(root)
    evaluated = promotion.evaluate(run_id, requested_by="operator:canonical-closure")
    if not evaluated.get("eligible"):
        raise AssertionError(json.dumps(evaluated, indent=2, default=str))
    promotion_approval_id = str(evaluated["approval"]["approval_id"])
    promotion.engine.store.resolve_approval(
        run_id,
        promotion_approval_id,
        {"approved": True, "scope": "once", "resolved_by": "operator:canonical-closure"},
    )
    promoted = promotion.promote(run_id, approval_id=promotion_approval_id, commit_message="BEAST Ollama canonical closure")
    candidate_commit = str(promoted["candidate"]["commit"])

    run(["git", "cherry-pick", candidate_commit], root, timeout=30)
    post = run([sys.executable, "-m", "pytest", "-q"], root, check=False, timeout=120)
    post_ok = post.returncode == 0
    engine.emit(
        run_id,
        "agent.promotion.post_verified",
        {
            "candidate_commit": candidate_commit,
            "returncode": post.returncode,
            "stdout_sha256": hashlib.sha256(post.stdout.encode()).hexdigest(),
            "stderr_sha256": hashlib.sha256(post.stderr.encode()).hexdigest(),
            "ok": post_ok,
        },
    )
    if not post_ok:
        raise AssertionError(f"post-promotion verification failed\nSTDOUT:\n{post.stdout}\nSTDERR:\n{post.stderr}")
    return {
        "run_id": run_id,
        "model": model,
        "provider_probe": probe,
        "assertions": {**assertions, "promotion_candidate_created": True, "post_promotion_verified": True},
        "planner": {"turns": planner.get("turn"), "repair_cycles": planner.get("repair_cycles"), "tool_ids": tool_ids},
        "candidate_commit": candidate_commit,
        "post_verification": {"returncode": post.returncode, "stdout": post.stdout[-4000:], "stderr": post.stderr[-4000:]},
        "event_chain": engine.store.verify_chain(run_id),
    }


async def restart_probe(root: Path) -> dict[str, Any]:
    engine1 = AgentRunEngine(root)
    run = engine1.create_run(session_id="restart", objective="persist planner state", provider="ollama", model="restart-probe")
    run_id = run["run_id"]
    engine1.merge_checkpoint(
        run_id,
        {
            "planner": {
                "run_id": run_id,
                "turn": 4,
                "max_turns": 12,
                "status": "paused",
                "observations": [{"tool_id": "workspace.list", "status": "completed"}],
            }
        },
    )
    engine1.store.transition(run_id, "paused")
    del engine1
    engine2 = AgentRunEngine(root)
    loaded = engine2.store.get_run(run_id) or {}
    planner = dict((loaded.get("checkpoint") or {}).get("planner") or {})
    ok = loaded.get("state") == "paused" and planner.get("turn") == 4 and len(planner.get("observations") or []) == 1
    if not ok:
        raise AssertionError(f"restart persistence failed: {loaded}")
    return {"run_id": run_id, "persisted": True, "turn": planner.get("turn")}


async def cancellation_probe(root: Path) -> dict[str, Any]:
    engine = AgentRunEngine(root)
    run_id = engine.create_run(session_id="cancel", objective="cancel process tree")["run_id"]
    approval = create_run_approval(engine, run_id)
    await engine.execute_tool(run_id, "worktree.bind", {"objective": "cancellation probe"}, approval_id=approval)

    async def execute_long() -> None:
        try:
            await engine.execute_tool(
                run_id,
                "worktree.verify",
                {
                    "command": [
                        sys.executable,
                        "-c",
                        "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)']); time.sleep(120)",
                    ],
                    "timeout_seconds": 180,
                },
                approval_id=approval,
            )
        except (asyncio.CancelledError, AgentRunCancelled, Exception):
            return

    task = asyncio.create_task(execute_long())
    await asyncio.sleep(1.0)
    cancelled = await engine.cancel(run_id, "canonical_closure_test")
    await asyncio.wait_for(task, timeout=8.0)
    final = engine.finalize_cancel(run_id, "canonical_closure_test")
    process_signalled = int(cancelled.get("execution", {}).get("processes_signalled") or 0)
    ok = final.get("state") == "cancelled" and process_signalled >= 1
    if not ok:
        raise AssertionError({"final": final, "cancelled": cancelled})
    return {"run_id": run_id, "state": final.get("state"), "processes_signalled": process_signalled}


async def _all(root: Path, model: str, max_turns: int, ollama_url: str) -> dict[str, Any]:
    main_result = await main_mission(root, model, max_turns, ollama_url)
    restart_result = await restart_probe(root)
    cancellation_result = await cancellation_probe(root)
    return {"main_mission": main_result, "restart_probe": restart_result, "cancellation_probe": cancellation_result}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=os.environ.get("BEAST_OLLAMA_MODEL", "qwen2.5-coder:1.5b"))
    parser.add_argument(
        "--ollama-url",
        default=os.environ.get(
            "BEAST_OLLAMA_BASE_URL",
            os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
        ),
        help="Ollama server origin. Native /api paths are appended automatically.",
    )
    parser.add_argument("--max-turns", type=int, default=24)
    parser.add_argument("--workspace", default="")
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    started = time.time()
    temp = Path(args.workspace).expanduser().resolve() if args.workspace else Path(tempfile.mkdtemp(prefix="beast-ollama-closure-"))
    temp.mkdir(parents=True, exist_ok=True)
    report_path = temp / "canonical_agent_ollama_closure.json"
    try:
        write_fixture(temp)
        report = asyncio.run(_all(temp, args.model, args.max_turns, args.ollama_url))
        report.update(
            {
                "beast_object_type": "beast_canonical_agent_ollama_closure",
                "version": "1.0",
                "passed": True,
                "ollama_base_url": OllamaPlannerProvider(base_url=args.ollama_url).base_url,
                "duration_seconds": round(time.time() - started, 3),
                "workspace": str(temp),
            }
        )
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
        print(f"\nPROOF_BUNDLE={report_path}")
        return 0
    except Exception as exc:
        failure = {
            "beast_object_type": "beast_canonical_agent_ollama_closure",
            "version": "1.0",
            "passed": False,
            "error": repr(exc),
            "duration_seconds": round(time.time() - started, 3),
            "workspace": str(temp),
        }
        report_path.write_text(json.dumps(failure, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(failure, indent=2, sort_keys=True), file=sys.stderr)
        print(f"\nFAILURE_BUNDLE={report_path}", file=sys.stderr)
        return 1
    finally:
        if not args.keep and not args.workspace and report_path.exists():
            out = Path.cwd() / "build" / "proof" / f"canonical_agent_ollama_{int(time.time())}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(report_path, out)
            shutil.rmtree(temp, ignore_errors=True)
            print(f"COPIED_PROOF={out}")


if __name__ == "__main__":
    raise SystemExit(main())
