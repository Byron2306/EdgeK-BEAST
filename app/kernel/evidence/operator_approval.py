"""BEAST Phase 3.9 operator review and one-use approval binding."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from typing import Any, Mapping, Optional
from uuid import uuid4

SCHEMA_VERSION = "3.9"
ALLOWED_DECISIONS = {"APPROVE", "REJECT", "REQUEST_CHANGES"}
ALLOWED_SCOPES = {"once"}
OPERATOR_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{2,127}$")


class OperatorApprovalError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def digest_object(value: Any) -> str:
    return "sha256:" + sha256(_canonical(value)).hexdigest()


def verify_receipt_digest(receipt: Mapping[str, Any]) -> bool:
    claimed = receipt.get("receipt_digest")
    core = {key: value for key, value in receipt.items() if key != "receipt_digest"}
    return isinstance(claimed, str) and claimed == digest_object(core)


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception as exc:
        raise OperatorApprovalError("invalid operator decision timestamp") from exc
    if parsed.tzinfo is None:
        raise OperatorApprovalError("operator decision timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class ApprovalPolicy:
    capability_ttl_seconds: int = 900
    require_reason_for_rejection: bool = True
    require_explicit_review_acknowledgement: bool = True
    require_operator_identity: bool = True
    permit_approval_scope: str = "once"

    @classmethod
    def from_mapping(cls, value: Optional[Mapping[str, Any]]) -> "ApprovalPolicy":
        if not value:
            return cls()
        unknown = set(value) - set(cls.__dataclass_fields__)
        if unknown:
            raise OperatorApprovalError(f"unknown approval policy controls: {sorted(unknown)}")
        policy = cls(**dict(value))
        if not 30 <= int(policy.capability_ttl_seconds) <= 3600:
            raise OperatorApprovalError("capability TTL must be between 30 and 3600 seconds")
        if policy.permit_approval_scope not in ALLOWED_SCOPES:
            raise OperatorApprovalError("only one-use approval scope is permitted")
        return policy


class OperatorReviewApprovalEngine:
    """Bind a human review decision to the exact Phase 3.8 SourcePlan handoff."""

    def resolve(
        self,
        *,
        handoff_receipt: Mapping[str, Any],
        operator_decision: Mapping[str, Any],
        policy_controls: Optional[Mapping[str, Any]] = None,
        created_at: Optional[str] = None,
        capability_nonce: Optional[str] = None,
    ) -> dict[str, Any]:
        policy = ApprovalPolicy.from_mapping(policy_controls)
        blockers: list[str] = []
        warnings: list[str] = []

        if handoff_receipt.get("beast_object_type") != "beast_evidence_sourceplan_handoff_receipt":
            blockers.append("invalid_phase3_8_object_type")
        if handoff_receipt.get("version") != "3.8":
            blockers.append("phase3_8_handoff_receipt_required")
        if not verify_receipt_digest(handoff_receipt):
            blockers.append("handoff_receipt_digest_invalid")
        if handoff_receipt.get("disposition") != "SOURCEPLAN_REVIEW_READY":
            blockers.append("sourceplan_not_review_ready")
        if handoff_receipt.get("sourceplan_review_eligible") is not True:
            blockers.append("sourceplan_review_not_eligible")
        for key in ("sourceplan_apply_authorized", "workspace_mutation_authorized", "promotion_authorized", "phase2_governance_bypass_allowed"):
            if handoff_receipt.get(key) is True:
                blockers.append(f"handoff_receipt_illegally_sets_{key}")

        decision = str(operator_decision.get("decision") or "").upper().strip()
        if decision not in ALLOWED_DECISIONS:
            blockers.append("invalid_operator_decision")
        operator_id = str(operator_decision.get("operator_id") or "").strip()
        if policy.require_operator_identity and not OPERATOR_ID_RE.fullmatch(operator_id):
            blockers.append("valid_operator_identity_required")
        review_ack = operator_decision.get("review_acknowledged") is True
        if policy.require_explicit_review_acknowledgement and not review_ack:
            blockers.append("explicit_review_acknowledgement_required")
        reason = str(operator_decision.get("reason") or "").strip()
        if decision in {"REJECT", "REQUEST_CHANGES"} and policy.require_reason_for_rejection and not reason:
            blockers.append("decision_reason_required")
        scope = str(operator_decision.get("scope") or "once").strip().lower()
        if scope != policy.permit_approval_scope:
            blockers.append("approval_scope_must_be_once")

        expected_plan = str(handoff_receipt.get("plan_id") or "")
        expected_sourceplan_digest = str(handoff_receipt.get("sourceplan_digest") or "")
        expected_operations_digest = str(handoff_receipt.get("operations_digest") or "")
        if str(operator_decision.get("plan_id") or "") != expected_plan:
            blockers.append("operator_plan_binding_mismatch")
        if str(operator_decision.get("sourceplan_digest") or "") != expected_sourceplan_digest:
            blockers.append("operator_sourceplan_digest_mismatch")
        if str(operator_decision.get("operations_digest") or "") != expected_operations_digest:
            blockers.append("operator_operations_digest_mismatch")
        for name, value in (
            ("sourceplan_digest", expected_sourceplan_digest),
            ("operations_digest", expected_operations_digest),
            ("handoff_receipt_digest", handoff_receipt.get("receipt_digest")),
        ):
            if not str(value or "").startswith("sha256:"):
                blockers.append(f"missing_digest_binding:{name}")

        decision_at_raw = str(operator_decision.get("decided_at") or created_at or datetime.now(timezone.utc).isoformat())
        try:
            decision_at = _parse_time(decision_at_raw)
        except OperatorApprovalError as exc:
            blockers.append(str(exc))
            decision_at = datetime.now(timezone.utc)
        issued_at = _parse_time(created_at) if created_at else datetime.now(timezone.utc)
        if abs((issued_at - decision_at).total_seconds()) > 300:
            blockers.append("operator_decision_timestamp_outside_allowed_skew")

        review_digest = digest_object({
            "operator_id": operator_id,
            "decision": decision,
            "reason": reason,
            "review_acknowledged": review_ack,
            "scope": scope,
            "plan_id": expected_plan,
            "sourceplan_digest": expected_sourceplan_digest,
            "operations_digest": expected_operations_digest,
            "decided_at": decision_at.isoformat(),
        })
        request_digest = digest_object({
            "action": "sourceplan.apply",
            "plan_id": expected_plan,
            "sourceplan_digest": expected_sourceplan_digest,
            "operations_digest": expected_operations_digest,
            "handoff_receipt_digest": handoff_receipt.get("receipt_digest"),
            "worktree_id": handoff_receipt.get("worktree_id"),
        })

        approved = decision == "APPROVE" and not blockers
        if blockers:
            disposition = "OPERATOR_DECISION_BLOCKED"
        elif decision == "APPROVE":
            disposition = "OPERATOR_APPROVED"
        elif decision == "REJECT":
            disposition = "OPERATOR_REJECTED"
        else:
            disposition = "OPERATOR_CHANGES_REQUESTED"

        capability = None
        if approved:
            nonce = capability_nonce or uuid4().hex
            expires_at = issued_at.timestamp() + int(policy.capability_ttl_seconds)
            capability_core = {
                "capability_id": "capability:sourceplan-apply:" + uuid4().hex,
                "request_digest": request_digest,
                "authority": "human_operator",
                "issuer_key_id": operator_id,
                "expires_at": expires_at,
                "nonce": nonce,
                "audience": "beast-sourceplan-runtime",
                "scope": "once",
                "plan_id": expected_plan,
                "sourceplan_digest": expected_sourceplan_digest,
                "operations_digest": expected_operations_digest,
                "approval_binding_digest": digest_object({
                    "review_digest": review_digest,
                    "request_digest": request_digest,
                    "handoff_receipt_digest": handoff_receipt.get("receipt_digest"),
                    "operator_id": operator_id,
                    "decision_at": decision_at.isoformat(),
                }),
            }
            capability = {**capability_core, "capability_digest": digest_object(capability_core)}

        core = {
            "version": SCHEMA_VERSION,
            "beast_object_type": "beast_evidence_operator_approval_receipt",
            "evidence_id": handoff_receipt.get("evidence_id"),
            "plan_id": expected_plan,
            "disposition": disposition,
            "operator_id": operator_id,
            "decision": decision,
            "decision_reason": reason,
            "decision_at": decision_at.isoformat(),
            "review_digest": review_digest,
            "request_digest": request_digest,
            "handoff_receipt_digest": handoff_receipt.get("receipt_digest"),
            "sourceplan_digest": expected_sourceplan_digest,
            "operations_digest": expected_operations_digest,
            "worktree_id": handoff_receipt.get("worktree_id"),
            "blockers": sorted(set(blockers)),
            "warnings": sorted(set(warnings)),
            "policy_digest": digest_object(asdict(policy)),
            "created_at": issued_at.isoformat(),
            "authority": "one_use_sourceplan_apply_capability_only" if approved else "classification_only",
            "operator_approved": approved,
            "sourceplan_apply_capability": capability,
            "sourceplan_apply_authorized": False,
            "capability_consumed": False,
            "workspace_mutation_authorized": False,
            "promotion_authorized": False,
            "human_promotion_required": True,
            "phase2_governance_bypass_allowed": False,
        }
        return {**core, "receipt_digest": digest_object(core)}
