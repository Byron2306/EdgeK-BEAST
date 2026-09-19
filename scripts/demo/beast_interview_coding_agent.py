#!/usr/bin/env python3
"""Interview-grade live BEAST coding-agent demo.

Creates a fresh throwaway git workspace, drives the canonical AgentRun HTTP
ingress through the live BEAST gateway, uses local Ollama/Qwen reasoning, grants
only bounded worktree approvals, and prints a compact acceptance receipt.

The operator workspace is never mutated. The coding change must remain inside
BEAST's isolated worktree and finish with fresh verification + SourcePlan.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


TERMINAL = {
    "completed", "failed", "cancelled", "budget_exhausted", "policy_blocked",
    "refused",
}
SAFE_APPROVAL_TOOLS = {
    "worktree.bind",
    "worktree.replace_exact",
    "worktree.write_file",
    "worktree.verify",
    "worktree.sourceplan_draft",
}


def http_json(base: str, method: str, path: str, payload: dict[str, Any] | None = None, timeout: float = 30.0) -> dict[str, Any]:
    url = f"{base.rstrip('/')}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as res:
        raw = res.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(root), check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()


def make_fixture(target: Path | None = None) -> Path:
    root = target.expanduser().resolve() if target else Path(tempfile.mkdtemp(prefix="beast-interview-invoice-"))
    if root.exists() and any(root.iterdir()):
        raise RuntimeError(f"fixture directory is not empty: {root}")
    root.mkdir(parents=True, exist_ok=True)

    (root / "pricing.py").write_text(
        """def percentage_discount(amount: float, percent: float) -> float:\n"
        "    return amount * (percent / 100.0)\n",
        encoding="utf-8",
    )
    (root / "calculator.py").write_text(
        """from pricing import percentage_discount\n\n"
        "def invoice_total(amount: float, discount_percent: float) -> float:\n"
        "    # BUG: discount_percent is a percentage, not a currency amount.\n"
        "    return amount - discount_percent\n",
        encoding="utf-8",
    )
    (root / "test_invoice.py").write_text(
        """from calculator import invoice_total\n\n"
        "def test_percentage_discount():\n"
        "    assert invoice_total(200.0, 15.0) == 170.0\n\n"
        "def test_zero_discount():\n"
        "    assert invoice_total(80.0, 0.0) == 80.0\n",
        encoding="utf-8",
    )

    git(root, "init")
    git(root, "config", "user.name", "BEAST Interview Demo")
    git(root, "config", "user.email", "beast-interview@example.invalid")
    git(root, "add", ".")
    git(root, "commit", "-m", "Broken invoice fixture")
    return root


def preflight_gateway(base: str) -> None:
    candidates = [
        "/edgek/control-plane/desktop-compatibility",
        "/edgek/agent-runs?limit=1",
    ]
    last = None
    for path in candidates:
        try:
            http_json(base, "GET", path, timeout=5.0)
            return
        except Exception as exc:
            last = exc
    raise RuntimeError(f"BEAST gateway is not reachable at {base}: {last}")


def preflight_ollama(model: str, ollama_base: str) -> None:
    body = http_json(ollama_base, "GET", "/api/tags", timeout=8.0)
    names = {
        str(item.get("name") or item.get("model") or "")
        for item in body.get("models", [])
        if isinstance(item, dict)
    }
    if model not in names and not any(name.split(":")[0] == model.split(":")[0] for name in names):
        raise RuntimeError(f"Ollama model {model!r} not found. Available: {sorted(names)}")


def create_session(base: str, root: Path, model: str, objective: str) -> str:
    payload = {
        "root_path": str(root),
        "objective": objective,
        "mode": "implementer",
        "provider": "ollama",
        "model": model,
        "files": ["test_invoice.py", "calculator.py", "pricing.py"],
        "tools": [
            "Code Cortex Search",
            "Workspace File Read",
            "Isolated Test Verifier",
            "SourcePlan",
            "Evidence",
        ],
        "budget": {"tokens": 120000, "seconds": 1200, "cost_usd": 0},
    }
    result = http_json(base, "POST", "/edgek/ide/agent-sessions/create", payload)
    return str(result["session"]["session_id"])


