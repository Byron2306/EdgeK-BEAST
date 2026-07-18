"""ARDA-style appraisal issuance for verified Commons TPM evidence."""
from __future__ import annotations

import base64
import hashlib
import secrets
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.kernel.commons.job_choir import NodeAdvertisement
from app.kernel.commons.signature_verifier import canonical_bytes
from app.kernel.commons.tpm_attestation import TpmChallengeLedger
from app.kernel.integration.signed_decision import signed_appraisal_body


@dataclass(frozen=True)
class TpmNodeAppraisal:
    node: NodeAdvertisement
    appraisal: dict[str, Any]
    request_digest: str
    evidence_digest: str


class TpmNodeAppraisalIssuer:
    """Issue signed node appraisals from verifier-produced TPM evidence."""

    def __init__(
        self,
        signer: Ed25519PrivateKey,
        *,
        policy_generation: str,
        key_id: str,
        authority: str = "arda",
        ttl_seconds: float = 300.0,
    ):
        if not policy_generation or not key_id:
            raise ValueError("policy generation and key id are required")
        self.signer = signer
        self.policy_generation = policy_generation
        self.key_id = key_id
        self.authority = authority
        self.ttl_seconds = ttl_seconds

    def issue(
        self,
        evidence: Mapping[str, Any],
        *,
        challenge_ledger: TpmChallengeLedger,
        capabilities: tuple[str, ...] = ("cpu",),
        pressure_budget: float = 0.5,
        reliability: float = 0.8,
        route_penalty: float = 0.0,
        now: float | None = None,
    ) -> TpmNodeAppraisal:
        moment = time.time() if now is None else float(now)
        node_id = str(evidence.get("node_id") or "")
        evidence_digest = str(evidence.get("evidence_digest") or "")
        challenge_id = str(evidence.get("challenge_id") or "")
        nonce = str(evidence.get("nonce") or "")
        if not node_id or not evidence_digest.startswith("sha256:"):
            raise PermissionError("TPM evidence identity is incomplete")
        if evidence.get("eligible_for_commons") is not True:
            raise PermissionError("TPM evidence is not Commons eligible")
        if evidence.get("status") != "hardware_quote_valid_measurements_reconciled":
            raise PermissionError("TPM measurements are not fully reconciled")
        if evidence.get("audience") != "beast-commons-node-attestation":
            raise PermissionError("TPM evidence audience is not accepted")
        reconciliation = evidence.get("measurement_reconciliation")
        if not isinstance(reconciliation, Mapping) or reconciliation.get("valid") is not True:
            raise PermissionError("TPM measurement reconciliation is not valid")
        facts = evidence.get("verifier_facts")
        if not isinstance(facts, Mapping) or any(value is not True for value in facts.values()):
            raise PermissionError("TPM verifier facts are incomplete")
        if not challenge_id or not nonce:
            raise PermissionError("TPM challenge binding is required for appraisal")
        consumed = challenge_ledger.consume(
            challenge_id,
            node_id=node_id,
            nonce=nonce,
            now=moment,
        )
        appraisal_ref_seed = {
            "challenge_id": consumed.challenge_id,
            "evidence_digest": evidence_digest,
            "node_id": node_id,
            "policy_generation": self.policy_generation,
        }
        appraisal_ref = (
            f"{self.authority}:commons-node:"
            + hashlib.sha256(canonical_bytes(appraisal_ref_seed)).hexdigest()
        )
        expires_at = moment + float(self.ttl_seconds)
        body = {
            "node_id": node_id,
            "attestation": "verified",
            "capabilities": list(capabilities),
            "pressure_budget": float(pressure_budget),
            "reliability": float(reliability),
            "route_penalty": float(route_penalty),
            "expires_at": expires_at,
            "appraisal_ref": appraisal_ref,
        }
        request_digest = "sha256:" + hashlib.sha256(canonical_bytes(body)).hexdigest()
        appraisal = {
            "appraisal_ref": appraisal_ref,
            "authority": self.authority,
            "audience": "commons-job-choir",
            "policy_generation": self.policy_generation,
            "state": "verified",
            "expires_at": expires_at,
            "request_digest": request_digest,
            "nonce": secrets.token_hex(16),
            "key_id": self.key_id,
            "evidence_digest": evidence_digest,
        }
        appraisal["signature"] = base64.b64encode(
            self.signer.sign(signed_appraisal_body(appraisal))
        ).decode("ascii")
        node = NodeAdvertisement(
            node_id=node_id,
            attestation="verified",
            capabilities=tuple(capabilities),
            pressure_budget=float(pressure_budget),
            reliability=float(reliability),
            route_penalty=float(route_penalty),
            expires_at=expires_at,
            appraisal_ref=appraisal_ref,
            attestation_evidence=appraisal,
        )
        return TpmNodeAppraisal(
            node=node,
            appraisal=appraisal,
            request_digest=request_digest,
            evidence_digest=evidence_digest,
        )
