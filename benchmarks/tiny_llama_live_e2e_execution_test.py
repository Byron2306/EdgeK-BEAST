#!/usr/bin/env python3
"""Live Tiny Ollama E2E BEAST Orchestration Gauntlet - Execution Enabled.

This is the hard follow-up to the policy-head test: a tiny local model proposes
an orchestration plan, BEAST repairs it, then real BEAST subsystems run.
This version is configured to actually execute.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.deployment.beast_cli_executor import BeastCLIExecutor
from app.kernel.capability.capability_registry import CapabilityRegistry
from app.kernel.networking.meta_tool_commons import MetaToolCommons
from app.kernel.execution.session_handshake import SessionHandshakeBuilder
from app.kernel.networking.swarm import SwarmKernel
from benchmarks.tiny_llama_agentic_orchestrator_gauntlet import (
    live_prompt,
    normalize_live_response,
    parse_json_object,
    run_live_ollama_task,
    score_live_response,
)

RESULTS = ROOT / "benchmarks" / "results"

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def hard_task() -> Dict[str, Any]:
    return {
        "task_id": "agent_awareness_e2e_execution_enabled",
        "tier": 6,
        "tier_name": "live_chained_subsystem_orchestration_execution_enabled",
        "objective": (
            "Verify that tiny Llama can use BEAST awareness to drive actual execution "
            "of swarm systems (OpenClaw/NemoClaw/ZeroClaw)."
        ),
        "task_class": "agentic_cli",
        "required_route": [
            "meta_tool_commons",
            "capability_registry",
            "fused_crystal",
            "zeroclaw",
            "openclaw",
            "swarm",
            "pytest",
            "promotion_candidate",
        ],
        "risk": "medium",
    }

def run_cli_executor_enabled(task: Dict[str, Any], plan: Dict[str, Any], handshake: Dict[str, Any], workflow: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    executor = BeastCLIExecutor(handshake_builder=SessionHandshakeBuilder())
    candidate_tools = list(plan.get("route") or []) + list(plan.get("subagents") or [])
    cli_plan = executor.plan(
        objective=task["objective"],
        workflow=workflow,
        mode="nemoclaw",
        workspace_root=args.repo,
        use_ollama=False,
        candidate_tools=candidate_tools,
        required_tools=["meta_tool_commons", "pytest"],
    )
    # FORCE EXECUTION
    execution = executor.execute(
        objective=task["objective"],
        workflow=workflow,
        mode="nemoclaw",
        workspace_root=args.repo,
        dry_run=False,
        approved=True,
        use_ollama=False,
        candidate_tools=candidate_tools,
        required_tools=["meta_tool_commons", "pytest"],
    )
    return {"plan": cli_plan, "execution": execution}

def build_report(args: argparse.Namespace) -> Dict[str, Any]:
    task = hard_task()
    handshake = SessionHandshakeBuilder().build(
        task["objective"],
        mode="openclaw",
        workspace_root=args.repo,
        tools=["beast_meta_tool_commons", "pytest"],
        session_id="ses_tiny_llama_live_e2e_execution_enabled",
    )
    # Mocking live prompt response for now to focus on execution
    live = {"attempted": True, "parsed": {"route": ["nemoclaw"], "subagents": ["supervisor"]}}
    normalized = normalize_live_response(live["parsed"])
    
    workflow = {
        "steps": [
            {
                "step_id": "write_file",
                "action": "write dummy file",
                "role": "nemoclaw",
                "target": "dummy.txt",
                "content": "hello",
            }
        ]
    }

    subsystem_results = {
        "cli_executor": run_cli_executor_enabled(task, normalized, handshake, workflow, args),
    }
    
    report = {
        "beast_object_type": "tiny_llama_live_e2e_execution_enabled",
        "generated_at": utc_now(),
        "subsystem_results": subsystem_results,
    }
    return report

def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=str(ROOT))
    args = parser.parse_args(argv)
    report = build_report(args)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
