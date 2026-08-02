from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Protocol

from .residual_candidate import ResidualCandidate
from .residual_contracts import DecisionPolicy, ResidualRoute, ROUTE_ORDER, sha256_digest
from .residual_decision_receipt import ResidualDecisionReceipt, alternatives_from_candidates
from .residual_refusal import ResidualRefusalCode, ResidualRefusal


class CandidateSource(Protocol):
    def __call__(self, request: "ResidualComputeRequest") -> Iterable[ResidualCandidate]: ...


@dataclass(frozen=True, slots=True)
class ResidualComputeRequest:
    request_id: str
    request_digest: str
    workspace_id: str
    privacy_domain: str
    task_class: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    policy_digest: str | None = None

    def __post_init__(self) -> None:
        if not self.request_id or not self.workspace_id or not self.privacy_domain or not self.task_class:
            raise ValueError("request identity, scope and task_class are required")


@dataclass(frozen=True, slots=True)
class GovernorPolicy:
    route_order: tuple[ResidualRoute, ...] = ROUTE_ORDER
    strict_residue_preference: bool = True
    max_parallel_collectors: int = 8
    score_weight_latency: float = 1.0
    score_weight_cpu: float = 0.002
    score_weight_memory_gib: float = 5.0
    score_weight_money: float = 1000.0
    score_weight_quality_shortfall: float = 10000.0
    score_weight_failure: float = 1000.0

    @property
    def policy_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class CandidateCollectionReceipt:
    candidates: tuple[ResidualCandidate, ...]
    source_failures: Mapping[str, str]
    collection_digest: str


class ResidualComputeGovernor:
    """Collect and select one residual-compute route without executing it."""

    def __init__(self, sources: Mapping[str, CandidateSource], policy: GovernorPolicy | None = None) -> None:
        self._sources = dict(sources)
        self._policy = policy or GovernorPolicy()

    def collect(self, request: ResidualComputeRequest) -> CandidateCollectionReceipt:
        found: list[ResidualCandidate] = []
        failures: dict[str, str] = {}
        workers = max(1, min(self._policy.max_parallel_collectors, len(self._sources) or 1))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="prism-r8-collect") as pool:
            futures = {pool.submit(source, request): name for name, source in self._sources.items()}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    batch = tuple(future.result())
                    for candidate in batch:
                        if candidate.workspace_id != request.workspace_id:
                            raise PermissionError(f"{name}: candidate workspace mismatch")
                        if candidate.privacy_domain != request.privacy_domain:
                            raise PermissionError(f"{name}: candidate privacy mismatch")
                    found.extend(batch)
                except Exception as exc:
                    failures[name] = f"{type(exc).__name__}: {exc}"
        # Determinism despite concurrent collection.
        found.sort(key=lambda c: (self._policy.route_order.index(c.route), c.candidate_id))
        ids = [item.candidate_id for item in found]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate IDs must be globally unique")
        digest = sha256_digest({"request": request.request_digest, "candidates": [c.candidate_digest for c in found], "failures": failures})
        return CandidateCollectionReceipt(tuple(found), failures, digest)

    def _score(self, candidate: ResidualCandidate) -> float:
        p = self._policy
        energy = candidate.predicted_energy_joules or 0.0
        return (
            candidate.expected_latency_ms * p.score_weight_latency
            + candidate.predicted_cpu_ms * p.score_weight_cpu
            + (candidate.predicted_memory_bytes / (1024 ** 3)) * p.score_weight_memory_gib
            + candidate.predicted_monetary_cost * p.score_weight_money
            + (1.0 - candidate.expected_quality) * p.score_weight_quality_shortfall
            + candidate.failure_probability * p.score_weight_failure
            + energy * 0.001
        )

    def decide(self, request: ResidualComputeRequest, collection: CandidateCollectionReceipt | None = None) -> ResidualDecisionReceipt:
        collection = collection or self.collect(request)
        candidates = collection.candidates
        scores = {c.candidate_id: self._score(c) for c in candidates if c.eligible}
        eligible = [c for c in candidates if c.eligible]
        if not eligible:
            refusal = ResidualRefusal(
                code=ResidualRefusalCode.ALL_ROUTES_REFUSED,
                message="no verified applicable residual route",
                evidence_digest=collection.collection_digest,
            )
            return ResidualDecisionReceipt(
                request_digest=request.request_digest,
                workspace_id=request.workspace_id,
                privacy_domain=request.privacy_domain,
                policy=DecisionPolicy.GOVERNED_REFUSAL,
                selected_route=None,
                selected_candidate_id=None,
                selected_candidate_digest=None,
                authority_required=None,
                reason="all_routes_refused",
                alternatives=alternatives_from_candidates(candidates, scores=scores),
                refusal=refusal,
                policy_digest=request.policy_digest or self._policy.policy_digest,
                metadata={"collection_digest": collection.collection_digest, "source_failures": dict(collection.source_failures)},
            )

        # Residues outrank newly manufactured inference when policy asks for it.
        if self._policy.strict_residue_preference:
            route_rank = {route: idx for idx, route in enumerate(self._policy.route_order)}
            best_rank = min(route_rank[c.route] for c in eligible)
            pool = [c for c in eligible if route_rank[c.route] == best_rank]
        else:
            pool = eligible
        selected = min(pool, key=lambda c: (scores[c.candidate_id], c.candidate_id))
        return ResidualDecisionReceipt(
            request_digest=request.request_digest,
            workspace_id=request.workspace_id,
            privacy_domain=request.privacy_domain,
            policy=DecisionPolicy.LOWEST_VERIFIED_EXPECTED_COST,
            selected_route=selected.route,
            selected_candidate_id=selected.candidate_id,
            selected_candidate_digest=selected.candidate_digest,
            authority_required=selected.authority,
            reason="lowest_verified_policy_compliant_expected_cost",
            alternatives=alternatives_from_candidates(candidates, scores=scores),
            policy_digest=request.policy_digest or self._policy.policy_digest,
            metadata={"collection_digest": collection.collection_digest, "source_failures": dict(collection.source_failures), "strict_residue_preference": self._policy.strict_residue_preference},
        )
