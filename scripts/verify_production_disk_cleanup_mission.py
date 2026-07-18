#!/usr/bin/env python3
"""Verify the joined ComputePlane/native disk-cleanup production receipt."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.kernel.sensorium.contracts_hash import content_hash


def require(value, message):
    if not value: raise ValueError(message)


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("packet",type=Path); args=parser.parse_args()
    packet=json.loads(args.packet.read_text()); body=dict(packet); supplied=body.pop("evidence_digest","")
    require(supplied==content_hash(body),"production disk packet digest mismatch")
    receipt=packet.get("mission_receipt") or {}; sealed=dict(receipt); response_digest=sealed.pop("response_digest","")
    require(response_digest==content_hash(sealed),"mission receipt digest mismatch")
    require(packet.get("production_path_proven") is True,"production path is not proven")
    require(receipt.get("interface")=="cli" and receipt.get("final_status")=="verified_local_recurrence",
            "CLI production mission did not verify")
    require((receipt.get("provider_call_witness") or {}).get("during_execution")==0,"provider call occurred")
    delegate=packet.get("delegate_evidence") or {}
    require(all(delegate.get(key) is True for key in ("verified","clone3_into_cgroup","namespace_isolation",
        "filesystem_secret_isolation","ambient_network_denied","root_cleanup_confirmed","targets_absent")),
        "native delegate isolation proof is incomplete")
    require(delegate.get("applicability_proof_digest")==receipt.get("applicability_proof_digest") and
            delegate.get("authorization_receipt_digest")==receipt.get("authorization_receipt_digest"),
            "native delegate is not bound to mission authority")
    require((packet.get("reachability") or {}).get("production_routing_mode")=="explicit_enforce",
            "production routing was not enforced")
    require(packet.get("populated_zero") is True and packet.get("no_orphans") is True and
            (packet.get("capsule_cleanup") or {}).get("confirmed") is True,"capsule cleanup is incomplete")
    print(json.dumps({"verified":True,"evidence_digest":supplied,"mission_digest":response_digest,
        "worker_digest":delegate.get("worker_digest")},sort_keys=True)); return 0


if __name__=="__main__": raise SystemExit(main())
