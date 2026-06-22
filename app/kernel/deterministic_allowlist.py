"""Phase 2 Deterministic Displacement Allowlist.

Defines the approved deterministic transforms that can be safely displaced from
model prompts/outputs when verified by paired shadow ablation.

Each entry requires:
- allowed_transform: the candidate name from DETERMINISTIC_SIGNALS
- verifier_command: how to verify the transform result
- risk_class: low/medium/high (high never auto-enforced)
- required_checks: which verification checks must pass
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Set


@dataclass(frozen=True)
class DeterministicTransformSpec:
    """Specification for an approved deterministic transform."""
    allowed_transform: str
    description: str
    risk_class: str  # "low", "medium", "high"
    verifier_command: str
    required_checks: List[str] = field(default_factory=list)
    # Default required checks for Phase 2
    DEFAULT_CHECKS = [
        "visible_tests_equal_or_better",
        "hidden_tests_equal_or_better",
        "scope_checks_equal_or_better",
        "rollback_equal_or_better",
        "security_checks_equal_or_better",
    ]

    def __post_init__(self):
        if self.risk_class not in ("low", "medium", "high"):
            raise ValueError(f"Invalid risk_class: {self.risk_class}")


# Phase 2 Initial Allowlist (from roadmap)
PHASE2_ALLOWLIST: Dict[str, DeterministicTransformSpec] = {
    "schema_validation": DeterministicTransformSpec(
        allowed_transform="schema_validation",
        description="JSON and Action IR schema validation",
        risk_class="low",
        verifier_command="validate_json_schema",
        required_checks=DeterministicTransformSpec.DEFAULT_CHECKS,
    ),
    "route_diagnostics": DeterministicTransformSpec(
        allowed_transform="route_diagnostics",
        description="Provider alias and route normalization",
        risk_class="low",
        verifier_command="normalize_route",
        required_checks=DeterministicTransformSpec.DEFAULT_CHECKS,
    ),
    "patch_compilation": DeterministicTransformSpec(
        allowed_transform="patch_compilation",
        description="Exact patch application followed by compile/lint checks",
        risk_class="medium",
        verifier_command="apply_patch_and_verify",
        required_checks=DeterministicTransformSpec.DEFAULT_CHECKS,
    ),
    "test_execution": DeterministicTransformSpec(
        allowed_transform="test_execution",
        description="Test discovery and deterministic test selection",
        risk_class="medium",
        verifier_command="discover_and_select_tests",
        required_checks=DeterministicTransformSpec.DEFAULT_CHECKS,
    ),
    "syntax_check": DeterministicTransformSpec(
        allowed_transform="syntax_check",
        description="File and handoff hash guards + syntax validation",
        risk_class="low",
        verifier_command="syntax_and_hash_guard",
        required_checks=DeterministicTransformSpec.DEFAULT_CHECKS,
    ),
    "lint_format": DeterministicTransformSpec(
        allowed_transform="lint_format",
        description="Secret detection and redaction (lint + secret scan)",
        risk_class="low",
        verifier_command="lint_and_secret_scan",
        required_checks=DeterministicTransformSpec.DEFAULT_CHECKS,
    ),
}


class Phase2Allowlist:
    """Registry of approved deterministic transforms for Phase 2 enforcement."""

    def __init__(self, specs: Dict[str, DeterministicTransformSpec] = None):
        self.specs = specs or PHASE2_ALLOWLIST

    def is_allowlisted(self, candidate: str) -> bool:
        """Check if a deterministic candidate is on the Phase 2 allowlist."""
        return candidate in self.specs

    def get_spec(self, candidate: str) -> DeterministicTransformSpec | None:
        """Get the specification for an allowlisted transform."""
        return self.specs.get(candidate)

    def get_risk_class(self, candidate: str) -> str:
        """Get the risk class for a candidate (default: high if not allowlisted)."""
        spec = self.specs.get(candidate)
        return spec.risk_class if spec else "high"

    def get_allowed_transforms(self, risk_class: str = None) -> List[str]:
        """Get all allowlisted transforms, optionally filtered by risk class."""
        if risk_class:
            return [
                name for name, spec in self.specs.items()
                if spec.risk_class == risk_class
            ]
        return list(self.specs.keys())

    def requires_verifier(self, candidate: str) -> bool:
        """Check if this transform requires explicit verifier proof."""
        spec = self.specs.get(candidate)
        if not spec:
            return True  # Unknown transforms always require proof
        return spec.risk_class != "low"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the allowlist for inspection."""
        return {
            "beast_object_type": "phase2_deterministic_allowlist",
            "version": "1.0",
            "allowlisted_transforms": {
                name: {
                    "description": spec.description,
                    "risk_class": spec.risk_class,
                    "verifier_command": spec.verifier_command,
                    "required_checks": spec.required_checks,
                }
                for name, spec in self.specs.items()
            },
            "count": len(self.specs),
        }


def create_proof_from_allowlist(
    candidate_name: str,
    task_class: str,
    allowlist: Phase2Allowlist = None,
    **verification_results,
) -> "DeterministicDisplacementProof":
    """Create a DeterministicDisplacementProof from allowlist entry + verification results.
    
    This is the bridge from keyword-detected hypothesis to enforceable proof.
    """
    from app.kernel.compute_ir import DeterministicDisplacementProof
    from datetime import datetime, timezone
    import uuid

    allowlist = allowlist or Phase2Allowlist()
    spec = allowlist.get_spec(candidate_name)
    
    if not spec:
        raise ValueError(f"Candidate '{candidate_name}' not on Phase 2 allowlist")
    
    # Extract verification results with defaults (all False until proven)
    return DeterministicDisplacementProof(
        candidate_name=candidate_name,
        task_class=task_class,
        risk_class=spec.risk_class,
        allowed_transform=spec.allowed_transform,
        verifier_command=spec.verifier_command,
        visible_tests_equal_or_better=verification_results.get("visible_tests_equal_or_better", False),
        hidden_tests_equal_or_better=verification_results.get("hidden_tests_equal_or_better", False),
        scope_checks_equal_or_better=verification_results.get("scope_checks_equal_or_better", False),
        rollback_equal_or_better=verification_results.get("rollback_equal_or_better", False),
        security_checks_equal_or_better=verification_results.get("security_checks_equal_or_better", False),
        paired_ablation_runs=verification_results.get("paired_ablation_runs", 0),
        confidence=verification_results.get("confidence", 0.0),
        approved_for_enforcement=verification_results.get("approved_for_enforcement", False),
        policy_version=verification_results.get("policy_version", "phase2_v1"),
        impact_fingerprint=verification_results.get("impact_fingerprint"),
        expected_output_sha256=str(verification_results.get("expected_output_sha256") or ""),
        created_at=datetime.now(timezone.utc).isoformat(),
        proof_id="proof_" + uuid.uuid4().hex[:16],
    )
