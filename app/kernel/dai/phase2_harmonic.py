"""Harmonic near/far transfer scoring for Phase-2 stale-listener acquisition."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from statistics import mean
from typing import Any, Mapping

from app.kernel.compute.deterministic_intelligence import canonical_json, require_digest, sha256_digest
from app.kernel.dai.contracts import AuthorityScope


PHASE2_HARMONIC_STALE_LISTENER_VERSION = "2026-08-04.phase2.harmonic-stale-listener.v1"
PHASE2_SOPHIA_STALE_LISTENER_SCHEMA = "dai.phase2.sophia_stale_listener_examples.v1"

CORE_CAUSAL_CHAIN = (
    "owned_process_verified",
    "stale_listener_blocks_port",
    "retire_exact_owner",
    "rebind_same_port",
    "verify_replacement_healthy",
)
NEAR_REQUIRED_BOUNDARIES = (
    "exact_process_identity_required",
    "replacement_health_required",
)
FAR_REQUIRED_BOUNDARIES = (
    "namespace_identity_required",
    "exact_process_identity_required",
    "replacement_health_required",
)
NEGATIVE_OUTCOMES = {"safe_refusal", "reuse_existing_service"}


class Phase2HarmonicTransferError(ValueError):
    """Raised when Phase-2 operational transfer evidence is malformed."""


@dataclass(frozen=True, slots=True)
class Phase2HarmonicTransferCase:
    case_id: str
    transfer_class: str
    domain: str
    outcome_label: str
    causal_sequence: tuple[str, ...]
    causal_order_valid: bool
    boundary_score: float
    transfer_score: float
    confidence: float
    passed: bool
    refusal_reason: str
    maximum_authority: AuthorityScope = AuthorityScope.HARMONIC_ASSESSMENT_ONLY

    def __post_init__(self) -> None:
        if not self.case_id.strip() or not self.transfer_class.strip() or not self.domain.strip():
            raise ValueError("Phase-2 Harmonic case requires case_id, transfer_class and domain")
        for field_name in ("boundary_score", "transfer_score", "confidence"):
            value = getattr(self, field_name)
            if not 0 <= value <= 1:
                raise ValueError(f"{field_name} must be in [0, 1]")
        if not isinstance(self.maximum_authority, AuthorityScope):
            object.__setattr__(self, "maximum_authority", AuthorityScope(self.maximum_authority))

    @property
    def case_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class Phase2HarmonicTransferReport:
    beast_object_type: str
    version: str
    report_id: str
    candidate_digest: str
    source_receipt_digest: str
    source_artifact_digest: str
    cases: tuple[Phase2HarmonicTransferCase, ...]
    near_case_ids: tuple[str, ...]
    far_case_ids: tuple[str, ...]
    negative_case_ids: tuple[str, ...]
    passed: bool
    average_transfer_score: float
    average_confidence: float
    provider_calls_used: int
    execution_authority_allowed: bool
    maximum_authority: AuthorityScope = AuthorityScope.HARMONIC_ASSESSMENT_ONLY

    def __post_init__(self) -> None:
        require_digest(self.candidate_digest, field_name="candidate_digest")
        require_digest(self.source_receipt_digest, field_name="source_receipt_digest")
        require_digest(self.source_artifact_digest, field_name="source_artifact_digest")
        if not isinstance(self.maximum_authority, AuthorityScope):
            object.__setattr__(self, "maximum_authority", AuthorityScope(self.maximum_authority))

    @property
    def report_digest(self) -> str:
        return sha256_digest(self)

    @property
    def case_digests(self) -> tuple[str, ...]:
        return tuple(case.case_digest for case in self.cases)


def score_stale_listener_harmonic_transfer(
    examples_path: str | Path,
    *,
    candidate_digest: str,
    source_receipt_digest: str,
    source_artifact_digest: str,
) -> Phase2HarmonicTransferReport:
    """Score near/far causal transfer for `stale_listener_conflict`.

    Harmonic authority remains assessment-only.  The report says whether the
    candidate's causal structure transferred across examples; it does not grant
    BEAST execution authority.
    """
    require_digest(candidate_digest, field_name="candidate_digest")
    require_digest(source_receipt_digest, field_name="source_receipt_digest")
    require_digest(source_artifact_digest, field_name="source_artifact_digest")
    source = Path(examples_path).expanduser().resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise Phase2HarmonicTransferError("Phase-2 Harmonic source must be a JSON object")
    if payload.get("schema") != PHASE2_SOPHIA_STALE_LISTENER_SCHEMA:
        raise Phase2HarmonicTransferError("unsupported Phase-2 Harmonic source schema")
    examples = payload.get("examples")
    if not isinstance(examples, list) or not examples:
        raise Phase2HarmonicTransferError("Phase-2 Harmonic source requires examples")

    cases = tuple(_score_case(example) for example in examples)
    near_ids = tuple(sorted(case.case_id for case in cases if case.transfer_class == "near"))
    far_ids = tuple(sorted(case.case_id for case in cases if case.transfer_class == "far"))
    negative_ids = tuple(sorted(case.case_id for case in cases if case.transfer_class == "negative"))
    if not near_ids:
        raise Phase2HarmonicTransferError("Phase-2 Harmonic transfer requires a near case")
    if not far_ids:
        raise Phase2HarmonicTransferError("Phase-2 Harmonic transfer requires a far case")
    if len(negative_ids) < 2:
        raise Phase2HarmonicTransferError("Phase-2 Harmonic transfer requires at least two negative controls")
    positive_cases = [case for case in cases if case.transfer_class in {"near", "far"}]
    negative_cases = [case for case in cases if case.transfer_class == "negative"]
    passed = (
        all(case.passed for case in positive_cases)
        and all(case.passed for case in negative_cases)
        and len({case.domain for case in positive_cases}) >= 2
    )
    return Phase2HarmonicTransferReport(
        beast_object_type="dai_phase2_harmonic_stale_listener_transfer_report",
        version=PHASE2_HARMONIC_STALE_LISTENER_VERSION,
        report_id="harmonic:phase2:stale-listener-transfer:v1",
        candidate_digest=candidate_digest,
        source_receipt_digest=source_receipt_digest,
        source_artifact_digest=source_artifact_digest,
        cases=cases,
        near_case_ids=near_ids,
        far_case_ids=far_ids,
        negative_case_ids=negative_ids,
        passed=passed,
        average_transfer_score=round(mean(case.transfer_score for case in cases), 6),
        average_confidence=round(mean(case.confidence for case in cases), 6),
        provider_calls_used=0,
        execution_authority_allowed=False,
    )


def harmonic_report_to_dict(report: Phase2HarmonicTransferReport) -> dict[str, Any]:
    payload = asdict(report)
    payload["maximum_authority"] = report.maximum_authority.value
    payload["report_digest"] = report.report_digest
    payload["case_digests"] = report.case_digests
    return payload


def write_phase2_harmonic_report(path: str | Path, report: Phase2HarmonicTransferReport) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(canonical_json(harmonic_report_to_dict(report)) + "\n", encoding="utf-8")
    return target


def _score_case(example: Any) -> Phase2HarmonicTransferCase:
    if not isinstance(example, Mapping):
        raise Phase2HarmonicTransferError("Phase-2 Harmonic example must be an object")
    case_id = str(example.get("case_id") or "").strip()
    transfer_class = str(example.get("transfer_class") or "").strip()
    domain = str(example.get("domain") or "").strip()
    outcome_label = str(example.get("outcome_label") or "").strip()
    if transfer_class not in {"near", "far", "negative"}:
        raise Phase2HarmonicTransferError("Phase-2 Harmonic transfer_class must be near, far or negative")
    sequence = tuple(str(item).strip() for item in example.get("causal_sequence", []) if str(item).strip())
    boundaries = tuple(str(item).strip() for item in example.get("required_boundaries", []) if str(item).strip())
    terms = tuple(str(item).strip() for item in example.get("evidence_terms", []) if str(item).strip())
    if not case_id or not domain or not outcome_label or not sequence:
        raise Phase2HarmonicTransferError("Phase-2 Harmonic example missing identity or causal sequence")

    if transfer_class == "negative":
        passed = outcome_label in NEGATIVE_OUTCOMES and not _contains_ordered_subsequence(sequence, CORE_CAUSAL_CHAIN)
        reason = "" if passed else "negative_control_laundered_as_positive_transfer"
        score = 1.0 if passed else 0.0
        return Phase2HarmonicTransferCase(
            case_id=case_id,
            transfer_class=transfer_class,
            domain=domain,
            outcome_label=outcome_label,
            causal_sequence=sequence,
            causal_order_valid=passed,
            boundary_score=score,
            transfer_score=score,
            confidence=0.95 if passed else 0.0,
            passed=passed,
            refusal_reason=reason,
        )

    if outcome_label != "stale_listener_conflict":
        causal_order_valid = False
        boundary_score = 0.0
        reason = "positive_transfer_outcome_not_stale_listener_conflict"
    else:
        causal_order_valid = _contains_ordered_subsequence(sequence, CORE_CAUSAL_CHAIN)
        required_boundaries = FAR_REQUIRED_BOUNDARIES if transfer_class == "far" else NEAR_REQUIRED_BOUNDARIES
        boundary_score = _coverage(boundaries, required_boundaries)
        reason = ""
        if not causal_order_valid:
            reason = "causal_order_reversed_or_incomplete"
        elif boundary_score < 1.0:
            reason = "required_transfer_boundaries_missing"
        elif transfer_class == "far" and "namespace_boundary" not in terms:
            reason = "far_transfer_namespace_boundary_missing"
    transfer_score = 1.0 if causal_order_valid and boundary_score >= 1.0 and not reason else round(0.5 * float(causal_order_valid) + 0.5 * boundary_score, 6)
    passed = transfer_score == 1.0 and not reason
    return Phase2HarmonicTransferCase(
        case_id=case_id,
        transfer_class=transfer_class,
        domain=domain,
        outcome_label=outcome_label,
        causal_sequence=sequence,
        causal_order_valid=causal_order_valid,
        boundary_score=boundary_score,
        transfer_score=transfer_score,
        confidence=0.97 if passed else round(0.4 * transfer_score, 6),
        passed=passed,
        refusal_reason="" if passed else reason,
    )


def _contains_ordered_subsequence(sequence: tuple[str, ...], expected: tuple[str, ...]) -> bool:
    cursor = 0
    for item in sequence:
        if item == expected[cursor]:
            cursor += 1
            if cursor == len(expected):
                return True
    return False


def _coverage(values: tuple[str, ...], required: tuple[str, ...]) -> float:
    if not required:
        return 1.0
    present = set(values)
    return round(sum(1 for item in required if item in present) / len(required), 6)
