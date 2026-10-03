from __future__ import annotations

from pathlib import Path

import pytest

from scripts.verify_dio_aws_nitro_attestation_document import _decode_cbor, verify_document


ROOT = Path(__file__).resolve().parents[1]
LIVE_DOC = (
    ROOT
    / "evidence/dai-diode/phase2.1-cloud-witness/aws-af-south-1-live-008/nitro-tpm-attestation-document.cbor"
)
LIVE_USER_DATA = ROOT / "evidence/dai-diode/phase2.1-cloud-witness/aws-af-south-1-live-008/user-data.json"
AWS_ROOT_ZIP = ROOT / "evidence/dai-diode/phase2.1-cloud-witness/aws-root/AWS_NitroEnclaves_Root-G1.zip"
LIVE_NONCE_HEX = "f009eb759d468a426a8365846840e72c9104b9781a558fca70f7c44c4ab78ff8"


def _requires_live_aws_fixture() -> None:
    if not (LIVE_DOC.exists() and LIVE_USER_DATA.exists() and AWS_ROOT_ZIP.exists()):
        pytest.skip("live AWS Nitro attestation fixture not present")


def test_cbor_definite_map_decodes_key_then_value() -> None:
    assert _decode_cbor(bytes.fromhex("a1013822")) == {1: -35}


def test_live_aws_nitro_document_verifies_cose_x509_nonce_user_data_and_instance() -> None:
    _requires_live_aws_fixture()

    result = verify_document(
        document_path=LIVE_DOC,
        root_zip=AWS_ROOT_ZIP,
        expected_nonce_hex=LIVE_NONCE_HEX,
        expected_user_data_file=LIVE_USER_DATA,
        expected_instance_id="i-0b71289635c195cd0",
        expected_module_id="i-0b71289635c195cd0-tpm0000000000000000",
        evaluation_time="2026-08-04T21:20:00+00:00",
    )

    assert result["passed"] is True
    assert result["red_gates"] == ()
    assert result["gates"]["certificate_chain_verified"] is True
    assert result["gates"]["cose_signature_verified"] is True
    assert result["gates"]["nonce_matches_expected"] is True
    assert result["details"]["raw_document_digest"] == (
        "sha256:9059b30540b37e2b75e5f9a516bfeab2f7ef65cc6c931ec51919dacf0f954066"
    )


def test_live_aws_nitro_document_rejects_wrong_nonce() -> None:
    _requires_live_aws_fixture()

    result = verify_document(
        document_path=LIVE_DOC,
        root_zip=AWS_ROOT_ZIP,
        expected_nonce_hex="00" * 32,
        expected_user_data_file=LIVE_USER_DATA,
        expected_instance_id="i-0b71289635c195cd0",
        evaluation_time="2026-08-04T21:20:00+00:00",
    )

    assert result["passed"] is False
    assert "nonce_matches_expected" in result["red_gates"]


def test_live_aws_nitro_document_rejects_wrong_pcr_policy() -> None:
    _requires_live_aws_fixture()

    result = verify_document(
        document_path=LIVE_DOC,
        root_zip=AWS_ROOT_ZIP,
        expected_nonce_hex=LIVE_NONCE_HEX,
        expected_user_data_file=LIVE_USER_DATA,
        expected_instance_id="i-0b71289635c195cd0",
        expected_pcr=("0=" + "00" * 48,),
        evaluation_time="2026-08-04T21:20:00+00:00",
    )

    assert result["passed"] is False
    assert "pcr_policy_matches" in result["red_gates"]


def test_live_aws_nitro_document_rejects_signature_tampering(tmp_path: Path) -> None:
    _requires_live_aws_fixture()
    tampered = tmp_path / "tampered.cbor"
    raw = bytearray(LIVE_DOC.read_bytes())
    raw[-1] ^= 0x01
    tampered.write_bytes(raw)

    result = verify_document(
        document_path=tampered,
        root_zip=AWS_ROOT_ZIP,
        expected_nonce_hex=LIVE_NONCE_HEX,
        expected_user_data_file=LIVE_USER_DATA,
        expected_instance_id="i-0b71289635c195cd0",
        evaluation_time="2026-08-04T21:20:00+00:00",
    )

    assert result["passed"] is False
    assert "cose_signature_verified" in result["red_gates"]
