from __future__ import annotations

import pytest

from app.kernel.compute.discovery_agnostic_reuse import (
    ARM_NAMES,
    CapabilityCandidate,
    DiscoveryAgnosticCorpusRunner,
    DiscoveryCorpusCase,
    DiscoveryAgnosticReceipt,
    DiscoveryAgnosticReuseHarness,
    DiscoveryTask,
    ReceiverContext,
    PairedEconomics,
    SemanticCapabilityContract,
    commons_node_attestation_verifier,
    read_receipt,
    write_receipt,
)


NOW = 1_800_000_000.0
HASHES = {name: "sha256:" + letter * 64 for name, letter in {
    "semantic": "a", "policy": "b", "verifier": "c", "state": "d", "runtime": "e",
}.items()}


def receiver(**changes):
    value = ReceiverContext(
        host_id="receiver-physical-host", physical_host=True, attestation_verified=True,
        attestation_expires_at=NOW + 60, policy_digest=HASHES["policy"],
        verifier_digest=HASHES["verifier"], state_digest=HASHES["state"], runtime_digest=HASHES["runtime"],
        attestation_evidence={"fixture": "locally-validated-attestation"},
    )
    return ReceiverContext(**{**value.__dict__, **changes})


def task(**changes):
    value = DiscoveryTask(
        task_id="heldout-distant-wording", semantic_contract_digest=HASHES["semantic"],
        policy_digest=HASHES["policy"], verifier_digest=HASHES["verifier"],
        state_digest=HASHES["state"], runtime_digest=HASHES["runtime"],
    )
    return DiscoveryTask(**{**value.__dict__, **changes})


def candidate(**changes):
    value = CapabilityCandidate(
        candidate_id="candidate-origin-host", semantic_contract_digest=HASHES["semantic"],
        policy_digest=HASHES["policy"], verifier_digest=HASHES["verifier"], state_digest=HASHES["state"],
        runtime_compatible_digests=(HASHES["runtime"],), expires_at=NOW + 60, source="peer_exchange",
    )
    return CapabilityCandidate(**{**value.__dict__, **changes})


def run(*, context=None, workload=None, candidates=None, verifier=lambda _task, _candidate: True,
        attestation_verifier=lambda _receiver: True):
    return DiscoveryAgnosticReuseHarness(now=lambda: NOW).run(
        preregistration={"corpus": "sealed-v1", "seed": 7}, origin_host_id="origin-physical-host",
        receiver=context or receiver(), task=workload or task(), candidates=candidates or [candidate()], verifier=verifier,
        attestation_verifier=attestation_verifier,
    )


def test_distant_wording_can_reuse_only_after_local_verification():
    receipt = run()
    assert tuple(item.arm for item in receipt.outcomes) == ARM_NAMES
    assert receipt.admission_reason == "locally_reproduced_and_verified"
    assert receipt.provider_calls_avoided == 1
    assert receipt.receiver_physical_host is True


def test_structured_contract_is_wording_agnostic_but_invariant_sensitive():
    base = SemanticCapabilityContract(
        operation="normalize_provider_identifier",
        input_schema={"provider": "string"}, output_schema={"provider": "canonical_identifier"},
        invariants=("case_fold", "hyphen_space_equivalence"), tool_schema_digest=HASHES["verifier"], risk_tier="low",
    )
    same_meaning_different_words = SemanticCapabilityContract(
        operation="normalize_provider_identifier",
        input_schema={"provider": "string"}, output_schema={"provider": "canonical_identifier"},
        invariants=("hyphen_space_equivalence", "case_fold"), tool_schema_digest=HASHES["verifier"], risk_tier="low",
    )
    lexical_lookalike = SemanticCapabilityContract(
        operation="normalize_provider_identifier",
        input_schema={"provider": "string"}, output_schema={"provider": "canonical_identifier"},
        invariants=("case_fold", "delete_unknown_provider"), tool_schema_digest=HASHES["verifier"], risk_tier="low",
    )
    assert base.digest == same_meaning_different_words.digest
    assert base.digest != lexical_lookalike.digest
    structured_task = DiscoveryTask.from_contract(
        task_id="different-user-words", contract=base, policy_digest=HASHES["policy"],
        verifier_digest=HASHES["verifier"], state_digest=HASHES["state"], runtime_digest=HASHES["runtime"],
    )
    receipt = run(workload=structured_task, candidates=[candidate(semantic_contract_digest=base.digest)])
    assert receipt.provider_calls_avoided == 1


