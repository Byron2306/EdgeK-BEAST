from app.kernel.commons.chunk_store import ChunkStore


def test_chunk_store_reconstructs_digest_bound_artifact(tmp_path):
    store = ChunkStore(tmp_path, chunk_size=4)
    payload = b"abcdefghijk"
    manifest = store.put(payload)
    assert len(manifest.chunks) == 3
    assert store.get(manifest) == payload
    assert manifest.artifact_size == len(payload)
