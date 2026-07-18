"""Sealed, fail-closed preflight for discovery-agnostic crystal reuse.

This module deliberately does *not* claim semantic discovery is solved.  It
defines the receipt and admission invariants needed to test that claim with a
real corpus and a remote attested receiver.  A candidate may be discovered by
any mechanism, but it becomes reusable only after the receiver validates the
same capability contract, its own current state, and a fresh node attestation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any, Callable, Mapping, Sequence
from pathlib import Path
import json
import time
import uuid

from app.kernel.sensorium.contracts_hash import content_hash


EXPERIMENT_PROTOCOL = "beast.discovery-agnostic-reuse.v1"
ARM_NAMES = (
    "bare_local_model",
    "retrieval_without_crystal",
    "beast_without_discovery",
    "beast_with_discovery",
    "deterministic_crystal_only",
    "provider_fallback_after_refusal",
)


@dataclass(frozen=True)
class SemanticCapabilityContract:
    """Structured meaning used for discovery; task wording is deliberately absent.

    An upstream semantic mapper/schema tree may produce this object.  The
    contract is not an authority token: it is only a stable, inspectable query
    representation that lets the experiment distinguish lexical similarity
    from compatibility of operation, schema, invariants, and risk.
    """

    operation: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    invariants: tuple[str, ...]
    tool_schema_digest: str
    risk_tier: str

    @property
    def digest(self) -> str:
        return content_hash({
            "operation": self.operation,
            "input_schema": dict(self.input_schema),
            "output_schema": dict(self.output_schema),
            "invariants": sorted(self.invariants),
            "tool_schema_digest": self.tool_schema_digest,
            "risk_tier": self.risk_tier,
        })


@dataclass(frozen=True)
class ReceiverContext:
    """Privacy-safe facts a receiver may use for local admission."""

    host_id: str
    physical_host: bool
    attestation_verified: bool
    attestation_expires_at: float
    policy_digest: str
    verifier_digest: str
    state_digest: str
    runtime_digest: str
    attestation_evidence: Mapping[str, Any] = field(default_factory=dict)

    def valid_attestation(self, now: float) -> bool:
        return bool(self.physical_host and self.attestation_verified and self.attestation_expires_at > now)


@dataclass(frozen=True)
class CapabilityCandidate:
    """A verify-only candidate. Discovery metadata never grants authority."""

    candidate_id: str
    semantic_contract_digest: str
    policy_digest: str
    verifier_digest: str
    state_digest: str
    runtime_compatible_digests: tuple[str, ...]
    negative_contract_digests: tuple[str, ...] = ()
    source: str = "local_history"
    expires_at: float = 0.0


@dataclass(frozen=True)
class DiscoveryTask:
    """A sealed task representation with wording intentionally excluded."""

    task_id: str
    semantic_contract_digest: str
    policy_digest: str
    verifier_digest: str
    state_digest: str
    runtime_digest: str
    negative: bool = False

    @classmethod
    def from_contract(
        cls, *, task_id: str, contract: SemanticCapabilityContract,
        policy_digest: str, verifier_digest: str, state_digest: str,
        runtime_digest: str, negative: bool = False,
    ) -> "DiscoveryTask":
        return cls(
            task_id=task_id, semantic_contract_digest=contract.digest,
            policy_digest=policy_digest, verifier_digest=verifier_digest,
            state_digest=state_digest, runtime_digest=runtime_digest, negative=negative,
        )


@dataclass(frozen=True)
class ArmOutcome:
    arm: str
    admitted: bool
    verified: bool
    provider_calls: int
    refusal_reason: str | None = None


@dataclass(frozen=True)
class DiscoveryAgnosticReceipt:
    experiment_id: str
    protocol: str
    preregistration_digest: str
    origin_host_id: str
    receiver_host_id: str
    receiver_attestation_verified: bool
    receiver_physical_host: bool
    receiver_attestation_digest: str
    task_id: str
    candidate_id: str | None
    discovery_source: str | None
    discovery_hypothesis_only: bool
    admission_reason: str
    outcomes: tuple[ArmOutcome, ...]
    receipt_digest: str = ""

    def content_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("receipt_digest", None)
        return payload

    def sealed(self) -> "DiscoveryAgnosticReceipt":
        return replace(self, receipt_digest=content_hash(self.content_payload()))

    def validate(self) -> None:
        if self.protocol != EXPERIMENT_PROTOCOL:
            raise ValueError("unsupported discovery-agnostic receipt protocol")
        if self.receipt_digest != content_hash(self.content_payload()):
            raise ValueError("discovery-agnostic receipt is tampered")
        if tuple(item.arm for item in self.outcomes) != ARM_NAMES:
            raise ValueError("receipt must include every preregistered arm exactly once")
        discovered = next(item for item in self.outcomes if item.arm == "beast_with_discovery")
        deterministic = next(item for item in self.outcomes if item.arm == "deterministic_crystal_only")
        if discovered.admitted and not (self.receiver_attestation_verified and self.receiver_physical_host):
            raise ValueError("discovery reuse requires a fresh verified physical receiver")
        if discovered.admitted and not discovered.verified:
            raise ValueError("discovery reuse may not bypass local verification")
        if deterministic.admitted and not deterministic.verified:
            raise ValueError("deterministic replay may not bypass local verification")
        if not self.discovery_hypothesis_only:
            raise ValueError("discovery metadata must remain hypothesis-only")

    @property
    def provider_calls_avoided(self) -> int:
        discovered = next(item for item in self.outcomes if item.arm == "beast_with_discovery")
        return int(discovered.admitted and discovered.verified and discovered.provider_calls == 0)


@dataclass(frozen=True)
class PairedEconomics:
    """Measured, not estimated, cost of one eligible receiver occurrence."""

    baseline_provider_ms: float
    discovery_ms: float
    transfer_ms: float
    reproduction_ms: float
    execution_ms: float
    verifier_ms: float
    baseline_provider_calls: int = 1
    reused_provider_calls: int = 0
    measured: bool = True

    @property
    def local_total_ms(self) -> float:
        return self.discovery_ms + self.transfer_ms + self.reproduction_ms + self.execution_ms + self.verifier_ms

    @property
    def net_latency_saved_ms(self) -> float:
        return self.baseline_provider_ms - self.local_total_ms

    def validate(self) -> None:
        values = (self.baseline_provider_ms, self.discovery_ms, self.transfer_ms,
                  self.reproduction_ms, self.execution_ms, self.verifier_ms)
        if not self.measured or any(value < 0 for value in values):
            raise ValueError("paired economics must contain non-negative measured values")
        if self.baseline_provider_calls < 1 or self.reused_provider_calls != 0:
            raise ValueError("paired economics requires one baseline call and zero reuse calls")


@dataclass(frozen=True)
class DiscoveryCorpusCase:
    case_id: str
    task: DiscoveryTask
    candidates: tuple[CapabilityCandidate, ...]
    expected_admission: bool
    economics: PairedEconomics | None = None


@dataclass(frozen=True)
class DiscoveryCorpusReceipt:
    experiment_id: str
    protocol: str
    preregistration_digest: str
    case_receipts: tuple[DiscoveryAgnosticReceipt, ...]
    expected_admissions: int
    actual_admissions: int
    unsafe_admissions: int
    provider_calls_avoided: int
    measured_economic_cases: int
    net_latency_saved_ms: float
    receipt_digest: str = ""

    def content_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("receipt_digest", None)
        return payload

    def sealed(self) -> "DiscoveryCorpusReceipt":
        return replace(self, receipt_digest=content_hash(self.content_payload()))

    def validate(self) -> None:
        if self.protocol != EXPERIMENT_PROTOCOL:
            raise ValueError("unsupported discovery-agnostic corpus protocol")
        if self.receipt_digest != content_hash(self.content_payload()):
            raise ValueError("discovery-agnostic corpus receipt is tampered")
        if self.unsafe_admissions != 0:
            raise ValueError("unsafe discovery admissions invalidate the corpus")
        for receipt in self.case_receipts:
            receipt.validate()


class DiscoveryAgnosticCorpusRunner:
    """Aggregate a sealed corpus; it never converts a preflight into a claim."""

    def __init__(self, harness: "DiscoveryAgnosticReuseHarness") -> None:
        self.harness = harness

    def run(
        self,
        *,
        preregistration: Mapping[str, Any],
        origin_host_id: str,
        receiver: ReceiverContext,
        cases: Sequence[DiscoveryCorpusCase],
        verifier: Callable[[DiscoveryTask, CapabilityCandidate], bool],
        attestation_verifier: Callable[[ReceiverContext], bool],
    ) -> DiscoveryCorpusReceipt:
        if not cases:
            raise ValueError("discovery corpus requires at least one case")
        preregistration_digest = content_hash(dict(preregistration))
        receipts: list[DiscoveryAgnosticReceipt] = []
        expected = actual = unsafe = avoided = measured = 0
        net_saved = 0.0
        for case in cases:
            receipt = self.harness.run(
                preregistration=preregistration, origin_host_id=origin_host_id,
                receiver=receiver, task=case.task, candidates=case.candidates,
                verifier=verifier, attestation_verifier=attestation_verifier,
            )
            receipts.append(receipt)
            admitted = receipt.provider_calls_avoided == 1
            expected += int(case.expected_admission)
            actual += int(admitted)
            unsafe += int(admitted and not case.expected_admission)
            avoided += receipt.provider_calls_avoided
            if case.economics is not None:
                case.economics.validate()
                if admitted:
                    measured += 1
                    net_saved += case.economics.net_latency_saved_ms
        result = DiscoveryCorpusReceipt(
            experiment_id="dar-corpus:" + uuid.uuid4().hex,
            protocol=EXPERIMENT_PROTOCOL, preregistration_digest=preregistration_digest,
            case_receipts=tuple(receipts), expected_admissions=expected,
            actual_admissions=actual, unsafe_admissions=unsafe,
            provider_calls_avoided=avoided, measured_economic_cases=measured,
            net_latency_saved_ms=round(net_saved, 6),
        ).sealed()
        result.validate()
        return result


class DiscoveryAgnosticReuseHarness:
    """Evaluates one task/candidate pair without trusting wording or source."""

    def __init__(self, *, now: Callable[[], float] = time.time) -> None:
        self._now = now

    def run(
        self,
        *,
        preregistration: Mapping[str, Any],
        origin_host_id: str,
        receiver: ReceiverContext,
        task: DiscoveryTask,
        candidates: Sequence[CapabilityCandidate],
        verifier: Callable[[DiscoveryTask, CapabilityCandidate], bool],
        attestation_verifier: Callable[[ReceiverContext], bool],
    ) -> DiscoveryAgnosticReceipt:
        preregistration_digest = content_hash(dict(preregistration))
        receiver_verified = receiver.valid_attestation(self._now()) and bool(attestation_verifier(receiver))
        candidate, reason = self._admit(receiver, task, candidates, verifier, receiver_verified)
        admitted = candidate is not None
        outcomes = (
            ArmOutcome("bare_local_model", False, False, 1, "baseline_requires_model"),
            ArmOutcome("retrieval_without_crystal", False, False, 1, "retrieval_is_not_admission"),
            ArmOutcome("beast_without_discovery", False, False, 1, "discovery_disabled"),
            ArmOutcome("beast_with_discovery", admitted, admitted, 0 if admitted else 1, None if admitted else reason),
            ArmOutcome("deterministic_crystal_only", admitted, admitted, 0 if admitted else 0, None if admitted else reason),
            ArmOutcome("provider_fallback_after_refusal", False, False, 0 if admitted else 1, None if not admitted else "not_needed"),
        )
        receipt = DiscoveryAgnosticReceipt(
            experiment_id="dar:" + uuid.uuid4().hex,
            protocol=EXPERIMENT_PROTOCOL,
            preregistration_digest=preregistration_digest,
            origin_host_id=origin_host_id,
            receiver_host_id=receiver.host_id,
            receiver_attestation_verified=receiver_verified,
            receiver_physical_host=receiver.physical_host,
            receiver_attestation_digest=content_hash(dict(receiver.attestation_evidence)),
            task_id=task.task_id,
            candidate_id=candidate.candidate_id if candidate else None,
            discovery_source=candidate.source if candidate else None,
            discovery_hypothesis_only=True,
            admission_reason=reason,
            outcomes=outcomes,
        ).sealed()
        receipt.validate()
        return receipt

    def _admit(
        self,
        receiver: ReceiverContext,
        task: DiscoveryTask,
        candidates: Sequence[CapabilityCandidate],
        verifier: Callable[[DiscoveryTask, CapabilityCandidate], bool],
        receiver_verified: bool,
    ) -> tuple[CapabilityCandidate | None, str]:
        now = self._now()
        if not receiver_verified:
            return None, "receiver_attestation_unverified_or_stale"
        for candidate in candidates:
            if candidate.expires_at <= now:
                continue
            if task.semantic_contract_digest in candidate.negative_contract_digests or task.negative:
                continue
            if candidate.semantic_contract_digest != task.semantic_contract_digest:
                continue
            if candidate.policy_digest != receiver.policy_digest or candidate.policy_digest != task.policy_digest:
                continue
            if candidate.verifier_digest != receiver.verifier_digest or candidate.verifier_digest != task.verifier_digest:
                continue
            if candidate.state_digest != receiver.state_digest or candidate.state_digest != task.state_digest:
                continue
            if receiver.runtime_digest not in candidate.runtime_compatible_digests:
                continue
            if verifier(task, candidate):
                return candidate, "locally_reproduced_and_verified"
            return None, "local_reproduction_failed"
        return None, "no_locally_verified_candidate"


def commons_node_attestation_verifier(node_verifier: Callable[[Any], bool]) -> Callable[[ReceiverContext], bool]:
    """Adapt the existing signed Commons node verifier to this experiment.

    The caller supplies a complete advertised node in `attestation_evidence`.
    This prevents a receiver from treating its own boolean label as an
    attestation result and keeps the experiment compatible with TPM/ARDA-backed
    `SignedNodeAttestationVerifier` instances.
    """
    from app.kernel.commons.job_choir import NodeAdvertisement

    def verify(receiver: ReceiverContext) -> bool:
        payload = receiver.attestation_evidence.get("node_advertisement")
        if not isinstance(payload, Mapping):
            return False
        try:
            node = NodeAdvertisement(**dict(payload))
        except (TypeError, ValueError):
            return False
        return node.node_id == receiver.host_id and bool(node_verifier(node))

    return verify


def write_receipt(path: str | Path, receipt: DiscoveryAgnosticReceipt) -> None:
    """Write a portable receipt that an independent receiver can verify."""
    receipt.validate()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(asdict(receipt), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_receipt(path: str | Path) -> DiscoveryAgnosticReceipt:
    """Load and validate a receipt without executing a candidate."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    payload["outcomes"] = tuple(ArmOutcome(**item) for item in payload.get("outcomes") or ())
    receipt = DiscoveryAgnosticReceipt(**payload)
    receipt.validate()
    return receipt


def read_corpus_receipt(path: str | Path) -> DiscoveryCorpusReceipt:
    """Load a corpus receipt and validate every nested receiver result."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    receipts = []
    for item in payload.get("case_receipts") or ():
        case = dict(item)
        case["outcomes"] = tuple(ArmOutcome(**outcome) for outcome in case.get("outcomes") or ())
        receipts.append(DiscoveryAgnosticReceipt(**case))
    payload["case_receipts"] = tuple(receipts)
    receipt = DiscoveryCorpusReceipt(**payload)
    receipt.validate()
    return receipt
