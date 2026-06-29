#!/usr/bin/env python3
"""Real Swarm Integration Test: Proving Agentic Execution."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.kernel.deployment.beast_cli_executor import BeastCLIExecutor
from app.kernel.execution.session_handshake import SessionHandshakeBuilder
from app.mcp.broker import MCPBroker
from app.kernel.governance.reason import Reasoner

def main() -> int:
    # Initialize Reasoner with correct policy path
    policy_path = ROOT / "policies" / "default.yaml"
    reasoner = Reasoner(policy_path=str(policy_path))
    
    # Use real broker with correct policies
    broker = MCPBroker(policies=reasoner.policies)
    executor = BeastCLIExecutor(
        handshake_builder=SessionHandshakeBuilder(),
        mcp_broker=broker
    )
    
    target_file = ROOT / "swarm_proof.txt"
    if target_file.exists():
        target_file.unlink()
        
    workflow = {
        "steps": [
            {
                "step_id": "write_file",
                "action": "write proof of agentic capability",
                "role": "nemoclaw",
                "target": str(target_file),
                "content": "Swarm executed this task successfully."
            }
        ]
    }
    
    print("--- Initiating Real Swarm Execution ---")
    execution = executor.execute(
        objective="Prove agentic capability by writing a proof file.",
        workflow=workflow,
        mode="nemoclaw",
        workspace_root=str(ROOT),
        dry_run=False,
        approved=True,
    )
    
    print(json.dumps(execution, indent=2, sort_keys=True))
    
    if target_file.exists():
        print(f"\n--- Proof File Content: {target_file.read_text()} ---")
        return 0
    else:
        print("\n--- ERROR: Proof file not found! ---")
        return 1

if __name__ == "__main__":
    sys.exit(main())
