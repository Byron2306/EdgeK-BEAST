import json
from pathlib import Path

from app.kernel.compute.deterministic_intelligence import canonical_json
from app.kernel.dai.phase6_sophia_integritas_lineage import (
    build_sophia_integritas_lineage_certificate,
    sign_sophia_export,
    verify_lineage_certificate_against_key_policy,
    verify_lineage_certificate,
    verify_sophia_signature,
)


ROOT = Path(__file__).resolve().parents[1]
SOPHIA = Path("/home/byron/Integritas-Mechanicus/evidence/sophia_writing_desk_phase3_export_semantic_latest.json")
PHASE1 = ROOT / "evidence/dai-diode/phase1-synthesis-001"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _certificate():
    packet = _read(PHASE1 / "dai_phase1_packet.json")
    signature = sign_sophia_export(SOPHIA)
    return build_sophia_integritas_lineage_certificate(
        signed_sophia=signature,
        phase1_packet=packet,
        phase1_validation=_read(PHASE1 / "dai_phase1_validation_receipt.json"),
        evidence_resolution=_read(PHASE1 / "dai_evidence_resolution_receipt.json"),
        seraph_assessment_packet=packet["seraph_assessment"],
        commons_admission=_read(PHASE1 / "dai_commons_admission_receipt.json"),
        quorum_decision=_read(PHASE1 / "dai_quorum_decision_receipt.json"),
        promotion=_read(PHASE1 / "dai_capability_promotion_receipt.json"),
        neural_mesh=_read(PHASE1 / "dai_neural_mesh_activation_receipt.json"),
        arda_execution=_read(PHASE1 / "dai_arda_execution_receipt.json"),
        phase6_1=_read(ROOT / "evidence/dai-diode/phase6-sophia-transfer-arena/dai_phase6_sophia_transfer_arena_receipt.json"),
        phase6_2_ledger=_read(ROOT / "evidence/dai-diode/phase6-truth-arena/dai_capability_ledger.json"),
        phase6_2_truth=_read(ROOT / "evidence/dai-diode/phase6-truth-arena/dai_phase6_truth_arena_receipt.json"),
    )


def test_signed_sophia_export_enters_unified_beast_lineage():
    certificate = _certificate()
    verification = verify_lineage_certificate(certificate)

    assert certificate["green"] is True
    assert certificate["red_gates"] == ()
    assert verification["verified"] is True
    assert certificate["signed_sophia_export_digest"] == "sha256:5fa74d666de74bbd1de9b41d5652cd6f16ee39d8985ab4de3ca6ef758fa6d3a2"
    assert certificate["phase6_2_truth_receipt_digest"] == "sha256:6b311269f33e381edf3b7536cddb4132506740624d7ca1fbe49c5c4df5221f8a"
    assert certificate["provider_calls_used"] == 0
    assert certificate["production_authority_allowed"] is False
    assert certificate["execution_authority_allowed"] is False


def test_sophia_lineage_signature_rejects_tampered_digest():
    signature = json.loads(canonical_json(sign_sophia_export(SOPHIA)))
    signature["export_digest"] = "sha256:" + "0" * 64

    assert verify_sophia_signature(signature) is False


def test_lineage_certificate_rejects_tampered_certificate_digest():
    certificate = dict(_certificate())
    certificate["signed_sophia_export_digest"] = "sha256:" + "1" * 64

    verification = verify_lineage_certificate(certificate)

    assert verification["verified"] is False
    assert "certificate_digest_recomputes" in verification["red_gates"]


def test_lineage_certificate_matches_project_pinned_key_policy():
    certificate = _read(ROOT / "evidence/dai-diode/phase6-sophia-integritas-lineage/sophia_integritas_unified_lineage_certificate.json")
    policy = _read(ROOT / "release-keys/sophia_integritas_lineage_key_policy.json")

    verification = verify_lineage_certificate_against_key_policy(certificate, policy)

    assert verification["verified"] is True
    assert verification["red_gates"] == ()
    assert verification["public_key_fingerprint"] == "sha256:bcfad7dbb07bff2858b7fc2172a5f40e1684012fe9764897e8d77a7a010028cc"


def test_project_pinned_key_policy_rejects_wrong_public_key():
    certificate = _read(ROOT / "evidence/dai-diode/phase6-sophia-integritas-lineage/sophia_integritas_unified_lineage_certificate.json")
    policy = dict(_read(ROOT / "release-keys/sophia_integritas_lineage_key_policy.json"))
    policy["public_key_fingerprint"] = "sha256:" + "2" * 64

    verification = verify_lineage_certificate_against_key_policy(certificate, policy)

    assert verification["verified"] is False
    assert "policy_digest_recomputes" in verification["red_gates"]
    assert "policy_key_fingerprint_matches_certificate" in verification["red_gates"]
