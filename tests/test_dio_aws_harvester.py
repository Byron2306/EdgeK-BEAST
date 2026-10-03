from __future__ import annotations

from pathlib import Path

from scripts import harvest_dio_aws_tee_attestation as aws_harvester


def test_aws_harvester_admits_digest_bound_fake_nitro_document(monkeypatch, tmp_path: Path) -> None:
    raw_doc = tmp_path / "nitro-attestation.cbor"
    raw_doc.write_bytes(b"\xd2\x84fake-cose-sign1-for-serializer-test")

    monkeypatch.setattr(
        aws_harvester,
        "_aws_json",
        lambda args: {"Account": "123456789012", "Arn": "arn:aws:iam::123456789012:user/test"}
        if args[:2] == ["sts", "get-caller-identity"]
        else None,
    )
    monkeypatch.setattr(aws_harvester, "_aws_value", lambda args: "af-south-1")
    monkeypatch.setattr(
        aws_harvester,
        "_ec2_instances",
        lambda region: (
            [
                {
                    "InstanceId": "i-0123456789abcdef0",
                    "ImageId": "ami-test",
                    "InstanceType": "m7i.large",
                    "State": {"Name": "running"},
                    "TpmSupport": "v2.0",
                    "EnclaveOptions": {"Enabled": False},
                    "LaunchTime": "2026-08-04T19:00:00+00:00",
                }
            ],
            "",
        ),
    )

    result = aws_harvester.harvest(
        region="af-south-1",
        instance_id="",
        out=tmp_path / "out",
        node_id="dio:aws:tee-governance-01",
        role=aws_harvester.DIOWitnessRole.GOVERNANCE,
        key_path=tmp_path / "aws.ed25519.pem",
        challenge_nonce="dio-aws-test-nonce",
        governance_epoch="dai-phase2.1-aws-cloud-witness",
        raw_attestation_document_file=raw_doc,
    )

    assert result["green"] is True
    assert result["admission_report"]["admitted"] is True
    assert result["evidence"]["provider"] == "aws"
    assert result["evidence"]["tee_type"] == "aws_nitro_tpm"
    assert result["evidence"]["raw_attestation_digest"].startswith("sha256:")
    assert result["production_authority_allowed"] is False


def test_aws_harvester_redacts_aws_identity_text() -> None:
    text = (
        "User: arn:aws:iam::123456789012:user/Seraph-Metatron is not authorized "
        "for account 123456789012 with key AKIAABCDEFGHIJKLMNOP"
    )

    redacted = aws_harvester._sanitize_aws_text(text)

    assert "123456789012" not in redacted
    assert "Seraph-Metatron" not in redacted
    assert "AKIAABCDEFGHIJKLMNOP" not in redacted


def test_aws_harvester_missing_raw_document_is_challenge_bound(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        aws_harvester,
        "_aws_json",
        lambda args: {"Account": "123456789012", "Arn": "arn:aws:iam::123456789012:user/test"}
        if args[:2] == ["sts", "get-caller-identity"]
        else None,
    )
    monkeypatch.setattr(aws_harvester, "_aws_value", lambda args: "af-south-1")
    monkeypatch.setattr(
        aws_harvester,
        "_ec2_instances",
        lambda region: (
            [
                {
                    "InstanceId": "i-0123456789abcdef0",
                    "ImageId": "ami-test",
                    "InstanceType": "t3.micro",
                    "State": {"Name": "running"},
                    "TpmSupport": "v2.0",
                    "EnclaveOptions": {"Enabled": False},
                    "LaunchTime": "2026-08-04T19:00:00+00:00",
                }
            ],
            "",
        ),
    )

    first = aws_harvester.harvest(
        region="af-south-1",
        instance_id="",
        out=tmp_path / "first",
        node_id="dio:aws:tee-governance-01",
        role=aws_harvester.DIOWitnessRole.GOVERNANCE,
        key_path=tmp_path / "aws.ed25519.pem",
        challenge_nonce="first-challenge",
        governance_epoch="dai-phase2.1-aws-cloud-witness",
        raw_attestation_document_file=None,
    )
    second = aws_harvester.harvest(
        region="af-south-1",
        instance_id="",
        out=tmp_path / "second",
        node_id="dio:aws:tee-governance-01",
        role=aws_harvester.DIOWitnessRole.GOVERNANCE,
        key_path=tmp_path / "aws.ed25519.pem",
        challenge_nonce="second-challenge",
        governance_epoch="dai-phase2.1-aws-cloud-witness",
        raw_attestation_document_file=None,
    )

    assert first["green"] is False
    assert second["green"] is False
    assert first["blocked_reason"] == "aws_raw_nitro_attestation_document_required"
    assert first["details"]["challenge_nonce_digest"].startswith("sha256:")
    assert first["details"]["challenge_nonce_digest"] != second["details"]["challenge_nonce_digest"]
    assert first["harvest_digest"] != second["harvest_digest"]


def test_aws_harvester_uses_full_nitro_verification_digest_when_enabled(monkeypatch, tmp_path: Path) -> None:
    raw_doc = tmp_path / "nitro-attestation.cbor"
    raw_doc.write_bytes(b"\xd2\x84fake-cose-sign1-for-verifier-routing-test")
    verification_digest = "sha256:" + "9" * 64

    monkeypatch.setattr(
        aws_harvester,
        "_aws_json",
        lambda args: {"Account": "123456789012", "Arn": "arn:aws:iam::123456789012:user/test"}
        if args[:2] == ["sts", "get-caller-identity"]
        else None,
    )
    monkeypatch.setattr(aws_harvester, "_aws_value", lambda args: "af-south-1")
    monkeypatch.setattr(
        aws_harvester,
        "_ec2_instances",
        lambda region: (
            [
                {
                    "InstanceId": "i-0123456789abcdef0",
                    "ImageId": "ami-test",
                    "InstanceType": "c5a.xlarge",
                    "State": {"Name": "running"},
                    "TpmSupport": "v2.0",
                    "EnclaveOptions": {"Enabled": True},
                    "LaunchTime": "2026-08-04T19:00:00+00:00",
                }
            ],
            "",
        ),
    )

    from scripts import verify_dio_aws_nitro_attestation_document as verifier

    monkeypatch.setattr(
        verifier,
        "verify_document",
        lambda **kwargs: {
            "passed": True,
            "red_gates": (),
            "verification_digest": verification_digest,
            "document": str(kwargs["document_path"]),
        },
    )

    result = aws_harvester.harvest(
        region="af-south-1",
        instance_id="",
        out=tmp_path / "out",
        node_id="dio:aws:tee-governance-01",
        role=aws_harvester.DIOWitnessRole.GOVERNANCE,
        key_path=tmp_path / "aws.ed25519.pem",
        challenge_nonce="aa" * 32,
        governance_epoch="dai-phase2.1-aws-cloud-witness",
        raw_attestation_document_file=raw_doc,
        verify_nitro_document=True,
    )

    assert result["green"] is True
    assert result["evidence"]["service_verification_digest"] == verification_digest
    assert result["nitro_document_verification"]["verification_digest"] == verification_digest