def create_run(base: str, root: Path, session_id: str, model: str, objective: str, max_turns: int) -> str:
    payload = {
        "root_path": str(root),
        "session_id": session_id,
        "objective": objective,
        "mode": "implementer",
        "provider": "ollama",
        "model": model,
        "launch": False,
        "request": {
            "transport": "durable_agent_run_v2",
            "prompt": objective,
            "context_files": ["test_invoice.py", "calculator.py", "pricing.py"],
            "semantic_context": {
                "active_file": "test_invoice.py",
                "open_files": ["test_invoice.py", "calculator.py", "pricing.py"],
                "selection_summary": "interview demo: repair invoice percentage calculation",
            },
            "semantic_risk": {
                "high": False,
                "score": 2,
                "reasons": ["small local fixture", "isolated worktree", "tests available"],
            },
            "launch_strategy": "typed_planner",
            "proof": "beast_interview_coding_agent_v1",
            "max_tokens": 1024,
            "context_max_chars_each": 2400,
            "max_repair_rounds": 2,
            "approval_timeout_seconds": 120,
            "ollama_base_url": os.environ.get("BEAST_OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        },
        "budget": {
            "policy_profile": "balanced",
            "max_turns": max_turns,
            "max_cloud_cost": 0,
        },
    }
    result = http_json(base, "POST", "/edgek/agent-runs", payload)
    return str(result["run"]["run_id"])


def launch(base: str, root: Path, run_id: str, max_turns: int) -> dict[str, Any]:
    runq = urllib.parse.quote(run_id, safe="")
    return http_json(
        base, "POST", f"/edgek/agent-runs/{runq}/planner/execute",
        {"root_path": str(root), "max_turns": max_turns},
        timeout=20.0,
    )


def get_run(base: str, root: Path, run_id: str) -> dict[str, Any]:
    q = urllib.parse.urlencode({"root_path": str(root)})
    return http_json(base, "GET", f"/edgek/agent-runs/{urllib.parse.quote(run_id, safe='')}?{q}")["run"]


def get_events(base: str, root: Path, run_id: str) -> list[dict[str, Any]]:
    q = urllib.parse.urlencode({"root_path": str(root)})
    return http_json(base, "GET", f"/edgek/agent-runs/{urllib.parse.quote(run_id, safe='')}/events?{q}")["events"]


def get_approvals(base: str, root: Path, run_id: str) -> list[dict[str, Any]]:
    q = urllib.parse.urlencode({"root_path": str(root)})
    return http_json(base, "GET", f"/edgek/agent-runs/{urllib.parse.quote(run_id, safe='')}/approvals?{q}")["approvals"]


def approval_tool(approval: dict[str, Any]) -> str:
    request = approval.get("request") if isinstance(approval.get("request"), dict) else {}
    return str(request.get("tool_id") or approval.get("tool_id") or "")


def approve_safe(base: str, root: Path, run_id: str) -> list[tuple[str, str]]:
    resolved: list[tuple[str, str]] = []
    for approval in get_approvals(base, root, run_id):
        status = str(approval.get("status") or "").lower()
        approval_id = str(approval.get("approval_id") or approval.get("request_id") or "")
        tool = approval_tool(approval)
        if status != "pending" or not approval_id:
            continue
        if tool not in SAFE_APPROVAL_TOOLS:
            raise RuntimeError(f"demo stopped at non-demo approval: {tool or approval_id}")
        path = f"/edgek/agent-runs/{urllib.parse.quote(run_id, safe='')}/approvals/{urllib.parse.quote(approval_id, safe='')}"
        http_json(base, "POST", path, {
            "root_path": str(root),
            "approved": True,
            "scope": "ONCE",
            "operator_id": "operator:interview-demo",
            "reason": f"Interview demo approval for bounded {tool}",
        })
        resolved.append((approval_id, tool))
    return resolved


def summarize_event(event: dict[str, Any]) -> str:
    kind = str(event.get("event_type") or "")
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    tool = str(payload.get("tool_id") or "")
    status = str(payload.get("status") or "")
    if tool:
        return f"{kind}: {tool} {status}".strip()
    if kind == "agent.model.delta":
        return ""
    return kind


def wait_for_run(base: str, root: Path, run_id: str, timeout_s: float) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    start = time.monotonic()
    seen: set[str] = set()
    while True:
        run = get_run(base, root, run_id)
        events = get_events(base, root, run_id)
        for event in events:
            event_id = str(event.get("event_id") or "")
            if event_id in seen:
                continue
            seen.add(event_id)
            line = summarize_event(event)
            if line:
                print(f"  [{time.monotonic()-start:6.1f}s] {line}", flush=True)

        for approval_id, tool in approve_safe(base, root, run_id):
            print(f"  [{time.monotonic()-start:6.1f}s] APPROVED ONCE: {tool} ({approval_id})", flush=True)

        state = str(run.get("state") or "")
        if state in TERMINAL:
            return run, events
        if time.monotonic() - start > timeout_s:
            raise TimeoutError(f"AgentRun timed out in state {state}")
        time.sleep(0.75)


def acceptance(root: Path, run: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
    planner = checkpoint.get("planner") if isinstance(checkpoint.get("planner"), dict) else {}
    observations = planner.get("observations") if isinstance(planner.get("observations"), list) else []
    tools = [str(item.get("tool_id") or "") for item in observations if isinstance(item, dict)]

    failed_verify = [
        item for item in observations
        if isinstance(item, dict)
        and item.get("tool_id") == "worktree.verify"
        and item.get("status") == "failed"
    ]
    passed_verify = [
        item for item in observations
        if isinstance(item, dict)
        and item.get("tool_id") == "worktree.verify"
        and item.get("status") == "completed"
    ]
    sourceplans = [
        item for item in observations
        if isinstance(item, dict)
        and item.get("tool_id") == "worktree.sourceplan_draft"
        and item.get("status") == "completed"
    ]
    mutations = [
        item for item in observations
        if isinstance(item, dict)
        and item.get("tool_id") in {"worktree.replace_exact", "worktree.write_file"}
        and item.get("status") == "completed"
    ]

    operator_clean = git(root, "status", "--porcelain") == ""
    operator_head = git(root, "show", "HEAD:calculator.py")
    operator_still_broken = "return amount - discount_percent" in operator_head

    event_types = [str(event.get("event_type") or "") for event in events]
    cloud_switch = any(
        t in {"agent.provider.fallback", "agent.provider.switch"}
        and "strong-cloud" in json.dumps(event.get("payload") or {})
        for t, event in zip(event_types, events)
    )

    checks = {
        "run_completed": str(run.get("state") or "") == "completed",
        "indexed": "workspace.index" in tools,
        "worktree_bound": "worktree.bind" in tools,
        "exact_source_read": "workspace.read_range" in tools,
        "baseline_failed": bool(failed_verify),
        "bounded_mutation": bool(mutations),
        "fresh_verify_passed": bool(passed_verify),
        "sourceplan_ready": bool(sourceplans),
        "operator_workspace_clean": operator_clean,
        "operator_workspace_unchanged": operator_still_broken,
        "no_cloud_switch": not cloud_switch,
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "state": run.get("state"),
        "run_id": run.get("run_id"),
        "planner_turns": planner.get("turn"),
        "repair_cycles": planner.get("repair_cycles"),
        "tools": tools,
        "final_summary": planner.get("final_summary"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the BEAST interview coding-agent demo.")
    parser.add_argument("--gateway", default=os.environ.get("BEAST_GATEWAY_URL", "http://127.0.0.1:8101"))
    parser.add_argument("--ollama", default=os.environ.get("BEAST_OLLAMA_BASE_URL", "http://127.0.0.1:11434"))
    parser.add_argument("--model", default=os.environ.get("BEAST_OLLAMA_MODEL", "qwen2.5-coder:1.5b"))
    parser.add_argument("--max-turns", type=int, default=16)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--fixture", default="")
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()

    print("\nBEAST CODING AGENT // INTERVIEW GAUNTLET", flush=True)
    print("=======================================", flush=True)
    print(f"Gateway : {args.gateway}")
    print(f"Model   : {args.model} (local Ollama)")
    print("Boundary: isolated worktree; no final promotion\n")

    preflight_gateway(args.gateway)
    preflight_ollama(args.model, args.ollama)
    root = make_fixture(Path(args.fixture) if args.fixture else None)

    objective = (
        "Repair the invoice percentage-discount bug. The tests are authoritative. "
        "Use the existing pricing.percentage_discount helper rather than duplicating "
        "percentage arithmetic. Make the smallest safe change, verify it, and prepare "
        "a SourcePlan. Do not modify the operator workspace or promote the result."
    )
    print(f"Fixture : {root}")
    print("Expected baseline: test_percentage_discount FAIL, test_zero_discount PASS\n")

    # Show the baseline independently for the interviewer.
    baseline = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"], cwd=str(root),
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    print("PRE-BEAST BASELINE")
    print("------------------")
    print(baseline.stdout.strip())
    if baseline.returncode == 0:
        raise RuntimeError("fixture baseline unexpectedly passed")

    session_id = create_session(args.gateway, root, args.model, objective)
    run_id = create_run(args.gateway, root, session_id, args.model, objective, args.max_turns)
    print(f"\nSession : {session_id}")
    print(f"AgentRun : {run_id}")
    launched = launch(args.gateway, root, run_id, args.max_turns)
    print(f"Engine   : {(launched.get('execution') or {}).get('engine', 'typed_planner_v1')}")
    print("\nLIVE BEAST TIMELINE")
    print("-------------------")

    run, events = wait_for_run(args.gateway, root, run_id, args.timeout)
    receipt = acceptance(root, run, events)

    print("\nACCEPTANCE RECEIPT")
    print("------------------")
    for name, ok in receipt["checks"].items():
        print(f"{'PASS' if ok else 'FAIL':4}  {name}")
    print(f"\nResult: {'PROMOTE-CANDIDATE' if receipt['ok'] else 'REFUSE'}")
    print("Note  : demo intentionally stops before promotion/final apply.")

    if args.json_out:
        Path(args.json_out).expanduser().write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print(f"Proof : {Path(args.json_out).expanduser().resolve()}")

    return 0 if receipt["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
