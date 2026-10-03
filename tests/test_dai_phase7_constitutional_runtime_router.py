from __future__ import annotations

from app.kernel.compute.deterministic_intelligence import sha256_digest
from app.kernel.dai.capability_ledger import CapabilityCrystal, CapabilityLedger, LEDGER_VERSION
from app.kernel.dai.constitutional_runtime_router import (
    BeastRuntimeContext,
    BeastRuntimeRequest,
    route_beast_runtime_request,
)


def _context() -> BeastRuntimeContext:
    ledger = CapabilityLedger(
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
    )
    return BeastRuntimeContext(
        ledger=ledger,
        phase6_4_constitutional_receipt={"green": True, "receipt_digest": sha256_digest("phase6.4")},
        phase6_5_formal_receipt={"green": True, "receipt_digest": sha256_digest("phase6.5")},
    )


def test_runtime_speak_answers_from_admitted_crystals_without_visual_payload() -> None:
    response = route_beast_runtime_request(
        BeastRuntimeRequest(
            question="Could restarting Ari-api destabilize Bex-core?",
            mode="speak",
            now="2026-08-05T12:00:00+00:00",
        ),
        _context(),
    )

    assert response["action"] == "answer"
    assert response["ordinary_answer_allowed"] is True
    assert response["visual_present"] is False
    assert response["svg"] == ""
    assert "Answer:" in response["answer_text"]
    assert "Ari-api" in response["answer_text"]
    assert response["provider_calls_used"] == 0
    assert response["runtime_receipt"]["hybrid_signature_verification_receipt"]["verified"] is True


def test_runtime_draw_returns_svg_from_same_semantic_graph() -> None:
    response = route_beast_runtime_request(
        BeastRuntimeRequest(
            question="Draw whether restarting Ari-api could destabilize Bex-core.",
            mode="draw",
            now="2026-08-05T12:00:00+00:00",
        ),
        _context(),
    )

    assert response["action"] == "answer"
    assert response["visual_present"] is True
    assert response["svg"].startswith("<svg")
    assert response["semantic_digest"] in response["svg"]
    assert "Ari-api" in response["svg"]
    assert "Bex-core" in response["svg"]
    assert "visual_generated_from_text_answer" in response["runtime_receipt"]["claim_boundary"] or response["runtime_receipt"]["green"] is True


def test_runtime_semantic_digest_is_stable_across_time_for_same_meaning() -> None:
    first = route_beast_runtime_request(
        BeastRuntimeRequest(
            question="Could restarting Ari-api destabilize Bex-core?",
            mode="speak",
            now="2026-08-05T12:00:00+00:00",
        ),
        _context(),
    )
    second = route_beast_runtime_request(
        BeastRuntimeRequest(
            question="Could restarting Ari-api destabilize Bex-core?",
            mode="speak",
            now="2026-08-05T12:05:00+00:00",
        ),
        _context(),
    )

    assert first["semantic_digest"] == second["semantic_digest"]
    assert first["answer_text"] == second["answer_text"]


def test_runtime_refuses_outside_current_crystal_family_with_lawful_reentry() -> None:
    response = route_beast_runtime_request(
        BeastRuntimeRequest(
            question="Can BEAST write a poem about the moon?",
            mode="speak",
            now="2026-08-05T12:00:00+00:00",
        ),
        _context(),
    )

    assert response["action"] == "refuse"
    assert response["ordinary_answer_allowed"] is False
    assert response["runtime_receipt"]["lawful_reentry_receipt"]["failed_criterion"] == "request_outside_admitted_runtime_family_or_missing_source_target"
    assert "Refusal:" in response["answer_text"]
    assert response["provider_calls_used"] == 0
