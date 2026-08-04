import json
from pathlib import Path

from app.kernel.compute.c4x_physical_truth_certificate import (
    CertificateLayer,
    REQUIRED_LAYERS,
    _source_linkage,
    build_c4x_physical_truth_certificate,
    empty_pending_sidecar,
)
from app.kernel.compute.deterministic_intelligence import sha256_digest
from scripts.run_c4x_physical_truth_certificate import run_physical_truth_certificate


def test_empty_physical_truth_certificate_refuses_all_public_credit():
    receipt = build_c4x_physical_truth_certificate(run_id="pytest-empty", **empty_pending_sidecar())

    assert receipt["public_credit_allowed"] is False
    assert receipt["truth_claim_allowed"] is False
    assert set(receipt["critical_failures"]) == set(REQUIRED_LAYERS)
    assert all(passed is False for passed in receipt["certificate_gates"].values())
    assert receipt["no_averaging_rule"] is True


def test_internal_provider_count_is_not_bpf_zero_provider_proof():
    sidecar = _complete_sidecar()
    sidecar["bpf_receipt"] = {
        "receipt_digest": sha256_digest({"bpf": "self-report-only"}),
        "provider_calls_used": 0,
    }

    receipt = build_c4x_physical_truth_certificate(run_id="pytest-bpf-refusal", **sidecar)

    assert receipt["certificate_gates"]["c4x_truth"] is True
    assert receipt["certificate_gates"]["bpf_witness"] is False
    assert receipt["public_credit_allowed"] is False
    bpf = [item for item in receipt["layer_verdicts"] if item["layer"] == "bpf_witness"][0]
    assert "outbound_connect_attempts" in bpf["missing"]
    assert "live_provider_comparator_observed_network" in bpf["missing"]


def test_fabricated_green_receipts_with_zero_digests_are_refused():
    sidecar = _complete_sidecar()
    zero = "sha256:" + ("0" * 64)
    for receipt in sidecar.values():
        receipt["receipt_digest"] = zero
        receipt["source_receipt_digest"] = zero
        receipt["attestation_digest"] = zero

    receipt = build_c4x_physical_truth_certificate(run_id="pytest-forgery", **sidecar)

    assert receipt["public_credit_allowed"] is False
    assert receipt["truth_claim_allowed"] is False
    assert set(receipt["critical_failures"]) == set(REQUIRED_LAYERS)
    assert all(passed is False for passed in receipt["certificate_gates"].values())
    for verdict in receipt["layer_verdicts"]:
        assert "receipt_digest_mismatch" in verdict["failure_reasons"]


def test_digest_bound_receipt_tamper_is_refused_even_when_booleans_stay_green():
    sidecar = _complete_sidecar()
    sidecar["pq_transport_receipt"]["reviewer_poison"] = "added after digest"

    receipt = build_c4x_physical_truth_certificate(run_id="pytest-tamper", **sidecar)

    assert receipt["certificate_gates"]["pq_transport"] is False
    assert receipt["public_credit_allowed"] is False
    pq = [item for item in receipt["layer_verdicts"] if item["layer"] == "pq_transport"][0]
    assert "receipt_digest_mismatch" in pq["failure_reasons"]


def test_contradictory_status_refused_even_when_required_fields_are_true():
    sidecar = _complete_sidecar()
    guardian = dict(sidecar["guardian_receipt"])
    guardian.pop("receipt_digest")
    guardian["status"] = "local_guardian_attack_suite_completed_producer_death_case_pending"
    sidecar["guardian_receipt"] = _with_digest(guardian)

    receipt = build_c4x_physical_truth_certificate(run_id="pytest-contradictory-status", **sidecar)

    assert receipt["certificate_gates"]["guardian_custody"] is False
    guardian_verdict = [item for item in receipt["layer_verdicts"] if item["layer"] == "guardian_custody"][0]
    assert any(reason.startswith("contradictory_status_") for reason in guardian_verdict["failure_reasons"])


def test_claimant_controlled_attestation_without_source_file_is_refused():
    sidecar = _complete_sidecar()
    c4x = dict(sidecar["c4x_receipt"])
    c4x.pop("receipt_digest")
    c4x.pop("source_artifacts")
    c4x["attestation_digest"] = sha256_digest(
        {
            "layer": CertificateLayer.C4X_TRUTH.value,
            "authority": c4x["authority"],
            "claim_boundary": c4x["claim_boundary"],
            "source_linkage": _source_linkage(c4x),
            "required_claims": {key: c4x.get(key) for key in sorted(_required_keys_for(CertificateLayer.C4X_TRUTH))},
        }
    )
    c4x["receipt_digest"] = sha256_digest(c4x)
    sidecar["c4x_receipt"] = c4x

    receipt = build_c4x_physical_truth_certificate(run_id="pytest-claimant-only-attestation", **sidecar)

    assert receipt["certificate_gates"]["c4x_truth"] is False
    c4x_verdict = [item for item in receipt["layer_verdicts"] if item["layer"] == "c4x_truth"][0]
    assert "source_artifacts_missing" in c4x_verdict["failure_reasons"]


