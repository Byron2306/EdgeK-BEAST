"""Held-out acceptance harness for the production operator-language plane."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Mapping

from app.kernel.compute.operator_language import MeaningResolutionState, OperatorMeaningDomain
from app.kernel.compute.operator_language_plane import OperatorLanguagePlane, OperatorLanguageResponse
from app.kernel.compute.residual_contracts import sha256_digest


@dataclass(frozen=True, slots=True)
class HeldOutOperatorPromptCase:
    case_id: str
    utterance: str
    expected_domain: OperatorMeaningDomain
    expected_intent: str
    expected_state: MeaningResolutionState
    expected_bound_names: tuple[str, ...] = ()
    must_contain: tuple[str, ...] = ()
    must_not_contain: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.case_id.strip() or not self.utterance.strip():
            raise ValueError("held-out operator prompt cases require case_id and utterance")
        if not isinstance(self.expected_domain, OperatorMeaningDomain):
            object.__setattr__(self, "expected_domain", OperatorMeaningDomain(self.expected_domain))
        if not isinstance(self.expected_state, MeaningResolutionState):
            object.__setattr__(self, "expected_state", MeaningResolutionState(self.expected_state))
        if not self.expected_intent.strip():
            raise ValueError("held-out operator prompt cases require expected_intent")


@dataclass(frozen=True, slots=True)
class HeldOutOperatorPromptEvaluation:
    case_id: str
    passed: bool
    failures: tuple[str, ...]
    output_digest: str
    receipt_digest: str
    domain: str
    intent: str
    state: str
    bound_names: tuple[str, ...]
    provider_called: bool
    action_taken: bool


@dataclass(frozen=True, slots=True)
class HeldOutOperatorCorpusReceipt:
    case_count: int
    passed_count: int
    failed_count: int
    provider_calls: int
    actions_taken: int
    evaluations: tuple[HeldOutOperatorPromptEvaluation, ...] = field(repr=False)

    @property
    def passed(self) -> bool:
        return self.failed_count == 0 and self.provider_calls == 0 and self.actions_taken == 0

    @property
    def receipt_digest(self) -> str:
        return sha256_digest({
            "case_count": self.case_count,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "provider_calls": self.provider_calls,
            "actions_taken": self.actions_taken,
            "evaluation_digests": [sha256_digest(item) for item in self.evaluations],
        })


def evaluate_held_out_operator_case(
    plane: OperatorLanguagePlane,
    case: HeldOutOperatorPromptCase,
    *,
    requester: Callable[[str], OperatorLanguageResponse] | None = None,
) -> HeldOutOperatorPromptEvaluation:
    response = requester(case.utterance) if requester is not None else plane.answer(case.utterance)
    failures: list[str] = []
    receipt = response.receipt
    if receipt.domain is not case.expected_domain:
        failures.append(f"domain {receipt.domain.value} != {case.expected_domain.value}")
    if receipt.intent != case.expected_intent:
        failures.append(f"intent {receipt.intent} != {case.expected_intent}")
    if receipt.state is not case.expected_state:
        failures.append(f"state {receipt.state.value} != {case.expected_state.value}")
    if tuple(receipt.bound_names) != tuple(case.expected_bound_names):
        failures.append(f"bound_names {tuple(receipt.bound_names)!r} != {tuple(case.expected_bound_names)!r}")
    output_text = response.output.casefold()
    for expected in case.must_contain:
        if expected.casefold() not in output_text:
            failures.append(f"output missing {expected!r}")
    for forbidden in case.must_not_contain:
        if forbidden.casefold() in output_text:
            failures.append(f"output contained forbidden {forbidden!r}")
    if receipt.provider_called:
        failures.append("provider_called was true")
    if receipt.action_taken:
        failures.append("action_taken was true")
    return HeldOutOperatorPromptEvaluation(
        case_id=case.case_id,
        passed=not failures,
        failures=tuple(failures),
        output_digest=sha256_digest(response.output),
        receipt_digest=receipt.receipt_digest,
        domain=receipt.domain.value,
        intent=receipt.intent,
        state=receipt.state.value,
        bound_names=tuple(receipt.bound_names),
        provider_called=bool(receipt.provider_called),
        action_taken=bool(receipt.action_taken),
    )


def run_held_out_operator_corpus(
    plane: OperatorLanguagePlane,
    cases: Iterable[HeldOutOperatorPromptCase],
    *,
    minimum_cases: int = 40,
    requester: Callable[[str], OperatorLanguageResponse] | None = None,
) -> HeldOutOperatorCorpusReceipt:
    case_tuple = tuple(cases)
    if len(case_tuple) < minimum_cases:
        raise ValueError(f"held-out operator corpus requires at least {minimum_cases} cases")
    evaluations = tuple(evaluate_held_out_operator_case(plane, case, requester=requester) for case in case_tuple)
    return HeldOutOperatorCorpusReceipt(
        case_count=len(case_tuple),
        passed_count=sum(1 for item in evaluations if item.passed),
        failed_count=sum(1 for item in evaluations if not item.passed),
        provider_calls=sum(1 for item in evaluations if item.provider_called),
        actions_taken=sum(1 for item in evaluations if item.action_taken),
        evaluations=evaluations,
    )


def failures_by_case(receipt: HeldOutOperatorCorpusReceipt) -> Mapping[str, tuple[str, ...]]:
    return {
        item.case_id: item.failures
        for item in receipt.evaluations
        if item.failures
    }
