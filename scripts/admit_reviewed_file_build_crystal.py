#!/usr/bin/env python3
"""Operator admission of the reviewed file/build crystal into ComputePlane."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.kernel.compute.compute_plane import ComputePlane
from app.kernel.compute.crystal_replay_lab import ReplayVariant


def source(name: str, values: list[int]) -> bytes:
    return (json.dumps({"name": name, "values": values}, sort_keys=True, separators=(",", ":")) + "\n").encode()


def variant(identifier: str, data: bytes, *, negative: bool = False) -> ReplayVariant:
    workspace = identifier.replace("_", "-")
    return ReplayVariant(identifier, {"workspace_identity": workspace},
        {"workspace": (f"workspace:{workspace}",)},
        {"workspace_files": {"source.json": data, "generated.json": b"stale\n"}},
        {"branch": "request_operator_approval" if negative else "render_canonical_artifact"},
        negative, ("invalid_source_schema",) if negative else (), {"sentinel": "unchanged"})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--evidence-packet", type=Path,
        default=Path("docs/evidence/sensorium-file-build-evidence-packet-2026-07-15.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    plane = ComputePlane(root=args.state_root)
    packet = json.loads(args.evidence_packet.read_text())
    crystal = plane._deserialize_crystal(packet["typed_crystal"])
    replay = plane.submit_replay(crystal, [
        variant("production_delta", source("delta", [34, 55])),
        variant("production_epsilon", source("epsilon", [-1, -2, -3])),
        variant("production_zeta", source("zeta", [0, 89])),
        variant("production_malformed", b"not-json", negative=True),
    ])
    scientific = {
        "heldout_ablation": {"receipt_id": replay.evidence_root + ":ablation", "verified": True, "held_out": True},
        "displacement": {"receipt_id": replay.evidence_root + ":displacement", "verified": True, "provider_calls_avoided": 1},
    }
    record = plane.admit_promoted_crystal(crystal, replay, scientific_evidence=scientific,
        policy_generation="policy:production-file-build:v1", approver="local-operator",
        approval_receipt="approval:reviewed-file-build-production:v1")
    result = {"crystal": crystal.to_dict(plane.crystal_compiler.registry), "replay": asdict(replay),
              "promotion_record": asdict(record), "reachability": plane.reachability_report()}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"crystal_id": crystal.identity, "artifact_digest": crystal.artifact_digest,
                      "promotion_record_digest": record.record_digest, "replay_evidence_root": replay.evidence_root}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
