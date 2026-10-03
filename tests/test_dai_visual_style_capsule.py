from __future__ import annotations

from dataclasses import asdict

from PIL import Image

from app.kernel.compute.deterministic_intelligence import sha256_digest
from app.kernel.dai.capability_ledger import CapabilityCrystal, CapabilityLedger, LEDGER_VERSION
from app.kernel.dai.constitutional_runtime_router import (
    BeastRuntimeContext,
    BeastRuntimeRequest,
    route_beast_runtime_request,
)
from app.kernel.dai.visual_style_capsule import (
    apply_visual_style_to_svg,
    teach_visual_style_from_reference,
    write_visual_style_capsule,
)


def _context(style: dict | None = None) -> BeastRuntimeContext:
    return BeastRuntimeContext(
        ledger=CapabilityLedger(
            beast_object_type="dai_capability_ledger",
            version=LEDGER_VERSION,
            ledger_id="test:ledger",
            crystals=(
                CapabilityCrystal(
                    crystal_id="crystal:test:restart",
                    family="restart_risk_composition",
                    source_phase="test",
                    capability_digest=sha256_digest("restart"),
                    receipt_digest=sha256_digest("restart-receipt"),
                    predicate_ids=("healthy", "depends_path_to", "restart_policy_ordered"),
                ),
                CapabilityCrystal(
                    crystal_id="crystal:test:sophia",
                    family="sophia_source_support",
                    source_phase="test",
                    capability_digest=sha256_digest("sophia"),
                    receipt_digest=sha256_digest("sophia-receipt"),
                    predicate_ids=("visible_source_span_bound", "source_supports_claim"),
                ),
            ),
        ),
        phase6_4_constitutional_receipt={"green": True, "receipt_digest": sha256_digest("phase6.4")},
        phase6_5_formal_receipt={"green": True, "receipt_digest": sha256_digest("phase6.5")},
        visual_style_capsule=style,
    )


def test_teach_visual_style_from_reference_extracts_digest_bound_capsule(tmp_path) -> None:
    image_path = tmp_path / "reference.png"
    image = Image.new("RGB", (32, 32), "#201030")
    for x in range(8, 24):
        for y in range(8, 24):
            image.putpixel((x, y), (240, 180, 80))
    image.save(image_path)

    capsule = teach_visual_style_from_reference(image_path, capsule_id="test:style")
    out = tmp_path / "style.json"
    write_visual_style_capsule(out, capsule)

    assert capsule.reference_image_digest.startswith("sha256:")
    assert capsule.capsule_digest.startswith("sha256:")
    assert len(capsule.palette) >= 2
    assert out.exists()


def test_style_application_preserves_semantics_fact_ids_edges_and_labels(tmp_path) -> None:
    image_path = tmp_path / "reference.png"
    Image.new("RGB", (16, 16), "#0a1630").save(image_path)
    capsule = teach_visual_style_from_reference(image_path, capsule_id="test:style")
    original = route_beast_runtime_request(
        BeastRuntimeRequest(
            question="Draw whether restarting Ari-api could destabilize Bex-core.",
            mode="draw",
            now="2026-08-05T12:00:00+00:00",
        ),
        _context(),
    )

    styled_svg, receipt = apply_visual_style_to_svg(original["svg"], capsule)

    assert receipt["verified"] is True
    assert receipt["semantic_digest"] == original["semantic_digest"]
    assert "data-style-capsule-digest" in styled_svg
    assert "Ari-api" in styled_svg
    assert "Bex-core" in styled_svg


def test_runtime_draw_can_use_taught_style_capsule(tmp_path) -> None:
    image_path = tmp_path / "reference.png"
    Image.new("RGB", (24, 24), "#301020").save(image_path)
    capsule = teach_visual_style_from_reference(image_path, capsule_id="test:style")
    response = route_beast_runtime_request(
        BeastRuntimeRequest(
            question="Draw whether restarting Ari-api could destabilize Bex-core.",
            mode="draw",
            now="2026-08-05T12:00:00+00:00",
        ),
        _context(asdict(capsule)),
    )

    assert response["action"] == "answer"
    assert response["visual_present"] is True
    assert response["runtime_receipt"]["visual_style_receipt"]["verified"] is True
    assert response["runtime_receipt"]["visual_style_capsule_digest"] == capsule.capsule_digest
    assert "data-style-capsule-digest" in response["svg"]
