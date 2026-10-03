"""Metatron Harmonic -> BEAST transfer assessment bridge.

Harmonic evidence is allowed to say: "this candidate behaved coherently or
discordantly across transfer surfaces."  It is not allowed to say: "therefore
the claim is true."  This bridge turns Sophia/Metatron office-response proof
matrices into bounded transfer receipts.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from statistics import mean
from typing import Any, Mapping

from app.kernel.compute.deterministic_intelligence import sha256_digest
from app.kernel.dai.contracts import ArtifactReceipt, AuthorityScope, DAIOrgan, HarmonicAssessment


class HarmonicBridgeError(ValueError):
    """Raised when harmonic evidence cannot form a bounded transfer assessment."""


@dataclass(frozen=True, slots=True)
class HarmonicTransferCase:
    case_id: str
    office: str
    active_office: str
    document_grounded: bool
    mandos_passed: bool
    office_match: bool
    no_takeover: bool
    has_uncertainty_boundary: bool
    has_learner_handback: bool
    resonance: float
    discord: float
    confidence: float
    harmonic_mode: str
    maximum_authority: AuthorityScope = AuthorityScope.HARMONIC_ASSESSMENT_ONLY

    def __post_init__(self) -> None:
        if not self.case_id.strip() or not self.office.strip() or not self.active_office.strip():
            raise ValueError("harmonic transfer case requires identity and office")
        for field_name in ("resonance", "discord", "confidence"):
            value = getattr(self, field_name)
            if not 0 <= value <= 1:
                raise ValueError(f"{field_name} must be in [0, 1]")
        if not isinstance(self.maximum_authority, AuthorityScope):
            object.__setattr__(self, "maximum_authority", AuthorityScope(self.maximum_authority))

    @property
    def passed(self) -> bool:
        return (
            self.document_grounded
            and self.mandos_passed
            and self.office_match
            and self.no_takeover
            and self.has_uncertainty_boundary
            and self.has_learner_handback
        )

    @property
    def case_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class HarmonicTransferAssessment:
    assessment_id: str
    source_artifact_receipt: str
    cases: tuple[HarmonicTransferCase, ...]
    passed_cases: int
    failed_cases: int
    average_resonance: float
    average_discord: float
    average_confidence: float
    drift_detected: bool
    maximum_authority: AuthorityScope = AuthorityScope.HARMONIC_ASSESSMENT_ONLY

    def __post_init__(self) -> None:
        if not self.assessment_id.strip() or not self.cases:
            raise ValueError("harmonic transfer assessment requires identity and cases")
        for field_name in ("average_resonance", "average_discord", "average_confidence"):
            value = getattr(self, field_name)
            if not 0 <= value <= 1:
                raise ValueError(f"{field_name} must be in [0, 1]")
        if not isinstance(self.maximum_authority, AuthorityScope):
            object.__setattr__(self, "maximum_authority", AuthorityScope(self.maximum_authority))

    @property
    def assessment_digest(self) -> str:
        return sha256_digest(self)

    @property
    def case_digests(self) -> tuple[str, ...]:
        return tuple(case.case_digest for case in self.cases)

    @property
    def offices(self) -> tuple[str, ...]:
        return tuple(case.office for case in self.cases)


def harmonic_transfer_from_office_matrix(
    matrix_path: str | Path,
    *,
    source_receipt: ArtifactReceipt,
) -> tuple[HarmonicAssessment, HarmonicTransferAssessment]:
    if source_receipt.organ is not DAIOrgan.METATRON_HARMONIC:
        raise HarmonicBridgeError("harmonic transfer requires a Metatron harmonic artifact receipt")
    if not source_receipt.verify_file_digest():
        raise HarmonicBridgeError("harmonic artifact digest does not recompute")

    source = Path(matrix_path).expanduser().resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise HarmonicBridgeError("harmonic matrix must be a JSON object")
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    results = payload.get("results") if isinstance(payload.get("results"), list) else None
    if not results:
        raise HarmonicBridgeError("harmonic matrix requires result rows")
    total = int(summary.get("total") or len(results))
    passed = int(summary.get("passed") or 0)
    failed = int(summary.get("failed") or 0)
    if total != len(results):
        raise HarmonicBridgeError("harmonic summary total does not match result rows")
    if passed != total or failed != 0:
        raise HarmonicBridgeError("harmonic matrix contains failed transfer rows")
    if int(summary.get("document_grounded") or 0) != total:
        raise HarmonicBridgeError("harmonic transfer rows are not all document grounded")
    if int(summary.get("mandos_passes") or 0) != total:
        raise HarmonicBridgeError("harmonic transfer rows are not all Mandos passing")
    if int(summary.get("office_active_matches") or 0) != total:
        raise HarmonicBridgeError("harmonic office routing is not stable")

    cases = tuple(_case_from_result(row) for row in results)
    if len({case.office for case in cases}) < 3:
        raise HarmonicBridgeError("harmonic transfer assessment requires at least three offices")
    if not all(case.passed for case in cases):
        raise HarmonicBridgeError("one or more harmonic transfer cases failed release checks")

    drift_detected = any(case.harmonic_mode == "observe_and_review" for case in cases)
    transfer = HarmonicTransferAssessment(
        assessment_id="metatron:harmonic:office-transfer:v1",
        source_artifact_receipt=source_receipt.receipt_digest,
        cases=cases,
        passed_cases=len(cases),
        failed_cases=0,
        average_resonance=round(mean(case.resonance for case in cases), 6),
        average_discord=round(mean(case.discord for case in cases), 6),
        average_confidence=round(mean(case.confidence for case in cases), 6),
        drift_detected=drift_detected,
    )
    assessment = HarmonicAssessment(
        assessment_id="metatron:harmonic:phase1:structured-transfer-assessment",
        source_artifact_receipts=(source_receipt.receipt_digest,),
        coherence_score=transfer.average_resonance,
        discord_score=transfer.average_discord,
        drift_detected=transfer.drift_detected,
        result="structured_transfer_assessment_available_not_truth_authority",
        transfer_receipts=transfer.case_digests + (transfer.assessment_digest,),
    )
    return assessment, transfer


def _case_from_result(row: Any) -> HarmonicTransferCase:
    if not isinstance(row, Mapping):
        raise HarmonicBridgeError("harmonic result row must be an object")
    evaluation = row.get("evaluation") if isinstance(row.get("evaluation"), Mapping) else {}
    checks = evaluation.get("checks") if isinstance(evaluation.get("checks"), Mapping) else {}
    ledger = row.get("response_release_ledger") if isinstance(row.get("response_release_ledger"), Mapping) else {}
    harmonic = ledger.get("harmonic") if isinstance(ledger.get("harmonic"), Mapping) else {}
    office = str(row.get("office") or "")
    active_office = str(row.get("active_office") or "")
    return HarmonicTransferCase(
        case_id=f"harmonic:office:{int(row.get('index') or 0):02d}:{office}",
        office=office,
        active_office=active_office,
        document_grounded=bool(row.get("document_evidence_used")) and bool(checks.get("document_evidence_used")),
        mandos_passed=bool(checks.get("mandos_passed")),
        office_match=bool(checks.get("office_active_match")) and office == active_office,
        no_takeover=bool(checks.get("no_takeover_markers")),
        has_uncertainty_boundary=bool(checks.get("has_pitfall_or_uncertainty")),
        has_learner_handback=bool(checks.get("has_learner_handback")),
        resonance=float(harmonic.get("resonance") or 0.0),
        discord=float(harmonic.get("discord") or 0.0),
        confidence=float(harmonic.get("confidence") or 0.0),
        harmonic_mode=str(harmonic.get("mode") or "unknown"),
    )

