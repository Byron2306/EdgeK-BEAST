"""Independent verification for stored BEAST evidence crystals."""
from __future__ import annotations

import hashlib
from typing import Any

from app.kernel.evidence.evidence_digest import canonical_bytes, sha256_digest


def verify_event_snapshot(events: list[dict[str, Any]], run_id: str) -> dict[str, Any]:
    previous = ""
    expected = 1
    for event in events:
        body = {
            "run_id": run_id,
            "sequence": event.get("sequence"),
            "event_type": event.get("event_type"),
            "legacy_type": event.get("legacy_type", ""),
            "created_at": event.get("created_at"),
            "payload": event.get("payload", {}),
        }
        calculated = "sha256:" + hashlib.sha256(previous.encode("utf-8") + canonical_bytes(body)).hexdigest()
        if event.get("sequence") != expected or event.get("previous_hash") != previous or event.get("event_hash") != calculated:
            return {"ok": False, "reason": "event_chain_mismatch", "sequence": event.get("sequence")}
        previous = calculated
        expected += 1
    return {"ok": True, "events": len(events), "head_hash": previous}


def verify_evidence_object(evidence: dict[str, Any], artifacts: dict[str, Any]) -> dict[str, Any]:
    core = {key: value for key, value in evidence.items() if key != "evidence_digest"}
    digest_ok = sha256_digest(core) == str(evidence.get("evidence_digest") or "")
    event_snapshot = artifacts.get("event_chain") if isinstance(artifacts.get("event_chain"), list) else []
    chain = verify_event_snapshot(event_snapshot, str(evidence.get("run_id") or ""))
    expected_head = str((evidence.get("provenance") or {}).get("event_chain_head") or "")
    chain_head_ok = bool(chain.get("ok")) and str(chain.get("head_hash") or "") == expected_head
    required = {str(item.get("kind")): str(item.get("digest")) for item in evidence.get("artifacts", []) if isinstance(item, dict)}
    artifact_results = {}
    for kind, expected in required.items():
        value = artifacts.get(kind)
        actual = sha256_digest(value)
        artifact_results[kind] = {"ok": actual == expected, "expected": expected, "actual": actual}
    ok = digest_ok and chain_head_ok and all(item["ok"] for item in artifact_results.values())
    return {
        "ok": ok,
        "evidence_id": evidence.get("evidence_id"),
        "digest_ok": digest_ok,
        "event_chain": {**chain, "head_matches": chain_head_ok},
        "artifacts": artifact_results,
    }
