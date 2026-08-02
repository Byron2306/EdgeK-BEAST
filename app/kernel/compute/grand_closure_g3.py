from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from .grand_closure_g2 import G2Bindings, G2LiveComposition, build_g2_live_composition
from .residual_contracts import ResidualRoute, sha256_digest, utc_now_iso


@dataclass(frozen=True, slots=True)
class ServiceBindingSpec:
    name: str
    import_path: str
    required: bool = True
    factory: bool = False
    kwargs: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ContractProbe:
    name: str
    passed: bool
    detail: str
    required: bool = True


@dataclass(frozen=True, slots=True)
class G3AuditReceipt:
    discovered_services: tuple[str, ...]
    missing_services: tuple[str, ...]
    probes: tuple[ContractProbe, ...]
    candidate_routes: tuple[str, ...]
    executor_routes: tuple[str, ...]
    mounted: bool
    production_ready: bool
    fail_closed: bool
    created_at: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def receipt_digest(self) -> str:
        return sha256_digest(self)


class ExplicitServiceLoader:
    """Loads only operator-declared import paths. No package-wide magic discovery."""

    def __init__(self, specs: Mapping[str, ServiceBindingSpec]) -> None:
        self.specs = dict(specs)

    def load(self) -> tuple[dict[str, Any], tuple[str, ...]]:
        loaded: dict[str, Any] = {}
        missing: list[str] = []
        for name, spec in self.specs.items():
            try:
                obj = _load_symbol(spec.import_path)
                if spec.factory:
                    if not callable(obj):
                        raise TypeError(f"{spec.import_path} is not callable")
                    obj = obj(**dict(spec.kwargs))
                loaded[name] = obj
            except Exception:
                if spec.required:
                    missing.append(name)
        return loaded, tuple(sorted(missing))


def _load_symbol(path: str) -> Any:
    module_name, sep, symbol = path.partition(":")
    if not sep or not module_name or not symbol:
        raise ValueError("import path must be module:symbol")
    module = importlib.import_module(module_name)
    return getattr(module, symbol)


def bindings_from_services(services: Mapping[str, Any]) -> G2Bindings:
    return G2Bindings(
        candidate_sources=services.get("candidate_sources", {}),
        route_executors=services.get("route_executors", {}),
        sensorium_sink=services.get("sensorium_sink"),
        economics_sink=services.get("economics_sink"),
        pressure_reader=services.get("pressure_reader"),
        process_lease_resolver=services.get("process_lease_resolver"),
        arda_appraiser=services.get("arda_appraiser"),
        capability_broker=services.get("capability_broker"),
        crystal_bus_sender=services.get("crystal_bus_sender"),
        promotion_registry=services.get("promotion_registry"),
        forge_kv=services.get("forge_kv"),
        capsule_registry=services.get("capsule_registry"),
    )


class G3ReachabilityAuditor:
    def __init__(self, composition: G2LiveComposition, *, mounted: bool = False) -> None:
        self.composition = composition
        self.mounted = mounted

    def audit(self, discovered: tuple[str, ...] = (), missing: tuple[str, ...] = ()) -> G3AuditReceipt:
        reach = self.composition.reachability()
        probes = list(_probe_bindings(self.composition.bindings))
        missing_executor = tuple(reach.metadata.get("missing_executor_routes", ()))
        probes.append(ContractProbe("candidate_executor_route_closure", not missing_executor, ",".join(missing_executor) or "closed"))
        required_ok = all(p.passed for p in probes if p.required)
        return G3AuditReceipt(
            discovered_services=tuple(sorted(discovered)),
            missing_services=tuple(sorted(missing)),
            probes=tuple(probes),
            candidate_routes=reach.candidate_routes,
            executor_routes=reach.executor_routes,
            mounted=self.mounted,
            production_ready=reach.production_ready and required_ok and not missing,
            fail_closed=True,
            created_at=utc_now_iso(),
            metadata={
                "g2_receipt_digest": reach.receipt_digest,
                "authority_minting": False,
                "automatic_permissive_fallback": False,
                "discovery_mode": "explicit_import_paths_only",
            },
        )


def _probe_bindings(bindings: G2Bindings) -> tuple[ContractProbe, ...]:
    probes: list[ContractProbe] = []
    probes.append(ContractProbe("candidate_sources_mapping", isinstance(bindings.candidate_sources, Mapping) and bool(bindings.candidate_sources), type(bindings.candidate_sources).__name__))
    probes.append(ContractProbe("route_executors_mapping", isinstance(bindings.route_executors, Mapping) and bool(bindings.route_executors), type(bindings.route_executors).__name__))
    probes.append(ContractProbe("sensorium_sink_callable", callable(bindings.sensorium_sink), type(bindings.sensorium_sink).__name__))
    for route, executor in bindings.route_executors.items():
        valid_route = isinstance(route, ResidualRoute)
        callable_executor = callable(executor)
        sig_ok = False
        if callable_executor:
            try:
                sig = inspect.signature(executor)
                sig_ok = len(sig.parameters) >= 2
            except (TypeError, ValueError):
                sig_ok = True
        probes.append(ContractProbe(f"executor:{getattr(route, 'value', route)}", valid_route and callable_executor and sig_ok, f"route={valid_route};callable={callable_executor};signature={sig_ok}"))
    for name, source in bindings.candidate_sources.items():
        probes.append(ContractProbe(f"candidate_source:{name}", callable(source), type(source).__name__))
    return tuple(probes)


def build_g3_from_specs(specs: Mapping[str, ServiceBindingSpec]) -> tuple[G2LiveComposition, G3AuditReceipt]:
    loader = ExplicitServiceLoader(specs)
    services, missing = loader.load()
    composition = build_g2_live_composition(bindings_from_services(services))
    receipt = G3ReachabilityAuditor(composition).audit(tuple(services), missing)
    return composition, receipt


def mount_g3(app: Any, composition: G2LiveComposition, decode_request: Callable[[Mapping[str, Any]], Any]) -> G3AuditReceipt:
    from .grand_closure_g2_api import create_g2_router
    app.include_router(create_g2_router(composition, decode_request))
    return G3ReachabilityAuditor(composition, mounted=True).audit()
