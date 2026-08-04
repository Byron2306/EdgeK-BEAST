import base64
import hashlib
import json
from pathlib import Path

import pytest

from app.kernel.compute.compute_plane import ComputePlane, ScientificPromotionGate
from app.kernel.compute.native_context_restore_verifier import NativeContextRestoreVerifier, RestoreObservation
from app.kernel.compute.residual_contracts import sha256_digest
from app.kernel.compute.scene_synthesis import (
    CanvasContract,
    SceneCrystal,
    SceneOpcode,
    SceneOpcodeKind,
    default_beast_asset_manifest,
)
from app.kernel.networking.commons_spaces import build_manifest, build_reduction_receipt


def _runtime_scene(manifest):
    return SceneCrystal(
        scene_id="scene:compute-plane-status",
        manifest_digest=manifest.manifest_digest,
        canvas=CanvasContract(320, 160, "#07110d"),
        opcodes=(
            SceneOpcode(SceneOpcodeKind.PLACE_ASSET, {"asset_id": "beast.mascot.idle", "x": 12, "y": 24, "width": 72, "height": 72}),
            SceneOpcode(SceneOpcodeKind.DRAW_TEXT, {"x": 96, "y": 64, "text": "BEAST healthy", "font_size": 18}),
            SceneOpcode(SceneOpcodeKind.PLACE_ASSET, {"asset_id": "beast.status.card", "x": 96, "y": 82, "width": 190, "height": 56}),
        ),
        policy_digest=sha256_digest({"policy": "deterministic-scene-runtime.v1"}),
        verifier_id="compute-plane-test",
    )


def test_production_plane_constructs_every_enforcement_component(tmp_path: Path):
    plane = ComputePlane(root=tmp_path)
    plane.assert_production_composition()
    report = plane.reachability_report()

    assert set(plane.REQUIRED_COMPONENTS) == set(report["components"])
    assert report["read_only"] is True
    assert plane.streaming_interceptor.governor is plane.governor
    assert plane.physical_interpreter.applicability_gate is plane.physical_applicability
    assert plane.physical_interpreter.evidence is plane.evidence_graph
    assert plane.synthesis_plane is not None
    assert plane.operator_language_plane is not None
    assert plane.semantic_generalizer is not plane.episode_generalizer
    assert plane.semantic_crystal_registry is not None
    assert plane.scene_compositor is not None
    assert plane.visual_residual_worker is not None
    assert plane.forge_scheduler.strict_isolation is True


def test_streaming_cannot_run_without_shared_governor_gate(tmp_path: Path):
    plane = ComputePlane(root=tmp_path)

    async def empty_stream():
        if False:
            yield ""

    import asyncio
    with pytest.raises(PermissionError, match="shared compute gate"):
        asyncio.run(plane.streaming_interceptor.intercept_provider_stream(empty_stream()))


def test_production_forge_rejects_unattested_node(tmp_path: Path):
    plane = ComputePlane(root=tmp_path)
    with pytest.raises(PermissionError, match="isolation attestation"):
        plane.forge_scheduler.register_node("unattested")


def test_non_ir_lane_has_all_five_observable_phases(tmp_path: Path):
    plane = ComputePlane(root=tmp_path)
    result = plane.execute_operation(
        lane="local", provider="test", authorize=lambda: True,
        execute=lambda: {"value": 7}, verify=lambda value: value["value"] == 7,
    )
    assert result == {"value": 7}
    report = plane.reachability_report()
    for phase in ("begin", "authorize", "execute", "verify", "complete"):
        assert report["call_counters"][f"local.{phase}"] == 1
    assert report["last_receipt_ids"]["local"].startswith("plane:")


def test_operator_language_enters_through_synthesis_plane(tmp_path: Path):
    plane = ComputePlane(root=tmp_path)

    response = plane.answer_operator_prompt("what endpoint is beast on?", interface="test")
    report = plane.reachability_report()

    assert "127.0.0.1:8101" in response.output
    assert report["call_counters"]["synthesis.complete"] == 1
    assert report["call_counters"]["operator_language.resolved"] == 1
    assert report["last_receipt_ids"]["synthesis"]
    assert report["last_receipt_ids"]["operator_language"]


def test_operator_language_replays_promoted_semantic_crystal_for_paraphrase(tmp_path: Path):
    plane = ComputePlane(root=tmp_path)
    record = plane.promote_operator_language_semantic_crystal(
        ("what is beast status?", "is beast healthy?"),
        crystal_id="meaning-crystal:operator-language:beast-health",
    )

    response = plane.answer_operator_prompt("how is beast doing?", interface="test")
    report = plane.reachability_report()

    assert record.semantic_key_digest.startswith("sha256:")
    assert "beast" in response.output.casefold()
    assert response.receipt.reason == "semantic crystal replay: meaning-crystal:operator-language:beast-health"
    assert report["call_counters"]["operator_language.semantic_promoted"] == 1
    assert report["call_counters"]["operator_language.semantic_reused"] == 1
    assert report["call_counters"]["synthesis.complete"] == 1
    assert response.receipt.provider_called is False
    assert response.receipt.action_taken is False


