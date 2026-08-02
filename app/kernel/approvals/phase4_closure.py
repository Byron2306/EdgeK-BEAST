from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .capability_issuer import RequestBoundCapabilityIssuer
from .capability_runtime import ExactStepResumeRuntime
from .cards import DurableApprovalCardStore
from .classifier import ApprovalRiskClassifier
from .digests import canonicalize, semantic_payload, sha256_digest, verify_digest
from .envelope import RichApprovalEnvelopeBuilder
from .external_content import ExternalContentAdmissionController
from .mode_engine import PermissionModeEngine
from .models import ApprovalContractFactory
from .revocation import RevocationPolicyStore
from .scope_engine import ApprovalScopeEngine
from .sensitive_data import SensitiveDataController

CLOSURE_VERSION = "4.13"
CLOSURE_OBJECT_TYPE = "beast_phase4_end_to_end_closure_receipt"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Phase4ClosureReceipt:
    closure_id: str
    workspace_root: str
    approval_id: str
    run_id: str
    step_id: str
    policy_generation: str
    verified_artifacts: tuple[str, ...]
    proof_checks: tuple[dict[str, Any], ...]
    restart_safe: bool
    exact_step_bound: bool
    request_bound_capability: bool
    replay_denied: bool
    revocation_enforced: bool
    future_authority_widened: bool
    closure_status: str
    created_at: str
    authority: str = "phase4_proof_receipt_only"
    grants_execution_authority: bool = False
    grants_workspace_mutation: bool = False
    grants_promotion_authority: bool = False
    version: str = CLOSURE_VERSION
    beast_object_type: str = CLOSURE_OBJECT_TYPE
    receipt_digest: str = ""

    def semantic_dict(self) -> dict[str, Any]:
        return canonicalize(semantic_payload(asdict(self), exclude={"receipt_digest"}))

    def to_dict(self) -> dict[str, Any]:
        payload = canonicalize(asdict(self))
        payload["receipt_digest"] = self.receipt_digest or sha256_digest(self.semantic_dict())
        return payload


