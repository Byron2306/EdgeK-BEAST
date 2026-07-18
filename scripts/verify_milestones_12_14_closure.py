#!/usr/bin/env python3
"""Independent structural verifier for the Milestones 12–14 closure packet."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.kernel.compute.displacement_economics import DisplacementEconomics
from app.kernel.sensorium.contracts_hash import content_hash


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("packet", type=Path); args = parser.parse_args()
    packet = json.loads(args.packet.read_text())
    body = dict(packet); supplied = str(body.pop("evidence_digest", ""))
    require(supplied == content_hash(body), "closure packet digest mismatch")
    economics = packet.get("economics") or {}; DisplacementEconomics.validate(economics)
    observations = packet.get("provider_observations") or []
    require(len(observations) == int(economics["provider_calls_avoided"]), "provider call evidence count mismatch")
    require(all(int(item.get("provider_tokens") or 0) > 0 and float(item.get("provider_latency_ms") or 0) > 0
                for item in observations), "provider counters are incomplete")
    admission = packet.get("commons_admission") or {}
    require(admission.get("authority") == "remote_hypothesis" and admission.get("maximum_authority") == "verify_only",
            "Commons artifact exported execution authority")
    reproductions = packet.get("reproductions") or []
    node_ids = {item.get("node_id") for item in reproductions}
    require(len(node_ids) == len(reproductions) >= 2, "independent node-local receipts are missing")
    require(len({item.get("displacement_receipt_digest") for item in reproductions}) == len(reproductions),
            "node-local displacement measurements are not independently bound")
    require(all(item.get("status") == "locally_reproduced" and
                (item.get("authority") or {}).get("execution") == "node_local" for item in reproductions),
            "receiving node authority is not sovereign")
    aggregate = packet.get("federated_aggregate") or {}
    require(aggregate.get("advertised_claims_counted") == 0, "advertised displacement was counted")
    require(int(aggregate.get("independent_node_count") or 0) == len(node_ids), "federated node count mismatch")
    require(int(aggregate.get("provider_calls_avoided") or 0) ==
            sum(int(item.get("provider_calls_avoided") or 0) for item in reproductions),
            "federated displacement is not the sum of local receipts")
    require(packet.get("remote_physical_node_claimed") is False, "local drill overclaims a remote physical node")
    print(json.dumps({"verified": True, "evidence_digest": supplied,
                      "provider_calls_avoided": economics["provider_calls_avoided"],
                      "logical_nodes": len(node_ids)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
