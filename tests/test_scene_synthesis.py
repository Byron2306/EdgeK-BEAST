import pytest

from app.kernel.compute.residual_contracts import sha256_digest
from app.kernel.compute.scene_synthesis import (
    AssetKind,
    CanvasContract,
    DeterministicSceneCompositor,
    SceneCapsule,
    SceneCrystal,
    SceneOpcode,
    SceneOpcodeKind,
    default_beast_asset_manifest,
    run_visual_corpus,
    seal_scene_capsule,
)


def _scene(manifest):
    return SceneCrystal(
        scene_id="scene:beast-status-card",
        manifest_digest=manifest.manifest_digest,
        canvas=CanvasContract(420, 220, "#07110d"),
        opcodes=(
            SceneOpcode(SceneOpcodeKind.DRAW_RECT, {"x": 8, "y": 8, "width": 404, "height": 204, "rx": 6, "fill": "#0b1712", "stroke": "#1f3a2d"}),
            SceneOpcode(SceneOpcodeKind.PLACE_ASSET, {"asset_id": "beast.mascot.idle", "x": 24, "y": 44, "width": 96, "height": 96}),
            SceneOpcode(SceneOpcodeKind.DRAW_TEXT, {"x": 140, "y": 72, "text": "BEAST healthy", "font_size": 22, "fill": "#e8fff1"}),
            SceneOpcode(SceneOpcodeKind.DRAW_LINE, {"x1": 140, "y1": 96, "x2": 360, "y2": 96, "stroke": "#52ff91", "stroke_width": 2}),
            SceneOpcode(SceneOpcodeKind.PLACE_ASSET, {"asset_id": "beast.status.card", "x": 140, "y": 112, "width": 220, "height": 70}),
        ),
        policy_digest=sha256_digest({"policy": "deterministic-scene-v1"}),
        verifier_id="scene-test",
    )


def test_default_asset_manifest_covers_i1_visual_classes():
    manifest = default_beast_asset_manifest()

    assert {asset.kind for asset in manifest.assets} == {
        AssetKind.MASCOT_STATE,
        AssetKind.DIAGRAM,
        AssetKind.STATUS_CARD,
        AssetKind.IDE_ASSET,
    }
    assert manifest.manifest_digest.startswith("sha256:")


def test_scene_crystal_composes_stable_svg_with_asset_provenance():
    manifest = default_beast_asset_manifest()
    scene = _scene(manifest)

    svg, receipt = DeterministicSceneCompositor().compose(scene, manifest)
    svg_again, receipt_again = DeterministicSceneCompositor().compose(scene, manifest)

    assert svg == svg_again
    assert receipt.output_digest == receipt_again.output_digest
    assert receipt.verified is True
    assert receipt.asset_provenance == (
        ("beast.mascot.idle", manifest.asset("beast.mascot.idle").digest),
        ("beast.status.card", manifest.asset("beast.status.card").digest),
    )
    assert "asset:beast.mascot.idle#" in svg


def test_scene_capsule_seals_render_only_visual_custody():
    manifest = default_beast_asset_manifest()
    scene = _scene(manifest)

    svg, receipt, capsule = DeterministicSceneCompositor().compose_capsule(scene, manifest)
    sealed_again = seal_scene_capsule(scene, manifest, receipt, capsule_id=capsule.capsule_id)

    assert svg.startswith("<svg")
    assert capsule.scene_digest == scene.scene_digest
    assert capsule.manifest_digest == manifest.manifest_digest
    assert capsule.composition_receipt_digest == receipt.receipt_digest
    assert capsule.output_digest == receipt.output_digest
    assert capsule.policy_digest == scene.policy_digest
    assert capsule.maximum_authority == "render_only"
    assert capsule.network_scope == "none"
    assert capsule.provider_scope == "none"
    assert capsule.physical_scope == "none"
    assert capsule.capsule_digest == sealed_again.capsule_digest


def test_scene_capsule_rejects_mismatched_receipts_and_expanded_authority():
    manifest = default_beast_asset_manifest()
    scene = _scene(manifest)
    _svg, receipt = DeterministicSceneCompositor().compose(scene, manifest)
    tampered = SceneCrystal(
        scene_id="scene:tampered",
        manifest_digest=manifest.manifest_digest,
        canvas=scene.canvas,
        opcodes=scene.opcodes,
        policy_digest=scene.policy_digest,
        verifier_id="scene-test",
    )

    with pytest.raises(ValueError, match="same scene"):
        seal_scene_capsule(tampered, manifest, receipt)
    with pytest.raises(ValueError, match="maximum authority"):
        SceneCapsule(
            capsule_id="scene-capsule:bad",
            scene_id=scene.scene_id,
            scene_digest=scene.scene_digest,
            manifest_digest=manifest.manifest_digest,
            composition_receipt_digest=receipt.receipt_digest,
            output_digest=receipt.output_digest,
            policy_digest=scene.policy_digest,
            canvas_digest=receipt.canvas_digest,
            asset_provenance=receipt.asset_provenance,
            output_format=scene.output_format,
            maximum_authority="execute",
        )


def test_scene_compositor_rejects_missing_asset_and_canvas_overflow():
    manifest = default_beast_asset_manifest()
    missing_asset = SceneCrystal(
        scene_id="scene:bad-asset",
        manifest_digest=manifest.manifest_digest,
        canvas=CanvasContract(100, 100),
        opcodes=(SceneOpcode(SceneOpcodeKind.PLACE_ASSET, {"asset_id": "missing", "x": 0, "y": 0}),),
        policy_digest=sha256_digest({"policy": "deterministic-scene-v1"}),
        verifier_id="scene-test",
    )
    overflow = SceneCrystal(
        scene_id="scene:overflow",
        manifest_digest=manifest.manifest_digest,
        canvas=CanvasContract(100, 100),
        opcodes=(SceneOpcode(SceneOpcodeKind.DRAW_RECT, {"x": 90, "y": 90, "width": 20, "height": 20}),),
        policy_digest=sha256_digest({"policy": "deterministic-scene-v1"}),
        verifier_id="scene-test",
    )

    with pytest.raises(ValueError, match="unknown asset"):
        DeterministicSceneCompositor().compose(missing_asset, manifest)
    with pytest.raises(ValueError, match="canvas bounds"):
        DeterministicSceneCompositor().compose(overflow, manifest)


def test_visual_corpus_meets_i1_deterministic_threshold_for_100_requests():
    manifest = default_beast_asset_manifest()
    scenes = tuple(
        SceneCrystal(
            scene_id=f"scene:status:{index}",
            manifest_digest=manifest.manifest_digest,
            canvas=CanvasContract(320, 160, "#07110d"),
            opcodes=(
                SceneOpcode(SceneOpcodeKind.PLACE_ASSET, {"asset_id": "beast.mascot.idle", "x": 12, "y": 24, "width": 72, "height": 72}),
                SceneOpcode(SceneOpcodeKind.PLACE_ASSET, {"asset_id": "beast.status.card", "x": 96, "y": 32, "width": 190, "height": 70}),
                SceneOpcode(SceneOpcodeKind.DRAW_TEXT, {"x": 96, "y": 124, "text": f"request {index:03d}", "font_size": 14}),
            ),
            policy_digest=sha256_digest({"policy": "deterministic-scene-v1"}),
            verifier_id="scene-corpus-test",
        )
        for index in range(100)
    )

    receipt = run_visual_corpus(scenes, manifest, threshold=0.75)

    assert receipt.scene_count == 100
    assert receipt.deterministic_rate == 1.0
    assert receipt.provenance_verified_count == 100
    assert receipt.passed is True
