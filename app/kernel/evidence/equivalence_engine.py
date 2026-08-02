"""BEAST Phase 3.7 fresh verification and measured equivalence gate."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Mapping, Optional

SCHEMA_VERSION = "3.7"
PASS_STATES = {"PASS", "PASSED", "SUCCESS", "SUCCEEDED", "GREEN"}
ALLOWED_DISPOSITIONS = {"PREPARED_EXACT_REPLAY", "PREPARED_ADAPTATION_SEED"}

class EquivalencePolicyError(ValueError):
    pass

def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()

def digest_object(value: Any) -> str:
    return "sha256:" + sha256(_canonical(value)).hexdigest()

def verify_receipt_digest(receipt: Mapping[str, Any]) -> bool:
    claimed = receipt.get("receipt_digest")
    core = {k: v for k, v in receipt.items() if k != "receipt_digest"}
    return isinstance(claimed, str) and claimed == digest_object(core)

def _passed(value: Any) -> bool:
    return value is True or str(value or "").strip().upper() in PASS_STATES

@dataclass(frozen=True)
class EquivalencePolicy:
    required_checks: tuple[str, ...] = ("content_safety", "syntax", "focused_tests")
    exact_requires_output_digest_match: bool = True
    adaptable_requires_declared_changes: bool = True
    require_clean_worktree_boundary: bool = True
    require_new_outcome_evidence: bool = True

    @classmethod
    def from_mapping(cls, value: Optional[Mapping[str, Any]]) -> "EquivalencePolicy":
        if not value:
            return cls()
        unknown = set(value) - set(cls.__dataclass_fields__)
        if unknown:
            raise EquivalencePolicyError(f"unknown equivalence policy controls: {sorted(unknown)}")
        data = dict(value)
        if "required_checks" in data:
            data["required_checks"] = tuple(str(x) for x in data["required_checks"])
        return cls(**data)

@dataclass(frozen=True)
class VerificationCheck:
    check_id: str
    status: str
    receipt_digest: str
    evidence_ref: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "VerificationCheck":
        try:
            item = cls(str(value["check_id"]), str(value["status"]), str(value["receipt_digest"]), str(value["evidence_ref"]) if value.get("evidence_ref") else None)
        except (KeyError, TypeError, ValueError) as exc:
            raise EquivalencePolicyError(f"invalid verification check: {exc}") from exc
        if not item.check_id:
            raise EquivalencePolicyError("verification check_id must not be empty")
        if not item.receipt_digest.startswith("sha256:"):
            raise EquivalencePolicyError("verification check must be digest-bound")
        return item

class FreshVerificationEquivalenceEngine:
    """Evaluates new Phase 2 worktree evidence after a Phase 3.6 reuse attempt."""
    def evaluate(self, *, reuse_receipt: Mapping[str, Any], verification_receipt: Mapping[str, Any], observed_outcome: Mapping[str, Any], policy_controls: Optional[Mapping[str, Any]] = None, created_at: Optional[str] = None) -> dict[str, Any]:
        policy = EquivalencePolicy.from_mapping(policy_controls)
        blockers: list[str] = []
        warnings: list[str] = []

        if reuse_receipt.get("beast_object_type") != "beast_evidence_reuse_receipt": blockers.append("invalid_reuse_object_type")
        if reuse_receipt.get("version") != "3.6": blockers.append("phase3_6_reuse_receipt_required")
        if not verify_receipt_digest(reuse_receipt): blockers.append("reuse_receipt_digest_invalid")
        if reuse_receipt.get("disposition") not in ALLOWED_DISPOSITIONS: blockers.append("reuse_was_not_prepared")
        if reuse_receipt.get("reuse_execution_authorized") is not True: blockers.append("reuse_execution_was_not_authorized")
        if reuse_receipt.get("fresh_verification_required") is not True: blockers.append("fresh_verification_obligation_missing")
        for key in ("workspace_mutation_authorized", "promotion_authorized", "phase2_governance_bypass_allowed"):
            if reuse_receipt.get(key) is True: blockers.append(f"reuse_receipt_illegally_sets_{key}")

        if verification_receipt.get("beast_object_type") != "beast_fresh_verification_receipt": blockers.append("invalid_verification_object_type")
        if not verify_receipt_digest(verification_receipt): blockers.append("verification_receipt_digest_invalid")
        if verification_receipt.get("phase2_worktree") is not True: blockers.append("verification_not_run_in_phase2_worktree")
        if policy.require_clean_worktree_boundary and verification_receipt.get("operator_workspace_touched") is True: blockers.append("operator_workspace_was_touched")
        if verification_receipt.get("reuse_receipt_digest") != reuse_receipt.get("receipt_digest"): blockers.append("verification_reuse_receipt_binding_mismatch")
        for key in ("worktree_id", "worktree_root_digest", "current_fingerprint_digest"):
            if verification_receipt.get(key) != reuse_receipt.get(key): blockers.append(f"verification_{key}_binding_mismatch")

        checks = tuple(VerificationCheck.from_mapping(item) for item in (verification_receipt.get("checks") or []))
        check_map = {item.check_id: item for item in checks}
        for required in policy.required_checks:
            if required not in check_map: blockers.append(f"required_check_missing:{required}")
            elif not _passed(check_map[required].status): blockers.append(f"required_check_failed:{required}")
        non_required_failures = sorted(item.check_id for item in checks if item.check_id not in policy.required_checks and not _passed(item.status))
        if non_required_failures: warnings.append("non_required_checks_failed:" + ",".join(non_required_failures))
        if not _passed(verification_receipt.get("overall_status")): blockers.append("verification_overall_status_failed")

        mode = str(reuse_receipt.get("requested_mode") or "")
        candidate_digest = str(observed_outcome.get("candidate_output_digest") or "")
        resulting_digest = str(observed_outcome.get("resulting_output_digest") or "")
        changed_paths = sorted(str(x) for x in (observed_outcome.get("changed_paths") or []))
        equivalence = {"mode": mode, "candidate_output_digest": candidate_digest, "resulting_output_digest": resulting_digest, "changed_paths": changed_paths, "measured_equivalent": False, "adaptation_verified": False}

        if mode == "EXACT_REPLAY":
            if policy.exact_requires_output_digest_match:
                if not candidate_digest.startswith("sha256:") or not resulting_digest.startswith("sha256:"): blockers.append("exact_output_digests_required")
                elif candidate_digest != resulting_digest: blockers.append("exact_output_digest_mismatch")
                else: equivalence["measured_equivalent"] = True
            disposition = "VERIFIED_EQUIVALENT" if not blockers else "VERIFICATION_FAILED"
        elif mode == "ADAPTATION_SEED":
            if policy.adaptable_requires_declared_changes and not changed_paths: blockers.append("adaptation_changed_paths_required")
            if not resulting_digest.startswith("sha256:"): blockers.append("adapted_result_digest_required")
            if observed_outcome.get("drift_resolved") is not True: blockers.append("environment_drift_not_resolved")
            if not blockers: equivalence["adaptation_verified"] = True
            disposition = "VERIFIED_ADAPTED" if not blockers else "VERIFICATION_FAILED"
        else:
            blockers.append("unsupported_reuse_mode")
            disposition = "VERIFICATION_FAILED"

        if policy.require_new_outcome_evidence and not str(observed_outcome.get("outcome_evidence_ref") or "").startswith("sha256:"):
            blockers.append("new_outcome_evidence_required")
            disposition = "VERIFICATION_FAILED"

        core = {
            "version": SCHEMA_VERSION,
            "beast_object_type": "beast_evidence_reuse_outcome_receipt",
            "evidence_id": reuse_receipt.get("evidence_id"),
            "reuse_receipt_digest": reuse_receipt.get("receipt_digest"),
            "verification_receipt_digest": verification_receipt.get("receipt_digest"),
            "disposition": disposition,
            "checks": [asdict(item) for item in checks],
            "equivalence": equivalence,
            "blockers": sorted(set(blockers)),
            "warnings": sorted(set(warnings)),
            "worktree_id": reuse_receipt.get("worktree_id"),
            "worktree_root_digest": reuse_receipt.get("worktree_root_digest"),
            "current_fingerprint_digest": reuse_receipt.get("current_fingerprint_digest"),
            "candidate_fingerprint_digest": reuse_receipt.get("candidate_fingerprint_digest"),
            "outcome_evidence_ref": observed_outcome.get("outcome_evidence_ref"),
            "policy_digest": digest_object(asdict(policy)),
            "created_at": created_at or datetime.now(timezone.utc).isoformat(),
            "authority": "sourceplan_eligibility_only",
            "sourceplan_synthesis_eligible": disposition in {"VERIFIED_EQUIVALENT", "VERIFIED_ADAPTED"},
            "workspace_mutation_authorized": False,
            "promotion_authorized": False,
            "human_promotion_required": True,
            "phase2_governance_bypass_allowed": False,
        }
        return {**core, "receipt_digest": digest_object(core)}

# --- Advanced e-graph-inspired canonical rewrite support -------------------
@dataclass(frozen=True)
class RewriteRule:
    """A bounded, terminating rewrite over canonical JSON-like expressions."""
    name: str
    source: Any
    target: Any


class EGraphRewriteEngine:
    """Small deterministic equality-saturation facade for BEAST policy terms.

    This is intentionally not a full theorem prover.  It repeatedly adds
    equivalent canonical forms using a bounded rule set, then extracts the
    lowest-cost representative.  The hard iteration/node limits prevent
    rewrite explosions in governance paths.
    """

    def __init__(self, rules: tuple[RewriteRule, ...] = (), *, max_iterations: int = 16, max_nodes: int = 4096) -> None:
        self.rules = tuple(rules)
        self.max_iterations = max(1, int(max_iterations))
        self.max_nodes = max(2, int(max_nodes))

    @staticmethod
    def _cost(value: Any) -> tuple[int, bytes]:
        encoded = _canonical(value)
        return len(encoded), encoded

    @staticmethod
    def _walk_replace(value: Any, source: Any, target: Any) -> set[Any]:
        # Returns serialized candidates to keep arbitrary JSON values hashable.
        candidates: set[bytes] = set()
        if value == source:
            candidates.add(_canonical(target))
        if isinstance(value, list):
            for index, child in enumerate(value):
                for replacement in EGraphRewriteEngine._walk_replace(child, source, target):
                    updated = list(value)
                    updated[index] = json.loads(replacement)
                    candidates.add(_canonical(updated))
        elif isinstance(value, dict):
            for key, child in value.items():
                for replacement in EGraphRewriteEngine._walk_replace(child, source, target):
                    updated = dict(value)
                    updated[key] = json.loads(replacement)
                    candidates.add(_canonical(updated))
        return candidates

    def saturate(self, expression: Any) -> dict[str, Any]:
        forms: dict[bytes, Any] = {_canonical(expression): expression}
        iterations = 0
        for iterations in range(1, self.max_iterations + 1):
            before = len(forms)
            for current in tuple(forms.values()):
                for rule in self.rules:
                    for candidate in self._walk_replace(current, rule.source, rule.target):
                        forms.setdefault(candidate, json.loads(candidate))
                        if len(forms) >= self.max_nodes:
                            break
                    if len(forms) >= self.max_nodes:
                        break
                if len(forms) >= self.max_nodes:
                    break
            if len(forms) == before or len(forms) >= self.max_nodes:
                break
        best = min(forms.values(), key=self._cost)
        core = {
            "version": "egraph-1",
            "beast_object_type": "beast_bounded_egraph_receipt",
            "input_digest": digest_object(expression),
            "canonical_expression": best,
            "canonical_digest": digest_object(best),
            "equivalence_class_size": len(forms),
            "iterations": iterations,
            "saturated": len(forms) < self.max_nodes,
            "authority": "equivalence_canonicalization_only",
            "workspace_mutation_authorized": False,
            "promotion_authorized": False,
        }
        return {**core, "receipt_digest": digest_object(core)}
