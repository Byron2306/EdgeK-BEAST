"""D9 Unified Adaptive Router: one proposal-only RouteDecision per request (IEI v0.9 §7.12.1, Table 15).

Similarity >= 0.95 *and* exact fingerprint compatibility nominates a zero-call crystal proposal; 0.80-<0.95 nominates
a boundary-checked local specialist adapter proposal; anything else falls back to provider routing. A RouteDecision
never grants execution (Table 14: "similarity never grants execution; it only selects proposal route"). D6 activation
gates, held-out-verified recipes, hidden tests and policy decide (PGEC §2.4, §3.3).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

EXACT_BAND = 0.95
STRUCTURAL_BAND = 0.80
ENABLE_ENV = "BEAST_ADAPTIVE_ROUTER"
CRYSTAL_FINGERPRINT_KEYS = ("opcode_catalog_digest", "crystal_digest", "source_envelope_digest")
VERIFIERS = {
    "crystal_replay": "d6_activation_gates_and_verify_command",
    "local_specialist_adapter": "hidden_tests_and_policy",
    "provider_fallback": "action_ir_full_verification",
}


def router_enabled(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return str(env.get(ENABLE_ENV) or "").strip().lower() in {"1", "true", "yes", "on"}


class RouteKind(StrEnum):
    CRYSTAL_REPLAY = "crystal_replay"
    LOCAL_SPECIALIST_ADAPTER = "local_specialist_adapter"
    PROVIDER_FALLBACK = "provider_fallback"


def classify_band(similarity: Any) -> str:
    try:
        value = float(similarity)
    except (TypeError, ValueError):
        return "insufficient"
    if math.isnan(value) or value < STRUCTURAL_BAND:
        return "insufficient"
    return "exact" if value >= EXACT_BAND else "structural"


@dataclass(frozen=True)
class RouteDecision:
    route: RouteKind
    similarity: float
    band: str
    fingerprint_compatible: bool = False
    crystal_id: str = ""
    specialist_ref: str = ""
    envelope_digest: str = ""
    demotion_signal: str = ""
    reasons: tuple[str, ...] = ()
    proposal_only: bool = True
    execution_granted: bool = False
    verifier: str = field(default="")

    def __post_init__(self) -> None:
        if self.execution_granted or not self.proposal_only:
            raise ValueError("a RouteDecision only selects a proposal route; verifiers grant execution")
        if not self.verifier:
            object.__setattr__(self, "verifier", VERIFIERS[RouteKind(self.route).value])

    def to_dict(self) -> dict[str, Any]:
        body = asdict(self)
        body["route"] = RouteKind(self.route).value
        body["reasons"] = list(self.reasons)
        body["beast_object_type"] = "beast_route_decision"
        body["version"] = "d9.1"
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()
        body["digest"] = "sha256:" + hashlib.sha256(canonical).hexdigest()
        return body


def fingerprints_compatible(crystal: Mapping[str, Any] | None, request: Mapping[str, Any] | None,
                            keys: tuple[str, ...] = CRYSTAL_FINGERPRINT_KEYS) -> bool:
    crystal, request = crystal or {}, request or {}
    return all(str(crystal.get(k) or "") and str(crystal.get(k) or "") == str(request.get(k) or "") for k in keys)


def _safe_specialist(specialist: Mapping[str, Any] | None) -> str:
    if not isinstance(specialist, Mapping) or specialist.get("execution_mode") != "local_specialist_adapter":
        return ""
    ref = str(specialist.get("model_ref") or "")
    if specialist.get("boundary_checks_passed") is not True or not ref.startswith("ollama://") or len(ref) <= 9:
        return ""
    return ref


class AdaptiveRouter:
    """Pure decision function over (similarity, fingerprints, specialist candidate); holds no execution authority."""

    def route(self, *, similarity: Any, crystal_id: str = "", crystal_fingerprints: Mapping[str, Any] | None = None,
              request_fingerprints: Mapping[str, Any] | None = None, specialist: Mapping[str, Any] | None = None,
              envelope_digest: str = "", reasons: tuple[str, ...] = (),
              fingerprint_keys: tuple[str, ...] = CRYSTAL_FINGERPRINT_KEYS) -> RouteDecision:
        band = classify_band(similarity)
        value = float(similarity) if band != "insufficient" else _finite(similarity)
        compatible = bool(crystal_id) and fingerprints_compatible(crystal_fingerprints, request_fingerprints,
                                                                  fingerprint_keys)
        notes = list(reasons)
        signal = ""
        if crystal_id and not compatible and band != "insufficient":
            signal = "fingerprint_mismatch"
            notes.append("crystal fingerprints incompatible: replay refused, verifier may demote")
        common = {"similarity": value, "band": band, "fingerprint_compatible": compatible, "crystal_id": crystal_id,
                  "envelope_digest": envelope_digest if crystal_id else "", "demotion_signal": signal}
        if band == "exact" and compatible:
            notes.append("similarity>=0.95 with exact fingerprints: zero-call crystal proposal")
            return RouteDecision(route=RouteKind.CRYSTAL_REPLAY, reasons=tuple(notes), **common)
        if band in {"exact", "structural"}:
            ref = _safe_specialist(specialist)
            if ref:
                notes.append("structural match: local specialist adapter proposal (adapter cannot execute)")
                return RouteDecision(route=RouteKind.LOCAL_SPECIALIST_ADAPTER, specialist_ref=ref,
                                     reasons=tuple(notes), **common)
            notes.append("no boundary-checked local specialist: provider fallback")
        else:
            notes.append("similarity<0.80: provider fallback")
        return RouteDecision(route=RouteKind.PROVIDER_FALLBACK, reasons=tuple(notes), **common)


def _finite(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(number) or math.isinf(number) else number


# --- D5/D6 binding for coding crystals ----------------------------------------------------------------------------

class CodingCrystalRouter:
    """Nominate a promoted D6 coding crystal for a run; only exact-band + fingerprint-compatible crystals propose replay.

    Similarity comes from ``request.route_similarity`` (an upstream matcher's nomination) or 1.0 for an exact
    task-family identity hit. Fingerprints: current opcode catalog, tamper-checked registry record digest, and the
    crystal's D5 source envelope (must exist, validate and have passed verification).
    """

    def __init__(self, registry: Any, envelope_store: Any = None, *, router: AdaptiveRouter | None = None,
                 lattice: Any = None, require_source_envelope: bool = True):
        self.registry = registry
        self.envelope_store = envelope_store
        self.router = router or AdaptiveRouter()
        # Lattice spine: when present, only lattice-admitted nodes are nominated (composites first) and the
        # tamper-checked lattice node digest becomes an extra fingerprint.
        self.lattice = lattice
        self.require_source_envelope = require_source_envelope

    def _nominate(self, family: str) -> Any:
        if self.lattice is None:
            return self.registry.active_for_family(family)
        node_id = self.lattice.best_for_family(family)
        if not node_id:
            return None
        try:
            record = self.registry.get(node_id)
        except (LookupError, ValueError):
            return None
        return record["candidate_object"] if record["status"] == "promoted" else None

    def _lattice_digests(self, crystal_id: str) -> tuple[str, str]:
        try:
            node = self.lattice.node(crystal_id)
        except (LookupError, ValueError):
            return "tampered", ""
        if node["status"] != "admitted" or not self.lattice.verify()["valid"]:
            return "not_admitted", ""
        return str(node["record_digest"]), str(node["record_digest"])

    def route_run(self, run: Mapping[str, Any], *, specialist: Mapping[str, Any] | None = None) -> RouteDecision:
        from app.kernel.compute.coding_crystals import coding_catalog_digest

        request = run.get("request") if isinstance(run.get("request"), Mapping) else {}
        family = str(request.get("task_family") or "")
        candidate = self._nominate(family) if family else None
        if candidate is None:
            return self.router.route(similarity=_finite(request.get("route_similarity")), specialist=specialist,
                                     reasons=("no promoted crystal for task family",))
        similarity = request.get("route_similarity", 1.0)
        crystal_fp = {"opcode_catalog_digest": candidate.opcode_catalog_digest,
                      "source_envelope_digest": candidate.source_envelope_digest}
        request_fp: dict[str, str] = {"opcode_catalog_digest": coding_catalog_digest()}
        try:
            record = self.registry.get(candidate.crystal_id)
            candidate.validate()
            crystal_fp["crystal_digest"] = request_fp["crystal_digest"] = str(record["record_digest"])
        except (LookupError, ValueError):
            crystal_fp["crystal_digest"] = "tampered"
        keys = CRYSTAL_FINGERPRINT_KEYS
        if self.require_source_envelope:
            request_fp["source_envelope_digest"] = self._source_envelope_digest(candidate)
        else:  # lattice admission (verified children + composite verifier) stands in for the D5 source envelope
            keys = tuple(k for k in keys if k != "source_envelope_digest")
        if self.lattice is not None:
            crystal_fp["lattice_node_digest"], request_fp["lattice_node_digest"] = self._lattice_digests(candidate.crystal_id)
            keys = (*keys, "lattice_node_digest")
        return self.router.route(similarity=similarity, crystal_id=candidate.crystal_id,
                                 crystal_fingerprints=crystal_fp, request_fingerprints=request_fp,
                                 specialist=specialist, envelope_digest=candidate.source_envelope_digest,
                                 fingerprint_keys=keys)

    def _source_envelope_digest(self, candidate: Any) -> str:
        if self.envelope_store is None:
            return ""
        try:
            envelope = self.envelope_store.get(candidate.source_run_id)
            envelope.validate()
        except (LookupError, ValueError):
            return ""
        if not (envelope.verification or {}).get("passed"):
            return ""
        return str(envelope.envelope_digest)


def record_dispatch_proposal(ir: Any, dispatcher_route: Mapping[str, Any] | None,
                             router: AdaptiveRouter | None = None) -> RouteDecision:
    """Turn an AdaptiveDispatcher result into a proposal-only RouteDecision recorded on the IR metadata.

    The IR's model, provider candidates and execution flags are never touched: routing alone grants nothing.
    """
    metadata = ir.metadata if isinstance(getattr(ir, "metadata", None), dict) else {}
    similarity = metadata.get("route_similarity")
    if similarity is None and isinstance(dispatcher_route, Mapping):
        similarity = dispatcher_route.get("confidence_score", 0.0)
    decision = (router or AdaptiveRouter()).route(
        similarity=_finite(similarity), specialist=dispatcher_route,
        reasons=("adaptive_dispatcher exact contract + boundary fingerprints",) if dispatcher_route else (),
    )
    metadata["adaptive_route"] = decision.to_dict()
    return decision
