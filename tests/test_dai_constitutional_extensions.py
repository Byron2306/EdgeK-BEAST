from __future__ import annotations

from app.kernel.compute.deterministic_intelligence import sha256_digest
from app.kernel.dai.constitutional_extensions import (
    AuthorityLevel,
    AuthorityVector,
    CadenceObservation,
    CadencePolicy,
    DependencyGraph,
    EffectManifest,
    EffectObservation,
    EvidenceAtom,
    EvidenceMode,
    EvidenceRequirement,
    RevocationEvent,
    build_counterfactual_receipt,
    build_lawful_reentry_receipt,
    detect_authority_pollution,
    evaluate_cadence,
    propagate_revocation,
    run_constitutional_extensions_demo,
    verify_effect_containment,
    verify_evidence_sufficiency,
)


def test_effect_manifest_rejects_network_model_and_write_escape() -> None:
    manifest = EffectManifest(
        capability_id="cap:test",
        capability_digest=sha256_digest("cap:test"),
        permitted_reads=("ledger.json",),
        permitted_writes=("receipt.json",),
        network_destinations=(),
        syscalls=("openat", "read", "write"),
        tools=("deterministic_expression",),
        model_calls=(),
        resource_limits={"max_provider_calls": 0},
        expected_postconditions=("receipt_written",),
    )
    clean = verify_effect_containment(
        manifest,
        EffectObservation(
            capability_id="cap:test",
            observed_reads=("ledger.json",),
            observed_writes=("receipt.json",),
            observed_network_destinations=(),
            observed_syscalls=("openat", "read", "write"),
            observed_tools=("deterministic_expression",),
            observed_model_calls=(),
            resource_usage={"max_provider_calls": 0},
            postconditions=("receipt_written",),
        ),
    )
    hostile = verify_effect_containment(
        manifest,
        EffectObservation(
            capability_id="cap:test",
            observed_reads=("ledger.json",),
            observed_writes=("receipt.json", "/tmp/escape"),
            observed_network_destinations=("provider.example:443",),
            observed_syscalls=("openat", "read", "write", "connect"),
            observed_tools=("deterministic_expression",),
            observed_model_calls=("gemini",),
            resource_usage={"max_provider_calls": 1},
            postconditions=("receipt_written",),
        ),
    )

    assert clean["contained"] is True
    assert hostile["contained"] is False
    assert "write_escape" in hostile["red_gates"]
    assert "network_escape" in hostile["red_gates"]
    assert "model_call_escape" in hostile["red_gates"]


def test_evidence_strength_prevents_mapping_laundering_as_direct_observation() -> None:
    requirement = EvidenceRequirement(
        claim_id="claim:test",
        required_mode=EvidenceMode.DIRECT_OBSERVED,
        environment="hardware_live",
        allow_synthetic=False,
    )
    mapped = EvidenceAtom(
        claim_id="claim:test",
        evidence_mode=EvidenceMode.MAPPING_ONLY,
        environment="hardware_live",
        inheritance="mapped",
        synthetic=True,
        freshness="current",
        authority_weight="mapping_only",
        limitations=("not_direct",),
        evidence_digest=sha256_digest("mapped"),
    )
    direct = EvidenceAtom(
        claim_id="claim:test",
        evidence_mode=EvidenceMode.DIRECT_OBSERVED,
        environment="hardware_live",
        inheritance="direct",
        synthetic=False,
        freshness="current",
        authority_weight="direct",
        limitations=(),
        evidence_digest=sha256_digest("direct"),
    )

    assert verify_evidence_sufficiency(requirement, (mapped,))["evidence_sufficient"] is False
    assert verify_evidence_sufficiency(requirement, (direct,))["evidence_sufficient"] is True


def test_cadence_miss_turns_current_applicability_unknown() -> None:
    policy = CadencePolicy(
        capability_id="cap:test",
        observation_recurrence_seconds=60,
        corroboration_frequency_seconds=60,
        maximum_tolerated_drift_seconds=3,
        required_challenge_cadence_seconds=60,
        lease_renewal_condition="same_world_state",
        silence_threshold_seconds=120,
        trusted_time_source="test_clock",
        expires_at="2026-08-04T23:00:00+00:00",
    )
    stale = evaluate_cadence(
        policy,
        CadenceObservation(
            capability_id="cap:test",
            observed_at="2026-08-04T21:00:00+00:00",
            last_corroborated_at="2026-08-04T21:00:00+00:00",
            last_challenged_at="2026-08-04T21:00:00+00:00",
            now="2026-08-04T22:00:00+00:00",
            observed_drift_seconds=4,
        ),
    )

    assert stale["current_applicability"] == "unknown"
    assert stale["action"] == "reobserve"
    assert "observation_recurrence_missed" in stale["failures"]
    assert "trusted_time_drift_exceeded" in stale["failures"]


