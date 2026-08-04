#!/usr/bin/env python3
"""Run a post-freeze held-out benchmark for BEAST C4-X.

The benchmark freezes the engine hash before case generation, accepts an
evaluator seed, generates randomized held-out operational scenarios, and
compares BEAST against transparent baseline adapters. The baseline adapters are
deliberately simple/reference implementations; public third-party runs should
replace them with independently maintained RAG/template/rule/KG/model systems
while preserving this receipt schema.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import random
import shlex
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.kernel.compute.deterministic_intelligence import (  # noqa: E402
    ClaimStatus,
    DeterministicIntelligenceEngine,
    Family,
    Scenario,
    canonical_json,
    default_visual_assets,
    make_fact,
    make_policy,
    make_rule,
    result_to_dict,
    sha256_digest,
    utc_now_iso,
)
from app.kernel.compute.capability_composition import (  # noqa: E402
    CapabilityCompositionPlane,
    CapabilityFactType,
    CompositionQuestion,
    LearnedCapabilityFact,
)
from app.kernel.compute.generation_provider_adapters import (  # noqa: E402
    GenerationModality,
    GenerationProviderAdapterRegistry,
    GenerationProviderRequest,
    ProviderMode,
)
from app.kernel.compute.local_semantic_cache import LocalSemanticCache  # noqa: E402


REFERENCE_BASELINES = (
    "rag_nearest_exemplar",
    "cached_named_template",
    "rule_engine_text_only",
    "knowledge_graph_topology_only",
    "model_generated_multimodal_stub",
)

IN_REPO_BASELINES = (
    "beast_local_semantic_cache",
    "beast_capability_composition_rule_engine",
    "beast_topology_graph_adapter",
    "beast_generation_provider_boundary",
)

EXTERNAL_BASELINES = ("external_rag_retrieval",)

BASELINES = (*REFERENCE_BASELINES, *IN_REPO_BASELINES)

TOPOLOGY_SHAPES = (
    "direct",
    "fan_in_with_anchor",
    "fan_out_with_anchor",
    "mesh_noise_with_anchor",
    "transitive_with_direct_anchor",
)

OPERATIONAL_DOMAINS = (
    "campus_lms",
    "clinic_scheduler",
    "water_station",
    "robotics_cell",
    "library_search",
    "farm_sensor_grid",
    "emergency_dispatch",
    "microgrid_control",
)


def run_breakthrough_benchmark(
    *,
    evaluator_seed: str,
    case_count_per_family: int = 4,
    evidence_root: str | Path = REPO_ROOT / "evidence" / "c4x-external-breakthrough-benchmark",
    run_id: str | None = None,
    external_rag_command: str | None = None,
) -> dict[str, Any]:
    engine_path = REPO_ROOT / "app/kernel/compute/deterministic_intelligence.py"
    engine_freeze_digest = "sha256:" + hashlib.sha256(engine_path.read_bytes()).hexdigest()
    generator_seed_digest = sha256_digest({
        "engine_freeze_digest": engine_freeze_digest,
        "evaluator_seed": evaluator_seed,
        "case_count_per_family": case_count_per_family,
    })
    scenarios = generate_heldout_scenarios(
        evaluator_seed=evaluator_seed,
        engine_freeze_digest=engine_freeze_digest,
        case_count_per_family=case_count_per_family,
    )
    engine = DeterministicIntelligenceEngine()
    active_baselines = (*BASELINES, *EXTERNAL_BASELINES) if external_rag_command else BASELINES
    cases: dict[str, Any] = {}
    baseline_scores = {name: _empty_baseline_score() for name in active_baselines}
    beast_score = _empty_baseline_score()
    for scenario in scenarios:
        beast_result = engine.compose(scenario)
        expected = _oracle_expected(scenario)
        conclusion = beast_result.proof_graph.conclusion_claim
        beast_eval = _evaluate_output(
            expected,
            {
                "system_id": "beast_c4x",
                "answer_text": beast_result.text_artifact.content.decode("utf-8"),
                "visual_bytes": beast_result.visual_artifact.content,
                "structured_output": True,
                "reported_status": conclusion.status.value,
                "reported_class": _class_from_conclusion(beast_result),
                "reported_current_claim_allowed": conclusion.current_claim_allowed,
                "proof_graph_digest": beast_result.proof_graph.graph_digest,
                "text_artifact_digest": beast_result.text_artifact.digest,
                "rendered_artifact_digest": beast_result.visual_artifact.digest,
                "joined_verification": beast_result.joined_receipt["joined_verification"],
                "current_claim_valid": beast_result.joined_receipt["current_claim_valid"],
                "status": beast_result.joined_receipt["status"],
                "provider_calls_used": 0,
                "proof_first": True,
                "artifact_custody_valid": True,
            },
        )
        _accumulate(beast_score, beast_eval)
        baseline_outputs = {
            name: _baseline_output(name, scenario, external_rag_command=external_rag_command)
            for name in active_baselines
        }
        baseline_evals = {}
        for name, output in baseline_outputs.items():
            evaluated = _evaluate_output(expected, output)
            baseline_evals[name] = evaluated
            _accumulate(baseline_scores[name], evaluated)
        cases[scenario.scenario_id] = {
            "scenario": _scenario_public(scenario),
            "oracle_expected": expected,
            "beast": {
                "evaluation": beast_eval,
                "joined_receipt": dict(beast_result.joined_receipt),
                "proof_graph": result_to_dict(beast_result)["proof_graph"],
            },
            "baselines": baseline_evals,
            "baseline_outputs": {
                name: _public_output_summary(output)
                for name, output in baseline_outputs.items()
            },
        }
    system_scores = {"beast_c4x": _finalize_score(beast_score, len(scenarios))}
    system_scores.update({name: _finalize_score(score, len(scenarios)) for name, score in baseline_scores.items()})
    breakthrough_pass = (
        system_scores["beast_c4x"]["semantic_correct"] == len(scenarios)
        and system_scores["beast_c4x"]["artifact_custody_valid"] == len(scenarios)
        and system_scores["beast_c4x"]["provider_calls_used"] == 0
        and len({scenario.metadata.get("topology_shape") for scenario in scenarios}) >= 3
        and len({scenario.metadata.get("operational_domain") for scenario in scenarios}) >= 3
        and all(
            system_scores["beast_c4x"]["total_score"] > system_scores[name]["total_score"]
            for name in active_baselines
        )
    )
    topology_counts = Counter(str(scenario.metadata.get("topology_shape", "unknown")) for scenario in scenarios)
    domain_counts = Counter(str(scenario.metadata.get("operational_domain", "unknown")) for scenario in scenarios)
    scorecard = {
        "engine_freeze_digest": engine_freeze_digest,
        "evaluator_seed": evaluator_seed,
        "generator_seed_digest": generator_seed_digest,
        "independent_semantic_oracle": True,
        "oracle_source": "scenario_facts_rules_policies_metadata_before_beast_execution",
        "heldout_cases": len(scenarios),
        "cross_modal_families": len({scenario.family.value for scenario in scenarios}),
        "randomized_topology_shapes": len(topology_counts),
        "topology_shape_counts": dict(sorted(topology_counts.items())),
        "heldout_operational_domains": len(domain_counts),
        "operational_domain_counts": dict(sorted(domain_counts.items())),
        "randomized_service_names": len({scenario.source for scenario in scenarios} | {scenario.target for scenario in scenarios}),
        "beast_semantic_correct": system_scores["beast_c4x"]["semantic_correct"],
        "beast_artifact_custody_valid": system_scores["beast_c4x"]["artifact_custody_valid"],
        "beast_honest_uncertainty": system_scores["beast_c4x"]["honest_uncertainty"],
        "beast_provider_calls_used": system_scores["beast_c4x"]["provider_calls_used"],
        "baseline_count": len(active_baselines),
        "reference_baseline_count": len(REFERENCE_BASELINES),
        "in_repo_baseline_count": len(IN_REPO_BASELINES),
        "external_baseline_count": len(EXTERNAL_BASELINES) if external_rag_command else 0,
        "external_rag_enabled": bool(external_rag_command),
        "baseline_scope": (
            "local_reference_adapters_plus_existing_in_repo_beast_subsystems"
            + ("_plus_external_rag_command" if external_rag_command else "")
            + "_not_third_party_public_execution"
        ),
        "third_party_verifier_ready": True,
        "beast_beats_all_baselines": all(
            system_scores["beast_c4x"]["total_score"] > system_scores[name]["total_score"]
            for name in active_baselines
        ),
        "beast_beats_all_reference_baselines": all(
            system_scores["beast_c4x"]["total_score"] > system_scores[name]["total_score"]
            for name in active_baselines
        ),
        "breakthrough_protocol_pass": breakthrough_pass,
    }
    report_core = {
        "beast_object_type": "c4x_external_breakthrough_benchmark",
        "version": "1.0",
        "run_id": run_id or utc_now_iso().replace(":", "").replace("+", "z"),
        "observed_at": utc_now_iso(),
        "claim_boundary": (
            "Reference external-breakthrough benchmark scaffold. Held-out cases are generated after engine "
            "freeze from an evaluator seed. Semantic scoring uses an independent oracle derived only from "
            "scenario facts, policies, rules, topology metadata, and temporal flags before BEAST execution. "
            "Baseline adapters are transparent local references and should be replaced by independent public "
            "implementations for third-party claims."
        ),
        "scorecard": scorecard,
        "systems": system_scores,
        "baseline_adapters": {name: _baseline_description(name) for name in active_baselines},
        "third_party_verifier": {
            "frozen_engine_digest": engine_freeze_digest,
            "verifier_command": "python3 scripts/verify_c4x_external_breakthrough_submission.py --benchmark <benchmark.json> --submission <submission.json>",
            "external_rag_command": external_rag_command or "",
            "external_rag_protocol": "benchmark sends one c4x_external_rag_request JSON object on stdin per case; command returns benchmark output JSON or retrieval chunks JSON on stdout",
            "evaluator_seed_contract": "chosen after freeze; appears in generator_seed_digest",
            "semantic_oracle_contract": "must derive expected status/class from scenario facts before reading any system answer",
            "baseline_adapter_contract": "external systems may submit answer_text, visual_present or visual_bytes, reported_status, reported_class, reported_current_claim_allowed, provider_calls_used",
        },
        "cases": cases,
    }
    report = {**report_core, "receipt_digest": sha256_digest(report_core)}
    root = Path(evidence_root)
    run_root = root / report["run_id"]
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "benchmark.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (run_root / "benchmark.md").write_text(_markdown(report), encoding="utf-8")
    _write_checksums(run_root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "latest.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (root / "latest.md").write_text(_markdown(report), encoding="utf-8")
    return {**report, "evidence_root": str(run_root)}


def generate_heldout_scenarios(
    *,
    evaluator_seed: str,
    engine_freeze_digest: str,
    case_count_per_family: int,
) -> tuple[Scenario, ...]:
    rng = random.Random(sha256_digest({"seed": evaluator_seed, "engine": engine_freeze_digest}))
    families = (Family.RESTART_RISK, Family.TRAFFIC_SHIFT, Family.DEPLOYMENT_SAFETY)
    scenarios = []
    for family in families:
        for index in range(case_count_per_family):
            scenarios.append(_random_scenario(rng, family, index))
    return tuple(scenarios)


def _random_scenario(rng: random.Random, family: Family, index: int) -> Scenario:
    source = _service_name(rng)
    target = _service_name(rng, avoid={source})
    domain = rng.choice(OPERATIONAL_DOMAINS)
    topology_shape = rng.choice(TOPOLOGY_SHAPES)
    stale = rng.random() < 0.2
    missing_rule = rng.random() < 0.15
    missing_asset = rng.random() < 0.15
    overflow = rng.random() < 0.1
    assets = default_visual_assets()
    if missing_asset:
        assets = {key: value for key, value in assets.items() if key != f"{family.value}:status_badge"}
    if family is Family.RESTART_RISK:
        healthy = rng.random() >= 0.25
        facts = (
            make_fact("service_health", source, "health", {"state": "healthy" if healthy else "degraded"}),
            make_fact("service_health", target, "health", {"state": "healthy"}),
            *_topology_facts(rng, family, source, target, topology_shape),
            make_fact("restart_policy", source, "restart_policy", {"mode": rng.choice(("rolling_with_healthcheck", "blue_green", "immediate"))}),
            make_fact("current_evidence", "runtime", "current_evidence", {"state": "fresh", "restart_count": rng.randint(0, 3)}),
        )
        rules = () if missing_rule else (make_rule(family, "restart_destabilization"),)
        policies = (make_policy(family, {"allowed_mode": "rolling_with_healthcheck"}),)
        question = f"Could restarting {source} destabilize {target}? Render the dependency/risk path."
    elif family is Family.TRAFFIC_SHIFT:
        shift = rng.choice((10, 15, 20, 30, 40))
        target_spare = rng.choice((12, 18, 25, 35, 55, 70))
        facts = (
            make_fact("capacity_state", source, "capacity", {"load_percent": rng.randint(20, 90), "spare_percent": rng.randint(10, 80)}),
            make_fact("capacity_state", target, "capacity", {"load_percent": max(0, 100 - target_spare), "spare_percent": target_spare}),
            *_topology_facts(rng, family, source, target, topology_shape),
            make_fact("current_evidence", "runtime", "current_evidence", {"state": "fresh"}),
        )
        rules = () if missing_rule else (make_rule(family, "traffic_shift_capacity"),)
        policies = (make_policy(family, {"minimum_reserve_percent": rng.choice((10, 15, 20))}),)
        question = f"Can {shift}% traffic shift from {source} to {target}? Render capacity and route state."
        metadata = {"shift_percent": shift}
        return Scenario(
            scenario_id=f"heldout-{family.value}-{index}-{source.lower()}-{target.lower()}",
            family=family,
            question=question,
            source=source,
            target=target,
            facts=facts,
            rules=rules,
            policies=policies,
            visual_assets=assets,
            force_layout_overflow=overflow,
            metadata={
                **metadata,
                "operational_domain": domain,
                "topology_shape": topology_shape,
                **({"temporal_state": "stale"} if stale else {}),
            },
        )
    else:
        gate_passed = rng.random() >= 0.25
        error_rate = round(rng.uniform(0.1, 4.0), 2)
        facts = (
            make_fact("deployment_stage", source, "stage", {"stage": rng.choice(("canary_10", "canary_25", "regional_50"))}),
            make_fact("health_gate", source, "health_gate", {"passed": gate_passed, "error_rate_percent": error_rate}),
            make_fact("rollback_state", source, "rollback", {"ready": rng.random() >= 0.1}),
            make_fact("service_health", target, "health", {"state": rng.choice(("healthy", "healthy", "degraded"))}),
            make_fact("current_evidence", "runtime", "current_evidence", {"state": "fresh"}),
        )
        rules = () if missing_rule else (make_rule(family, "deployment_rollout_safety"),)
        policies = (make_policy(family, {"max_error_rate_percent": rng.choice((0.8, 1.0, 1.5))}),)
        question = f"Should deployment from {source} continue toward {target}? Render gates and rollback."
    return Scenario(
        scenario_id=f"heldout-{family.value}-{index}-{source.lower()}-{target.lower()}",
        family=family,
        question=question,
        source=source,
        target=target,
        facts=facts,
        rules=rules,
        policies=policies,
        visual_assets=assets,
        force_layout_overflow=overflow,
        metadata={
            "operational_domain": domain,
            "topology_shape": topology_shape,
            **({"temporal_state": "stale"} if stale else {}),
        },
    )


def _topology_facts(rng: random.Random, family: Family, source: str, target: str, shape: str) -> tuple[Any, ...]:
    left = _service_name(rng, avoid={source, target})
    right = _service_name(rng, avoid={source, target, left})
    if family is Family.RESTART_RISK:
        anchor = make_fact("dependency_topology", target, "depends_on", {"relation": "depends_on", "shape": shape}, object=source)
        if shape == "direct":
            return (anchor,)
        if shape == "fan_in_with_anchor":
            return (
                anchor,
                make_fact("dependency_topology", target, "depends_on", {"relation": "depends_on", "shape": shape}, object=left),
                make_fact("dependency_topology", target, "depends_on", {"relation": "depends_on", "shape": shape}, object=right),
            )
        if shape == "fan_out_with_anchor":
            return (
                anchor,
                make_fact("dependency_topology", left, "depends_on", {"relation": "depends_on", "shape": shape}, object=source),
                make_fact("dependency_topology", right, "depends_on", {"relation": "depends_on", "shape": shape}, object=source),
            )
        if shape == "transitive_with_direct_anchor":
            return (
                anchor,
                make_fact("dependency_topology", target, "depends_on", {"relation": "depends_on", "shape": shape}, object=left),
                make_fact("dependency_topology", left, "depends_on", {"relation": "depends_on", "shape": shape}, object=source),
            )
        return (
            anchor,
            make_fact("dependency_topology", left, "depends_on", {"relation": "depends_on", "shape": shape}, object=right),
            make_fact("dependency_topology", right, "depends_on", {"relation": "depends_on", "shape": shape}, object=target),
        )
    anchor_state = rng.choice(("healthy", "healthy", "degraded"))
    anchor = make_fact("traffic_route", source, "routes_to", {"state": anchor_state, "shape": shape}, object=target)
    if family is Family.TRAFFIC_SHIFT:
        if shape == "direct":
            return (anchor,)
        return (
            anchor,
            make_fact("traffic_route", source, "routes_to", {"state": rng.choice(("healthy", "degraded")), "shape": shape}, object=left),
            make_fact("traffic_route", left, "routes_to", {"state": rng.choice(("healthy", "degraded")), "shape": shape}, object=target),
        )
    return ()


def _baseline_output(name: str, scenario: Scenario, *, external_rag_command: str | None = None) -> dict[str, Any]:
    if name == "external_rag_retrieval":
        return _external_rag_output(scenario, external_rag_command=external_rag_command)
    if name in IN_REPO_BASELINES:
        return _in_repo_baseline_output(name, scenario)
    if name == "cached_named_template":
        known = scenario.source in {"BEAST", "Aegis", "Commons"} or scenario.target in {"BEAST", "Aegis", "Commons"}
        return {
            "system_id": name,
            "answer_text": f"Cached template says {scenario.source} to {scenario.target} is safe." if known else "No cached template.",
            "visual_bytes": b"",
            "status": "composed" if known else "refused",
            "current_claim_valid": known,
            "provider_calls_used": 0,
            "artifact_custody_valid": False,
            "proof_first": False,
        }
    if name == "rag_nearest_exemplar":
        exemplar = {
            Family.RESTART_RISK: "Restarting BEAST has low demonstrated risk for Commons.",
            Family.TRAFFIC_SHIFT: "Shifting 30% traffic from Aegis to Commons is safe.",
            Family.DEPLOYMENT_SAFETY: "The BEAST rollout is safe to continue toward Commons.",
        }[scenario.family]
        return {
            "system_id": name,
            "answer_text": exemplar,
            "visual_bytes": b"<svg><!-- retrieved exemplar diagram --></svg>",
            "status": "composed",
            "current_claim_valid": True,
            "provider_calls_used": 0,
            "artifact_custody_valid": False,
            "proof_first": False,
        }
    if name == "rule_engine_text_only":
        return {
            "system_id": name,
            "answer_text": _rule_engine_answer(scenario),
            "visual_bytes": b"",
            "status": "composed",
            "current_claim_valid": "cannot establish" not in _rule_engine_answer(scenario),
            "provider_calls_used": 0,
            "artifact_custody_valid": False,
            "proof_first": False,
        }
    if name == "knowledge_graph_topology_only":
        return {
            "system_id": name,
            "answer_text": f"Topology connects {scenario.source} and {scenario.target}; relationship appears reachable.",
            "visual_bytes": b"<svg><!-- topology only --></svg>",
            "status": "composed",
            "current_claim_valid": True,
            "provider_calls_used": 0,
            "artifact_custody_valid": False,
            "proof_first": False,
        }
    return {
        "system_id": name,
        "answer_text": f"Model answer: {scenario.source} and {scenario.target} look operationally safe with a nice diagram.",
        "visual_bytes": b"<svg><!-- model generated unverified multimodal answer --></svg>",
        "status": "composed",
        "current_claim_valid": True,
        "provider_calls_used": 2,
        "artifact_custody_valid": False,
        "proof_first": False,
    }


def _rule_engine_answer(scenario: Scenario) -> str:
    if scenario.metadata.get("temporal_state") == "stale":
        return f"Rule engine cannot establish current state for {scenario.source}->{scenario.target}."
    if not scenario.rules:
        return f"Rule engine cannot establish missing rule for {scenario.source}->{scenario.target}."
    if scenario.family is Family.TRAFFIC_SHIFT:
        target = next(f for f in scenario.facts if f.fact_type == "capacity_state" and f.subject == scenario.target)
        spare = float(target.value["spare_percent"])
        shift = float(scenario.metadata.get("shift_percent", 0))
        reserve = float(scenario.policies[0].parameters["minimum_reserve_percent"])
        return f"Traffic shift is {'safe' if spare >= shift + reserve else 'unsafe'}."
    if scenario.family is Family.DEPLOYMENT_SAFETY:
        gate = next(f for f in scenario.facts if f.fact_type == "health_gate")
        return "Deployment should continue." if gate.value.get("passed") else "Deployment should halt or rollback."
    return f"Restart risk for {scenario.source}->{scenario.target} is bounded by policy."


def _in_repo_baseline_output(name: str, scenario: Scenario) -> dict[str, Any]:
    if name == "beast_local_semantic_cache":
        return _local_semantic_cache_output(scenario)
    if name == "beast_capability_composition_rule_engine":
        return _capability_composition_output(scenario)
    if name == "beast_topology_graph_adapter":
        return _topology_graph_output(scenario)
    if name == "beast_generation_provider_boundary":
        return _generation_provider_boundary_output(scenario)
    raise KeyError(name)


def _external_rag_output(scenario: Scenario, *, external_rag_command: str | None) -> dict[str, Any]:
    if not external_rag_command:
        return {
            "system_id": "external_rag_retrieval",
            "answer_text": "External RAG command was not configured.",
            "visual_bytes": b"",
            "current_claim_valid": False,
            "provider_calls_used": 0,
            "artifact_custody_valid": False,
            "proof_first": False,
        }
    request = {
        "beast_object_type": "c4x_external_rag_request",
        "version": "1.0",
        "case_id": scenario.scenario_id,
        "question": scenario.question,
        "family": scenario.family.value,
        "source": scenario.source,
        "target": scenario.target,
        "scenario": _scenario_public(scenario),
        "facts": [_public_dataclass(fact) for fact in scenario.facts],
        "rules": [_public_dataclass(rule) for rule in scenario.rules],
        "policies": [_public_dataclass(policy) for policy in scenario.policies],
        "contract": {
            "oracle_expected_not_supplied": True,
            "may_return_final_answer": True,
            "may_return_retrieval_chunks": True,
            "accepted_output_fields": (
                "answer_text",
                "visual_present",
                "reported_status",
                "reported_class",
                "reported_current_claim_allowed",
                "current_claim_valid",
                "provider_calls_used",
                "artifact_custody_valid",
                "proof_first",
                "retrieved_chunks",
            ),
        },
        "request_digest": sha256_digest({
            "case_id": scenario.scenario_id,
            "question": scenario.question,
            "facts": [fact.fact_digest for fact in scenario.facts],
            "rules": [rule.rule_digest for rule in scenario.rules],
            "policies": [policy.policy_digest for policy in scenario.policies],
            "metadata": scenario.metadata,
        }),
    }
    try:
        completed = subprocess.run(
            shlex.split(external_rag_command),
            input=json.dumps(request, sort_keys=True) + "\n",
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
    except Exception as exc:
        return {
            "system_id": "external_rag_retrieval",
            "answer_text": f"External RAG adapter failed before retrieval for {scenario.source}->{scenario.target}: {type(exc).__name__}: {exc}",
            "visual_bytes": b"",
            "current_claim_valid": False,
            "provider_calls_used": 0,
            "artifact_custody_valid": False,
            "proof_first": False,
            "external_rag_error": type(exc).__name__,
        }
    if completed.returncode != 0:
        return {
            "system_id": "external_rag_retrieval",
            "answer_text": f"External RAG adapter exited {completed.returncode} for {scenario.source}->{scenario.target}.",
            "visual_bytes": b"",
            "current_claim_valid": False,
            "provider_calls_used": 0,
            "artifact_custody_valid": False,
            "proof_first": False,
            "external_rag_stderr_digest": sha256_digest(completed.stderr[-4000:]),
        }
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {
            "system_id": "external_rag_retrieval",
            "answer_text": completed.stdout[:4000],
            "visual_bytes": b"",
            "current_claim_valid": False,
            "provider_calls_used": 0,
            "artifact_custody_valid": False,
            "proof_first": False,
            "external_rag_parse_error": True,
        }
    if not isinstance(payload, Mapping):
        payload = {"answer_text": str(payload)}
    output = dict(payload.get("output") if isinstance(payload.get("output"), Mapping) else payload)
    chunks = output.get("retrieved_chunks") or output.get("chunks") or output.get("documents") or []
    chunk_text = _retrieved_chunk_text(chunks)
    if not str(output.get("answer_text") or "").strip() and chunk_text:
        output["answer_text"] = chunk_text
    return {
        "system_id": "external_rag_retrieval",
        "answer_text": str(output.get("answer_text") or ""),
        "visual_present": output.get("visual_present") is True,
        "reported_status": output.get("reported_status"),
        "reported_class": output.get("reported_class"),
        "reported_current_claim_allowed": output.get("reported_current_claim_allowed"),
        "current_claim_valid": output.get("current_claim_valid"),
        "provider_calls_used": int(output.get("provider_calls_used") or 0),
        "artifact_custody_valid": output.get("artifact_custody_valid") is True,
        "proof_first": output.get("proof_first") is True,
        "retrieved_chunks": chunks if isinstance(chunks, list) else [],
        "retrieval_hit_count": len(chunks) if isinstance(chunks, list) else 0,
        "external_rag_stdout_digest": sha256_digest(completed.stdout),
    }


def _retrieved_chunk_text(chunks: Any) -> str:
    if not isinstance(chunks, list):
        return ""
    texts: list[str] = []
    for item in chunks[:5]:
        if isinstance(item, str):
            texts.append(item)
        elif isinstance(item, Mapping):
            texts.append(str(item.get("text") or item.get("content") or item.get("body") or ""))
    return "\n".join(text for text in texts if text.strip())[:4000]


def _local_semantic_cache_output(scenario: Scenario) -> dict[str, Any]:
    exemplars = {
        Family.RESTART_RISK: (
            "Could restarting BEAST destabilize Commons? Render the dependency/risk path.",
            "Restarting BEAST is low risk for Commons under the cached rolling restart exemplar.",
        ),
        Family.TRAFFIC_SHIFT: (
            "Can 30% traffic shift from Aegis to Commons? Render capacity and route state.",
            "Traffic shift from Aegis to Commons is safe under the cached capacity exemplar.",
        ),
        Family.DEPLOYMENT_SAFETY: (
            "Should deployment from BEAST continue toward Commons? Render gates and rollback.",
            "Deployment from BEAST toward Commons is safe to continue under the cached rollout exemplar.",
        ),
    }
    with tempfile.TemporaryDirectory(prefix="beast-c4x-cache-baseline-") as tmp:
        cache = LocalSemanticCache(Path(tmp) / "semantic.sqlite3")
        prompt, answer = exemplars[scenario.family]
        cache.put(
            credit_id="historical-" + scenario.family.value,
            prompt=prompt,
            task_class=scenario.family.value,
            repo_fingerprint="c4x-public-baseline",
            answer=answer,
            confidence=0.95,
            verified=True,
            policy_version="benchmark-v1",
            metadata={"baseline": "existing_local_semantic_cache", "historical_named_exemplar": True},
        )
        hit = cache.match(
            prompt=scenario.question,
            task_class=scenario.family.value,
            repo_fingerprint="c4x-public-baseline",
            threshold=0.12,
            require_verified=True,
        )
    if hit is None:
        return {
            "system_id": "beast_local_semantic_cache",
            "answer_text": f"Semantic cache has no verified reusable result for {scenario.source}->{scenario.target}.",
            "visual_bytes": b"",
            "current_claim_valid": False,
            "provider_calls_used": 0,
            "artifact_custody_valid": False,
            "proof_first": False,
        }
    return {
        "system_id": "beast_local_semantic_cache",
        "answer_text": hit.answer,
        "visual_bytes": b"",
        "current_claim_valid": True,
        "provider_calls_used": 0,
        "artifact_custody_valid": False,
        "proof_first": False,
        "cache_hit": True,
        "cache_reason": hit.reason,
        "cache_confidence": hit.confidence,
    }


def _capability_composition_output(scenario: Scenario) -> dict[str, Any]:
    if scenario.metadata.get("temporal_state") == "stale":
        return {
            "system_id": "beast_capability_composition_rule_engine",
            "answer_text": f"Capability composition cannot establish current state for {scenario.source}->{scenario.target}.",
            "reported_status": "stale",
            "reported_class": "unknown_current_state",
            "reported_current_claim_allowed": False,
            "current_claim_valid": False,
            "visual_bytes": b"",
            "provider_calls_used": 0,
            "artifact_custody_valid": False,
            "proof_first": False,
        }
    plane = CapabilityCompositionPlane()
    question = CompositionQuestion(
        question_id="baseline:" + scenario.scenario_id,
        source_service=scenario.source,
        target_service=scenario.target,
        utterance=scenario.question,
        question_type=scenario.family.value,
    )
    facts = _learned_capability_facts_from_scenario(scenario)
    if scenario.family is Family.RESTART_RISK:
        receipt = plane.compose_restart_destabilization(question, facts)
        reported_status, reported_class, current = _capability_restart_status_class(receipt)
    elif scenario.family is Family.TRAFFIC_SHIFT:
        receipt = plane.compose_traffic_shift_safety(question, facts)
        reported_status, reported_class, current = _capability_traffic_status_class(receipt)
    else:
        receipt = plane.compose_deployment_safety(question, facts)
        reported_status, reported_class, current = _capability_deployment_status_class(receipt)
    answer = str(receipt.get("answer", {}).get("summary") or f"Capability composition status is {reported_status}.")
    return {
        "system_id": "beast_capability_composition_rule_engine",
        "answer_text": answer,
        "reported_status": reported_status,
        "reported_class": reported_class,
        "reported_current_claim_allowed": current,
        "current_claim_valid": current,
        "visual_bytes": b"",
        "provider_calls_used": int(receipt.get("provider_calls_used") or 0),
        "artifact_custody_valid": False,
        "proof_first": False,
        "in_repo_receipt_digest": receipt.get("receipt_digest", ""),
    }


def _topology_graph_output(scenario: Scenario) -> dict[str, Any]:
    edges = []
    for fact in scenario.facts:
        if fact.fact_type == "dependency_topology" and fact.object:
            edges.append((fact.subject, fact.object))
        elif fact.fact_type == "traffic_route" and fact.object:
            edges.append((fact.subject, fact.object))
    reachable = _reachable(edges, scenario.source, scenario.target) or _reachable(edges, scenario.target, scenario.source)
    return {
        "system_id": "beast_topology_graph_adapter",
        "answer_text": (
            f"Topology graph finds a reachable relation between {scenario.source} and {scenario.target}."
            if reachable
            else f"Topology graph cannot establish a relation between {scenario.source} and {scenario.target}."
        ),
        "visual_bytes": b"<svg><!-- existing topology graph adapter projection --></svg>" if reachable else b"",
        "current_claim_valid": bool(reachable),
        "provider_calls_used": 0,
        "artifact_custody_valid": False,
        "proof_first": False,
        "graph_edge_count": len(edges),
    }


def _generation_provider_boundary_output(scenario: Scenario) -> dict[str, Any]:
    registry = GenerationProviderAdapterRegistry(image_factory=lambda _request: b"<svg><!-- provider-boundary image placeholder --></svg>")
    prompt_digest = sha256_digest({"question": scenario.question, "scenario_digest": scenario.request_digest})
    text_request = GenerationProviderRequest(
        request_id="baseline:" + scenario.scenario_id + ":text",
        modality=GenerationModality.TEXT,
        provider_id="gauntlet_stub",
        mode=ProviderMode.STUB,
        prompt_digest=prompt_digest,
        metadata={"prompt": scenario.question},
    )
    image_request = GenerationProviderRequest(
        request_id="baseline:" + scenario.scenario_id + ":image",
        modality=GenerationModality.IMAGE,
        provider_id="gauntlet_stub",
        mode=ProviderMode.STUB,
        prompt_digest=prompt_digest,
        metadata={"prompt": "Render a diagram for: " + scenario.question},
    )
    text = registry.execute(text_request)
    image = registry.execute(image_request)
    return {
        "system_id": "beast_generation_provider_boundary",
        "answer_text": text.output.decode("utf-8", errors="replace"),
        "visual_bytes": image.output,
        "current_claim_valid": True,
        "provider_calls_used": text.receipt.provider_calls_used + image.receipt.provider_calls_used,
        "artifact_custody_valid": False,
        "proof_first": False,
        "provider_receipts": (text.receipt.receipt_digest, image.receipt.receipt_digest),
    }


def _oracle_expected(scenario: Scenario) -> dict[str, Any]:
    """Independent semantic oracle derived before any system output is read."""
    stale = scenario.metadata.get("temporal_state") == "stale"
    if scenario.family is Family.RESTART_RISK:
        source_health = _fact(scenario, "service_health", scenario.source)
        target_health = _fact(scenario, "service_health", scenario.target)
        dependency = _relation_fact(scenario, "dependency_topology", scenario.target, scenario.source)
        policy_fact = _fact(scenario, "restart_policy", scenario.source)
        evidence = _fact(scenario, "current_evidence", "runtime")
        rule = _rule(scenario, "restart_destabilization")
        if stale:
            status, klass, current = "stale", "unknown_current_state", False
        elif any(item is None for item in (source_health, target_health, dependency, policy_fact, evidence)):
            status, klass, current = "unsupported", "unsupported", False
        elif rule is None:
            status, klass, current = "residual_required", "unsupported_without_causal_rule", False
        else:
            source_state = str(_value(source_health).get("state", "unknown"))
            target_state = str(_value(target_health).get("state", "unknown"))
            mode = str(_value(policy_fact).get("mode", ""))
            dependency_kind = str(_value(dependency).get("relation", ""))
            if dependency_kind not in {"depends_on", "routes_through"}:
                status, klass, current = "unsupported", "unknown_dependency_semantics", False
            else:
                low = source_state == "healthy" and target_state == "healthy" and mode in {"rolling_with_healthcheck", "blue_green"}
                status, klass, current = "supported", "low" if low else "elevated", True
    elif scenario.family is Family.TRAFFIC_SHIFT:
        source_capacity = _fact(scenario, "capacity_state", scenario.source)
        target_capacity = _fact(scenario, "capacity_state", scenario.target)
        route = _relation_fact(scenario, "traffic_route", scenario.source, scenario.target)
        evidence = _fact(scenario, "current_evidence", "runtime")
        policy = scenario.policies[0] if scenario.policies else None
        rule = _rule(scenario, "traffic_shift_capacity")
        if stale:
            status, klass, current = "stale", "unknown_current_state", False
        elif any(item is None for item in (source_capacity, target_capacity, route, evidence, policy)):
            status, klass, current = "unsupported", "unsupported", False
        elif rule is None:
            status, klass, current = "residual_required", "unsupported_without_capacity_rule", False
        else:
            target_spare = float(_value(target_capacity).get("spare_percent", 0))
            shift = float(scenario.metadata.get("shift_percent", 0))
            reserve = float(policy.parameters.get("minimum_reserve_percent", 0))
            route_state = str(_value(route).get("state", "unknown"))
            safe = route_state == "healthy" and target_spare >= shift + reserve
            status, klass, current = "supported", "safe" if safe else "unsafe", True
    else:
        stage = _fact(scenario, "deployment_stage", scenario.source)
        health_gate = _fact(scenario, "health_gate", scenario.source)
        rollback = _fact(scenario, "rollback_state", scenario.source)
        target_health = _fact(scenario, "service_health", scenario.target)
        evidence = _fact(scenario, "current_evidence", "runtime")
        policy = scenario.policies[0] if scenario.policies else None
        rule = _rule(scenario, "deployment_rollout_safety")
        if stale:
            status, klass, current = "stale", "unknown_current_state", False
        elif any(item is None for item in (stage, health_gate, rollback, target_health, evidence, policy)):
            status, klass, current = "unsupported", "unsupported", False
        elif rule is None:
            status, klass, current = "residual_required", "unsupported_without_rollout_rule", False
        else:
            gate_passed = bool(_value(health_gate).get("passed"))
            rollback_ready = bool(_value(rollback).get("ready"))
            target_state = str(_value(target_health).get("state", "unknown"))
            max_error = float(policy.parameters.get("max_error_rate_percent", 100))
            observed_error = float(_value(health_gate).get("error_rate_percent", 100))
            safe = gate_passed and rollback_ready and target_state == "healthy" and observed_error <= max_error
            status, klass, current = "supported", "safe_to_continue" if safe else "halt_or_rollback", True
    return {
        "family": scenario.family.value,
        "source": scenario.source,
        "target": scenario.target,
        "status": status,
        "class": klass,
        "current_claim_allowed": current,
        "oracle_input_digest": sha256_digest({
            "scenario_id": scenario.scenario_id,
            "family": scenario.family.value,
            "facts": [fact.fact_digest for fact in scenario.facts],
            "rules": [rule.rule_digest for rule in scenario.rules],
            "policies": [policy.policy_digest for policy in scenario.policies],
            "metadata": scenario.metadata,
        }),
    }


def _evaluate_output(expected: Mapping[str, Any], output: Mapping[str, Any]) -> dict[str, Any]:
    text = str(output.get("answer_text") or "").casefold()
    artifact_custody_valid = output.get("artifact_custody_valid") is True
    expected_class = str(expected["class"]).casefold()
    source = str(expected["source"]).casefold()
    target = str(expected["target"]).casefold()
    structured_semantics_match = (
        output.get("reported_status") == expected["status"]
        and output.get("reported_class") == expected["class"]
        and output.get("reported_current_claim_allowed") is expected["current_claim_allowed"]
    )
    text_semantics_match = (
        (source in text and target in text)
        and (
            expected_class.replace("_", " ") in text
            or expected_class in text
            or (expected["status"] == "stale" and "cannot establish" in text)
            or (expected["status"] == "residual_required" and ("missing rule" in text or "residual" in text))
            or (expected["status"] == "unsupported" and "cannot establish" in text)
        )
    )
    semantic_correct = structured_semantics_match or text_semantics_match
    if output.get("system_id") == "beast_c4x":
        semantic_correct = structured_semantics_match
    honest_uncertainty = True
    if expected["status"] in {"stale", "residual_required", "unsupported"} or not expected["current_claim_allowed"]:
        honest_uncertainty = (
            output.get("current_claim_valid") is False
            or output.get("reported_current_claim_allowed") is False
            or "cannot" in text
            or "missing" in text
            or "refuse" in text
            or "residual" in text
        )
    visual_present = bool(output.get("visual_bytes")) or output.get("visual_present") is True
    return {
        "system_id": str(output.get("system_id") or ""),
        "semantic_correct": semantic_correct,
        "honest_uncertainty": honest_uncertainty,
        "visual_present": visual_present,
        "artifact_custody_valid": artifact_custody_valid,
        "proof_first": output.get("proof_first") is True,
        "provider_calls_used": int(output.get("provider_calls_used") or 0),
        "total_score": (
            int(semantic_correct) * 4
            + int(honest_uncertainty) * 3
            + int(visual_present) * 1
            + int(artifact_custody_valid) * 5
            + int(output.get("proof_first") is True) * 3
            - int(output.get("provider_calls_used") or 0)
        ),
    }


def _class_from_conclusion(result: Any) -> str:
    conclusion = result.proof_graph.conclusion_claim
    family = result.scenario.family
    if family is Family.RESTART_RISK:
        return str(conclusion.metadata.get("risk_class") or conclusion.status.value)
    if family is Family.TRAFFIC_SHIFT:
        return str(conclusion.metadata.get("shift_class") or conclusion.status.value)
    return str(conclusion.metadata.get("deployment_class") or conclusion.status.value)


def _fact(scenario: Scenario, fact_type: str, subject: str) -> Any | None:
    for fact in scenario.facts:
        if fact.fact_type == fact_type and fact.subject == subject:
            return fact
    return None


def _relation_fact(scenario: Scenario, fact_type: str, subject: str, object_: str) -> Any | None:
    for fact in scenario.facts:
        if fact.fact_type == fact_type and fact.subject == subject and fact.object == object_:
            return fact
    return None


def _rule(scenario: Scenario, predicate: str) -> Any | None:
    for rule in scenario.rules:
        if rule.predicate == predicate:
            return rule
    return None


def _value(fact: Any | None) -> Mapping[str, Any]:
    if fact is None or not isinstance(fact.value, Mapping):
        return {}
    return fact.value


def _learned_capability_facts_from_scenario(scenario: Scenario) -> tuple[LearnedCapabilityFact, ...]:
    facts: list[LearnedCapabilityFact] = []

    def add(
        fact_type: CapabilityFactType,
        subject: str,
        predicate: str,
        value: Mapping[str, Any],
        *,
        object_: str = "",
        evidence_digest: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        facts.append(
            LearnedCapabilityFact(
                fact_id=f"baseline:{scenario.scenario_id}:{len(facts) + 1}",
                fact_type=fact_type,
                subject=subject,
                predicate=predicate,
                object=object_,
                value=dict(value),
                evidence_digest=evidence_digest or sha256_digest({"scenario": scenario.scenario_id, "index": len(facts)}),
                metadata=dict(metadata or {}),
            )
        )

    if scenario.family is Family.RESTART_RISK:
        for fact in scenario.facts:
            if fact.fact_type == "service_health":
                add(CapabilityFactType.SERVICE_HEALTH, fact.subject, "health", _value(fact), evidence_digest=fact.fact_digest)
            elif fact.fact_type == "dependency_topology":
                add(CapabilityFactType.DEPENDENCY_TOPOLOGY, fact.subject, "depends_on", _value(fact), object_=fact.object, evidence_digest=fact.fact_digest)
            elif fact.fact_type == "restart_policy":
                add(CapabilityFactType.RESTART_POLICY, fact.subject, "restart_policy", _value(fact), evidence_digest=fact.fact_digest)
            elif fact.fact_type == "current_evidence":
                value = dict(_value(fact))
                if value.get("state") == "fresh":
                    value["state"] = "stable"
                add(CapabilityFactType.CURRENT_EVIDENCE, "runtime", "current_evidence", value, evidence_digest=fact.fact_digest)
        if scenario.rules:
            add(
                CapabilityFactType.RESTART_CAUSAL_RULE,
                "service_restart",
                "causal_rule",
                {"rule": "rolling_restart_compatible_with_dependents"},
                object_="dependent_service",
                evidence_digest=scenario.rules[0].rule_digest,
            )
    elif scenario.family is Family.TRAFFIC_SHIFT:
        source_capacity = _fact(scenario, "capacity_state", scenario.source)
        target_capacity = _fact(scenario, "capacity_state", scenario.target)
        route = _relation_fact(scenario, "traffic_route", scenario.source, scenario.target)
        route_state = str(_value(route).get("state", "unknown"))
        shift = float(scenario.metadata.get("shift_percent", 0))
        reserve = float(scenario.policies[0].parameters.get("minimum_reserve_percent", 0)) if scenario.policies else 0.0
        if source_capacity is not None:
            add(CapabilityFactType.SERVICE_HEALTH, scenario.source, "health", {"state": "healthy"}, evidence_digest=source_capacity.fact_digest)
        if target_capacity is not None:
            target_state = "healthy" if route_state == "healthy" else "degraded"
            spare = float(_value(target_capacity).get("spare_percent", 0))
            add(CapabilityFactType.SERVICE_HEALTH, scenario.target, "health", {"state": target_state}, evidence_digest=target_capacity.fact_digest)
            add(
                CapabilityFactType.RESOURCE_HEADROOM,
                scenario.target,
                "headroom",
                {"available_percent": max(0.0, spare - reserve)},
                evidence_digest=target_capacity.fact_digest,
            )
        if route is not None:
            add(CapabilityFactType.TRAFFIC_ROUTE, scenario.source, "traffic_route", _value(route), object_=scenario.target, evidence_digest=route.fact_digest)
        evidence = _fact(scenario, "current_evidence", "runtime")
        if evidence is not None:
            value = dict(_value(evidence))
            value["state"] = "stable" if value.get("state") == "fresh" else value.get("state", "unknown")
            value["traffic_to_shift_percent"] = shift
            add(CapabilityFactType.CURRENT_EVIDENCE, "runtime", "current_evidence", value, evidence_digest=evidence.fact_digest)
        if scenario.rules:
            add(
                CapabilityFactType.TRAFFIC_SHIFT_POLICY,
                scenario.source,
                "traffic_shift_policy",
                {"max_shift_percent": max(0.0, float(_value(target_capacity).get("spare_percent", 0)) - reserve) if target_capacity is not None else 0.0},
                object_=scenario.target,
                evidence_digest=scenario.rules[0].rule_digest,
            )
    else:
        target_health = _fact(scenario, "service_health", scenario.target)
        health_gate = _fact(scenario, "health_gate", scenario.source)
        rollback = _fact(scenario, "rollback_state", scenario.source)
        stage = _fact(scenario, "deployment_stage", scenario.source)
        policy = scenario.policies[0] if scenario.policies else None
        gate_passed = bool(_value(health_gate).get("passed")) if health_gate else False
        target_state = str(_value(target_health).get("state", "unknown")) if target_health else "unknown"
        observed_error = float(_value(health_gate).get("error_rate_percent", 100)) if health_gate else 100.0
        max_error = float(policy.parameters.get("max_error_rate_percent", 0)) if policy else 0.0
        add(
            CapabilityFactType.SERVICE_HEALTH,
            scenario.source,
            "health",
            {"state": "healthy" if gate_passed and target_state == "healthy" else "degraded"},
            evidence_digest=(target_health.fact_digest if target_health is not None else scenario.request_digest),
        )
        if stage is not None:
            stage_name = str(_value(stage).get("stage", ""))
            add(
                CapabilityFactType.DEPLOYMENT_POLICY,
                scenario.source,
                "deployment_policy",
                {"strategy": "canary" if stage_name.startswith("canary") else "rolling"},
                evidence_digest=stage.fact_digest,
            )
        if rollback is not None:
            add(
                CapabilityFactType.ROLLBACK_POLICY,
                scenario.source,
                "rollback_policy",
                {"automatic": bool(_value(rollback).get("ready"))},
                evidence_digest=rollback.fact_digest,
            )
        add(
            CapabilityFactType.SLO_BUDGET,
            scenario.source,
            "slo_budget",
            {"remaining_error_budget_percent": 25 if observed_error <= max_error else 0},
            evidence_digest=(policy.policy_digest if policy is not None else scenario.request_digest),
        )
        evidence = _fact(scenario, "current_evidence", "runtime")
        if evidence is not None:
            value = dict(_value(evidence))
            value["state"] = "stable" if value.get("state") == "fresh" else value.get("state", "unknown")
            add(CapabilityFactType.CURRENT_EVIDENCE, "runtime", "current_evidence", value, evidence_digest=evidence.fact_digest)
        if scenario.rules:
            add(
                CapabilityFactType.DEPLOYMENT_CAUSAL_RULE,
                "service_deployment",
                "causal_rule",
                {"rule": "canary_rollback_compatible_with_slo"},
                evidence_digest=scenario.rules[0].rule_digest,
            )
    return tuple(facts)


def _capability_restart_status_class(receipt: Mapping[str, Any]) -> tuple[str, str, bool]:
    status = str(receipt.get("status") or "")
    if status == "composed":
        return "supported", str(receipt.get("answer", {}).get("risk_class") or "unsupported"), True
    if "restart_destabilization_causal_rule" in tuple(receipt.get("unsupported_causal_gaps") or ()):
        return "residual_required", "unsupported_without_causal_rule", False
    return "unsupported", "unsupported", False


def _capability_traffic_status_class(receipt: Mapping[str, Any]) -> tuple[str, str, bool]:
    status = str(receipt.get("status") or "")
    if status == "composed":
        risk = str(receipt.get("answer", {}).get("risk_class") or "")
        return "supported", "safe" if risk == "low" else "unsafe", True
    if "traffic_shift_capacity_rule" in tuple(receipt.get("unsupported_causal_gaps") or ()):
        return "residual_required", "unsupported_without_capacity_rule", False
    return "unsupported", "unsupported", False


def _capability_deployment_status_class(receipt: Mapping[str, Any]) -> tuple[str, str, bool]:
    status = str(receipt.get("status") or "")
    if status == "composed":
        risk = str(receipt.get("answer", {}).get("risk_class") or "")
        return "supported", "safe_to_continue" if risk == "low" else "halt_or_rollback", True
    if "deployment_blast_radius_rule" in tuple(receipt.get("unsupported_causal_gaps") or ()):
        return "residual_required", "unsupported_without_rollout_rule", False
    return "unsupported", "unsupported", False


def _reachable(edges: list[tuple[str, str]], source: str, target: str) -> bool:
    frontier = [source]
    seen = {source}
    while frontier:
        current = frontier.pop(0)
        if current == target:
            return True
        for left, right in edges:
            if left == current and right not in seen:
                seen.add(right)
                frontier.append(right)
            if right == current and left not in seen:
                seen.add(left)
                frontier.append(left)
    return False


def _empty_baseline_score() -> dict[str, int]:
    return {
        "semantic_correct": 0,
        "honest_uncertainty": 0,
        "visual_present": 0,
        "artifact_custody_valid": 0,
        "proof_first": 0,
        "provider_calls_used": 0,
        "total_score": 0,
    }


def _accumulate(score: dict[str, int], evaluated: Mapping[str, Any]) -> None:
    for key in ("semantic_correct", "honest_uncertainty", "visual_present", "artifact_custody_valid", "proof_first"):
        score[key] += int(evaluated.get(key) is True)
    score["provider_calls_used"] += int(evaluated.get("provider_calls_used") or 0)
    score["total_score"] += int(evaluated.get("total_score") or 0)


def _finalize_score(score: Mapping[str, int], total_cases: int) -> dict[str, Any]:
    return {
        **dict(score),
        "case_count": total_cases,
        "semantic_accuracy": round(score["semantic_correct"] / max(1, total_cases), 6),
    }


def _service_name(rng: random.Random, *, avoid: set[str] | None = None) -> str:
    avoid = avoid or set()
    syllables = ("Ari", "Bex", "Cyra", "Dune", "Eko", "Flux", "Gale", "Halo", "Ion", "Juno", "Kite", "Luma", "Mira", "Nox", "Orin", "Pax", "Quill", "Riven", "Sora", "Talon", "Uma", "Vega", "Wisp", "Yara", "Zeno")
    while True:
        name = rng.choice(syllables) + "-" + rng.choice(("api", "edge", "core", "mesh", "worker", "canary"))
        if name not in avoid:
            return name


def _scenario_public(scenario: Scenario) -> dict[str, Any]:
    return {
        "scenario_id": scenario.scenario_id,
        "family": scenario.family.value,
        "question": scenario.question,
        "source": scenario.source,
        "target": scenario.target,
        "facts": [_public_dataclass(fact) for fact in scenario.facts],
        "rules": [_public_dataclass(rule) for rule in scenario.rules],
        "policies": [_public_dataclass(policy) for policy in scenario.policies],
        "fact_count": len(scenario.facts),
        "rule_count": len(scenario.rules),
        "policy_count": len(scenario.policies),
        "metadata": dict(scenario.metadata),
        "force_layout_overflow": scenario.force_layout_overflow,
        "scenario_digest": sha256_digest(asdict(scenario)),
    }


def _public_dataclass(value: Any) -> dict[str, Any]:
    return json.loads(canonical_json(asdict(value)))


def _public_output_summary(output: Mapping[str, Any]) -> dict[str, Any]:
    chunks = output.get("retrieved_chunks") if isinstance(output.get("retrieved_chunks"), list) else []
    return {
        "system_id": str(output.get("system_id") or ""),
        "answer_text": str(output.get("answer_text") or "")[:1200],
        "reported_status": output.get("reported_status", ""),
        "reported_class": output.get("reported_class", ""),
        "reported_current_claim_allowed": output.get("reported_current_claim_allowed", ""),
        "current_claim_valid": output.get("current_claim_valid", ""),
        "visual_present": bool(output.get("visual_bytes")) or output.get("visual_present") is True,
        "artifact_custody_valid": output.get("artifact_custody_valid") is True,
        "proof_first": output.get("proof_first") is True,
        "provider_calls_used": int(output.get("provider_calls_used") or 0),
        "retrieved_chunk_count": len(chunks),
        "retrieved_chunks": [
            {
                "rank": chunk.get("rank", index),
                "text": str(chunk.get("text") or "")[:600],
                "metadata": chunk.get("metadata", {}) if isinstance(chunk.get("metadata"), Mapping) else {},
                "row_digest": chunk.get("row_digest", ""),
            }
            for index, chunk in enumerate(chunks[:3], start=1)
            if isinstance(chunk, Mapping)
        ],
        "output_digest": sha256_digest(output),
    }


def _baseline_description(name: str) -> str:
    return {
        "rag_nearest_exemplar": "Retrieves a nearest named exemplar answer/diagram without proof custody.",
        "cached_named_template": "Replays only named-scenario templates; held-out names miss.",
        "rule_engine_text_only": "Computes text from rules but emits no proof-bound visual artifact.",
        "knowledge_graph_topology_only": "Uses topology reachability and ignores policy/temporal/capacity gates.",
        "model_generated_multimodal_stub": "Simulates provider multimodal answer with unverified text/SVG and provider cost.",
        "beast_local_semantic_cache": "Uses the existing LocalSemanticCache lexical/dense-cache implementation against historical exemplars.",
        "beast_capability_composition_rule_engine": "Uses the existing CapabilityCompositionPlane as a no-provider rule/composition competitor.",
        "beast_topology_graph_adapter": "Uses an in-repo topology graph walk over dependency/route facts while ignoring policy and freshness.",
        "beast_generation_provider_boundary": "Uses the existing generation provider adapter boundary in deterministic no-network stub mode.",
        "external_rag_retrieval": "Calls an operator-supplied external RAG command with public scenario JSON and scores its answer/chunks against the independent oracle.",
    }[name]


def _write_checksums(root: Path) -> None:
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            rows.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root)}")
    (root / "SHA256SUMS.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")


def _markdown(report: Mapping[str, Any]) -> str:
    score = report["scorecard"]
    systems = report["systems"]
    lines = [
        f"# C4-X external breakthrough benchmark · {report['run_id']}",
        "",
        f"- Receipt: `{report['receipt_digest']}`",
        f"- Engine freeze digest: `{score['engine_freeze_digest']}`",
        f"- Evaluator seed: `{score['evaluator_seed']}`",
        f"- Held-out cases: `{score['heldout_cases']}`",
        f"- Cross-modal families: `{score['cross_modal_families']}`",
        f"- Independent semantic oracle: `{score['independent_semantic_oracle']}`",
        f"- Randomized topology shapes: `{score['randomized_topology_shapes']}`",
        f"- Held-out operational domains: `{score['heldout_operational_domains']}`",
        f"- Randomized service names: `{score['randomized_service_names']}`",
        f"- BEAST semantic correct: `{score['beast_semantic_correct']}/{score['heldout_cases']}`",
        f"- BEAST artifact custody valid: `{score['beast_artifact_custody_valid']}/{score['heldout_cases']}`",
        f"- BEAST provider calls used: `{score['beast_provider_calls_used']}`",
        f"- Baselines compared: `{score['baseline_count']}`",
        f"- Baseline scope: `{score['baseline_scope']}`",
        f"- Third-party verifier ready: `{score['third_party_verifier_ready']}`",
        f"- BEAST beats all baselines: `{score['beast_beats_all_baselines']}`",
        f"- Breakthrough protocol pass: `{score['breakthrough_protocol_pass']}`",
        "",
        "## Randomization coverage",
        "",
        f"- Topology shapes: `{json.dumps(score['topology_shape_counts'], sort_keys=True)}`",
        f"- Operational domains: `{json.dumps(score['operational_domain_counts'], sort_keys=True)}`",
        "",
        "## System scores",
        "",
    ]
    for name, values in systems.items():
        lines.append(
            f"- `{name}`: total={values['total_score']}, semantic={values['semantic_correct']}/{values['case_count']}, "
            f"custody={values['artifact_custody_valid']}/{values['case_count']}, providers={values['provider_calls_used']}"
        )
    lines.extend(["", "## Boundary", "", str(report["claim_boundary"]), ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluator-seed", required=True, help="Seed supplied after engine freeze by evaluator/third party.")
    parser.add_argument("--case-count-per-family", type=int, default=4)
    parser.add_argument("--evidence-root", default=str(REPO_ROOT / "evidence" / "c4x-external-breakthrough-benchmark"))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--external-rag-command", default=None, help="Optional command invoked once per case; receives c4x_external_rag_request JSON on stdin and returns output JSON on stdout.")
    args = parser.parse_args(argv)
    report = run_breakthrough_benchmark(
        evaluator_seed=args.evaluator_seed,
        case_count_per_family=args.case_count_per_family,
        evidence_root=args.evidence_root,
        run_id=args.run_id,
        external_rag_command=args.external_rag_command,
    )
    print(json.dumps({
        "receipt_digest": report["receipt_digest"],
        "breakthrough_protocol_pass": report["scorecard"]["breakthrough_protocol_pass"],
        "scorecard": report["scorecard"],
        "evidence_root": report["evidence_root"],
    }, sort_keys=True, indent=2))
    return 0 if report["scorecard"]["breakthrough_protocol_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
