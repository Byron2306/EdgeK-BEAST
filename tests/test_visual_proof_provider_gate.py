from app.kernel.compute.generation_provider_adapters import (
    GenerationModality,
    GenerationProviderAdapterRegistry,
    GenerationProviderRequest,
    ProviderMode,
)
from app.kernel.compute.proof_graph import CanonicalProofGraph, ProofClaimStatus, ProofGraphClaim, VisualProofPrimitive, VisualProofView
from app.kernel.compute.residual_contracts import sha256_digest
from app.kernel.compute.scene_synthesis import CanvasContract
from app.kernel.compute.visual_proof_provider_gate import (
    attest_visual_provider_output_against_proof,
    build_visual_proof_provider_prompt,
)
from app.kernel.compute.visual_residuals import RegionMask


def test_visual_provider_output_is_trusted_only_when_derived_from_visual_proof():
    graph, visual_view = _proof_artifacts(ProofClaimStatus.SUPPORTED)
    prompt_spec = build_visual_proof_provider_prompt(graph, visual_view, primitive_id="primitive:risk-edge")
    mask = _mask()
    output = _status_light_region_bytes((38, 220, 72))
    registry = GenerationProviderAdapterRegistry(image_factory=lambda _request: output)
    request = _provider_request(prompt_spec.prompt, prompt_spec.prompt_digest)

    result = registry.execute(request)
    gate = attest_visual_provider_output_against_proof(
        graph,
        visual_view,
        primitive_id="primitive:risk-edge",
        provider_request=request,
        provider_receipt=result.receipt,
        output=result.output,
        mask=mask,
    )

    assert prompt_spec.raw_text_answer_used is False
    assert gate.trusted_for_promotion is True
    assert gate.proof_prompt_valid is True
    assert gate.quality_valid is True
    assert gate.intent_valid is True
    assert gate.perceptual_valid is True
    assert gate.failure_class == ""


def test_visual_provider_gate_rejects_text_or_arbitrary_prompt_digest():
    graph, visual_view = _proof_artifacts(ProofClaimStatus.SUPPORTED)
    prompt_spec = build_visual_proof_provider_prompt(graph, visual_view, primitive_id="primitive:risk-edge")
    output = _status_light_region_bytes((38, 220, 72))
    registry = GenerationProviderAdapterRegistry(image_factory=lambda _request: output)
    request = _provider_request(prompt_spec.prompt, sha256_digest({"prompt": "text answer says service restart is safe"}))

    result = registry.execute(request)
    gate = attest_visual_provider_output_against_proof(
        graph,
        visual_view,
        primitive_id="primitive:risk-edge",
        provider_request=request,
        provider_receipt=result.receipt,
        output=result.output,
        mask=_mask(),
    )

    assert gate.trusted_for_promotion is False
    assert gate.proof_prompt_valid is False
    assert gate.failure_class == "prompt_proof_mismatch"
    assert "prompt_not_derived_from_visual_proof" in gate.refusal_reasons


def test_visual_provider_gate_rejects_semantically_wrong_pixels():
    graph, visual_view = _proof_artifacts(ProofClaimStatus.SUPPORTED)
    prompt_spec = build_visual_proof_provider_prompt(graph, visual_view, primitive_id="primitive:risk-edge")
    red_output = _status_light_region_bytes((220, 38, 32))
    registry = GenerationProviderAdapterRegistry(image_factory=lambda _request: red_output)
    request = _provider_request(prompt_spec.prompt, prompt_spec.prompt_digest)

    result = registry.execute(request)
    gate = attest_visual_provider_output_against_proof(
        graph,
        visual_view,
        primitive_id="primitive:risk-edge",
        provider_request=request,
        provider_receipt=result.receipt,
        output=result.output,
        mask=_mask(),
    )

    assert gate.trusted_for_promotion is False
    assert gate.intent_valid is False
    assert gate.failure_class == "visual_intent_failure"
    assert any(reason.startswith("intent:") for reason in gate.refusal_reasons)


