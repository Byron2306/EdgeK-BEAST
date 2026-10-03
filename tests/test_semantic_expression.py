import json
from dataclasses import replace

from app.kernel.compute.semantic_expression import (
    ClaimStatus,
    ExpressionVerifier,
    SemanticEntity,
    SemanticExpressionEngine,
    SemanticClaim,
    SemanticEdge,
    SemanticIntent,
    SemanticProgram,
    SourceTransformationCapabilityRegistry,
    SourceTransformationRuntime,
    SvgSceneRenderer,
    bind_semantic_receipts,
    code_transform_program,
    failure_explanation_program,
    resolve_python_symbol,
    result_to_dict,
    verify_python_symbol_contract,
)


def test_beast_speaks_same_semantics_with_controlled_style_variation():
    program = failure_explanation_program()
    engine = SemanticExpressionEngine()

    technical = engine.compile(program, style="technical")
    conversational = engine.compile(program, style="conversational")

    tech_text = json.loads(technical.text_artifact.content)["text"]
    convo_text = json.loads(conversational.text_artifact.content)["text"]
    assert technical.program.semantic_digest == conversational.program.semantic_digest
    assert technical.discourse_plan.digest != conversational.discourse_plan.digest
    assert technical.text_artifact.digest != conversational.text_artifact.digest
    assert tech_text != convo_text
    assert "service certificate" in tech_text
    assert "mTLS handshake" in tech_text
    assert "does not establish why certificate was not rotated" in tech_text
    assert technical.joined_receipt["joined_verification"] is True
    assert conversational.joined_receipt["joined_verification"] is True
    assert technical.joined_receipt["provider_calls_used"] == 0


def test_beast_draws_from_semantic_program_not_text_artifact():
    program = failure_explanation_program()
    result = SemanticExpressionEngine().compile(program, style="executive")

    scene = result.scene_plan
    assert scene.semantic_digest == program.semantic_digest
    assert len(scene.nodes) >= 4
    assert len(scene.edges) == 3
    svg = result.visual_artifact.content.decode("utf-8")
    assert program.semantic_digest in svg
    assert "uncertainty boundary" in svg
    assert "why_certificate_was_not_rotated" in svg
    assert result.joined_receipt["visual_from_semantics_not_text"] is True


def test_beast_codes_sourceplan_from_constraints_without_applying_mutation():
    result = SemanticExpressionEngine().compile(code_transform_program(), style="forensic")

    assert result.sourceplan.status == "draft_requires_approval"
    assert result.sourceplan.approval_required is True
    assert len(result.sourceplan.operations) == 1
    operation = result.sourceplan.operations[0]
    assert operation["operation_type"] == "typed_ast_transform"
    assert operation["target_symbol"] == "app.kernel.registry.provider_registry.ProviderRegistry"
    assert operation["transformation"] == "add_retry_damping"
    assert operation["public_api_preserved"] is True
    assert "public_api_preserved" in result.sourceplan.preconditions
    assert result.joined_receipt["sourceplan_from_semantics_not_text"] is True
    assert result.joined_receipt["provider_calls_used"] == 0


def test_sourceplan_refuses_when_code_authority_missing():
    program = code_transform_program()
    refused = SemanticProgram(
        program_id=program.program_id + ":no-authority",
        intent=program.intent,
        entities=program.entities,
        claims=program.claims,
        edges=program.edges,
        boundaries=program.boundaries,
        permissions={**program.permissions, "sourceplan_allowed": False},
        created_at=program.created_at,
    )

    result = SemanticExpressionEngine().compile(refused)

    assert result.sourceplan.status == "refused_missing_code_authority_or_precondition"
    assert result.sourceplan.operations == ()
    assert result.verification["joined_verification"] is True


def test_joined_verifier_rejects_text_tamper():
    result = SemanticExpressionEngine().compile(failure_explanation_program())
    tampered_text = replace(result.text_artifact, content=result.text_artifact.content.replace(b"expired", b"revoked"))

    receipt, verification = ExpressionVerifier().verify(
        program=result.program,
        discourse_plan=result.discourse_plan,
        text_artifact=tampered_text,
        scene_plan=result.scene_plan,
        visual_artifact=result.visual_artifact,
        sourceplan=result.sourceplan,
        residual_decision=result.residual_decision,
    )

    assert verification["joined_verification"] is False
    assert "text_artifact_drift" in verification["failure_classes"]
    assert receipt["joined_verification"] is False


