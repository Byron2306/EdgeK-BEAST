# BEAST Crystal Reuse Integrations

Status: **implemented local control plane with public integration contracts**.

BEAST now has a crystal reuse gateway that decides whether a request should
reuse stored inference before any provider execution. The implementation lives
in `app/kernel/compute/crystal_reuse_gateway.py`.

## Runtime Order

1. Reuse a verified semantic compute credit.
2. Reuse an exact cached answer.
3. Reuse a durable prefill identity.
4. Use a semantic-cache adapter hook.
5. Use the local LMCache-style KV transport adapter.
6. Execute the provider through the normal BEAST-governed route.

## Public Repo Mapping

| Repo | BEAST role | Local adapter |
| --- | --- | --- |
| `LMCache/LMCache` | External KV and prefix-cache substrate | `CrossEngineKVCacheTransport` |
| `zilliztech/GPTCache` | Semantic answer cache | `DurableInferenceStorage` plus `semantic_matcher` hook |
| `BerriAI/litellm` | Provider gateway behind BEAST governance | existing provider gateway insertion point |
| `traceloop/openllmetry` | OpenTelemetry spans for crystal lifecycle | `export_openllmetry_span()` |
| `langfuse/langfuse` | Trace, dataset, and eval observation export | `export_langfuse_observation()` |
| `tensorzero/tensorzero` | Inference feedback and optimization flywheel | `crystal_reuse_record_receipt` payload |
| `promptfoo/promptfoo` | Reuse safety assertions and CI eval gates | `export_promptfoo_assertion()` |
| `vllm-project/vllm` | Prefix-cache-capable execution engine | `InferenceEngineFabric` |
| `sgl-project/sglang` | Radix-cache structured execution engine | `InferenceEngineFabric` |

## API

- `GET /edgek/crystal-reuse`
- `POST /edgek/crystal-reuse/decide`
- `POST /edgek/integration-harness/run`
- `POST /edgek/crystal-reuse/record`
- `POST /edgek/crystal-reuse/prefill`
- `POST /edgek/crystal-reuse/kv-block`
- `GET /edgek/memory-security`

## Thin Integration Harness

`POST /edgek/integration-harness/run` exercises the production flow as one
auditable receipt:

1. `AgentPassportPolicy` authorizes the caller.
2. `CrystalReuseGateway` decides reuse versus provider execution.
3. The provider result is verified when provider execution is required.
4. `ResidueSeal` signs the final harness receipt.
5. `MemoryHull` writes Markdown plus a sealed sidecar for verified provider
   responses that become reusable crystals.
6. `EnterpriseManager` records budget, observability, and encrypted trace data
   when team context is supplied.
7. `ProductionReadinessHardeningGauntlet.production_ops_gate()` emits the
   readiness gate receipt embedded in the harness receipt.

The harness is intentionally thin: provider execution and verification are
callable insertion points, so production routes can plug in without changing
the evidence contract.

## TUI

The BEAST TUI now surfaces these layers on the Intelligence page with dedicated
Crystal Reuse Integrations and Memory Hull / Residue Seal / Agent Passport
panels. The Deployment page also reports the crystal reuse gateway, public reuse
adapter count, and memory-security readiness alongside Nginx, LiteLLM, and
provider adapter status.

## First-Class Adapter State

`GET /edgek/crystal-reuse/integrations` reports every public integration as a
named BEAST adapter with configured state, capability flags, repo URL, expected
environment variables, and claim boundary.

`POST /edgek/crystal-reuse/export` builds native envelopes for:

- LMCache reuse manifests
- GPTCache semantic records
- LiteLLM metadata passthrough
- OpenLLMetry/OpenTelemetry spans
- Langfuse observations and scores
- TensorZero feedback candidates
- Promptfoo assertions

The gateway is intentionally dependency-light. External services become live
when their environment variables are configured, but BEAST can already perform
local exact-answer reuse, semantic-credit reuse, durable prefill lookup, KV
block reuse, decision sealing, and observability-envelope export without those
services running.
