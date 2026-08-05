from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

from app.kernel.compute.deterministic_intelligence import canonical_json, sha256_digest
from app.kernel.dai.dio_distributed_quorum import DIOProposalPacket
from scripts.run_dio_github_actions_witness import build_autonomous_packet, build_legacy_packet
from scripts.verify_dio_github_actions_witness import verify


def _github_env(monkeypatch) -> None:
    values = {
        "GITHUB_REPOSITORY": "Byron2306/EdgeK-BEAST",
        "GITHUB_REPOSITORY_ID": "123456",
        "GITHUB_REPOSITORY_OWNER": "Byron2306",
        "GITHUB_RUN_ID": "phase5-local-test",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_WORKFLOW": "DIO Remote GitHub Witness",
        "GITHUB_WORKFLOW_REF": "Byron2306/EdgeK-BEAST/.github/workflows/dio-remote-witness.yml@refs/heads/chore/wip-safety-hygiene",
        "GITHUB_WORKFLOW_SHA": "f" * 40,
        "GITHUB_JOB": "dio-github-actions-witness",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/chore/wip-safety-hygiene",
        "GITHUB_SHA": "f" * 40,
        "GITHUB_ACTOR": "byron",
        "RUNNER_OS": "Linux",
        "RUNNER_ARCH": "X64",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def _write_packet(path: Path, packet: dict) -> Path:
    path.write_text(canonical_json(packet) + "\n", encoding="utf-8")
    return path


def test_github_actions_emits_phase5_autonomous_remote_witness_envelope(tmp_path: Path, monkeypatch) -> None:
    _github_env(monkeypatch)
    packet = build_autonomous_packet(test_status="passed", test_command="pytest --noconftest dio")
    packet["envelope_digest"] = sha256_digest(packet)
    path = _write_packet(tmp_path / "packet.json", packet)

    receipt = verify(path)

    assert receipt["verified"] is True
    assert receipt["red_gates"] == ()
    assert receipt["autonomous_packet_verification"]["verified"] is True
    assert receipt["autonomous_packet_red_gates"] == ()
    assert packet["beast_object_type"] == "dio_github_actions_autonomous_witness_envelope"
    assert packet["packet"]["beast_object_type"] == "dio_autonomous_remote_witness_packet"
    assert packet["requires_github_artifact_attestation"] is True
    assert packet["requires_oidc_identity"] is True
    assert packet["maximum_authority"] == "remote_oidc_sigstore_software_witness_only"


def test_github_actions_autonomous_packet_binds_supplied_shared_proposal(tmp_path: Path, monkeypatch) -> None:
    _github_env(monkeypatch)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    proposal = DIOProposalPacket(
        beast_object_type="dio_proposition_packet",
        proposal_digest=sha256_digest({"proposal": "shared-github-quorum"}),
        capability_digest=sha256_digest({"capability": "shared-github-quorum"}),
        evidence_root=sha256_digest({"evidence": "shared-github-quorum"}),
        world_state_hash=sha256_digest({"world": "shared-github-quorum"}),
        governance_epoch="dio-phase5-shared-quorum-test",
        challenge_nonce="phase5-shared-github-" + "x" * 24,
        issued_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=30)).isoformat(),
    )
    packet = build_autonomous_packet(test_status="passed", test_command="pytest --noconftest dio", proposal=proposal)
    packet["envelope_digest"] = sha256_digest(packet)
    path = _write_packet(tmp_path / "packet.json", packet)

    receipt = verify(path)

    assert receipt["verified"] is True
    assert packet["shared_proposal_supplied"] is True
    assert packet["proposal"]["packet_digest"] == proposal.packet_digest
    assert packet["packet"]["proposal_packet_digest"] == proposal.packet_digest
    assert packet["packet"]["vote"]["proposal_digest"] == proposal.proposal_digest


def test_github_actions_autonomous_verifier_rejects_inner_packet_tamper_even_when_envelope_rehashed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _github_env(monkeypatch)
    packet = build_autonomous_packet(test_status="passed", test_command="pytest --noconftest dio")
    packet["packet"]["packet_signature"] = packet["packet"]["packet_signature"][:-4] + "AAAA"
    packet["packet"]["packet_digest"] = sha256_digest({key: value for key, value in packet["packet"].items() if key != "packet_digest"})
    packet["envelope_digest"] = sha256_digest(packet)
    path = _write_packet(tmp_path / "packet.json", packet)

    receipt = verify(path)

    assert receipt["verified"] is False
    assert "autonomous_packet_verified" in receipt["red_gates"]
    assert "packet_signature_valid" in receipt["autonomous_packet_red_gates"]


def test_github_actions_autonomous_verifier_rejects_envelope_digest_tamper(tmp_path: Path, monkeypatch) -> None:
    _github_env(monkeypatch)
    packet = build_autonomous_packet(test_status="passed", test_command="pytest --noconftest dio")
    packet["envelope_digest"] = "sha256:" + "0" * 64
    path = _write_packet(tmp_path / "packet.json", packet)

    receipt = verify(path)

    assert receipt["verified"] is False
    assert "envelope_digest_recomputes" in receipt["red_gates"]


def test_github_actions_legacy_packet_shape_still_verifies_for_phase4_adapter(tmp_path: Path, monkeypatch) -> None:
    _github_env(monkeypatch)
    packet = build_legacy_packet(test_status="passed", test_command="pytest --noconftest dio")
    packet["packet_digest"] = sha256_digest(packet)
    path = _write_packet(tmp_path / "legacy.json", packet)

    receipt = verify(path)

    assert receipt["verified"] is True
    assert receipt["beast_object_type"] == "dio_github_actions_witness_verification"
