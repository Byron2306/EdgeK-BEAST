#!/usr/bin/env python3
"""Run the BEAST semantic expression gauntlet.

This proves a bounded version of:

semantic program -> discourse plan -> deterministic text
semantic program -> scene graph -> SVG
semantic program -> SourcePlan draft

The text is not the source for the visual or code plan.  The semantic program is.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
import sys
import time
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.kernel.compute.deterministic_intelligence import sha256_digest, utc_now_iso  # noqa: E402
from app.kernel.compute.semantic_expression import (  # noqa: E402
    ClaimStatus,
    ExpressionStyle,
    ExpressionVerifier,
    SemanticEntity,
    SemanticClaim,
    SemanticEdge,
    SemanticExpressionEngine,
    SemanticIntent,
    SemanticProgram,
    SourceTransformationCapabilityRegistry,
    SourceTransformationRuntime,
    SvgSceneRenderer,
    bind_semantic_receipts,
    code_transform_program,
    failure_explanation_program,
    result_to_dict,
)


DEFAULT_ROOT = REPO_ROOT / "evidence" / "semantic-expression"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="semantic-expression-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
    parser.add_argument("--evidence-root", default=str(DEFAULT_ROOT))
    args = parser.parse_args()

    root = Path(args.evidence_root)
    if not root.is_absolute():
        root = REPO_ROOT / root
    run_root = root / args.run_id
    run_root.mkdir(parents=True, exist_ok=True)

    engine = SemanticExpressionEngine()
    ordinary_cases = {
        "speaks_failure_technical": engine.compile(failure_explanation_program(), style=ExpressionStyle.TECHNICAL),
        "speaks_failure_conversational": engine.compile(failure_explanation_program(), style=ExpressionStyle.CONVERSATIONAL),
        "draws_failure_executive": engine.compile(failure_explanation_program(), style=ExpressionStyle.EXECUTIVE),
        "codes_retry_damping_forensic": engine.compile(code_transform_program(), style=ExpressionStyle.FORENSIC),
        "relevance_pruned_failure_forensic": engine.compile(_irrelevant_branch_program(), style=ExpressionStyle.FORENSIC),
        **{
            name: engine.compile(program, style=ExpressionStyle.FORENSIC)
            for name, program in _third_wave_ordinary_programs().items()
        },
    }
    hostile_cases = {
        name: engine.compile(program, style=ExpressionStyle.FORENSIC)
        for name, program in _hostile_programs().items()
    }
    residual_pending_cases = {
        name: engine.compile(program, style=ExpressionStyle.FORENSIC)
        for name, program in _residual_pending_programs().items()
    }
    cases = {**ordinary_cases, **hostile_cases, **residual_pending_cases}

    case_reports: dict[str, Mapping[str, Any]] = {}
    for name, result in cases.items():
        case_dir = run_root / name
        case_dir.mkdir(parents=True, exist_ok=True)
        payload = result_to_dict(result, include_artifacts=True)
        (case_dir / "semantic_expression.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (case_dir / "answer.json").write_text(result.text_artifact.content.decode("utf-8"), encoding="utf-8")
        visual_name = "diagram.svg" if result.visual_artifact.media_type == "image/svg+xml" else "visual_refusal.json"
        (case_dir / visual_name).write_bytes(result.visual_artifact.content)
        (case_dir / "sourceplan.json").write_text(json.dumps(payload["sourceplan"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (case_dir / "joined_receipt.json").write_text(json.dumps(result.joined_receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        case_reports[name] = {
            "semantic_digest": result.program.semantic_digest,
            "semantic_validation_accepted": result.validation_report.accepted,
            "semantic_validation_issue_classes": tuple(issue.issue_class for issue in result.validation_report.issues),
            "residual_action": result.residual_decision["action"],
            "text_digest": result.text_artifact.digest,
            "visual_digest": result.visual_artifact.digest,
            "sourceplan_digest": result.sourceplan.digest,
            "joined_receipt_digest": result.joined_receipt["receipt_digest"],
            "joined_verification": result.joined_receipt["joined_verification"],
            "ordinary_answer_available": result.joined_receipt["ordinary_answer_available"],
            "refusal_enforced": result.joined_receipt["refusal_enforced"],
            "independent_text_entailment_valid": result.joined_receipt["independent_text_entailment_valid"],
            "independent_visual_entailment_valid": result.joined_receipt["independent_visual_entailment_valid"],
            "independent_sourceplan_valid": result.joined_receipt["independent_sourceplan_valid"],
            "provider_calls_used": result.joined_receipt["provider_calls_used"],
            "sourceplan_status": result.sourceplan.status,
            "style": result.discourse_plan.style.value,
        }

    overflow_control = _visual_overflow_negative_control(engine)
    (run_root / "visual_overflow_negative_control.json").write_text(
        json.dumps(overflow_control, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    source_runtime_receipt = SourceTransformationRuntime(REPO_ROOT).execute_preview(
        ordinary_cases["codes_retry_damping_forensic"].sourceplan,
        evidence_root=run_root / "source_transformation_runtime",
        run_id=args.run_id + ":source-runtime",
    )
    surname_target_denied = SourceTransformationCapabilityRegistry().lookup(
        "add_retry_damping",
        "app.kernel.registry.some_other_module.ProviderRegistry",
    )

    technical = ordinary_cases["speaks_failure_technical"]
    conversational = ordinary_cases["speaks_failure_conversational"]
    code = ordinary_cases["codes_retry_damping_forensic"]
    scorecard = {
        "ordinary_case_count": len(ordinary_cases),
        "hostile_case_count": len(hostile_cases),
        "residual_pending_case_count": len(residual_pending_cases),
        "case_count": len(cases),
        "meaning_first_cases": sum(bool(item.joined_receipt["meaning_first"]) for item in ordinary_cases.values()),
        "joined_verified_cases": sum(bool(item.joined_receipt["joined_verification"]) for item in ordinary_cases.values()),
        "hostile_refusal_cases": sum(
            bool(item.residual_decision["action"] == "refuse" and item.joined_receipt["refusal_enforced"])
            for item in hostile_cases.values()
        ),
        "hostile_joined_verified_cases": sum(bool(item.joined_receipt["joined_verification"]) for item in hostile_cases.values()),
        "residual_pending_cases_enforced": sum(
            bool(item.residual_decision["action"] == "bounded_residual" and item.joined_receipt["residual_pending_enforced"])
            for item in residual_pending_cases.values()
        ),
        "residual_pending_joined_verified_cases": sum(bool(item.joined_receipt["joined_verification"]) for item in residual_pending_cases.values()),
        "independent_entailment_cases": sum(
            bool(
                item.joined_receipt["independent_text_entailment_valid"]
                and item.joined_receipt["independent_visual_entailment_valid"]
                and item.joined_receipt["independent_sourceplan_valid"]
            )
            for item in cases.values()
        ),
        "visual_overflow_negative_control_rejected": overflow_control["joined_verification"] is False
        and "visual_node_overflow:node:deployment-47" in overflow_control["failure_classes"],
        "source_transformation_preview_verified": source_runtime_receipt["status"] == "verified_preview"
        and source_runtime_receipt["compile_ok"] is True
        and source_runtime_receipt.get("module_import", {}).get("ok") is True
        and source_runtime_receipt["structural_verifier"]["passed"] is True
        and source_runtime_receipt["live_source_mutated"] is False,
        "exact_target_surname_denied": surname_target_denied["allowed"] is False,
        "boolean_false_negative_realized": "did not fail" in ordinary_cases["boolean_false_failed_negative_realization"].text_artifact.content.decode("utf-8")
        and "did not roll back" in ordinary_cases["boolean_false_rollback_negative_realization"].text_artifact.content.decode("utf-8"),
        "visual_temperature_proposition_realized": "900degC" in ordinary_cases["visual_temperature_proposition_covered"].visual_artifact.content.decode("utf-8"),
        "provider_calls_used": sum(int(item.joined_receipt["provider_calls_used"]) for item in cases.values()),
        "style_variation_same_semantic_digest": technical.program.semantic_digest == conversational.program.semantic_digest
        and technical.text_artifact.digest != conversational.text_artifact.digest,
        "visual_from_semantics_not_text": all(bool(item.joined_receipt["visual_from_semantics_not_text"]) for item in ordinary_cases.values()),
        "sourceplan_from_semantics_not_text": all(bool(item.joined_receipt["sourceplan_from_semantics_not_text"]) for item in ordinary_cases.values()),
        "sourceplan_drafted_from_code_constraints": code.sourceplan.status == "draft_requires_approval" and len(code.sourceplan.operations) == 1,
        "unsupported_boundary_realized": "does not establish" in technical.text_artifact.content.decode("utf-8"),
        "irrelevant_causal_branch_pruned": "Coffee machine" not in ordinary_cases["relevance_pruned_failure_forensic"].text_artifact.content.decode("utf-8")
        and "Coffee machine" not in ordinary_cases["relevance_pruned_failure_forensic"].visual_artifact.content.decode("utf-8"),
    }
    scorecard["semantic_expression_pass"] = (
        scorecard["meaning_first_cases"] == scorecard["ordinary_case_count"]
        and scorecard["joined_verified_cases"] == scorecard["ordinary_case_count"]
        and scorecard["hostile_refusal_cases"] == scorecard["hostile_case_count"]
        and scorecard["hostile_joined_verified_cases"] == scorecard["hostile_case_count"]
        and scorecard["residual_pending_cases_enforced"] == scorecard["residual_pending_case_count"]
        and scorecard["residual_pending_joined_verified_cases"] == scorecard["residual_pending_case_count"]
        and scorecard["independent_entailment_cases"] == scorecard["case_count"]
        and scorecard["visual_overflow_negative_control_rejected"]
        and scorecard["source_transformation_preview_verified"]
        and scorecard["exact_target_surname_denied"]
        and scorecard["boolean_false_negative_realized"]
        and scorecard["visual_temperature_proposition_realized"]
        and scorecard["irrelevant_causal_branch_pruned"]
        and scorecard["provider_calls_used"] == 0
        and scorecard["style_variation_same_semantic_digest"]
        and scorecard["visual_from_semantics_not_text"]
        and scorecard["sourceplan_from_semantics_not_text"]
        and scorecard["sourceplan_drafted_from_code_constraints"]
        and scorecard["unsupported_boundary_realized"]
    )
    report = {
        "beast_object_type": "semantic_expression_gauntlet",
        "version": "1.0",
        "run_id": args.run_id,
        "created_at": utc_now_iso(),
        "cases": case_reports,
        "scorecard": scorecard,
        "claim_boundary": (
            "Bounded BEAST semantic expression proof. It demonstrates deterministic "
            "text, SVG scene, and SourcePlan draft generation from canonical semantic "
            "programs with joined verification and zero provider calls. Hostile "
            "semantic programs are validated before expression and must become "
            "dedicated refusal artifacts, residual-required claims become pending "
            "residual packets rather than facts, and irrelevant causal branches are "
            "pruned from requested explanations. The registered code transformation "
            "path produces a compile-checked preview diff in an evidence worktree, "
            "but still requires approval before live apply. It does not claim "
            "open-domain conversation, photorealistic rendering, or autonomous "
            "source mutation authority."
        ),
        "source_transformation_runtime": {
            "receipt_digest": source_runtime_receipt["receipt_digest"],
            "status": source_runtime_receipt["status"],
            "module_import": source_runtime_receipt.get("module_import"),
            "diff_digest": source_runtime_receipt.get("diff_digest"),
            "diff_path": source_runtime_receipt.get("diff_path"),
            "live_source_mutated": source_runtime_receipt.get("live_source_mutated"),
        },
        "exact_target_negative_control": surname_target_denied,
    }
    report["receipt_digest"] = sha256_digest(report)
    (run_root / "semantic_expression_gauntlet.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (run_root / "semantic_expression_gauntlet.md").write_text(_markdown(report), encoding="utf-8")
    _write_checksums(run_root)
    (root / "latest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (root / "latest.md").write_text(_markdown(report), encoding="utf-8")
    print(json.dumps({
        "run_id": args.run_id,
        "evidence_root": str(run_root),
        "receipt_digest": report["receipt_digest"],
        "semantic_expression_pass": scorecard["semantic_expression_pass"],
        "joined_verified_cases": scorecard["joined_verified_cases"],
        "hostile_refusal_cases": scorecard["hostile_refusal_cases"],
        "residual_pending_cases_enforced": scorecard["residual_pending_cases_enforced"],
        "irrelevant_causal_branch_pruned": scorecard["irrelevant_causal_branch_pruned"],
        "source_transformation_preview_verified": scorecard["source_transformation_preview_verified"],
        "exact_target_surname_denied": scorecard["exact_target_surname_denied"],
        "boolean_false_negative_realized": scorecard["boolean_false_negative_realized"],
        "visual_temperature_proposition_realized": scorecard["visual_temperature_proposition_realized"],
        "visual_overflow_negative_control_rejected": scorecard["visual_overflow_negative_control_rejected"],
        "provider_calls_used": scorecard["provider_calls_used"],
    }, indent=2, sort_keys=True))
    return 0 if scorecard["semantic_expression_pass"] else 1


def _hostile_programs() -> dict[str, SemanticProgram]:
    base = failure_explanation_program()
    code = code_transform_program()
    return {
        "hostile_contradictory_claims_refused": SemanticProgram(
            program_id=base.program_id + ":contradiction",
            intent=base.intent,
            entities=base.entities,
            claims=base.claims + (
                SemanticClaim("claim:cert-valid", "state", "certificate", value="valid"),
            ),
            edges=base.edges,
            boundaries=base.boundaries,
            permissions=base.permissions,
            created_at=base.created_at,
        ),
        "hostile_reversed_causality_refused": SemanticProgram(
            program_id=base.program_id + ":reversed",
            intent=base.intent,
            entities=base.entities,
            claims=base.claims,
            edges=(
                SemanticEdge("edge:rollback-to-health", "claim:rolled-back", "claim:health-failed"),
                SemanticEdge("edge:health-to-mtls-reversed", "claim:health-failed", "claim:mtls-failed"),
                SemanticEdge("edge:mtls-to-cert-reversed", "claim:mtls-failed", "claim:cert-expired"),
            ),
            boundaries=base.boundaries,
            permissions=base.permissions,
            created_at=base.created_at,
        ),
        "hostile_circular_causality_refused": SemanticProgram(
            program_id=base.program_id + ":cycle",
            intent=base.intent,
            entities=base.entities,
            claims=base.claims,
            edges=base.edges + (
                SemanticEdge("edge:rollback-to-cert-cycle", "claim:rolled-back", "claim:cert-expired"),
            ),
            boundaries=base.boundaries,
            permissions=base.permissions,
            created_at=base.created_at,
        ),
        "hostile_unbounded_unsupported_claim_refused": SemanticProgram(
            program_id=base.program_id + ":unsupported-unbounded",
            intent=base.intent,
            entities=base.entities,
            claims=tuple(
                replace(claim, status=ClaimStatus.UNSUPPORTED)
                if claim.claim_id == "claim:mtls-failed"
                else claim
                for claim in base.claims
            ),
            edges=base.edges,
            boundaries=(),
            permissions=base.permissions,
            created_at=base.created_at,
        ),
        "hostile_missing_code_symbol_refused": SemanticProgram(
            program_id=code.program_id + ":missing-symbol",
            intent=code.intent,
            entities=code.entities,
            claims=tuple(
                replace(claim, value="no.such.module.NoSuchClass")
                if claim.predicate == "target_symbol"
                else claim
                for claim in code.claims
            ),
            edges=code.edges,
            boundaries=code.boundaries,
            permissions=code.permissions,
            created_at=code.created_at,
        ),
        "hostile_stale_causal_source_refused": SemanticProgram(
            program_id=base.program_id + ":stale-causal-source",
            intent=base.intent,
            entities=base.entities,
            claims=tuple(
                replace(claim, status=ClaimStatus.STALE)
                if claim.claim_id == "claim:cert-expired"
                else claim
                for claim in base.claims
            ),
            edges=base.edges,
            boundaries=base.boundaries,
            permissions=base.permissions,
            created_at=base.created_at,
        ),
        "hostile_unsupported_causal_edge_refused": SemanticProgram(
            program_id=base.program_id + ":unsupported-edge",
            intent=base.intent,
            entities=base.entities,
            claims=base.claims,
            edges=tuple(
                replace(edge, status=ClaimStatus.UNSUPPORTED)
                if edge.edge_id == "edge:cert-to-mtls"
                else edge
                for edge in base.edges
            ),
            boundaries=base.boundaries,
            permissions=base.permissions,
            created_at=base.created_at,
        ),
        "hostile_ontology_xor_refused": SemanticProgram(
            program_id="semantic:ontology-xor",
            intent=SemanticIntent(
                intent="answer_status",
                subject="service-a",
                question="What is Service A's state?",
            ),
            entities=(SemanticEntity("service-a", "service", "Service A"),),
            claims=(
                SemanticClaim("claim:healthy", "state", "service-a", value="healthy"),
                SemanticClaim("claim:failed", "failed", "service-a", value=True),
            ),
            created_at="2026-08-04T00:00:00+00:00",
        ),
        "hostile_unknown_code_transform_refused": SemanticProgram(
            program_id=code.program_id + ":exfiltrate",
            intent=code.intent,
            entities=code.entities,
            claims=tuple(
                replace(claim, value="exfiltrate_all_secrets")
                if claim.predicate == "code_transform_objective"
                else claim
                for claim in code.claims
            ),
            edges=code.edges,
            boundaries=code.boundaries,
            permissions=code.permissions,
            created_at=code.created_at,
        ),
        "hostile_malformed_time_refused": SemanticProgram(
            program_id=base.program_id + ":bad-time",
            intent=base.intent,
            entities=base.entities,
            claims=tuple(
                replace(claim, metadata={"observed_at": "not-a-date", "expires_at": "zzz"})
                if claim.claim_id == "claim:cert-expired"
                else claim
                for claim in base.claims
            ),
            edges=base.edges,
            boundaries=base.boundaries,
            permissions=base.permissions,
            created_at=base.created_at,
        ),
        "hostile_bool_like_string_refused": SemanticProgram(
            program_id="semantic:typed-bool-string",
            intent=SemanticIntent("answer_status", "service-a", "Did Service A fail?"),
            entities=(SemanticEntity("service-a", "service", "Service A"),),
            claims=(
                SemanticClaim("claim:failed-string", "failed", "service-a", value="true", evidence_refs=("sha256:" + "3" * 64,), metadata={"evidence_authority": "verified_receipt"}),
            ),
            created_at="2026-08-04T00:00:00+00:00",
        ),
        "hostile_unknown_predicate_refused": SemanticProgram(
            program_id="semantic:unknown-predicate",
            intent=SemanticIntent("answer_status", "service-a", "What is Service A doing?"),
            entities=(SemanticEntity("service-a", "service", "Service A"),),
            claims=(SemanticClaim("claim:vibes", "vibes_like", "service-a", value="fine"),),
            created_at="2026-08-04T00:00:00+00:00",
        ),
        "hostile_invalid_evidence_ref_refused": SemanticProgram(
            program_id="semantic:bad-evidence-ref",
            intent=SemanticIntent("answer_status", "service-a", "Did Service A fail?"),
            entities=(SemanticEntity("service-a", "service", "Service A"),),
            claims=(
                SemanticClaim("claim:failed-bad-ref", "failed", "service-a", value=True, evidence_refs=("sha256:not-real",), metadata={"evidence_authority": "verified_receipt"}),
            ),
            created_at="2026-08-04T00:00:00+00:00",
        ),
        "hostile_target_identity_kind_mismatch_refused": SemanticProgram(
            program_id=code.program_id + ":wrong-target-kind",
            intent=SemanticIntent(
                intent="draft_code_transform",
                subject="service-a",
                question="Add retry damping to a service identity.",
                requested_outputs=("text", "visual", "sourceplan"),
            ),
            entities=(
                SemanticEntity("service-a", "service", "Service A"),
                SemanticEntity("retry-damping", "capability", "retry damping"),
                SemanticEntity("public-api", "interface", "public API"),
                SemanticEntity("router-tests", "test_suite", "router tests"),
            ),
            claims=(
                SemanticClaim("claim:objective", "code_transform_objective", "service-a", object="retry-damping", value="add_retry_damping"),
                SemanticClaim("claim:target-symbol", "target_symbol", "service-a", value="app.kernel.registry.provider_registry.ProviderRegistry"),
                SemanticClaim("claim:api-preserved", "preserve_public_api", "public-api", value=True),
                SemanticClaim("claim:test-required", "test_requirement", "router-tests", value="preserve existing provider API tests"),
            ),
            edges=code.edges,
            permissions=code.permissions,
            created_at=code.created_at,
        ),
        "hostile_expired_temporal_authority_refused": SemanticProgram(
            program_id="semantic:expired-authority",
            intent=SemanticIntent("answer_status", "service-a", "Is Service A healthy now?"),
            entities=(SemanticEntity("service-a", "service", "Service A"),),
            claims=(
                SemanticClaim(
                    "claim:healthy-expired",
                    "state",
                    "service-a",
                    value="healthy",
                    evidence_refs=("sha256:" + "4" * 64,),
                    metadata={"evidence_authority": "verified_receipt", "observed_at": "2026-08-03T00:00:00+00:00", "expires_at": "2026-08-03T01:00:00+00:00"},
                ),
            ),
            created_at="2026-08-04T00:00:00+00:00",
        ),
        "hostile_future_observation_refused": SemanticProgram(
            program_id="semantic:future-observation",
            intent=SemanticIntent("answer_status", "service-a", "Is Service A healthy now?"),
            entities=(SemanticEntity("service-a", "service", "Service A"),),
            claims=(
                SemanticClaim(
                    "claim:healthy-future",
                    "state",
                    "service-a",
                    value="healthy",
                    evidence_refs=("sha256:" + "5" * 64,),
                    metadata={"evidence_authority": "verified_receipt", "observed_at": "2026-08-05T00:00:00+00:00"},
                ),
            ),
            created_at="2026-08-04T00:00:00+00:00",
        ),
        "hostile_unverified_supported_claim_refused": SemanticProgram(
            program_id="semantic:unverified-supported",
            intent=SemanticIntent("answer_status", "service-a", "Is Service A healthy?"),
            entities=(SemanticEntity("service-a", "service", "Service A"),),
            claims=(
                SemanticClaim(
                    "claim:healthy-unverified",
                    "state",
                    "service-a",
                    value="healthy",
                    confidence="unverified",
                    evidence_refs=("sha256:" + "6" * 64,),
                    metadata={"evidence_authority": "verified_receipt"},
                ),
            ),
            created_at="2026-08-04T00:00:00+00:00",
        ),
        "hostile_public_api_false_refused": SemanticProgram(
            program_id=code.program_id + ":public-api-false",
            intent=code.intent,
            entities=code.entities,
            claims=tuple(
                replace(claim, value=False)
                if claim.predicate == "preserve_public_api"
                else claim
                for claim in code.claims
            ),
            edges=code.edges,
            boundaries=code.boundaries,
            permissions=code.permissions,
            created_at=code.created_at,
        ),
        "hostile_generic_stale_causal_chain_refused": SemanticProgram(
            program_id="semantic:generic-stale-causal",
            intent=SemanticIntent("answer_status", "service-b", "What happened to Service B?"),
            entities=(
                SemanticEntity("service-a", "service", "Service A"),
                SemanticEntity("service-b", "service", "Service B"),
            ),
            claims=(
                SemanticClaim("claim:service-a-unavailable", "state", "service-a", value="unavailable", status=ClaimStatus.STALE),
                SemanticClaim("claim:service-b-failed", "failed", "service-b", value=True, evidence_refs=("sha256:" + "9" * 64,), metadata={"evidence_authority": "verified_receipt"}),
            ),
            edges=(SemanticEdge("edge:a-to-b", "claim:service-a-unavailable", "claim:service-b-failed"),),
            created_at="2026-08-04T00:00:00+00:00",
        ),
        "hostile_supported_without_evidence_authority_refused": SemanticProgram(
            program_id="semantic:supported-self-declared",
            intent=SemanticIntent("answer_status", "service-a", "Is Service A healthy?"),
            entities=(SemanticEntity("service-a", "service", "Service A"),),
            claims=(
                SemanticClaim("claim:self-declared-supported", "state", "service-a", value="healthy", confidence="verified", evidence_refs=("sha256:" + "b" * 64,)),
            ),
            created_at="2026-08-04T00:00:00+00:00",
        ),
        "hostile_claim_authority_label_without_receipt_refused": SemanticProgram(
            program_id="semantic:fake-evidence-receipt",
            intent=SemanticIntent("answer_status", "service-a", "Did Service A fail?"),
            entities=(SemanticEntity("service-a", "service", "Service A"),),
            claims=(
                SemanticClaim("claim:failed-fake-receipt", "failed", "service-a", value=True, evidence_refs=("sha256:" + "1" * 64,), metadata={"evidence_authority": "verified_receipt"}),
            ),
            created_at="2026-08-04T00:00:00+00:00",
        ),
        "hostile_supported_edge_without_relationship_receipt_refused": SemanticProgram(
            program_id=base.program_id + ":edge-without-receipt",
            intent=base.intent,
            entities=base.entities,
            claims=base.claims,
            edges=tuple(
                replace(edge, metadata={})
                if edge.edge_id == "edge:cert-to-mtls"
                else edge
                for edge in base.edges
            ),
            boundaries=base.boundaries,
            permissions=base.permissions,
            created_at=base.created_at,
        ),
        "hostile_failed_state_vs_failed_false_refused": bind_semantic_receipts(SemanticProgram(
            program_id="semantic:failed-state-false-boolean",
            intent=SemanticIntent("answer_status", "service-a", "Did Service A fail?"),
            entities=(SemanticEntity("service-a", "service", "Service A"),),
            claims=(
                SemanticClaim("claim:state-failed", "state", "service-a", value="failed"),
                SemanticClaim("claim:not-failed", "failed", "service-a", value=False),
            ),
            created_at="2026-08-04T00:00:00+00:00",
        )),
        "hostile_temperature_bad_unit_refused": SemanticProgram(
            program_id="semantic:bad-temperature-unit",
            intent=SemanticIntent("answer_status", "reactor-7", "What is Reactor 7 temperature?"),
            entities=(SemanticEntity("reactor-7", "reactor", "Reactor 7"),),
            claims=(
                SemanticClaim(
                    "claim:reactor-temp",
                    "temperature",
                    "reactor-7",
                    value={"magnitude": 900, "unit": "bananas", "dimension": "temperature"},
                    evidence_refs=("sha256:" + "2" * 64,),
                    metadata={"evidence_authority": "sensorium_receipt"},
                ),
            ),
            created_at="2026-08-04T00:00:00+00:00",
        ),
    }


def _residual_pending_programs() -> dict[str, SemanticProgram]:
    return {
        "residual_required_claim_pending_not_asserted": SemanticProgram(
            program_id="semantic:residual-compromise",
            intent=SemanticIntent(
                intent="answer_status",
                subject="service-a",
                question="Is Service A compromised?",
                requested_outputs=("text", "visual"),
            ),
            entities=(SemanticEntity("service-a", "service", "Service A"),),
            claims=(
                SemanticClaim(
                    "claim:service-compromised",
                    "state",
                    "service-a",
                    value="compromised",
                    status=ClaimStatus.RESIDUAL_REQUIRED,
                ),
            ),
            created_at="2026-08-04T00:00:00+00:00",
        )
    }


def _third_wave_ordinary_programs() -> dict[str, SemanticProgram]:
    base = failure_explanation_program()
    return {
        "boolean_false_failed_negative_realization": bind_semantic_receipts(SemanticProgram(
            program_id="semantic:false-failed",
            intent=SemanticIntent("answer_status", "service-a", "Did Service A fail?"),
            entities=(SemanticEntity("service-a", "service", "Service A"),),
            claims=(
                SemanticClaim("claim:not-failed", "failed", "service-a", value=False, evidence_refs=("sha256:" + "7" * 64,), metadata={"evidence_authority": "verified_receipt"}),
            ),
            created_at="2026-08-04T00:00:00+00:00",
        )),
        "boolean_false_rollback_negative_realization": bind_semantic_receipts(SemanticProgram(
            program_id="semantic:false-rollback",
            intent=SemanticIntent("answer_status", "deployment-x", "Did Deployment X roll back?"),
            entities=(
                SemanticEntity("deployment-x", "deployment", "Deployment X"),
                SemanticEntity("rollback", "deployment_action", "rollback"),
            ),
            claims=(
                SemanticClaim("claim:not-rolled-back", "rolled_back", "deployment-x", object="rollback", value=False, evidence_refs=("sha256:" + "8" * 64,), metadata={"evidence_authority": "verified_receipt"}),
            ),
            created_at="2026-08-04T00:00:00+00:00",
        )),
        "enabled_false_registry_law_realized": SemanticProgram(
            program_id="semantic:feature-disabled",
            intent=SemanticIntent("answer_status", "feature-x", "Is Feature X enabled?"),
            entities=(SemanticEntity("feature-x", "feature", "Feature X"),),
            claims=(SemanticClaim("claim:feature-not-enabled", "enabled", "feature-x", value=False),),
            created_at="2026-08-04T00:00:00+00:00",
        ),
        "visual_temperature_proposition_covered": bind_semantic_receipts(SemanticProgram(
            program_id="semantic:reactor-temperature",
            intent=SemanticIntent("answer_status", "reactor-7", "What is Reactor 7 temperature?"),
            entities=(SemanticEntity("reactor-7", "reactor", "Reactor 7"),),
            claims=(
                SemanticClaim(
                    "claim:reactor-temp",
                    "temperature",
                    "reactor-7",
                    value={"magnitude": 900, "unit": "degC", "dimension": "temperature"},
                    evidence_refs=("sha256:" + "a" * 64,),
                    metadata={"evidence_authority": "sensorium_receipt"},
                ),
            ),
            created_at="2026-08-04T00:00:00+00:00",
        )),
        "same_subject_wrong_predicate_pruned": bind_semantic_receipts(SemanticProgram(
            program_id=base.program_id + ":same-subject-wrong-predicate",
            intent=base.intent,
            entities=base.entities + (SemanticEntity("weather", "external_context", "Weather"),),
            claims=base.claims + (
                SemanticClaim("claim:rainy-weather", "state", "weather", value="rainy", evidence_refs=("sha256:" + "c" * 64,), metadata={"evidence_authority": "verified_receipt"}),
                SemanticClaim("claim:deployment-available", "state", "deployment-47", value="available", evidence_refs=("sha256:" + "d" * 64,), metadata={"evidence_authority": "verified_receipt"}),
            ),
            edges=base.edges + (
                SemanticEdge("edge:weather-to-deployment-available", "claim:rainy-weather", "claim:deployment-available"),
            ),
            boundaries=base.boundaries,
            permissions=base.permissions,
            created_at=base.created_at,
        )),
    }


def _irrelevant_branch_program() -> SemanticProgram:
    base = failure_explanation_program()
    return bind_semantic_receipts(SemanticProgram(
        program_id=base.program_id + ":irrelevant-branch",
        intent=base.intent,
        entities=base.entities + (
            SemanticEntity("weather", "external_context", "Weather"),
            SemanticEntity("coffee-machine", "appliance", "Coffee machine"),
        ),
        claims=base.claims + (
            SemanticClaim("claim:rainy-weather", "state", "weather", value="rainy", evidence_refs=("sha256:" + "1" * 64,), metadata={"evidence_authority": "verified_receipt"}),
            SemanticClaim("claim:coffee-failed", "failed", "coffee-machine", value=True, evidence_refs=("sha256:" + "2" * 64,), metadata={"evidence_authority": "verified_receipt"}),
        ),
        edges=base.edges + (
            SemanticEdge("edge:weather-to-coffee", "claim:rainy-weather", "claim:coffee-failed"),
        ),
        boundaries=base.boundaries,
        permissions=base.permissions,
        created_at=base.created_at,
    ))


def _visual_overflow_negative_control(engine: SemanticExpressionEngine) -> dict[str, Any]:
    result = engine.compile(failure_explanation_program())
    bad_node = replace(result.scene_plan.nodes[0], x=result.scene_plan.width + 10)
    bad_scene = replace(result.scene_plan, nodes=(bad_node, *result.scene_plan.nodes[1:]))
    bad_visual = SvgSceneRenderer().render(result.program, bad_scene)
    receipt, verification = ExpressionVerifier().verify(
        program=result.program,
        validation_report=result.validation_report,
        discourse_plan=result.discourse_plan,
        text_artifact=result.text_artifact,
        scene_plan=bad_scene,
        visual_artifact=bad_visual,
        sourceplan=result.sourceplan,
        residual_decision=result.residual_decision,
    )
    return {
        "beast_object_type": "semantic_expression_visual_negative_control",
        "case": "scene_node_overflow_after_renderer_recompute",
        "semantic_digest": result.program.semantic_digest,
        "joined_verification": receipt["joined_verification"],
        "independent_visual_entailment_valid": receipt["independent_visual_entailment_valid"],
        "failure_classes": tuple(verification["failure_classes"]),
        "receipt_digest": receipt["receipt_digest"],
    }


def _write_checksums(root: Path) -> None:
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            rows.append(f"{_file_sha256(path).removeprefix('sha256:')}  {path.relative_to(root)}")
    (root / "SHA256SUMS.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")


def _file_sha256(path: Path) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _markdown(report: Mapping[str, Any]) -> str:
    score = report["scorecard"]
    lines = [
        f"# BEAST semantic expression gauntlet · {report['run_id']}",
        "",
        f"- Receipt: `{report['receipt_digest']}`",
        f"- Pass: `{score['semantic_expression_pass']}`",
        f"- Ordinary joined verified: `{score['joined_verified_cases']}/{score['ordinary_case_count']}`",
        f"- Hostile semantic programs refused: `{score['hostile_refusal_cases']}/{score['hostile_case_count']}`",
        f"- Hostile refusal artifacts verified: `{score['hostile_joined_verified_cases']}/{score['hostile_case_count']}`",
        f"- Residual-required claims held pending: `{score['residual_pending_cases_enforced']}/{score['residual_pending_case_count']}`",
        f"- Residual-pending artifacts verified: `{score['residual_pending_joined_verified_cases']}/{score['residual_pending_case_count']}`",
        f"- Independent entailment checks passed: `{score['independent_entailment_cases']}/{score['case_count']}`",
        f"- Visual overflow negative control rejected: `{score['visual_overflow_negative_control_rejected']}`",
        f"- Source transformation preview verified: `{score['source_transformation_preview_verified']}`",
        f"- Exact target surname denied: `{score['exact_target_surname_denied']}`",
        f"- Boolean false negative realization: `{score['boolean_false_negative_realized']}`",
        f"- Visual temperature proposition realized: `{score['visual_temperature_proposition_realized']}`",
        f"- Irrelevant causal branch pruned: `{score['irrelevant_causal_branch_pruned']}`",
        f"- Provider calls: `{score['provider_calls_used']}`",
        f"- Style variation from same semantic digest: `{score['style_variation_same_semantic_digest']}`",
        f"- Visual from semantics, not text: `{score['visual_from_semantics_not_text']}`",
        f"- SourcePlan from semantics, not text: `{score['sourceplan_from_semantics_not_text']}`",
        f"- Unsupported boundary realized: `{score['unsupported_boundary_realized']}`",
        "",
        "## Source transformation runtime",
        "",
        f"- Runtime receipt: `{report.get('source_transformation_runtime', {}).get('receipt_digest')}`",
        f"- Preview status: `{report.get('source_transformation_runtime', {}).get('status')}`",
        f"- Diff digest: `{report.get('source_transformation_runtime', {}).get('diff_digest')}`",
        f"- Live source mutated: `{report.get('source_transformation_runtime', {}).get('live_source_mutated')}`",
        "",
        "## Boundary",
        "",
        str(report["claim_boundary"]),
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