class Phase4EndToEndClosure:
    """Verify the complete Phase 4 authority chain without granting new authority."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.contracts = ApprovalContractFactory()
        self.classifier = ApprovalRiskClassifier()
        self.envelopes = RichApprovalEnvelopeBuilder()
        self.scopes = ApprovalScopeEngine()
        self.issuer = RequestBoundCapabilityIssuer()
        self.modes = PermissionModeEngine()
        self.sensitive = SensitiveDataController()
        self.external = ExternalContentAdmissionController()
        self.cards = DurableApprovalCardStore(self.workspace_root)
        self.revocations = RevocationPolicyStore(self.workspace_root)
        self.runtime = ExactStepResumeRuntime(self.workspace_root)

    @staticmethod
    def _check(checks: list[dict[str, Any]], name: str, passed: bool, detail: str = "") -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": str(detail)})
        if not passed:
            raise ValueError(f"phase4 closure check failed: {name}: {detail}")

    @staticmethod
    def _same(left: Mapping[str, Any], right: Mapping[str, Any], fields: tuple[str, ...]) -> bool:
        return all(str(left.get(field) or "") == str(right.get(field) or "") for field in fields)

    def close(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(payload or {})
        request = payload.get("request") or {}
        classification = payload.get("classification") or {}
        envelope = payload.get("envelope") or {}
        card = payload.get("card") or {}
        decision = payload.get("decision") or {}
        grant = payload.get("scope_grant") or {}
        scope_match = payload.get("scope_match") or {}
        capability = payload.get("capability") or {}
        consumption = payload.get("consumption_receipt") or {}
        mode_profile = payload.get("mode_profile") or {}
        mode_decision = payload.get("mode_decision") or {}
        sensitive_classification = payload.get("sensitive_classification")
        sensitive_redaction = payload.get("sensitive_redaction")
        external_classification = payload.get("external_classification")
        external_admission = payload.get("external_admission")

        checks: list[dict[str, Any]] = []
        self.contracts.validate_request(request)
        self._check(checks, "canonical_request", True)
        self._check(checks, "risk_classification", self.classifier.verify(classification))
        self._check(checks, "rich_envelope", self.envelopes.verify(envelope))
        self._check(checks, "durable_card", self.cards.verify(card))
        chain = self.cards.verify_chain(str(card.get("approval_id") or ""))
        self._check(checks, "durable_card_event_chain", bool(chain.get("ok")), str(chain))
        self._check(checks, "scope_grant", self.scopes.verify_grant(grant))
        self._check(checks, "scope_match", self.scopes.verify_match(scope_match))
        self._check(checks, "scope_match_result", str(scope_match.get("result")) == "MATCH")
        self._check(checks, "request_bound_capability", self.issuer.verify(capability))
        self._check(checks, "consumption_receipt", self.runtime.verify_receipt(consumption))
        self._check(checks, "permission_mode_profile", self.modes.verify_profile(mode_profile))
        self._check(checks, "permission_mode_decision", self.modes.verify_decision(mode_decision))

        if sensitive_classification is not None:
            self._check(checks, "sensitive_classification", self.sensitive.verify_classification(sensitive_classification))
        if sensitive_redaction is not None:
            self._check(checks, "sensitive_redaction", self.sensitive.verify_redaction(sensitive_redaction))
        if external_classification is not None:
            self._check(checks, "external_classification", self.external.verify_classification(external_classification))
        if external_admission is not None:
            self._check(checks, "external_admission", self.external.verify_admission(external_admission))

        artifact_bindings = (
            ("classification", classification, ("tool_id", "tool_version", "workspace_id", "execution_target", "policy_generation", "risk_class", "permission_mode")),
            ("envelope_request", envelope.get("approval_request") or {}, ("approval_id", "run_id", "step_id", "tool_id", "tool_version", "workspace_id", "execution_target", "policy_generation", "request_digest")),
            ("card", card, ("approval_id", "run_id", "step_id", "request_digest")),
            ("scope_grant", grant, ("approval_id", "run_id", "step_id", "tool_id", "tool_version", "workspace_id", "execution_target", "policy_generation", "request_digest")),
            ("capability", capability, ("approval_id", "run_id", "step_id", "tool_id", "tool_version", "workspace_id", "execution_target", "policy_generation", "request_digest")),
            ("consumption", consumption, ("approval_id", "run_id", "step_id", "tool_id", "tool_version", "workspace_id", "execution_target", "policy_generation", "request_digest")),
        )
        for name, artifact, fields in artifact_bindings:
            self._check(checks, f"binding_{name}", self._same(request, artifact, fields), name)

        self._check(checks, "decision_request_binding", str(decision.get("request_digest")) == str(request.get("request_digest")))
        self._check(checks, "scope_grant_decision_binding", str(grant.get("decision_digest")) == str(decision.get("decision_digest")))
        self._check(checks, "scope_match_grant_binding", str(scope_match.get("grant_digest")) == str(grant.get("grant_digest")))
        self._check(checks, "capability_scope_match_binding", str(capability.get("scope_match_digest")) == str(scope_match.get("match_digest")))
        self._check(checks, "capability_single_use", bool(capability.get("single_use")))
        self._check(checks, "capability_consumed", bool(consumption.get("capability_consumed")))
        self._check(checks, "replay_denied", consumption.get("replay_allowed") is False)
        self._check(checks, "exact_step_resumed", bool(consumption.get("run_resumed")) and str(consumption.get("step_id")) == str(request.get("step_id")))

        persisted = self.cards.get(str(request["approval_id"]))
        self._check(checks, "restart_safe_card_recovery", str(persisted.get("card_digest")) == str(card.get("card_digest")))
        ledger = self.runtime.consumptions.get(str(capability.get("capability_id") or ""))
        self._check(checks, "restart_safe_consumption_recovery", bool(ledger), "durable consumption missing")
        self.revocations.assert_active(capability)
        self._check(checks, "revocation_gate", True)

        no_widen = all(not bool(item.get(field)) for item in (capability, consumption, card) for field in (
            "execution_authorized", "workspace_mutation_authorized", "promotion_authorized",
            "phase2_governance_bypass_allowed", "grants_execution_authority",
        ))
        self._check(checks, "no_future_authority_widening", no_widen)

        verified = tuple(check["check"] for check in checks if check["passed"])
        receipt = Phase4ClosureReceipt(
            closure_id="p4close_" + sha256_digest({"approval": request["approval_id"], "capability": capability.get("capability_id"), "checks": verified})[7:23],
            workspace_root=str(self.workspace_root),
            approval_id=str(request["approval_id"]), run_id=str(request["run_id"]), step_id=str(request["step_id"]),
            policy_generation=str(request["policy_generation"]), verified_artifacts=verified,
            proof_checks=tuple(checks), restart_safe=True, exact_step_bound=True,
            request_bound_capability=True, replay_denied=True, revocation_enforced=True,
            future_authority_widened=False, closure_status="PASS", created_at=_utcnow(),
        ).to_dict()
        return receipt

    @staticmethod
    def verify(receipt: Mapping[str, Any]) -> bool:
        try:
            return (
                receipt.get("beast_object_type") == CLOSURE_OBJECT_TYPE
                and receipt.get("closure_status") == "PASS"
                and receipt.get("authority") == "phase4_proof_receipt_only"
                and receipt.get("grants_execution_authority") is False
                and receipt.get("grants_workspace_mutation") is False
                and receipt.get("grants_promotion_authority") is False
                and receipt.get("future_authority_widened") is False
                and all(bool(check.get("passed")) for check in receipt.get("proof_checks") or [])
                and verify_digest(semantic_payload(receipt, exclude={"receipt_digest"}), str(receipt.get("receipt_digest") or ""))
            )
        except Exception:
            return False