@pytest.mark.parametrize("workload,candidates", [
    (task(negative=True), [candidate()]),
    (task(semantic_contract_digest="sha256:" + "f" * 64), [candidate()]),
    (task(state_digest="sha256:" + "f" * 64), [candidate()]),
    (task(), [candidate(negative_contract_digests=(HASHES["semantic"],))]),
])
def test_lookalikes_and_boundary_mutations_refuse(workload, candidates):
    receipt = run(workload=workload, candidates=candidates)
    discovery = next(item for item in receipt.outcomes if item.arm == "beast_with_discovery")
    fallback = next(item for item in receipt.outcomes if item.arm == "provider_fallback_after_refusal")
    assert discovery.admitted is False
    assert fallback.provider_calls == 1


def test_stale_or_nonphysical_attestation_refuses():
    for context in (receiver(attestation_expires_at=NOW), receiver(physical_host=False)):
        receipt = run(context=context)
        assert receipt.admission_reason == "receiver_attestation_unverified_or_stale"
        assert receipt.provider_calls_avoided == 0


def test_receipt_tampering_is_rejected():
    receipt = run()
    with pytest.raises(ValueError, match="tampered"):
        DiscoveryAgnosticReceipt(**{**receipt.__dict__, "task_id": "altered"}).validate()


def test_portable_receipt_round_trip_and_independent_validation(tmp_path):
    receipt = run()
    target = tmp_path / "receipt.json"
    write_receipt(target, receipt)
    loaded = read_receipt(target)
    assert loaded.receipt_digest == receipt.receipt_digest
    target.write_text(target.read_text().replace("locally_reproduced_and_verified", "altered"), encoding="utf-8")
    with pytest.raises(ValueError, match="tampered"):
        read_receipt(target)


def test_commons_signed_attestation_adapter_requires_matching_node_identity():
    context = receiver(attestation_evidence={"node_advertisement": {
        "node_id": "receiver-physical-host", "attestation": "verified", "capabilities": ("cpu",),
        "pressure_budget": 0.5, "reliability": 0.9, "expires_at": NOW + 60,
    }})
    receipt = run(context=context, attestation_verifier=commons_node_attestation_verifier(lambda node: node.attestation == "verified"))
    assert receipt.provider_calls_avoided == 1
    wrong_identity = receiver(attestation_evidence={"node_advertisement": {
        "node_id": "other-host", "attestation": "verified", "capabilities": ("cpu",),
        "pressure_budget": 0.5, "reliability": 0.9, "expires_at": NOW + 60,
    }})
    assert run(context=wrong_identity, attestation_verifier=commons_node_attestation_verifier(lambda _node: True)).provider_calls_avoided == 0


def test_corpus_reports_safe_discovery_and_measured_net_economics():
    runner = DiscoveryAgnosticCorpusRunner(DiscoveryAgnosticReuseHarness(now=lambda: NOW))
    economics = PairedEconomics(
        baseline_provider_ms=250.0, discovery_ms=4.0, transfer_ms=3.0,
        reproduction_ms=12.0, execution_ms=6.0, verifier_ms=5.0,
    )
    receipt = runner.run(
        preregistration={"corpus": "sealed-v1", "seed": 7, "families": 2},
        origin_host_id="origin-physical-host", receiver=receiver(), verifier=lambda _task, _candidate: True,
        attestation_verifier=lambda _receiver: True,
        cases=(
            DiscoveryCorpusCase("positive", task(), (candidate(),), True, economics),
            DiscoveryCorpusCase("negative-boundary", task(negative=True), (candidate(),), False),
            DiscoveryCorpusCase("state-drift", task(state_digest="sha256:" + "f" * 64), (candidate(),), False),
        ),
    )
    assert receipt.unsafe_admissions == 0
    assert receipt.provider_calls_avoided == 1
    assert receipt.measured_economic_cases == 1
    assert receipt.net_latency_saved_ms == pytest.approx(220.0)
