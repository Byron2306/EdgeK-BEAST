# Forge KV proof status

## Ollama legacy context API

Status: **not proven for performance claims**.

The local warmed paired measurement for qwen2.5:0.5b supplied and returned
Ollama native context, but the median continuation processed 1,292 prompt-eval
tokens versus 1,262 for the warmed fresh-prompt baseline. The continuation was
also slower. This means context-array transport is observed, but it must not be
reported as prompt-work or latency savings.

Promotion requires a repeatable engine-specific paired proof whose median
measured prompt work is lower than its warmed baseline. Until then, Forge KV
results expose performance_claim_allowed: false.

## llama.cpp prompt cache

Status: **proven for engine-local prompt-cache claims only**.

The local llama.cpp runtime reports cache_n and prompt_n for each completion.
The paired cache receipt recorded 962 cached prompt tokens and only 9 new
prompt tokens versus 971 on fresh requests. The restart-boundary receipt then
showed 642 cached tokens and 7 new prompt tokens before restart, followed by
cache_n 0 and 649 new prompt tokens after restart. This proves local
single-server cache reuse and explicitly rules out a portable raw-KV claim.

Receipts:

- `evidence/forge_kv/llamacpp_prompt_cache_20260720T115125Z.json`
- `evidence/forge_kv/llamacpp_restart_boundary_20260720T131312Z.json`

Start the isolated server in one terminal:

    scripts/forge_kv_llamacpp_server.sh

Run the proof in another:

    scripts/forge_kv_llamacpp_proof.sh

For the stronger lifetime boundary, run the self-contained restart proof. It
starts and stops an isolated server on port 11436 and must show both a warm
cache hit before restart and no cache reuse after restart:

    scripts/forge_kv_llamacpp_restart_boundary.sh
