"""D9: Unified Adaptive Router — Table 15 bands, proposal-only, verifiers decide (IEI v0.9 §7.12.1)."""
from __future__ import annotations

import pytest

from app.kernel.compute.adaptive_router import (
    AdaptiveRouter,
    RouteKind,
    classify_band,
)

CRYSTAL_FP = {"opcode_catalog_digest": "sha256:cat", "crystal_digest": "sha256:rec", "source_envelope_digest": "sha256:env"}
SPECIALIST = {"execution_mode": "local_specialist_adapter", "model_ref": "ollama://beast-specialist-n1",
              "boundary_checks_passed": True}


def _route(similarity, *, request_fp=CRYSTAL_FP, crystal_fp=CRYSTAL_FP, crystal_id="coding-crystal:abc", specialist=None):
    return AdaptiveRouter().route(similarity=similarity, crystal_id=crystal_id, crystal_fingerprints=crystal_fp,
                                  request_fingerprints=request_fp, specialist=specialist,
                                  envelope_digest="sha256:env")


@pytest.mark.parametrize("value,band", [(1.0, "exact"), (0.95, "exact"), (0.9499, "structural"), (0.80, "structural"),
                                        (0.7999, "insufficient"), (float("nan"), "insufficient"), (-1, "insufficient")])
def test_bands_follow_table_15(value, band):
    assert classify_band(value) == band


def test_exact_band_with_compatible_fingerprints_proposes_crystal_replay_only():
    decision = _route(0.97)
    assert decision.route is RouteKind.CRYSTAL_REPLAY
    assert decision.proposal_only is True and decision.execution_granted is False
    assert decision.verifier == "d6_activation_gates_and_verify_command"
    assert decision.crystal_id == "coding-crystal:abc" and decision.envelope_digest == "sha256:env"
    assert decision.to_dict()["digest"].startswith("sha256:")


def test_structural_band_proposes_specialist_never_executes():
    decision = _route(0.88, specialist=SPECIALIST)
    assert decision.route is RouteKind.LOCAL_SPECIALIST_ADAPTER
    assert decision.specialist_ref == "ollama://beast-specialist-n1"
    assert decision.execution_granted is False and decision.verifier == "hidden_tests_and_policy"


def test_structural_band_without_safe_specialist_falls_back():
    assert _route(0.88).route is RouteKind.PROVIDER_FALLBACK
    remote = {**SPECIALIST, "model_ref": "https://evil.example/model"}
    assert _route(0.88, specialist=remote).route is RouteKind.PROVIDER_FALLBACK
    unchecked = {**SPECIALIST, "boundary_checks_passed": False}
    assert _route(0.88, specialist=unchecked).route is RouteKind.PROVIDER_FALLBACK


def test_low_similarity_falls_back_even_with_compatible_crystal():
    decision = _route(0.79, specialist=SPECIALIST)
    assert decision.route is RouteKind.PROVIDER_FALLBACK
    assert decision.verifier == "action_ir_full_verification"


@pytest.mark.parametrize("request_fp", [
    {**CRYSTAL_FP, "opcode_catalog_digest": "sha256:drifted"},
    {k: v for k, v in CRYSTAL_FP.items() if k != "source_envelope_digest"},
    {**CRYSTAL_FP, "crystal_digest": ""},
])
def test_fingerprint_mismatch_never_replays_and_signals_demotion(request_fp):
    decision = _route(0.99, request_fp=request_fp)
    assert decision.route is not RouteKind.CRYSTAL_REPLAY
    assert decision.fingerprint_compatible is False
    assert decision.demotion_signal == "fingerprint_mismatch"


def test_similarity_without_compat_never_executes_in_any_band():
    for similarity in (1.0, 0.96, 0.9, 0.81, 0.5):
        for specialist in (None, SPECIALIST):
            decision = _route(similarity, crystal_fp={}, specialist=specialist)
            assert decision.route is not RouteKind.CRYSTAL_REPLAY
            assert decision.execution_granted is False
            assert decision.to_dict()["execution_granted"] is False


def test_route_decision_cannot_be_constructed_with_execution():
    from app.kernel.compute.adaptive_router import RouteDecision

    with pytest.raises(ValueError):
        RouteDecision(route=RouteKind.CRYSTAL_REPLAY, similarity=1.0, band="exact", execution_granted=True)


# --- Task 2: execute.py leak --------------------------------------------------------------------------------------

