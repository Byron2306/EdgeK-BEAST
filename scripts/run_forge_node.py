#!/usr/bin/env python3
"""
Real Forge Node Runner (CPU-first)

Runs a ComputeForgeNode as a persistent background process on any Linux CPU machine
(Jetson, old laptop, edge device, etc.).

Usage:
    python scripts/run_forge_node.py --node-id my_edge_01 --repo /path/to/watch --interval 300

This is the real deployment path for forge nodes. No simulation.
"""

import argparse
import json
import signal
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

# Add parent to path for imports when run directly
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.kernel.compute_forge import ComputeForgeNode, ComputeLedger
from app.kernel.durable_inference_storage import DurableInferenceStorage


def main():
    parser = argparse.ArgumentParser(description="Run a real CPU Forge Node")
    parser.add_argument("--node-id", required=True, help="Unique node identifier (e.g. jetson_living_room)")
    parser.add_argument("--node-type", default="cpu_ollama", choices=["jetson", "rtx", "cpu_ollama", "edge_cpu"])
    parser.add_argument("--repo", default=".", help="Repository path to watch and fingerprint")
    parser.add_argument("--interval", type=int, default=300, help="Seconds between work cycles")
    parser.add_argument("--work", nargs="*", default=["fingerprint", "local_inference"],
                        help="Work types to perform each cycle")
    parser.add_argument("--ledger", default="data/compute_ledger.json", help="Path to persist ledger")
    parser.add_argument("--snapshot-dir", default="data/forge_nodes", help="Directory for per-node live snapshots")
    parser.add_argument("--propose-candidate", action="store_true", help="Propose a bounded candidate each cycle for central promotion")
    args = parser.parse_args()

    storage = DurableInferenceStorage()
    node = ComputeForgeNode(node_id=args.node_id, node_type=args.node_type, storage=storage)
    ledger = ComputeLedger()

    print(f"[ForgeNode] Starting {args.node_id} ({args.node_type})")
    print(f"[ForgeNode] Watching: {args.repo}")
    print(f"[ForgeNode] Cycle interval: {args.interval}s")
    print(f"[ForgeNode] Work per cycle: {args.work}")

    running = True

    def handle_sigterm(*_):
        nonlocal running
        print("\n[ForgeNode] Received shutdown signal, stopping...")
        running = False

    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    cycle = 0
    while running:
        cycle += 1
        print(f"\n[ForgeNode] Cycle {cycle} @ {datetime.now(timezone.utc).isoformat()}")

        for work in args.work:
            if work == "fingerprint":
                try:
                    fp = node.watch_repo(args.repo, target_paths=[])
                    print(f"  - Fingerprint: {fp.get('fingerprint_hash', 'N/A')[:16]}...")
                except Exception as e:
                    print(f"  - Fingerprint failed: {e}")

            elif work == "local_inference":
                try:
                    result = node.run_local_inference(
                        task_class="forge_background_query",
                        prompt="Summarize the current repository state in one sentence.",
                    )
                    print(f"  - Local inference: {result['result']['tokens']} tokens "
                          f"(real={result['result']['actual_inference']})")
                except Exception as e:
                    print(f"  - Local inference failed: {e}")

            elif work == "secret_scan":
                try:
                    node.perform_secret_scan(args.repo)
                    print("  - Secret scan complete")
                except Exception as e:
                    print(f"  - Secret scan failed: {e}")

            elif work == "test_map":
                try:
                    node.update_test_impact_map(args.repo, ["tests/"])
                    print("  - Test impact map updated")
                except Exception as e:
                    print(f"  - Test map update failed: {e}")

        if args.propose_candidate:
            try:
                fp = node.watch_repo(args.repo, target_paths=[])
                proposal = node.propose_crystallization_candidate(
                    candidate_name="forge_repo_fingerprint",
                    task_class="repo_fingerprint",
                    transform_type="deterministic",
                    impact_fingerprint=fp,
                    shadow_runs=3,
                )
                print(f"  - Candidate proposal: {proposal['candidate_name']}")
            except Exception as e:
                print(f"  - Candidate proposal failed: {e}")

        # Update ledger
        ledger.update_from_node(node)
        Path(args.ledger).parent.mkdir(parents=True, exist_ok=True)
        Path(args.ledger).write_text(json.dumps(ledger.to_dict(), indent=2))
        snapshot_path = Path(args.snapshot_dir) / f"{args.node_id}.json"
        node.persist_snapshot(snapshot_path)

        summary = node.get_earned_credits_summary()
        print(f"[ForgeNode] Credits earned this run: {summary['total_work_items']}")
        print(f"[ForgeNode] Profile: tokens={node.profile.total_tokens_displaced}, "
              f"candidates={node.profile.total_candidates_produced}, "
              f"stale_fp={node.profile.stale_fingerprints_caught}")
        print(f"[ForgeNode] Snapshot: {snapshot_path}")

        if running:
            time.sleep(args.interval)

    print("[ForgeNode] Shutdown complete. Final ledger written.")


if __name__ == "__main__":
    main()