def test_capability_learning_ledger_records_text_visual_reuse_and_demotion(tmp_path: Path):
    plane = ComputePlane(root=tmp_path)
    semantic = plane.promote_operator_language_semantic_crystal(
        ("what is beast status?", "is beast healthy?"),
        crystal_id="meaning-crystal:operator-language:beast-health",
    )
    plane.answer_operator_prompt("how is beast doing?", interface="test")
    manifest = default_beast_asset_manifest()
    scene = _runtime_scene(manifest)
    mask = {"mask_id": "mask:learning-status-light", "x": 240, "y": 44, "width": 16, "height": 16}
    plane.run_visual_residual(scene, manifest=manifest, mask=mask, prompt="green healthy status light", seed=21, interface="test")
    second = plane.run_visual_residual(scene, manifest=manifest, mask=mask, prompt="green healthy status light", seed=21, interface="test")
    third = plane.run_visual_residual(scene, manifest=manifest, mask=mask, prompt="green healthy status light", seed=21, interface="test")
    before_demote = plane.capability_learning_report()
    visual_asset_id = third.receipt.details["asset_id"]
    demoted = plane.demote_visual_asset(visual_asset_id, reason="gauntlet drift")
    revoked = plane.revoke_operator_language_semantic_crystal(semantic.crystal.crystal_id, reason="world drift")
    after_demote = plane.capability_learning_report()

    assert second.receipt.details["worker"] == "supervised_cpu_visual_residual"
    assert third.receipt.details["worker"] == "promoted_visual_asset_reuse"
    assert before_demote["beast_object_type"] == "capability_learning_report"
    assert before_demote["by_capability_type"]["semantic_crystal"] >= 2
    assert before_demote["by_capability_type"]["visual_asset"] >= 2
    assert before_demote["reuse_hits"] >= 2
    assert before_demote["provider_calls_avoided"] >= 2
    assert demoted.asset.asset_id == visual_asset_id
    assert revoked.lifecycle_state.value == "revoked"
    assert after_demote["by_event_type"]["demoted"] == 1
    assert after_demote["by_event_type"]["revoked"] == 1
    assert all(item["asset"]["asset_id"] != visual_asset_id for item in plane.visual_asset_registry_report()["assets"])
    assert after_demote["ledger_digest"].startswith("sha256:")


def test_scene_capsule_composes_through_compute_plane_with_render_only_witnesses(tmp_path: Path):
    plane = ComputePlane(root=tmp_path)
    manifest = default_beast_asset_manifest()
    scene = _runtime_scene(manifest)

    result = plane.compose_scene_capsule(scene, manifest=manifest, capsule_id="scene-capsule:compute-test", interface="test")
    again = plane.compose_scene_capsule(scene, manifest=manifest, capsule_id="scene-capsule:compute-test", interface="test")
    report = plane.reachability_report()

    assert result.svg == again.svg
    assert result.composition_receipt.output_digest == again.composition_receipt.output_digest
    assert result.capsule.capsule_digest == again.capsule.capsule_digest
    assert result.capsule.maximum_authority == "render_only"
    assert result.capsule.network_scope == "none"
    assert result.capsule.provider_scope == "none"
    assert result.capsule.physical_scope == "none"
    assert result.evidence_node_id
    assert report["call_counters"]["scene_capsule.composed"] == 2
    assert report["last_receipt_ids"]["scene_capsule"] == again.evidence_node_id


def test_scene_capsule_payload_rejects_manifest_drift(tmp_path: Path):
    plane = ComputePlane(root=tmp_path)
    payload = {
        "scene_id": "scene:bad-manifest",
        "manifest_digest": sha256_digest({"manifest": "not-default"}),
        "canvas": {"width": 100, "height": 80},
        "opcodes": [
            {"kind": "draw_text", "args": {"x": 10, "y": 20, "text": "nope"}},
        ],
    }

    with pytest.raises(ValueError, match="manifest_digest"):
        plane.compose_scene_capsule(payload, interface="test")


def test_provider_reduction_scorecard_unifies_runtime_displacement_channels(tmp_path: Path):
    plane = ComputePlane(root=tmp_path)
    plane.promote_operator_language_semantic_crystal(
        ("what is beast status?", "is beast healthy?"),
        crystal_id="meaning-crystal:operator-language:beast-health",
    )
    plane.answer_operator_prompt("how is beast doing?", interface="test")
    manifest = default_beast_asset_manifest()
    plane.compose_scene_capsule(_runtime_scene(manifest), manifest=manifest, interface="test")

    scorecard = plane.provider_reduction_scorecard()
    registry = plane.visual_asset_registry_report()
    channels = {item["channel"]: item for item in scorecard["observed_channels"]}
    unsupported = {item["channel"]: item for item in scorecard["unsupported_or_estimated_channels"]}

    assert scorecard["beast_object_type"] == "provider_reduction_scorecard"
    assert scorecard["semantic_replays"] == 1
    assert scorecard["provider_calls_avoided"] >= 1
    assert scorecard["provider_calls_used"] == 0
    assert scorecard["scene_capsules_composed"] == 1
    assert channels["semantic_crystals"]["provider_calls_avoided"] == 1
    assert channels["scene_capsules"]["events"] == 1
    assert unsupported["visual_image_generation"]["claim_class"] == "route_selection_only"
    assert unsupported["forge_kv_prompt_cache"]["claim_class"] == "hypothesis"
    assert scorecard["scorecard_digest"].startswith("sha256:")


def test_visual_residual_runs_through_scene_capsule_and_scorecard(tmp_path: Path):
    plane = ComputePlane(root=tmp_path)
    manifest = default_beast_asset_manifest()

    result = plane.run_visual_residual(
        _runtime_scene(manifest),
        manifest=manifest,
        mask={"mask_id": "mask:status-light", "x": 240, "y": 44, "width": 16, "height": 16},
        prompt="green healthy status light",
        seed=11,
        capsule_id="scene-capsule:visual-residual-test",
        interface="test",
    )
    again = plane.run_visual_residual(
        _runtime_scene(manifest),
        manifest=manifest,
        mask={"mask_id": "mask:status-light", "x": 240, "y": 44, "width": 16, "height": 16},
        prompt="green healthy status light",
        seed=11,
        capsule_id="scene-capsule:visual-residual-test",
        interface="test",
    )
    scorecard = plane.provider_reduction_scorecard()
    registry = plane.visual_asset_registry_report()
    channels = {item["channel"]: item for item in scorecard["observed_channels"]}

    assert result.output == again.output
    assert result.receipt.output_digest == again.receipt.output_digest
    assert result.receipt.scene_capsule_digest == result.scene_capsule.capsule_digest
    assert result.receipt.network_used is False
    assert result.receipt.details["region_only"] is True
    assert result.evidence_node_id
    assert scorecard["visual_regions_local"] == 2
    assert channels["visual_residuals"]["events"] == 2
    assert scorecard["provider_calls_used"] == 0


