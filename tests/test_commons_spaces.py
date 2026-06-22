import json
import zipfile

import pytest

from app.kernel.commons_spaces import (
    BUNDLE_MANIFEST_NAME,
    MANIFEST_NAME,
    build_manifest,
    build_reduction_receipt,
    export_space,
    import_space,
    package_tiny_llama_case,
    validate_manifest,
    validate_reduction_receipt,
    write_space,
)
from app.kernel.crystal_seal import canonical_bytes, verify_crystal_seal


def test_manifest_hashes_artifacts_and_rejects_private_paths(tmp_path):
    (tmp_path / "evidence.json").write_text('{"verified": true}\n', encoding="utf-8")
    manifest = build_manifest(
        tmp_path,
        space_id="demo_space",
        name="Demo Space",
        task_class="demo",
        artifacts=[{"path": "evidence.json", "artifact_type": "evidence"}],
        hardware_profile={"gpu_required": False},
        verifier_bundles=[],
        reduction_claims={"tokens_avoided": 10},
        safety={"approval_required": True},
    )

    assert validate_manifest(tmp_path, manifest)["valid"] is True
    assert manifest["artifacts"][0]["sha256"].startswith("sha256:")
    assert manifest["privacy"]["contains_private_paths"] is False

    (tmp_path / "unsafe.json").write_text('{"path": "/home/user/private.py"}', encoding="utf-8")
    with pytest.raises(ValueError, match="privacy scan failed"):
        build_manifest(
            tmp_path,
            space_id="unsafe",
            name="Unsafe",
            task_class="demo",
            artifacts=[{"path": "unsafe.json", "artifact_type": "evidence"}],
            hardware_profile={},
            verifier_bundles=[],
            reduction_claims={},
            safety={},
        )


def test_receipt_has_verifiable_local_seal(tmp_path, monkeypatch):
    monkeypatch.setenv("BEAST_CRYSTAL_SEAL_KEY", "test-space-key")
    (tmp_path / "evidence.json").write_text("{}\n", encoding="utf-8")
    manifest = build_manifest(
        tmp_path,
        space_id="sealed_space",
        name="Sealed",
        task_class="demo",
        artifacts=[{"path": "evidence.json", "artifact_type": "evidence"}],
        hardware_profile={},
        verifier_bundles=[],
        reduction_claims={},
        safety={},
    )
    receipt = build_reduction_receipt(
        space_manifest=manifest,
        baseline_route={"route_id": "cloud"},
        optimized_route={"route_id": "local"},
        displacement={"provider_calls_avoided": 1},
        verifier={"passed": True},
        resource_deltas={"gpu_avoided": True},
        provenance={"source": "test"},
        rollback_available=True,
        approval_required=True,
    )

    assert validate_reduction_receipt(receipt)["valid"] is True
    receipt["displacement"]["provider_calls_avoided"] = 2
    assert validate_reduction_receipt(receipt)["valid"] is False


def test_pqc_seal_can_use_portable_local_integrity_signature(monkeypatch):
    import hashlib
    import hmac

    monkeypatch.setenv("BEAST_CRYSTAL_SEAL_KEY", "portable-test-key")
    payload = {"receipt": "portable"}
    body = canonical_bytes(payload)
    signature = "hmac-sha256:" + hmac.new(b"portable-test-key", body, hashlib.sha256).hexdigest()
    seal = {
        "payload_hash": "sha256:" + hashlib.sha256(body).hexdigest(),
        "crypto_profile": {"provider": "liboqs", "signature": "ML-DSA-65"},
        "signature": "invalid-without-liboqs",
        "local_integrity_signature": signature,
    }

    assert verify_crystal_seal(payload, seal)["verified"] is True


def test_local_export_import_requires_approval_and_blocks_traversal(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "evidence.json").write_text("{}\n", encoding="utf-8")
    manifest = build_manifest(
        source,
        space_id="portable_space",
        name="Portable",
        task_class="demo",
        artifacts=[{"path": "evidence.json", "artifact_type": "evidence"}],
        hardware_profile={},
        verifier_bundles=[],
        reduction_claims={},
        safety={"approval_required": True},
    )
    write_space(source, manifest)
    bundle = tmp_path / "space.beast-space.zip"
    export_space(source, bundle)

    with zipfile.ZipFile(bundle) as archive:
        assert BUNDLE_MANIFEST_NAME in archive.namelist()

    preview = import_space(bundle, tmp_path / "imports", approved=False, dry_run=False)
    assert preview["imported"] is False
    assert preview["reason"] == "approval_required"

    imported = import_space(bundle, tmp_path / "imports", approved=True, dry_run=False)
    assert imported["imported"] is True
    assert (tmp_path / "imports" / "portable_space" / MANIFEST_NAME).exists()

    malicious = tmp_path / "malicious.zip"
    with zipfile.ZipFile(malicious, "w") as archive:
        archive.writestr("../escape", "no")
        archive.writestr(MANIFEST_NAME, json.dumps(manifest))
    with pytest.raises(ValueError, match="local and relative"):
        import_space(malicious, tmp_path / "other", approved=True, dry_run=False)


def test_private_key_files_are_never_exportable_or_importable(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    private_key = "-----BEGIN PRIVATE KEY-----\nnot-real-but-still-forbidden\n-----END PRIVATE KEY-----\n"
    (source / "node_ed25519.pem").write_text(private_key, encoding="utf-8")

    with pytest.raises(ValueError, match="private_key"):
        build_manifest(
            source,
            space_id="key_leak",
            name="Key Leak",
            task_class="demo",
            artifacts=[{"path": "node_ed25519.pem", "artifact_type": "fixture"}],
            hardware_profile={},
            verifier_bundles=[],
            reduction_claims={},
            safety={},
        )

    bundle = tmp_path / "key_leak.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("fixtures/test_private_key.pem", private_key)
        archive.writestr(MANIFEST_NAME, "{}")
        archive.writestr(BUNDLE_MANIFEST_NAME, "{}")

    with pytest.raises(ValueError, match="private_key"):
        import_space(bundle, tmp_path / "imports", approved=True, dry_run=False)


def test_tiny_llama_case_packages_without_raw_report(tmp_path):
    source = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "benchmarks/results/tiny_llama_opus_case_study_qwen25_05b"
    )
    result = package_tiny_llama_case(source, tmp_path / "space")

    assert result["manifest"]["valid"] is True
    assert result["receipt"]["valid"] is True
    assert not (tmp_path / "space" / "opus_case_report.json").exists()
    manifest = json.loads((tmp_path / "space" / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["reduction_claims"]["tokens_avoided"] is None
    assert manifest["privacy"]["contains_source_code"] is False
