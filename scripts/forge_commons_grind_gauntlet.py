#!/usr/bin/env python3
"""Compute Forge -> Commons grind gauntlet.

Runs safe CPU-first Forge work and emits a Commons candidate feed:

- candidate proposals
- model-agnostic defensive crystals
- fused crystals
- meta-tool / skill / swarm recipe components
- mutation and ablation failure cases

This does not adopt anything. It stages potential crystallized compute for the
Commons registration pipeline.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.kernel.commons_space_registry import CommonsSpaceRegistry
from app.kernel.compute_forge import ComputeForgeNode


LATEST_RECEIPT = ROOT / "benchmarks" / "results" / "forge_commons_grind_gauntlet_latest.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Forge grind and expose Commons candidates")
    parser.add_argument("--node-id", default="local_cpu_forge_commons")
    parser.add_argument("--node-type", default="cpu_ollama", choices=["jetson", "rtx", "cpu_ollama", "edge_cpu"])
    parser.add_argument("--repo", default=str(ROOT))
    parser.add_argument("--max-crystals", type=int, default=4)
    parser.add_argument("--snapshot-dir", default=str(ROOT / "data" / "forge_nodes"))
    parser.add_argument("--output", default=str(LATEST_RECEIPT))
    args = parser.parse_args()

    node = ComputeForgeNode(args.node_id, node_type=args.node_type)
    fingerprint = node.watch_repo(args.repo, target_paths=[])
    proposal = node.propose_crystallization_candidate(
        candidate_name="forge_commons_reuse_boundary",
        task_class="commons_crystallized_compute_reuse",
        transform_type="deterministic_reuse_boundary",
        impact_fingerprint=fingerprint,
        shadow_runs=3,
    )
    mining = node.mine_defensive_crystals(
        args.repo,
        objectives=[
            "verify Commons privacy boundaries",
            "rank safe local verifier candidates",
            "detect stale fingerprint risk",
            "summarize mutation and ablation failures",
        ],
        target_model="qwen2.5:0.5b",
        teacher_model="local_beast_reference",
        max_crystals=args.max_crystals,
    )
    pack = node.build_crystal_amplification_pack(mining["crystals"], target_model="qwen2.5:0.5b")
    fused = node.fuse_inference_crystals(
        name="commons_space_registration_operator",
        task_class="commons_space_registration",
        crystals=mining["crystals"],
        meta_tools=[
            {"name": "meta_tool_commons_ranker"},
            {"name": "commons_privacy_scrubber"},
        ],
        skills=[
            {"name": "space_manifest_packager"},
            {"name": "live_replay_verifier"},
        ],
        swarm_recipes=[
            {"name": "zeroclaw_no_exec_plan"},
            {"name": "openclaw_local_evidence_replay"},
        ],
        target_model="qwen2.5:0.5b",
    )
    comparison = node.compare_amplified_tiny_model(pack, big_model_label="frontier_reference")
    failures = node.mutation_ablation_backlog(
        space_id="forge_generated_commons_space_candidate",
        crystals=mining["crystals"],
        fused_crystals=[fused],
    )
    feed = node.commons_candidate_feed(include_failures=True)
    snapshot_path = Path(args.snapshot_dir) / f"{args.node_id}.json"
    snapshot = node.persist_snapshot(snapshot_path)
    registry_candidates = CommonsSpaceRegistry().registration_candidates(limit=50)

    receipt = {
        "beast_object_type": "forge_commons_grind_gauntlet_receipt",
        "version": "1.0",
        "node": node.profile.to_dict(),
        "fingerprint_hash": fingerprint.get("fingerprint_hash"),
        "proposal": proposal,
        "mining": {
            "crystal_count": mining.get("crystal_count"),
            "crystals": mining.get("crystals"),
        },
        "amplification_pack": {
            "pack_hash": pack.get("pack_hash"),
            "crystal_count": pack.get("crystal_count"),
            "tokens_displaced_estimate": pack.get("tokens_displaced_estimate"),
        },
        "fused_crystal": fused,
        "comparison": comparison,
        "mutation_ablation_backlog": failures,
        "commons_candidate_feed": feed,
        "snapshot_path": str(snapshot_path),
        "snapshot_candidate_count": (snapshot.get("commons_candidate_feed") or {}).get("candidate_count"),
        "registry_forge_candidate_count": registry_candidates.get("forge_candidate_count"),
        "success": bool(feed.get("candidate_count") and failures.get("case_count")),
        "claim_boundary": "Forge grind stages candidates and failure oracles; Commons adoption still requires privacy scan, replay, approval, and receipts.",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt["receipt_path"] = str(output)
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
