import json

import pytest

from app.kernel.compute.residual_candidate import ResidualCandidate
from app.kernel.compute.residual_compute_governor import ResidualComputeGovernor
from app.kernel.compute.residual_compute_plane import RouteExecutionResult
from app.kernel.compute.residual_contracts import (
    ApplicabilityState,
    ResidualAuthority,
    ResidualRoute,
    VerificationState,
    sha256_digest,
)
from app.kernel.compute.synthesis_contracts import SynthesisMode, SynthesisOutcome, SynthesisRequest
from app.kernel.compute.synthesis_plane import SynthesisPlane, SynthesisReceiptStore


def _candidate(route=ResidualRoute.SEMANTIC_RESULT, authority=ResidualAuthority.READ_VERIFIED):
    return ResidualCandidate(
        candidate_id=f"candidate-{route.value}",
        route=route,
        applicability=ApplicabilityState.APPLICABLE,
        verification=VerificationState.VERIFIED,
        authority=authority,
        predicted_latency_ms=1.0,
        predicted_cpu_ms=1.0,
        predicted_memory_bytes=128,
        predicted_monetary_cost=0.0,
        confidence=1.0,
        expected_quality=1.0,
        failure_probability=0.0,
        workspace_id="ws",
        privacy_domain="operator",
        evidence_digest=sha256_digest({"evidence": route.value}),
    )


def _request(mode=SynthesisMode.REALIZE):
    return SynthesisRequest(
        request_id="synth-1",
        workspace_id="ws",
        privacy_domain="operator",
        task_class="beast.operator_language",
        mode=mode,
        payload={"utterance": "summarize the service registry"},
        evidence_digest=sha256_digest({"registry": "services"}),
    )


def test_synthesis_plane_records_verified_governed_receipt(tmp_path):
    seen = {}

    def executor(request, decision_digest):
        seen["payload"] = request.payload
        return RouteExecutionResult(
            route=ResidualRoute.SEMANTIC_RESULT,
            authority_used=ResidualAuthority.READ_VERIFIED,
            output={"answer_frame": "registry_summary"},
            verified=True,
            execution_digest=sha256_digest({"execution": decision_digest}),
        )

    receipt_path = tmp_path / "synthesis.jsonl"
    plane = SynthesisPlane(
        ResidualComputeGovernor({"semantic": lambda _request: [_candidate()]}),
        {ResidualRoute.SEMANTIC_RESULT: executor},
        receipt_store=SynthesisReceiptStore(receipt_path),
    )

    output, receipt = plane.run(_request())

    assert output == {"answer_frame": "registry_summary"}
    assert seen["payload"]["synthesis_mode"] == "realize"
    assert seen["payload"]["synthesis_payload"]["utterance"] == "summarize the service registry"
    assert receipt.outcome is SynthesisOutcome.VERIFIED
    assert receipt.verification_state is VerificationState.VERIFIED
    assert receipt.selected_route is ResidualRoute.SEMANTIC_RESULT
    assert receipt.authority_required is ResidualAuthority.READ_VERIFIED
    assert receipt.receipt_digest.startswith("sha256:")
    stored = [json.loads(line) for line in receipt_path.read_text(encoding="utf-8").splitlines()]
    assert stored[0]["outcome"] == "verified"
    assert stored[0]["mode"] == "realize"


def test_synthesis_plane_records_refusal_without_executing(tmp_path):
    plane = SynthesisPlane(
        ResidualComputeGovernor({"empty": lambda _request: []}),
        {},
        receipt_store=SynthesisReceiptStore(tmp_path / "refused.jsonl"),
    )

    output, receipt = plane.run(_request(SynthesisMode.EXACT))

    assert output is None
    assert receipt.outcome is SynthesisOutcome.REFUSED
    assert receipt.selected_route is None
    assert receipt.authority_used is None


def test_provider_candidate_cannot_bypass_missing_governed_executor(tmp_path):
    plane = SynthesisPlane(
        ResidualComputeGovernor(
            {
                "provider": lambda _request: [
                    _candidate(ResidualRoute.PROVIDER, ResidualAuthority.PROVIDER_CALL)
                ]
            }
        ),
        {},
        receipt_store=SynthesisReceiptStore(tmp_path / "provider.jsonl"),
    )

    with pytest.raises(RuntimeError, match="no executor registered for provider"):
        plane.run(_request(SynthesisMode.OPEN))

    stored = [
        json.loads(line)
        for line in (tmp_path / "provider.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert stored[0]["outcome"] == "unverified"
    assert stored[0]["selected_route"] == "provider"
    assert stored[0]["authority_required"] == "provider_call"


def test_synthesis_mode_rejects_route_outside_allowed_contract(tmp_path):
    plane = SynthesisPlane(
        ResidualComputeGovernor({"semantic": lambda _request: [_candidate()]}),
        {
            ResidualRoute.SEMANTIC_RESULT: lambda request, decision_digest: RouteExecutionResult(
                route=ResidualRoute.SEMANTIC_RESULT,
                authority_used=ResidualAuthority.READ_VERIFIED,
                output={"should_not": "execute"},
                verified=True,
                execution_digest=sha256_digest({"execution": decision_digest}),
            )
        },
        receipt_store=SynthesisReceiptStore(tmp_path / "mode-policy.jsonl"),
    )

    output, receipt = plane.run(_request(SynthesisMode.LEXICALIZE))

    assert output is None
    assert receipt.outcome is SynthesisOutcome.REFUSED
    assert receipt.reason == "route semantic_result is not allowed for synthesis mode lexicalize"
    assert receipt.metadata["refusal"] == "mode_route_policy"
    assert receipt.metadata["selected_route"] == "semantic_result"
