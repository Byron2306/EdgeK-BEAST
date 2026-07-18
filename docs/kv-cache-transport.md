# KV Cache Transport Setup

BEAST's KV transport only moves exact engine-native payload bytes. Metadata-only
blocks are deliberately not persisted, sent, or reused.

## Local setup

The gateway now uses the centralized KV settings:

```bash
BEAST_KV_CACHE_DIR=/var/lib/beast/kv-cache
BEAST_KV_MAX_MEMORY_BYTES=8589934592
```

The local restore check is available at `GET /edgek/kv-cache/restore-harness`.
It proves local register, persistence, reload, identity validation, and lookup;
it does not claim that Ollama, vLLM, or SGLang can import each other's opaque
runtime tensors.

## Authenticated peer setup

To send a block to a BEAST peer, configure the source gateway with the peer's
receive URL and a shared high-entropy token:

```bash
BEAST_KV_TRANSPORT_ENDPOINT=https://peer.example/edgek/kv-cache/receive
BEAST_KV_TRANSPORT_TOKEN=<shared-secret>
BEAST_KV_TRANSPORT_MAX_BYTES=67108864
```

Configure the receiving gateway with the same token and a writable cache
directory. The receiver rejects transfers unless its token is configured and
the `X-BEAST-KV-Token` header matches. It also rejects empty or oversized
payloads, malformed manifests, checksum mismatches, invalid engines, identity
collisions, and non-engine-native payloads.

A producer must set `target_endpoint` in the block metadata to the configured
peer URL. The transport writes a checksum-bound receipt beside the source
block and persists verified received bytes on the target. Network transport is
an explicit peer action; it is never enabled merely because a cache block
exists.
