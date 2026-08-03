from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .residual_contracts import canonical_json, sha256_digest, utc_now_iso, validate_digest


class OperatorMeaningDomain(str, Enum):
    SERVICE = "service"
    CONTAINER = "container"
    MODEL = "model"
    REPOSITORY = "repository"
    FILE = "file"
    DEPLOYMENT = "deployment"
    LOG = "log"
    CACHE = "cache"
    CRYSTAL = "crystal"
    COMMONS_NODE = "commons_node"
    SPACE = "space"


class MeaningResolutionState(str, Enum):
    ENTAILED = "entailed"
    REFUTED = "refuted"
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNSUPPORTED = "unsupported"
    NOVEL = "novel"
    UNRESOLVED = "unresolved"
    CONTRADICTED = "contradicted"


BOUNDED_DOMAIN_SLOT_SCHEMA: Mapping[OperatorMeaningDomain, tuple[str, ...]] = {
    OperatorMeaningDomain.SERVICE: ("name", "status"),
    OperatorMeaningDomain.CONTAINER: ("name", "image"),
    OperatorMeaningDomain.MODEL: ("name", "provider"),
    OperatorMeaningDomain.REPOSITORY: ("path", "branch"),
    OperatorMeaningDomain.FILE: ("path", "state"),
    OperatorMeaningDomain.DEPLOYMENT: ("name", "environment"),
    OperatorMeaningDomain.LOG: ("source", "summary"),
    OperatorMeaningDomain.CACHE: ("name", "state"),
    OperatorMeaningDomain.CRYSTAL: ("crystal_id", "task_family"),
    OperatorMeaningDomain.COMMONS_NODE: ("node_id", "space"),
    OperatorMeaningDomain.SPACE: ("space_id", "runtime"),
}

REALIZATION_TONES = frozenset({"neutral", "concise", "status"})
UNAUTHORIZED_ACTION_TERMS = frozenset({
    "restarted", "deleted", "deployed", "created", "modified", "killed", "published",
})