def test_result_packet_is_canonical_and_audit_friendly():
    result = SemanticExpressionEngine().compile(code_transform_program(), style="tutorial")
    payload = result_to_dict(result, include_artifacts=True)

    assert payload["semantic_program"]["semantic_digest"] == result.program.semantic_digest
    assert payload["text_artifact"]["content"].startswith("{")
    assert payload["visual_artifact"]["content"].startswith("<svg")
    assert payload["joined_receipt"]["meaning_first"] is True
    assert payload["joined_receipt"]["joined_verification"] is True


def test_semantic_validator_refuses_mutually_contradictory_claims():
    base = failure_explanation_program()
    hostile = SemanticProgram(
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
    )

    result = SemanticExpressionEngine().compile(hostile)

    assert result.residual_decision["action"] == "refuse"
    assert "mutually_contradictory_claims" in result.residual_decision["critical_issue_classes"]
    assert result.joined_receipt["ordinary_answer_available"] is False
    assert result.text_artifact.media_type == "application/vnd.beast.semantic-refusal+json"
    assert result.sourceplan.status == "refused_by_semantic_validator"
    assert result.joined_receipt["joined_verification"] is True


def test_semantic_validator_refuses_reversed_causal_chain():
    base = failure_explanation_program()
    hostile = SemanticProgram(
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
    )

    result = SemanticExpressionEngine().compile(hostile)

    assert result.residual_decision["action"] == "refuse"
    assert "causal_direction_or_conclusion_missing" in result.residual_decision["critical_issue_classes"]
    assert result.joined_receipt["ordinary_answer_available"] is False


def test_semantic_validator_refuses_circular_causal_chain():
    base = failure_explanation_program()
    hostile = SemanticProgram(
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
    )

    result = SemanticExpressionEngine().compile(hostile)

    assert result.residual_decision["action"] == "refuse"
    assert "circular_causal_chain" in result.residual_decision["critical_issue_classes"]
    assert result.visual_artifact.status == "refused"


def test_unbounded_unsupported_claim_forces_dedicated_refusal_artifact():
    base = failure_explanation_program()
    hostile = SemanticProgram(
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
    )

    result = SemanticExpressionEngine().compile(hostile)

    assert result.residual_decision["action"] == "refuse"
    assert "unsupported_claim_without_boundary" in result.residual_decision["critical_issue_classes"]
    assert result.joined_receipt["ordinary_answer_available"] is False
    assert result.joined_receipt["refusal_enforced"] is True
    assert result.text_artifact.status == "refused"
    assert result.visual_artifact.status == "refused"


def test_nonexistent_code_symbol_is_not_marked_resolved():
    base = code_transform_program()
    hostile = SemanticProgram(
        program_id=base.program_id + ":missing-symbol",
        intent=base.intent,
        entities=base.entities,
        claims=tuple(
            replace(claim, value="no.such.module.NoSuchClass")
            if claim.predicate == "target_symbol"
            else claim
            for claim in base.claims
        ),
        edges=base.edges,
        boundaries=base.boundaries,
        permissions=base.permissions,
        created_at=base.created_at,
    )

    result = SemanticExpressionEngine().compile(hostile)

    assert resolve_python_symbol("no.such.module.NoSuchClass")["resolved"] is False
    assert result.residual_decision["action"] == "refuse"
    assert "target_symbol_not_resolved" in result.residual_decision["critical_issue_classes"]
    assert result.sourceplan.status == "refused_by_semantic_validator"
    assert result.sourceplan.operations == ()


def test_independent_visual_verifier_rejects_canvas_overflow_even_when_renderer_recomputes():
    result = SemanticExpressionEngine().compile(failure_explanation_program())
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

    assert verification["joined_verification"] is False
    assert any(item.startswith("visual_node_overflow:") for item in verification["failure_classes"])
    assert receipt["independent_visual_entailment_valid"] is False


