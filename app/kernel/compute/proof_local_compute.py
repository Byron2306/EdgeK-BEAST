"""CPU-first proof packets, staged transfer accounting, and LAN route planning.

The objects in this module are inert metadata.  They never grant adoption,
execute remote verifier commands, or move private artifact/KV payloads.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from app.kernel.networking.commons_privacy import CommonsPrivacyScrubber
from app.kernel.security.crystal_seal import canonical_bytes


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid proof-local timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("proof-local timestamps require a timezone")
    return parsed.astimezone(timezone.utc)


def sha256_payload(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def valid_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(char in "0123456789abcdef" for char in value[7:])
    )


PROOF_DEPTH = {
    "unverified_claim": 0.05,
    "manifest_valid": 0.20,
    "locally_replayed": 0.55,
    "locally_reproduced": 0.75,
    "adopted": 0.90,
    "promoted": 1.00,
}
LOAD_FACTOR = {"idle": 1.0, "low": 0.9, "medium": 0.65, "high": 0.30}


def build_receipt_packet(
    detail: Dict[str, Any],
    *,
    contributor_id: str,
    issued_at: str,
    expires_at: str,
    chain_head: str,
    declared_bundle_bytes: int = 0,
    bundle_sha256: str = "sha256:" + "0" * 64,
) -> Dict[str, Any]:
    manifest = detail.get("manifest") or {}
    receipt = detail.get("reduction_receipt") or {}
    artifacts = manifest.get("artifacts") or []
    verifier_bundles = manifest.get("verifier_bundles") or []
    artifact_index = [
        {
            "artifact_type": str(item.get("artifact_type") or "unknown"),
            "sha256": str(item.get("sha256") or ""),
            "bytes": max(0, int(item.get("bytes") or 0)),
        }
        for item in artifacts
    ]
    verifier_descriptions = [
        {
            "name": str(item.get("name") or item.get("verifier") or "verifier")[:120],
            "type": str(item.get("type") or item.get("kind") or "local_allowlisted")[:80],
            "hash": sha256_payload(item),
        }
        for item in verifier_bundles
    ]
    core = {
        "beast_object_type": "proof_receipt_packet",
        "version": "1.0",
        "contributor_id": contributor_id,
        "space_id": str(manifest.get("space_id") or ""),
        "manifest_hash": str(manifest.get("manifest_hash") or ""),
        "artifact_root_hash": sha256_payload(artifact_index),
        "task_class": str(manifest.get("task_class") or "unknown")[:120],
        "privacy_class": "public_metadata_only",
        "proof_depth": _proof_depth(detail),
        "verifier_bundle_hash": sha256_payload(verifier_descriptions),
        "verifier_descriptions": verifier_descriptions,
        "artifact_count": len(artifact_index),
        "declared_artifact_bytes": sum(item["bytes"] for item in artifact_index),
        "declared_bundle_bytes": max(0, int(declared_bundle_bytes)),
        "bundle_sha256": bundle_sha256,
        "replay_required": True,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "promotion_state": str((manifest.get("safety") or {}).get("promotion_state") or "quarantined_hypothesis"),
        "credit_eligible": False,
        "chain_head": chain_head,
        "reduction_claim_hash": sha256_payload(receipt.get("displacement") or {}),
        "authority": "remote_hypothesis",
    }
    core["packet_id"] = "prp_" + hashlib.sha256(canonical_bytes(core)).hexdigest()[:24]
    return core


def validate_receipt_packet(packet: Dict[str, Any], *, now: Optional[datetime] = None) -> Dict[str, Any]:
    errors: List[str] = []
    required = {
        "beast_object_type", "version", "packet_id", "contributor_id", "space_id",
        "manifest_hash", "artifact_root_hash", "task_class", "privacy_class",
        "proof_depth", "verifier_bundle_hash", "artifact_count",
        "declared_artifact_bytes", "declared_bundle_bytes", "bundle_sha256", "issued_at", "expires_at", "chain_head",
    }
    missing = sorted(required - set(packet))
    if missing:
        errors.append("missing fields: " + ", ".join(missing))
    if packet.get("beast_object_type") != "proof_receipt_packet":
        errors.append("invalid beast_object_type")
    for field_name in ("manifest_hash", "artifact_root_hash", "verifier_bundle_hash", "chain_head", "bundle_sha256"):
        if not valid_sha256(packet.get(field_name)):
            errors.append(f"invalid {field_name}")
    if packet.get("privacy_class") != "public_metadata_only":
        errors.append("receipt packet must be public_metadata_only")
    if packet.get("proof_depth") not in PROOF_DEPTH:
        errors.append("invalid proof_depth")
    if int(packet.get("artifact_count") or 0) < 0 or int(packet.get("artifact_count") or 0) > 128:
        errors.append("artifact_count out of bounds")
    if int(packet.get("declared_artifact_bytes") or 0) < 0 or int(packet.get("declared_artifact_bytes") or 0) > 25_000_000:
        errors.append("declared_artifact_bytes out of bounds")
    if int(packet.get("declared_bundle_bytes") or 0) <= 0 or int(packet.get("declared_bundle_bytes") or 0) > 25_000_000:
        errors.append("declared_bundle_bytes out of bounds")
    try:
        issued = parse_time(str(packet.get("issued_at") or ""))
        expires = parse_time(str(packet.get("expires_at") or ""))
        if expires <= (now or datetime.now(timezone.utc)) or expires <= issued:
            errors.append("receipt packet is expired or has an invalid lifetime")
    except ValueError as exc:
        errors.append(str(exc))
    privacy_findings = CommonsPrivacyScrubber().scan_payload(_unsigned(packet))
    if privacy_findings:
        errors.append("privacy scan failed")
    expected = dict(_unsigned(packet))
    packet_id = expected.pop("packet_id", "")
    if packet_id != "prp_" + hashlib.sha256(canonical_bytes(expected)).hexdigest()[:24]:
        errors.append("packet_id mismatch")
    return {
        "beast_object_type": "proof_receipt_packet_validation",
        "version": "1.0",
        "valid": not errors,
        "errors": errors,
        "privacy_findings": privacy_findings,
        "packet_id": packet.get("packet_id"),
    }



def build_manifest_stage(public_card: Dict[str, Any]) -> Dict[str, Any]:
    manifest = public_card.get("manifest") or {}
    stage = {
        "beast_object_type": "proof_manifest_stage",
        "version": "1.0",
        "space_id": public_card.get("space_id"),
        "manifest_hash": public_card.get("manifest_hash"),
        "name": public_card.get("name"),
        "task_class": public_card.get("task_class"),
        "authority": "advisory_remote_hypothesis",
        "artifacts": manifest.get("artifacts") or [],
        "hardware_profile": manifest.get("hardware_profile") or {},
        "safety": manifest.get("safety") or {},
        "privacy": manifest.get("privacy") or {},
        "risk_approval": public_card.get("risk_approval") or {},
        "reproduction_status": public_card.get("reproduction_status") or {},
        "excluded_payloads": public_card.get("excluded_from_public_card") or [],
    }
    stage["stage_hash"] = sha256_payload(stage)
    return stage


def validate_manifest_stage(stage: Dict[str, Any], *, expected_manifest_hash: str = "") -> Dict[str, Any]:
    errors = []
    if stage.get("beast_object_type") != "proof_manifest_stage":
        errors.append("invalid beast_object_type")
    if not valid_sha256(stage.get("manifest_hash")):
        errors.append("invalid manifest_hash")
    if expected_manifest_hash and stage.get("manifest_hash") != expected_manifest_hash:
        errors.append("manifest_hash does not match receipt packet")
    payload = dict(stage)
    stage_hash = payload.pop("stage_hash", "")
    if stage_hash != sha256_payload(payload):
        errors.append("stage_hash mismatch")
    privacy_findings = CommonsPrivacyScrubber().scan_payload(payload)
    if privacy_findings:
        errors.append("privacy scan failed")
    return {
        "beast_object_type": "proof_manifest_stage_validation", "version": "1.0",
        "valid": not errors, "errors": errors, "privacy_findings": privacy_findings,
    }


def build_verifier_stage(public_card: Dict[str, Any]) -> Dict[str, Any]:
    bundles = (public_card.get("manifest") or {}).get("verifier_bundles") or []
    descriptors = [
        {
            "name": str(item.get("name") or item.get("verifier") or "verifier")[:120],
            "type": str(item.get("type") or item.get("kind") or "local_allowlisted")[:80],
            "descriptor_hash": sha256_payload(item),
            "remote_execution_allowed": False,
        }
        for item in bundles
    ]
    stage = {
        "beast_object_type": "proof_verifier_stage", "version": "1.0",
        "space_id": public_card.get("space_id"), "manifest_hash": public_card.get("manifest_hash"),
        "verifiers": descriptors,
        "execution_policy": "receiver_maps_descriptors_to_locally_installed_allowlisted_verifiers",
    }
    stage["stage_hash"] = sha256_payload(stage)
    return stage


def validate_verifier_stage(stage: Dict[str, Any], *, expected_manifest_hash: str = "") -> Dict[str, Any]:
    errors = []
    if stage.get("beast_object_type") != "proof_verifier_stage":
        errors.append("invalid beast_object_type")
    if expected_manifest_hash and stage.get("manifest_hash") != expected_manifest_hash:
        errors.append("manifest_hash does not match receipt packet")
    if any(item.get("remote_execution_allowed") is not False for item in stage.get("verifiers") or []):
        errors.append("remote verifier execution is forbidden")
    payload = dict(stage)
    stage_hash = payload.pop("stage_hash", "")
    if stage_hash != sha256_payload(payload):
        errors.append("stage_hash mismatch")
    privacy_findings = CommonsPrivacyScrubber().scan_payload(payload)
    if privacy_findings:
        errors.append("privacy scan failed")
    return {
        "beast_object_type": "proof_verifier_stage_validation", "version": "1.0",
        "valid": not errors, "errors": errors, "privacy_findings": privacy_findings,
    }
def build_capability_advertisement(
    *,
    node_id: str,
    contributor_id: str,
    capability_hashes: Iterable[str],
    task_classes: Iterable[str],
    verifier_classes: Iterable[str],
    engine_profiles: Iterable[str],
    privacy_classes_accepted: Iterable[str],
    load_bucket: str,
    rtt_bucket_ms: int,
    max_transfer_bytes: int,
    issued_at: str,
    expires_at: str,
    receipt_packets: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    core = {
        "beast_object_type": "node_capability_advertisement",
        "version": "1.0",
        "node_id": str(node_id),
        "contributor_id": str(contributor_id),
        "capability_hashes": sorted(set(str(item) for item in capability_hashes)),
        "task_classes": sorted(set(str(item)[:120] for item in task_classes)),
        "verifier_classes": sorted(set(str(item)[:80] for item in verifier_classes)),
        "engine_profiles": sorted(set(str(item)[:80] for item in engine_profiles)),
        "privacy_classes_accepted": sorted(set(str(item)[:80] for item in privacy_classes_accepted)),
        "load_bucket": str(load_bucket),
        "rtt_bucket_ms": max(1, int(rtt_bucket_ms)),
        "max_transfer_bytes": max(0, int(max_transfer_bytes)),
        "issued_at": issued_at,
        "expires_at": expires_at,
        "authority": "advisory_peer_metadata",
        "receipt_packets": list(receipt_packets or []),
    }
    core["advertisement_id"] = "adv_" + hashlib.sha256(canonical_bytes(core)).hexdigest()[:24]
    return core


def validate_capability_advertisement(advertisement: Dict[str, Any], *, now: Optional[datetime] = None) -> Dict[str, Any]:
    errors: List[str] = []
    if advertisement.get("beast_object_type") != "node_capability_advertisement":
        errors.append("invalid beast_object_type")
    if advertisement.get("load_bucket") not in LOAD_FACTOR:
        errors.append("invalid load_bucket")
    hashes = advertisement.get("capability_hashes") or []
    if len(hashes) > 256 or any(not valid_sha256(item) for item in hashes):
        errors.append("invalid capability_hashes")
    if not advertisement.get("privacy_classes_accepted"):
        errors.append("privacy_classes_accepted is required")
    if int(advertisement.get("rtt_bucket_ms") or 0) <= 0:
        errors.append("invalid rtt_bucket_ms")
    try:
        issued = parse_time(str(advertisement.get("issued_at") or ""))
        expires = parse_time(str(advertisement.get("expires_at") or ""))
        if expires <= (now or datetime.now(timezone.utc)) or expires <= issued:
            errors.append("advertisement is expired or has an invalid lifetime")
    except ValueError as exc:
        errors.append(str(exc))
    privacy_findings = CommonsPrivacyScrubber().scan_payload(_advertisement_payload(advertisement))
    if privacy_findings:
        errors.append("privacy scan failed")
    expected = dict(_advertisement_payload(advertisement))
    advertisement_id = expected.pop("advertisement_id", "")
    if advertisement_id != "adv_" + hashlib.sha256(canonical_bytes(expected)).hexdigest()[:24]:
        errors.append("advertisement_id mismatch")
    return {
        "beast_object_type": "node_capability_advertisement_validation",
        "version": "1.0", "valid": not errors, "errors": errors,
        "privacy_findings": privacy_findings,
        "advertisement_id": advertisement.get("advertisement_id"),
    }


@dataclass(frozen=True)
class ProofRouteRequest:
    task_class: str
    space_id: str = ""
    manifest_hash: str = ""
    privacy_class: str = "public_metadata_only"
    required_verifiers: List[str] = field(default_factory=list)
    max_lan_rtt_ms: int = 200
    max_transfer_bytes: int = 5_000_000
    risk_class: str = "low"
    allow_trusted_lan: bool = True
    fallback: str = "local_ollama"


class ProofRoutePlanner:
    """Advisory LAN candidate ranking. Compute Governor remains authoritative."""

    def plan(
        self,
        request: ProofRouteRequest,
        advertisements: Iterable[Dict[str, Any]],
        *,
        reputations: Optional[Dict[str, Dict[str, Any]]] = None,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        reputations = reputations or {}
        now = now or datetime.now(timezone.utc)
        candidates = []
        rejected = []
        for advertisement in advertisements:
            reasons = self._rejection_reasons(request, advertisement, now)
            if reasons:
                rejected.append({"advertisement_id": advertisement.get("advertisement_id"), "reasons": reasons})
                continue
            contributor = str(advertisement.get("contributor_id") or "")
            reputation = reputations.get(contributor) or {}
            reputation_score = max(0.0, min(1.0, float(reputation.get("reputation_score") or 0.0)))
            receipt_packets = list(advertisement.get("receipt_packets") or [])
            if request.space_id:
                receipt_packets = [item for item in receipt_packets if item.get("space_id") == request.space_id]
            if request.manifest_hash:
                receipt_packets = [item for item in receipt_packets if item.get("manifest_hash") == request.manifest_hash]
            best_receipt = max(
                receipt_packets,
                key=lambda item: PROOF_DEPTH.get(str(item.get("proof_depth") or "unverified_claim"), 0.0),
                default={},
            )
            proof_depth = PROOF_DEPTH.get(
                str(best_receipt.get("proof_depth") or "manifest_valid"), PROOF_DEPTH["manifest_valid"],
            )
            rtt = max(1, int(advertisement.get("rtt_bucket_ms") or 1))
            load = LOAD_FACTOR.get(str(advertisement.get("load_bucket") or "high"), 0.0)
            latency_factor = max(0.05, 1.0 - (rtt / max(1, request.max_lan_rtt_ms + 1)))
            score = round(0.35 * proof_depth + 0.25 * reputation_score + 0.20 * load + 0.20 * latency_factor, 6)
            candidates.append({
                "route": "trusted_lan_replay", "node_id": advertisement.get("node_id"),
                "contributor_id": contributor, "advertisement_id": advertisement.get("advertisement_id"),
                "score": score, "proof_depth": proof_depth, "reputation_score": reputation_score,
                "rtt_bucket_ms": rtt, "load_bucket": advertisement.get("load_bucket"),
                "space_id": best_receipt.get("space_id"),
                "manifest_hash": best_receipt.get("manifest_hash"),
                "requires_approval": request.risk_class == "high",
                "authority": "advisory_requires_local_replay",
            })
        candidates.sort(key=lambda item: (-item["score"], item["rtt_bucket_ms"], str(item["node_id"])))
        selected = candidates[0] if request.allow_trusted_lan and candidates else None
        return {
            "beast_object_type": "proof_route_plan", "version": "1.0",
            "decision": "trusted_lan_candidate" if selected else "fallback",
            "selected": selected, "candidates": candidates, "rejected": rejected,
            "fallback": request.fallback,
            "enforcing": False,
            "claim_boundary": "advisory ranking; Compute Governor gates and local replay decide execution",
        }

    @staticmethod
    def _rejection_reasons(request: ProofRouteRequest, advertisement: Dict[str, Any], now: datetime) -> List[str]:
        reasons = []
        validation = validate_capability_advertisement(advertisement, now=now)
        if not validation["valid"]:
            reasons.append("invalid_or_expired_advertisement")
            return reasons
        if not request.allow_trusted_lan:
            reasons.append("trusted_lan_disabled")
        if request.task_class not in (advertisement.get("task_classes") or []):
            reasons.append("task_class_mismatch")
        receipts = advertisement.get("receipt_packets") or []
        if request.space_id and not any(item.get("space_id") == request.space_id for item in receipts):
            reasons.append("space_id_mismatch")
        if request.manifest_hash and not any(item.get("manifest_hash") == request.manifest_hash for item in receipts):
            reasons.append("manifest_hash_mismatch")
        if request.privacy_class not in (advertisement.get("privacy_classes_accepted") or []):
            reasons.append("privacy_class_mismatch")
        if not set(request.required_verifiers).issubset(set(advertisement.get("verifier_classes") or [])):
            reasons.append("required_verifier_missing")
        if int(advertisement.get("rtt_bucket_ms") or 0) > request.max_lan_rtt_ms:
            reasons.append("rtt_budget_exceeded")
        if int(advertisement.get("max_transfer_bytes") or 0) < request.max_transfer_bytes:
            reasons.append("transfer_budget_unsupported")
        return reasons


def staged_transfer_receipt(
    *,
    transfer_id: str,
    stage: str,
    accepted: bool,
    reason: str,
    bytes_received: int,
    declared_artifact_bytes: int,
    declared_bundle_bytes: int = 0,
    packet_id: str = "",
    manifest_hash: str = "",
    full_bundle_transferred: bool = False,
) -> Dict[str, Any]:
    transfer_basis = max(0, int(declared_bundle_bytes or declared_artifact_bytes))
    avoided = max(0, transfer_basis - max(0, int(bytes_received))) if not full_bundle_transferred else 0
    return {
        "beast_object_type": "staged_transfer_receipt", "version": "1.0",
        "transfer_id": transfer_id, "stage": stage, "accepted": bool(accepted),
        "reason": str(reason), "packet_id": packet_id, "manifest_hash": manifest_hash,
        "bytes_received": max(0, int(bytes_received)), "declared_artifact_bytes": max(0, int(declared_artifact_bytes)),
        "declared_bundle_bytes": max(0, int(declared_bundle_bytes)),
        "bytes_avoided": avoided, "full_bundle_avoided": not full_bundle_transferred,
        "created_at": utc_now(),
        "credit_eligible": False,
    }


def _unsigned(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in {"signature", "optional_pq_seal"}}


def _advertisement_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: value for key, value in payload.items()
        if key not in {"signature", "optional_pq_seal", "state", "ingested_at"}
    }


def _proof_depth(detail: Dict[str, Any]) -> str:
    manifest = detail.get("manifest") or {}
    safety = manifest.get("safety") or {}
    if safety.get("promotion_state") == "promoted":
        return "promoted"
    if any(item.get("adopted") for item in detail.get("adoptions") or []):
        return "adopted"
    reproductions = detail.get("reproductions") or []
    if any(item.get("reproduced") and item.get("live_verifier_passed") for item in reproductions):
        return "locally_reproduced"
    if any(item.get("reproduced") for item in reproductions):
        return "locally_replayed"
    return "manifest_valid"
