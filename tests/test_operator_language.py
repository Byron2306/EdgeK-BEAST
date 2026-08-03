import pytest

from app.kernel.compute.operator_language import (
    AnswerFrame,
    BOUNDED_DOMAIN_SLOT_SCHEMA,
    CandidateMeaning,
    EvidenceBinding,
    MeaningCrystal,
    MeaningResolutionState,
    OperatorMeaningDomain,
    OperatorPromptCase,
    build_residual_lexicalization_payload,
    compile_bounded_meaning,
    realize_answer_frame,
    run_operator_language_acceptance,
)
from app.kernel.compute.residual_contracts import sha256_digest


def _digest(value):
    return sha256_digest(value)


def _evidence():
    return EvidenceBinding(
        evidence_digest=_digest({"service": "beast"}),
        source="services.yaml",
        world_digest=_digest({"world": "local-runtime"}),
        policy_digest=_digest({"policy": "operator-language-v1"}),
        temporal_scope_digest=_digest({"date": "2026-08-03"}),
    )


def _meaning():
    return CandidateMeaning(
        meaning_id="meaning:service-registry-summary",
        domain=OperatorMeaningDomain.SERVICE,
        intent="summarize_service_registry",
        slots={"service": "beast", "port": 8101},
        evidence=(_evidence(),),
        resolution_state=MeaningResolutionState.RESOLVED,
        confidence=1.0,
        negative_conditions=("service registry digest drift",),
    )


def _frame(meaning):
    return AnswerFrame(
        frame_id="frame:service-registry-summary",
        meaning_digest=meaning.meaning_digest,
        template_id="service_summary.neutral.v1",
        slots={"title": "BEAST service registry", "body": "BEAST is bound to 127.0.0.1:8101."},
        evidence_digests=(_evidence().evidence_digest,),
        resolution_state=MeaningResolutionState.RESOLVED,
    )


def test_meaning_crystal_binds_meaning_frame_evidence_and_scope():
    meaning = _meaning()
    frame = _frame(meaning)
    crystal = MeaningCrystal(
        crystal_id="meaning-crystal:service-registry-summary",
        meaning=meaning,
        answer_frame=frame,
        schema_digest=_digest({"schema": "operator-language-v1"}),
        discourse_digest=_digest({"utterance": "what is my beast endpoint"}),
        world_digest=_evidence().world_digest,
        capability_digest=_digest({"capability": "read_registry"}),
        policy_digest=_evidence().policy_digest,
        temporal_scope_digest=_evidence().temporal_scope_digest,
        verifier_id="operator-language-contract-test",
        verification_evidence_digest=_evidence().binding_digest,
    )

    assert crystal.crystal_digest.startswith("sha256:")
    assert realize_answer_frame(frame) == "BEAST service registry\n\nBEAST is bound to 127.0.0.1:8101."
    assert realize_answer_frame(frame, tone="concise") == "BEAST service registry: BEAST is bound to 127.0.0.1:8101."
    assert realize_answer_frame(frame, tone="status") == "[BEAST service registry] BEAST is bound to 127.0.0.1:8101."


def test_bounded_operator_domains_compile_to_meaning_and_answer_frame():
    examples = {
        OperatorMeaningDomain.SERVICE: {"name": "beast", "status": "healthy"},
        OperatorMeaningDomain.CONTAINER: {"name": "beast-api", "image": "edgek/beast:local"},
        OperatorMeaningDomain.MODEL: {"name": "qwen2.5", "provider": "ollama"},
        OperatorMeaningDomain.REPOSITORY: {"path": "/repo", "branch": "main"},
        OperatorMeaningDomain.FILE: {"path": "app/main.py", "state": "present"},
        OperatorMeaningDomain.DEPLOYMENT: {"name": "local", "environment": "operator"},
        OperatorMeaningDomain.LOG: {"source": "guardian", "summary": "no restarts"},
        OperatorMeaningDomain.CACHE: {"name": "semantic", "state": "active"},
        OperatorMeaningDomain.CRYSTAL: {"crystal_id": "crystal:1", "task_family": "service"},
        OperatorMeaningDomain.COMMONS_NODE: {"node_id": "commons:1", "space": "local"},
        OperatorMeaningDomain.SPACE: {"space_id": "space:1", "runtime": "cpu"},
    }

    assert set(examples) == set(BOUNDED_DOMAIN_SLOT_SCHEMA)
    for domain, slots in examples.items():
        meaning, frame = compile_bounded_meaning(
            meaning_id=f"meaning:{domain.value}",
            domain=domain,
            intent=f"summarize_{domain.value}",
            slots=slots,
            evidence=(_evidence(),),
        )
        assert meaning.domain is domain
        assert meaning.resolution_state is MeaningResolutionState.RESOLVED
        assert frame.resolution_state is MeaningResolutionState.RESOLVED
        assert realize_answer_frame(frame)


