"""Unified Sophia/Integritas -> BEAST lineage certificate.

This module closes the specific proof gap between adjacent receipts:

* the exact Sophia/Integritas academic-integrity export is signed;
* the signed export digest matches the Sophia artifact inside the Phase-1 DAI
  packet that passed Seraph challenge, Commons admission/quorum and promotion;
* the same export digest matches the Phase-6.1 deterministic source-support
  arena and the Phase-6.2 mixed-capability expression ledger;
* the Arda execution lineage is present only as bounded replay / refusal of
  production authority.

The signing key is a local lineage key generated for the certificate unless a
caller supplies one.  This proves possession of that key for this artifact.  It
does not claim a public institutional identity unless the public key fingerprint
is separately pinned in release materials.
"""
from __future__ import annotations

from dataclasses import dataclass
import base64
import json
from pathlib import Path
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from app.kernel.compute.deterministic_intelligence import canonical_json, require_digest, sha256_bytes, sha256_digest


LINEAGE_VERSION = "2026-08-04.phase6.3.sophia-integritas-lineage.v1"


@dataclass(frozen=True, slots=True)
class SophiaLineageSignature:
    beast_object_type: str
    version: str
    signer_id: str
    export_digest: str
    export_schema: str
    signed_payload_digest: str
    public_key_b64: str
    public_key_fingerprint: str
    signature_b64: str
    identity_boundary: str = "local_lineage_key_not_public_identity_pinned"

    @property
    def signature_packet_digest(self) -> str:
        return sha256_digest(self)


def sign_sophia_export(
    export_path: str | Path,
    *,
    signer_id: str = "integritas-sophia-local-lineage-signer",
    private_key: Ed25519PrivateKey | None = None,
) -> SophiaLineageSignature:
    source = Path(export_path).expanduser().resolve()
    export_digest = sha256_bytes(source.read_bytes())
    key = private_key or Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    payload = _signature_payload(
        signer_id=signer_id,
        export_digest=export_digest,
        export_schema="sophia_writing_desk_phase3_export_semantic",
    )
    signature = key.sign(canonical_json(payload).encode("utf-8"))
    return SophiaLineageSignature(
        beast_object_type="dai_sophia_integritas_lineage_signature",
        version=LINEAGE_VERSION,
        signer_id=signer_id,
        export_digest=export_digest,
        export_schema="sophia_writing_desk_phase3_export_semantic",
        signed_payload_digest=sha256_digest(payload),
        public_key_b64=base64.b64encode(public).decode("ascii"),
        public_key_fingerprint=sha256_bytes(public),
        signature_b64=base64.b64encode(signature).decode("ascii"),
    )


def verify_sophia_signature(packet: Mapping[str, Any]) -> bool:
    payload = _signature_payload(
        signer_id=str(packet.get("signer_id") or ""),
        export_digest=str(packet.get("export_digest") or ""),
        export_schema=str(packet.get("export_schema") or ""),
    )
    if sha256_digest(payload) != packet.get("signed_payload_digest"):
        return False
    try:
        public = base64.b64decode(str(packet.get("public_key_b64") or ""), validate=True)
        signature = base64.b64decode(str(packet.get("signature_b64") or ""), validate=True)
        if sha256_bytes(public) != packet.get("public_key_fingerprint"):
            return False
        Ed25519PublicKey.from_public_bytes(public).verify(signature, canonical_json(payload).encode("utf-8"))
        return True
    except (ValueError, InvalidSignature):
        return False


