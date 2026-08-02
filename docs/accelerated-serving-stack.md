# KV-aware serving stack

BEAST now has operational adapters for these independent layers:

| Layer | BEAST integration | Runtime condition |
| --- | --- | --- |
| Local prefix KV store | Exact compatibility and identity guard; no external runtime required | Available now |
| LMCache MP | Health, `/status`, Prometheus metrics, explicit approved cache clear | Set `LMCACHE_HTTP_URL` after deployment |
| vLLM | OpenAI-compatible generation, `/v1/models` probe, prefix cache and LMCache MP deployment manifest | Supported accelerator plus explicit enablement |
| SGLang | OpenAI-compatible generation and `/v1/models` probe | Configured SGLang server plus explicit enablement |
| TensorRT-LLM | OpenAI frontend or native Triton generate API | NVIDIA runtime plus explicit enablement |
| TGI | OpenAI Messages API with documented native `/generate` fallback | A configured TGI server; Intel CPU TGI is possible |

## Safety boundary

`BEAST_ACCELERATOR_ENABLED=true` is required before BEAST can send a request to vLLM, SGLang, or TensorRT-LLM. An endpoint alone is not authority to use an accelerator. On the present Intel-only host, this remains off and those engines fail closed.

BEAST does not feed `CrossEngineKVCacheTransport` tensors into vLLM, SGLang, LMCache, or TensorRT-LLM. Those engines own their native KV representation. The BEAST local-prefix layer is therefore an admission and compatibility record, not a claim that arbitrary KV tensors are portable.

## vLLM + LMCache MP

The reviewed manifest is [compose.vllm-lmcache.yml](../deploy/accelerator/compose.vllm-lmcache.yml). On a supported GPU host, create an operator-owned `.env` with a pinned image and model, review it, then start the `gpu` profile. The stack uses LMCache MP, SHA-256 prefix hashing, and vLLM's `LMCacheMPConnector`.

After it is live, configure BEAST:

```bash
export VLLM_BASE_URL=http://127.0.0.1:8000
export LMCACHE_HTTP_URL=http://127.0.0.1:8081
export LMCACHE_ZMQ_URL=tcp://127.0.0.1:5555
export LMCACHE_MODE=mp
export BEAST_ACCELERATOR_ENABLED=true
```

Then inspect, rather than assume:

```bash
curl 'http://127.0.0.1:8000/edgek/inference-engines?probe=true'
curl 'http://127.0.0.1:8000/edgek/lmcache/state?probe=true'
```

`POST /edgek/lmcache/clear` requires `{ "approved": true }`; no automatic cache deletion is performed.

## Other server adapters

Set one endpoint and use the existing governed generation route:

```bash
export SGLANG_BASE_URL=http://server:30000
export TGI_BASE_URL=http://127.0.0.1:8080
export TENSORRT_LLM_BASE_URL=http://triton:9000
# For a native Triton TensorRT-LLM endpoint instead of its OpenAI frontend:
export TENSORRT_LLM_API_MODE=triton
export TENSORRT_LLM_MODEL_NAME=tensorrt_llm
```

Use `POST /edgek/inference-engines/{engine_id}/generate` only after its live probe passes. Successful API reachability is not evidence of a cache hit: cache savings require the engine's own metrics and a paired workload receipt.

For this Intel host, [compose.tgi-intel-cpu.yml](../deploy/accelerator/compose.tgi-intel-cpu.yml) is the available local expansion route. It pins the last published official Intel CPU image rather than the now-retired `3.3.5-intel-cpu` tag, and deliberately does not request `/dev/dri` or privileged container access. It adds a TGI server, not a KV-sharing layer.
