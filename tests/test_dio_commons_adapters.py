from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.kernel.dai.dio_commons_adapters import (
    DIO_COMMONS_ADAPTER_VERSION,
    DIOCommonsAdapterKind,
    DIOCommonsSpaceAdapterReport,
    adapt_arda_receipt_to_commons_space,
    adapt_cloud_harvest_to_commons_space,
    adapt_github_actions_verification_to_commons_space,
)


ROOT = Path(__file__).resolve().parents[1]
GCP_HARVEST = ROOT / "evidence/dai-diode/phase2.1-cloud-witness/gcp-africa-south1-witness-02-repair-20260804T190327Z/harvest/dio_gcp_tee_attestation_harvest.json"
AWS_HARVEST = ROOT / "evidence/dai-diode/phase2.1-cloud-witness/aws-af-south-1-live-008/dio_aws_tee_attestation_harvest.json"
GITHUB_PACKET = ROOT / "evidence/dai-diode/phase2.1-github-witness/run-30937227770/dio_github_actions_witness_packet.json"
GITHUB_VERIFICATION = ROOT / "evidence/dai-diode/phase2.1-github-witness/run-30937227770/dio_github_actions_witness_verification.json"
ARDA_RECEIPT = ROOT / "evidence/dai-diode/phase1-synthesis-001/dai_arda_execution_receipt.json"


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_gcp_harvest_adapts_as_non_persistent_provider_hardware_space():
    manifest, report = adapt_cloud_harvest_to_commons_space(_json(GCP_HARVEST), adapter_kind=DIOCommonsAdapterKind.GCP_CONFIDENTIAL_SPACE)

    assert report.adapted is True
    assert report.red_gates == ()
    assert report.attestation_class == "provider_hardware_attestation"
    assert report.persistent_service is False
    assert report.online_protocol_ready is False
    assert report.identity_signature_present is False
    assert manifest.persistent_service is False
    assert manifest.manifest_digest == report.capability_manifest_digest


def test_aws_harvest_adapts_as_non_persistent_provider_hardware_space():
    manifest, report = adapt_cloud_harvest_to_commons_space(_json(AWS_HARVEST), adapter_kind=DIOCommonsAdapterKind.AWS_NITRO_TPM)

    assert report.adapted is True
    assert report.infrastructure_provider == "aws"
    assert report.attestation_class == "provider_hardware_attestation"
    assert report.persistent_service is False
    assert manifest.manifest_digest == report.capability_manifest_digest


def test_github_actions_adapts_as_ephemeral_provenance_not_online_space():
    manifest, report = adapt_github_actions_verification_to_commons_space(_json(GITHUB_PACKET), _json(GITHUB_VERIFICATION))

    assert report.adapted is True
    assert report.attestation_class == "ephemeral_build_provenance"
    assert report.persistent_service is False
    assert report.online_protocol_ready is False
    assert report.identity_signature_present is False
    assert manifest.persistent_service is False


def test_arda_adapts_as_local_physical_witness_without_online_protocol():
    manifest, report = adapt_arda_receipt_to_commons_space(_json(ARDA_RECEIPT))

    assert report.adapted is True
    assert report.attestation_class == "local_physical_witness"
    assert report.role == "physical_execution_witness"
    assert report.persistent_service is False
    assert report.execution_authority_allowed is False
    assert manifest.persistent_service is False


def test_adapter_report_rejects_persistence_inflation_without_signed_challenge_surface():
    _manifest, report = adapt_github_actions_verification_to_commons_space(_json(GITHUB_PACKET), _json(GITHUB_VERIFICATION))

    with pytest.raises(ValueError, match="online-ready Commons adapter"):
        DIOCommonsSpaceAdapterReport(
            **{
                **{
                    field: getattr(report, field)
                    for field in DIOCommonsSpaceAdapterReport.__dataclass_fields__
                    if field != "report_digest"
                },
                "persistent_service": True,
                "online_protocol_ready": True,
                "identity_signature_present": False,
                "challenge_endpoint_present": False,
            }
        )


def test_cloud_adapter_rejects_wrong_provider_kind():
    _manifest, report = adapt_cloud_harvest_to_commons_space(_json(AWS_HARVEST), adapter_kind=DIOCommonsAdapterKind.GCP_CONFIDENTIAL_SPACE)

    assert report.adapted is False
    assert "provider_matches_adapter" in report.red_gates
    assert "tee_matches_adapter" in report.red_gates
