import json
import zipfile
from pathlib import Path

import pytest

from app.kernel.commons_privacy import CommonsPrivacyScrubber
from app.kernel.commons_space_registry import CommonsSpaceRegistry
from app.kernel.commons_spaces import MANIFEST_NAME, build_manifest, import_space, package_tiny_llama_case
from app.kernel.federated_commons import FederatedCommons


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "benchmarks/results/tiny_llama_opus_case_study_qwen25_05b"


def prepared_registry(tmp_path):
    registry = CommonsSpaceRegistry(tmp_path / "spaces")
    package_tiny_llama_case(CASE, registry.root / "tiny_llama_opus_gateway_repair")
    return registry


def tamper_zip_entry(source: Path, destination: Path, entry_name: str, replacement: bytes) -> None:
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            body = src.read(info.filename)
            if info.filename == entry_name:
                body = replacement
            dst.writestr(info.filename, body)


def test_tampered_bundle_artifact_hash_is_rejected(tmp_path):
    registry = prepared_registry(tmp_path / "source")
    exported = registry.export_bundle("tiny_llama_opus_gateway_repair")
    tampered = tmp_path / "tampered.zip"
    tamper_zip_entry(Path(exported["path"]), tampered, "README.md", b"tampered public docs\n")
    target = CommonsSpaceRegistry(tmp_path / "target")

    with pytest.raises(ValueError, match="bundle entry integrity failed"):
        target.import_untrusted_bundle(tampered, approved=True, dry_run=False)


def test_tampered_signed_envelope_after_signing_is_rejected(tmp_path):
    registry = prepared_registry(tmp_path)
    federation = FederatedCommons(registry, tmp_path / "federation")
    envelope = federation.prepare("tiny_llama_opus_gateway_repair", contributor_id="node_alpha")
    federation.allow_contributor(
        "node_alpha",
        public_key_hash=envelope["signature"]["public_key_hash"],
        approved=True,
        reason="test",
    )
    envelope["space_id"] = "tampered_space"

    with pytest.raises(ValueError, match="signature did not verify"):
        federation.ingest(envelope)


def test_non_allowlisted_import_is_rejected_and_not_adopted(tmp_path):
    registry = prepared_registry(tmp_path)
    federation = FederatedCommons(registry, tmp_path / "federation")
    envelope = federation.prepare("tiny_llama_opus_gateway_repair", contributor_id="unknown_node")

    with pytest.raises(ValueError, match="not locally allowlisted"):
        federation.ingest(envelope)
    assert registry.adoptions() == []


@pytest.mark.parametrize("name, body", [
    ("node_ed25519.pem", "-----BEGIN PRIVATE KEY-----\nnope\n-----END PRIVATE KEY-----\n"),
    ("raw_prompt.txt", "private prompt"),
    ("rollback_snapshot.json", "{}"),
    ("source_fixture.py", "print('private')"),
    ("private_test_fixture.json", "{}"),
    ("local_path.json", '{"path": "/home/byron/private/repo"}'),
])
def test_forbidden_file_patterns_fail_privacy_scan(tmp_path, name, body):
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    report = CommonsPrivacyScrubber().scan_space(tmp_path, [name])

    assert report["safe"] is False


def test_manifest_builder_blocks_forbidden_raw_prompt_path(tmp_path):
    (tmp_path / "raw_prompt.txt").write_text("private prompt", encoding="utf-8")

    with pytest.raises(ValueError, match="privacy scan failed"):
        build_manifest(
            tmp_path,
            space_id="raw_prompt_space",
            name="Raw Prompt Space",
            task_class="demo",
            artifacts=[{"path": "raw_prompt.txt", "artifact_type": "prompt"}],
            hardware_profile={},
            verifier_bundles=[],
            reduction_claims={},
            safety={},
        )


def test_reproduce_with_missing_verifier_artifact_fails_without_reputation(tmp_path):
    registry = prepared_registry(tmp_path)
    federation = FederatedCommons(registry, tmp_path / "federation")
    envelope = federation.prepare("tiny_llama_opus_gateway_repair", contributor_id="node_alpha")
    federation.allow_contributor(
        "node_alpha",
        public_key_hash=envelope["signature"]["public_key_hash"],
        approved=True,
        reason="test",
    )
    ingested = federation.ingest(envelope)
    (registry.root / "tiny_llama_opus_gateway_repair" / "README.md").unlink()
    replay = registry.replay("tiny_llama_opus_gateway_repair")
    recorded = federation.record_reproduction(ingested["envelope_id"], replay)

    assert replay["reproduced"] is False
    assert recorded["reputation"]["successful_reproductions"] == 0


def test_stale_fingerprint_stays_unadopted(tmp_path):
    registry = prepared_registry(tmp_path)
    artifact = registry.root / "tiny_llama_opus_gateway_repair" / "README.md"
    artifact.write_text(artifact.read_text(encoding="utf-8") + "\nstale mutation\n", encoding="utf-8")
    replay = registry.replay("tiny_llama_opus_gateway_repair")

    assert replay["reproduced"] is False
    with pytest.raises(ValueError, match="must validate"):
        registry.adopt(
            "tiny_llama_opus_gateway_repair",
            approved=True,
            dry_run=False,
            approved_by="test",
            reason="should fail",
        )
    assert registry.get("tiny_llama_opus_gateway_repair")["adoptions"] == []


def test_duplicate_space_import_is_suppressed_by_manifest_hash(tmp_path):
    source = prepared_registry(tmp_path / "source")
    exported = source.export_bundle("tiny_llama_opus_gateway_repair")
    target = CommonsSpaceRegistry(tmp_path / "target")
    first = target.import_untrusted_bundle(Path(exported["path"]), approved=True, dry_run=False)
    second = target.import_untrusted_bundle(Path(exported["path"]), approved=True, dry_run=False)

    assert first["imported"] is True
    assert second["duplicate"] is True
    assert second["imported"] is False


def test_reputation_gaming_duplicate_reproduction_is_suppressed(tmp_path):
    registry = prepared_registry(tmp_path)
    federation = FederatedCommons(registry, tmp_path / "federation")
    envelope = federation.prepare("tiny_llama_opus_gateway_repair", contributor_id="node_alpha")
    federation.allow_contributor(
        "node_alpha",
        public_key_hash=envelope["signature"]["public_key_hash"],
        approved=True,
        reason="test",
    )
    ingested = federation.ingest(envelope)
    replay = registry.replay("tiny_llama_opus_gateway_repair")
    first = federation.record_reproduction(ingested["envelope_id"], replay)
    second = federation.record_reproduction(ingested["envelope_id"], replay)

    assert first["reputation"]["reproductions"] == 1
    assert second["duplicate"] is True
    assert second["reputation"]["reproductions"] == 1