def test_visual_residual_promotes_repeated_regions_and_reuses_asset(tmp_path: Path):
    provider_calls = []

    def provider(payload):
        provider_calls.append(payload)
        return {"verified": True, "output_base64": "", "output_digest": sha256_digest({"empty": True})}

    plane = ComputePlane(root=tmp_path, provider_fallback=provider)
    manifest = default_beast_asset_manifest()
    scene = _runtime_scene(manifest)
    mask = {"mask_id": "mask:status-light", "x": 240, "y": 44, "width": 16, "height": 16}

    first = plane.run_visual_residual(
        scene,
        manifest=manifest,
        mask=mask,
        prompt="green healthy status light",
        seed=11,
        capsule_id="scene-capsule:visual-promotion-test",
        interface="test",
    )
    second = plane.run_visual_residual(
        scene,
        manifest=manifest,
        mask=mask,
        prompt="green healthy status light",
        seed=11,
        capsule_id="scene-capsule:visual-promotion-test",
        interface="test",
    )
    third = plane.run_visual_residual(
        scene,
        manifest=manifest,
        mask=mask,
        prompt="green healthy status light",
        seed=11,
        capsule_id="scene-capsule:visual-promotion-test",
        interface="test",
    )
    scorecard = plane.provider_reduction_scorecard()
    registry = plane.visual_asset_registry_report()
    channels = {item["channel"]: item for item in scorecard["observed_channels"]}

    assert first.output == second.output == third.output
    assert second.receipt.details["worker"] == "supervised_cpu_visual_residual"
    assert third.receipt.details["worker"] == "promoted_visual_asset_reuse"
    assert third.receipt.details["asset_id"].startswith("beast.visual.region.")
    assert scorecard["visual_regions_local"] == 2
    assert scorecard["visual_asset_promotions"] == 1
    assert scorecard["visual_asset_reuses"] == 1
    assert registry["count"] == 1
    assert registry["assets"][0]["asset"]["asset_id"] == third.receipt.details["asset_id"]
    assert registry["assets"][0]["provenance_receipts"]
    assert registry["registry_digest"].startswith("sha256:")
    assert channels["promoted_visual_assets"]["events"] == 2
    assert channels["visual_residuals"]["events"] == 3
    assert any(asset_id.startswith("beast.visual.region.") for asset_id, _digest in third.scene_capsule.asset_provenance)
    assert scorecard["provider_calls_used"] == 0
    with pytest.raises(PermissionError, match="promoted visual asset already exists"):
        plane.run_visual_provider_fallback(
            scene,
            manifest=manifest,
            mask=mask,
            prompt="green healthy status light",
            seed=11,
            capsule_id="scene-capsule:visual-promotion-test",
            allow_provider_fallback=True,
            operator_approval="approval:after-promotion",
            interface="test",
        )
    assert provider_calls == []


def test_visual_provider_fallback_requires_approval_and_is_counted(tmp_path: Path):
    provider_output = bytes([0, 255, 0, 255]) * (8 * 6)

    def provider(payload):
        assert payload["task_family"] == "visual_image_region_generation"
        assert payload["network_scope"] == ("provider_only",)
        assert payload["approval_receipt_digest"].startswith("sha256:")
        return {
            "verified": True,
            "output_base64": base64.b64encode(provider_output).decode("ascii"),
            "output_digest": "sha256:" + hashlib.sha256(provider_output).hexdigest(),
        }

    manifest = default_beast_asset_manifest()
    plane = ComputePlane(root=tmp_path, provider_fallback=provider)

    with pytest.raises(PermissionError, match="operator approval"):
        plane.run_visual_provider_fallback(
            _runtime_scene(manifest),
            manifest=manifest,
            mask={"mask_id": "mask:status-light", "x": 240, "y": 44, "width": 8, "height": 6},
            prompt="green healthy status light",
            allow_provider_fallback=True,
            operator_approval="",
            interface="test",
        )

    result = plane.run_visual_provider_fallback(
        _runtime_scene(manifest),
        manifest=manifest,
        mask={"mask_id": "mask:status-light", "x": 240, "y": 44, "width": 8, "height": 6},
        prompt="green healthy status light",
        allow_provider_fallback=True,
        operator_approval="approval:visual-region-test",
        provider="test-image-provider",
        interface="test",
    )
    scorecard = plane.provider_reduction_scorecard()
    unsupported = {item["channel"]: item for item in scorecard["unsupported_or_estimated_channels"]}

    assert result.output == provider_output
    assert result.receipt.final_status == "verified_visual_provider_fallback"
    assert result.receipt.provider_call_witness["during_execution"] == 1
    assert result.receipt.response_digest.startswith("sha256:")
    assert scorecard["provider_calls_used"] == 1
    assert scorecard["visual_provider_fallbacks"] == 1
    assert unsupported["visual_image_generation"]["provider_calls_used"] == 1