def test_visual_provider_gate_refuses_to_promote_stale_claim_pixels():
    graph, visual_view = _proof_artifacts(ProofClaimStatus.STALE)
    prompt_spec = build_visual_proof_provider_prompt(graph, visual_view, primitive_id="primitive:risk-edge")
    yellow_output = _status_light_region_bytes((235, 204, 52))
    registry = GenerationProviderAdapterRegistry(image_factory=lambda _request: yellow_output)
    request = _provider_request(prompt_spec.prompt, prompt_spec.prompt_digest)

    result = registry.execute(request)
    gate = attest_visual_provider_output_against_proof(
        graph,
        visual_view,
        primitive_id="primitive:risk-edge",
        provider_request=request,
        provider_receipt=result.receipt,
        output=result.output,
        mask=_mask(),
    )

    assert gate.proof_graph_valid is True
    assert gate.current_supported_claim is False
    assert gate.trusted_for_promotion is False
    assert gate.failure_class == "non_current_claim"
    assert "claim_not_current_supported" in gate.refusal_reasons


def _proof_artifacts(status: ProofClaimStatus) -> tuple[CanonicalProofGraph, VisualProofView]:
    fact_digest = sha256_digest({"fact": "service-health", "service": "beast"})
    rule_digest = sha256_digest({"rule": "restart-risk-visual-proof"})
    policy_digest = sha256_digest({"policy": "visual-provider-proof-bound.v1"})
    claim = ProofGraphClaim(
        claim_id="claim:restart-risk:beast-to-commons",
        claim_type="conditional_causal",
        subject="beast",
        predicate="restart_may_destabilize",
        object="commons",
        status=status,
        confidence_class="bounded_verified",
        fact_refs=(fact_digest,),
        rule_ref=rule_digest,
        policy_ref=policy_digest,
    )
    graph = CanonicalProofGraph(
        graph_id="proof-graph:test:visual-provider-gate:" + status.value,
        claims=(claim,),
        world_snapshot_digest=sha256_digest({"snapshot": "test", "status": status.value}),
        policy_digest=policy_digest,
        capability_fact_digests=(fact_digest,),
        causal_rule_digests=(rule_digest,),
    )
    visual_view = VisualProofView(
        view_id="visual-view:test:restart-risk",
        scene_capsule_digest=sha256_digest({"scene": "restart-risk"}),
        rendered_visual_digest=sha256_digest({"render": "candidate-visual-view"}),
        asset_manifest_digest=sha256_digest({"manifest": "beast-test"}),
        layout_engine_digest=sha256_digest({"layout": "proof-view"}),
        primitives=(
            VisualProofPrimitive(
                primitive_id="primitive:risk-edge",
                primitive="risk_edge",
                claim_ref=claim.claim_id,
                evidence_state=status,
                metadata={
                    "object_hint": "status_light",
                    "expected_color": "green" if status is ProofClaimStatus.SUPPORTED else "yellow",
                    "visual_treatment": "solid_edge_with_rule_badge" if status is ProofClaimStatus.SUPPORTED else "clock_badge_and_faded_status",
                },
            ),
        ),
    )
    return graph, visual_view


def _provider_request(prompt: str, prompt_digest: str) -> GenerationProviderRequest:
    return GenerationProviderRequest(
        request_id="provider:test:proof-bound-image",
        modality=GenerationModality.IMAGE,
        provider_id="gauntlet_stub",
        mode=ProviderMode.STUB,
        prompt_digest=prompt_digest,
        metadata={"prompt": prompt, "boundary": "visual_proof_provider_gate"},
    )


def _mask() -> RegionMask:
    return RegionMask(
        mask_id="mask:proof-bound-risk-edge",
        x=0,
        y=0,
        width=8,
        height=8,
        canvas=CanvasContract(8, 8, "#000000"),
        provenance_digest=sha256_digest({"provenance": "visual-proof-provider-gate"}),
    )


def _status_light_region_bytes(color: tuple[int, int, int]) -> bytes:
    region = bytearray()
    for y in range(8):
        for x in range(8):
            distance = (((x - 3.5) ** 2 + (y - 3.5) ** 2) ** 0.5) / 4
            gain = 0.38 + max(0.0, 1.0 - distance) * 0.72
            region.extend([
                min(255, int(color[0] * gain) + (x + y) % 3),
                min(255, int(color[1] * gain) + (x % 2)),
                min(255, int(color[2] * gain)),
                255,
            ])
    return bytes(region)
