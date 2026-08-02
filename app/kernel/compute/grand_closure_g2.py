from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Callable, Iterable, Mapping, Protocol

from .residual_candidate import ResidualCandidate
from .residual_compute_governor import GovernorPolicy, ResidualComputeGovernor, ResidualComputeRequest
from .residual_compute_plane import ResidualComputePlane, RouteExecutionResult
from .residual_contracts import ResidualRoute, ResidualAuthority, sha256_digest, utc_now_iso


class CandidateAdapter(Protocol):
    def __call__(self, request: ResidualComputeRequest) -> Iterable[ResidualCandidate]: ...


class RouteExecutor(Protocol):
    def __call__(self, request: ResidualComputeRequest, decision_digest: str) -> RouteExecutionResult: ...


@dataclass(frozen=True, slots=True)
class CompositionHealth:
    name: str
    constructed: bool
    required: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class G2ReachabilityReceipt:
    components: tuple[CompositionHealth, ...]
    candidate_routes: tuple[str, ...]
    executor_routes: tuple[str, ...]
    fail_closed: bool
    production_ready: bool
    created_at: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def receipt_digest(self) -> str:
        return sha256_digest(self)


@dataclass(slots=True)
class G2Bindings:
    candidate_sources: Mapping[str, CandidateAdapter]
    route_executors: Mapping[ResidualRoute, RouteExecutor]
    sensorium_sink: Callable[[Mapping[str, Any]], str]
    economics_sink: Callable[[Mapping[str, Any]], str] | None = None
    pressure_reader: Any | None = None
    process_lease_resolver: Any | None = None
    arda_appraiser: Any | None = None
    capability_broker: Any | None = None
    crystal_bus_sender: Any | None = None
    promotion_registry: Any | None = None
    forge_kv: Any | None = None
    capsule_registry: Any | None = None


class G2LiveComposition:
    """One fail-closed composition root for PRISM, Forge-KV and sealed capsules.

    This object only wires already-governed dependencies. It does not mint authority,
    fabricate candidate evidence, or silently install permissive fallbacks.
    """

    def __init__(self, bindings: G2Bindings, *, policy: GovernorPolicy | None = None) -> None:
        if not bindings.candidate_sources:
            raise ValueError("at least one candidate source is required")
        if not bindings.route_executors:
            raise ValueError("at least one route executor is required")
        if bindings.sensorium_sink is None:
            raise ValueError("sensorium_sink is required")
        self.bindings = bindings
        self.governor = ResidualComputeGovernor(bindings.candidate_sources, policy=policy)
        self.plane = ResidualComputePlane(
            self.governor,
            bindings.route_executors,
            sensorium_sink=bindings.sensorium_sink,
            economics_sink=bindings.economics_sink,
        )
        self._lock = RLock()
        self._runs = 0
        self._last_closure_digest: str | None = None

    def run(self, request: ResidualComputeRequest):
        output, closure = self.plane.run(request)
        with self._lock:
            self._runs += 1
            self._last_closure_digest = closure.closure_digest
        return output, closure

    def reachability(self) -> G2ReachabilityReceipt:
        b = self.bindings
        required = {
            "sensorium_sink": b.sensorium_sink,
            "candidate_sources": b.candidate_sources,
            "route_executors": b.route_executors,
        }
        optional = {
            "economics_sink": b.economics_sink,
            "pressure_reader": b.pressure_reader,
            "process_lease_resolver": b.process_lease_resolver,
            "arda_appraiser": b.arda_appraiser,
            "capability_broker": b.capability_broker,
            "crystal_bus_sender": b.crystal_bus_sender,
            "promotion_registry": b.promotion_registry,
            "forge_kv": b.forge_kv,
            "capsule_registry": b.capsule_registry,
        }
        components = []
        for name, obj in required.items():
            components.append(CompositionHealth(name, bool(obj), True, type(obj).__name__ if obj is not None else "missing"))
        for name, obj in optional.items():
            components.append(CompositionHealth(name, obj is not None, False, type(obj).__name__ if obj is not None else "not_bound"))
        candidate_routes = sorted({c.route.value for source in b.candidate_sources.values() for c in _probe_source(source)})
        executor_routes = sorted(route.value for route in b.route_executors)
        missing_executor = sorted(set(candidate_routes) - set(executor_routes))
        required_ok = all(item.constructed for item in components if item.required)
        production_ready = required_ok and not missing_executor
        return G2ReachabilityReceipt(
            components=tuple(components),
            candidate_routes=tuple(candidate_routes),
            executor_routes=tuple(executor_routes),
            fail_closed=True,
            production_ready=production_ready,
            created_at=utc_now_iso(),
            metadata={
                "missing_executor_routes": missing_executor,
                "runs": self._runs,
                "last_closure_digest": self._last_closure_digest,
                "authority_minting": False,
                "permissive_fallback": False,
            },
        )


def _probe_source(source: CandidateAdapter) -> tuple[ResidualCandidate, ...]:
    probe = ResidualComputeRequest(
        request_id="g2-reachability-probe",
        request_digest="sha256:" + "0" * 64,
        workspace_id="__g2_probe__",
        privacy_domain="__g2_probe__",
        task_class="reachability_probe",
        payload={"probe_only": True},
    )
    try:
        return tuple(source(probe))
    except Exception:
        return ()


class StaticRouteAdapter:
    """Narrow adapter useful for binding an existing candidate producer."""

    def __init__(self, producer: Callable[[ResidualComputeRequest], Iterable[ResidualCandidate]]) -> None:
        self._producer = producer

    def __call__(self, request: ResidualComputeRequest) -> Iterable[ResidualCandidate]:
        return tuple(self._producer(request))


class VerifiedResultExecutor:
    route = ResidualRoute.SEMANTIC_RESULT
    authority = ResidualAuthority.READ_VERIFIED

    def __init__(self, resolver: Callable[[ResidualComputeRequest, str], Any]) -> None:
        self._resolver = resolver

    def __call__(self, request: ResidualComputeRequest, decision_digest: str) -> RouteExecutionResult:
        output = self._resolver(request, decision_digest)
        return RouteExecutionResult(
            route=self.route,
            authority_used=self.authority,
            output=output,
            verified=True,
            execution_digest=sha256_digest({"route": self.route.value, "request": request.request_digest, "decision": decision_digest, "output": output}),
        )


def build_g2_live_composition(bindings: G2Bindings, *, policy: GovernorPolicy | None = None) -> G2LiveComposition:
    return G2LiveComposition(bindings, policy=policy)