def test_visual_low_quality_provider_regions_are_refused_for_promotion(tmp_path: Path):
    low_quality_output = bytes([0, 0, 0, 0]) * (4 * 4)

    def provider(_payload):
        return {
            "verified": True,
            "output_base64": base64.b64encode(low_quality_output).decode("ascii"),
            "output_digest": "sha256:" + hashlib.sha256(low_quality_output).hexdigest(),
        }

    manifest = default_beast_asset_manifest()
    plane = ComputePlane(root=tmp_path, provider_fallback=provider)
    scene = _runtime_scene(manifest)
    mask = {"mask_id": "mask:bad-status-light", "x": 240, "y": 44, "width": 4, "height": 4}

    first = plane.run_visual_provider_fallback(
        scene,
        manifest=manifest,
        mask=mask,
        prompt="green healthy status light",
        seed=3,
        capsule_id="scene-capsule:visual-quality-refusal-test",
        allow_provider_fallback=True,
        operator_approval="approval:bad-region-1",
        interface="test",
    )
    second = plane.run_visual_provider_fallback(
        scene,
        manifest=manifest,
        mask=mask,
        prompt="green healthy status light",
        seed=3,
        capsule_id="scene-capsule:visual-quality-refusal-test",
        allow_provider_fallback=True,
        operator_approval="approval:bad-region-2",
        interface="test",
    )
    scorecard = plane.provider_reduction_scorecard()
    channels = {item["channel"]: item for item in scorecard["observed_channels"]}
    registry = plane.visual_asset_registry_report()
    refusals = plane.evidence_graph.query("visual_asset_candidate_refused")

    assert first.output == second.output == low_quality_output
    assert registry["count"] == 0
    assert scorecard["visual_asset_promotions"] == 0
    assert scorecard["visual_asset_refusals"] == 2
    assert channels["visual_asset_refusals"]["events"] == 2
    assert {item.receipt["reason"] for item in refusals} == {"quality_gate_failed"}
    assert all("insufficient_alpha_coverage" in item.receipt["quality_receipt"]["refusal_reasons"] for item in refusals)


def test_visual_provider_regions_that_miss_prompt_intent_are_refused_for_promotion(tmp_path: Path):
    bad_output = bytearray()
    for index in range(16):
        bad_output.extend([220 + index % 16, 30 + index % 16, 25, 255])
    red_region = bytes(bad_output)

    def provider(payload):
        assert payload["visual_intent_digest"].startswith("sha256:")
        return {
            "verified": True,
            "output_base64": base64.b64encode(red_region).decode("ascii"),
            "output_digest": "sha256:" + hashlib.sha256(red_region).hexdigest(),
        }

    manifest = default_beast_asset_manifest()
    plane = ComputePlane(root=tmp_path, provider_fallback=provider)
    scene = _runtime_scene(manifest)
    mask = {"mask_id": "mask:wrong-color-status-light", "x": 240, "y": 44, "width": 4, "height": 4}

    first = plane.run_visual_provider_fallback(
        scene,
        manifest=manifest,
        mask=mask,
        prompt="green healthy status light",
        seed=5,
        capsule_id="scene-capsule:visual-intent-refusal-test",
        allow_provider_fallback=True,
        operator_approval="approval:wrong-intent-1",
        interface="test",
    )
    second = plane.run_visual_provider_fallback(
        scene,
        manifest=manifest,
        mask=mask,
        prompt="green healthy status light",
        seed=5,
        capsule_id="scene-capsule:visual-intent-refusal-test",
        allow_provider_fallback=True,
        operator_approval="approval:wrong-intent-2",
        interface="test",
    )
    scorecard = plane.provider_reduction_scorecard()
    registry = plane.visual_asset_registry_report()
    refusals = plane.evidence_graph.query("visual_asset_candidate_refused")

    assert first.output == second.output == red_region
    assert registry["count"] == 0
    assert scorecard["visual_asset_promotions"] == 0
    assert scorecard["visual_asset_refusals"] == 2
    assert {item.receipt["reason"] for item in refusals} == {"intent_gate_failed"}
    assert all(item.receipt["intent_receipt"]["expected_color"] == "green" for item in refusals)
    assert all("color_intent_mismatch" in item.receipt["intent_receipt"]["refusal_reasons"] for item in refusals)


def test_visual_provider_regions_that_lack_perceptual_structure_are_refused_for_promotion(tmp_path: Path):
    weak_output = bytearray()
    for index in range(64):
        green = 182 + (index % 2) * 32
        weak_output.extend([26, green, 55, 255])
    weak_green_region = bytes(weak_output)

    def provider(payload):
        assert payload["visual_intent_digest"].startswith("sha256:")
        return {
            "verified": True,
            "output_base64": base64.b64encode(weak_green_region).decode("ascii"),
            "output_digest": "sha256:" + hashlib.sha256(weak_green_region).hexdigest(),
        }

    manifest = default_beast_asset_manifest()
    plane = ComputePlane(root=tmp_path, provider_fallback=provider)
    scene = _runtime_scene(manifest)
    mask = {"mask_id": "mask:flat-status-light", "x": 240, "y": 44, "width": 8, "height": 8}

    first = plane.run_visual_provider_fallback(
        scene,
        manifest=manifest,
        mask=mask,
        prompt="green healthy status light",
        seed=6,
        capsule_id="scene-capsule:visual-perceptual-refusal-test",
        allow_provider_fallback=True,
        operator_approval="approval:weak-visual-1",
        interface="test",
    )
    second = plane.run_visual_provider_fallback(
        scene,
        manifest=manifest,
        mask=mask,
        prompt="green healthy status light",
        seed=6,
        capsule_id="scene-capsule:visual-perceptual-refusal-test",
        allow_provider_fallback=True,
        operator_approval="approval:weak-visual-2",
        interface="test",
    )
    scorecard = plane.provider_reduction_scorecard()
    registry = plane.visual_asset_registry_report()
    refusals = plane.evidence_graph.query("visual_asset_candidate_refused")

    assert first.output == second.output == weak_green_region
    assert registry["count"] == 0
    assert scorecard["visual_asset_promotions"] == 0
    assert scorecard["visual_asset_refusals"] == 2
    assert {item.receipt["reason"] for item in refusals} == {"perceptual_gate_failed"}
    assert all(item.receipt["intent_receipt_digest"].startswith("sha256:") for item in refusals)
    assert all(item.receipt["perceptual_receipt"]["object_hint"] == "status_light" for item in refusals)
    assert all("status_light_not_center_focused" in item.receipt["perceptual_receipt"]["refusal_reasons"] for item in refusals)