def test_dispatcher_specialist_is_recorded_as_proposal_and_never_rewrites_the_request():
    from app.kernel.compute.adaptive_router import record_dispatch_proposal
    from app.kernel.compute.perceive import EdgeKIR

    ir = EdgeKIR(messages=[], model="gpt-4o", metadata={"route_similarity": 0.9})
    decision = record_dispatch_proposal(ir, {**SPECIALIST, "confidence_score": 0.95})
    assert decision.route is RouteKind.LOCAL_SPECIALIST_ADAPTER
    assert ir.model == "gpt-4o"
    assert "adaptive_route_executed" not in ir.metadata and "provider_candidates" not in ir.metadata
    assert ir.metadata["adaptive_route"]["execution_granted"] is False
    assert ir.metadata["adaptive_route"]["route"] == "local_specialist_adapter"


def test_dispatcher_without_specialist_records_provider_fallback():
    from app.kernel.compute.adaptive_router import record_dispatch_proposal
    from app.kernel.compute.perceive import EdgeKIR

    ir = EdgeKIR(messages=[], model="m", metadata={})
    assert record_dispatch_proposal(ir, None).route is RouteKind.PROVIDER_FALLBACK
    assert ir.model == "m" and ir.metadata["adaptive_route"]["route"] == "provider_fallback"


def test_executor_no_longer_grants_execution_from_routing():
    import inspect

    from app.kernel.execution import execute

    source = inspect.getsource(execute.Executor)
    assert "adaptive_route_executed" not in source
    assert 'removeprefix("ollama://")' not in source
    assert "record_dispatch_proposal" in source


# --- Task 3: CrystalReuseGateway subordination ------------------------------------------------------------------

def _semantic_gateway(tmp_path, confidence, verifier=None):
    from app.kernel.compute.crystal_reuse_gateway import CrystalReuseGateway
    from app.kernel.security.residue_seal import ResidueSeal
    from app.kernel.storage.durable_inference_storage import DurableInferenceStorage, RuntimeReplayResult

    def matcher(request):
        return RuntimeReplayResult(replay_type="cached_answer", credit_id="semantic-hit", reusable=True,
                                   payload={"response": "near match"}, avoided_tokens_estimate=55,
                                   confidence=confidence, reason="semantic_similarity_hit")

    return CrystalReuseGateway(storage=DurableInferenceStorage(tmp_path / "durable"), semantic_matcher=matcher,
                               seal=ResidueSeal(tmp_path / "keys"), semantic_verifier=verifier)


@pytest.mark.parametrize("confidence", [0.83, 0.91, 0.99])
def test_semantic_hit_without_verifier_is_only_a_proposal(tmp_path, confidence):
    from app.kernel.compute.crystal_reuse_gateway import CrystalReuseRequest

    decision = _semantic_gateway(tmp_path, confidence).decide(CrystalReuseRequest(prompt="similar prompt", model="m"))
    assert decision.action == "execute_local_cpu"
    assert decision.reason == "semantic_hit_requires_verifier_pass"
    assert decision.payload["semantic_proposal"]["credit_id"] == "semantic-hit"
    assert decision.payload["route_decision"]["execution_granted"] is False
    assert "near match" not in str(decision.payload.get("reuse"))


def test_semantic_hit_below_exact_band_never_reuses_even_if_verifier_passes(tmp_path):
    from app.kernel.compute.crystal_reuse_gateway import CrystalReuseRequest

    calls = []
    gateway = _semantic_gateway(tmp_path, 0.91, verifier=lambda req, replay: calls.append(1) or True)
    decision = gateway.decide(CrystalReuseRequest(prompt="similar prompt", model="m"))
    assert decision.action == "execute_local_cpu" and calls == []


def test_semantic_hit_reuses_only_with_exact_band_and_verifier_pass(tmp_path):
    from app.kernel.compute.crystal_reuse_gateway import CrystalReuseRequest

    passed = _semantic_gateway(tmp_path / "a", 0.97, verifier=lambda req, replay: True)
    assert passed.decide(CrystalReuseRequest(prompt="p", model="m")).action == "reuse_answer"
    failed = _semantic_gateway(tmp_path / "b", 0.97, verifier=lambda req, replay: False)
    assert failed.decide(CrystalReuseRequest(prompt="p", model="m")).action == "execute_local_cpu"
    raising = _semantic_gateway(tmp_path / "c", 0.97, verifier=lambda req, replay: 1 / 0)
    assert raising.decide(CrystalReuseRequest(prompt="p", model="m")).action == "execute_local_cpu"
