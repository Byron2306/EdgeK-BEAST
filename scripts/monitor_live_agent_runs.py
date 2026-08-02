#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from app.kernel.agents.run_state import TERMINAL_STATES as CANONICAL_TERMINAL_STATES

TERMINAL_STATES = {state.value for state in CANONICAL_TERMINAL_STATES} | {"paused", "waiting_for_approval"}
PLANNER_PROVIDERS = {"ollama", "local_ollama", "nvidia_nim", "nim", "local_nim"}


def http_json(base_url: str, method: str, path: str, payload: dict | None = None, timeout: float = 45.0) -> dict:
    url = f"{base_url.rstrip('/')}{path}"
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def create_probe_workspace() -> Path:
    root = Path(tempfile.mkdtemp(prefix="beast-agent-probe-"))
    (root / "README.md").write_text(
        textwrap.dedent(
            """
            # BEAST Agent Probe

            This workspace is safe for live ask/edit/agent monitoring.
            """
        ).strip() + "\n",
        encoding="utf-8",
    )
    (root / "sample.py").write_text(
        textwrap.dedent(
            """
            def greet(name: str) -> str:
                return f"hello, {name}"
            """
        ).lstrip(),
        encoding="utf-8",
    )
    subprocess.run(["git", "init"], cwd=str(root), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    subprocess.run(["git", "config", "user.name", "BEAST Probe"], cwd=str(root), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    subprocess.run(["git", "config", "user.email", "beast-probe@example.invalid"], cwd=str(root), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    subprocess.run(["git", "add", "README.md", "sample.py"], cwd=str(root), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    subprocess.run(["git", "commit", "-m", "Initial probe workspace"], cwd=str(root), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return root


def scenario_prompt(mode: str) -> str:
    if mode == "ask":
        return "Read README.md and explain what this workspace is for in one short paragraph."
    if mode == "edit":
        return "Update sample.py so greet trims surrounding whitespace from name before formatting. Verify mentally before proposing the patch."
    return "Inspect README.md and sample.py, describe the intended code change, then carry out the smallest safe implementation plan."


def scenario_ui_mode(mode: str) -> str:
    return "chat" if mode == "ask" else "implementer"


def create_session(base_url: str, root: Path, provider: str, model: str, mode: str) -> str:
    payload = {
        "root_path": str(root),
        "objective": scenario_prompt(mode),
        "mode": scenario_ui_mode(mode),
        "provider": provider,
        "model": model,
        "files": ["README.md", "sample.py"],
        "tools": [
            "Code Cortex Search",
            "Workspace File Read",
            "Isolated Test Verifier",
            "SourcePlan",
            "Evidence",
        ],
        "budget": {"tokens": 120000, "seconds": 1800, "cost_usd": 0},
    }
    response = http_json(base_url, "POST", "/edgek/ide/agent-sessions/create", payload, timeout=45.0)
    return str(response["session"]["session_id"])


def create_run(base_url: str, root: Path, session_id: str, provider: str, model: str, mode: str) -> tuple[str, dict]:
    prompt = scenario_prompt(mode)
    semantic_context = {
        "active_file": "sample.py" if mode != "ask" else "README.md",
        "open_files": ["README.md", "sample.py"],
        "selection_summary": "pair programmer live probe",
    }
    payload = {
        "root_path": str(root),
        "session_id": session_id,
        "objective": prompt,
        "mode": "chat" if mode == "ask" else "implementer",
        "provider": provider,
        "model": model,
        "launch": False if provider in PLANNER_PROVIDERS else True,
        "request": {
            "transport": "durable_agent_run_v2",
            "prompt": prompt,
            "context_files": ["README.md", "sample.py"],
            "semantic_context": semantic_context,
            "semantic_risk": {"high": mode != "ask", "score": 4 if mode != "ask" else 1, "reasons": ["live probe"]},
            "launch_strategy": "typed_planner",
            "max_tokens": 1536 if mode == "edit" else 1024,
            "context_max_chars_each": 3200,
            "max_repair_rounds": 2,
            "approval_timeout_seconds": 120,
        },
        "budget": {"tokens": 120000, "seconds": 1800, "cost_usd": 0},
    }
    response = http_json(base_url, "POST", "/edgek/agent-runs", payload, timeout=45.0)
    return str(response["run"]["run_id"]), response


def launch_planner(base_url: str, root: Path, run_id: str, max_turns: int = 5) -> dict:
    return http_json(
        base_url,
        "POST",
        f"/edgek/agent-runs/{urllib.parse.quote(run_id, safe='')}/planner/execute",
        {"root_path": str(root), "max_turns": max_turns},
        timeout=20.0,
    )


def get_detail(base_url: str, root: Path, run_id: str) -> dict:
    query = urllib.parse.urlencode({"root_path": str(root), "auto_recover": "true"})
    return http_json(base_url, "GET", f"/edgek/agent-runs/{urllib.parse.quote(run_id, safe='')}?{query}", timeout=20.0)["run"]


def get_events(base_url: str, root: Path, run_id: str) -> list[dict]:
    query = urllib.parse.urlencode({"root_path": str(root), "auto_recover": "true"})
    return http_json(base_url, "GET", f"/edgek/agent-runs/{urllib.parse.quote(run_id, safe='')}/events?{query}", timeout=20.0)["events"]


def get_approvals(base_url: str, root: Path, run_id: str) -> list[dict]:
    query = urllib.parse.urlencode({"root_path": str(root)})
    return http_json(base_url, "GET", f"/edgek/agent-runs/{urllib.parse.quote(run_id, safe='')}/approvals?{query}", timeout=20.0)["approvals"]


def approve_pending(base_url: str, root: Path, run_id: str) -> list[str]:
    approvals = get_approvals(base_url, root, run_id)
    resolved = []
    for approval in approvals:
        approval_id = str(approval.get("approval_id") or approval.get("request_id") or "")
        status = str(approval.get("status") or "")
        if not approval_id or status != "pending":
            continue
        http_json(
            base_url,
            "POST",
            f"/edgek/agent-runs/{urllib.parse.quote(run_id, safe='')}/approvals/{urllib.parse.quote(approval_id, safe='')}",
            {"root_path": str(root), "approved": True, "scope": "run"},
            timeout=20.0,
        )
        resolved.append(approval_id)
    return resolved


def monitor_run(base_url: str, root: Path, run_id: str, timeout_seconds: float, *, auto_approve: bool = False) -> dict:
    started = time.monotonic()
    emitted = set()
    timeline = []
    last_state = ""
    while True:
        detail = get_detail(base_url, root, run_id)
        events = get_events(base_url, root, run_id)
        for event in events:
            event_id = str(event.get("event_id") or "")
            if event_id in emitted:
                continue
            emitted.add(event_id)
            elapsed = round(time.monotonic() - started, 3)
            timeline.append(
                {
                    "elapsed_s": elapsed,
                    "type": event.get("event_type"),
                    "summary": event.get("summary") or event.get("message") or "",
                    "payload": event.get("payload") or {},
                }
            )
            print(json.dumps({"run_id": run_id, "elapsed_s": elapsed, "event": event.get("event_type"), "summary": timeline[-1]["summary"]}), flush=True)
        state = str(detail.get("state") or "")
        last_state = state or last_state
        if auto_approve and state == "waiting_for_approval":
            for approval_id in approve_pending(base_url, root, run_id):
                elapsed = round(time.monotonic() - started, 3)
                timeline.append(
                    {
                        "elapsed_s": elapsed,
                        "type": "probe.auto_approved",
                        "summary": approval_id,
                        "payload": {"approval_id": approval_id},
                    }
                )
                print(json.dumps({"run_id": run_id, "elapsed_s": elapsed, "event": "probe.auto_approved", "summary": approval_id}), flush=True)
        terminal_states = set(TERMINAL_STATES)
        if auto_approve:
            terminal_states.discard("waiting_for_approval")
        if state in terminal_states:
            return {"state": state, "detail": detail, "timeline": timeline}
        if time.monotonic() - started > timeout_seconds:
            return {"state": "timeout", "detail": detail, "timeline": timeline}
        time.sleep(1.0)


def run_probe(base_url: str, provider: str, model: str, mode: str, timeout_seconds: float, *, auto_approve: bool = False) -> dict:
    root = create_probe_workspace()
    session_id = create_session(base_url, root, provider, model, mode)
    run_id, create_response = create_run(base_url, root, session_id, provider, model, mode)
    launch_response = None
    launch_error = ""
    if provider in PLANNER_PROVIDERS:
        try:
            launch_response = launch_planner(base_url, root, run_id, max_turns=5)
        except urllib.error.URLError as error:
            launch_error = str(error)
        except Exception as error:  # pragma: no cover - live diagnostics
            launch_error = str(error)
    result = monitor_run(base_url, root, run_id, timeout_seconds, auto_approve=auto_approve)
    return {
        "provider": provider,
        "model": model,
        "mode": mode,
        "workspace": str(root),
        "session_id": session_id,
        "run_id": run_id,
        "create_response": create_response,
        "launch_response": launch_response,
        "launch_error": launch_error,
        **result,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("BEAST_GATEWAY_URL", "http://127.0.0.1:8103"))
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--auto-approve", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    scenarios = [
        ("nvidia_nim", os.environ.get("BEAST_NIM_MODEL", "meta/llama-3.1-70b-instruct"), "ask"),
        ("nvidia_nim", os.environ.get("BEAST_NIM_MODEL", "meta/llama-3.1-70b-instruct"), "edit"),
        ("nvidia_nim", os.environ.get("BEAST_NIM_MODEL", "meta/llama-3.1-70b-instruct"), "agent"),
        ("ollama", os.environ.get("BEAST_OLLAMA_MODEL", "qwen2.5-coder:1.5b"), "ask"),
        ("ollama", os.environ.get("BEAST_OLLAMA_MODEL", "qwen2.5-coder:1.5b"), "edit"),
        ("ollama", os.environ.get("BEAST_OLLAMA_MODEL", "qwen2.5-coder:1.5b"), "agent"),
    ]

    results = []
    for provider, model, mode in scenarios:
        print(f"=== {provider} {model} {mode} ===", flush=True)
        try:
            results.append(run_probe(args.base_url, provider, model, mode, args.timeout_seconds, auto_approve=args.auto_approve))
        except Exception as error:  # pragma: no cover - live diagnostics
            results.append({"provider": provider, "model": model, "mode": mode, "error": str(error)})
            print(json.dumps({"provider": provider, "mode": mode, "fatal": str(error)}), flush=True)

    output = json.dumps({"generated_at": time.time(), "results": results}, indent=2)
    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
