from __future__ import annotations

import copy
import os
import shutil
import zipfile
from pathlib import Path

import pytest

import dai_evidence as evidence
import dai_publication as publication
import dai_publication_core as core


DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
DIGEST_D = "sha256:" + "d" * 64
DIGEST_E = "sha256:" + "e" * 64
DIGEST_F = "sha256:" + "f" * 64


def make_operator_key(candidate: Path, tmp_path: Path, name: str) -> tuple[Path, str, str]:
    private = tmp_path / f"{name}.private.pem"
    public = candidate / "keys" / f"{name}.public.pem"
    public.parent.mkdir(parents=True, exist_ok=True)
    report = core.generate_key(private, public)
    relative = public.relative_to(candidate).as_posix()
    return private, relative, report["public_key_fingerprint"]


def write_signed(
    candidate: Path,
    path: Path,
    document: dict,
    private: Path,
    public_relative: str,
) -> dict:
    core.write_canonical_json(path, document)
    evidence.sign_document(
        path,
        private_key_path=private,
        public_key_path=public_relative,
    )
    return core.load_json_file(path)


def test_signed_document_detects_post_signature_tampering(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    private, public_relative, _ = make_operator_key(candidate, tmp_path, "operator-a")
    path = candidate / "reports" / "reproductions" / "operator-a.json"
    document = {
        "schema": "dai.independent-reproduction.v1",
        "operator_id": "operator-a",
        "operator_control_domain": "org-a",
        "subject_core_capsule_sha256": DIGEST_A,
        "environment_digest": DIGEST_B,
        "verifier_digest": DIGEST_C,
        "semantic_result_digest": DIGEST_D,
        "mutation_report_digest": DIGEST_E,
        "private_help_received": False,
        "result": "pass",
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }
    write_signed(candidate, path, document, private, public_relative)
    verified = evidence.verify_signed_document(
        candidate,
        path,
        expected_schema="dai.independent-reproduction.v1",
    )
    assert verified["result"] == "pass"

    tampered = core.load_json_file(path)
    tampered["result"] = "fail"
    core.write_canonical_json(path, tampered)
    with pytest.raises(evidence.EvidenceError, match="invalid independent signature"):
        evidence.verify_signed_document(
            candidate,
            path,
            expected_schema="dai.independent-reproduction.v1",
        )


def build_core_capsule(tmp_path: Path, candidate: Path) -> tuple[str, str]:
    source = tmp_path / "core-source"
    (source / "evidence").mkdir(parents=True)
    (source / "evidence" / "bounded-result.json").write_text(
        '{"decision":"answer","production_authority_allowed":false,"execution_authority_allowed":false}\n',
        encoding="utf-8",
    )
    private = tmp_path / "core-publisher.private.pem"
    public = tmp_path / "core-publisher.public.pem"
    key_report = core.generate_key(private, public)
    previous = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = "1785888000"
    try:
        build = core.build_release(
            source,
            release_id="DAI-Core-Test",
            private_key_path=private,
            output=tmp_path / "core-dist",
        )
    finally:
        if previous is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = previous
    core_dir = candidate / "core"
    core_dir.mkdir(parents=True, exist_ok=True)
    capsule = core_dir / "CORE_CAPSULE.zip"
    shutil.copy2(build["release_zip"], capsule)
    trust = {
        "schema": "dai.core-capsule-trust.v1",
        "core_release_id": "DAI-Core-Test",
        "core_capsule_sha256": core.sha256_file(capsule),
        "publisher_fingerprint": key_report["public_key_fingerprint"],
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }
    core.write_canonical_json(core_dir / "CORE_CAPSULE.TRUST.json", trust)
    return trust["core_capsule_sha256"], trust["publisher_fingerprint"]


def test_two_stage_core_capsule_verification(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    subject, _ = build_core_capsule(tmp_path, candidate)
    report = evidence.verify_core_capsule(candidate)
    assert report["core_capsule_sha256"] == subject
    assert report["verification"]["verified"] is True


def test_independent_reproductions_require_distinct_control_domains(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    subject = DIGEST_A
    for index in range(2):
        private, public_relative, _ = make_operator_key(candidate, tmp_path, f"operator-{index}")
        document = {
            "schema": "dai.independent-reproduction.v1",
            "operator_id": f"operator-{index}",
            "operator_control_domain": "shared-org",
            "subject_core_capsule_sha256": subject,
            "environment_digest": core.sha256_bytes(f"environment-{index}".encode()),
            "verifier_digest": DIGEST_B,
            "semantic_result_digest": DIGEST_C,
            "mutation_report_digest": DIGEST_D,
            "private_help_received": False,
            "result": "pass",
            "production_authority_allowed": False,
            "execution_authority_allowed": False,
        }
        write_signed(
            candidate,
            candidate / "reports" / "reproductions" / f"operator-{index}.json",
            document,
            private,
            public_relative,
        )
    with pytest.raises(evidence.EvidenceError, match="control domains"):
        evidence.validate_reproductions(candidate, subject)


def test_network_witness_requires_zero_observed_egress(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    private, public_relative, _ = make_operator_key(candidate, tmp_path, "observer")
    document = {
        "schema": "dai.network-denial-witness.v1",
        "observer_operator_id": "observer",
        "subject_core_capsule_sha256": DIGEST_A,
        "result": "pass",
        "network_policy": {
            "default_egress": "deny",
            "dns_allowed": False,
            "loopback_allowed": True,
            "exceptions": [],
        },
        "observation_sources": [
            "network_namespace_or_firewall_rules",
            "socket_or_ebpf_trace",
            "packet_capture_summary",
            "process_tree",
            "dns_attempt_log",
        ],
        "provider_calls_observed": 0,
        "observed_outbound_connections": [],
        "denied_connection_attempts": [],
        "started_at": "2026-08-05T00:00:00Z",
        "ended_at": "2026-08-05T00:10:00Z",
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }
    path = candidate / "reports" / "NETWORK_DENIAL_WITNESS.json"
    write_signed(candidate, path, document, private, public_relative)
    assert evidence.validate_network_witness(candidate, DIGEST_A)["verified"] is True

    changed = core.load_json_file(path)
    changed["observed_outbound_connections"] = ["198.51.100.8:443"]
    core.write_canonical_json(path, changed)
    evidence.sign_document(path, private_key_path=private, public_key_path=public_relative)
    with pytest.raises(evidence.EvidenceError, match="observed outbound"):
        evidence.validate_network_witness(candidate, DIGEST_A)


def quorum_context(subject: str) -> dict:
    return {
        "schema": "dai.commons-quorum-context.v1",
        "subject_core_capsule_sha256": subject,
        "evaluation_time": "2026-08-05T00:05:00Z",
        "expected_binding": {
            "proposal_digest": DIGEST_A,
            "capability_digest": DIGEST_B,
            "evidence_root": DIGEST_C,
            "world_state_hash": DIGEST_D,
            "governance_epoch": "epoch-7",
            "challenge_nonce": "challenge-nonce-0000000000000001",
            "verifier_digest": DIGEST_E,
        },
        "policy": {
            "minimum_approvals": 3,
            "minimum_distinct_operators": 3,
            "minimum_distinct_keys": 3,
            "minimum_distinct_providers": 3,
            "minimum_distinct_control_domains": 3,
            "required_approve_roles": ["semantic", "adversarial", "governance"],
        },
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }


def add_witness(
    candidate: Path,
    tmp_path: Path,
    *,
    index: int,
    role: str,
    provider: str,
    world_state_hash: str = DIGEST_D,
) -> Path:
    name = f"operator-{index}"
    private, public_relative, _ = make_operator_key(candidate, tmp_path, name)
    raw = candidate / "evidence" / "raw" / f"{name}.attestation.json"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(f'{{"operator":"{name}","provider":"{provider}"}}\n', encoding="utf-8")
    packet = {
        "schema": "dai.commons-witness-packet.v1",
        "operator_id": name,
        "operator_control_domain": f"control-{index}",
        "infrastructure_provider": provider,
        "runtime_platform": f"runtime-{index}",
        "witness_role": role,
        "subject_core_capsule_sha256": DIGEST_A,
        "proposal_digest": DIGEST_A,
        "capability_digest": DIGEST_B,
        "evidence_root": DIGEST_C,
        "world_state_hash": world_state_hash,
        "governance_epoch": "epoch-7",
        "challenge_nonce": "challenge-nonce-0000000000000001",
        "verifier_digest": DIGEST_E,
        "raw_attestation_evidence": [
            {
                "path": raw.relative_to(candidate).as_posix(),
                "sha256": core.sha256_file(raw),
            }
        ],
        "issued_at": "2026-08-05T00:00:00Z",
        "expires_at": "2026-08-05T00:10:00Z",
        "decision": "approve",
        "reason_codes": ["verified"],
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }
    path = candidate / "evidence" / "quorum" / f"{name}.witness.json"
    write_signed(candidate, path, packet, private, public_relative)
    return path


def test_quorum_validates_all_binding_fields_and_raw_evidence(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    context_path = candidate / "evidence" / "quorum" / "QUORUM_CONTEXT.json"
    core.write_canonical_json(context_path, quorum_context(DIGEST_A))
    add_witness(candidate, tmp_path, index=0, role="semantic", provider="provider-a")
    add_witness(candidate, tmp_path, index=1, role="adversarial", provider="provider-b")
    add_witness(candidate, tmp_path, index=2, role="governance", provider="provider-c")
    report = evidence.validate_quorum(candidate, DIGEST_A)
    assert report["verified"] is True
    assert report["approve_count"] == 3
    assert report["distinct_control_domain_count"] == 3
    assert report["raw_attestation_evidence_count"] == 3


def test_quorum_rejects_validly_signed_equivocation(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    context_path = candidate / "evidence" / "quorum" / "QUORUM_CONTEXT.json"
    core.write_canonical_json(context_path, quorum_context(DIGEST_A))
    add_witness(candidate, tmp_path, index=0, role="semantic", provider="provider-a")
    add_witness(candidate, tmp_path, index=1, role="adversarial", provider="provider-b")
    add_witness(
        candidate,
        tmp_path,
        index=2,
        role="governance",
        provider="provider-c",
        world_state_hash=DIGEST_F,
    )
    with pytest.raises(evidence.EvidenceError, match="world_state_hash"):
        evidence.validate_quorum(candidate, DIGEST_A)


def test_publication_verification_requires_exact_outer_digest_and_no_comment(tmp_path: Path) -> None:
    release, fingerprint = _build_publication_release(tmp_path)
    digest = core.sha256_file(release)
    report = evidence.verify_publication_release(
        release,
        expected_zip_sha256=digest,
        trusted_fingerprint=fingerprint,
    )
    assert report["verified"] is True

    with zipfile.ZipFile(release, "a") as archive:
        archive.comment = b"unlisted metadata"
    mutated_digest = core.sha256_file(release)
    with pytest.raises(evidence.EvidenceError, match="comment"):
        evidence.verify_publication_release(
            release,
            expected_zip_sha256=mutated_digest,
            trusted_fingerprint=fingerprint,
        )


def _build_publication_release(tmp_path: Path) -> tuple[Path, str]:
    candidate = tmp_path / "publication-source"
    candidate.mkdir(parents=True)
    (candidate / "README.txt").write_text("publication envelope\n", encoding="utf-8")
    private = tmp_path / "publication.private.pem"
    public = tmp_path / "publication.public.pem"
    key = core.generate_key(private, public)
    previous = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = "1785888000"
    try:
        report = core.build_release(
            candidate,
            release_id="DAI-Publication-Test",
            private_key_path=private,
            output=tmp_path / "publication-dist",
        )
    finally:
        if previous is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = previous
    return Path(report["release_zip"]), key["public_key_fingerprint"]