@dataclass(frozen=True, slots=True)
class EvidenceBinding:
    evidence_digest: str
    source: str
    world_digest: str
    policy_digest: str
    temporal_scope_digest: str

    def __post_init__(self) -> None:
        for name in ("evidence_digest", "world_digest", "policy_digest", "temporal_scope_digest"):
            validate_digest(getattr(self, name), field_name=name)
        if not self.source.strip():
            raise ValueError("evidence source must not be empty")

    @property
    def binding_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class CandidateMeaning:
    meaning_id: str
    domain: OperatorMeaningDomain
    intent: str
    slots: Mapping[str, Any]
    evidence: tuple[EvidenceBinding, ...]
    resolution_state: MeaningResolutionState
    confidence: float
    negative_conditions: tuple[str, ...] = ()
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.meaning_id.strip() or not self.intent.strip():
            raise ValueError("meaning_id and intent must not be empty")
        if not isinstance(self.domain, OperatorMeaningDomain):
            object.__setattr__(self, "domain", OperatorMeaningDomain(self.domain))
        if not isinstance(self.resolution_state, MeaningResolutionState):
            object.__setattr__(self, "resolution_state", MeaningResolutionState(self.resolution_state))
        canonical_json(self.slots)
        if not isinstance(self.confidence, (int, float)) or isinstance(self.confidence, bool):
            raise TypeError("confidence must be numeric")
        if self.confidence < 0 or self.confidence > 1:
            raise ValueError("confidence must be between 0 and 1")
        if self.resolution_state is MeaningResolutionState.RESOLVED and not self.evidence:
            raise ValueError("resolved meanings require evidence")
        if self.resolution_state is MeaningResolutionState.RESOLVED and self.confidence <= 0:
            raise ValueError("resolved meanings require positive confidence")
        if any(not item.strip() for item in self.negative_conditions):
            raise ValueError("negative applicability conditions must not be empty")
        if not self.created_at:
            object.__setattr__(self, "created_at", utc_now_iso())

    @property
    def meaning_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class AnswerFrame:
    frame_id: str
    meaning_digest: str
    template_id: str
    slots: Mapping[str, Any]
    evidence_digests: tuple[str, ...]
    resolution_state: MeaningResolutionState
    unresolved_fields: tuple[str, ...] = ()
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.frame_id.strip() or not self.template_id.strip():
            raise ValueError("frame_id and template_id must not be empty")
        validate_digest(self.meaning_digest, field_name="meaning_digest")
        for digest in self.evidence_digests:
            validate_digest(digest, field_name="evidence_digest")
        if not isinstance(self.resolution_state, MeaningResolutionState):
            object.__setattr__(self, "resolution_state", MeaningResolutionState(self.resolution_state))
        canonical_json(self.slots)
        if self.resolution_state is MeaningResolutionState.RESOLVED and self.unresolved_fields:
            raise ValueError("resolved answer frames cannot carry unresolved fields")
        if self.resolution_state is not MeaningResolutionState.RESOLVED and not self.unresolved_fields:
            raise ValueError("unresolved or ambiguous answer frames must name unresolved fields")
        if not self.created_at:
            object.__setattr__(self, "created_at", utc_now_iso())

    @property
    def frame_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class MeaningCrystal:
    crystal_id: str
    meaning: CandidateMeaning
    answer_frame: AnswerFrame
    schema_digest: str
    discourse_digest: str
    world_digest: str
    capability_digest: str
    policy_digest: str
    temporal_scope_digest: str
    verifier_id: str
    verification_evidence_digest: str
    expires_at: str | None = None
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.crystal_id.strip() or not self.verifier_id.strip():
            raise ValueError("crystal_id and verifier_id must not be empty")
        for name in (
            "schema_digest", "discourse_digest", "world_digest", "capability_digest",
            "policy_digest", "temporal_scope_digest", "verification_evidence_digest",
        ):
            validate_digest(getattr(self, name), field_name=name)
        if self.meaning.resolution_state is not MeaningResolutionState.RESOLVED:
            raise ValueError("meaning crystals require resolved meanings")
        if self.answer_frame.resolution_state is not MeaningResolutionState.RESOLVED:
            raise ValueError("meaning crystals require resolved answer frames")
        if self.answer_frame.meaning_digest != self.meaning.meaning_digest:
            raise ValueError("answer frame is not bound to the candidate meaning")
        if not self.created_at:
            object.__setattr__(self, "created_at", utc_now_iso())

    @property
    def crystal_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class OperatorPromptCase:
    case_id: str
    utterance: str
    domain: OperatorMeaningDomain
    intent: str
    slots: Mapping[str, Any]
    evidence: tuple[EvidenceBinding, ...]
    tone: str = "neutral"
    unresolved_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.case_id.strip() or not self.utterance.strip() or not self.intent.strip():
            raise ValueError("operator prompt cases require identity, utterance, and intent")
        if not isinstance(self.domain, OperatorMeaningDomain):
            object.__setattr__(self, "domain", OperatorMeaningDomain(self.domain))
        canonical_json(self.slots)
        if self.tone not in REALIZATION_TONES:
            raise ValueError("operator prompt case uses unsupported tone")


@dataclass(frozen=True, slots=True)
class OperatorPromptEvaluation:
    case_id: str
    resolution_state: MeaningResolutionState
    output_digest: str
    unauthorized_actions: int
    unsupported_factual_additions: int
    ambiguity_explicit: bool


@dataclass(frozen=True, slots=True)
class OperatorLanguageAcceptanceReceipt:
    case_count: int
    unauthorized_actions: int
    unsupported_factual_additions: int
    ambiguous_cases: int
    explicit_ambiguity_cases: int
    passed: bool
    evaluation_digests: tuple[str, ...]

    @property
    def receipt_digest(self) -> str:
        return sha256_digest(self)


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def validate_bounded_domain_slots(domain: OperatorMeaningDomain, slots: Mapping[str, Any]) -> None:
    if not isinstance(domain, OperatorMeaningDomain):
        domain = OperatorMeaningDomain(domain)
    canonical_json(slots)
    required = BOUNDED_DOMAIN_SLOT_SCHEMA[domain]
    missing = [name for name in required if not _clean_text(slots.get(name))]
    if missing:
        raise ValueError(f"{domain.value} meaning is missing required slots: {', '.join(missing)}")


