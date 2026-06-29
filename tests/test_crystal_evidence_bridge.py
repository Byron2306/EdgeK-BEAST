import json
from pathlib import Path

from app.kernel.compute.crystal_evidence_bridge import CrystalEvidenceBridge
from app.kernel.compute.crystallized_compute_proof import CrystallizedOpusNIMGatewayMegaGauntlet
from app.kernel.compute.unified_evidence_packet import UnifiedEvidencePacketBuilder
from app.kernel.security.residue_seal import ResidueSeal
from app.kernel.storage.memory_hull import MemoryHull


def test_crystal_evidence_bridge_publishes_envelopes_chronicle_and_hull(tmp_path):
    packet = CrystallizedOpusNIMGatewayMegaGauntlet(tmp_path / "run", local_only=True).run()[
        "unified_evidence_packet"
    ]
    seal = ResidueSeal(tmp_path / "keys")
    hull = MemoryHull(tmp_path / "vault", seal=seal)
    bridge = CrystalEvidenceBridge(tmp_path / "bridge", memory_hull=hull, seal=seal)

    receipt = bridge.publish(packet)

    assert receipt["beast_object_type"] == "crystal_evidence_bridge_receipt"
    assert receipt["packet_hash"] == packet["packet_hash"]
    assert receipt["envelope_count"] == 2
    assert all(evidence_id.startswith("ev_") for evidence_id in receipt["evidence_ids"])
    assert all(item["written"] is True for item in receipt["chronicle_receipts"])
    assert receipt["memory_hull"]["verified"] is True
    assert receipt["metrics"]["runtime_tokens_avoided"] == packet["metrics"]["runtime_tokens_avoided"]
    assert receipt["metrics"]["unique_crystals"] >= 1
    assert receipt["metrics"]["cloud_calls_during_completion"] == 0
    assert receipt["residue_seal"]["purpose"] == "crystal_evidence_bridge_receipt"

    sidecar_path = Path(receipt["memory_hull"]["sidecar_path"])
    assert hull.verify_sidecar(sidecar_path)["verified"] is True
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    evidence = sidecar["payload"]["evidence"]
    assert evidence["packet_hash"] == packet["packet_hash"]
    assert evidence["runtime"]["cloud_used"] is False
    assert evidence["negative_case_count"] == 6

    for chronicle in receipt["chronicle_receipts"]:
        assert Path(chronicle["path"]).exists()


def test_unified_packet_builder_can_publish_to_beast_evidence_plane(tmp_path):
    packet = CrystallizedOpusNIMGatewayMegaGauntlet(tmp_path / "run", local_only=True).run()[
        "unified_evidence_packet"
    ]

    receipt = UnifiedEvidencePacketBuilder.publish_to_beast_evidence_plane(packet, tmp_path / "plane")

    assert receipt["packet_hash"] == packet["packet_hash"]
    assert receipt["memory_hull"]["verified"] is True
    assert (tmp_path / "plane" / "crystal_evidence_bridge").exists()
