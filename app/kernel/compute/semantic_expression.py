"""Universal semantic expression spine for BEAST.

The central object here is not text, an SVG, or a patch.  It is a canonical
semantic program: entities, claims, causal links, uncertainty boundaries, and
permissions.  Text, visuals, and SourcePlan drafts are deterministic views over
that program.  A verifier recomputes each view from the meaning object so no
modality gets to become the source of truth for another modality.
"""
from __future__ import annotations

import ast
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from datetime import datetime
import difflib
from enum import Enum
import html
import importlib.util
import json
from pathlib import Path
import py_compile
import re
import sys
from typing import Any, Iterable, Mapping, Sequence

from app.kernel.compute.deterministic_intelligence import canonical_json, sha256_bytes, sha256_digest, utc_now_iso


class ClaimStatus(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    STALE = "stale"
    RESIDUAL_REQUIRED = "residual_required"


class ExpressionStyle(str, Enum):
    TECHNICAL = "technical"
    EXECUTIVE = "executive"
    CONVERSATIONAL = "conversational"
    TUTORIAL = "tutorial"
    TERSE = "terse"
    FORENSIC = "forensic"


@dataclass(frozen=True, slots=True)
class SemanticEntity:
    entity_id: str
    kind: str
    label: str
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.entity_id.strip() or not self.kind.strip() or not self.label.strip():
            raise ValueError("semantic entities require id, kind, and label")
        canonical_json(self.attributes)

    @property
    def digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class SemanticClaim:
    claim_id: str
    predicate: str
    subject: str
    object: str = ""
    value: Any = None
    status: ClaimStatus = ClaimStatus.SUPPORTED
    confidence: str = "verified"
    evidence_refs: tuple[str, ...] = ()
    claim_type: str = "fact"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.claim_id.strip() or not self.predicate.strip() or not self.subject.strip():
            raise ValueError("semantic claims require id, predicate, and subject")
        if not isinstance(self.status, ClaimStatus):
            object.__setattr__(self, "status", ClaimStatus(self.status))
        canonical_json(self.value)
        canonical_json(self.metadata)

    @property
    def digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class SemanticEdge:
    edge_id: str
    source_claim: str
    target_claim: str
    relation: str = "causes"
    status: ClaimStatus = ClaimStatus.SUPPORTED
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.edge_id.strip() or not self.source_claim.strip() or not self.target_claim.strip() or not self.relation.strip():
            raise ValueError("semantic edges require identity and claim refs")
        if not isinstance(self.status, ClaimStatus):
            object.__setattr__(self, "status", ClaimStatus(self.status))
        canonical_json(self.metadata)

    @property
    def digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class UncertaintyBoundary:
    boundary_id: str
    unsupported_fields: tuple[str, ...]
    reason: str
    affected_claim_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.boundary_id.strip() or not self.unsupported_fields or not self.reason.strip():
            raise ValueError("uncertainty boundaries require id, unsupported fields, and reason")

    @property
    def digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class SemanticIntent:
    intent: str
    subject: str
    question: str
    audience: str = "operator"
    requested_outputs: tuple[str, ...] = ("text",)

    def __post_init__(self) -> None:
        if not self.intent.strip() or not self.subject.strip() or not self.question.strip():
            raise ValueError("semantic intent requires intent, subject, and question")
        if not self.requested_outputs:
            raise ValueError("semantic intent requires at least one requested output")


@dataclass(frozen=True, slots=True)
class SemanticProgram:
    program_id: str
    intent: SemanticIntent
    entities: tuple[SemanticEntity, ...]
    claims: tuple[SemanticClaim, ...]
    edges: tuple[SemanticEdge, ...] = ()
    boundaries: tuple[UncertaintyBoundary, ...] = ()
    permissions: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    compiler_id: str = "beast.semantic-program.v1"

    def __post_init__(self) -> None:
        if not self.program_id.strip():
            raise ValueError("semantic program requires id")
        entity_ids = {entity.entity_id for entity in self.entities}
        claim_ids = {claim.claim_id for claim in self.claims}
        if len(entity_ids) != len(self.entities):
            raise ValueError("semantic entity ids must be unique")
        if len(claim_ids) != len(self.claims):
            raise ValueError("semantic claim ids must be unique")
        if self.intent.subject not in entity_ids:
            raise ValueError("semantic intent subject must reference an entity")
        for claim in self.claims:
            if claim.subject not in entity_ids:
                raise ValueError(f"claim subject does not reference an entity: {claim.claim_id}")
            if claim.object and claim.object in entity_ids:
                continue
        for edge in self.edges:
            if edge.source_claim not in claim_ids or edge.target_claim not in claim_ids:
                raise ValueError(f"semantic edge has unknown claim ref: {edge.edge_id}")
        for boundary in self.boundaries:
            for ref in boundary.affected_claim_refs:
                if ref not in claim_ids:
                    raise ValueError(f"uncertainty boundary has unknown claim ref: {boundary.boundary_id}")
        canonical_json(self.permissions)

    @property
    def semantic_digest(self) -> str:
        return sha256_digest(self)

    @property
    def entity_map(self) -> dict[str, SemanticEntity]:
        return {entity.entity_id: entity for entity in self.entities}

    @property
    def claim_map(self) -> dict[str, SemanticClaim]:
        return {claim.claim_id: claim for claim in self.claims}


@dataclass(frozen=True, slots=True)
class DiscourseStep:
    step_id: str
    act: str
    claim_refs: tuple[str, ...] = ()
    boundary_refs: tuple[str, ...] = ()
    text: str = ""

    @property
    def digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class DiscoursePlan:
    plan_id: str
    semantic_digest: str
    style: ExpressionStyle
    steps: tuple[DiscourseStep, ...]
    plan_sequence: int = 2
    planner_id: str = "beast.discourse-planner.v1"

    def __post_init__(self) -> None:
        if not isinstance(self.style, ExpressionStyle):
            object.__setattr__(self, "style", ExpressionStyle(self.style))
        if not self.steps:
            raise ValueError("discourse plan requires steps")

    @property
    def digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class SceneNode:
    node_id: str
    entity_ref: str
    x: int
    y: int
    width: int
    height: int
    label: str
    status: ClaimStatus = ClaimStatus.SUPPORTED

    @property
    def digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class SceneEdge:
    edge_id: str
    semantic_edge_ref: str
    from_entity: str
    to_entity: str
    label: str
    status: ClaimStatus = ClaimStatus.SUPPORTED

    @property
    def digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class SemanticScenePlan:
    plan_id: str
    semantic_digest: str
    nodes: tuple[SceneNode, ...]
    edges: tuple[SceneEdge, ...]
    uncertainty_markers: tuple[Mapping[str, Any], ...] = ()
    width: int = 960
    height: int = 540
    compile_sequence: int = 3
    compiler_id: str = "beast.semantic-scene-compiler.v1"

    @property
    def digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class SourcePlanDraft:
    plan_id: str
    semantic_digest: str
    objective: str
    operations: tuple[Mapping[str, Any], ...]
    preconditions: tuple[str, ...]
    postconditions: tuple[str, ...]
    approval_required: bool = True
    status: str = "draft_requires_approval"
    compiler_id: str = "beast.semantic-sourceplan-compiler.v1"

    @property
    def digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    issue_id: str
    severity: str
    issue_class: str
    message: str
    refs: tuple[str, ...] = ()

    @property
    def digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class SemanticValidationReport:
    semantic_digest: str
    issues: tuple[ValidationIssue, ...]
    validator_id: str = "beast.semantic-validator.v1"

    @property
    def critical_issues(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "critical")

    @property
    def accepted(self) -> bool:
        return not self.critical_issues

    @property
    def digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class PredicateLaw:
    predicate: str
    value_type: str
    subject_kinds: tuple[str, ...] = ()
    object_kinds: tuple[str, ...] = ()
    allowed_values: tuple[Any, ...] = ()
    true_text: str = ""
    false_text: str = ""
    visual_true: str = ""
    visual_false: str = ""
    object_required: bool = False
    evidence_required_when_supported: bool = False
    claim_types: tuple[str, ...] = ("fact",)

    @property
    def digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class SemanticArtifact:
    media_type: str
    content: bytes
    sequence: int
    status: str = "rendered"
    failure_class: str = ""

    @property
    def digest(self) -> str:
        return sha256_bytes(self.content)


@dataclass(frozen=True, slots=True)
class SemanticExpressionResult:
    program: SemanticProgram
    validation_report: SemanticValidationReport
    discourse_plan: DiscoursePlan
    text_artifact: SemanticArtifact
    scene_plan: SemanticScenePlan
    visual_artifact: SemanticArtifact
    sourceplan: SourcePlanDraft
    residual_decision: Mapping[str, Any]
    joined_receipt: Mapping[str, Any]
    verification: Mapping[str, Any]


class SemanticExpressionEngine:
    def compile(self, program: SemanticProgram, *, style: ExpressionStyle | str = ExpressionStyle.TECHNICAL) -> SemanticExpressionResult:
        style = ExpressionStyle(style)
        validation = SemanticValidator().validate(program)
        residual = ResidualRouter().decide(program, validation)
        if residual["action"] == "refuse":
            discourse_plan = RefusalCompiler().plan(program, validation, style=style)
            text_artifact = RefusalCompiler().text_artifact(program, discourse_plan, validation, residual)
            scene_plan = RefusalCompiler().scene_plan(program)
            visual_artifact = RefusalCompiler().visual_artifact(program, validation, residual)
            sourceplan = RefusalCompiler().sourceplan(program, validation)
        elif residual["action"] == "bounded_residual":
            discourse_plan = ResidualPendingCompiler().plan(program, style=style)
            text_artifact = ResidualPendingCompiler().text_artifact(program, discourse_plan, residual)
            scene_plan = ResidualPendingCompiler().scene_plan(program)
            visual_artifact = ResidualPendingCompiler().visual_artifact(program, residual)
            sourceplan = ResidualPendingCompiler().sourceplan(program)
        else:
            discourse_plan = DiscoursePlanner().plan(program, style=style)
            text_artifact = Lexicalizer().render(program, discourse_plan)
            scene_plan = SceneCompiler().compile(program)
            visual_artifact = SvgSceneRenderer().render(program, scene_plan)
            sourceplan = SourcePlanCompiler().compile(program)
        receipt, verification = ExpressionVerifier().verify(
            program=program,
            validation_report=validation,
            discourse_plan=discourse_plan,
            text_artifact=text_artifact,
            scene_plan=scene_plan,
            visual_artifact=visual_artifact,
            sourceplan=sourceplan,
            residual_decision=residual,
        )
        return SemanticExpressionResult(
            program=program,
            validation_report=validation,
            discourse_plan=discourse_plan,
            text_artifact=text_artifact,
            scene_plan=scene_plan,
            visual_artifact=visual_artifact,
            sourceplan=sourceplan,
            residual_decision=residual,
            joined_receipt=receipt,
            verification=verification,
        )


class EvidenceResolver:
    """Resolve evidence refs into receipt objects and bind them to propositions."""

    CLAIM_OBJECT_TYPE = "semantic_evidence_receipt"
    EDGE_OBJECT_TYPE = "semantic_relationship_receipt"
    POLICY_GENERATION = "semantic-evidence-policy-2026-08-04.1"

    def verify_claim_receipt(
        self,
        program: SemanticProgram,
        claim: SemanticClaim,
        ref: str,
        authority: str,
    ) -> tuple[ValidationIssue, ...]:
        receipts = _mapping(program.permissions.get("evidence_receipts"))
        receipt = _mapping(receipts.get(ref))
        if not receipt:
            return (ValidationIssue(
                issue_id=f"issue:evidence-receipt-missing:{claim.claim_id}",
                severity="critical",
                issue_class="evidence_receipt_missing",
                message="Evidence ref has no resolvable receipt in the semantic program.",
                refs=(claim.claim_id, ref),
            ),)
        failures: list[ValidationIssue] = []
        self._check_receipt_digest(failures, ref, receipt, claim.claim_id, "evidence")
        expected = {
            "beast_object_type": self.CLAIM_OBJECT_TYPE,
            "policy_generation": self.POLICY_GENERATION,
            "claim_id": claim.claim_id,
            "subject": claim.subject,
            "predicate": claim.predicate,
            "object": claim.object,
            "value": claim.value,
            "status": claim.status.value,
            "confidence": claim.confidence,
            "authority": authority,
            "program_created_at": program.created_at,
        }
        for key, value in expected.items():
            if receipt.get(key) != value:
                failures.append(ValidationIssue(
                    issue_id=f"issue:evidence-receipt-binding:{claim.claim_id}:{key}",
                    severity="critical",
                    issue_class="evidence_receipt_binding_mismatch",
                    message="Evidence receipt does not bind to the exact claim proposition.",
                    refs=(claim.claim_id, ref, key),
                ))
        if not str(receipt.get("attestation_digest") or "").startswith("sha256:"):
            failures.append(ValidationIssue(
                issue_id=f"issue:evidence-attestation:{claim.claim_id}",
                severity="critical",
                issue_class="evidence_receipt_attestation_missing",
                message="Evidence receipt lacks an attestation digest.",
                refs=(claim.claim_id, ref),
            ))
        return tuple(failures)

    def verify_edge_receipt(
        self,
        program: SemanticProgram,
        edge: SemanticEdge,
        ref: str,
        authority: str,
    ) -> tuple[ValidationIssue, ...]:
        receipts = _mapping(program.permissions.get("relationship_receipts"))
        receipt = _mapping(receipts.get(ref))
        if not receipt:
            return (ValidationIssue(
                issue_id=f"issue:relationship-receipt-missing:{edge.edge_id}",
                severity="critical",
                issue_class="relationship_receipt_missing",
                message="Relationship evidence ref has no resolvable receipt in the semantic program.",
                refs=(edge.edge_id, ref),
            ),)
        failures: list[ValidationIssue] = []
        self._check_receipt_digest(failures, ref, receipt, edge.edge_id, "relationship")
        expected = {
            "beast_object_type": self.EDGE_OBJECT_TYPE,
            "policy_generation": self.POLICY_GENERATION,
            "edge_id": edge.edge_id,
            "source_claim": edge.source_claim,
            "target_claim": edge.target_claim,
            "relation": edge.relation,
            "status": edge.status.value,
            "authority": authority,
            "program_created_at": program.created_at,
        }
        for key, value in expected.items():
            if receipt.get(key) != value:
                failures.append(ValidationIssue(
                    issue_id=f"issue:relationship-receipt-binding:{edge.edge_id}:{key}",
                    severity="critical",
                    issue_class="relationship_receipt_binding_mismatch",
                    message="Relationship receipt does not bind to the exact semantic edge.",
                    refs=(edge.edge_id, ref, key),
                ))
        if not str(receipt.get("attestation_digest") or "").startswith("sha256:"):
            failures.append(ValidationIssue(
                issue_id=f"issue:relationship-attestation:{edge.edge_id}",
                severity="critical",
                issue_class="relationship_receipt_attestation_missing",
                message="Relationship receipt lacks an attestation digest.",
                refs=(edge.edge_id, ref),
            ))
        return tuple(failures)

    def _check_receipt_digest(
        self,
        failures: list[ValidationIssue],
        ref: str,
        receipt: Mapping[str, Any],
        object_id: str,
        label: str,
    ) -> None:
        claimed = str(receipt.get("receipt_digest") or "")
        recomputed = _receipt_digest(receipt)
        if claimed != ref or recomputed != ref:
            failures.append(ValidationIssue(
                issue_id=f"issue:{label}-receipt-digest:{object_id}",
                severity="critical",
                issue_class=f"{label}_receipt_digest_mismatch",
                message="Receipt digest does not recompute to the referenced digest.",
                refs=(object_id, ref, claimed, recomputed),
            ))


class SemanticPredicateLawRegistry:
    """Typed law for predicate meaning, value type, evidence, and target identity."""

    _STATE_VALUES = (
        "expired",
        "valid",
        "healthy",
        "failed",
        "compromised",
        "rainy",
        "enabled",
        "disabled",
        "available",
        "unavailable",
        "accepted",
        "refused",
        "current",
        "stale",
    )
    _LAWS: tuple[PredicateLaw, ...] = (
        PredicateLaw(
            predicate="state",
            value_type="string",
            subject_kinds=("service", "credential", "deployment", "external_context", "system", "artifact"),
            allowed_values=_STATE_VALUES,
            true_text="was {value}",
            visual_true="state:{value}",
            evidence_required_when_supported=True,
        ),
        PredicateLaw(
            predicate="failed",
            value_type="bool",
            subject_kinds=("service", "protocol", "monitor", "appliance", "test_suite", "system"),
            true_text="failed",
            false_text="did not fail",
            visual_true="failure badge",
            visual_false="healthy badge",
            evidence_required_when_supported=True,
        ),
        PredicateLaw(
            predicate="rolled_back",
            value_type="bool",
            subject_kinds=("deployment",),
            object_kinds=("deployment_action",),
            true_text="rolled back",
            false_text="did not roll back",
            visual_true="rollback badge",
            visual_false="no rollback badge",
            object_required=True,
            evidence_required_when_supported=True,
        ),
        PredicateLaw(
            predicate="code_transform_objective",
            value_type="identifier",
            subject_kinds=("code_symbol",),
            object_kinds=("capability",),
            object_required=True,
        ),
        PredicateLaw(
            predicate="target_symbol",
            value_type="python_symbol",
            subject_kinds=("code_symbol",),
        ),
        PredicateLaw(
            predicate="preserve_public_api",
            value_type="bool",
            subject_kinds=("interface",),
            true_text="must remain unchanged",
            false_text="may change",
            visual_true="api preserved",
            visual_false="api break risk",
        ),
        PredicateLaw(
            predicate="temperature",
            value_type="quantity",
            subject_kinds=("reactor", "sensor", "service", "system"),
            true_text="temperature was {value}",
            visual_true="temperature:{value}",
            evidence_required_when_supported=True,
        ),
        PredicateLaw(
            predicate="test_requirement",
            value_type="nonempty_string",
            subject_kinds=("test_suite",),
        ),
        PredicateLaw(predicate="enabled", value_type="bool", subject_kinds=("service", "system", "feature"), true_text="was enabled", false_text="was not enabled"),
        PredicateLaw(predicate="disabled", value_type="bool", subject_kinds=("service", "system", "feature"), true_text="was disabled", false_text="was not disabled"),
        PredicateLaw(predicate="available", value_type="bool", subject_kinds=("service", "system", "artifact"), true_text="was available", false_text="was unavailable"),
        PredicateLaw(predicate="unavailable", value_type="bool", subject_kinds=("service", "system", "artifact"), true_text="was unavailable", false_text="was available"),
        PredicateLaw(predicate="accepted", value_type="bool", subject_kinds=("artifact", "claim", "decision"), true_text="was accepted", false_text="was not accepted"),
        PredicateLaw(predicate="refused", value_type="bool", subject_kinds=("artifact", "claim", "decision"), true_text="was refused", false_text="was not refused"),
        PredicateLaw(predicate="current", value_type="bool", subject_kinds=("artifact", "claim", "evidence", "service", "system"), true_text="was current", false_text="was not current"),
    )

    _CONFIDENCE_VALUES = ("verified", "observed", "inferred", "unverified")
    _CLAIM_TYPES = ("fact", "constraint", "code_transform", "evidence", "context")
    _EVIDENCE_AUTHORITIES = ("verified_receipt", "capability_receipt", "promotion_receipt", "sensorium_receipt")
    _RELATIONSHIP_AUTHORITIES = ("relationship_receipt", "causal_receipt", "capability_receipt", "promotion_receipt")
    _EVIDENCE_REF = re.compile(r"^sha256:[0-9a-f]{64}$")
    _PYTHON_SYMBOL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+$")
    _IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

    def law_for(self, predicate: str) -> PredicateLaw | None:
        return next((law for law in self._LAWS if law.predicate == predicate), None)

    def validate(self, program: SemanticProgram) -> tuple[ValidationIssue, ...]:
        issues: list[ValidationIssue] = []
        entity_map = program.entity_map
        program_created = _parse_iso_timestamp(program.created_at)
        if program_created is None:
            issues.append(ValidationIssue(
                issue_id="issue:malformed-program-created-at",
                severity="critical",
                issue_class="malformed_program_timestamp",
                message="Semantic program created_at must be a timezone-aware ISO-8601 timestamp.",
                refs=(program.created_at,),
            ))
        for claim in program.claims:
            law = self.law_for(claim.predicate)
            if law is None:
                issues.append(ValidationIssue(
                    issue_id=f"issue:unknown-predicate:{claim.claim_id}",
                    severity="critical",
                    issue_class="unknown_predicate",
                    message="Claim predicate has no registered typed law.",
                    refs=(claim.claim_id, claim.predicate),
                ))
                continue
            issues.extend(self._validate_claim_against_law(program, claim, law, program_created))
        for edge in program.edges:
            if edge.relation not in {"causes", "constrained_by", "verified_by"}:
                issues.append(ValidationIssue(
                    issue_id=f"issue:unknown-relation:{edge.edge_id}",
                    severity="critical",
                    issue_class="unknown_edge_relation",
                    message="Semantic edge relation has no registered meaning law.",
                    refs=(edge.edge_id, edge.relation),
                ))
            if edge.status is ClaimStatus.SUPPORTED and edge.relation in {"causes", "constrained_by", "verified_by"}:
                ref = str(edge.metadata.get("evidence_ref") or "")
                authority = str(edge.metadata.get("evidence_authority") or "")
                if authority not in self._RELATIONSHIP_AUTHORITIES:
                    issues.append(ValidationIssue(
                        issue_id=f"issue:edge-evidence-authority:{edge.edge_id}",
                        severity="critical",
                        issue_class="supported_edge_lacks_relationship_authority",
                        message="Supported semantic relationships require typed relationship receipt authority.",
                        refs=(edge.edge_id, authority),
                    ))
                if not ref:
                    issues.append(ValidationIssue(
                        issue_id=f"issue:edge-evidence-missing:{edge.edge_id}",
                        severity="critical",
                        issue_class="relationship_evidence_required_missing",
                        message="Supported semantic relationships require a receipt reference.",
                        refs=(edge.edge_id,),
                    ))
                elif not self._EVIDENCE_REF.match(ref):
                    issues.append(ValidationIssue(
                        issue_id=f"issue:edge-evidence-ref:{edge.edge_id}",
                        severity="critical",
                        issue_class="invalid_evidence_ref",
                        message="Edge evidence_ref must be a SHA-256 digest.",
                        refs=(edge.edge_id, ref),
                    ))
                else:
                    issues.extend(EvidenceResolver().verify_edge_receipt(program, edge, ref, authority))
        return tuple(issues)

    def _validate_claim_against_law(
        self,
        program: SemanticProgram,
        claim: SemanticClaim,
        law: PredicateLaw,
        program_created: datetime | None,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        subject = program.entity_map[claim.subject]
        obj = program.entity_map.get(claim.object) if claim.object else None
        if law.subject_kinds and subject.kind not in law.subject_kinds:
            issues.append(ValidationIssue(
                issue_id=f"issue:subject-kind:{claim.claim_id}",
                severity="critical",
                issue_class="target_identity_kind_mismatch",
                message=f"Predicate {claim.predicate} is not authorized for subject kind {subject.kind}.",
                refs=(claim.claim_id, claim.subject, subject.kind),
            ))
        if law.object_required and not claim.object:
            issues.append(ValidationIssue(
                issue_id=f"issue:object-required:{claim.claim_id}",
                severity="critical",
                issue_class="predicate_object_required",
                message=f"Predicate {claim.predicate} requires an object identity.",
                refs=(claim.claim_id,),
            ))
        if claim.object and law.object_kinds and (obj is None or obj.kind not in law.object_kinds):
            issues.append(ValidationIssue(
                issue_id=f"issue:object-kind:{claim.claim_id}",
                severity="critical",
                issue_class="target_identity_kind_mismatch",
                message=f"Predicate {claim.predicate} object kind is not authorized.",
                refs=(claim.claim_id, claim.object, obj.kind if obj is not None else "missing"),
            ))
        if not self._value_matches_law(claim.value, law):
            issues.append(ValidationIssue(
                issue_id=f"issue:value-type:{claim.claim_id}",
                severity="critical",
                issue_class="predicate_value_type_mismatch",
                message=f"Predicate {claim.predicate} requires value type {law.value_type}.",
                refs=(claim.claim_id, canonical_json(claim.value)),
            ))
        if law.allowed_values and claim.value not in law.allowed_values:
            issues.append(ValidationIssue(
                issue_id=f"issue:value-domain:{claim.claim_id}",
                severity="critical",
                issue_class="predicate_value_domain_mismatch",
                message=f"Predicate {claim.predicate} value is outside the registered domain.",
                refs=(claim.claim_id, str(claim.value)),
            ))
        if claim.confidence not in self._CONFIDENCE_VALUES:
            issues.append(ValidationIssue(
                issue_id=f"issue:confidence:{claim.claim_id}",
                severity="critical",
                issue_class="invalid_evidence_state",
                message="Claim confidence/evidence state has no registered meaning.",
                refs=(claim.claim_id, claim.confidence),
            ))
        if claim.claim_type not in self._CLAIM_TYPES:
            issues.append(ValidationIssue(
                issue_id=f"issue:claim-type:{claim.claim_id}",
                severity="critical",
                issue_class="invalid_claim_type",
                message="Claim type has no registered meaning.",
                refs=(claim.claim_id, claim.claim_type),
            ))
        if claim.status is ClaimStatus.SUPPORTED and claim.confidence not in {"verified", "observed"}:
            issues.append(ValidationIssue(
                issue_id=f"issue:supported-confidence:{claim.claim_id}",
                severity="critical",
                issue_class="supported_claim_lacks_verified_evidence_state",
                message="Supported claims require verified or observed evidence state.",
                refs=(claim.claim_id, claim.confidence),
            ))
        if law.evidence_required_when_supported and claim.status is ClaimStatus.SUPPORTED:
            authority = str(claim.metadata.get("evidence_authority") or "")
            if authority not in self._EVIDENCE_AUTHORITIES:
                issues.append(ValidationIssue(
                    issue_id=f"issue:evidence-authority:{claim.claim_id}",
                    severity="critical",
                    issue_class="supported_claim_lacks_evidence_authority",
                    message="Supported operational claims require verified evidence, capability, promotion, or sensorium receipt authority.",
                    refs=(claim.claim_id, authority),
                ))
            if not claim.evidence_refs:
                issues.append(ValidationIssue(
                    issue_id=f"issue:evidence-missing:{claim.claim_id}",
                    severity="critical",
                    issue_class="evidence_required_missing",
                    message=f"Predicate {claim.predicate} requires evidence refs when supported.",
                    refs=(claim.claim_id,),
                ))
            for ref in claim.evidence_refs:
                if not self._EVIDENCE_REF.match(ref):
                    issues.append(ValidationIssue(
                        issue_id=f"issue:evidence-ref:{claim.claim_id}:{sha256_digest(ref).removeprefix('sha256:')[:12]}",
                        severity="critical",
                        issue_class="invalid_evidence_ref",
                        message="Evidence refs must be SHA-256 digests.",
                        refs=(claim.claim_id, ref),
                    ))
                else:
                    issues.extend(EvidenceResolver().verify_claim_receipt(program, claim, ref, authority))
        observed = _parse_iso_timestamp(str(claim.metadata.get("observed_at"))) if claim.metadata.get("observed_at") else None
        expires = _parse_iso_timestamp(str(claim.metadata.get("expires_at"))) if claim.metadata.get("expires_at") else None
        if claim.status is ClaimStatus.SUPPORTED and expires is not None and program_created is not None and expires < program_created:
            issues.append(ValidationIssue(
                issue_id=f"issue:temporal-authority-expired:{claim.claim_id}",
                severity="critical",
                issue_class="temporal_authority_expired",
                message="Supported current claim has expired before the semantic program timestamp.",
                refs=(claim.claim_id, str(claim.metadata.get("expires_at")), program.created_at),
            ))
        if observed is not None and program_created is not None and observed > program_created:
            issues.append(ValidationIssue(
                issue_id=f"issue:future-observation:{claim.claim_id}",
                severity="critical",
                issue_class="temporal_authority_future_observation",
                message="Claim observation time is after the semantic program timestamp.",
                refs=(claim.claim_id, str(claim.metadata.get("observed_at")), program.created_at),
            ))
        return issues

    def _value_matches_law(self, value: Any, law: PredicateLaw) -> bool:
        if law.value_type == "bool_true":
            return value is True
        if law.value_type == "bool":
            return isinstance(value, bool)
        if law.value_type == "string":
            return isinstance(value, str) and bool(value.strip())
        if law.value_type == "nonempty_string":
            return isinstance(value, str) and bool(value.strip())
        if law.value_type == "identifier":
            return isinstance(value, str) and self._IDENTIFIER.match(value) is not None
        if law.value_type == "python_symbol":
            return isinstance(value, str) and self._PYTHON_SYMBOL.match(value) is not None
        if law.value_type == "quantity":
            if not isinstance(value, Mapping):
                return False
            unit = str(value.get("unit") or "")
            dimension = str(value.get("dimension") or "")
            magnitude = value.get("magnitude")
            allowed_units = {"temperature": {"degC", "degF", "K"}}
            return (
                isinstance(magnitude, (int, float))
                and dimension in allowed_units
                and unit in allowed_units[dimension]
            )
        return False


class SemanticValidator:
    def validate(self, program: SemanticProgram) -> SemanticValidationReport:
        issues: list[ValidationIssue] = []
        issues.extend(SemanticPredicateLawRegistry().validate(program))
        issues.extend(self._contradictions(program))
        issues.extend(self._unsupported_without_boundary(program))
        issues.extend(self._temporal_consistency(program))
        issues.extend(self._causal_structure(program))
        issues.extend(self._code_symbol_authority(program))
        return SemanticValidationReport(program.semantic_digest, tuple(issues))

    def _contradictions(self, program: SemanticProgram) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        supported = [claim for claim in program.claims if claim.status is ClaimStatus.SUPPORTED]
        grouped: dict[tuple[str, str, str], list[SemanticClaim]] = {}
        for claim in supported:
            grouped.setdefault((claim.subject, claim.predicate, claim.object), []).append(claim)
        for key, claims in grouped.items():
            values = {canonical_json(claim.value) for claim in claims}
            if len(values) > 1:
                issues.append(ValidationIssue(
                    issue_id="issue:contradiction:" + sha256_digest(key).removeprefix("sha256:")[:16],
                    severity="critical",
                    issue_class="mutually_contradictory_claims",
                    message="Supported claims assert incompatible values for the same subject/predicate/object.",
                    refs=tuple(claim.claim_id for claim in claims),
                ))
        state_by_subject: dict[str, list[SemanticClaim]] = {}
        for claim in supported:
            if claim.predicate == "state":
                state_by_subject.setdefault(claim.subject, []).append(claim)
        for subject, claims in state_by_subject.items():
            states = {canonical_json(claim.value) for claim in claims}
            if len(states) > 1:
                issues.append(ValidationIssue(
                    issue_id=f"issue:exclusive-state:{subject}",
                    severity="critical",
                    issue_class="mutually_exclusive_state",
                    message="A single entity has multiple supported state values.",
                    refs=tuple(claim.claim_id for claim in claims),
                ))
        issues.extend(self._ontology_exclusions(supported))
        return issues

    def _ontology_exclusions(self, supported: Sequence[SemanticClaim]) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        tokens_by_subject: dict[str, dict[str, SemanticClaim]] = {}
        for claim in supported:
            token = _ontology_token(claim)
            if token:
                tokens_by_subject.setdefault(claim.subject, {})[token] = claim
        exclusive_sets = (
            frozenset(("healthy", "failed_positive")),
            frozenset(("failed_positive", "failed_negative")),
            frozenset(("enabled", "disabled")),
            frozenset(("available", "unavailable")),
            frozenset(("accepted", "refused")),
            frozenset(("current", "stale")),
        )
        for subject, tokens in tokens_by_subject.items():
            for exclusive in exclusive_sets:
                overlap = exclusive.intersection(tokens)
                if len(overlap) > 1:
                    refs = tuple(tokens[token].claim_id for token in sorted(overlap))
                    issues.append(ValidationIssue(
                        issue_id="issue:ontology-xor:" + subject + ":" + "-".join(sorted(overlap)),
                        severity="critical",
                        issue_class="ontology_mutual_exclusion",
                        message="Supported claims violate ontology-level mutual exclusion.",
                        refs=refs,
                    ))
        return issues

    def _unsupported_without_boundary(self, program: SemanticProgram) -> list[ValidationIssue]:
        bounded = {ref for boundary in program.boundaries for ref in boundary.affected_claim_refs}
        return [
            ValidationIssue(
                issue_id=f"issue:unsupported-unbounded:{claim.claim_id}",
                severity="critical",
                issue_class="unsupported_claim_without_boundary",
                message="Unsupported claims require an explicit uncertainty boundary before expression.",
                refs=(claim.claim_id,),
            )
            for claim in program.claims
            if claim.status is ClaimStatus.UNSUPPORTED and claim.claim_id not in bounded
        ]

    def _temporal_consistency(self, program: SemanticProgram) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for claim in program.claims:
            observed = str(claim.metadata.get("observed_at") or "")
            expires = str(claim.metadata.get("expires_at") or "")
            observed_dt = _parse_iso_timestamp(observed) if observed else None
            expires_dt = _parse_iso_timestamp(expires) if expires else None
            if observed and observed_dt is None:
                issues.append(ValidationIssue(
                    issue_id=f"issue:malformed-observed-at:{claim.claim_id}",
                    severity="critical",
                    issue_class="malformed_timestamp",
                    message="Claim observed_at metadata is not a valid ISO-8601 timestamp.",
                    refs=(claim.claim_id, observed),
                ))
            if expires and expires_dt is None:
                issues.append(ValidationIssue(
                    issue_id=f"issue:malformed-expires-at:{claim.claim_id}",
                    severity="critical",
                    issue_class="malformed_timestamp",
                    message="Claim expires_at metadata is not a valid ISO-8601 timestamp.",
                    refs=(claim.claim_id, expires),
                ))
            if observed_dt is not None and expires_dt is not None and expires_dt < observed_dt:
                issues.append(ValidationIssue(
                    issue_id=f"issue:temporal:{claim.claim_id}",
                    severity="critical",
                    issue_class="temporal_inconsistency",
                    message="Claim expiry precedes observation time.",
                    refs=(claim.claim_id,),
                ))
            if claim.status is ClaimStatus.SUPPORTED and claim.metadata.get("fresh") is False:
                issues.append(ValidationIssue(
                    issue_id=f"issue:stale-marked-supported:{claim.claim_id}",
                    severity="critical",
                    issue_class="stale_claim_marked_supported",
                    message="Claim is marked supported while metadata declares it stale.",
                    refs=(claim.claim_id,),
                ))
        return issues

    def _causal_structure(self, program: SemanticProgram) -> list[ValidationIssue]:
        causal = [edge for edge in program.edges if edge.relation == "causes"]
        if not causal:
            return []
        issues: list[ValidationIssue] = []
        cycle = GraphReasoner().cycle(causal)
        if cycle:
            issues.append(ValidationIssue(
                issue_id="issue:causal-cycle:" + sha256_digest(cycle).removeprefix("sha256:")[:16],
                severity="critical",
                issue_class="circular_causal_chain",
                message="Causal edges form a cycle; ordinary causal narration is refused.",
                refs=cycle,
            ))
        claim_map = program.claim_map
        for edge in causal:
            if edge.source_claim not in claim_map or edge.target_claim not in claim_map:
                issues.append(ValidationIssue(
                    issue_id=f"issue:causal-edge-ref:{edge.edge_id}",
                    severity="critical",
                    issue_class="causal_edge_unknown_claim",
                    message="Causal edge references an unknown claim.",
                    refs=(edge.edge_id,),
                ))
                continue
            source = claim_map[edge.source_claim]
            target = claim_map[edge.target_claim]
            if edge.status is not ClaimStatus.SUPPORTED or source.status is not ClaimStatus.SUPPORTED or target.status is not ClaimStatus.SUPPORTED:
                issues.append(ValidationIssue(
                    issue_id=f"issue:causal-authority:{edge.edge_id}",
                    severity="critical",
                    issue_class="causal_edge_lacks_current_authority",
                    message="Current causal assertions require supported source claim, target claim, and relationship status.",
                    refs=(edge.edge_id, source.claim_id, target.claim_id),
                ))
        if program.intent.intent.startswith("explain"):
            subject_claims = {claim.claim_id for claim in program.claims if claim.subject == program.intent.subject}
            incoming = {edge.target_claim for edge in causal}
            outgoing = {edge.source_claim for edge in causal}
            conclusions = subject_claims.intersection(incoming)
            if not conclusions:
                issues.append(ValidationIssue(
                    issue_id="issue:causal-direction:" + program.intent.subject,
                    severity="critical",
                    issue_class="causal_direction_or_conclusion_missing",
                    message="Explanation intent requires a causal path ending at a claim about the requested subject.",
                    refs=tuple(edge.edge_id for edge in causal),
                ))
            elif all(claim_id in outgoing for claim_id in conclusions):
                issues.append(ValidationIssue(
                    issue_id="issue:causal-direction-reversed:" + program.intent.subject,
                    severity="critical",
                    issue_class="causal_direction_reversed",
                    message="The intended conclusion is used as a cause; causal direction is not trustworthy.",
                    refs=tuple(sorted(conclusions)),
                ))
        return issues

    def _code_symbol_authority(self, program: SemanticProgram) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if program.intent.intent != "draft_code_transform":
            return issues
        objective_claim = _first_claim(program, "code_transform_objective")
        target_claim = _first_claim(program, "target_symbol")
        if objective_claim is not None and target_claim is not None:
            capability = SourceTransformationCapabilityRegistry().lookup(str(objective_claim.value), str(target_claim.value))
            if not capability["allowed"]:
                issues.append(ValidationIssue(
                    issue_id=f"issue:unknown-transform-capability:{objective_claim.claim_id}",
                    severity="critical",
                    issue_class="unknown_code_transformation_capability",
                    message=str(capability["reason"]),
                    refs=(objective_claim.claim_id, str(objective_claim.value), target_claim.claim_id, str(target_claim.value)),
                ))
            else:
                contract = verify_python_symbol_contract(str(target_claim.value), capability)
                if not contract["passed"]:
                    issues.append(ValidationIssue(
                        issue_id=f"issue:target-contract:{target_claim.claim_id}",
                        severity="critical",
                        issue_class="target_symbol_contract_mismatch",
                        message="Resolved source symbol does not satisfy registered capability contract.",
                        refs=(target_claim.claim_id, *tuple(contract["failure_classes"])),
                    ))
        preserve_claim = _first_claim(program, "preserve_public_api")
        if preserve_claim is not None and preserve_claim.status is ClaimStatus.SUPPORTED and preserve_claim.value is not True:
            issues.append(ValidationIssue(
                issue_id=f"issue:public-api-not-preserved:{preserve_claim.claim_id}",
                severity="critical",
                issue_class="public_api_preservation_not_authorized",
                message="SourcePlan authority requires preserve_public_api=true.",
                refs=(preserve_claim.claim_id, canonical_json(preserve_claim.value)),
            ))
        for claim in program.claims:
            if claim.predicate != "target_symbol" or claim.status is not ClaimStatus.SUPPORTED:
                continue
            resolved = resolve_python_symbol(str(claim.value))
            if not resolved["resolved"]:
                issues.append(ValidationIssue(
                    issue_id=f"issue:unresolved-symbol:{claim.claim_id}",
                    severity="critical",
                    issue_class="target_symbol_not_resolved",
                    message=str(resolved["reason"]),
                    refs=(claim.claim_id, str(claim.value)),
                ))
        return issues


class GraphReasoner:
    def ordered_edges(self, program: SemanticProgram) -> tuple[SemanticEdge, ...]:
        edges = tuple(edge for edge in program.edges if edge.relation in {"causes", "constrained_by", "verified_by"})
        if not edges:
            return ()
        if program.intent.intent.startswith("explain"):
            return self.relevant_edges(program)
        return self._ordered_subset(edges)

    def relevant_edges(self, program: SemanticProgram) -> tuple[SemanticEdge, ...]:
        edges = tuple(edge for edge in program.edges if edge.relation == "causes")
        if not program.intent.intent.startswith("explain") or not edges:
            return self._ordered_subset(edges)
        claim_map = program.claim_map
        candidate_conclusions = {
            edge.target_claim
            for edge in edges
            if (claim_map.get(edge.target_claim) is not None and claim_map[edge.target_claim].subject == program.intent.subject)
        }
        scored = sorted(
            (
                (_claim_question_relevance(program, claim_map[claim_id]), claim_id)
                for claim_id in candidate_conclusions
            ),
            reverse=True,
        )
        conclusions = {claim_id for score, claim_id in scored if score > 0}
        if not conclusions and scored:
            conclusions = {scored[0][1]}
        if not conclusions:
            return ()
        by_target: dict[str, list[SemanticEdge]] = {}
        for edge in edges:
            by_target.setdefault(edge.target_claim, []).append(edge)
        relevant_ids: set[str] = set()

        def walk_upstream(claim_id: str) -> None:
            for edge in by_target.get(claim_id, ()):
                if edge.edge_id in relevant_ids:
                    continue
                relevant_ids.add(edge.edge_id)
                walk_upstream(edge.source_claim)

        for conclusion in conclusions:
            walk_upstream(conclusion)
        return self._ordered_subset(tuple(edge for edge in edges if edge.edge_id in relevant_ids))

    def _ordered_subset(self, edges: Sequence[SemanticEdge]) -> tuple[SemanticEdge, ...]:
        edges = tuple(edges)
        if not edges:
            return ()
        causal = tuple(edge for edge in edges if edge.relation == "causes")
        if causal and self.cycle(causal):
            return edges
        by_source: dict[str, list[SemanticEdge]] = {}
        incoming = {edge.target_claim for edge in edges}
        for edge in edges:
            by_source.setdefault(edge.source_claim, []).append(edge)
        roots = sorted({edge.source_claim for edge in edges}.difference(incoming))
        if not roots:
            return edges
        ordered: list[SemanticEdge] = []
        seen: set[str] = set()

        def walk(claim_id: str) -> None:
            for edge in sorted(by_source.get(claim_id, ()), key=lambda item: item.edge_id):
                if edge.edge_id in seen:
                    continue
                seen.add(edge.edge_id)
                ordered.append(edge)
                walk(edge.target_claim)

        for root in roots:
            walk(root)
        ordered.extend(edge for edge in edges if edge.edge_id not in seen)
        return tuple(ordered)

    def cycle(self, edges: Sequence[SemanticEdge]) -> tuple[str, ...]:
        graph: dict[str, list[SemanticEdge]] = {}
        for edge in edges:
            graph.setdefault(edge.source_claim, []).append(edge)
        visiting: set[str] = set()
        visited: set[str] = set()
        path: list[SemanticEdge] = []

        def dfs(node: str) -> tuple[str, ...]:
            visiting.add(node)
            for edge in graph.get(node, ()):
                if edge.target_claim in visiting:
                    path.append(edge)
                    return tuple(item.edge_id for item in path)
                if edge.target_claim not in visited:
                    path.append(edge)
                    found = dfs(edge.target_claim)
                    if found:
                        return found
                    path.pop()
            visiting.remove(node)
            visited.add(node)
            return ()

        for node in sorted(graph):
            if node not in visited:
                found = dfs(node)
                if found:
                    return found
        return ()


class ResidualRouter:
    def decide(self, program: SemanticProgram, validation: SemanticValidationReport | None = None) -> dict[str, Any]:
        unsupported = [claim.claim_id for claim in program.claims if claim.status is ClaimStatus.UNSUPPORTED]
        stale = [claim.claim_id for claim in program.claims if claim.status is ClaimStatus.STALE]
        residual = [claim.claim_id for claim in program.claims if claim.status is ClaimStatus.RESIDUAL_REQUIRED]
        critical = tuple(validation.critical_issues) if validation is not None else ()
        if critical:
            action = "refuse"
            reason = "semantic_validation_failed"
        elif unsupported and not program.boundaries:
            action = "refuse"
            reason = "unsupported_claim_without_boundary"
        elif residual:
            action = "bounded_residual"
            reason = "small_unresolved_field_packet_only"
        elif stale:
            action = "answer_with_temporal_boundary"
            reason = "stale_claims_cannot_be_current"
        else:
            action = "deterministic"
            reason = "all_required_claims_supported"
        payload = {
            "beast_object_type": "semantic_expression_residual_decision",
            "program_digest": program.semantic_digest,
            "action": action,
            "reason": reason,
            "unsupported_claims": tuple(unsupported),
            "stale_claims": tuple(stale),
            "residual_claims": tuple(residual),
            "semantic_validation_digest": validation.digest if validation is not None else "",
            "semantic_validation_accepted": validation.accepted if validation is not None else False,
            "critical_issue_classes": tuple(issue.issue_class for issue in critical),
            "provider_calls_allowed": action == "bounded_residual",
            "allowed_residual_fields": tuple(field for boundary in program.boundaries for field in boundary.unsupported_fields),
            "forbidden_residual_fields": ("final_answer", "new_fact", "new_claim", "action_authority", "visual_scene"),
        }
        return {**payload, "decision_digest": sha256_digest(payload)}


class RefusalCompiler:
    def plan(self, program: SemanticProgram, validation: SemanticValidationReport, *, style: ExpressionStyle) -> DiscoursePlan:
        return DiscoursePlan(
            plan_id=f"refusal-discourse:{program.program_id}:{style.value}",
            semantic_digest=program.semantic_digest,
            style=style,
            steps=(DiscourseStep(
                step_id="step:refusal",
                act="semantic_refusal",
                claim_refs=tuple(ref for issue in validation.critical_issues for ref in issue.refs if ref.startswith("claim:")),
            ),),
            planner_id="beast.refusal-discourse-planner.v1",
        )

    def text_artifact(
        self,
        program: SemanticProgram,
        plan: DiscoursePlan,
        validation: SemanticValidationReport,
        residual: Mapping[str, Any],
    ) -> SemanticArtifact:
        payload = {
            "beast_object_type": "semantic_expression_refusal_artifact",
            "semantic_digest": program.semantic_digest,
            "discourse_plan_digest": plan.digest,
            "residual_decision_digest": residual.get("decision_digest", ""),
            "ordinary_answer_available": False,
            "reason": residual.get("reason", "semantic_refusal"),
            "critical_issue_classes": tuple(issue.issue_class for issue in validation.critical_issues),
            "text": "BEAST refuses ordinary expression because semantic validation failed: "
            + ", ".join(issue.issue_class for issue in validation.critical_issues)
            + ".",
        }
        return SemanticArtifact(
            media_type="application/vnd.beast.semantic-refusal+json",
            content=(json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            sequence=4,
            status="refused",
            failure_class="semantic_validation_failed",
        )

    def scene_plan(self, program: SemanticProgram) -> SemanticScenePlan:
        return SemanticScenePlan(
            plan_id=f"refusal-scene:{program.program_id}",
            semantic_digest=program.semantic_digest,
            nodes=(),
            edges=(),
            uncertainty_markers=(),
            compiler_id="beast.refusal-scene-compiler.v1",
        )

    def visual_artifact(
        self,
        program: SemanticProgram,
        validation: SemanticValidationReport,
        residual: Mapping[str, Any],
    ) -> SemanticArtifact:
        payload = {
            "beast_object_type": "semantic_expression_visual_refusal_artifact",
            "semantic_digest": program.semantic_digest,
            "residual_decision_digest": residual.get("decision_digest", ""),
            "ordinary_visual_available": False,
            "critical_issue_classes": tuple(issue.issue_class for issue in validation.critical_issues),
        }
        return SemanticArtifact(
            media_type="application/vnd.beast.semantic-refusal+json",
            content=(json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            sequence=5,
            status="refused",
            failure_class="semantic_validation_failed",
        )

    def sourceplan(self, program: SemanticProgram, validation: SemanticValidationReport) -> SourcePlanDraft:
        return SourcePlanDraft(
            plan_id=f"sourceplan-refusal:{program.program_id}",
            semantic_digest=program.semantic_digest,
            objective=program.intent.question,
            operations=(),
            preconditions=(),
            postconditions=(),
            status="refused_by_semantic_validator",
            compiler_id="beast.refusal-sourceplan-compiler.v1",
        )


class ResidualPendingCompiler:
    def plan(self, program: SemanticProgram, *, style: ExpressionStyle) -> DiscoursePlan:
        residual_claims = tuple(claim.claim_id for claim in program.claims if claim.status is ClaimStatus.RESIDUAL_REQUIRED)
        return DiscoursePlan(
            plan_id=f"residual-pending-discourse:{program.program_id}:{style.value}",
            semantic_digest=program.semantic_digest,
            style=style,
            steps=(DiscourseStep(
                step_id="step:residual-pending",
                act="residual_pending",
                claim_refs=residual_claims,
            ),),
            planner_id="beast.residual-pending-discourse-planner.v1",
        )

    def text_artifact(
        self,
        program: SemanticProgram,
        plan: DiscoursePlan,
        residual: Mapping[str, Any],
    ) -> SemanticArtifact:
        payload = {
            "beast_object_type": "semantic_expression_residual_pending_artifact",
            "semantic_digest": program.semantic_digest,
            "discourse_plan_digest": plan.digest,
            "residual_decision_digest": residual.get("decision_digest", ""),
            "ordinary_answer_available": False,
            "provider_calls_allowed": residual.get("provider_calls_allowed", False),
            "residual_claims": tuple(residual.get("residual_claims", ())),
            "allowed_residual_fields": tuple(residual.get("allowed_residual_fields", ())),
            "text": "BEAST cannot assert the residual-required proposition as fact until a residual result is returned, verified, and promoted.",
        }
        return SemanticArtifact(
            media_type="application/vnd.beast.semantic-residual-pending+json",
            content=(json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            sequence=4,
            status="residual_pending",
            failure_class="residual_result_required",
        )

    def scene_plan(self, program: SemanticProgram) -> SemanticScenePlan:
        return SemanticScenePlan(
            plan_id=f"residual-pending-scene:{program.program_id}",
            semantic_digest=program.semantic_digest,
            nodes=(),
            edges=(),
            uncertainty_markers=(),
            compiler_id="beast.residual-pending-scene-compiler.v1",
        )

    def visual_artifact(self, program: SemanticProgram, residual: Mapping[str, Any]) -> SemanticArtifact:
        payload = {
            "beast_object_type": "semantic_expression_visual_residual_pending_artifact",
            "semantic_digest": program.semantic_digest,
            "residual_decision_digest": residual.get("decision_digest", ""),
            "ordinary_visual_available": False,
            "provider_calls_allowed": residual.get("provider_calls_allowed", False),
            "residual_claims": tuple(residual.get("residual_claims", ())),
        }
        return SemanticArtifact(
            media_type="application/vnd.beast.semantic-residual-pending+json",
            content=(json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            sequence=5,
            status="residual_pending",
            failure_class="residual_result_required",
        )

    def sourceplan(self, program: SemanticProgram) -> SourcePlanDraft:
        return SourcePlanDraft(
            plan_id=f"sourceplan-residual-pending:{program.program_id}",
            semantic_digest=program.semantic_digest,
            objective=program.intent.question,
            operations=(),
            preconditions=("residual_result_verified_and_promoted",),
            postconditions=(),
            status="blocked_pending_residual_result",
            compiler_id="beast.residual-pending-sourceplan-compiler.v1",
        )


class DiscoursePlanner:
    def plan(self, program: SemanticProgram, *, style: ExpressionStyle) -> DiscoursePlan:
        conclusion = _primary_claim(program)
        ordered_edges = _causal_chain(program)
        steps: list[DiscourseStep] = []
        if program.intent.intent == "draft_code_transform":
            steps.append(DiscourseStep("step:sourceplan-premises", "list_supported_claims", _relevant_claim_refs(program)))
            if ordered_edges:
                steps.append(DiscourseStep("step:sourceplan-chain", "causal_chain", tuple(_edge_claim_refs(ordered_edges))))
            return DiscoursePlan(
                plan_id=f"discourse:{program.program_id}:{style.value}",
                semantic_digest=program.semantic_digest,
                style=style,
                steps=tuple(steps),
                planner_id="beast.semantic-discourse-planner.v2",
            )
        if style is ExpressionStyle.EXECUTIVE:
            steps.append(DiscourseStep("step:outcome", "state_outcome", (conclusion.claim_id,)))
            if ordered_edges:
                steps.append(DiscourseStep("step:cause", "compress_causal_chain", tuple(_edge_claim_refs(ordered_edges))))
        elif style is ExpressionStyle.TERSE:
            steps.append(DiscourseStep("step:answer", "single_sentence_answer", (conclusion.claim_id,)))
        elif style is ExpressionStyle.FORENSIC:
            steps.append(DiscourseStep("step:evidence", "list_supported_claims", _relevant_claim_refs(program)))
            if ordered_edges:
                steps.append(DiscourseStep("step:chain", "causal_chain", tuple(_edge_claim_refs(ordered_edges))))
        elif style is ExpressionStyle.TUTORIAL:
            steps.append(DiscourseStep("step:setup", "define_subject", (conclusion.claim_id,)))
            if ordered_edges:
                steps.append(DiscourseStep("step:chain", "causal_chain_with_definitions", tuple(_edge_claim_refs(ordered_edges))))
        elif style is ExpressionStyle.CONVERSATIONAL:
            steps.append(DiscourseStep("step:plain", "plain_answer", (conclusion.claim_id,)))
            if ordered_edges:
                steps.append(DiscourseStep("step:because", "because_chain", tuple(_edge_claim_refs(ordered_edges))))
        else:
            steps.append(DiscourseStep("step:claim", "technical_claim", (conclusion.claim_id,)))
            if ordered_edges:
                steps.append(DiscourseStep("step:chain", "causal_chain", tuple(_edge_claim_refs(ordered_edges))))
        if program.boundaries:
            steps.append(DiscourseStep(
                "step:boundary",
                "uncertainty_boundary",
                tuple(ref for boundary in program.boundaries for ref in boundary.affected_claim_refs),
                tuple(boundary.boundary_id for boundary in program.boundaries),
            ))
        return DiscoursePlan(
            plan_id=f"discourse:{program.program_id}:{style.value}",
            semantic_digest=program.semantic_digest,
            style=style,
            steps=tuple(steps),
        )


class Lexicalizer:
    def render(self, program: SemanticProgram, plan: DiscoursePlan) -> SemanticArtifact:
        text = " ".join(_realize_step(program, step, plan.style) for step in plan.steps if _realize_step(program, step, plan.style))
        payload = {
            "beast_object_type": "semantic_expression_text_artifact",
            "semantic_digest": program.semantic_digest,
            "discourse_plan_digest": plan.digest,
            "style": plan.style.value,
            "text": text,
            "claim_refs": tuple(sorted({ref for step in plan.steps for ref in step.claim_refs})),
            "boundary_refs": tuple(sorted({ref for step in plan.steps for ref in step.boundary_refs})),
        }
        return SemanticArtifact(
            media_type="application/vnd.beast.semantic-text+json",
            content=(json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            sequence=4,
        )


class SceneCompiler:
    def compile(self, program: SemanticProgram) -> SemanticScenePlan:
        relevant_claim_refs = set(_relevant_claim_refs(program))
        relevant_entity_refs = {
            claim.subject
            for claim in program.claims
            if claim.claim_id in relevant_claim_refs
        }
        relevant_entity_refs.update(
            claim.object
            for claim in program.claims
            if claim.claim_id in relevant_claim_refs and claim.object in program.entity_map
        )
        entities = [entity for entity in program.entities if entity.entity_id in relevant_entity_refs] or list(program.entities)
        spacing = max(120, 780 // max(1, len(entities)))
        nodes = tuple(
            SceneNode(
                node_id=f"node:{entity.entity_id}",
                entity_ref=entity.entity_id,
                x=60 + index * spacing,
                y=185,
                width=170,
                height=78,
                label=entity.label,
                status=_entity_status(program, entity.entity_id),
            )
            for index, entity in enumerate(entities)
        )
        entity_by_claim = {claim.claim_id: claim.subject for claim in program.claims}
        scene_edges: list[SceneEdge] = []
        scene_source_edges = _causal_chain(program) if program.intent.intent.startswith("explain") else program.edges
        for edge in scene_source_edges:
            source_entity = entity_by_claim.get(edge.source_claim, "")
            target_entity = entity_by_claim.get(edge.target_claim, "")
            if source_entity and target_entity:
                scene_edges.append(SceneEdge(
                    edge_id=f"scene-edge:{edge.edge_id}",
                    semantic_edge_ref=edge.edge_id,
                    from_entity=source_entity,
                    to_entity=target_entity,
                    label=edge.relation.replace("_", " "),
                    status=edge.status,
                ))
        markers = tuple(
            {
                "boundary_ref": boundary.boundary_id,
                "unsupported_fields": boundary.unsupported_fields,
                "reason": boundary.reason,
                "claim_refs": boundary.affected_claim_refs,
            }
            for boundary in program.boundaries
        )
        return SemanticScenePlan(
            plan_id=f"scene:{program.program_id}",
            semantic_digest=program.semantic_digest,
            nodes=nodes,
            edges=tuple(scene_edges),
            uncertainty_markers=markers,
        )


class SvgSceneRenderer:
    def render(self, program: SemanticProgram, plan: SemanticScenePlan) -> SemanticArtifact:
        node_by_entity = {node.entity_ref: node for node in plan.nodes}
        elements = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{plan.width}" height="{plan.height}" viewBox="0 0 {plan.width} {plan.height}">',
            '<rect width="100%" height="100%" fill="#081018"/>',
            '<text x="28" y="38" fill="#d8e8ef" font-family="monospace" font-size="20">BEAST semantic expression</text>',
            f'<text x="28" y="62" fill="#78f0c8" font-family="monospace" font-size="12">meaning {html.escape(program.semantic_digest)}</text>',
        ]
        for edge in plan.edges:
            source = node_by_entity.get(edge.from_entity)
            target = node_by_entity.get(edge.to_entity)
            if not source or not target:
                continue
            stroke = _status_color(edge.status)
            dash = ' stroke-dasharray="8 6"' if edge.status is not ClaimStatus.SUPPORTED else ""
            x1, y1 = source.x + source.width, source.y + source.height // 2
            x2, y2 = target.x, target.y + target.height // 2
            elements.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="3"{dash}/>')
            elements.append(f'<text x="{(x1+x2)//2 - 38}" y="{y1 - 12}" fill="#d8e8ef" font-family="monospace" font-size="12">{html.escape(edge.label)}</text>')
        for node in plan.nodes:
            fill = "#102635" if node.status is ClaimStatus.SUPPORTED else "#30251b"
            stroke = _status_color(node.status)
            elements.append(f'<rect x="{node.x}" y="{node.y}" width="{node.width}" height="{node.height}" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
            elements.append(f'<text x="{node.x + 14}" y="{node.y + 42}" fill="#f4fbff" font-family="monospace" font-size="15">{html.escape(node.label)}</text>')
        claim_labels = [
            _visual_claim_label(program, claim)
            for claim in program.claims
            if claim.claim_id in set(_relevant_claim_refs(program)) and claim.status is ClaimStatus.SUPPORTED
        ]
        for index, label in enumerate(label for label in claim_labels if label):
            elements.append(
                f'<text x="62" y="{310 + index * 18}" fill="#bde8ff" font-family="monospace" font-size="12">'
                f'{html.escape(label)}</text>'
            )
        if plan.uncertainty_markers:
            elements.append('<rect x="42" y="390" width="876" height="96" rx="12" fill="#261d12" stroke="#f0b45b"/>')
            elements.append('<text x="62" y="420" fill="#ffdca0" font-family="monospace" font-size="15">uncertainty boundary</text>')
            marker_text = "; ".join(
                ",".join(str(field) for field in marker.get("unsupported_fields", ()))
                for marker in plan.uncertainty_markers
            )
            elements.append(f'<text x="62" y="450" fill="#ffdca0" font-family="monospace" font-size="13">{html.escape(marker_text)}</text>')
        elements.append("</svg>")
        return SemanticArtifact(
            media_type="image/svg+xml",
            content=("\n".join(elements) + "\n").encode("utf-8"),
            sequence=5,
        )


class SourceTransformationCapabilityRegistry:
    """Small explicit bridge from request strings to typed code capabilities."""

    _CAPABILITIES: tuple[Mapping[str, Any], ...] = ({
        "transformation_id": "add_retry_damping",
        "operation_type": "typed_ast_transform",
        "policy_generation": "semantic-source-transform-policy-2026-08-04.3",
        "allowed_targets": ({
            "target_symbol": "app.kernel.registry.provider_registry.ProviderRegistry",
            "module_path": "app/kernel/registry/provider_registry.py",
            "object_path": "ProviderRegistry",
            "required_methods": ("records", "inventory", "_record", "_normalize_backend"),
            "required_import_names": ("Dict", "Any"),
        },),
        "typed_args": {
            "max_retries": 3,
            "base_delay_ms": 100,
            "jitter": "bounded",
        },
        "risk_class": "low_guarded_control_flow",
        "required_verifier": "provider_registry_retry_damping_tests",
    },)

    def lookup(self, transformation_id: str, target_symbol: str) -> dict[str, Any]:
        for capability in self._CAPABILITIES:
            if capability["transformation_id"] != transformation_id:
                continue
            target = next(
                (
                    dict(item)
                    for item in capability.get("allowed_targets", ())
                    if isinstance(item, Mapping) and item.get("target_symbol") == target_symbol
                ),
                None,
            )
            if target is None:
                return {
                    "allowed": False,
                    "reason": f"registered transformation {transformation_id} is not authorized for exact target {target_symbol}",
                    "transformation_id": transformation_id,
                }
            core = {key: value for key, value in capability.items() if key != "allowed_targets"}
            payload = {**dict(core), "allowed_target": target}
            return {**payload, "schema_digest": sha256_digest(payload), "allowed": True}
        return {
            "allowed": False,
            "reason": f"unknown source transformation capability: {transformation_id}",
            "transformation_id": transformation_id,
        }


class SourcePlanCompiler:
    def compile(self, program: SemanticProgram) -> SourcePlanDraft:
        objective_claim = _first_claim(program, "code_transform_objective")
        target_claim = _first_claim(program, "target_symbol")
        preserve_claim = _first_claim(program, "preserve_public_api")
        test_claim = _first_claim(program, "test_requirement")
        capability = (
            SourceTransformationCapabilityRegistry().lookup(str(objective_claim.value), str(target_claim.value))
            if objective_claim is not None and target_claim is not None
            else {"allowed": False}
        )
        resolved_target = (
            resolve_python_symbol(str(target_claim.value))
            if target_claim is not None
            else {"resolved": False}
        )
        target_contract = (
            verify_python_symbol_contract(str(target_claim.value), capability)
            if target_claim is not None and capability.get("allowed") is True
            else {"passed": False, "contract_digest": ""}
        )
        allowed = (
            objective_claim is not None
            and target_claim is not None
            and capability["allowed"]
            and resolved_target["resolved"]
            and target_contract["passed"]
            and preserve_claim is not None
            and preserve_claim.status is ClaimStatus.SUPPORTED
            and preserve_claim.value is True
            and program.permissions.get("sourceplan_allowed") is True
        )
        operations: tuple[Mapping[str, Any], ...] = ()
        status = "not_applicable"
        if allowed:
            operations = ({
                "operation_id": "semantic_edit_001",
                "operation_type": "typed_ast_transform",
                "target_symbol": target_claim.value,
                "target_module_path": resolved_target.get("module_path"),
                "target_object_path": resolved_target.get("object_path"),
                "target_module_digest": resolved_target.get("module_digest"),
                "target_symbol_digest": resolved_target.get("symbol_digest"),
                "target_contract_digest": target_contract.get("contract_digest"),
                "transformation": capability["transformation_id"],
                "transformation_schema_digest": capability["schema_digest"],
                "policy_generation": capability["policy_generation"],
                "typed_args": capability["typed_args"],
                "risk_class": capability["risk_class"],
                "required_verifier": capability["required_verifier"],
                "public_api_preserved": True,
                "semantic_digest": program.semantic_digest,
            },)
            status = "draft_requires_approval"
        elif objective_claim is not None:
            status = "refused_missing_code_authority_or_precondition"
        preconditions = tuple(filter(None, (
            "target_symbol_resolved" if resolved_target.get("resolved") else "",
            "target_symbol_contract_satisfied" if target_contract.get("passed") else "",
            "transformation_capability_registered" if capability.get("allowed") is True else "",
            "public_api_preserved" if preserve_claim is not None and preserve_claim.status is ClaimStatus.SUPPORTED and preserve_claim.value is True else "",
            "sourceplan_allowed" if program.permissions.get("sourceplan_allowed") is True else "",
        )))
        postconditions = tuple(filter(None, (
            str(test_claim.value) if test_claim is not None else "",
            "unrelated_behavior_preserved" if allowed else "",
        )))
        return SourcePlanDraft(
            plan_id=f"sourceplan:{program.program_id}",
            semantic_digest=program.semantic_digest,
            objective=str(objective_claim.value if objective_claim is not None else program.intent.question),
            operations=operations,
            preconditions=preconditions,
            postconditions=postconditions,
            status=status,
        )


class ExpressionVerifier:
    def verify(
        self,
        *,
        program: SemanticProgram,
        validation_report: SemanticValidationReport | None = None,
        discourse_plan: DiscoursePlan,
        text_artifact: SemanticArtifact,
        scene_plan: SemanticScenePlan,
        visual_artifact: SemanticArtifact,
        sourceplan: SourcePlanDraft,
        residual_decision: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        failures: list[str] = []
        validation_report = validation_report or SemanticValidator().validate(program)
        refusal_mode = residual_decision.get("action") == "refuse"
        residual_pending_mode = residual_decision.get("action") == "bounded_residual"
        if validation_report.semantic_digest != program.semantic_digest:
            failures.append("validation_semantic_digest_mismatch")
        if validation_report.accepted and refusal_mode:
            failures.append("accepted_program_reported_refused")
        if not validation_report.accepted and not refusal_mode:
            failures.append("invalid_program_not_refused")
        if residual_decision.get("residual_claims") and not residual_pending_mode:
            failures.append("residual_claims_not_routed_to_residual_pending")
        if discourse_plan.semantic_digest != program.semantic_digest:
            failures.append("discourse_semantic_digest_mismatch")
        if scene_plan.semantic_digest != program.semantic_digest:
            failures.append("scene_semantic_digest_mismatch")
        if sourceplan.semantic_digest != program.semantic_digest:
            failures.append("sourceplan_semantic_digest_mismatch")
        if refusal_mode:
            compiler = RefusalCompiler()
            expected_text = compiler.text_artifact(program, discourse_plan, validation_report, residual_decision)
            expected_visual = compiler.visual_artifact(program, validation_report, residual_decision)
            expected_sourceplan = compiler.sourceplan(program, validation_report)
        elif residual_pending_mode:
            compiler = ResidualPendingCompiler()
            expected_text = compiler.text_artifact(program, discourse_plan, residual_decision)
            expected_visual = compiler.visual_artifact(program, residual_decision)
            expected_sourceplan = compiler.sourceplan(program)
        else:
            expected_text = Lexicalizer().render(program, discourse_plan)
            expected_visual = SvgSceneRenderer().render(program, scene_plan)
            expected_sourceplan = SourcePlanCompiler().compile(program)
        if expected_text.content != text_artifact.content:
            failures.append("text_artifact_drift")
        if expected_visual.content != visual_artifact.content:
            failures.append("visual_artifact_drift")
        if expected_sourceplan.digest != sourceplan.digest:
            failures.append("sourceplan_drift")
        text_payload = _json_bytes(text_artifact.content)
        if text_payload.get("semantic_digest") != program.semantic_digest:
            failures.append("text_payload_semantic_digest_mismatch")
        unsupported_fields = tuple(field for boundary in program.boundaries for field in boundary.unsupported_fields)
        text = str(text_payload.get("text") or "").lower()
        if not refusal_mode and not residual_pending_mode and unsupported_fields and "does not establish" not in text:
            failures.append("uncertainty_boundary_not_realized")
        if residual_decision.get("program_digest") != program.semantic_digest:
            failures.append("residual_decision_digest_mismatch")
        independent_text = IndependentTextEntailmentVerifier().verify(program, text_artifact, residual_decision)
        independent_visual = IndependentVisualEntailmentVerifier().verify(program, scene_plan, visual_artifact, residual_decision)
        independent_source = IndependentSourcePlanVerifier().verify(program, sourceplan, residual_decision)
        failures.extend(independent_text["failures"])
        failures.extend(independent_visual["failures"])
        failures.extend(independent_source["failures"])
        receipt_core = {
            "beast_object_type": "semantic_expression_joined_receipt",
            "version": "1.0",
            "semantic_digest": program.semantic_digest,
            "semantic_validation_digest": validation_report.digest,
            "semantic_validation_accepted": validation_report.accepted,
            "discourse_plan_digest": discourse_plan.digest,
            "text_artifact_digest": text_artifact.digest,
            "scene_plan_digest": scene_plan.digest,
            "visual_artifact_digest": visual_artifact.digest,
            "sourceplan_digest": sourceplan.digest,
            "residual_decision_digest": residual_decision.get("decision_digest", ""),
            "provider_calls_used": 0,
            "ordinary_answer_available": not failures and not refusal_mode and not residual_pending_mode and validation_report.accepted,
            "ordinary_visual_available": not failures and not refusal_mode and not residual_pending_mode and validation_report.accepted,
            "ordinary_sourceplan_available": not failures and not refusal_mode and not residual_pending_mode and validation_report.accepted and sourceplan.status == "draft_requires_approval",
            "refusal_enforced": refusal_mode and not validation_report.accepted,
            "residual_pending_enforced": residual_pending_mode and validation_report.accepted,
            "phase_trace": (
                "semantic_program_compiled",
                "semantic_program_validated",
                "residual_decision_made",
                "discourse_plan_compiled",
                "text_realized",
                "scene_compiled",
                "svg_rendered",
                "sourceplan_compiled",
                "joined_verified",
            ),
            "meaning_first": True,
            "text_from_semantics_not_visual": True,
            "visual_from_semantics_not_text": True,
            "sourceplan_from_semantics_not_text": True,
            "independent_text_entailment_valid": not independent_text["failures"],
            "independent_visual_entailment_valid": not independent_visual["failures"],
            "independent_sourceplan_valid": not independent_source["failures"],
            "joined_verification": not failures,
            "failure_classes": tuple(failures),
            "claim_boundary": (
                "Bounded semantic expression only. BEAST claims deterministic "
                "speech, scene, and SourcePlan realization from the supplied "
                "semantic program; it does not claim open-domain language, "
                "photorealistic rendering, or mutation authority."
            ),
        }
        receipt = {**receipt_core, "receipt_digest": sha256_digest(receipt_core)}
        verification = {
            "joined_verification": not failures,
            "failure_classes": tuple(failures),
            "semantic_validation_accepted": validation_report.accepted,
            "semantic_validation_issues": tuple(issue.issue_class for issue in validation_report.issues),
            "independent_text_entailment": independent_text,
            "independent_visual_entailment": independent_visual,
            "independent_sourceplan": independent_source,
            "verification_digest": sha256_digest({
                "semantic_digest": program.semantic_digest,
                "receipt_digest": receipt["receipt_digest"],
                "failures": tuple(failures),
            }),
        }
        return receipt, verification


class IndependentTextEntailmentVerifier:
    """A deliberately separate proposition check, not a lexicalizer replay."""

    def verify(
        self,
        program: SemanticProgram,
        artifact: SemanticArtifact,
        residual_decision: Mapping[str, Any],
    ) -> dict[str, Any]:
        failures: list[str] = []
        payload = _json_bytes(artifact.content)
        text = str(payload.get("text") or "").lower()
        refusal_mode = residual_decision.get("action") == "refuse"
        residual_pending_mode = residual_decision.get("action") == "bounded_residual"
        if refusal_mode:
            if artifact.media_type != "application/vnd.beast.semantic-refusal+json" or payload.get("ordinary_answer_available") is not False:
                failures.append("refusal_text_artifact_not_dedicated")
            if "refuses ordinary expression" not in text:
                failures.append("refusal_text_missing_refusal_language")
            return {"valid": not failures, "failures": tuple(failures)}
        if residual_pending_mode:
            if artifact.media_type != "application/vnd.beast.semantic-residual-pending+json" or payload.get("ordinary_answer_available") is not False:
                failures.append("residual_pending_text_artifact_not_dedicated")
            if "cannot assert" not in text or "verified, and promoted" not in text:
                failures.append("residual_pending_text_missing_capability_boundary")
            for claim in program.claims:
                if claim.status is ClaimStatus.RESIDUAL_REQUIRED and _claim_phrase(program.entity_map, claim).lower() in text:
                    failures.append(f"residual_claim_asserted_as_fact:{claim.claim_id}")
            return {"valid": not failures, "failures": tuple(failures)}
        if artifact.media_type != "application/vnd.beast.semantic-text+json":
            failures.append("ordinary_text_artifact_wrong_media_type")
        if payload.get("semantic_digest") != program.semantic_digest:
            failures.append("ordinary_text_missing_semantic_digest")
        primary = _primary_claim(program)
        if _entity_label(program, primary.subject).lower() not in text:
            failures.append("text_missing_primary_subject")
        relevant_claim_ids = set(_relevant_claim_refs(program))
        for claim in program.claims:
            if claim.claim_id not in relevant_claim_ids or claim.status is not ClaimStatus.SUPPORTED:
                continue
            value_text = _value_text(claim.value).lower()
            if claim.value not in (None, True, False, "") and value_text and value_text not in text:
                failures.append(f"text_missing_proposition_value:{claim.claim_id}")
            law = SemanticPredicateLawRegistry().law_for(claim.predicate)
            if claim.value is False and law is not None and law.false_text and law.false_text.lower() not in text:
                failures.append(f"text_missing_negative_predicate_realization:{claim.claim_id}")
        for edge in _causal_chain(program):
            if edge.relation != "causes":
                continue
            if edge.status is not ClaimStatus.SUPPORTED:
                failures.append(f"text_realized_non_supported_edge:{edge.edge_id}")
            source_phrase = _claim_phrase(program.entity_map, program.claim_map[edge.source_claim]).lower()
            target_phrase = _claim_phrase(program.entity_map, program.claim_map[edge.target_claim]).lower()
            source_index = text.find(source_phrase)
            target_index = text.find(target_phrase)
            if source_index < 0 or target_index < 0:
                failures.append(f"text_missing_causal_endpoint:{edge.edge_id}")
            elif source_index > target_index:
                failures.append(f"text_causal_direction_reversed:{edge.edge_id}")
        for boundary in program.boundaries:
            for field in boundary.unsupported_fields:
                if field.replace("_", " ") not in text or "does not establish" not in text:
                    failures.append(f"text_missing_uncertainty_boundary:{boundary.boundary_id}")
        forbidden = [
            claim for claim in program.claims
            if claim.status in {ClaimStatus.UNSUPPORTED, ClaimStatus.RESIDUAL_REQUIRED}
            and claim.claim_id not in {ref for boundary in program.boundaries for ref in boundary.affected_claim_refs}
        ]
        if forbidden:
            failures.append("text_realized_unspeakable_claim")
        relevant_edge_ids = {edge.edge_id for edge in _causal_chain(program)}
        for edge in program.edges:
            if edge.relation == "causes" and edge.edge_id not in relevant_edge_ids:
                phrase = _realize_edge(program, edge, ExpressionStyle.TECHNICAL).lower()
                if phrase in text:
                    failures.append(f"text_realized_irrelevant_causal_edge:{edge.edge_id}")
        return {"valid": not failures, "failures": tuple(failures)}


class IndependentVisualEntailmentVerifier:
    def verify(
        self,
        program: SemanticProgram,
        scene_plan: SemanticScenePlan,
        artifact: SemanticArtifact,
        residual_decision: Mapping[str, Any],
    ) -> dict[str, Any]:
        failures: list[str] = []
        refusal_mode = residual_decision.get("action") == "refuse"
        residual_pending_mode = residual_decision.get("action") == "bounded_residual"
        if refusal_mode:
            payload = _json_bytes(artifact.content)
            if artifact.media_type != "application/vnd.beast.semantic-refusal+json" or payload.get("ordinary_visual_available") is not False:
                failures.append("refusal_visual_artifact_not_dedicated")
            if scene_plan.nodes or scene_plan.edges:
                failures.append("refusal_scene_contains_ordinary_visual_claims")
            return {"valid": not failures, "failures": tuple(failures)}
        if residual_pending_mode:
            payload = _json_bytes(artifact.content)
            if artifact.media_type != "application/vnd.beast.semantic-residual-pending+json" or payload.get("ordinary_visual_available") is not False:
                failures.append("residual_pending_visual_artifact_not_dedicated")
            if scene_plan.nodes or scene_plan.edges:
                failures.append("residual_pending_scene_contains_ordinary_visual_claims")
            return {"valid": not failures, "failures": tuple(failures)}
        if artifact.media_type != "image/svg+xml":
            failures.append("ordinary_visual_wrong_media_type")
        if scene_plan.semantic_digest != program.semantic_digest:
            failures.append("scene_plan_semantic_digest_mismatch")
        for node in scene_plan.nodes:
            if node.x < 0 or node.y < 0 or node.width <= 0 or node.height <= 0:
                failures.append(f"visual_node_invalid_geometry:{node.node_id}")
            if node.x + node.width > scene_plan.width or node.y + node.height > scene_plan.height:
                failures.append(f"visual_node_overflow:{node.node_id}")
        node_entities = {node.entity_ref for node in scene_plan.nodes}
        relevant_claims = {
            claim_id
            for claim_id in _relevant_claim_refs(program)
        }
        for claim in program.claims:
            if claim.claim_id in relevant_claims and claim.status is ClaimStatus.SUPPORTED and claim.subject not in node_entities:
                failures.append(f"visual_missing_claim_subject:{claim.claim_id}")
        represented_edges = {edge.semantic_edge_ref for edge in scene_plan.edges}
        required_edges = _causal_chain(program) if program.intent.intent.startswith("explain") else tuple(
            edge for edge in program.edges if edge.relation in {"causes", "constrained_by", "verified_by"}
        )
        for edge in required_edges:
            if edge.relation in {"causes", "constrained_by", "verified_by"} and edge.edge_id not in represented_edges:
                failures.append(f"visual_missing_semantic_edge:{edge.edge_id}")
        marker_refs = {
            str(marker.get("boundary_ref"))
            for marker in scene_plan.uncertainty_markers
            if isinstance(marker, Mapping)
        }
        for boundary in program.boundaries:
            if boundary.boundary_id not in marker_refs:
                failures.append(f"visual_missing_uncertainty_marker:{boundary.boundary_id}")
        svg = artifact.content.decode("utf-8", errors="replace")
        if program.semantic_digest not in svg:
            failures.append("visual_missing_semantic_digest")
        required_entity_refs = {
            claim.subject
            for claim in program.claims
            if claim.claim_id in relevant_claims
        }
        for entity in program.entities:
            if entity.entity_id in required_entity_refs and entity.label not in svg:
                failures.append(f"visual_missing_entity_label:{entity.entity_id}")
        for claim in program.claims:
            if claim.claim_id in relevant_claims and claim.status is ClaimStatus.SUPPORTED:
                label = _visual_claim_label(program, claim)
                if label and label not in svg:
                    failures.append(f"visual_missing_proposition_label:{claim.claim_id}")
        return {"valid": not failures, "failures": tuple(failures)}


class IndependentSourcePlanVerifier:
    def verify(
        self,
        program: SemanticProgram,
        sourceplan: SourcePlanDraft,
        residual_decision: Mapping[str, Any],
    ) -> dict[str, Any]:
        failures: list[str] = []
        refusal_mode = residual_decision.get("action") == "refuse"
        residual_pending_mode = residual_decision.get("action") == "bounded_residual"
        if refusal_mode:
            if sourceplan.operations:
                failures.append("refused_program_has_sourceplan_operations")
            if sourceplan.status != "refused_by_semantic_validator":
                failures.append("refused_program_sourceplan_status_wrong")
            return {"valid": not failures, "failures": tuple(failures)}
        if residual_pending_mode:
            if sourceplan.operations:
                failures.append("residual_pending_program_has_sourceplan_operations")
            if sourceplan.status != "blocked_pending_residual_result":
                failures.append("residual_pending_sourceplan_status_wrong")
            return {"valid": not failures, "failures": tuple(failures)}
        objective = _first_claim(program, "code_transform_objective")
        target = _first_claim(program, "target_symbol")
        if objective is None:
            if sourceplan.status != "not_applicable":
                failures.append("non_code_program_sourceplan_not_applicable")
            return {"valid": not failures, "failures": tuple(failures)}
        if program.permissions.get("sourceplan_allowed") is not True:
            if sourceplan.operations:
                failures.append("sourceplan_operations_without_permission")
            return {"valid": not failures, "failures": tuple(failures)}
        if target is None:
            failures.append("code_program_missing_target_symbol_claim")
            return {"valid": not failures, "failures": tuple(failures)}
        preserve = _first_claim(program, "preserve_public_api")
        if preserve is None or preserve.value is not True:
            failures.append("sourceplan_public_api_preservation_not_true")
        resolved = resolve_python_symbol(str(target.value))
        if not resolved["resolved"]:
            failures.append("sourceplan_target_symbol_not_resolved")
        capability = SourceTransformationCapabilityRegistry().lookup(str(objective.value), str(target.value))
        if not capability["allowed"]:
            failures.append("sourceplan_transformation_capability_not_registered")
        contract = verify_python_symbol_contract(str(target.value), capability) if capability.get("allowed") else {"passed": False}
        if not contract["passed"]:
            failures.append("sourceplan_target_symbol_contract_mismatch")
        if not sourceplan.operations:
            failures.append("sourceplan_missing_operation")
        for operation in sourceplan.operations:
            if operation.get("target_symbol") != target.value:
                failures.append("sourceplan_operation_target_mismatch")
            if operation.get("target_module_path") != resolved.get("module_path"):
                failures.append("sourceplan_operation_target_module_path_mismatch")
            if operation.get("target_object_path") != resolved.get("object_path"):
                failures.append("sourceplan_operation_target_object_path_mismatch")
            if operation.get("target_module_digest") != resolved.get("module_digest"):
                failures.append("sourceplan_operation_target_module_digest_mismatch")
            if operation.get("target_symbol_digest") != resolved.get("symbol_digest"):
                failures.append("sourceplan_operation_target_symbol_digest_mismatch")
            if operation.get("target_contract_digest") != contract.get("contract_digest"):
                failures.append("sourceplan_operation_target_contract_digest_mismatch")
            if operation.get("transformation") != objective.value:
                failures.append("sourceplan_operation_transformation_mismatch")
            if operation.get("transformation_schema_digest") != capability.get("schema_digest"):
                failures.append("sourceplan_operation_schema_digest_mismatch")
            if operation.get("policy_generation") != capability.get("policy_generation"):
                failures.append("sourceplan_operation_policy_generation_mismatch")
            if operation.get("required_verifier") != capability.get("required_verifier"):
                failures.append("sourceplan_operation_required_verifier_mismatch")
            if operation.get("semantic_digest") != program.semantic_digest:
                failures.append("sourceplan_operation_semantic_digest_mismatch")
            if operation.get("operation_type") != "typed_ast_transform":
                failures.append("sourceplan_operation_not_typed_ast_transform")
        if "target_symbol_resolved" not in sourceplan.preconditions:
            failures.append("sourceplan_missing_symbol_resolution_precondition")
        if "transformation_capability_registered" not in sourceplan.preconditions:
            failures.append("sourceplan_missing_capability_registry_precondition")
        if "target_symbol_contract_satisfied" not in sourceplan.preconditions:
            failures.append("sourceplan_missing_symbol_contract_precondition")
        return {"valid": not failures, "failures": tuple(failures)}


class SourceTransformationRuntime:
    """Execute semantic SourcePlans into proof-linked patch previews.

    This runtime is intentionally preview-only.  It never mutates the live
    repository.  It resolves the target symbol, creates a disposable evidence
    worktree containing the modified source file, compiles that file, runs
    structural verifier checks, and writes a diff/receipt pair.
    """

    def __init__(self, repo_root: Path | str | None = None):
        self.repo_root = Path(repo_root or Path(__file__).resolve().parents[3]).resolve()

    def execute_preview(
        self,
        sourceplan: SourcePlanDraft,
        *,
        evidence_root: Path | str | None = None,
        run_id: str = "semantic-source-transform-preview",
    ) -> dict[str, Any]:
        evidence_dir = Path(evidence_root or (self.repo_root / "evidence" / "semantic-source-transform" / run_id)).resolve()
        evidence_dir.mkdir(parents=True, exist_ok=True)
        if sourceplan.status != "draft_requires_approval" or not sourceplan.operations:
            return self._negative_receipt(
                sourceplan,
                evidence_dir,
                run_id=run_id,
                reason="sourceplan_not_executable_preview",
                failures=("sourceplan_not_draft_requires_approval",),
            )

        operation = dict(sourceplan.operations[0])
        target_symbol = str(operation.get("target_symbol") or "")
        transformation = str(operation.get("transformation") or "")
        capability = SourceTransformationCapabilityRegistry().lookup(transformation, target_symbol)
        resolved = resolve_python_symbol(target_symbol, repo_root=self.repo_root)
        preflight_failures: list[str] = []
        if operation.get("operation_type") != "typed_ast_transform":
            preflight_failures.append("operation_not_typed_ast_transform")
        if not capability["allowed"]:
            preflight_failures.append("transformation_capability_not_registered")
        if not resolved["resolved"]:
            preflight_failures.append("target_symbol_not_resolved")
        if operation.get("target_module_path") != resolved.get("module_path"):
            preflight_failures.append("target_module_path_mismatch")
        if operation.get("target_object_path") != resolved.get("object_path"):
            preflight_failures.append("target_object_path_mismatch")
        if operation.get("target_module_digest") != resolved.get("module_digest"):
            preflight_failures.append("target_module_digest_mismatch")
        if operation.get("target_symbol_digest") != resolved.get("symbol_digest"):
            preflight_failures.append("target_symbol_digest_mismatch")
        contract = verify_python_symbol_contract(target_symbol, capability, repo_root=self.repo_root) if capability.get("allowed") else {"passed": False}
        if not contract["passed"]:
            preflight_failures.append("target_symbol_contract_mismatch")
        if operation.get("target_contract_digest") != contract.get("contract_digest"):
            preflight_failures.append("target_contract_digest_mismatch")
        if operation.get("transformation_schema_digest") != capability.get("schema_digest"):
            preflight_failures.append("transformation_schema_digest_mismatch")
        if operation.get("policy_generation") != capability.get("policy_generation"):
            preflight_failures.append("policy_generation_mismatch")
        if preflight_failures:
            return self._negative_receipt(
                sourceplan,
                evidence_dir,
                run_id=run_id,
                reason="preflight_failed",
                failures=tuple(preflight_failures),
            )

        rel_path = Path(str(resolved["module_path"]))
        source_path = (self.repo_root / rel_path).resolve()
        if not _is_relative_to(source_path, self.repo_root) or not source_path.is_file():
            return self._negative_receipt(
                sourceplan,
                evidence_dir,
                run_id=run_id,
                reason="target_path_outside_repo_or_missing",
                failures=("target_path_invalid",),
            )

        original_text = source_path.read_text(encoding="utf-8")
        original_digest = sha256_bytes(original_text.encode("utf-8"))
        try:
            modified_text, transform_receipt = self._apply_registered_transform(original_text, operation, capability, target_symbol)
        except ValueError as exc:
            return self._negative_receipt(
                sourceplan,
                evidence_dir,
                run_id=run_id,
                reason=str(exc),
                failures=("typed_transform_failed",),
            )

        modified_digest = sha256_bytes(modified_text.encode("utf-8"))
        diff_text = "".join(difflib.unified_diff(
            original_text.splitlines(keepends=True),
            modified_text.splitlines(keepends=True),
            fromfile=str(rel_path),
            tofile=str(rel_path) + " (semantic-preview)",
        ))
        worktree_file = evidence_dir / "disposable_worktree" / rel_path
        worktree_file.parent.mkdir(parents=True, exist_ok=True)
        worktree_file.write_text(modified_text, encoding="utf-8")
        diff_path = evidence_dir / "preview.diff"
        diff_path.write_text(diff_text, encoding="utf-8")

        compile_ok = True
        compile_error = ""
        try:
            py_compile.compile(str(worktree_file), doraise=True)
        except py_compile.PyCompileError as exc:
            compile_ok = False
            compile_error = str(exc)

        import_result = _import_python_file(worktree_file)
        verifier = self._verify_registered_transform(modified_text, operation, capability, target_symbol)
        live_digest_after = sha256_bytes(source_path.read_text(encoding="utf-8").encode("utf-8"))
        failures = tuple(filter(None, (
            "" if compile_ok else "py_compile_failed",
            "" if import_result["ok"] else "module_import_failed",
            "" if verifier["passed"] else "structural_verifier_failed",
            "" if live_digest_after == original_digest else "live_source_mutated",
            "" if diff_text else "empty_diff",
        )))
        receipt_core = {
            "beast_object_type": "semantic_source_transformation_preview_receipt",
            "version": "1.0",
            "run_id": run_id,
            "sourceplan_digest": sourceplan.digest,
            "semantic_digest": sourceplan.semantic_digest,
            "operation": operation,
            "capability": capability,
            "target_symbol_resolution": resolved,
            "target_path": str(rel_path),
            "original_digest": original_digest,
            "modified_digest": modified_digest,
            "live_digest_after": live_digest_after,
            "diff_digest": sha256_bytes(diff_text.encode("utf-8")),
            "diff_path": str(diff_path),
            "disposable_worktree_file": str(worktree_file),
            "compile_ok": compile_ok,
            "compile_error": compile_error,
            "module_import": import_result,
            "structural_verifier": verifier,
            "target_symbol_contract": contract,
            "transform_receipt": transform_receipt,
            "rollback_available": True,
            "live_source_mutated": live_digest_after != original_digest,
            "approval_required_before_apply": True,
            "preview_only": True,
            "provider_calls_used": 0,
            "status": "verified_preview" if not failures else "failed_preview",
            "failure_classes": failures,
        }
        receipt = {**receipt_core, "receipt_digest": sha256_digest(receipt_core)}
        (evidence_dir / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return receipt

    def _apply_registered_transform(
        self,
        original_text: str,
        operation: Mapping[str, Any],
        capability: Mapping[str, Any],
        target_symbol: str,
    ) -> tuple[str, dict[str, Any]]:
        if operation.get("transformation") != "add_retry_damping":
            raise ValueError("unsupported_registered_transform")
        tree = ast.parse(original_text)
        class_name = target_symbol.rsplit(".", 1)[-1]
        class_node = next((node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name), None)
        if class_node is None:
            raise ValueError("target_class_missing_from_ast")
        existing_names = {
            getattr(node, "name", "")
            for node in class_node.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        }
        existing_names.update(
            target.id
            for node in class_node.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        )
        existing_names.update(
            node.target.id
            for node in class_node.body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        )
        if {"RETRY_DAMPING_POLICY", "retry_damping_policy"}.issubset(existing_names):
            raise ValueError("retry_damping_already_present")
        insert_after = class_node.lineno
        if (
            class_node.body
            and isinstance(class_node.body[0], ast.Expr)
            and isinstance(getattr(class_node.body[0], "value", None), ast.Constant)
            and isinstance(class_node.body[0].value.value, str)
        ):
            insert_after = int(getattr(class_node.body[0], "end_lineno", class_node.body[0].lineno))
        typed_args = dict(capability.get("typed_args") or {})
        insertion = [
            "",
            "    RETRY_DAMPING_POLICY: Dict[str, Any] = {",
            f"        \"max_retries\": {int(typed_args.get('max_retries', 3))},",
            f"        \"base_delay_ms\": {int(typed_args.get('base_delay_ms', 100))},",
            f"        \"jitter\": \"{str(typed_args.get('jitter', 'bounded'))}\",",
            "    }",
            "",
            "    def retry_damping_policy(self) -> Dict[str, Any]:",
            "        \"\"\"Return bounded retry damping policy for provider resolution callers.\"\"\"",
            "        return dict(self.RETRY_DAMPING_POLICY)",
        ]
        lines = original_text.splitlines()
        modified_lines = lines[:insert_after] + insertion + lines[insert_after:]
        modified_text = "\n".join(modified_lines) + ("\n" if original_text.endswith("\n") else "")
        ast.parse(modified_text)
        return modified_text, {
            "insert_after_line": insert_after,
            "target_class": class_name,
            "inserted_symbols": ("RETRY_DAMPING_POLICY", "retry_damping_policy"),
            "typed_args": typed_args,
        }

    def _verify_registered_transform(
        self,
        modified_text: str,
        operation: Mapping[str, Any],
        capability: Mapping[str, Any],
        target_symbol: str,
    ) -> dict[str, Any]:
        failures: list[str] = []
        tree = ast.parse(modified_text)
        class_name = target_symbol.rsplit(".", 1)[-1]
        class_node = next((node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name), None)
        if class_node is None:
            failures.append("target_class_missing")
            return {"passed": False, "failure_classes": tuple(failures)}
        class_body_names = {
            getattr(node, "name", "")
            for node in class_node.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        if "retry_damping_policy" not in class_body_names:
            failures.append("retry_damping_policy_method_missing")
        policy_node = next(
            (
                node
                for node in class_node.body
                if isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == "RETRY_DAMPING_POLICY"
            ),
            None,
        )
        if policy_node is None:
            failures.append("retry_damping_policy_constant_missing")
        typed_args = dict(capability.get("typed_args") or {})
        if int(typed_args.get("max_retries", 0)) <= 0:
            failures.append("invalid_max_retries")
        if int(typed_args.get("base_delay_ms", 0)) <= 0:
            failures.append("invalid_base_delay_ms")
        suspicious = ("secret", "token", "password", "exfiltrate")
        if any(term in str(operation.get("transformation", "")).lower() for term in suspicious):
            failures.append("suspicious_transformation_term")
        return {
            "passed": not failures,
            "failure_classes": tuple(failures),
            "checked": (
                "target_class_exists",
                "retry_damping_policy_method_exists",
                "retry_damping_policy_constant_exists",
                "typed_args_positive",
                "no_suspicious_transform_terms",
            ),
        }

    def _negative_receipt(
        self,
        sourceplan: SourcePlanDraft,
        evidence_dir: Path,
        *,
        run_id: str,
        reason: str,
        failures: tuple[str, ...],
    ) -> dict[str, Any]:
        receipt_core = {
            "beast_object_type": "semantic_source_transformation_negative_receipt",
            "version": "1.0",
            "run_id": run_id,
            "sourceplan_digest": sourceplan.digest,
            "semantic_digest": sourceplan.semantic_digest,
            "reason": reason,
            "failure_classes": failures,
            "status": "refused",
            "preview_only": True,
            "provider_calls_used": 0,
        }
        receipt = {**receipt_core, "receipt_digest": sha256_digest(receipt_core)}
        (evidence_dir / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return receipt


def result_to_dict(result: SemanticExpressionResult, *, include_artifacts: bool = False) -> dict[str, Any]:
    payload = {
        "semantic_program": {**_canonical(result.program), "semantic_digest": result.program.semantic_digest},
        "semantic_validation": {**_canonical(result.validation_report), "validation_digest": result.validation_report.digest},
        "discourse_plan": {**_canonical(result.discourse_plan), "plan_digest": result.discourse_plan.digest},
        "text_artifact": _artifact_summary(result.text_artifact),
        "scene_plan": {**_canonical(result.scene_plan), "plan_digest": result.scene_plan.digest},
        "visual_artifact": _artifact_summary(result.visual_artifact),
        "sourceplan": {**_canonical(result.sourceplan), "sourceplan_digest": result.sourceplan.digest},
        "residual_decision": result.residual_decision,
        "joined_receipt": result.joined_receipt,
        "verification": result.verification,
    }
    if include_artifacts:
        payload["text_artifact"]["content"] = result.text_artifact.content.decode("utf-8")
        payload["visual_artifact"]["content"] = result.visual_artifact.content.decode("utf-8")
    return payload


def bind_semantic_receipts(program: SemanticProgram) -> SemanticProgram:
    """Attach deterministic receipt maps for supported claims/edges that need authority."""
    registry = SemanticPredicateLawRegistry()
    evidence_receipts = dict(_mapping(program.permissions.get("evidence_receipts")))
    relationship_receipts = dict(_mapping(program.permissions.get("relationship_receipts")))
    claims: list[SemanticClaim] = []
    for claim in program.claims:
        law = registry.law_for(claim.predicate)
        if law is not None and law.evidence_required_when_supported and claim.status is ClaimStatus.SUPPORTED:
            authority = str(claim.metadata.get("evidence_authority") or "verified_receipt")
            metadata = {**dict(claim.metadata), "evidence_authority": authority}
            receipt_claim = replace(claim, metadata=metadata, evidence_refs=())
            receipt = _claim_receipt(program, receipt_claim, authority)
            evidence_receipts[receipt["receipt_digest"]] = receipt
            claims.append(replace(claim, metadata=metadata, evidence_refs=(receipt["receipt_digest"],)))
        else:
            claims.append(claim)
    edges: list[SemanticEdge] = []
    for edge in program.edges:
        if edge.status is ClaimStatus.SUPPORTED and edge.relation in {"causes", "constrained_by", "verified_by"}:
            authority = str(edge.metadata.get("evidence_authority") or ("causal_receipt" if edge.relation == "causes" else "relationship_receipt"))
            metadata = {**dict(edge.metadata), "evidence_authority": authority}
            receipt_edge = replace(edge, metadata=metadata)
            receipt = _edge_receipt(program, receipt_edge, authority)
            relationship_receipts[receipt["receipt_digest"]] = receipt
            edges.append(replace(edge, metadata={**metadata, "evidence_ref": receipt["receipt_digest"]}))
        else:
            edges.append(edge)
    permissions = {
        **dict(program.permissions),
        "evidence_receipts": evidence_receipts,
        "relationship_receipts": relationship_receipts,
    }
    return replace(program, claims=tuple(claims), edges=tuple(edges), permissions=permissions)


def failure_explanation_program() -> SemanticProgram:
    return bind_semantic_receipts(SemanticProgram(
        program_id="semantic:deployment-47-expired-cert",
        intent=SemanticIntent(
            intent="explain_failure",
            subject="deployment-47",
            question="Why did deployment 47 roll back?",
            requested_outputs=("text", "visual", "sourceplan"),
        ),
        entities=(
            SemanticEntity("deployment-47", "deployment", "Deployment 47"),
            SemanticEntity("certificate", "credential", "service certificate"),
            SemanticEntity("mtls", "protocol", "mTLS handshake"),
            SemanticEntity("health-checks", "monitor", "health checks"),
            SemanticEntity("rollback", "deployment_action", "rollback"),
        ),
        claims=(
            SemanticClaim("claim:cert-expired", "state", "certificate", value="expired", evidence_refs=(_semantic_evidence_ref("cert"),), metadata={"evidence_authority": "verified_receipt"}),
            SemanticClaim("claim:mtls-failed", "failed", "mtls", value=True, evidence_refs=(_semantic_evidence_ref("mtls"),), metadata={"evidence_authority": "sensorium_receipt"}),
            SemanticClaim("claim:health-failed", "failed", "health-checks", value=True, evidence_refs=(_semantic_evidence_ref("health"),), metadata={"evidence_authority": "sensorium_receipt"}),
            SemanticClaim("claim:rolled-back", "rolled_back", "deployment-47", object="rollback", value=True, evidence_refs=(_semantic_evidence_ref("deploy"),), metadata={"evidence_authority": "verified_receipt"}),
        ),
        edges=(
            SemanticEdge("edge:cert-to-mtls", "claim:cert-expired", "claim:mtls-failed"),
            SemanticEdge("edge:mtls-to-health", "claim:mtls-failed", "claim:health-failed"),
            SemanticEdge("edge:health-to-rollback", "claim:health-failed", "claim:rolled-back"),
        ),
        boundaries=(
            UncertaintyBoundary(
                "boundary:rotation-missed",
                unsupported_fields=("why_certificate_was_not_rotated",),
                reason="No verified rotation job or operator-action evidence was supplied.",
                affected_claim_refs=("claim:cert-expired",),
            ),
        ),
        permissions={"sourceplan_allowed": False},
        created_at="2026-08-04T00:00:00+00:00",
    ))


def code_transform_program() -> SemanticProgram:
    return bind_semantic_receipts(SemanticProgram(
        program_id="semantic:provider-router-retry-damping",
        intent=SemanticIntent(
            intent="draft_code_transform",
            subject="provider-router",
            question="Add retry damping to the provider router without changing its public API.",
            requested_outputs=("text", "visual", "sourceplan"),
        ),
        entities=(
            SemanticEntity("provider-router", "code_symbol", "ProviderRouter"),
            SemanticEntity("retry-damping", "capability", "retry damping"),
            SemanticEntity("public-api", "interface", "public API"),
            SemanticEntity("router-tests", "test_suite", "router tests"),
        ),
        claims=(
            SemanticClaim("claim:objective", "code_transform_objective", "provider-router", object="retry-damping", value="add_retry_damping"),
            SemanticClaim("claim:target-symbol", "target_symbol", "provider-router", value="app.kernel.registry.provider_registry.ProviderRegistry"),
            SemanticClaim("claim:api-preserved", "preserve_public_api", "public-api", value=True),
            SemanticClaim("claim:test-required", "test_requirement", "router-tests", value="add retry damping tests and preserve existing provider API tests"),
        ),
        edges=(
            SemanticEdge("edge:objective-to-api", "claim:objective", "claim:api-preserved", relation="constrained_by"),
            SemanticEdge("edge:objective-to-tests", "claim:objective", "claim:test-required", relation="verified_by"),
        ),
        permissions={"sourceplan_allowed": True},
        created_at="2026-08-04T00:00:00+00:00",
    ))


def _primary_claim(program: SemanticProgram) -> SemanticClaim:
    if program.intent.intent.startswith("explain"):
        for edge in reversed(GraphReasoner().ordered_edges(program)):
            claim = program.claim_map.get(edge.target_claim)
            if claim is not None and claim.subject == program.intent.subject:
                return claim
    if program.edges:
        ordered = GraphReasoner().ordered_edges(program)
        if ordered:
            return program.claim_map[ordered[-1].target_claim]
    return program.claims[-1]


def _causal_chain(program: SemanticProgram) -> tuple[SemanticEdge, ...]:
    return GraphReasoner().ordered_edges(program)


def _relevant_claim_refs(program: SemanticProgram) -> tuple[str, ...]:
    if program.intent.intent.startswith("explain"):
        edge_refs = _edge_claim_refs(_causal_chain(program))
        if edge_refs:
            return edge_refs
        return tuple(claim.claim_id for claim in program.claims if claim.subject == program.intent.subject)
    if program.intent.intent == "draft_code_transform":
        return tuple(claim.claim_id for claim in program.claims)
    return tuple(claim.claim_id for claim in program.claims if claim.status is ClaimStatus.SUPPORTED)


def _claim_question_relevance(program: SemanticProgram, claim: SemanticClaim) -> int:
    question_terms = _semantic_terms(program.intent.question)
    subject_terms = _semantic_terms(_entity_label(program, program.intent.subject))
    query_terms = question_terms.difference(subject_terms)
    if not query_terms:
        query_terms = question_terms
    candidate_text = " ".join(filter(None, (
        claim.predicate.replace("_", " "),
        str(claim.value),
        _entity_label(program, claim.object) if claim.object in program.entity_map else str(claim.object or ""),
    )))
    candidate_terms = _semantic_terms(candidate_text)
    return len(query_terms.intersection(candidate_terms))


def _semantic_terms(text: str) -> set[str]:
    stop = {"the", "a", "an", "is", "are", "was", "were", "did", "why", "what", "how", "could", "should", "now", "to", "of", "and", "or", "in"}
    terms = set(re.findall(r"[a-zA-Z0-9]+", text.lower().replace("_", " ")))
    stems = set(terms)
    for term in terms:
        if term.endswith("ed") and len(term) > 4:
            stems.add(term[:-2])
        if term.endswith("ing") and len(term) > 5:
            stems.add(term[:-3])
    return {term for term in stems if len(term) > 1 and term not in stop}


def _edge_claim_refs(edges: Sequence[SemanticEdge]) -> tuple[str, ...]:
    refs: list[str] = []
    for edge in edges:
        refs.extend([edge.source_claim, edge.target_claim])
    return tuple(dict.fromkeys(refs))


def _realize_step(program: SemanticProgram, step: DiscourseStep, style: ExpressionStyle) -> str:
    entities = program.entity_map
    claims = program.claim_map
    conclusion = _primary_claim(program)
    if step.act in {"technical_claim", "state_outcome", "single_sentence_answer", "plain_answer", "define_subject"}:
        return _realize_claim(entities, conclusion, style)
    if step.act in {"causal_chain", "compress_causal_chain", "causal_chain_with_definitions", "because_chain"}:
        chain = [_realize_edge(program, edge, style) for edge in _causal_chain(program)]
        if not chain:
            return ""
        if style is ExpressionStyle.EXECUTIVE:
            return "The causal path is: " + " → ".join(chain) + "."
        if style is ExpressionStyle.CONVERSATIONAL:
            return "In plain terms, " + "; then ".join(chain) + "."
        return "The verified chain is: " + " → ".join(chain) + "."
    if step.act == "list_supported_claims":
        rendered = [_realize_claim(entities, claims[ref], style) for ref in step.claim_refs if ref in claims]
        return "Evidence items: " + " ".join(rendered)
    if step.act == "uncertainty_boundary":
        fields = tuple(field for boundary in program.boundaries for field in boundary.unsupported_fields)
        return "The available evidence does not establish " + ", ".join(field.replace("_", " ") for field in fields) + "."
    return ""


def _realize_claim(entities: Mapping[str, SemanticEntity], claim: SemanticClaim, style: ExpressionStyle) -> str:
    subject = entities[claim.subject].label
    obj = entities[claim.object].label if claim.object in entities else str(claim.object or claim.value)
    predicate = claim.predicate.replace("_", " ")
    if claim.status is ClaimStatus.STALE:
        return f"{subject}'s current {predicate} cannot be established from stale evidence."
    if claim.status is ClaimStatus.UNSUPPORTED:
        return f"{subject}'s {predicate} is not established by the supplied evidence."
    law_text = _predicate_text(subject, claim)
    if law_text:
        return law_text
    if predicate == "state":
        return f"{subject} was {claim.value}."
    if predicate == "failed":
        return f"{subject} failed." if claim.value is True else f"{subject} did not fail."
    if predicate == "rolled back":
        return f"{subject} rolled back." if claim.value is True else f"{subject} did not roll back."
    if predicate == "temperature":
        return f"{subject}'s temperature was {claim.value}."
    if predicate == "code transform objective":
        return f"{subject} should receive the bounded transformation `{claim.value}`."
    if predicate == "target symbol":
        return f"The target symbol is `{claim.value}`."
    if predicate == "preserve public api":
        return f"The public API must remain unchanged."
    if predicate == "test requirement":
        return f"Verification requires: {claim.value}."
    return f"{subject} has {predicate}: {obj}."


def _realize_edge(program: SemanticProgram, edge: SemanticEdge, style: ExpressionStyle) -> str:
    claims = program.claim_map
    source = claims[edge.source_claim]
    target = claims[edge.target_claim]
    source_label = _claim_phrase(program.entity_map, source)
    target_label = _claim_phrase(program.entity_map, target)
    relation = edge.relation.replace("_", " ")
    if edge.relation == "causes":
        return f"{source_label} caused {target_label}"
    if edge.relation == "verified_by":
        return f"{source_label} is verified by {target_label}"
    if edge.relation == "constrained_by":
        return f"{source_label} is constrained by {target_label}"
    return f"{source_label} {relation} {target_label}"


def _visual_claim_label(program: SemanticProgram, claim: SemanticClaim) -> str:
    subject = _entity_label(program, claim.subject)
    law = SemanticPredicateLawRegistry().law_for(claim.predicate)
    if law is not None:
        if claim.value is True and law.visual_true:
            return f"{subject}: {law.visual_true.format(value=_value_text(claim.value))}"
        if claim.value is False and law.visual_false:
            return f"{subject}: {law.visual_false.format(value=_value_text(claim.value))}"
        if law.visual_true:
            return f"{subject}: {law.visual_true.format(value=_value_text(claim.value))}"
    if claim.value not in (None, ""):
        return f"{subject}: {claim.predicate}={claim.value}"
    return f"{subject}: {claim.predicate}"


def _predicate_text(subject: str, claim: SemanticClaim) -> str:
    law = SemanticPredicateLawRegistry().law_for(claim.predicate)
    if law is None:
        return ""
    template = ""
    if claim.value is True and law.true_text:
        template = law.true_text
    elif claim.value is False and law.false_text:
        template = law.false_text
    elif law.true_text:
        template = law.true_text
    if not template:
        return ""
    return f"{subject} {template.format(value=_value_text(claim.value))}."


def _value_text(value: Any) -> str:
    if isinstance(value, Mapping) and {"magnitude", "unit"}.issubset(value):
        magnitude = value.get("magnitude")
        if isinstance(magnitude, float) and magnitude.is_integer():
            magnitude = int(magnitude)
        return f"{magnitude}{value.get('unit')}"
    return str(value)


def _claim_phrase(entities: Mapping[str, SemanticEntity], claim: SemanticClaim) -> str:
    subject = entities[claim.subject].label
    if claim.predicate == "state":
        article = "" if subject.lower().startswith(("deployment", "beast", "providerrouter")) else "the "
        return f"{article}{claim.value} {subject}"
    if claim.predicate == "failed":
        article = "" if subject.lower().startswith(("deployment", "beast", "providerrouter")) else "the "
        return f"{article}failed {subject}" if claim.value is True else f"{subject} did not fail"
    if claim.predicate == "rolled_back":
        return f"{subject} rolling back" if claim.value is True else f"{subject} not rolling back"
    if claim.predicate == "temperature":
        return f"{subject} temperature {_value_text(claim.value)}"
    if claim.predicate == "code_transform_objective":
        return subject
    if claim.predicate == "preserve_public_api":
        return subject
    if claim.predicate == "test_requirement":
        return subject
    return subject


def _entity_status(program: SemanticProgram, entity_id: str) -> ClaimStatus:
    statuses = [claim.status for claim in program.claims if claim.subject == entity_id or claim.object == entity_id]
    if any(status is ClaimStatus.UNSUPPORTED for status in statuses):
        return ClaimStatus.UNSUPPORTED
    if any(status is ClaimStatus.STALE for status in statuses):
        return ClaimStatus.STALE
    if any(status is ClaimStatus.RESIDUAL_REQUIRED for status in statuses):
        return ClaimStatus.RESIDUAL_REQUIRED
    return ClaimStatus.SUPPORTED


def _status_color(status: ClaimStatus) -> str:
    return {
        ClaimStatus.SUPPORTED: "#78f0c8",
        ClaimStatus.UNSUPPORTED: "#ff7a7a",
        ClaimStatus.STALE: "#f0c35b",
        ClaimStatus.RESIDUAL_REQUIRED: "#9db7ff",
    }[status]


def _first_claim(program: SemanticProgram, predicate: str) -> SemanticClaim | None:
    for claim in program.claims:
        if claim.predicate == predicate:
            return claim
    return None


def _semantic_evidence_ref(label: str) -> str:
    return sha256_digest({"semantic_fixture_evidence": label})


def _claim_receipt(program: SemanticProgram, claim: SemanticClaim, authority: str) -> dict[str, Any]:
    core = {
        "beast_object_type": EvidenceResolver.CLAIM_OBJECT_TYPE,
        "policy_generation": EvidenceResolver.POLICY_GENERATION,
        "claim_id": claim.claim_id,
        "subject": claim.subject,
        "predicate": claim.predicate,
        "object": claim.object,
        "value": claim.value,
        "status": claim.status.value,
        "confidence": claim.confidence,
        "authority": authority,
        "program_created_at": program.created_at,
        "attestation_digest": sha256_digest({
            "attests": "claim_receipt",
            "claim_id": claim.claim_id,
            "authority": authority,
            "program_created_at": program.created_at,
        }),
    }
    return {**core, "receipt_digest": sha256_digest(core)}


def _edge_receipt(program: SemanticProgram, edge: SemanticEdge, authority: str) -> dict[str, Any]:
    core = {
        "beast_object_type": EvidenceResolver.EDGE_OBJECT_TYPE,
        "policy_generation": EvidenceResolver.POLICY_GENERATION,
        "edge_id": edge.edge_id,
        "source_claim": edge.source_claim,
        "target_claim": edge.target_claim,
        "relation": edge.relation,
        "status": edge.status.value,
        "authority": authority,
        "program_created_at": program.created_at,
        "attestation_digest": sha256_digest({
            "attests": "relationship_receipt",
            "edge_id": edge.edge_id,
            "authority": authority,
            "program_created_at": program.created_at,
        }),
    }
    return {**core, "receipt_digest": sha256_digest(core)}


def _receipt_digest(receipt: Mapping[str, Any]) -> str:
    return sha256_digest({key: value for key, value in receipt.items() if key != "receipt_digest"})


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _ontology_token(claim: SemanticClaim) -> str:
    value = str(claim.value).strip().lower()
    predicate = claim.predicate.strip().lower()
    if claim.status is ClaimStatus.STALE:
        return "stale"
    if predicate == "state":
        return "failed_positive" if value == "failed" else value
    if predicate == "failed":
        return "failed_positive" if claim.value is True else "failed_negative" if claim.value is False else ""
    if predicate == "enabled" and claim.value is True:
        return "enabled"
    if predicate == "disabled" and claim.value is True:
        return "disabled"
    if predicate == "available" and claim.value is True:
        return "available"
    if predicate == "unavailable" and claim.value is True:
        return "unavailable"
    if predicate == "accepted" and claim.value is True:
        return "accepted"
    if predicate == "refused" and claim.value is True:
        return "refused"
    if predicate == "current" and claim.value is True:
        return "current"
    return ""


def _parse_iso_timestamp(value: str) -> datetime | None:
    try:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _entity_label(program: SemanticProgram, entity_id: str) -> str:
    entity = program.entity_map.get(entity_id)
    return entity.label if entity is not None else entity_id


def resolve_python_symbol(symbol: str, *, repo_root: Path | None = None) -> dict[str, Any]:
    """Resolve a Python dotted symbol by parsing source, not by trusting labels."""
    repo = repo_root or Path(__file__).resolve().parents[3]
    parts = [part for part in str(symbol).split(".") if part]
    if len(parts) < 2:
        return {"resolved": False, "reason": "symbol must include module and object", "symbol": symbol}
    for split in range(len(parts) - 1, 0, -1):
        module_parts = parts[:split]
        object_parts = parts[split:]
        module_path = repo.joinpath(*module_parts).with_suffix(".py")
        package_path = repo.joinpath(*module_parts, "__init__.py")
        path = module_path if module_path.is_file() else package_path if package_path.is_file() else None
        if path is None:
            continue
        try:
            source_text = path.read_text(encoding="utf-8")
            tree = ast.parse(source_text)
        except SyntaxError as exc:
            return {"resolved": False, "reason": f"syntax error while parsing {path}: {exc}", "symbol": symbol}
        current: Any = tree
        for name in object_parts:
            current = _ast_child_named(current, name)
            if current is None:
                return {
                    "resolved": False,
                    "reason": f"object {'.'.join(object_parts)} not found in {path.relative_to(repo)}",
                    "symbol": symbol,
                    "module_path": str(path.relative_to(repo)),
                }
        return {
            "resolved": True,
            "symbol": symbol,
            "module_path": str(path.relative_to(repo)),
            "object_path": ".".join(object_parts),
            "module_digest": sha256_bytes(source_text.encode("utf-8")),
            "symbol_digest": sha256_bytes((ast.get_source_segment(source_text, current) or "").encode("utf-8")),
        }
    return {"resolved": False, "reason": "module source file not found under repository", "symbol": symbol}


def verify_python_symbol_contract(
    symbol: str,
    capability: Mapping[str, Any],
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    repo = repo_root or Path(__file__).resolve().parents[3]
    resolved = resolve_python_symbol(symbol, repo_root=repo)
    failures: list[str] = []
    if not resolved["resolved"]:
        failures.append("symbol_not_resolved")
        return {"passed": False, "failure_classes": tuple(failures), "contract_digest": sha256_digest({"symbol": symbol, "failures": failures})}
    target = _mapping(capability.get("allowed_target"))
    if target and resolved.get("module_path") != target.get("module_path"):
        failures.append("module_path_mismatch")
    if target and resolved.get("object_path") != target.get("object_path"):
        failures.append("object_path_mismatch")
    source_path = repo / str(resolved["module_path"])
    source_text = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source_text)
    required_imports = tuple(str(item) for item in target.get("required_import_names", ()))
    imported_names = _module_bound_names(tree)
    for name in required_imports:
        if name not in imported_names:
            failures.append(f"required_import_missing:{name}")
    class_node = _ast_child_named(tree, str(resolved["object_path"]).split(".")[0])
    methods = {
        node.name
        for node in getattr(class_node, "body", [])
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for method in tuple(str(item) for item in target.get("required_methods", ())):
        if method not in methods:
            failures.append(f"required_method_missing:{method}")
    contract_core = {
        "symbol": symbol,
        "module_path": resolved.get("module_path"),
        "object_path": resolved.get("object_path"),
        "module_digest": resolved.get("module_digest"),
        "symbol_digest": resolved.get("symbol_digest"),
        "required_methods": target.get("required_methods", ()),
        "required_import_names": target.get("required_import_names", ()),
        "policy_generation": capability.get("policy_generation"),
        "failures": tuple(failures),
    }
    return {
        **contract_core,
        "passed": not failures,
        "failure_classes": tuple(failures),
        "contract_digest": sha256_digest(contract_core),
    }


def _module_bound_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        names.add(target.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names.add(node.target.id)
    return names


def _import_python_file(path: Path) -> dict[str, Any]:
    try:
        module_name = "_beast_semantic_preview_" + sha256_bytes(str(path).encode("utf-8")).removeprefix("sha256:")[:16]
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            return {"ok": False, "error": "spec_loader_missing"}
        module = importlib.util.module_from_spec(spec)
        prior = sys.modules.get(module_name)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            if prior is not None:
                sys.modules[module_name] = prior
            else:
                sys.modules.pop(module_name, None)
        return {"ok": True, "module_name": module_name}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "message": str(exc)}


def _ast_child_named(node: Any, name: str) -> ast.AST | None:
    body = getattr(node, "body", None)
    if not isinstance(body, list):
        return None
    for child in body:
        if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == name:
            return child
        if isinstance(child, ast.Assign):
            for target in child.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return child
        if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name) and child.target.id == name:
            return child
    return None


def _json_bytes(value: bytes) -> Mapping[str, Any]:
    try:
        payload = json.loads(value.decode("utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, Mapping) else {}


def _artifact_summary(artifact: SemanticArtifact) -> dict[str, Any]:
    return {
        "media_type": artifact.media_type,
        "digest": artifact.digest,
        "bytes": len(artifact.content),
        "sequence": artifact.sequence,
        "status": artifact.status,
        "failure_class": artifact.failure_class,
    }


def _canonical(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _canonical(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _canonical(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    return value