def build_sophia_integritas_lineage_certificate(
    *,
    signed_sophia: SophiaLineageSignature,
    phase1_packet: Mapping[str, Any],
    phase1_validation: Mapping[str, Any],
    evidence_resolution: Mapping[str, Any],
    seraph_assessment_packet: Mapping[str, Any],
    commons_admission: Mapping[str, Any],
    quorum_decision: Mapping[str, Any],
    promotion: Mapping[str, Any],
    neural_mesh: Mapping[str, Any],
    arda_execution: Mapping[str, Any],
    phase6_1: Mapping[str, Any],
    phase6_2_ledger: Mapping[str, Any],
    phase6_2_truth: Mapping[str, Any],
) -> dict[str, Any]:
    signed_packet = json.loads(canonical_json(signed_sophia))
    gates: dict[str, bool] = {}
    notes: list[str] = []

    phase1_packet_digest = sha256_digest(phase1_packet)
    phase1_candidate = phase1_packet.get("concept_candidate") if isinstance(phase1_packet.get("concept_candidate"), Mapping) else {}
    phase1_candidate_digest = sha256_digest(phase1_candidate)
    phase1_sophia_artifact = _artifact_by_organ(phase1_packet, "sophia")
    phase1_sophia_artifact_digest = str(phase1_sophia_artifact.get("artifact_digest") or "")
    phase1_sophia_receipt_digest = sha256_digest(phase1_sophia_artifact)

    gates["sophia_signature_valid"] = verify_sophia_signature(signed_packet)
    gates["signed_export_digest_matches_phase1_artifact"] = signed_sophia.export_digest == phase1_sophia_artifact_digest
    gates["phase1_candidate_source_receipt_matches_sophia_artifact"] = phase1_sophia_receipt_digest in tuple(phase1_candidate.get("source_artifact_receipts") or ())
    gates["phase1_packet_validation_accepted"] = (
        _self_digest(phase1_validation, "receipt_digest")
        and phase1_validation.get("accepted") is True
        and phase1_validation.get("packet_digest") == phase1_packet_digest
    )
    gates["phase1_evidence_resolution_green"] = _self_digest(evidence_resolution, "receipt_digest") and evidence_resolution.get("resolved") is True and not evidence_resolution.get("red_gates")
    gates["seraph_challenge_present"] = bool(seraph_assessment_packet.get("challenge_receipts")) and len(tuple(seraph_assessment_packet.get("challenge_receipts") or ())) >= 4
    gates["seraph_is_challenge_only"] = seraph_assessment_packet.get("maximum_authority") == "adversarial_challenge_only"
    gates["commons_admission_green"] = _self_digest(commons_admission, "receipt_digest") and commons_admission.get("admitted") is True and not commons_admission.get("red_gates")
    gates["commons_quorum_approved"] = _self_digest(quorum_decision, "receipt_digest") and quorum_decision.get("decision") == "approved" and not quorum_decision.get("red_gates")
    gates["quorum_binds_phase1_candidate"] = quorum_decision.get("proposal_digest") == phase1_candidate_digest
    gates["promotion_green"] = (
        _self_digest(promotion, "receipt_digest")
        and promotion.get("promoted") is True
        and promotion.get("candidate_digest") == phase1_candidate_digest
        and not promotion.get("red_gates")
    )
    gates["neural_mesh_binds_promotion_without_execution_authority"] = (
        _self_digest(neural_mesh, "receipt_digest")
        and neural_mesh.get("activated") is True
        and neural_mesh.get("promotion_receipt_digest") == promotion.get("receipt_digest")
        and neural_mesh.get("execution_authority_allowed") is False
    )
    gates["arda_bounded_execution_binds_promotion_without_execution_authority"] = (
        _self_digest(arda_execution, "receipt_digest")
        and arda_execution.get("executed") is True
        and arda_execution.get("promotion_receipt_digest") == promotion.get("receipt_digest")
        and arda_execution.get("execution_authority_allowed") is False
    )
    gates["phase6_1_binds_same_signed_sophia_export"] = (
        _self_digest(phase6_1, "receipt_digest")
        and phase6_1.get("green") is True
        and phase6_1.get("sophia_export_digest") == signed_sophia.export_digest
    )
    gates["phase6_2_ledger_binds_phase6_1_source_support_crystal"] = (
        _self_digest(phase6_2_ledger, "ledger_digest")
        and _ledger_has_phase6_1_crystal(phase6_2_ledger, phase6_1)
    )
    gates["phase6_2_expression_green"] = (
        _self_digest(phase6_2_truth, "receipt_digest")
        and phase6_2_truth.get("green") is True
        and phase6_2_truth.get("ledger_digest") == phase6_2_ledger.get("ledger_digest")
        and int(phase6_2_truth.get("text_visual_joined_green_count") or 0) == int(phase6_2_truth.get("case_count") or -1)
        and int(phase6_2_truth.get("visual_proposition_coverage_count") or 0) == int(phase6_2_truth.get("case_count") or -1)
    )
    gates["zero_provider_and_no_production_execution_authority"] = all(
        _zero_provider_no_exec(payload)
        for payload in (phase1_validation, promotion, neural_mesh, arda_execution, phase6_1, phase6_2_ledger, phase6_2_truth)
    )
    if signed_sophia.identity_boundary != "public_identity_pinned":
        notes.append("Sophia signature is cryptographic but local-key only; public identity pinning remains a publication task.")
    if arda_execution.get("executed") is True and arda_execution.get("execution_authority_allowed") is False:
        notes.append("Arda lineage is bounded replay evidence; it does not grant production execution authority.")

    red_gates = tuple(name for name, passed in sorted(gates.items()) if not passed)
    certificate: dict[str, Any] = {
        "beast_object_type": "dai_sophia_integritas_unified_lineage_certificate",
        "version": LINEAGE_VERSION,
        "signed_sophia_signature_packet": signed_packet,
        "signed_sophia_signature_packet_digest": signed_sophia.signature_packet_digest,
        "signed_sophia_export_digest": signed_sophia.export_digest,
        "phase1_packet_digest": phase1_packet_digest,
        "phase1_candidate_digest": phase1_candidate_digest,
        "phase1_sophia_artifact_receipt_digest": phase1_sophia_receipt_digest,
        "seraph_challenge_receipts": tuple(seraph_assessment_packet.get("challenge_receipts") or ()),
        "commons_admission_receipt_digest": commons_admission.get("receipt_digest"),
        "commons_quorum_receipt_digest": quorum_decision.get("receipt_digest"),
        "promotion_receipt_digest": promotion.get("receipt_digest"),
        "neural_mesh_receipt_digest": neural_mesh.get("receipt_digest"),
        "arda_bounded_execution_receipt_digest": arda_execution.get("receipt_digest"),
        "phase6_1_receipt_digest": phase6_1.get("receipt_digest"),
        "phase6_2_ledger_digest": phase6_2_ledger.get("ledger_digest"),
        "phase6_2_truth_receipt_digest": phase6_2_truth.get("receipt_digest"),
        "gates": gates,
        "red_gates": red_gates,
        "green": not red_gates,
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
        "claim_boundary": (
            "Signed local-key Sophia/Integritas export digest is bound to Phase-1 Seraph challenge, "
            "Commons quorum, promotion and bounded Arda replay receipts, and to Phase-6.1/6.2 deterministic "
            "expression ledger receipts for the same export digest."
        ),
        "nonclaims": (
            "No public identity-pinned Sophia signing key.",
            "No production execution authority.",
            "No claim that Phase-6.2 itself was approved by a fresh remote Commons quorum.",
        ),
        "notes": tuple(notes),
    }
    certificate["certificate_digest"] = sha256_digest(certificate)
    return certificate


