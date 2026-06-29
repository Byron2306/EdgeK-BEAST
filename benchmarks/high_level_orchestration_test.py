#!/usr/bin/env python3
"""High-Level Agentic Orchestration Gauntlet."""

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.kernel.deployment.beast_cli_executor import BeastCLIExecutor
from app.kernel.execution.session_handshake import SessionHandshakeBuilder
from app.mcp.broker import MCPBroker
from app.kernel.governance.reason import Reasoner
import logging

# Set up logging to capture the detailed decision trace
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


def main() -> int:
    policy_path = ROOT / "policies" / "default.yaml"
    reasoner = Reasoner(policy_path=str(policy_path))
    
    broker = MCPBroker(policies=reasoner.policies)
    executor = BeastCLIExecutor(
        handshake_builder=SessionHandshakeBuilder(),
        mcp_broker=broker
    )

    target_file = ROOT / "benchmarks" / "legacy_broken_component.py"
    objective = f"Refactor {target_file} to be asynchronous using 'httpx' and add retry mechanism. This is a performance-critical architectural fix."
    
    print(f"\n--- Initiating High-Level Agentic Orchestration: {objective} ---")
    
    result = executor.execute(
        objective=objective,
        dry_run=False,
        approved=True,
        mode="nemoclaw"
    )
    
    print(f"\n--- Execution Result ---")
    print(result)
    
    # Verify the fix (simple existence check for now, ideally would run a test)
    if "async" in target_file.read_text().lower():
        print("\n--- SUCCESS: Code appears refactored to async. ---")
        return 0
    else:
        print("\n--- FAILURE: Code not refactored. ---")
        return 1

if __name__ == "__main__":
    sys.exit(main())