def test_residual_required_claim_does_not_masquerade_as_known_fact():
    program = bind_semantic_receipts(SemanticProgram(
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
    ))

    result = SemanticExpressionEngine().compile(program)
    text = json.loads(result.text_artifact.content)["text"]

    assert result.residual_decision["action"] == "bounded_residual"
    assert result.text_artifact.media_type == "application/vnd.beast.semantic-residual-pending+json"
    assert result.joined_receipt["ordinary_answer_available"] is False
    assert result.joined_receipt["residual_pending_enforced"] is True
    assert "Service A was compromised" not in text
    assert result.joined_receipt["joined_verification"] is True


def test_stale_causal_source_cannot_generate_current_causal_assertion():
    base = failure_explanation_program()
    stale = SemanticProgram(
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
    )

    result = SemanticExpressionEngine().compile(stale)

    assert result.residual_decision["action"] == "refuse"
    assert "causal_edge_lacks_current_authority" in result.residual_decision["critical_issue_classes"]
    assert result.joined_receipt["ordinary_answer_available"] is False


def test_unsupported_causal_edge_cannot_be_narrated_as_supported_cause():
    base = failure_explanation_program()
    unsupported_edge = SemanticProgram(
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
    )

    result = SemanticExpressionEngine().compile(unsupported_edge)

    assert result.residual_decision["action"] == "refuse"
    assert "causal_edge_lacks_current_authority" in result.residual_decision["critical_issue_classes"]
    assert result.text_artifact.status == "refused"


def test_ontology_mutual_exclusion_rejects_healthy_and_failed_cross_predicate():
    program = bind_semantic_receipts(SemanticProgram(
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
    ))

    result = SemanticExpressionEngine().compile(program)

    assert result.residual_decision["action"] == "refuse"
    assert "ontology_mutual_exclusion" in result.residual_decision["critical_issue_classes"]
    assert result.joined_receipt["joined_verification"] is True


