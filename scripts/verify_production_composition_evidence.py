#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.kernel.sensorium.contracts_hash import content_hash


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("admission", type=Path)
    parser.add_argument("mission", type=Path)
    parser.add_argument("reachability", type=Path)
    args = parser.parse_args()
    admission = json.loads(args.admission.read_text())
    response = json.loads(args.mission.read_text())
    reach = json.loads(args.reachability.read_text())
    receipt = response["receipt"]
    body = dict(receipt); supplied = body.pop("response_digest")
    require(supplied == content_hash(body), "mission response digest mismatch")
    promotion = admission["promotion_record"]
    require(receipt["crystal_digest"] == admission["crystal"]["artifact_digest"], "crystal artifact mismatch")
    require(receipt["promotion_record_digest"] == promotion["record_digest"], "promotion lifecycle mismatch")
    require(receipt["appraisal_ref"] == promotion["appraisal_ref"], "appraisal mismatch")
    require(receipt["final_status"] == "verified_local_recurrence", "mission did not verify")
    require(response["route"] == "production_crystal" and response["status"] == "ok", "normal response route failed")
    require(reach["active_attempts"] == 0 and not reach["bypass_counters"], "runtime has active or bypassed attempts")
    require(reach["module_dispositions"]["all_present_modules_classified"] is True, "compute modules remain unclassified")
    require(receipt["crystal_id"] in reach["promoted_crystals"], "promoted artifact is not reachable")
    counters = reach["call_counters"]
    for phase in ("begin", "authorize", "execute", "verify", "complete"):
        require(counters.get(f"physical_crystal.{phase}") == 1, f"missing lifecycle phase: {phase}")
    require(counters.get("sensorium.ingest") == 2 and counters.get("sensorium.episode.close") == 1,
            "Sensorium mission closure is incomplete")
    require(reach.get("production_routing_mode") == "explicit_enforce", "production routing is not enforced")
    interface = str(receipt.get("interface") or "")
    require(interface in {"api", "cli", "ide"}, "mission used an unreviewed interface")
    require(counters.get(f"interface.{interface}.mission.complete") == 1,
            f"mission did not return through {interface}")
    print(json.dumps({"verified": True, "response_digest": supplied,
                      "promotion_record_digest": promotion["record_digest"],
                      "crystal_digest": receipt["crystal_digest"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
