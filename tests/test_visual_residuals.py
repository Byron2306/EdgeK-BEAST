from dataclasses import replace

import pytest

from app.kernel.compute.residual_contracts import sha256_digest
from app.kernel.compute.scene_synthesis import CanvasContract
from app.kernel.compute.visual_residuals import (
    CPURegionDiffusionBackend,
    RegionMask,
    SupervisedCPUVisualResidualWorker,
    VisualResidualBudget,
    VisualPromptIntent,
    VisualResidualRequest,
    build_visual_region_feature_embedding,
    evaluate_visual_region_equivalence,
    evaluate_visual_region_intent,
    evaluate_visual_region_perceptual,
    evaluate_visual_region_quality,
    extract_visual_prompt_intent,
    verify_visual_residual_output,
    verify_visual_residual_receipt,
)


BACKEND = CPURegionDiffusionBackend(diffusion_steps=3)
ENGINE_DIGEST = BACKEND.engine_digest
MODEL_DIGEST = BACKEND.model_digest


def _request(width=8, height=6, *, max_output_bytes=8 * 6 * 4):
    canvas = CanvasContract(64, 48, "#000")
    mask = RegionMask(
        mask_id="mask:status-light",
        x=4,
        y=4,
        width=width,
        height=height,
        canvas=canvas,
        provenance_digest=sha256_digest({"scene_asset": "status-light"}),
    )
    return VisualResidualRequest(
        request_id="visual-residual:1",
        scene_digest=sha256_digest({"scene": "status-card"}),
        scene_capsule_digest=sha256_digest({"scene_capsule": "status-card"}),
        mask=mask,
        unresolved_region_prompt_digest=sha256_digest({"prompt": "green status light"}),
        engine_digest=ENGINE_DIGEST,
        model_digest=MODEL_DIGEST,
        seed=7,
        budget=VisualResidualBudget(max_runtime_ms=100, max_memory_bytes=4096, max_output_bytes=max_output_bytes),
        sealed_input_digest=sha256_digest({"sealed": "input"}),
        visual_intent=extract_visual_prompt_intent("green status light"),
    )


def test_supervised_cpu_visual_residual_is_region_only_deterministic_and_verified():
    request = _request()
    worker = SupervisedCPUVisualResidualWorker(engine_digest=ENGINE_DIGEST, model_digest=MODEL_DIGEST, backend=BACKEND)

    output, receipt = worker.run(request)
    output_again, receipt_again = worker.run(request)

    assert output == output_again
    assert receipt.output_digest == receipt_again.output_digest
    assert len(output) == request.mask.width * request.mask.height * 4
    assert receipt.network_used is False
    assert receipt.details["region_only"] is True
    assert receipt.details["backend"]["engine"] == "beast-cpu-region-diffusion"
    assert receipt.details["model"]["model"] == "seeded-neighborhood-region-field"
    assert verify_visual_residual_receipt(request, receipt) is True
    assert verify_visual_residual_output(request, receipt, output) is True


def test_visual_residual_worker_rejects_mismatched_backend_pins():
    with pytest.raises(ValueError, match="must match its CPU diffusion backend"):
        SupervisedCPUVisualResidualWorker(
            engine_digest=sha256_digest({"engine": "other"}),
            model_digest=MODEL_DIGEST,
            backend=BACKEND,
        )


def test_visual_residual_rejects_network_scope_missing_provenance_and_budget_overflow():
    with pytest.raises(ValueError, match="ambient network"):
        replace(_request(), network_scope=("https://example.invalid",))
    with pytest.raises(ValueError, match="provenance_digest"):
        replace(_request().mask, provenance_digest="")
    with pytest.raises(ValueError, match="byte budget"):
        SupervisedCPUVisualResidualWorker(engine_digest=ENGINE_DIGEST, model_digest=MODEL_DIGEST, backend=BACKEND).run(
            _request(max_output_bytes=1)
        )


def test_visual_residual_verifier_rejects_tampered_receipt():
    request = _request()
    _output, receipt = SupervisedCPUVisualResidualWorker(
        engine_digest=ENGINE_DIGEST,
        model_digest=MODEL_DIGEST,
        backend=BACKEND,
    ).run(request)

    assert verify_visual_residual_receipt(request, replace(receipt, network_used=True)) is False
    assert verify_visual_residual_receipt(request, replace(receipt, output_size_bytes=999999)) is False
    assert verify_visual_residual_receipt(request, replace(receipt, scene_capsule_digest=sha256_digest({"scene_capsule": "other"}))) is False
    assert verify_visual_residual_output(request, receipt, _output[:-1]) is False