def test_complete_physical_truth_sidecar_allows_public_credit():
    receipt = build_c4x_physical_truth_certificate(run_id="pytest-complete", **_complete_sidecar())

    assert receipt["public_credit_allowed"] is True
    assert receipt["truth_claim_allowed"] is True
    assert receipt["critical_failures"] == []
    assert all(receipt["certificate_gates"].values())


def test_physical_truth_script_writes_pending_template_and_receipt(tmp_path: Path):
    receipt = run_physical_truth_certificate(evidence_root=tmp_path, run_id="pytest-physical", write_template=True)

    root = tmp_path / "pytest-physical"
    assert receipt["public_credit_allowed"] is False
    assert (root / "physical_truth_sidecar_template.json").is_file()
    assert (root / "physical_truth_certificate.json").is_file()
    assert (root / "physical_truth_certificate.md").is_file()
    assert (root / "SHA256SUMS.txt").is_file()


def test_physical_truth_script_accepts_complete_sidecar(tmp_path: Path):
    sidecar = tmp_path / "complete-sidecar.json"
    sidecar.write_text(json.dumps(_complete_sidecar(), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    receipt = run_physical_truth_certificate(sidecar=sidecar, evidence_root=tmp_path, run_id="pytest-complete-script")

    assert receipt["public_credit_allowed"] is True
    assert json.loads((tmp_path / "pytest-complete-script" / "physical_truth_certificate.json").read_text())["receipt_digest"] == receipt["receipt_digest"]


def _complete_sidecar():
    return {
        "c4x_receipt": _with_digest({
            "proof_first": True,
            "joined_verification": True,
            "text_artifact_digest_valid": True,
            "visual_artifact_digest_valid": True,
            "unsupported_gaps_refused": True,
            "provider_calls_used": 0,
        }),
        "sensorium_receipt": _with_digest({
            "ordered_episode": True,
            "journal_integrity_valid": True,
            "explicit_loss_accounting": True,
            "raw_sensitive_payloads_absent": True,
            "observer_lifecycle_recorded": True,
            "missing_observations_lower_authority": True,
        }),
        "bpf_receipt": _with_digest({
            "read_only_program": True,
            "cgroup_bound": True,
            "outbound_connect_attempts": 0,
            "dns_activity": 0,
            "provider_sockets_opened": 0,
            "unexpected_child_processes": 0,
            "live_provider_comparator_observed_network": True,
            "ring_loss_explicit": True,
            "raw_packet_payload_retained": False,
        }),
        "crystal_bus_receipt": _with_digest({
            "af_unix_seqpacket": True,
            "so_peercred_bound": True,
            "session_id_bound": True,
            "message_mac_or_signature_verified": True,
            "sequence_replay_rejected": True,
            "durable_high_water_checked": True,
            "capability_lease_required": True,
            "arda_appraisal_required": True,
            "fd_count_type_seals_digest_verified": True,
            "sender_death_after_handoff_verified": True,
            "revocation_replay_rejected": True,
        }),
        "memfd_receipt": _with_digest({
            "sealed_memfd": True,
            "seal_write": True,
            "seal_grow": True,
            "seal_shrink": True,
            "seal_seal": True,
            "digest_verified_after_seal": True,
            "mutation_attempt_rejected": True,
            "wrong_fd_type_rejected": True,
        }),
        "guardian_receipt": _with_digest({
            "separate_process": True,
            "scm_rights_handoff_verified": True,
            "process_lease_verified": True,
            "one_use_render_capability_consumed": True,
            "replay_render_capability_rejected": True,
            "wrong_uid_rejected": True,
            "expired_lease_rejected": True,
            "producer_death_after_handoff_verified": True,
            "joined_custody_receipt_signed": True,
        }),
        "reuse_receipt": _with_digest({
            "exact_prefix_hit_verified": True,
            "identity_mismatch_refused": True,
            "corrupt_payload_rejected": True,
            "restart_persistence_credit_only_if_demonstrated": True,
            "cross_engine_import_refused_without_physical_success": True,
            "crystal_composition_reuse_verified": True,
            "semantic_truth_points_not_awarded_for_kv_speed": True,
        }),
        "pq_transport_receipt": _with_digest({
            "ml_kem_active": True,
            "ml_dsa_signature_verified": True,
            "fallback": False,
            "recipient_decapsulation_verified": True,
            "ciphertext_tamper_rejected": True,
            "signature_tamper_rejected": True,
            "replay_nonce_unused": True,
            "artifact_digest_verified": True,
            "policy_scope_accepted": True,
        }),
        "commons_receipt": _with_digest({
            "imported_as_quarantined_hypothesis": True,
            "clean_source_rebuild": True,
            "independent_seed": True,
            "independent_oracle": True,
            "reproduction_successful": True,
            "promotion_after_local_success_only": True,
            "node_count_minimum_met": True,
        }),
        "route_receipt": _with_digest({
            "deterministic_failure_schedule_hidden_from_router": True,
            "attestation_failure_immediate_suppression": True,
            "timeout_accumulates_penalty": True,
            "429_suppression": True,
            "recovery_after_decay": True,
            "oscillation_bounded": True,
            "decision_receipts_explain_route_change": True,
            "beats_no_damping_retry_and_circuit_breaker": True,
        }),
        "psi_receipt": _with_digest({
            "cpu_pressure_case": True,
            "memory_pressure_case": True,
            "io_pressure_case": True,
            "near_oom_case": True,
            "disk_full_or_inode_case": True,
            "evidence_not_corrupted": True,
            "sensorium_loss_not_silent": True,
            "low_priority_work_shed_first": True,
            "proof_and_custody_preserved": True,
            "refused_before_corrupting_evidence": True,
        }),
        "xdp_receipt": _with_digest({
            "isolated_veth_or_namespace": True,
            "redirect_pass_drop_observed": True,
            "unauthorized_cgroup_rejected": True,
            "worker_death_observed": True,
            "rx_ring_loss_reported": True,
            "xdp_detach_detected": True,
            "no_unrelated_traffic_redirected": True,
            "policy_fail_open_or_closed_verified": True,
            "guardian_policy_not_bypassed": True,
        }),
    }


def _with_digest(payload):
    body = dict(payload)
    body.pop("receipt_digest", None)
    layer, authority = _infer_layer_and_authority(body)
    boundary = f"pytest source-linked receipt for {layer.value}; exact digest binding and attestation required."
    body.setdefault("authority", authority)
    body.setdefault("claim_boundary", boundary)
    body.setdefault("source_receipt_digest", sha256_digest({"pytest_source": layer.value}))
    body.setdefault("source_artifacts", _pytest_source_artifacts())
    body["attestation_digest"] = sha256_digest(
        {
            "layer": layer.value,
            "authority": authority,
            "claim_boundary": body["claim_boundary"],
            "source_linkage": _source_linkage(body),
            "required_claims": {key: body.get(key) for key in sorted(_required_keys_for(layer))},
        }
    )
    body["receipt_digest"] = sha256_digest(body)
    return body


def _pytest_source_artifacts():
    path = Path("tests/test_c4x_physical_truth_certificate.py")
    import hashlib

    return [{"path": str(path), "file_sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()}]


def _infer_layer_and_authority(payload):
    if "proof_first" in payload:
        return CertificateLayer.C4X_TRUTH, "semantic_truth_only"
    if "ordered_episode" in payload:
        return CertificateLayer.SENSORIUM_OBSERVATION, "observation_only"
    if "read_only_program" in payload:
        return CertificateLayer.BPF_WITNESS, "kernel_observation_only"
    if "af_unix_seqpacket" in payload:
        return CertificateLayer.PROTOCOL_INTEGRITY, "host_local_protocol_integrity"
    if "sealed_memfd" in payload:
        return CertificateLayer.MEMFD_CUSTODY, "kernel_immutable_artifact_custody"
    if "separate_process" in payload:
        return CertificateLayer.GUARDIAN_CUSTODY, "independent_custody_gatekeeper"
    if "exact_prefix_hit_verified" in payload:
        return CertificateLayer.REUSE, "reuse_certificate_only"
    if "ml_kem_active" in payload:
        return CertificateLayer.PQ_TRANSPORT, "transport_confidentiality_and_authenticity"
    if "imported_as_quarantined_hypothesis" in payload:
        return CertificateLayer.COMMONS_REPLICATION, "replication_certificate"
    if "deterministic_failure_schedule_hidden_from_router" in payload:
        return CertificateLayer.ROUTE_RESILIENCE, "route_resilience_certificate"
    if "cpu_pressure_case" in payload:
        return CertificateLayer.PSI_GOVERNANCE, "scarcity_governance_certificate"
    if "isolated_veth_or_namespace" in payload:
        return CertificateLayer.XDP_SCOPE, "scoped_packet_actuation_certificate"
    raise AssertionError(f"could not infer layer from payload keys: {sorted(payload)}")


def _required_keys_for(layer):
    return {
        CertificateLayer.C4X_TRUTH: (
            "proof_first",
            "joined_verification",
            "text_artifact_digest_valid",
            "visual_artifact_digest_valid",
            "unsupported_gaps_refused",
            "provider_calls_used",
        ),
        CertificateLayer.SENSORIUM_OBSERVATION: (
            "ordered_episode",
            "journal_integrity_valid",
            "explicit_loss_accounting",
            "raw_sensitive_payloads_absent",
            "observer_lifecycle_recorded",
            "missing_observations_lower_authority",
        ),
        CertificateLayer.BPF_WITNESS: (
            "read_only_program",
            "cgroup_bound",
            "outbound_connect_attempts",
            "dns_activity",
            "provider_sockets_opened",
            "unexpected_child_processes",
            "live_provider_comparator_observed_network",
            "ring_loss_explicit",
            "raw_packet_payload_retained",
        ),
        CertificateLayer.PROTOCOL_INTEGRITY: (
            "af_unix_seqpacket",
            "so_peercred_bound",
            "session_id_bound",
            "message_mac_or_signature_verified",
            "sequence_replay_rejected",
            "durable_high_water_checked",
            "capability_lease_required",
            "arda_appraisal_required",
            "fd_count_type_seals_digest_verified",
            "sender_death_after_handoff_verified",
            "revocation_replay_rejected",
        ),
        CertificateLayer.MEMFD_CUSTODY: (
            "sealed_memfd",
            "seal_write",
            "seal_grow",
            "seal_shrink",
            "seal_seal",
            "digest_verified_after_seal",
            "mutation_attempt_rejected",
            "wrong_fd_type_rejected",
        ),
        CertificateLayer.GUARDIAN_CUSTODY: (
            "separate_process",
            "scm_rights_handoff_verified",
            "process_lease_verified",
            "one_use_render_capability_consumed",
            "replay_render_capability_rejected",
            "wrong_uid_rejected",
            "expired_lease_rejected",
            "producer_death_after_handoff_verified",
            "joined_custody_receipt_signed",
        ),
        CertificateLayer.REUSE: (
            "exact_prefix_hit_verified",
            "identity_mismatch_refused",
            "corrupt_payload_rejected",
            "restart_persistence_credit_only_if_demonstrated",
            "cross_engine_import_refused_without_physical_success",
            "crystal_composition_reuse_verified",
            "semantic_truth_points_not_awarded_for_kv_speed",
        ),
        CertificateLayer.PQ_TRANSPORT: (
            "ml_kem_active",
            "ml_dsa_signature_verified",
            "fallback",
            "recipient_decapsulation_verified",
            "ciphertext_tamper_rejected",
            "signature_tamper_rejected",
            "replay_nonce_unused",
            "artifact_digest_verified",
            "policy_scope_accepted",
        ),
        CertificateLayer.COMMONS_REPLICATION: (
            "imported_as_quarantined_hypothesis",
            "clean_source_rebuild",
            "independent_seed",
            "independent_oracle",
            "reproduction_successful",
            "promotion_after_local_success_only",
            "node_count_minimum_met",
        ),
        CertificateLayer.ROUTE_RESILIENCE: (
            "deterministic_failure_schedule_hidden_from_router",
            "attestation_failure_immediate_suppression",
            "timeout_accumulates_penalty",
            "429_suppression",
            "recovery_after_decay",
            "oscillation_bounded",
            "decision_receipts_explain_route_change",
            "beats_no_damping_retry_and_circuit_breaker",
        ),
        CertificateLayer.PSI_GOVERNANCE: (
            "cpu_pressure_case",
            "memory_pressure_case",
            "io_pressure_case",
            "near_oom_case",
            "disk_full_or_inode_case",
            "evidence_not_corrupted",
            "sensorium_loss_not_silent",
            "low_priority_work_shed_first",
            "proof_and_custody_preserved",
            "refused_before_corrupting_evidence",
        ),
        CertificateLayer.XDP_SCOPE: (
            "isolated_veth_or_namespace",
            "redirect_pass_drop_observed",
            "unauthorized_cgroup_rejected",
            "worker_death_observed",
            "rx_ring_loss_reported",
            "xdp_detach_detected",
            "no_unrelated_traffic_redirected",
            "policy_fail_open_or_closed_verified",
            "guardian_policy_not_bypassed",
        ),
    }[layer]
