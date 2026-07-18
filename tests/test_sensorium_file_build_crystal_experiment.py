import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.kernel.compute.file_build_transform import atomic_render, expected_artifact, inspect_source, verify_artifact
from app.kernel.compute.sensorium_file_build_crystal_experiment import SensoriumFileBuildCrystalExperiment


def _keys(tmp_path):
    key=Ed25519PrivateKey.generate();private=tmp_path/"arda.pem";public=tmp_path/"arda.pub.pem"
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
    return private,public


def test_transform_is_byte_exact_and_rejects_symlink_source(tmp_path):
    workspace=tmp_path/"workspace";workspace.mkdir();(workspace/"source.json").write_text('{"values":[3,-1,5],"name":"proof"}\n')
    source=inspect_source(workspace);effect=atomic_render(workspace,source)
    assert effect["artifact_sha256"].startswith("sha256:")
    assert (workspace/"generated.json").read_bytes()==expected_artifact(source)
    assert verify_artifact(workspace,source)["tests_passed"] is True
    (workspace/"source.json").unlink();(workspace/"source.json").symlink_to(tmp_path/"outside.json")
    assert inspect_source(workspace)["eligible"] is False


def test_file_build_crystal_is_naturally_generalized_promoted_and_executed(tmp_path):
    private,public=_keys(tmp_path)
    receipt=SensoriumFileBuildCrystalExperiment(tmp_path/"state",arda_private_key=private,arda_public_key=public).run()
    receipt.validate()
    assert receipt.verified is True
    assert receipt.structural_signature==(
        ("file.inspect_source","observation"),("build.select_branch","decision"),
        ("build.render_artifact","actuation"),("artifact.verify_build","verification"),
    )
    assert receipt.inferred_parameters==("workspace_identity",)
    assert receipt.replay_verified_variants==6
    assert receipt.rollback_probe_passed is True
    assert receipt.initial_artifact_digest!=receipt.final_artifact_digest==receipt.expected_artifact_digest
    assert receipt.compute_plane_phases==("begin","authorize","execute","verify","complete")
    assert receipt.provider_calls==0 and receipt.negative_cases_passed==2
    assert receipt.evidence_packet_digest.startswith("sha256:")


def test_persisted_live_receipt_is_content_bound_when_present():
    path=Path("docs/evidence/sensorium-learned-file-build-crystal-linux-2026-07-15.json")
    if not path.exists(): return
    value=json.loads(path.read_text())
    assert value["verified"] is True
    assert value["final_artifact_digest"]==value["expected_artifact_digest"]