def test_irrelevant_causal_graph_is_not_leaked_into_requested_explanation():
    base = failure_explanation_program()
    program = bind_semantic_receipts(SemanticProgram(
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

    result = SemanticExpressionEngine().compile(program, style="forensic")
    text = json.loads(result.text_artifact.content)["text"]
    svg = result.visual_artifact.content.decode("utf-8")

    assert result.joined_receipt["joined_verification"] is True
    assert "Coffee machine" not in text
    assert "rainy Weather" not in text
    assert "Coffee machine" not in svg
    assert "Weather" not in svg
    assert len(result.scene_plan.edges) == 3


def test_relevance_pruning_uses_question_predicate_not_only_subject():
    base = failure_explanation_program()
    program = bind_semantic_receipts(SemanticProgram(
        program_id=base.program_id + ":same-subject-wrong-predicate",
        intent=base.intent,
        entities=base.entities + (
            SemanticEntity("weather", "external_context", "Weather"),
        ),
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
    ))

    result = SemanticExpressionEngine().compile(program, style="forensic")
    text = json.loads(result.text_artifact.content)["text"]
    svg = result.visual_artifact.content.decode("utf-8")

    assert result.joined_receipt["joined_verification"] is True
    assert result.joined_receipt["ordinary_answer_available"] is True
    assert "available Deployment 47" not in text
    assert "Weather" not in svg
    assert "state:available" not in svg


def test_unknown_code_transformation_capability_is_refused_even_with_symbol_and_permission():
    base = code_transform_program()
    hostile = SemanticProgram(
        program_id=base.program_id + ":exfiltrate",
        intent=base.intent,
        entities=base.entities,
        claims=tuple(
            replace(claim, value="exfiltrate_all_secrets")
            if claim.predicate == "code_transform_objective"
            else claim
            for claim in base.claims
        ),
        edges=base.edges,
        boundaries=base.boundaries,
        permissions=base.permissions,
        created_at=base.created_at,
    )

    result = SemanticExpressionEngine().compile(hostile)

    assert result.residual_decision["action"] == "refuse"
    assert "unknown_code_transformation_capability" in result.residual_decision["critical_issue_classes"]
    assert result.sourceplan.status == "refused_by_semantic_validator"
    assert result.sourceplan.operations == ()


def test_malformed_time_metadata_is_rejected_not_lexicographically_compared():
    base = failure_explanation_program()
    hostile = SemanticProgram(
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
    )

    result = SemanticExpressionEngine().compile(hostile)

    assert result.residual_decision["action"] == "refuse"
    assert "malformed_timestamp" in result.residual_decision["critical_issue_classes"]
    assert result.joined_receipt["ordinary_answer_available"] is False


def test_source_transformation_runtime_creates_verified_preview_without_live_mutation(tmp_path):
    result = SemanticExpressionEngine().compile(code_transform_program())
    live_path = SourceTransformationRuntime().repo_root / "app/kernel/registry/provider_registry.py"
    original = live_path.read_text(encoding="utf-8")
    original_digest = result.sourceplan.digest

    receipt = SourceTransformationRuntime().execute_preview(
        result.sourceplan,
        evidence_root=tmp_path / "source-runtime",
        run_id="runtime-success",
    )
    diff_text = (tmp_path / "source-runtime" / "preview.diff").read_text(encoding="utf-8")
    modified_text = (tmp_path / "source-runtime" / "disposable_worktree" / "app/kernel/registry/provider_registry.py").read_text(encoding="utf-8")

    assert receipt["status"] == "verified_preview"
    assert receipt["beast_object_type"] == "semantic_source_transformation_preview_receipt"
    assert receipt["sourceplan_digest"] == original_digest
    assert receipt["compile_ok"] is True
    assert receipt["structural_verifier"]["passed"] is True
    assert receipt["provider_calls_used"] == 0
    assert receipt["preview_only"] is True
    assert receipt["approval_required_before_apply"] is True
    assert receipt["live_source_mutated"] is False
    assert live_path.read_text(encoding="utf-8") == original
    assert "RETRY_DAMPING_POLICY" in diff_text
    assert "def retry_damping_policy" in diff_text
    assert "def retry_damping_policy" in modified_text


def test_source_transformation_runtime_refuses_non_executable_sourceplan(tmp_path):
    result = SemanticExpressionEngine().compile(failure_explanation_program())

    receipt = SourceTransformationRuntime().execute_preview(
        result.sourceplan,
        evidence_root=tmp_path / "source-runtime-negative",
        run_id="runtime-negative",
    )

    assert receipt["beast_object_type"] == "semantic_source_transformation_negative_receipt"
    assert receipt["status"] == "refused"
    assert "sourceplan_not_draft_requires_approval" in receipt["failure_classes"]
    assert receipt["provider_calls_used"] == 0


def test_boolean_false_failed_realizes_as_negative_proposition_not_failure():
    program = bind_semantic_receipts(SemanticProgram(
        program_id="semantic:false-failed",
        intent=SemanticIntent("answer_status", "service-a", "Did Service A fail?"),
        entities=(SemanticEntity("service-a", "service", "Service A"),),
        claims=(
            SemanticClaim("claim:not-failed", "failed", "service-a", value=False, evidence_refs=("sha256:" + "7" * 64,), metadata={"evidence_authority": "verified_receipt"}),
        ),
        created_at="2026-08-04T00:00:00+00:00",
    ))

    result = SemanticExpressionEngine().compile(program)
    text = json.loads(result.text_artifact.content)["text"]

    assert result.joined_receipt["joined_verification"] is True
    assert result.joined_receipt["ordinary_answer_available"] is True
    assert "Service A did not fail." in text
    assert "Service A failed." not in text


def test_boolean_false_rolled_back_realizes_as_negative_proposition():
    program = bind_semantic_receipts(SemanticProgram(
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
    ))

    result = SemanticExpressionEngine().compile(program)
    text = json.loads(result.text_artifact.content)["text"]

    assert result.joined_receipt["joined_verification"] is True
    assert "Deployment X did not roll back." in text
    assert "Deployment X rolled back." not in text


def test_sourceplan_refuses_when_public_api_preservation_value_is_false():
    base = code_transform_program()
    hostile = SemanticProgram(
        program_id=base.program_id + ":public-api-false",
        intent=base.intent,
        entities=base.entities,
        claims=tuple(
            replace(claim, value=False)
            if claim.predicate == "preserve_public_api"
            else claim
            for claim in base.claims
        ),
        edges=base.edges,
        boundaries=base.boundaries,
        permissions=base.permissions,
        created_at=base.created_at,
    )

    result = SemanticExpressionEngine().compile(hostile)

    assert result.residual_decision["action"] == "refuse"
    assert "public_api_preservation_not_authorized" in result.residual_decision["critical_issue_classes"]
    assert result.sourceplan.status == "refused_by_semantic_validator"
    assert result.sourceplan.operations == ()


def test_source_transformation_registry_denies_providerregistry_surname_target():
    denied = SourceTransformationCapabilityRegistry().lookup(
        "add_retry_damping",
        "app.kernel.registry.some_other_module.ProviderRegistry",
    )

    assert denied["allowed"] is False
    assert "exact target" in denied["reason"]


def test_generic_answer_intent_still_refuses_stale_causal_chain():
    program = SemanticProgram(
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
    )

    result = SemanticExpressionEngine().compile(program)

    assert result.residual_decision["action"] == "refuse"
    assert "causal_edge_lacks_current_authority" in result.residual_decision["critical_issue_classes"]
    assert result.joined_receipt["ordinary_answer_available"] is False


def test_visual_entailment_requires_full_temperature_proposition():
    program = bind_semantic_receipts(SemanticProgram(
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
    ))

    result = SemanticExpressionEngine().compile(program)
    text = json.loads(result.text_artifact.content)["text"]
    svg = result.visual_artifact.content.decode("utf-8")

    assert result.joined_receipt["joined_verification"] is True
    assert "900degC" in text
    assert "900degC" in svg
    assert "temperature:900degC" in svg


def test_supported_operational_claim_without_evidence_authority_is_refused():
    program = SemanticProgram(
        program_id="semantic:supported-self-declared",
        intent=SemanticIntent("answer_status", "service-a", "Is Service A healthy?"),
        entities=(SemanticEntity("service-a", "service", "Service A"),),
        claims=(
            SemanticClaim(
                "claim:self-declared-supported",
                "state",
                "service-a",
                value="healthy",
                confidence="verified",
                evidence_refs=("sha256:" + "b" * 64,),
            ),
        ),
        created_at="2026-08-04T00:00:00+00:00",
    )

    result = SemanticExpressionEngine().compile(program)

    assert result.residual_decision["action"] == "refuse"
    assert "supported_claim_lacks_evidence_authority" in result.residual_decision["critical_issue_classes"]


def test_typed_law_rejects_bool_like_string_for_boolean_predicate():
    program = SemanticProgram(
        program_id="semantic:typed-bool-string",
        intent=SemanticIntent("answer_status", "service-a", "Did Service A fail?"),
        entities=(SemanticEntity("service-a", "service", "Service A"),),
        claims=(
            SemanticClaim("claim:failed-string", "failed", "service-a", value="true", evidence_refs=("sha256:" + "3" * 64,), metadata={"evidence_authority": "verified_receipt"}),
        ),
        created_at="2026-08-04T00:00:00+00:00",
    )

    result = SemanticExpressionEngine().compile(program)

    assert result.residual_decision["action"] == "refuse"
    assert "predicate_value_type_mismatch" in result.residual_decision["critical_issue_classes"]
    assert result.joined_receipt["ordinary_answer_available"] is False


def test_typed_law_rejects_unknown_predicate_before_expression():
    program = SemanticProgram(
        program_id="semantic:unknown-predicate",
        intent=SemanticIntent("answer_status", "service-a", "What is Service A doing?"),
        entities=(SemanticEntity("service-a", "service", "Service A"),),
        claims=(
            SemanticClaim("claim:vibes", "vibes_like", "service-a", value="fine"),
        ),
        created_at="2026-08-04T00:00:00+00:00",
    )

    result = SemanticExpressionEngine().compile(program)

    assert result.residual_decision["action"] == "refuse"
    assert "unknown_predicate" in result.residual_decision["critical_issue_classes"]


def test_typed_law_rejects_invalid_evidence_ref_shape_for_supported_operational_fact():
    program = SemanticProgram(
        program_id="semantic:bad-evidence-ref",
        intent=SemanticIntent("answer_status", "service-a", "Did Service A fail?"),
        entities=(SemanticEntity("service-a", "service", "Service A"),),
        claims=(
            SemanticClaim("claim:failed-bad-ref", "failed", "service-a", value=True, evidence_refs=("sha256:not-real",), metadata={"evidence_authority": "verified_receipt"}),
        ),
        created_at="2026-08-04T00:00:00+00:00",
    )

    result = SemanticExpressionEngine().compile(program)

    assert result.residual_decision["action"] == "refuse"
    assert "invalid_evidence_ref" in result.residual_decision["critical_issue_classes"]


def test_claim_evidence_authority_label_without_resolvable_receipt_is_refused():
    program = SemanticProgram(
        program_id="semantic:fake-evidence-receipt",
        intent=SemanticIntent("answer_status", "service-a", "Did Service A fail?"),
        entities=(SemanticEntity("service-a", "service", "Service A"),),
        claims=(
            SemanticClaim(
                "claim:failed-fake-receipt",
                "failed",
                "service-a",
                value=True,
                evidence_refs=("sha256:" + "1" * 64,),
                metadata={"evidence_authority": "verified_receipt"},
            ),
        ),
        created_at="2026-08-04T00:00:00+00:00",
    )

    result = SemanticExpressionEngine().compile(program)

    assert result.residual_decision["action"] == "refuse"
    assert "evidence_receipt_missing" in result.residual_decision["critical_issue_classes"]


def test_supported_edge_requires_own_relationship_receipt_not_only_endpoint_receipts():
    base = failure_explanation_program()
    missing_edge_receipt = SemanticProgram(
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
    )

    result = SemanticExpressionEngine().compile(missing_edge_receipt)

    assert result.residual_decision["action"] == "refuse"
    assert "supported_edge_lacks_relationship_authority" in result.residual_decision["critical_issue_classes"]
    assert "relationship_evidence_required_missing" in result.residual_decision["critical_issue_classes"]


def test_ontology_rejects_failed_state_against_false_failed_boolean():
    program = bind_semantic_receipts(SemanticProgram(
        program_id="semantic:failed-state-false-boolean",
        intent=SemanticIntent("answer_status", "service-a", "Did Service A fail?"),
        entities=(SemanticEntity("service-a", "service", "Service A"),),
        claims=(
            SemanticClaim("claim:state-failed", "state", "service-a", value="failed"),
            SemanticClaim("claim:not-failed", "failed", "service-a", value=False),
        ),
        created_at="2026-08-04T00:00:00+00:00",
    ))

    result = SemanticExpressionEngine().compile(program)

    assert result.residual_decision["action"] == "refuse"
    assert "ontology_mutual_exclusion" in result.residual_decision["critical_issue_classes"]


def test_typed_quantity_rejects_semantically_invalid_temperature_unit():
    program = SemanticProgram(
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
    )

    result = SemanticExpressionEngine().compile(program)

    assert result.residual_decision["action"] == "refuse"
    assert "predicate_value_type_mismatch" in result.residual_decision["critical_issue_classes"]


def test_registry_law_realizes_enabled_false_without_fallback_phrase():
    program = SemanticProgram(
        program_id="semantic:feature-disabled",
        intent=SemanticIntent("answer_status", "feature-x", "Is Feature X enabled?"),
        entities=(SemanticEntity("feature-x", "feature", "Feature X"),),
        claims=(SemanticClaim("claim:feature-not-enabled", "enabled", "feature-x", value=False),),
        created_at="2026-08-04T00:00:00+00:00",
    )

    result = SemanticExpressionEngine().compile(program)
    text = json.loads(result.text_artifact.content)["text"]

    assert result.joined_receipt["joined_verification"] is True
    assert "Feature X was not enabled." in text
    assert "has enabled: False" not in text


def test_independent_text_entailment_rejects_noncausal_value_substitution():
    result = SemanticExpressionEngine().compile(bind_semantic_receipts(SemanticProgram(
        program_id="semantic:reactor-temperature",
        intent=SemanticIntent("answer_status", "reactor-7", "What is Reactor 7 temperature?"),
        entities=(SemanticEntity("reactor-7", "reactor", "Reactor 7"),),
        claims=(
            SemanticClaim(
                "claim:reactor-temp",
                "temperature",
                "reactor-7",
                value={"magnitude": 900, "unit": "degC", "dimension": "temperature"},
                metadata={"evidence_authority": "sensorium_receipt"},
            ),
        ),
        created_at="2026-08-04T00:00:00+00:00",
    )))
    tampered_text = replace(result.text_artifact, content=result.text_artifact.content.replace(b"900degC", b"100degC"))

    receipt, verification = ExpressionVerifier().verify(
        program=result.program,
        validation_report=result.validation_report,
        discourse_plan=result.discourse_plan,
        text_artifact=tampered_text,
        scene_plan=result.scene_plan,
        visual_artifact=result.visual_artifact,
        sourceplan=result.sourceplan,
        residual_decision=result.residual_decision,
    )

    assert receipt["joined_verification"] is False
    assert "text_missing_proposition_value:claim:reactor-temp" in verification["failure_classes"]


def test_python_symbol_contract_rejects_fake_exact_path_and_class_without_registered_api(tmp_path):
    fake_repo = tmp_path / "repo"
    fake_module = fake_repo / "app" / "kernel" / "registry" / "provider_registry.py"
    fake_module.parent.mkdir(parents=True)
    fake_module.write_text("class ProviderRegistry:\n    pass\n", encoding="utf-8")
    capability = SourceTransformationCapabilityRegistry().lookup(
        "add_retry_damping",
        "app.kernel.registry.provider_registry.ProviderRegistry",
    )

    contract = verify_python_symbol_contract(
        "app.kernel.registry.provider_registry.ProviderRegistry",
        capability,
        repo_root=fake_repo,
    )

    assert capability["allowed"] is True
    assert contract["passed"] is False
    assert "required_method_missing:records" in contract["failure_classes"]
    assert "required_import_missing:Dict" in contract["failure_classes"]


def test_typed_law_rejects_target_identity_kind_mismatch():
    base = code_transform_program()
    hostile = SemanticProgram(
        program_id=base.program_id + ":wrong-target-kind",
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
        edges=base.edges,
        permissions=base.permissions,
        created_at=base.created_at,
    )

    result = SemanticExpressionEngine().compile(hostile)

    assert result.residual_decision["action"] == "refuse"
    assert "target_identity_kind_mismatch" in result.residual_decision["critical_issue_classes"]


def test_typed_law_rejects_supported_claim_with_expired_temporal_authority():
    program = SemanticProgram(
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
                metadata={
                    "evidence_authority": "verified_receipt",
                    "observed_at": "2026-08-03T00:00:00+00:00",
                    "expires_at": "2026-08-03T01:00:00+00:00",
                },
            ),
        ),
        created_at="2026-08-04T00:00:00+00:00",
    )

    result = SemanticExpressionEngine().compile(program)

    assert result.residual_decision["action"] == "refuse"
    assert "temporal_authority_expired" in result.residual_decision["critical_issue_classes"]


def test_typed_law_rejects_future_observation_time():
    program = SemanticProgram(
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
    )

    result = SemanticExpressionEngine().compile(program)

    assert result.residual_decision["action"] == "refuse"
    assert "temporal_authority_future_observation" in result.residual_decision["critical_issue_classes"]


def test_typed_law_rejects_supported_claim_with_unverified_evidence_state():
    program = SemanticProgram(
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
    )

    result = SemanticExpressionEngine().compile(program)

    assert result.residual_decision["action"] == "refuse"
    assert "supported_claim_lacks_verified_evidence_state" in result.residual_decision["critical_issue_classes"]
