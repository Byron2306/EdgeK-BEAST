"""Two-phase, fail-closed proof of continuity across a real host reboot."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import tempfile
import time
from dataclasses import dataclass, asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from app.kernel.sensorium.adapters import current_boot_id


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":")).encode()


def _digest(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dict(value), handle, indent=2, sort_keys=True)
            handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sqlite_rows(path: Path, query: str) -> list[list[Any]]:
    if not path.exists():
        return []
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try: return [list(row) for row in connection.execute(query).fetchall()]
    finally: connection.close()


def guardian_state(path: Path) -> dict[str, Any]:
    generations = _sqlite_rows(path, "SELECT identity_key,generation FROM generations ORDER BY identity_key")
    leases = _sqlite_rows(path, "SELECT lease_id,lifecycle_state,health_state,payload FROM leases ORDER BY lease_id")
    return {
        "ledger_digest": file_digest(path) if path.exists() else "",
        "generations": {str(key): int(value) for key, value in generations},
        "leases": [{"lease_id": row[0], "lifecycle_state": row[1], "health_state": row[2],
                    "payload_digest": "sha256:" + hashlib.sha256(str(row[3]).encode()).hexdigest()} for row in leases],
    }


def capability_state(path: Path) -> dict[str, Any]:
    consumed = _sqlite_rows(path, "SELECT capability_id,request_digest,authority,issuer_key_id FROM consumed_capabilities ORDER BY capability_id")
    revoked = _sqlite_rows(path, "SELECT capability_id,authority,issuer_key_id,reason FROM revoked_capabilities ORDER BY capability_id")
    return {"consumed": consumed, "revoked": revoked, "ledger_digest": file_digest(path) if path.exists() else ""}


def sensorium_state(path: Path) -> dict[str, Any]:
    rows = _sqlite_rows(path, "SELECT offset,record_hash FROM sensor_events ORDER BY offset DESC LIMIT 1")
    return {"offset": int(rows[0][0]) if rows else 0, "head_hash": str(rows[0][1]) if rows else "",
            "journal_digest": file_digest(path) if path.exists() else ""}


def promotion_state(path: Path) -> dict[str, Any]:
    if not path.exists(): return {"records": {}, "registry_digest": ""}
    records = _json(path)
    return {"records": {key: value.get("record_digest", "") for key, value in sorted(records.items())},
            "registry_digest": file_digest(path)}


@dataclass(frozen=True)
class ContinuityPaths:
    tpm_evidence: Path
    arda_appraisal: Path
    guardian_ledger: Path
    capability_ledger: Path
    sensorium_journal: Path
    promotion_registry: Path


def _bound_evidence(paths: ContinuityPaths) -> dict[str, Any]:
    tpm = _json(paths.tpm_evidence)
    arda = _json(paths.arda_appraisal)
    appraisal = arda.get("appraisal", arda)
    return {
        "tpm": {"boot_id": tpm.get("boot_id"), "evidence_digest": tpm.get("evidence_digest"),
                "eligible_for_commons": tpm.get("eligible_for_commons"), "collected_at": tpm.get("collected_at"),
                "file_digest": file_digest(paths.tpm_evidence)},
        "arda": {"appraisal_ref": appraisal.get("appraisal_ref"), "state": appraisal.get("state", arda.get("status")),
                 "evidence_digest": appraisal.get("evidence_digest"), "expires_at": appraisal.get("expires_at", 0),
                 "policy_generation": appraisal.get("policy_generation"), "signature": appraisal.get("signature", ""),
                 "file_digest": file_digest(paths.arda_appraisal)},
        "guardian": guardian_state(paths.guardian_ledger),
        "capabilities": capability_state(paths.capability_ledger),
        "sensorium": sensorium_state(paths.sensorium_journal),
        "promotions": promotion_state(paths.promotion_registry),
    }


def create_preboot_witness(paths: ContinuityPaths, *, signer=None, now: float | None = None) -> dict[str, Any]:
    now = time.time() if now is None else now
    state = _bound_evidence(paths)
    boot = current_boot_id()
    if state["tpm"]["boot_id"] != boot or not state["tpm"]["eligible_for_commons"]:
        raise PermissionError("pre-boot TPM evidence is not current and eligible")
    if not state["arda"]["signature"] or state["arda"]["evidence_digest"] != state["tpm"]["evidence_digest"]:
        raise PermissionError("pre-boot ARDA appraisal is not signed and TPM-bound")
    if float(state["arda"]["expires_at"] or 0) <= now:
        raise PermissionError("pre-boot ARDA appraisal is expired")
    if not state["guardian"]["generations"] or not state["promotions"]["records"] or not state["sensorium"]["head_hash"]:
        raise PermissionError("reboot witness requires Guardian, promoted crystal, and Sensorium durable state")
    body = {"schema": "beast.reboot-continuity.preboot.v1", "boot_id": boot,
            "created_at": datetime.fromtimestamp(now, timezone.utc).isoformat(), "created_at_unix": now,
            "state": state, "stale_runtime_authority_must_not_survive": True}
    body["witness_digest"] = _digest(body)
    body["signature"] = base64.b64encode(signer.sign(_canonical(body))).decode() if signer else ""
    return body


def verify_preboot_witness(witness: Mapping[str, Any], *, verifier=None) -> None:
    body = dict(witness); signature = body.pop("signature", ""); claimed = body.pop("witness_digest", "")
    if claimed != _digest(body): raise ValueError("pre-boot witness digest mismatch")
    if verifier is not None:
        if not signature: raise PermissionError("pre-boot witness is unsigned")
        verifier.verify(base64.b64decode(signature, validate=True), _canonical({**body, "witness_digest": claimed}))


def verify_postboot(preboot: Mapping[str, Any], paths: ContinuityPaths, *, verifier=None,
                    recurrence_receipt: Mapping[str, Any] | None = None, now: float | None = None) -> dict[str, Any]:
    verify_preboot_witness(preboot, verifier=verifier)
    now = time.time() if now is None else now
    before, after = preboot["state"], _bound_evidence(paths)
    old_boot, new_boot = str(preboot["boot_id"]), current_boot_id()
    active_states = {"reserved", "handed_off", "healthy", "unhealthy"}
    active_before = [item for item in before["guardian"]["leases"] if item["lifecycle_state"] in active_states]
    active_after = [item for item in after["guardian"]["leases"] if item["lifecycle_state"] in active_states]
    checks: dict[str, bool] = {
        "boot_id_changed": bool(old_boot and new_boot and old_boot != new_boot),
        "fresh_tpm_matches_boot": after["tpm"]["boot_id"] == new_boot and bool(after["tpm"]["eligible_for_commons"]),
        "fresh_arda_binds_tpm": after["arda"]["state"] in {"verified", "appraised"} and after["arda"]["evidence_digest"] == after["tpm"]["evidence_digest"] and float(after["arda"]["expires_at"] or 0) > now,
        "attestation_is_postboot_fresh": after["tpm"]["evidence_digest"] != before["tpm"]["evidence_digest"] and after["arda"]["appraisal_ref"] != before["arda"]["appraisal_ref"],
        "promotion_records_preserved": before["promotions"]["records"] == after["promotions"]["records"],
        "sensorium_chain_not_rolled_back": int(after["sensorium"]["offset"]) >= int(before["sensorium"]["offset"]),
        "consumed_capabilities_not_revived": {tuple(x) for x in before["capabilities"]["consumed"]}.issubset({tuple(x) for x in after["capabilities"]["consumed"]}),
        "revocations_not_revived": {tuple(x) for x in before["capabilities"]["revoked"]}.issubset({tuple(x) for x in after["capabilities"]["revoked"]}),
        "guardian_generation_not_rolled_back": all(int(after["guardian"]["generations"].get(key, -1)) >= int(value) for key, value in before["guardian"]["generations"].items()),
        "guardian_recovered_active_descriptors": bool(active_after) and len(active_after) >= len(active_before),
        "old_runtime_authority_invalidated": old_boot != new_boot,
        "fresh_recurrence_verified": bool(recurrence_receipt and recurrence_receipt.get("verified") and recurrence_receipt.get("boot_id") == new_boot and recurrence_receipt.get("provider_calls") == 0),
    }
    body = {"schema": "beast.reboot-continuity.receipt.v1", "preboot_witness_digest": preboot["witness_digest"],
            "old_boot_id": old_boot, "new_boot_id": new_boot, "verified_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
            "checks": checks, "before": before, "after": after,
            "recurrence_receipt_digest": (recurrence_receipt or {}).get("receipt_digest", ""),
            "verified": all(checks.values())}
    body["receipt_digest"] = _digest(body)
    if not body["verified"]:
        failed = ",".join(sorted(name for name, passed in checks.items() if not passed))
        raise PermissionError("post-boot continuity checks failed: " + failed)
    return body


def write_receipt(path: Path, value: Mapping[str, Any]) -> None:
    _atomic_json(path, value)
