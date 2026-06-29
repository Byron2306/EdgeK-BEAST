"""Canonical public surface for deterministic displacement governance.

The implementation remains split internally for compatibility. New code should
import from this module while legacy imports are migrated.
"""

from app.kernel.governance.deterministic_allowlist import (
    PHASE2_ALLOWLIST,
    DeterministicTransformSpec,
    Phase2Allowlist,
    create_proof_from_allowlist,
)
from app.kernel.governance.deterministic_registry import (
    DeterministicDisplacementRegistry,
    promote_candidate_after_ablation,
)
from app.kernel.governance.deterministic_executor import (
    DeterministicTransformExecutor,
    DeterministicTransformResult,
)

__all__ = [
    "PHASE2_ALLOWLIST",
    "DeterministicTransformSpec",
    "Phase2Allowlist",
    "create_proof_from_allowlist",
    "DeterministicDisplacementRegistry",
    "promote_candidate_after_ablation",
    "DeterministicTransformExecutor",
    "DeterministicTransformResult",
]
