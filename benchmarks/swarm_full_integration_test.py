#!/usr/bin/env python3
"""Comprehensive Swarm Integration Test.

Verifies that all swarm systems (OpenClaw, NemoClaw, ZeroClaw) are:
1. Registered as active profiles.
2. Capable of executing their respective workflows.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.kernel.deployment.beast_cli_executor import BeastCLIExecutor
from app.kernel.execution.session_handshake import SessionHandshakeBuilder

class MockMCPBroker:
    def execute(self, request: Dict[str, Any], workspace_root: str) -> Dict[str, Any]:
        return {"executed": True, "result": "mock_success"}

def run_test_for_profile(profile: str, objective: str) -> Dict[str, Any]:
    print(f"--- Testing profile: {profile} ---")
    executor = BeastCLIExecutor(
        handshake_builder=SessionHandshakeBuilder(),
        mcp_broker=MockMCPBroker()  # Enable execution
    )
    
    # Workflow tailored to the profile
    workflow = {
        "steps": [
            {
                "step_id": "write_file",
                "action": "write dummy file",
                "role": profile,
                "target": "dummy.txt",
                "content": "hello"
            }
        ]
    }
    
    # Execute with approval to ensure gated systems run
    execution = executor.execute(
        objective=objective,
        workflow=workflow,
        mode=profile,
        workspace_root=str(ROOT),
        dry_run=False,
        approved=True,
    )
    return execution

def main() -> int:
    profiles = ["openclaw", "nemoclaw", "zeroclaw"]
    results = {}
    
    for profile in profiles:
        results[profile] = run_test_for_profile(
            profile, 
            f"Verify swarm profile {profile} is operational and capable of task execution."
        )
    
    print(json.dumps(results, indent=2, sort_keys=True))
    
    # Check if all succeeded
    all_passed = all(
        res.get("status") in ["succeeded", "dry_run"] 
        for res in results.values()
    )
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