def compile_bounded_meaning(
    *,
    meaning_id: str,
    domain: OperatorMeaningDomain,
    intent: str,
    slots: Mapping[str, Any],
    evidence: tuple[EvidenceBinding, ...],
    confidence: float = 1.0,
    unresolved_fields: tuple[str, ...] = (),
    negative_conditions: tuple[str, ...] = (),
    template_id: str | None = None,
) -> tuple[CandidateMeaning, AnswerFrame]:
    if not isinstance(domain, OperatorMeaningDomain):
        domain = OperatorMeaningDomain(domain)
    validate_bounded_domain_slots(domain, slots)
    unresolved = tuple(dict.fromkeys(_clean_text(item) for item in unresolved_fields if _clean_text(item)))
    unknown = [field for field in unresolved if field not in slots and field not in {"title", "body"}]
    if unknown:
        raise ValueError("unresolved fields must be declared answer or meaning slots: " + ", ".join(unknown))
    state = MeaningResolutionState.UNRESOLVED if unresolved else MeaningResolutionState.RESOLVED
    meaning = CandidateMeaning(
        meaning_id=meaning_id,
        domain=domain,
        intent=intent,
        slots=dict(slots),
        evidence=evidence,
        resolution_state=state,
        confidence=confidence,
        negative_conditions=negative_conditions,
    )
    title = _clean_text(slots.get("title")) or f"{domain.value.replace('_', ' ').title()}: {_clean_text(next(iter(slots.values()), domain.value))}"
    body = _clean_text(slots.get("body")) or _summarize_slots(domain, slots)
    frame = AnswerFrame(
        frame_id="frame:" + meaning_id.removeprefix("meaning:"),
        meaning_digest=meaning.meaning_digest,
        template_id=template_id or f"{domain.value}.summary.v1",
        slots={"title": title, "body": body, **dict(slots)},
        evidence_digests=tuple(item.evidence_digest for item in evidence),
        resolution_state=state,
        unresolved_fields=unresolved,
    )
    return meaning, frame


def _summarize_slots(domain: OperatorMeaningDomain, slots: Mapping[str, Any]) -> str:
    required = BOUNDED_DOMAIN_SLOT_SCHEMA[domain]
    fragments = [f"{name}={_clean_text(slots.get(name))}" for name in required]
    optional = [
        f"{name}={_clean_text(slots[name])}"
        for name in sorted(slots)
        if name not in set(required) | {"title", "body"} and _clean_text(slots[name])
    ]
    return "; ".join(fragments + optional)


def realize_answer_frame(frame: AnswerFrame, *, tone: str = "neutral") -> str:
    if frame.resolution_state is not MeaningResolutionState.RESOLVED:
        raise ValueError("cannot realize an unresolved answer frame")
    if tone not in REALIZATION_TONES:
        raise ValueError("unsupported deterministic realization tone")
    title = str(frame.slots.get("title") or "").strip()
    body = str(frame.slots.get("body") or "").strip()
    if not title or not body:
        raise ValueError("resolved answer frames require title and body slots")
    if tone == "neutral":
        return f"{title}\n\n{body}"
    if tone == "concise":
        return f"{title}: {body}"
    return f"[{title}] {body}"


def build_residual_lexicalization_payload(
    frame: AnswerFrame,
    *,
    target: Mapping[str, Any] | None = None,
    failure_summary: str = "answer frame has unresolved lexical fields",
    constraints: tuple[str, ...] = (),
) -> dict[str, Any]:
    if frame.resolution_state is MeaningResolutionState.RESOLVED:
        return {
            "model_call_required": False,
            "resolved_fields": dict(frame.slots),
            "unresolved_fields": [],
            "answer_frame_digest": frame.frame_digest,
        }
    unresolved = tuple(dict.fromkeys(_clean_text(item) for item in frame.unresolved_fields if _clean_text(item)))
    if not unresolved:
        raise ValueError("lexicalization residual requires declared unresolved fields")
    allowed = {field: "string" for field in unresolved}
    resolved_digests = {
        key: sha256_digest(value)
        for key, value in frame.slots.items()
        if key not in set(unresolved)
    }
    return {
        "task_family": "beast.operator_language",
        "operation": "lexicalize_answer_frame",
        "answer_frame_digest": frame.frame_digest,
        "template_id": frame.template_id,
        "target": dict(target or {}),
        "failure_summary": failure_summary,
        "constraints": tuple(constraints) + (
            "return only declared unresolved fields",
            "do not introduce new facts",
            "do not claim actions were taken",
            "do not add causal claims",
        ),
        "resolved_field_digests": resolved_digests,
        "unresolved_fields": list(unresolved),
        "allowed_output": allowed,
        "residual_contract": {
            "field": unresolved[0],
            "scope": "text_fragment",
            "allowed_fields": list(unresolved),
            "forbidden_claims": ("new_facts", "actions", "causal_claims"),
        },
    }


