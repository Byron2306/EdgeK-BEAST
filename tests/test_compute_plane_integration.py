from pathlib import Path

import pytest

from app.kernel.compute.compute_plane import ComputePlane, ScientificPromotionGate


def test_production_plane_constructs_every_enforcement_component(tmp_path: Path):
    plane = ComputePlane(root=tmp_path)
    plane.assert_production_composition()
    report = plane.reachability_report()

    assert set(plane.REQUIRED_COMPONENTS) == set(report["components"])
    assert report["read_only"] is True
    assert plane.streaming_interceptor.governor is plane.governor
    assert plane.physical_interpreter.applicability_gate is plane.physical_applicability
    assert plane.physical_interpreter.evidence is plane.evidence_graph
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