def test_visual_region_quality_gate_refuses_blank_or_transparent_regions():
    request = _request(width=4, height=4)
    good_output, _receipt = SupervisedCPUVisualResidualWorker(
        engine_digest=ENGINE_DIGEST,
        model_digest=MODEL_DIGEST,
        backend=BACKEND,
    ).run(request)
    blank = bytes([0, 0, 0, 0]) * (4 * 4)

    good = evaluate_visual_region_quality(request.mask, good_output)
    refused = evaluate_visual_region_quality(request.mask, blank)

    assert good.passed is True
    assert good.receipt_digest.startswith("sha256:")
    assert refused.passed is False
    assert "insufficient_alpha_coverage" in refused.refusal_reasons
    assert "blank_or_flat_region" in refused.refusal_reasons


def test_visual_prompt_intent_extracts_and_verifies_bounded_color_hints():
    request = _request(width=4, height=4)
    intent = extract_visual_prompt_intent("green healthy status light")
    green = bytearray()
    red = bytearray()
    for index in range(16):
        green.extend([28 + index % 7, 210 + index % 19, 54 + index % 5, 255])
        red.extend([220 + index % 19, 32 + index % 7, 24 + index % 5, 255])

    green_receipt = evaluate_visual_region_intent(request.mask, bytes(green), intent)
    red_receipt = evaluate_visual_region_intent(request.mask, bytes(red), intent)

    assert intent.color_name == "green"
    assert intent.object_hint == "status_light"
    assert intent.intent_digest.startswith("sha256:")
    assert green_receipt.passed is True
    assert red_receipt.passed is False
    assert "color_intent_mismatch" in red_receipt.refusal_reasons


def test_cpu_visual_residual_honors_bounded_color_intent():
    request = replace(_request(width=4, height=4), visual_intent=VisualPromptIntent(color_name="green", object_hint="status_light"))
    output, receipt = SupervisedCPUVisualResidualWorker(
        engine_digest=ENGINE_DIGEST,
        model_digest=MODEL_DIGEST,
        backend=BACKEND,
    ).run(request)
    intent_receipt = evaluate_visual_region_intent(request.mask, output, request.visual_intent)

    assert receipt.details["visual_intent"]["color_name"] == "green"
    assert intent_receipt.passed is True


def test_visual_perceptual_gate_refuses_flat_status_light_regions():
    request = _request(width=8, height=8, max_output_bytes=8 * 8 * 4)
    intent = extract_visual_prompt_intent("green healthy status light")
    flat_green = bytes([20, 220, 60, 255]) * (8 * 8)
    structured_output, _receipt = SupervisedCPUVisualResidualWorker(
        engine_digest=ENGINE_DIGEST,
        model_digest=MODEL_DIGEST,
        backend=BACKEND,
    ).run(request)

    flat = evaluate_visual_region_perceptual(request.mask, flat_green, intent)
    structured = evaluate_visual_region_perceptual(request.mask, structured_output, intent)

    assert flat.passed is False
    assert "status_light_not_center_focused" in flat.refusal_reasons
    assert structured.passed is True
    assert structured.center_luma_lift > 0
    assert structured.receipt_digest.startswith("sha256:")


def test_visual_feature_embeddings_allow_near_equivalent_region_outputs():
    request = _request(width=8, height=8, max_output_bytes=8 * 8 * 4)
    intent = extract_visual_prompt_intent("green healthy status light")
    base = bytearray()
    variant = bytearray()
    for y in range(8):
        for x in range(8):
            distance = (((x - 3.5) ** 2 + (y - 3.5) ** 2) ** 0.5) / 4
            gain = 0.38 + max(0.0, 1.0 - distance) * 0.72
            base.extend([int(38 * gain) + (x + y) % 3, int(220 * gain) + (x % 2), int(72 * gain), 255])
            variant.extend([int(39 * gain) + (x + y + 1) % 3, int(219 * gain) + ((x + 1) % 2), int(73 * gain), 255])

    left = build_visual_region_feature_embedding(request.mask, bytes(base), intent)
    right = build_visual_region_feature_embedding(request.mask, bytes(variant), intent)
    equivalence = evaluate_visual_region_equivalence(left, right)

    assert left.source_output_digest != right.source_output_digest
    assert equivalence.equivalent is True
    assert equivalence.distance <= equivalence.max_distance
    assert equivalence.receipt_digest.startswith("sha256:")