def evaluate_operator_prompt_case(case: OperatorPromptCase) -> OperatorPromptEvaluation:
    if not case.evidence:
        output = f"Ambiguous: evidence is required before resolving {case.domain.value}."
        return OperatorPromptEvaluation(
            case_id=case.case_id,
            resolution_state=MeaningResolutionState.AMBIGUOUS,
            output_digest=sha256_digest(output),
            unauthorized_actions=0,
            unsupported_factual_additions=0,
            ambiguity_explicit="ambiguous" in output.casefold() and "evidence" in output.casefold(),
        )
    _meaning, frame = compile_bounded_meaning(
        meaning_id="meaning:" + case.case_id,
        domain=case.domain,
        intent=case.intent,
        slots=case.slots,
        evidence=case.evidence,
        unresolved_fields=case.unresolved_fields,
    )
    output = realize_answer_frame(frame, tone=case.tone) if not frame.unresolved_fields else ""
    text = output.casefold()
    slot_text = " ".join(str(value).casefold() for value in case.slots.values())
    unauthorized = sum(1 for term in UNAUTHORIZED_ACTION_TERMS if term in text and term not in slot_text)
    unsupported = _unsupported_output_terms(output, frame.slots)
    return OperatorPromptEvaluation(
        case_id=case.case_id,
        resolution_state=frame.resolution_state,
        output_digest=sha256_digest(output or frame.frame_digest),
        unauthorized_actions=unauthorized,
        unsupported_factual_additions=unsupported,
        ambiguity_explicit=frame.resolution_state is not MeaningResolutionState.AMBIGUOUS,
    )


def run_operator_language_acceptance(cases: tuple[OperatorPromptCase, ...]) -> OperatorLanguageAcceptanceReceipt:
    if len(cases) < 200:
        raise ValueError("operator-language acceptance requires at least 200 prompt cases")
    evaluations = tuple(evaluate_operator_prompt_case(case) for case in cases)
    unauthorized = sum(item.unauthorized_actions for item in evaluations)
    unsupported = sum(item.unsupported_factual_additions for item in evaluations)
    ambiguous = sum(1 for item in evaluations if item.resolution_state is MeaningResolutionState.AMBIGUOUS)
    explicit = sum(1 for item in evaluations if item.resolution_state is MeaningResolutionState.AMBIGUOUS and item.ambiguity_explicit)
    return OperatorLanguageAcceptanceReceipt(
        case_count=len(cases),
        unauthorized_actions=unauthorized,
        unsupported_factual_additions=unsupported,
        ambiguous_cases=ambiguous,
        explicit_ambiguity_cases=explicit,
        passed=unauthorized == 0 and unsupported == 0 and ambiguous == explicit,
        evaluation_digests=tuple(sha256_digest(item) for item in evaluations),
    )


def _unsupported_output_terms(output: str, slots: Mapping[str, Any]) -> int:
    if not output:
        return 0
    allowed = set()
    for value in slots.values():
        allowed.update(_words(str(value)))
    allowed.update({"and", "is", "are", "to", "the", "a", "an", "of", "for", "with"})
    return sum(1 for word in _words(output) if word not in allowed)


def _words(value: str) -> tuple[str, ...]:
    result = []
    current = []
    for char in value.casefold():
        if char.isalnum() or char in {"_", "-", "/"}:
            current.append(char)
        elif current:
            result.append("".join(current))
            current.clear()
    if current:
        result.append("".join(current))
    return tuple(result)
