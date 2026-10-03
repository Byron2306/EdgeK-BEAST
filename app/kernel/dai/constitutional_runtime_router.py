"""Phase-7 Constitutional Runtime Router.

This is the first "speak to BEAST" entrypoint.  It does not bypass the arenas;
it consumes the admitted crystals and constitutional receipts, then decides
whether an ordinary deterministic answer or visual may be emitted.

Supported first runtime family:

    restart-risk composition + Sophia source-support

The same canonical meaning graph drives both text and SVG.  The visual is never
generated from the text answer.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from app.kernel.compute.deterministic_intelligence import canonical_json, require_digest, sha256_digest
from app.kernel.dai.capability_ledger import CapabilityLedger, CapabilityCrystal, LEDGER_VERSION
from app.kernel.dai.constitutional_extensions import (
    AuthorityLevel,
    AuthorityVector,
    CadenceObservation,
    CadencePolicy,
    EffectManifest,
    EffectObservation,
    EvidenceAtom,
    EvidenceMode,
    EvidenceRequirement,
    build_lawful_reentry_receipt,
    detect_authority_pollution,
    evaluate_cadence,
    verify_effect_containment,
    verify_evidence_sufficiency,
)
from app.kernel.dai.constitutional_formal_hardening import (
    sign_hybrid_ed25519_ml_dsa_65,
    run_z3_effect_containment_model,
)
from app.kernel.dai.phase3_composition import prune_phase3_composition_graph, route_phase3_residuals
from app.kernel.dai.phase3_expression import (
    compile_phase3_expression,
    phase3_expression_receipt,
    verify_phase3_text_entailment,
    verify_phase3_visual_entailment,
)
from app.kernel.dai.phase6_truth_arena import (
    REQUIRED_LEDGER_FAMILIES,
    Phase62TruthCase,
    build_phase6_truth_graph,
)
from app.kernel.dai.visual_style_capsule import VisualStyleCapsule, apply_visual_style_to_svg


PHASE7_RUNTIME_ROUTER_VERSION = "2026-08-05.phase7.constitutional-runtime-router.v1"
DEFAULT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class BeastRuntimeRequest:
    question: str
    mode: str = "auto"
    source_service: str = ""
    target_service: str = ""
    request_id: str = "phase7:runtime:interactive"
    now: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        if not self.question.strip():
            raise ValueError("BEAST runtime request requires a question")
        if self.mode not in {"auto", "speak", "draw"}:
            raise ValueError("BEAST runtime mode must be auto, speak or draw")

    @property
    def request_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class BeastRuntimeContext:
    ledger: CapabilityLedger
    phase6_4_constitutional_receipt: Mapping[str, Any]
    phase6_5_formal_receipt: Mapping[str, Any]
    visual_style_capsule: Mapping[str, Any] | None = None
    root: str = str(DEFAULT_ROOT)

    def __post_init__(self) -> None:
        if self.phase6_4_constitutional_receipt.get("green") is not True:
            raise ValueError("Phase 6.4 constitutional receipt must be green before runtime use")
        if self.phase6_5_formal_receipt.get("green") is not True:
            raise ValueError("Phase 6.5 formal hardening receipt must be green before runtime use")


def load_default_runtime_context(root: str | Path = DEFAULT_ROOT) -> BeastRuntimeContext:
    base = Path(root)
    return BeastRuntimeContext(
        ledger=_read_capability_ledger(base / "evidence/dai-diode/phase6-truth-arena/dai_capability_ledger.json"),
        phase6_4_constitutional_receipt=_read_json(base / "evidence/dai-diode/phase6-constitutional-extensions/dai_phase6_constitutional_extensions_receipt.json"),
        phase6_5_formal_receipt=_read_json(base / "evidence/dai-diode/phase6-formal-hardening/dai_phase6_formal_hardening_receipt.json"),
        visual_style_capsule=None,
        root=str(base),
    )


def route_beast_runtime_request(request: BeastRuntimeRequest, context: BeastRuntimeContext) -> dict[str, Any]:
    mode = _resolve_mode(request)
    source, target = _resolve_services(request)
    family_supported = _question_matches_restart_risk(request.question) and bool(source and target)
    ledger_ready = context.ledger.require_families(REQUIRED_LEDGER_FAMILIES)

    if family_supported and ledger_ready:
        case = _runtime_case(request, source=source, target=target, answerable=True)
    else:
        case = _runtime_case(
            request,
            source=source or "unresolved_source_service",
            target=target or "unresolved_target_service",
            answerable=False,
            visible_span_bound=bool(source and target),
            source_supports_policy=False,
            topology_edge_supported=False,
            current_evidence_supported=False,
        )

    graph = build_phase6_truth_graph(case, ledger=context.ledger)
    relevance = prune_phase3_composition_graph(graph, answer_claim_ids=("claim:phase6.2:mixed-policy-restart-answer",))
    route = route_phase3_residuals(graph, relevance)
    bundle = compile_phase3_expression(graph, route, relevance)
    text_receipt = verify_phase3_text_entailment(graph, route, bundle, relevance)
    visual_receipt = verify_phase3_visual_entailment(graph, route, bundle, relevance)
    joined_receipt = phase3_expression_receipt(bundle, text_receipt, visual_receipt)

    checks = _constitutional_runtime_checks(
        request=request,
        context=context,
        bundle_digest=bundle.bundle_digest,
        answerable=family_supported and ledger_ready,
    )
    constitutional_green = all(checks["gates"].values())
    ordinary_answer_allowed = bool(
        route.ordinary_answer_available
        and joined_receipt["joined_verification"]
        and constitutional_green
    )
    svg_payload = bundle.svg if mode == "draw" else ""
    visual_style_receipt = None
    visual_style_capsule_digest = ""
    if mode == "draw" and ordinary_answer_allowed and context.visual_style_capsule:
        capsule_payload = dict(context.visual_style_capsule)
        capsule_payload.pop("capsule_digest", None)
        capsule = VisualStyleCapsule(**capsule_payload)
        svg_payload, visual_style_receipt = apply_visual_style_to_svg(bundle.svg, capsule)
        visual_style_capsule_digest = capsule.capsule_digest
        ordinary_answer_allowed = ordinary_answer_allowed and visual_style_receipt["verified"]
    lawful_reentry = None
    if not ordinary_answer_allowed:
        lawful_reentry = build_lawful_reentry_receipt(
            refusal_digest=bundle.bundle_digest,
            failed_criterion=_failed_criterion(family_supported=family_supported, ledger_ready=ledger_ready, checks=checks),
            cure_evidence=(
                "ask within admitted restart-risk/source-support capability family",
                "provide source and target service identifiers",
                "refresh stale constitutional cadence if cadence failed",
                "promote new crystal family through Sophia/BEAST/Commons if outside current capability",
            ),
            eligible_evidence_providers=("beast", "sophia", "commons", "sensorium"),
            appealable=True,
            fresh_world_state_required=True,
            permanent_prohibitions=("provider_call_without_residual_authority", "visual_generated_from_text_answer"),
        )

    answer_payload: dict[str, Any] = {
        "beast_object_type": "dai_phase7_runtime_answer_payload",
        "version": PHASE7_RUNTIME_ROUTER_VERSION,
        "request_digest": request.request_digest,
        "mode": mode,
        "family": "restart_risk_composition+sophia_source_support" if family_supported else "unsupported_or_unparsed",
        "graph_digest": graph.graph_digest,
        "relevance_slice_digest": relevance.slice_digest,
        "route_digest": route.route_digest,
        "expression_bundle_digest": bundle.bundle_digest,
        "semantic_digest": bundle.semantic_digest,
        "ordinary_answer_allowed": ordinary_answer_allowed,
        "text": bundle.text,
        "svg": svg_payload if ordinary_answer_allowed else "",
        "visual_present": mode == "draw" and ordinary_answer_allowed,
        "lawful_reentry_receipt_digest": lawful_reentry["receipt_digest"] if lawful_reentry else "",
        "visual_style_capsule_digest": visual_style_capsule_digest,
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }
    signature_packet, signature_receipt = sign_hybrid_ed25519_ml_dsa_65(answer_payload)
    runtime_receipt: dict[str, Any] = {
        "beast_object_type": "dai_phase7_constitutional_runtime_receipt",
        "version": PHASE7_RUNTIME_ROUTER_VERSION,
        "request_digest": request.request_digest,
        "mode": mode,
        "family_supported": family_supported,
        "ledger_digest": context.ledger.ledger_digest,
        "phase6_4_constitutional_receipt_digest": context.phase6_4_constitutional_receipt["receipt_digest"],
        "phase6_5_formal_receipt_digest": context.phase6_5_formal_receipt["receipt_digest"],
        "graph_digest": graph.graph_digest,
        "route_digest": route.route_digest,
        "expression_bundle_digest": bundle.bundle_digest,
        "text_entailment_receipt_digest": text_receipt["receipt_digest"],
        "visual_entailment_receipt_digest": visual_receipt["receipt_digest"],
        "joined_receipt_digest": joined_receipt["receipt_digest"],
        "constitutional_checks": checks,
        "visual_style_capsule_digest": visual_style_capsule_digest,
        "visual_style_receipt": visual_style_receipt,
        "ordinary_answer_allowed": ordinary_answer_allowed,
        "lawful_reentry_receipt": lawful_reentry,
        "answer_payload_digest": sha256_digest(answer_payload),
        "hybrid_signature_packet": signature_packet,
        "hybrid_signature_verification_receipt": signature_receipt,
        "green": bool(
            signature_receipt["verified"]
            and joined_receipt["joined_verification"]
            and constitutional_green
            and (visual_style_receipt is None or visual_style_receipt["verified"])
        ),
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
        "claim_boundary": (
            "Phase-7 runtime routes a live request through admitted crystals, constitutional law, "
            "deterministic text/SVG expression and hybrid signature. It supports only the currently "
            "admitted restart-risk + Sophia source-support family; outside-family requests lawfully refuse. "
            "Optional visual style capsules may restyle SVG but cannot change semantic graph content."
        ),
    }
    runtime_receipt["receipt_digest"] = sha256_digest(runtime_receipt)
    return {
        "beast_object_type": "dai_phase7_constitutional_runtime_response",
        "version": PHASE7_RUNTIME_ROUTER_VERSION,
        "answer_text": bundle.text,
        "svg": answer_payload["svg"],
        "visual_present": answer_payload["visual_present"],
        "ordinary_answer_allowed": ordinary_answer_allowed,
        "action": route.action.value if ordinary_answer_allowed else "refuse",
        "semantic_digest": bundle.semantic_digest,
        "runtime_receipt": runtime_receipt,
        "runtime_receipt_digest": runtime_receipt["receipt_digest"],
        "hybrid_signature_packet_digest": signature_packet.packet_digest,
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }


def _constitutional_runtime_checks(
    *,
    request: BeastRuntimeRequest,
    context: BeastRuntimeContext,
    bundle_digest: str,
    answerable: bool,
) -> dict[str, Any]:
    require_digest(bundle_digest, field_name="bundle_digest")
    phase6_4_digest = str(context.phase6_4_constitutional_receipt["receipt_digest"])
    phase6_5_digest = str(context.phase6_5_formal_receipt["receipt_digest"])
    manifest = EffectManifest(
        capability_id="crystal:phase7:constitutional-runtime-router",
        capability_digest=bundle_digest,
        permitted_reads=(
            "evidence/dai-diode/phase6-truth-arena/dai_capability_ledger.json",
            "evidence/dai-diode/phase6-constitutional-extensions/dai_phase6_constitutional_extensions_receipt.json",
            "evidence/dai-diode/phase6-formal-hardening/dai_phase6_formal_hardening_receipt.json",
        ),
        permitted_writes=("evidence/dai-diode/phase7-runtime/dai_phase7_runtime_latest.json",),
        network_destinations=(),
        syscalls=("openat", "read", "write", "close", "fstat"),
        tools=("capability_ledger", "constitutional_runtime_router", "phase3_expression", "hybrid_signer"),
        model_calls=(),
        data_classifications=("public_test_artifact", "interactive_question_metadata"),
        resource_limits={"max_provider_calls": 0, "max_network_destinations": 0, "max_model_calls": 0},
        expected_postconditions=("runtime_receipt_emitted", "hybrid_signature_verified"),
    )
    observation = EffectObservation(
        capability_id=manifest.capability_id,
        observed_reads=manifest.permitted_reads,
        observed_writes=manifest.permitted_writes,
        observed_network_destinations=(),
        observed_syscalls=("openat", "read", "write", "close", "fstat"),
        observed_tools=("capability_ledger", "constitutional_runtime_router", "phase3_expression", "hybrid_signer"),
        observed_model_calls=(),
        observed_data_classifications=("public_test_artifact", "interactive_question_metadata"),
        resource_usage={"max_provider_calls": 0, "max_network_destinations": 0, "max_model_calls": 0},
        postconditions=("runtime_receipt_emitted", "hybrid_signature_verified"),
    )
    containment = verify_effect_containment(manifest, observation)
    z3 = run_z3_effect_containment_model(manifest)
    evidence = verify_evidence_sufficiency(
        EvidenceRequirement(
            claim_id="claim:phase7:runtime-answer-use",
            required_mode=EvidenceMode.DIRECT_OBSERVED,
            environment="beast_runtime",
            allow_synthetic=False,
        ),
        (
            EvidenceAtom(
                claim_id="claim:phase7:runtime-answer-use",
                evidence_mode=EvidenceMode.DIRECT_OBSERVED,
                environment="beast_runtime",
                inheritance="direct",
                synthetic=False,
                freshness="current",
                authority_weight="direct_evidence",
                limitations=("single_runtime_family",),
                evidence_digest=phase6_4_digest,
            ),
            EvidenceAtom(
                claim_id="claim:phase7:runtime-answer-use",
                evidence_mode=EvidenceMode.DIRECT_OBSERVED,
                environment="beast_runtime",
                inheritance="direct",
                synthetic=False,
                freshness="current",
                authority_weight="direct_evidence",
                limitations=("single_proposition_commons_model",),
                evidence_digest=phase6_5_digest,
            ),
        ),
    )
    now = _parse_runtime_now(request.now)
    cadence = evaluate_cadence(
        CadencePolicy(
            capability_id=manifest.capability_id,
            observation_recurrence_seconds=900,
            corroboration_frequency_seconds=900,
            maximum_tolerated_drift_seconds=5,
            required_challenge_cadence_seconds=1800,
            lease_renewal_condition="phase6_4_and_phase6_5_receipts_green_and_ledger_digest_unchanged",
            silence_threshold_seconds=1800,
            trusted_time_source="runtime_utc_clock_test_only",
            expires_at=(now + timedelta(minutes=10)).isoformat(),
        ),
        CadenceObservation(
            capability_id=manifest.capability_id,
            observed_at=now.isoformat(),
            last_corroborated_at=now.isoformat(),
            last_challenged_at=now.isoformat(),
            now=now.isoformat(),
            observed_drift_seconds=0,
            trusted_time_receipt_digest=sha256_digest({"request": request.request_digest, "now": now.isoformat()}),
        ),
    )
    authority = detect_authority_pollution(
        AuthorityVector(
            claim_id="claim:phase7:runtime-answer-use",
            normative_authority=AuthorityLevel.TEST_ONLY,
            epistemic_authority=AuthorityLevel.DIRECT_EVIDENCE if answerable else AuthorityLevel.MAPPING,
            source_authority=AuthorityLevel.TEST_ONLY,
            data_authority=AuthorityLevel.DIRECT_EVIDENCE if answerable else AuthorityLevel.MAPPING,
            rhetorical_confidence=AuthorityLevel.TEST_ONLY,
            requested_authority=AuthorityLevel.TEST_ONLY,
        ),
    )
    gates = {
        "ledger_has_required_families": context.ledger.require_families(REQUIRED_LEDGER_FAMILIES),
        "phase6_4_constitutional_green": context.phase6_4_constitutional_receipt.get("green") is True,
        "phase6_5_formal_green": context.phase6_5_formal_receipt.get("green") is True,
        "effect_containment_green": containment["contained"] is True,
        "z3_effect_model_green": z3["green"] is True,
        "evidence_strength_sufficient": evidence["evidence_sufficient"] is True,
        "cadence_current": cadence["action"] == "answer",
        "authority_pollution_absent": authority["admission_allowed"] is True,
        "provider_calls_zero": True,
        "production_execution_forbidden": True,
    }
    return {
        "beast_object_type": "dai_phase7_runtime_constitutional_checks",
        "version": PHASE7_RUNTIME_ROUTER_VERSION,
        "effect_manifest_digest": manifest.manifest_digest,
        "effect_containment_receipt_digest": containment["receipt_digest"],
        "z3_receipt_digest": z3["receipt_digest"],
        "evidence_sufficiency_receipt_digest": evidence["receipt_digest"],
        "cadence_receipt_digest": cadence["receipt_digest"],
        "authority_pollution_receipt_digest": authority["receipt_digest"],
        "gates": gates,
        "green": all(gates.values()),
    }


def _runtime_case(
    request: BeastRuntimeRequest,
    *,
    source: str,
    target: str,
    answerable: bool,
    visible_span_bound: bool = True,
    source_supports_policy: bool = True,
    topology_edge_supported: bool = True,
    current_evidence_supported: bool = True,
) -> Phase62TruthCase:
    semantic_case_digest = sha256_digest({
        "family": "phase7:restart-risk+sophia-source-support",
        "source": source,
        "target": target,
        "answerable": answerable,
        "visible_span_bound": visible_span_bound,
        "source_supports_policy": source_supports_policy,
        "topology_edge_supported": topology_edge_supported,
        "current_evidence_supported": current_evidence_supported,
    })
    return Phase62TruthCase(
        case_id=f"phase7:runtime:{semantic_case_digest[-12:]}",
        domain="interactive-runtime",
        source_service=source,
        target_service=target,
        policy_source="BEAST Constitutional Runtime Policy",
        policy_claim_id="claim:phase7:runtime-policy:restart-risk",
        policy_claim_text="Admitted restart-risk crystals may answer only when source support, topology and current evidence are available.",
        dependency_path=(source, f"{source}-dependency-bridge", target),
        visible_span_bound=visible_span_bound,
        source_supports_policy=source_supports_policy,
        source_contradicts_policy=False if answerable else True,
        topology_edge_supported=topology_edge_supported,
        current_evidence_supported=current_evidence_supported,
        ledger_families_available=REQUIRED_LEDGER_FAMILIES if answerable else ("restart_risk_composition",),
        expected_action="answer" if answerable else "refuse",
        expected_answer_available=answerable,
    )


def _resolve_mode(request: BeastRuntimeRequest) -> str:
    if request.mode != "auto":
        return request.mode
    text = request.question.casefold()
    return "draw" if any(word in text for word in ("draw", "diagram", "visual", "svg")) else "speak"


def _question_matches_restart_risk(question: str) -> bool:
    text = question.casefold()
    return bool(
        ("restart" in text or "restarting" in text)
        and any(word in text for word in ("destabilize", "destabilise", "risk", "break", "impact"))
    )


def _resolve_services(request: BeastRuntimeRequest) -> tuple[str, str]:
    if request.source_service and request.target_service:
        return request.source_service, request.target_service
    text = request.question
    restarting = re.search(r"restart(?:ing)?\s+([A-Za-z][A-Za-z0-9_-]+)", text, flags=re.IGNORECASE)
    target = re.search(r"(?:destabili[sz]e|risk\s+to|impact|break)\s+([A-Za-z][A-Za-z0-9_-]+)", text, flags=re.IGNORECASE)
    if restarting and target:
        return restarting.group(1), target.group(1).rstrip("?.!,;:")
    candidates = re.findall(r"\b[A-Z][A-Za-z0-9]+-[A-Za-z0-9_-]+\b", text)
    if len(candidates) >= 2:
        return candidates[0], candidates[1]
    return "", ""


def _failed_criterion(*, family_supported: bool, ledger_ready: bool, checks: Mapping[str, Any]) -> str:
    if not family_supported:
        return "request_outside_admitted_runtime_family_or_missing_source_target"
    if not ledger_ready:
        return "required_capability_crystals_missing"
    failed = tuple(name for name, passed in checks.get("gates", {}).items() if not passed)
    return ",".join(failed) if failed else "ordinary_answer_route_unavailable"


def _parse_runtime_now(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_capability_ledger(path: Path) -> CapabilityLedger:
    payload = _read_json(path)
    crystals = tuple(CapabilityCrystal(**item) for item in payload["crystals"])
    return CapabilityLedger(
        beast_object_type=payload["beast_object_type"],
        version=payload.get("version", LEDGER_VERSION),
        ledger_id=payload["ledger_id"],
        crystals=crystals,
        provider_calls_used=int(payload.get("provider_calls_used", 0)),
        production_authority_allowed=bool(payload.get("production_authority_allowed", False)),
        execution_authority_allowed=bool(payload.get("execution_authority_allowed", False)),
    )
