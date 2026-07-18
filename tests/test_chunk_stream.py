from app.kernel.commons.chunk_store import ChunkStore


def test_chunk_stream_supports_resume(tmp_path):
    store = ChunkStore(tmp_path, chunk_size=3); manifest = store.put(b"abcdefgh")
    assert b"".join(store.stream(manifest, start_chunk=1)) == b"defgh"

