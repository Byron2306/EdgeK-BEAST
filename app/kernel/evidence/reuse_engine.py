"""BEAST Phase 3.6 governed evidence reuse kernel.

This module deliberately grants no authority over the operator workspace.
It converts a Phase 3.5 compatibility classification into a deterministic,
bounded reuse plan that must execute in a Phase 2 worktree, pass fresh
verification, and receive human promotion.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

SCHEMA_VERSION = "3.6"
ALLOWED_VERDICTS = {"EXACT", "ADAPTABLE", "REFERENCE", "REJECTED", "REVOKED"}
DENIED_VERDICTS = {"REFERENCE", "REJECTED", "REVOKED"}
ALLOWED_REUSE_MODES = {"EXACT_REPLAY", "ADAPTATION_SEED"}


class ReusePolicyError(ValueError):
    """Raised when a reuse request violates a hard governance boundary."""


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def digest_object(value: Any) -> str:
    return "sha256:" + sha256(_canonical(value)).hexdigest()


def _without_digest(receipt: Mapping[str, Any], digest_key: str) -> Dict[str, Any]:
    return {key: value for key, value in receipt.items() if key != digest_key}


def verify_receipt_digest(
    receipt: Mapping[str, Any],
    *,
    digest_key: str = "receipt_digest",
) -> bool:
    claimed = receipt.get(digest_key)
    return isinstance(claimed, str) and claimed == digest_object(
        _without_digest(receipt, digest_key)
    )


@dataclass(frozen=True)
class ReusePolicy:
    require_compatibility_digest: bool = True
    require_retrieval_binding: bool = True
    require_phase2_worktree: bool = True
    require_fresh_verification: bool = True
    require_human_promotion: bool = True
    allow_exact_replay: bool = True
    allow_adaptation_seed: bool = True
    max_artifact_count: int = 128
    max_total_bytes: int = 16 * 1024 * 1024
    allowed_artifact_kinds: Tuple[str, ...] = (
        "patch",
        "sourceplan_fragment",
        "test_fixture",
        "generated_file",
        "recipe",
    )

    @classmethod
    def from_mapping(cls, value: Optional[Mapping[str, Any]]) -> "ReusePolicy":
        if not value:
            return cls()
        allowed = {field_name for field_name in cls.__dataclass_fields__}
        unknown = set(value) - allowed
        if unknown:
            raise ReusePolicyError(f"unknown reuse policy controls: {sorted(unknown)}")
        data = dict(value)
        if "allowed_artifact_kinds" in data:
            data["allowed_artifact_kinds"] = tuple(data["allowed_artifact_kinds"])
        return cls(**data)


@dataclass(frozen=True)
class ReuseArtifact:
    artifact_id: str
    kind: str
    digest: str
    size_bytes: int
    relative_path: Optional[str] = None
    media_type: Optional[str] = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ReuseArtifact":
        try:
            artifact = cls(
                artifact_id=str(value["artifact_id"]),
                kind=str(value["kind"]),
                digest=str(value["digest"]),
                size_bytes=int(value["size_bytes"]),
                relative_path=(
                    str(value["relative_path"])
                    if value.get("relative_path") is not None
                    else None
                ),
                media_type=(
                    str(value["media_type"])
                    if value.get("media_type") is not None
                    else None
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ReusePolicyError(f"invalid reuse artifact: {exc}") from exc
        if not artifact.artifact_id:
            raise ReusePolicyError("artifact_id must not be empty")
        if not artifact.digest.startswith("sha256:"):
            raise ReusePolicyError("artifact digest must be sha256-bound")
        if artifact.size_bytes < 0:
            raise ReusePolicyError("artifact size must not be negative")
        if artifact.relative_path:
            path = artifact.relative_path.replace("\\", "/")
            if path.startswith("/") or ".." in path.split("/"):
                raise ReusePolicyError("artifact relative_path escapes reuse root")
        return artifact


@dataclass(frozen=True)
class GovernedReuseDecision:
    evidence_id: str
    verdict: str
    requested_mode: str
    disposition: str
    blockers: Tuple[str, ...]
    obligations: Tuple[str, ...]
    artifacts: Tuple[ReuseArtifact, ...]
    compatibility_receipt_digest: str
    retrieval_receipt_digest: Optional[str]
    current_fingerprint_digest: str
    candidate_fingerprint_digest: str
    worktree_id: str
    worktree_root_digest: str
    policy_digest: str
    created_at: str
    authority: str = "bounded_phase2_worktree_only"
    workspace_mutation_authorized: bool = False
    fresh_verification_required: bool = True
    human_promotion_required: bool = True
    phase2_governance_bypass_allowed: bool = False
    reuse_execution_authorized: bool = False
    promotion_authorized: bool = False
    version: str = SCHEMA_VERSION
    beast_object_type: str = "beast_evidence_reuse_receipt"
    receipt_digest: str = field(default="")

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["blockers"] = list(self.blockers)
        data["obligations"] = list(self.obligations)
        data["artifacts"] = [asdict(item) for item in self.artifacts]
        return data


class GovernedEvidenceReuseEngine:
    """Transforms compatibility evidence into a least-authority reuse receipt."""

    def evaluate(
        self,
        *,
        compatibility_receipt: Mapping[str, Any],
        worktree: Mapping[str, Any],
        artifacts: Sequence[Mapping[str, Any]],
        requested_mode: Optional[str] = None,
        current_fingerprint_digest: Optional[str] = None,
        candidate_fingerprint_digest: Optional[str] = None,
        policy_controls: Optional[Mapping[str, Any]] = None,
        created_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        policy = ReusePolicy.from_mapping(policy_controls)
        verdict = str(compatibility_receipt.get("verdict", "")).upper()
        if verdict not in ALLOWED_VERDICTS:
            raise ReusePolicyError(f"unknown compatibility verdict: {verdict or '<empty>'}")

        compatibility_digest = str(compatibility_receipt.get("receipt_digest", ""))
        blockers = []
        obligations = [
            "materialize_only_in_phase2_worktree",
            "preserve_candidate_and_current_fingerprint_binding",
            "run_fresh_verification",
            "produce_new_outcome_evidence",
            "human_review_and_promotion_required",
        ]

        if compatibility_receipt.get("authority") != "classification_only":
            blockers.append("compatibility_authority_not_classification_only")
        if compatibility_receipt.get("reuse_authorized") is True:
            blockers.append("compatibility_receipt_illegally_authorizes_reuse")
        if compatibility_receipt.get("phase2_governance_bypass_allowed") is True:
            blockers.append("compatibility_receipt_illegally_allows_phase2_bypass")
        if policy.require_compatibility_digest and not verify_receipt_digest(
            compatibility_receipt
        ):
            blockers.append("compatibility_receipt_digest_invalid")

        retrieval_digest = compatibility_receipt.get("retrieval_receipt_digest")
        if policy.require_retrieval_binding and not retrieval_digest:
            blockers.append("retrieval_receipt_binding_missing")

        worktree_id = str(worktree.get("worktree_id", ""))
        worktree_root_digest = str(worktree.get("root_digest", ""))
        if policy.require_phase2_worktree:
            if worktree.get("phase") != "2":
                blockers.append("phase2_worktree_required")
            if worktree.get("isolated") is not True:
                blockers.append("isolated_worktree_required")
            if worktree.get("operator_workspace") is True:
                blockers.append("operator_workspace_is_never_a_reuse_target")
            if not worktree_id:
                blockers.append("worktree_id_missing")
            if not worktree_root_digest.startswith("sha256:"):
                blockers.append("worktree_root_digest_missing")

        parsed_artifacts = tuple(ReuseArtifact.from_mapping(item) for item in artifacts)
        if len(parsed_artifacts) > policy.max_artifact_count:
            blockers.append("artifact_count_exceeds_policy")
        if sum(item.size_bytes for item in parsed_artifacts) > policy.max_total_bytes:
            blockers.append("artifact_bytes_exceed_policy")
        disallowed = sorted(
            {item.kind for item in parsed_artifacts}
            - set(policy.allowed_artifact_kinds)
        )
        if disallowed:
            blockers.append("disallowed_artifact_kinds:" + ",".join(disallowed))
        duplicate_ids = _duplicates(item.artifact_id for item in parsed_artifacts)
        if duplicate_ids:
            blockers.append("duplicate_artifact_ids:" + ",".join(duplicate_ids))

        current_digest = current_fingerprint_digest or str(
            compatibility_receipt.get("current_fingerprint_digest", "")
        )
        candidate_digest = candidate_fingerprint_digest or str(
            compatibility_receipt.get("candidate_fingerprint_digest", "")
        )
        if not current_digest.startswith("sha256:"):
            blockers.append("current_fingerprint_digest_missing")
        if not candidate_digest.startswith("sha256:"):
            blockers.append("candidate_fingerprint_digest_missing")

        mode = (requested_mode or self._default_mode(verdict)).upper()
        if mode not in ALLOWED_REUSE_MODES:
            blockers.append("unsupported_reuse_mode")
        if verdict == "EXACT" and mode != "EXACT_REPLAY":
            blockers.append("exact_verdict_requires_exact_replay_mode")
        if verdict == "ADAPTABLE" and mode != "ADAPTATION_SEED":
            blockers.append("adaptable_verdict_requires_adaptation_seed_mode")
        if verdict == "EXACT" and not policy.allow_exact_replay:
            blockers.append("exact_replay_disabled_by_policy")
        if verdict == "ADAPTABLE" and not policy.allow_adaptation_seed:
            blockers.append("adaptation_seed_disabled_by_policy")
        if verdict in DENIED_VERDICTS:
            blockers.append(f"compatibility_verdict_{verdict.lower()}_is_not_reusable")

        disposition = "DENIED"
        execution_authorized = False
        if not blockers and verdict == "EXACT":
            disposition = "PREPARED_EXACT_REPLAY"
            execution_authorized = True
            obligations.append("replay_is_evidence_guided_not_capability_equivalence")
        elif not blockers and verdict == "ADAPTABLE":
            disposition = "PREPARED_ADAPTATION_SEED"
            execution_authorized = True
            obligations.extend(
                [
                    "candidate_output_must_be_transformed_not_blindly_applied",
                    "environment_drift_must_be_resolved_in_new_sourceplan",
                ]
            )

        timestamp = created_at or datetime.now(timezone.utc).isoformat()
        base = GovernedReuseDecision(
            evidence_id=str(compatibility_receipt.get("evidence_id", "")),
            verdict=verdict,
            requested_mode=mode,
            disposition=disposition,
            blockers=tuple(sorted(set(blockers))),
            obligations=tuple(dict.fromkeys(obligations)),
            artifacts=parsed_artifacts,
            compatibility_receipt_digest=compatibility_digest,
            retrieval_receipt_digest=(str(retrieval_digest) if retrieval_digest else None),
            current_fingerprint_digest=current_digest,
            candidate_fingerprint_digest=candidate_digest,
            worktree_id=worktree_id,
            worktree_root_digest=worktree_root_digest,
            policy_digest=digest_object(asdict(policy)),
            created_at=timestamp,
            fresh_verification_required=policy.require_fresh_verification,
            human_promotion_required=policy.require_human_promotion,
            reuse_execution_authorized=execution_authorized,
        )
        data = base.to_dict()
        data["receipt_digest"] = digest_object(_without_digest(data, "receipt_digest"))
        return data

    @staticmethod
    def _default_mode(verdict: str) -> str:
        if verdict == "EXACT":
            return "EXACT_REPLAY"
        return "ADAPTATION_SEED"


def _duplicates(values: Iterable[str]) -> Tuple[str, ...]:
    seen = set()
    duplicates = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return tuple(sorted(duplicates))


def verify_reuse_receipt(receipt: Mapping[str, Any]) -> bool:
    """Verify deterministic integrity and immutable governance denials."""
    if receipt.get("beast_object_type") != "beast_evidence_reuse_receipt":
        return False
    if receipt.get("version") != SCHEMA_VERSION:
        return False
    if receipt.get("workspace_mutation_authorized") is not False:
        return False
    if receipt.get("promotion_authorized") is not False:
        return False
    if receipt.get("phase2_governance_bypass_allowed") is not False:
        return False
    if receipt.get("fresh_verification_required") is not True:
        return False
    if receipt.get("human_promotion_required") is not True:
        return False
    return verify_receipt_digest(receipt)