def test_authority_pollution_detector_blocks_rhetoric_source_and_normative_laundering() -> None:
    polluted = detect_authority_pollution(
        AuthorityVector(
            claim_id="claim:polluted",
            normative_authority=AuthorityLevel.PRODUCTION,
            epistemic_authority=AuthorityLevel.MAPPING,
            source_authority=AuthorityLevel.PRODUCTION,
            data_authority=AuthorityLevel.SYNTHETIC,
            rhetorical_confidence=AuthorityLevel.PRODUCTION,
            requested_authority=AuthorityLevel.DIRECT_EVIDENCE,
        ),
    )

    assert polluted["authority_pollution_detected"] is True
    assert "rhetorical_confidence_exceeds_epistemic_authority" in polluted["illegal_transitions"]
    assert "source_identity_laundered_as_claim_correctness" in polluted["illegal_transitions"]
    assert "normative_authority_laundered_as_epistemic_authority" in polluted["illegal_transitions"]


def test_dependency_revocation_reaches_claim_expression_quorum_and_lease() -> None:
    graph = DependencyGraph(
        graph_id="dep:test",
        nodes={
            "world:fact": {"node_type": "world_fact"},
            "claim:answer": {"node_type": "claim"},
            "expression:answer": {"node_type": "expression"},
            "quorum:answer": {"node_type": "quorum"},
            "lease:answer": {"node_type": "lease"},
        },
        edges=(
            ("world:fact", "claim:answer"),
            ("claim:answer", "expression:answer"),
            ("claim:answer", "quorum:answer"),
            ("quorum:answer", "lease:answer"),
        ),
    )
    receipt = propagate_revocation(
        graph,
        RevocationEvent(
            event_id="event:test",
            changed_node_id="world:fact",
            reason="topology_changed",
            observed_at="2026-08-04T22:00:00+00:00",
        ),
    )

    assert "claim:answer" in receipt["stale_nodes"]
    assert receipt["withdrawn_expressions"] == ("expression:answer",)
    assert receipt["superseded_quorum_results"] == ("quorum:answer",)
    assert receipt["revoked_leases"] == ("lease:answer",)


def test_counterfactual_and_lawful_reentry_are_digest_bound() -> None:
    counterfactual = build_counterfactual_receipt(
        answer_digest=sha256_digest("answer"),
        minimal_capability_set=(sha256_digest("capability"),),
        minimal_evidence_set=(sha256_digest("evidence"),),
        missing_fact_forces_refusal="visible_source_span_bound=false",
        contradictory_fact_reverses_result="source_contradicts_policy=true",
        organ_constraints={"sophia": {"may_veto": True, "may_approve_execution": False}},
    )
    reentry = build_lawful_reentry_receipt(
        refusal_digest=counterfactual["receipt_digest"],
        failed_criterion="visible_source_span_bound=false",
        cure_evidence=("exact_page_span_locator",),
        eligible_evidence_providers=("sophia",),
        appealable=True,
        fresh_world_state_required=True,
        permanent_prohibitions=("bypass_original_refusal",),
    )

    assert counterfactual["explainability_mode"] == "minimal_proof_object_not_chain_of_thought"
    assert reentry["refusal_digest"] == counterfactual["receipt_digest"]
    assert "rerun deterministic composition without bypassing refusal" in reentry["reentry_steps"]


def test_phase6_4_demo_accepts_clean_path_and_rejects_hostile_controls() -> None:
    truth = {
        "green": True,
        "receipt_digest": sha256_digest("phase6.2.truth"),
        "production_authority_allowed": False,
        "case_receipts": [{"expression_bundle_digest": sha256_digest("expression")}],
    }
    policy = {
        "verified": True,
        "policy_digest": sha256_digest("lineage.policy"),
    }

    receipt = run_constitutional_extensions_demo(
        phase6_2_truth_receipt=truth,
        lineage_policy_verification=policy,
    )

    assert receipt["green"] is True
    assert all(receipt["extension_gates"].values())
    assert all(receipt["hostile_controls"].values())
    assert "full_bounded_smt_model_checking" in receipt["deferred_extensions_not_claimed_green"]
    assert receipt["provider_calls_used"] == 0
    assert receipt["production_authority_allowed"] is False