def test_visual_provider_equivalent_regions_promote_without_exact_byte_match(tmp_path: Path):
    outputs = []
    for delta in (0, 1):
        region = bytearray()
        for y in range(8):
            for x in range(8):
                distance = (((x - 3.5) ** 2 + (y - 3.5) ** 2) ** 0.5) / 4
                gain = 0.38 + max(0.0, 1.0 - distance) * 0.72
                region.extend([
                    int((38 + delta) * gain) + (x + y + delta) % 3,
                    int((220 - delta) * gain) + ((x + delta) % 2),
                    int((72 + delta) * gain),
                    255,
                ])
        outputs.append(bytes(region))
    provider_calls = []

    def provider(payload):
        output = outputs[len(provider_calls)]
        provider_calls.append(payload)
        return {
            "verified": True,
            "output_base64": base64.b64encode(output).decode("ascii"),
            "output_digest": "sha256:" + hashlib.sha256(output).hexdigest(),
        }

    manifest = default_beast_asset_manifest()
    plane = ComputePlane(root=tmp_path, provider_fallback=provider)
    scene = _runtime_scene(manifest)
    mask = {"mask_id": "mask:equivalent-status-light", "x": 240, "y": 44, "width": 8, "height": 8}

    first = plane.run_visual_provider_fallback(
        scene,
        manifest=manifest,
        mask=mask,
        prompt="green healthy status light",
        seed=7,
        capsule_id="scene-capsule:visual-equivalence-promotion-test",
        allow_provider_fallback=True,
        operator_approval="approval:eq-visual-1",
        interface="test",
    )
    second = plane.run_visual_provider_fallback(
        scene,
        manifest=manifest,
        mask=mask,
        prompt="green healthy status light",
        seed=7,
        capsule_id="scene-capsule:visual-equivalence-promotion-test",
        allow_provider_fallback=True,
        operator_approval="approval:eq-visual-2",
        interface="test",
    )
    reuse = plane.run_visual_residual(
        scene,
        manifest=manifest,
        mask=mask,
        prompt="green healthy status light",
        seed=7,
        capsule_id="scene-capsule:visual-equivalence-promotion-test",
        interface="test",
    )
    scorecard = plane.provider_reduction_scorecard()
    registry = plane.visual_asset_registry_report()
    equivalence_nodes = plane.evidence_graph.query("visual_asset_candidate_equivalent")
    refusals = plane.evidence_graph.query("visual_asset_candidate_refused")

    assert first.output != second.output
    assert registry["count"] == 1
    assert registry["assets"][0]["feature_embedding_digest"].startswith("sha256:")
    assert registry["assets"][0]["equivalence_receipt_digest"].startswith("sha256:")
    assert equivalence_nodes
    assert equivalence_nodes[0].receipt["equivalence_receipt"]["equivalent"] is True
    assert not refusals
    assert reuse.receipt.details["worker"] == "promoted_visual_asset_reuse"
    assert reuse.receipt.details["visual_intent"]["equivalence_receipt_digest"].startswith("sha256:")
    assert scorecard["visual_provider_fallbacks"] == 2
    assert scorecard["visual_asset_promotions"] == 1
    assert scorecard["visual_asset_reuses"] == 1
    assert len(provider_calls) == 2


def test_reduction_evidence_ingests_forge_kv_only_with_native_restore_proof(tmp_path: Path):
    plane = ComputePlane(root=tmp_path)
    context_digest = sha256_digest({"context": "kv-block"})
    verifier = NativeContextRestoreVerifier()
    observed = verifier.verify(
        source_context_digest=context_digest,
        baseline=RestoreObservation(
            restored=False,
            prompt_eval_count=80,
            prompt_eval_duration_ns=1_000_000,
            continuation="ok",
            context_digest_observed=context_digest,
            metadata={},
        ),
        restored=RestoreObservation(
            restored=True,
            prompt_eval_count=12,
            prompt_eval_duration_ns=100_000,
            continuation="ok",
            context_digest_observed=context_digest,
            metadata={},
        ),
    )
    metadata_only = {
        "beast_object_type": "forge_kv_episode_economics",
        "authority": "observation_only",
        "paired_baseline_present": True,
        "prompt_tokens_avoided": 999,
    }

    proof_result = plane.ingest_reduction_evidence("forge_kv_prompt_cache", observed.__dict__, interface="test")
    metadata_result = plane.ingest_reduction_evidence("forge_kv_prompt_cache", metadata_only, interface="test")
    scorecard = plane.provider_reduction_scorecard()
    channels = {item["channel"]: item for item in scorecard["observed_channels"]}
    unsupported = {item["channel"]: item for item in scorecard["unsupported_or_estimated_channels"]}

    assert proof_result["claim_class"] == "observed"
    assert proof_result["tokens_avoided_observed"] == 68
    assert metadata_result["claim_class"] == "route_selection_only"
    assert metadata_result["tokens_avoided_observed"] == 0
    assert scorecard["tokens_avoided_observed"] == 68
    assert scorecard["normalized_evidence_events"] == 2
    assert channels["forge_kv_prompt_cache"]["tokens_avoided_observed"] == 68
    assert channels["forge_kv_prompt_cache"]["events"] == 2
    assert "forge_kv_prompt_cache" not in unsupported