def test_resolved_meaning_requires_evidence():
    with pytest.raises(ValueError, match="resolved meanings require evidence"):
        CandidateMeaning(
            meaning_id="meaning:unsupported",
            domain=OperatorMeaningDomain.LOG,
            intent="summarize_logs",
            slots={"claim": "healthy"},
            evidence=(),
            resolution_state=MeaningResolutionState.RESOLVED,
            confidence=1.0,
        )


def test_unresolved_answer_frame_names_only_unresolved_fields():
    meaning = _meaning()
    with pytest.raises(ValueError, match="resolved answer frames cannot carry unresolved fields"):
        AnswerFrame(
            frame_id="frame:bad",
            meaning_digest=meaning.meaning_digest,
            template_id="bad.v1",
            slots={"title": "bad", "body": "bad"},
            evidence_digests=(_evidence().evidence_digest,),
            resolution_state=MeaningResolutionState.RESOLVED,
            unresolved_fields=("body",),
        )


def test_residual_lexicalization_payload_exposes_only_declared_unresolved_fields():
    meaning, frame = compile_bounded_meaning(
        meaning_id="meaning:service-unresolved",
        domain=OperatorMeaningDomain.SERVICE,
        intent="summarize_service",
        slots={"name": "beast", "status": "healthy", "title": "Do not leak me", "body": "<unresolved>"},
        evidence=(_evidence(),),
        unresolved_fields=("body",),
    )

    payload = build_residual_lexicalization_payload(frame, target={"path": "operator"})

    assert meaning.resolution_state is MeaningResolutionState.UNRESOLVED
    assert payload["unresolved_fields"] == ["body"]
    assert payload["allowed_output"] == {"body": "string"}
    assert "Do not leak me" not in str(payload)
    assert "resolved_field_digests" in payload
    assert set(payload["resolved_field_digests"]) == {"name", "status", "title"}


def test_meaning_crystal_rejects_unbound_answer_frame():
    meaning = _meaning()
    other = _meaning()
    frame = AnswerFrame(
        frame_id="frame:other",
        meaning_digest=_digest({"different": other.meaning_digest}),
        template_id="service_summary.neutral.v1",
        slots={"title": "Other", "body": "Other"},
        evidence_digests=(_evidence().evidence_digest,),
        resolution_state=MeaningResolutionState.RESOLVED,
    )

    with pytest.raises(ValueError, match="answer frame is not bound"):
        MeaningCrystal(
            crystal_id="meaning-crystal:bad-binding",
            meaning=meaning,
            answer_frame=frame,
            schema_digest=_digest({"schema": "operator-language-v1"}),
            discourse_digest=_digest({"utterance": "what is my beast endpoint"}),
            world_digest=_evidence().world_digest,
            capability_digest=_digest({"capability": "read_registry"}),
            policy_digest=_evidence().policy_digest,
            temporal_scope_digest=_evidence().temporal_scope_digest,
            verifier_id="operator-language-contract-test",
            verification_evidence_digest=_evidence().binding_digest,
        )


def test_operator_language_acceptance_corpus_covers_200_realistic_prompts():
    examples = {
        OperatorMeaningDomain.SERVICE: {"name": "beast", "status": "healthy"},
        OperatorMeaningDomain.CONTAINER: {"name": "beast-api", "image": "edgek/beast:local"},
        OperatorMeaningDomain.MODEL: {"name": "qwen2.5", "provider": "ollama"},
        OperatorMeaningDomain.REPOSITORY: {"path": "/repo", "branch": "main"},
        OperatorMeaningDomain.FILE: {"path": "app/main.py", "state": "present"},
        OperatorMeaningDomain.DEPLOYMENT: {"name": "local", "environment": "operator"},
        OperatorMeaningDomain.LOG: {"source": "guardian", "summary": "stable"},
        OperatorMeaningDomain.CACHE: {"name": "semantic", "state": "active"},
        OperatorMeaningDomain.CRYSTAL: {"crystal_id": "crystal:1", "task_family": "service"},
        OperatorMeaningDomain.COMMONS_NODE: {"node_id": "commons:1", "space": "local"},
        OperatorMeaningDomain.SPACE: {"space_id": "space:1", "runtime": "cpu"},
    }
    domains = tuple(examples)
    cases = []
    for index in range(200):
        domain = domains[index % len(domains)]
        slots = {
            **examples[domain],
            "title": f"{domain.value} {index}",
            "body": f"{domain.value} {index} verified by evidence",
        }
        evidence = () if index % 17 == 0 else (_evidence(),)
        cases.append(
            OperatorPromptCase(
                case_id=f"case:{index:03d}",
                utterance=f"show me {domain.value} status {index}",
                domain=domain,
                intent=f"summarize_{domain.value}",
                slots=slots,
                evidence=evidence,
                tone=("neutral", "concise", "status")[index % 3],
            )
        )

    receipt = run_operator_language_acceptance(tuple(cases))

    assert receipt.case_count == 200
    assert receipt.unauthorized_actions == 0
    assert receipt.unsupported_factual_additions == 0
    assert receipt.ambiguous_cases == receipt.explicit_ambiguity_cases
    assert receipt.passed is True
