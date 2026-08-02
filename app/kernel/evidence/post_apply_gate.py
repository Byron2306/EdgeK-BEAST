"""BEAST Phase 3.11 post-apply verification and promotion eligibility gate."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Optional

SCHEMA_VERSION = "3.11"


class PostApplyGateError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def digest_object(value: Any) -> str:
    return "sha256:" + sha256(_canonical(value)).hexdigest()


def verify_receipt_digest(receipt: Mapping[str, Any]) -> bool:
    claimed = receipt.get("receipt_digest")
    core = {key: value for key, value in receipt.items() if key != "receipt_digest"}
    return isinstance(claimed, str) and claimed == digest_object(core)


def _safe_relative(path: str) -> str:
    candidate = Path(path)
    if not path or candidate.is_absolute() or ".." in candidate.parts or ".git" in candidate.parts:
        raise PostApplyGateError(f"unsafe changed-file path: {path}")
    return candidate.as_posix()


@dataclass(frozen=True)
class PostApplyPolicy:
    required_checks: tuple[str, ...] = ("content_safety", "syntax", "focused_tests")
    require_rollback_material: bool = True
    require_clean_verification: bool = True
    require_exact_changed_file_set: bool = True
    maximum_verification_age_seconds: int = 3600

    @classmethod
    def from_mapping(cls, value: Optional[Mapping[str, Any]]) -> "PostApplyPolicy":
        if not value:
            return cls()
        unknown = set(value) - set(cls.__dataclass_fields__)
        if unknown:
            raise PostApplyGateError(f"unknown post-apply policy controls: {sorted(unknown)}")
        data = dict(value)
        if "required_checks" in data:
            checks = data["required_checks"]
            if not isinstance(checks, (list, tuple)) or not checks or any(not isinstance(item, str) or not item for item in checks):
                raise PostApplyGateError("required_checks must be a non-empty string list")
            data["required_checks"] = tuple(dict.fromkeys(checks))
        policy = cls(**data)
        if not 1 <= policy.maximum_verification_age_seconds <= 86400:
            raise PostApplyGateError("invalid maximum_verification_age_seconds")
        return policy


class PostApplyVerificationPromotionGate:
    """Classify an applied SourcePlan as promotion eligible or fail closed."""

    def evaluate(
        self,
        *,
        consumption_receipt: Mapping[str, Any],
        verification_receipt: Mapping[str, Any],
        applied_state: Mapping[str, Any],
        rollback_receipt: Optional[Mapping[str, Any]] = None,
        policy_controls: Optional[Mapping[str, Any]] = None,
        created_at: Optional[str] = None,
    ) -> dict[str, Any]:
        policy = PostApplyPolicy.from_mapping(policy_controls)
        blockers: list[str] = []

        if consumption_receipt.get("beast_object_type") != "beast_evidence_capability_consumption_receipt" or consumption_receipt.get("version") != "3.10":
            blockers.append("phase3_10_consumption_receipt_required")
        if not verify_receipt_digest(consumption_receipt):
            blockers.append("consumption_receipt_digest_invalid")
        if consumption_receipt.get("disposition") != "SOURCEPLAN_APPLIED":
            blockers.append("sourceplan_not_applied")
        if consumption_receipt.get("capability_consumed") is not True or consumption_receipt.get("apply_succeeded") is not True:
            blockers.append("successful_consumed_apply_required")
        if consumption_receipt.get("rollback_performed") is True:
            blockers.append("rolled_back_apply_not_promotable")
        for key in ("promotion_authorized", "phase2_governance_bypass_allowed"):
            if consumption_receipt.get(key) is True:
                blockers.append(f"consumption_receipt_illegally_sets_{key}")

        if verification_receipt.get("beast_object_type") != "beast_post_apply_verification_receipt":
            blockers.append("post_apply_verification_receipt_required")
        if not verify_receipt_digest(verification_receipt):
            blockers.append("verification_receipt_digest_invalid")
        if verification_receipt.get("consumption_receipt_digest") != consumption_receipt.get("receipt_digest"):
            blockers.append("verification_consumption_binding_mismatch")
        if verification_receipt.get("plan_id") != consumption_receipt.get("plan_id"):
            blockers.append("verification_plan_binding_mismatch")
        if verification_receipt.get("worktree_id") != consumption_receipt.get("worktree_id"):
            blockers.append("verification_worktree_binding_mismatch")
        if verification_receipt.get("sourceplan_digest") != consumption_receipt.get("sourceplan_digest"):
            blockers.append("verification_sourceplan_binding_mismatch")
        if verification_receipt.get("operations_digest") != consumption_receipt.get("operations_digest"):
            blockers.append("verification_operations_binding_mismatch")
        if verification_receipt.get("overall_status") != "PASS":
            blockers.append("post_apply_verification_failed")

        checks = verification_receipt.get("checks") or []
        by_id = {str(item.get("check_id")): item for item in checks if isinstance(item, Mapping) and item.get("check_id")}
        for check_id in policy.required_checks:
            check = by_id.get(check_id)
            if not check:
                blockers.append(f"required_check_missing:{check_id}")
            elif check.get("status") != "PASS":
                blockers.append(f"required_check_failed:{check_id}")
            elif not isinstance(check.get("receipt_digest"), str) or not check.get("receipt_digest", "").startswith("sha256:"):
                blockers.append(f"required_check_unbound:{check_id}")

        now = datetime.fromisoformat(created_at.replace("Z", "+00:00")) if created_at else datetime.now(timezone.utc)
        verified_at_raw = verification_receipt.get("verified_at")
        try:
            verified_at = datetime.fromisoformat(str(verified_at_raw).replace("Z", "+00:00"))
            if verified_at.tzinfo is None:
                raise ValueError("timezone required")
            age = (now.astimezone(timezone.utc) - verified_at.astimezone(timezone.utc)).total_seconds()
            if age < -60 or age > policy.maximum_verification_age_seconds:
                blockers.append("post_apply_verification_stale")
        except Exception:
            blockers.append("invalid_verification_timestamp")

        state_files = applied_state.get("files") or []
        normalized_files: list[dict[str, Any]] = []
        seen: set[str] = set()
        for entry in state_files:
            if not isinstance(entry, Mapping):
                blockers.append("invalid_applied_state_entry")
                continue
            try:
                path = _safe_relative(str(entry.get("path") or ""))
            except PostApplyGateError as exc:
                blockers.append(str(exc))
                continue
            if path in seen:
                blockers.append(f"duplicate_applied_state_path:{path}")
            seen.add(path)
            digest = entry.get("digest")
            if not isinstance(digest, str) or not digest.startswith("sha256:"):
                blockers.append(f"missing_applied_file_digest:{path}")
            normalized_files.append({"path": path, "digest": digest, "exists": bool(entry.get("exists", True))})
        normalized_files.sort(key=lambda item: item["path"])
        applied_state_digest = digest_object(normalized_files)
        if applied_state.get("state_digest") != applied_state_digest:
            blockers.append("applied_state_digest_invalid")
        if verification_receipt.get("applied_state_digest") != applied_state_digest:
            blockers.append("verification_applied_state_binding_mismatch")

        changed_files = sorted({_safe_relative(str(path)) for path in consumption_receipt.get("changed_files") or []})
        state_paths = sorted(item["path"] for item in normalized_files)
        if policy.require_exact_changed_file_set and changed_files != state_paths:
            blockers.append("changed_file_set_mismatch")

        rollback_digest = None
        if policy.require_rollback_material:
            rr = rollback_receipt or {}
            if rr.get("beast_object_type") != "beast_sourceplan_rollback_material_receipt":
                blockers.append("rollback_material_receipt_required")
            elif not verify_receipt_digest(rr):
                blockers.append("rollback_material_receipt_digest_invalid")
            else:
                rollback_digest = rr.get("receipt_digest")
                if rr.get("consumption_receipt_digest") != consumption_receipt.get("receipt_digest"):
                    blockers.append("rollback_consumption_binding_mismatch")
                if rr.get("plan_id") != consumption_receipt.get("plan_id") or rr.get("worktree_id") != consumption_receipt.get("worktree_id"):
                    blockers.append("rollback_scope_binding_mismatch")
                materials = rr.get("materials") or []
                material_paths = sorted({_safe_relative(str(item.get("path") or "")) for item in materials if isinstance(item, Mapping)})
                if material_paths != changed_files:
                    blockers.append("rollback_material_file_set_mismatch")
                for item in materials:
                    if not isinstance(item, Mapping) or not isinstance(item.get("preimage_digest"), str) or not item.get("preimage_digest", "").startswith("sha256:"):
                        blockers.append("rollback_preimage_digest_missing")
                        break

        if policy.require_clean_verification and verification_receipt.get("workspace_clean") is not True:
            blockers.append("verified_worktree_not_clean")

        eligible = not blockers
        core = {
            "version": SCHEMA_VERSION,
            "beast_object_type": "beast_evidence_post_apply_promotion_gate_receipt",
            "evidence_id": consumption_receipt.get("evidence_id"),
            "plan_id": consumption_receipt.get("plan_id"),
            "worktree_id": consumption_receipt.get("worktree_id"),
            "disposition": "PROMOTION_ELIGIBLE" if eligible else "PROMOTION_INELIGIBLE",
            "consumption_receipt_digest": consumption_receipt.get("receipt_digest"),
            "verification_receipt_digest": verification_receipt.get("receipt_digest"),
            "rollback_receipt_digest": rollback_digest,
            "sourceplan_digest": consumption_receipt.get("sourceplan_digest"),
            "operations_digest": consumption_receipt.get("operations_digest"),
            "applied_state_digest": applied_state_digest,
            "changed_files": changed_files,
            "required_checks": list(policy.required_checks),
            "blockers": sorted(set(blockers)),
            "policy_digest": digest_object(asdict(policy)),
            "created_at": now.astimezone(timezone.utc).isoformat(),
            "authority": "promotion_eligibility_classification_only",
            "promotion_eligible": eligible,
            "promotion_authorized": False,
            "workspace_promotion_performed": False,
            "human_promotion_required": True,
            "phase2_governance_bypass_allowed": False,
        }
        return {**core, "receipt_digest": digest_object(core)}