def test_reduction_evidence_ingests_engine_local_forge_kv_nodes_and_restart_boundary(tmp_path: Path):
    plane = ComputePlane(root=tmp_path)
    prompt_cache = {
        "authority": "engine_local_prompt_cache_only",
        "beast_object_type": "forge_kv_llamacpp_prompt_cache_proof",
        "created_at": 1784548285.0,
        "engine": "llama.cpp",
        "portable_raw_kv": False,
        "prefix_digest": "sha256:" + "a" * 64,
        "trials": [
            {"baseline": {"prompt_n": 100, "prompt_ms": 1000.0}, "cached": {"prompt_n": 8, "prompt_ms": 50.0}},
            {"baseline": {"prompt_n": 100, "prompt_ms": 900.0}, "cached": {"prompt_n": 8, "prompt_ms": 40.0}},
        ],
        "validated": True,
    }
    restart_boundary = {
        "authority": "engine_local_prompt_cache_only",
        "beast_object_type": "forge_kv_llamacpp_restart_boundary_proof",
        "before_restart": {
            "baseline": {"prompt_n": 100, "prompt_ms": 1000.0},
            "warm_cache": {"prompt_n": 7, "prompt_ms": 60.0},
        },
        "after_restart": {"cache_n": 0, "prompt_n": 100, "prompt_ms": 990.0},
        "portable_raw_kv": False,
        "prefix_digest": "sha256:" + "b" * 64,
        "validated": True,
    }

    observed = plane.ingest_reduction_evidence("forge_kv_prompt_cache", prompt_cache, interface="test")
    boundary = plane.ingest_reduction_evidence("forge_kv_prompt_cache", restart_boundary, interface="test")
    scorecard = plane.provider_reduction_scorecard()
    learning = plane.capability_learning_report()
    channels = {item["channel"]: item for item in scorecard["observed_channels"]}

    assert observed["claim_class"] == "observed"
    assert observed["tokens_avoided_observed"] == 184
    assert observed["portable_raw_kv"] is False
    assert boundary["claim_class"] == "route_selection_only"
    assert boundary["restart_cache_reset"] is True
    assert scorecard["tokens_avoided_observed"] == 184
    assert channels["forge_kv_prompt_cache"]["events"] == 2
    assert learning["by_capability_type"]["forge_kv_node"] == 2
    states = {item["lifecycle_state"] for item in learning["capabilities"]}
    assert "observed_engine_local" in states
    assert "restart_boundary_observed" in states


def test_reduction_evidence_ingests_ml_kem_bound_forge_kv_transport_without_counting_savings(tmp_path: Path):
    from app.kernel.commons.ml_kem import ML_KEM_ALGORITHM
    from app.kernel.compute.forge_kv_ml_kem_transport import build_ml_kem_bound_transport_receipt

    plane = ComputePlane(root=tmp_path)
    checksum = "sha256:" + "a" * 64
    transport_receipt = build_ml_kem_bound_transport_receipt(
        kv_manifest={
            "beast_object_type": "kv_cache_network_manifest",
            "version": "1.0",
            "status": "transferred",
            "block_id": "kv_mlkem_compute",
            "transfer_id": "transfer_mlkem_compute",
            "model": "llama",
            "tokenizer": "tok",
            "prompt_prefix_hash": "sha256:" + "b" * 64,
            "system_prompt_hash": "sha256:" + "c" * 64,
            "engine": "sglang",
            "target_engine": "sglang",
            "precision": "bf16",
            "num_layers": 2,
            "num_heads": 2,
            "head_dim": 8,
            "seq_len": 16,
            "size_bytes": 19,
            "source_node": "commons-a",
            "target_endpoint": "https://commons-b.example/edgek/kv-cache/receive",
            "checksum_sha256": checksum,
            "tensor_payload_sha256": checksum,
            "tensor_payload_format": "safetensors",
            "engine_native_tensor_payload": True,
            "acknowledgement": {
                "accepted": True,
                "block_id": "kv_mlkem_compute",
                "transfer_id": "transfer_mlkem_compute",
                "tensor_payload_sha256": checksum,
                "stored_location": "storage",
            },
        },
        ml_kem_receipt={
            "beast_object_type": "commons_ml_kem_gauntlet_receipt",
            "version": "1.0",
            "status": "passed",
            "algorithm": ML_KEM_ALGORITHM,
            "nodes": [
                {
                    "node_id": "commons-a",
                    "confirmed": True,
                    "secret_exported": False,
                    "public_key_digest": "sha256:" + "d" * 64,
                    "ciphertext_digest": "sha256:" + "e" * 64,
                    "transcript_digest": "sha256:" + "f" * 64,
                },
                {
                    "node_id": "commons-b",
                    "confirmed": True,
                    "secret_exported": False,
                    "public_key_digest": "sha256:" + "1" * 64,
                    "ciphertext_digest": "sha256:" + "2" * 64,
                    "transcript_digest": "sha256:" + "3" * 64,
                },
            ],
            "pairwise_transcript_matrix": [
                {"source": "commons-a", "target": "commons-b", "transcript_digest": "sha256:" + "4" * 64}
            ],
            "secret_storage_policy": "shared_secret_bytes_never_serialized",
            "receipt_digest": "sha256:" + "5" * 64,
        },
    )

    result = plane.ingest_reduction_evidence("forge_kv_prompt_cache", transport_receipt, interface="test")
    scorecard = plane.provider_reduction_scorecard()
    learning = plane.capability_learning_report()

    assert result["claim_class"] == "route_selection_only"
    assert result["verified"] is True
    assert result["transport_verified"] is True
    assert result["bytes_transferred_verified"] == 19
    assert result["provider_calls_avoided"] == 0
    assert result["tokens_avoided_observed"] == 0
    assert scorecard["tokens_avoided_observed"] == 0
    assert scorecard["provider_calls_avoided"] == 0
    assert learning["by_capability_type"]["forge_kv_node"] == 1
    assert learning["capabilities"][0]["lifecycle_state"] == "transport_verified"


