from dataclasses import replace
from pathlib import Path

from app.kernel.dai.evidence_resolver import phase1_packet_core_digest, resolve_phase1_evidence
from tests.test_dai_phase1_contracts import _valid_packet


def test_evidence_resolver_recomputes_and_resolves_valid_packet(tmp_path):
    packet = _valid_packet(tmp_path)
    receipt = resolve_phase1_evidence(packet)

    assert receipt.resolved is True
    assert receipt.red_gates == ()
    assert receipt.component_digests["packet"] == phase1_packet_core_digest(packet)
    assert receipt.component_digests["concept_candidate"] == packet.concept_candidate.candidate_digest
    assert receipt.receipt_digest.startswith("sha256:")


def test_evidence_resolver_rejects_tampered_artifact_file(tmp_path):
    packet = _valid_packet(tmp_path)
    Path(packet.artifacts[0].artifact_path).write_text('{"tampered":true}\n', encoding="utf-8")

    receipt = resolve_phase1_evidence(packet)

    assert receipt.resolved is False
    assert "artifact_file_digests_recompute" in receipt.red_gates


def test_evidence_resolver_rejects_wrong_candidate_source_receipt(tmp_path):
    packet = _valid_packet(tmp_path)
    bad_candidate = replace(
        packet.concept_candidate,
        source_artifact_receipts=("sha256:" + "0" * 64,),
    )

    receipt = resolve_phase1_evidence(replace(packet, concept_candidate=bad_candidate))

    assert receipt.resolved is False
    assert "candidate_sources_resolve_exactly" in receipt.red_gates


def test_core_digest_excludes_attached_resolver_and_world_receipts(tmp_path):
    packet = _valid_packet(tmp_path)
    altered = replace(
        packet,
        evidence_resolution_receipts=("sha256:" + "1" * 64,),
        world_event_receipts=("sha256:" + "2" * 64,),
        commons_admission_receipts=("sha256:" + "3" * 64,),
        quorum_receipts=("sha256:" + "4" * 64,),
    )

    assert phase1_packet_core_digest(packet) == phase1_packet_core_digest(altered)
    assert packet.packet_digest != altered.packet_digest
