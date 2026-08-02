"""BEAST Phase 3.8 governed SourcePlan handoff for verified evidence reuse."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Mapping, Optional

SCHEMA_VERSION = "3.8"
ALLOWED_OUTCOMES = {"VERIFIED_EQUIVALENT", "VERIFIED_ADAPTED"}
ALLOWED_OPS = {"replace_exact", "create_or_replace", "delete_exact", "move_exact"}


class SourcePlanHandoffError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def digest_object(value: Any) -> str:
    return "sha256:" + sha256(_canonical(value)).hexdigest()


def verify_receipt_digest(receipt: Mapping[str, Any]) -> bool:
    claimed = receipt.get("receipt_digest")
    core = {key: value for key, value in receipt.items() if key != "receipt_digest"}
    return isinstance(claimed, str) and claimed == digest_object(core)


def _safe_path(value: Any) -> str:
    path = str(value or "").replace("\\", "/").strip()
    if not path or path.startswith("/") or path == ".." or path.startswith("../") or "/../" in f"/{path}":
        raise SourcePlanHandoffError(f"unsafe SourcePlan path: {path!r}")
    if path.startswith(".git/") or path == ".git":
        raise SourcePlanHandoffError("SourcePlan may not modify .git")
    return path


@dataclass(frozen=True)
class HandoffPolicy:
    max_operations: int = 100
    max_files: int = 100
    require_exact_operations: bool = True
    require_untruncated_diff: bool = True
    require_machine_bounded_plan: bool = True
    require_human_review: bool = True

    @classmethod
    def from_mapping(cls, value: Optional[Mapping[str, Any]]) -> "HandoffPolicy":
        if not value:
            return cls()
        unknown = set(value) - set(cls.__dataclass_fields__)
        if unknown:
            raise SourcePlanHandoffError(f"unknown handoff policy controls: {sorted(unknown)}")
        policy = cls(**dict(value))
        if policy.max_operations < 1 or policy.max_files < 1:
            raise SourcePlanHandoffError("handoff limits must be positive")
        return policy


class SourcePlanReuseHandoffEngine:
    """Bind a successful Phase 3.7 result to a non-applying SourcePlan review packet."""

    def prepare(
        self,
        *,
        outcome_receipt: Mapping[str, Any],
        sourceplan: Mapping[str, Any],
        policy_controls: Optional[Mapping[str, Any]] = None,
        created_at: Optional[str] = None,
    ) -> dict[str, Any]:
        policy = HandoffPolicy.from_mapping(policy_controls)
        blockers: list[str] = []
        warnings: list[str] = []

        if outcome_receipt.get("beast_object_type") != "beast_evidence_reuse_outcome_receipt":
            blockers.append("invalid_phase3_7_object_type")
        if outcome_receipt.get("version") != "3.7":
            blockers.append("phase3_7_outcome_receipt_required")
        if not verify_receipt_digest(outcome_receipt):
            blockers.append("outcome_receipt_digest_invalid")
        if outcome_receipt.get("disposition") not in ALLOWED_OUTCOMES:
            blockers.append("reuse_outcome_not_verified")
        if outcome_receipt.get("sourceplan_synthesis_eligible") is not True:
            blockers.append("sourceplan_synthesis_not_eligible")
        for key in ("workspace_mutation_authorized", "promotion_authorized", "phase2_governance_bypass_allowed"):
            if outcome_receipt.get(key) is True:
                blockers.append(f"outcome_receipt_illegally_sets_{key}")

        if sourceplan.get("beast_object_type") != "sourceplan":
            blockers.append("invalid_sourceplan_object_type")
        if sourceplan.get("kind") != "beast_source_patch_plan":
            blockers.append("invalid_sourceplan_kind")
        if str(sourceplan.get("status") or "") != "draft":
            blockers.append("sourceplan_must_be_draft")
        plan_id = str(sourceplan.get("plan_id") or "").strip()
        if not plan_id:
            blockers.append("sourceplan_plan_id_required")
        if sourceplan.get("diff_truncated") is True and policy.require_untruncated_diff:
            blockers.append("sourceplan_diff_truncated")
        if sourceplan.get("requires_operator_translation") is True and policy.require_machine_bounded_plan:
            blockers.append("sourceplan_requires_operator_translation")

        worktree_id = str(outcome_receipt.get("worktree_id") or "")
        source_task = str(sourceplan.get("worktree_task_id") or "")
        if not worktree_id:
            blockers.append("outcome_worktree_id_required")
        elif source_task != worktree_id:
            blockers.append("sourceplan_worktree_binding_mismatch")

        raw_files = sourceplan.get("files") if isinstance(sourceplan.get("files"), list) else []
        files: list[str] = []
        for value in raw_files:
            try:
                files.append(_safe_path(value))
            except SourcePlanHandoffError as exc:
                blockers.append(str(exc))
        if len(files) > policy.max_files:
            blockers.append("sourceplan_file_budget_exceeded")

        raw_operations = sourceplan.get("operations") if isinstance(sourceplan.get("operations"), list) else []
        if not raw_operations:
            blockers.append("sourceplan_operations_required")
        if len(raw_operations) > policy.max_operations:
            blockers.append("sourceplan_operation_budget_exceeded")

        operations: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        operation_paths: set[str] = set()
        for index, raw in enumerate(raw_operations):
            if not isinstance(raw, Mapping):
                blockers.append(f"invalid_operation:{index}")
                continue
            op = dict(raw)
            op_id = str(op.get("op_id") or "").strip()
            kind = str(op.get("op") or "").strip()
            if not op_id:
                blockers.append(f"operation_id_required:{index}")
            elif op_id in seen_ids:
                blockers.append(f"duplicate_operation_id:{op_id}")
            seen_ids.add(op_id)
            if policy.require_exact_operations and kind not in ALLOWED_OPS:
                blockers.append(f"non_exact_operation:{op_id or index}")
            try:
                path = _safe_path(op.get("path"))
                operation_paths.add(path)
            except SourcePlanHandoffError as exc:
                blockers.append(str(exc))
                path = str(op.get("path") or "")
            if op.get("selected") is False:
                warnings.append(f"operation_not_selected:{op_id or index}")
            normalized = dict(op)
            normalized["path"] = path
            normalized["operation_digest"] = digest_object(op)
            operations.append(normalized)

        if files and not operation_paths.issubset(set(files)):
            blockers.append("operation_path_not_declared_in_files")

        sourceplan_core = {key: value for key, value in sourceplan.items() if key not in {"handoff_receipt", "receipt_digest"}}
        sourceplan_digest = digest_object(sourceplan_core)
        operations_digest = digest_object([item["operation_digest"] for item in operations])
        evidence_bindings = {
            "phase3_7_outcome_receipt_digest": outcome_receipt.get("receipt_digest"),
            "phase3_6_reuse_receipt_digest": outcome_receipt.get("reuse_receipt_digest"),
            "fresh_verification_receipt_digest": outcome_receipt.get("verification_receipt_digest"),
            "outcome_evidence_ref": outcome_receipt.get("outcome_evidence_ref"),
            "current_fingerprint_digest": outcome_receipt.get("current_fingerprint_digest"),
            "candidate_fingerprint_digest": outcome_receipt.get("candidate_fingerprint_digest"),
        }
        for key, value in evidence_bindings.items():
            if not str(value or "").startswith("sha256:"):
                blockers.append(f"missing_digest_binding:{key}")

        disposition = "SOURCEPLAN_REVIEW_READY" if not blockers else "SOURCEPLAN_HANDOFF_BLOCKED"
        core = {
            "version": SCHEMA_VERSION,
            "beast_object_type": "beast_evidence_sourceplan_handoff_receipt",
            "evidence_id": outcome_receipt.get("evidence_id"),
            "plan_id": plan_id,
            "disposition": disposition,
            "sourceplan_digest": sourceplan_digest,
            "operations_digest": operations_digest,
            "operation_count": len(operations),
            "file_count": len(files),
            "files": sorted(set(files)),
            "operation_receipts": [
                {"op_id": item.get("op_id"), "op": item.get("op"), "path": item.get("path"), "operation_digest": item["operation_digest"]}
                for item in operations
            ],
            "evidence_bindings": evidence_bindings,
            "worktree_id": worktree_id,
            "worktree_root_digest": outcome_receipt.get("worktree_root_digest"),
            "reuse_disposition": outcome_receipt.get("disposition"),
            "blockers": sorted(set(blockers)),
            "warnings": sorted(set(warnings)),
            "policy_digest": digest_object(asdict(policy)),
            "created_at": created_at or datetime.now(timezone.utc).isoformat(),
            "authority": "operator_review_only",
            "sourceplan_review_eligible": disposition == "SOURCEPLAN_REVIEW_READY",
            "sourceplan_apply_authorized": False,
            "workspace_mutation_authorized": False,
            "promotion_authorized": False,
            "human_approval_required": policy.require_human_review,
            "phase2_governance_bypass_allowed": False,
        }
        return {**core, "receipt_digest": digest_object(core)}