def test_reduction_evidence_reports_g9_health_without_counting_savings(tmp_path: Path):
    plane = ComputePlane(root=tmp_path)
    g9_bundle = {
        "beast_object_type": "grand_closure_g9_evidence_bundle",
        "validation": {
            "required_gates": ["G1", "G2", "G3"],
            "present_gates": ["G1", "G2"],
            "missing_gates": ["G3"],
            "valid": False,
        },
        "bundle_digest": sha256_digest({"bundle": "missing-g3"}),
        "provider_calls_avoided": 999,
    }

    result = plane.ingest_reduction_evidence("grand_closure_g9", g9_bundle, interface="test")
    scorecard = plane.provider_reduction_scorecard()
    unsupported = {item["channel"]: item for item in scorecard["unsupported_or_estimated_channels"]}

    assert result["claim_class"] == "route_selection_only"
    assert result["provider_calls_avoided"] == 0
    assert scorecard["provider_calls_avoided"] == 0
    assert scorecard["g9_bundle_health"][0]["missing_gates"] == ("G3",)
    assert scorecard["g9_bundle_health"][0]["valid"] is False
    assert unsupported["grand_closure"]["claim_class"] == "route_selection_only"


def test_commons_space_reduction_counts_only_after_local_reproduction(tmp_path: Path):
    plane = ComputePlane(root=tmp_path)
    evidence_path = tmp_path / "commons-evidence.json"
    evidence_path.write_text('{"verified": true}\n', encoding="utf-8")
    manifest = build_manifest(
        tmp_path,
        space_id="space:local-reproduced",
        name="Local Reproduced",
        task_class="operator_language",
        artifacts=[{"path": evidence_path.name, "artifact_type": "evidence"}],
        hardware_profile={},
        verifier_bundles=[],
        reduction_claims={"tokens_avoided": 11},
        safety={"approval_required": True},
    )
    receipt = build_reduction_receipt(
        space_manifest=manifest,
        baseline_route={"route_id": "provider"},
        optimized_route={"route_id": "local", "local_reproduction_verified": True},
        displacement={"provider_calls_avoided": 1, "provider_tokens_avoided": 11},
        verifier={"passed": True},
        resource_deltas={},
        provenance={"source": "test", "local_reproduction_verified": True},
        rollback_available=True,
        approval_required=True,
    )
    unverified = dict(receipt)
    unverified["provenance"] = {"source": "test"}
    unverified["optimized_route"] = {"route_id": "local"}

    observed = plane.ingest_reduction_evidence("commons_spaces", receipt, interface="test")
    hypothesis = plane.ingest_reduction_evidence("commons_spaces", unverified, interface="test")
    scorecard = plane.provider_reduction_scorecard()
    channels = {item["channel"]: item for item in scorecard["observed_channels"]}
    unsupported = {item["channel"]: item for item in scorecard["unsupported_or_estimated_channels"]}

    assert observed["claim_class"] == "observed"
    assert observed["provider_calls_avoided"] == 1
    assert hypothesis["claim_class"] == "hypothesis"
    assert hypothesis["provider_calls_avoided"] == 0
    assert scorecard["provider_calls_avoided"] == 1
    assert scorecard["tokens_avoided_observed"] == 11
    assert channels["commons_spaces"]["provider_calls_avoided"] == 1
    assert channels["commons_spaces"]["events"] == 2
    assert "commons_spaces" not in unsupported


def test_reduction_evidence_ingests_sensorium_disk_pressure_as_resource_governance(tmp_path: Path):
    plane = ComputePlane(root=tmp_path)
    receipt = {
        "schema": "beast.sensorium.disk-cleanup-evidence.v1",
        "claim": "learned_bounded_disk_cleanup_candidate",
        "crystal": {
            "identity": "crystal:sensorium-disk-cleanup:v1",
            "artifact_digest": "sha256:" + "c" * 64,
        },
        "replay": {
            "promotion_eligible": True,
            "verified_variants": 2,
            "variant_receipts": [{"verified": True}, {"verified": True}],
        },
        "safety": {
            "manifest_identity_fields": ["device", "inode", "size", "mtime_ns", "sha256"],
        },
        "production_promotion_allowed": False,
    }

    result = plane.ingest_reduction_evidence("sensorium_disk_pressure", receipt, interface="test")
    scorecard = plane.provider_reduction_scorecard()
    unsupported = {item["channel"]: item for item in scorecard["unsupported_or_estimated_channels"]}
    learning = plane.capability_learning_report()
    capabilities = {item["capability_id"]: item for item in learning["capabilities"]}

    assert result["source_system"] == "sensorium"
    assert result["claim_class"] == "route_selection_only"
    assert result["verified"] is True
    assert result["sensorium_capability"] == "disk_pressure_governed_cleanup"
    assert result["production_promotion_allowed"] is False
    assert result["provider_calls_avoided"] == 0
    assert scorecard["normalized_evidence_events"] == 1
    assert unsupported["sensorium"]["claim_class"] == "route_selection_only"
    assert learning["by_capability_type"]["sensorium_physical_crystal"] == 1
    assert capabilities["crystal:sensorium-disk-cleanup:v1"]["lifecycle_state"] == "promotion_blocked_destructive"