def verify_lineage_certificate(certificate: Mapping[str, Any]) -> dict[str, Any]:
    body = dict(certificate)
    claimed = str(body.pop("certificate_digest", ""))
    gates = {
        "certificate_digest_recomputes": bool(claimed) and sha256_digest(body) == claimed,
        "certificate_green": certificate.get("green") is True and not certificate.get("red_gates"),
        "embedded_signature_valid": verify_sophia_signature(certificate.get("signed_sophia_signature_packet") or {}),
        "no_authority_inflation": certificate.get("production_authority_allowed") is False and certificate.get("execution_authority_allowed") is False,
    }
    red_gates = tuple(name for name, passed in sorted(gates.items()) if not passed)
    result = {
        "beast_object_type": "dai_sophia_integritas_lineage_certificate_verification",
        "certificate_digest": claimed,
        "verified": not red_gates,
        "gates": gates,
        "red_gates": red_gates,
    }
    result["verification_digest"] = sha256_digest(result)
    return result


def verify_lineage_certificate_against_key_policy(
    certificate: Mapping[str, Any],
    key_policy: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify the certificate against a project-pinned public key policy."""
    signature_packet = certificate.get("signed_sophia_signature_packet")
    signature_packet = signature_packet if isinstance(signature_packet, Mapping) else {}
    certificate_verification = verify_lineage_certificate(certificate)
    policy_body = dict(key_policy)
    claimed_policy_digest = str(policy_body.pop("policy_digest", ""))
    gates = {
        "certificate_verifies": certificate_verification["verified"] is True,
        "policy_digest_recomputes": bool(claimed_policy_digest) and sha256_digest(policy_body) == claimed_policy_digest,
        "policy_object_type": key_policy.get("beast_object_type") == "dai_sophia_integritas_lineage_project_key_policy",
        "policy_status_active": str(key_policy.get("status") or "").startswith("active_"),
        "policy_key_fingerprint_matches_certificate": key_policy.get("public_key_fingerprint") == signature_packet.get("public_key_fingerprint"),
        "policy_public_key_matches_certificate": key_policy.get("public_key_b64") == signature_packet.get("public_key_b64"),
        "policy_signed_export_matches_certificate": key_policy.get("signed_export_digest") == certificate.get("signed_sophia_export_digest"),
        "policy_signature_packet_matches_certificate": key_policy.get("signature_packet_digest") == certificate.get("signed_sophia_signature_packet_digest"),
        "policy_certificate_digest_matches_certificate": key_policy.get("certificate_digest") == certificate.get("certificate_digest"),
        "policy_declares_repo_pins": {"RELEASE_KEYS.md", "SECURITY.md"}.issubset(set(key_policy.get("pinned_in") or ())),
        "no_authority_inflation": certificate.get("production_authority_allowed") is False and certificate.get("execution_authority_allowed") is False,
    }
    red_gates = tuple(name for name, passed in sorted(gates.items()) if not passed)
    result = {
        "beast_object_type": "dai_sophia_integritas_project_key_policy_verification",
        "version": LINEAGE_VERSION,
        "certificate_digest": certificate.get("certificate_digest"),
        "policy_digest": key_policy.get("policy_digest"),
        "public_key_fingerprint": key_policy.get("public_key_fingerprint"),
        "verified": not red_gates,
        "gates": gates,
        "red_gates": red_gates,
        "identity_boundary": "project_pinned_beast_sophia_lineage_key_not_institutional_endorsement",
    }
    result["verification_digest"] = sha256_digest(result)
    return result


def _signature_payload(*, signer_id: str, export_digest: str, export_schema: str) -> dict[str, Any]:
    require_digest(export_digest, field_name="export_digest")
    return {
        "beast_object_type": "dai_sophia_integritas_lineage_signing_payload",
        "version": LINEAGE_VERSION,
        "signer_id": signer_id,
        "export_digest": export_digest,
        "export_schema": export_schema,
        "purpose": "bind exact Sophia/Integritas pedagogical-academic-integrity export into BEAST DAI lineage",
    }


def _artifact_by_organ(packet: Mapping[str, Any], organ: str) -> Mapping[str, Any]:
    for artifact in packet.get("artifacts") or ():
        if isinstance(artifact, Mapping) and artifact.get("organ") == organ:
            return artifact
    return {}


def _self_digest(payload: Mapping[str, Any], field: str) -> bool:
    claimed = str(payload.get(field) or "")
    if not claimed:
        return False
    body = dict(payload)
    body.pop(field, None)
    return sha256_digest(body) == claimed


def _ledger_has_phase6_1_crystal(ledger: Mapping[str, Any], phase6_1: Mapping[str, Any]) -> bool:
    for crystal in ledger.get("crystals") or ():
        if not isinstance(crystal, Mapping):
            continue
        if crystal.get("family") == "sophia_source_support" and crystal.get("receipt_digest") == phase6_1.get("receipt_digest"):
            return crystal.get("capability_digest") == phase6_1.get("capability_family_digest")
    return False


def _zero_provider_no_exec(payload: Mapping[str, Any]) -> bool:
    provider_ok = int(payload.get("provider_calls_used") or payload.get("provider_calls_after_ledger") or payload.get("provider_calls_after_promotion") or 0) == 0
    return provider_ok and payload.get("production_authority_allowed", False) is False and payload.get("execution_authority_allowed", False) is False
