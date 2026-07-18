from app.kernel.commons.artifact_vault import ArtifactVault


def test_artifact_vault_round_trip_and_digest_verification(tmp_path):
    vault = ArtifactVault(tmp_path)
    digest = vault.put(b"model chunk")
    assert vault.get(digest) == b"model chunk"


def test_artifact_vault_rejects_symlink_substitution(tmp_path):
    vault=ArtifactVault(tmp_path/"vault")
    payload=b"model chunk"; digest="sha256:"+__import__("hashlib").sha256(payload).hexdigest()
    outside=tmp_path/"outside"; outside.write_bytes(payload)
    (tmp_path/"vault"/digest[7:]).symlink_to(outside)
    assert vault.has(digest) is False
    import pytest
    with pytest.raises(ValueError,match="regular immutable"):
        vault.get(digest)