def test_reduction_evidence_discovery_imports_repo_local_receipts_idempotently(tmp_path: Path):
    plane = ComputePlane(root=tmp_path)
    incoming = tmp_path / "evidence" / "incoming"
    incoming.mkdir(parents=True)
    context_digest = sha256_digest({"context": "discovery-kv-block"})
    observed = NativeContextRestoreVerifier().verify(
        source_context_digest=context_digest,
        baseline=RestoreObservation(
            restored=False,
            prompt_eval_count=50,
            prompt_eval_duration_ns=900_000,
            continuation="same",
            context_digest_observed=context_digest,
            metadata={},
        ),
        restored=RestoreObservation(
            restored=True,
            prompt_eval_count=5,
            prompt_eval_duration_ns=90_000,
            continuation="same",
            context_digest_observed=context_digest,
            metadata={},
        ),
    )
    (incoming / "forge-kv-native-restore.json").write_text(
        json.dumps(observed.__dict__, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (incoming / "grand-closure-g9-missing-g3.json").write_text(
        json.dumps({
            "beast_object_type": "grand_closure_g9_evidence_bundle",
            "validation": {
                "required_gates": ["G1", "G2", "G3"],
                "present_gates": ["G1", "G2"],
                "missing_gates": ["G3"],
                "valid": False,
            },
        }, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (incoming / "sensorium-disk-cleanup.json").write_text(
        json.dumps({
            "schema": "beast.sensorium.disk-cleanup-evidence.v1",
            "claim": "learned_bounded_disk_cleanup_candidate",
            "crystal": {"identity": "crystal:sensorium-disk-cleanup:v1", "artifact_digest": "sha256:" + "d" * 64},
            "replay": {"promotion_eligible": True, "verified_variants": 1, "variant_receipts": [{"verified": True}]},
            "safety": {"manifest_identity_fields": ["device", "inode", "size", "mtime_ns", "sha256"]},
            "production_promotion_allowed": False,
        }, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (incoming / "llamacpp-prompt-cache.json").write_text(
        json.dumps({
            "beast_object_type": "forge_kv_llamacpp_prompt_cache_proof",
            "engine": "llama.cpp",
            "portable_raw_kv": False,
            "prefix_digest": "sha256:" + "e" * 64,
            "trials": [{"baseline": {"prompt_n": 40, "prompt_ms": 500.0}, "cached": {"prompt_n": 4, "prompt_ms": 50.0}}],
            "validated": True,
        }, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (incoming / "raw-prompt-forbidden.json").write_text(
        json.dumps({"beast_object_type": "forge_kv_episode_economics", "raw_prompt": "nope"}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (incoming / "unknown.json").write_text('{"hello": "world"}\n', encoding="utf-8")

    report = plane.discover_reduction_evidence(paths=(incoming,), interface="test")
    again = plane.discover_reduction_evidence(paths=(incoming,), interface="test")
    scorecard = plane.provider_reduction_scorecard()

    assert report["files_considered"] == 6
    assert report["ingested_count"] == 4
    assert report["source_counts"] == {"forge_kv_prompt_cache": 2, "grand_closure": 1, "sensorium": 1}
    assert any(item["reason"] == "PermissionError" for item in report["skipped"])
    assert any(item["reason"] == "unrecognized_reduction_evidence" for item in report["skipped"])
    assert again["ingested_count"] == 0
    assert again["duplicate_count"] == 4
    assert scorecard["normalized_evidence_events"] == 4
    assert scorecard["tokens_avoided_observed"] == 81
    assert scorecard["g9_bundle_health"][0]["missing_gates"] == ("G3",)


def test_provider_reduction_scorecard_reports_trend_buckets(tmp_path: Path):
    plane = ComputePlane(root=tmp_path)
    plane.promote_operator_language_semantic_crystal(
        ("what is beast status?", "is beast healthy?"),
        crystal_id="meaning-crystal:operator-language:beast-health",
    )
    plane.answer_operator_prompt("how is beast doing?", interface="test")
    manifest = default_beast_asset_manifest()
    scene = _runtime_scene(manifest)
    mask = {"mask_id": "mask:trend-status-light", "x": 240, "y": 44, "width": 16, "height": 16}
    plane.run_visual_residual(scene, manifest=manifest, mask=mask, prompt="green healthy status light", seed=17, interface="test")
    plane.run_visual_residual(scene, manifest=manifest, mask=mask, prompt="green healthy status light", seed=17, interface="test")
    plane.run_visual_residual(scene, manifest=manifest, mask=mask, prompt="green healthy status light", seed=17, interface="test")
    context_digest = sha256_digest({"context": "trend-kv-block"})
    restore = NativeContextRestoreVerifier().verify(
        source_context_digest=context_digest,
        baseline=RestoreObservation(
            restored=False,
            prompt_eval_count=25,
            prompt_eval_duration_ns=500_000,
            continuation="ok",
            context_digest_observed=context_digest,
            metadata={},
        ),
        restored=RestoreObservation(
            restored=True,
            prompt_eval_count=3,
            prompt_eval_duration_ns=50_000,
            continuation="ok",
            context_digest_observed=context_digest,
            metadata={},
        ),
    )
    plane.ingest_reduction_evidence("forge_kv_prompt_cache", restore.__dict__, interface="test")

    scorecard = plane.provider_reduction_scorecard()
    buckets = scorecard["trend_buckets"]
    totals = {
        "events": sum(item["events"] for item in buckets),
        "provider_calls_avoided": sum(item["provider_calls_avoided"] for item in buckets),
        "tokens_avoided_observed": sum(item["tokens_avoided_observed"] for item in buckets),
        "visual_promoted_asset_reuses": sum(item["visual_promoted_asset_reuses"] for item in buckets),
        "semantic_replays": sum(item["semantic_replays"] for item in buckets),
        "normalized_evidence_events": sum(item["normalized_evidence_events"] for item in buckets),
    }

    assert buckets
    assert all(item["period"] != "undated" for item in buckets)
    assert totals["events"] >= 6
    assert totals["provider_calls_avoided"] >= 1
    assert totals["tokens_avoided_observed"] == 22
    assert totals["visual_promoted_asset_reuses"] == 1
    assert totals["semantic_replays"] == 1
    assert totals["normalized_evidence_events"] == 1
    assert all(item["bucket_digest"].startswith("sha256:") for item in buckets)


def test_promotion_requires_independent_heldout_and_displacement_receipts():
    with pytest.raises(PermissionError, match="heldout_ablation"):
        ScientificPromotionGate.require({})
    evidence = {
        "heldout_ablation": {"receipt_id": "ablation:1", "verified": True, "held_out": True},
        "displacement": {"receipt_id": "displacement:1", "verified": True, "provider_calls_avoided": 3},
    }
    assert ScientificPromotionGate.require(evidence) == {
        "heldout_ablation": "ablation:1", "displacement": "displacement:1"
    }
