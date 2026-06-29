# BEAST API Reference

BEAST exposes an OpenAI-compatible gateway, an Anthropic-compatible gateway, and BEAST-native governance endpoints.

Start the server:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8005
```

Base URL:

```text
http://localhost:8005
```

## Health And UI

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Gateway health check |
| `GET` | `/edgek/state` | High-level BEAST state |
| `GET` | `/ui` | BEAST cockpit web UI |

## Provider-Compatible Inference

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/v1/chat/completions` | OpenAI-compatible chat completions |
| `POST` | `/v1/messages` | Anthropic-compatible messages |
| `POST` | `/hf/v1/chat/completions` | Hugging Face router-compatible chat completions |
| `POST` | `/litellm/v1/chat/completions` | LiteLLM proxy-compatible chat completions |

## Output Governance And Coding Flow

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/edgek/handoff/prepare` | Build provider handoff packet |
| `POST` | `/edgek/beast-cli/plan` | Create a governed source plan |
| `POST` | `/edgek/beast-cli/execute` | Execute a governed BEAST CLI action |
| `GET` | `/edgek/canon/schemas` | List canonical output schemas |
| `POST` | `/edgek/canon/validate` | Validate canonical Action IR / output payloads |
| `GET` | `/edgek/canon/metrics` | Output-governance metrics |
| `POST` | `/edgek/maintenance/run` | Run repo hygiene checks: language inventory, Python compile, pytest collection, dependency sanity, HTML/JS syntax, docs links, extension syntax, optional pytest and packaging/build checks |
| `GET` | `/edgek/chronicle` | Chronicle event list |
| `POST` | `/edgek/chronicle/publish` | Publish Chronicle evidence |
| `POST` | `/edgek/session/handshake` | Build the BEAST agent-awareness and local preflight latency contract |
| `GET` | `/edgek/memory-security` | Report Memory Hull, Residue Seal, and Agent Passport state |

## Connectors And Marketplace

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/edgek/connectors/otel` | Report OTLP/HTTP connector configuration |
| `POST` | `/edgek/connectors/otel/export` | Export Chronicle, route, packet-timing, and provider-fitness spans to Grafana Tempo, Jaeger, or another OTLP collector |
| `POST` | `/edgek/plugins/manifest/prepare` | Canonicalize a plugin manifest and generate tool schema hashes |
| `POST` | `/edgek/plugins/manifest/validate` | Validate risk, permissions, budgets, approvals, and schema pins |
| `POST` | `/edgek/plugins/install` | Dry-run or perform an explicitly approved local installation |
| `GET` | `/edgek/plugins` | List installed local plugin manifests |

OTLP export uses `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` or `OTEL_EXPORTER_OTLP_ENDPOINT`; optional headers use `OTEL_EXPORTER_OTLP_HEADERS`. Live export and plugin installation are approval-gated and dry-run by default.

## Capability Exchange

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/edgek/capability-exchange` | Report opt-in, endpoint, signing, and privacy state |
| `POST` | `/edgek/capability-exchange/prepare` | Prepare allowlisted tool or skill outcome evidence |
| `POST` | `/edgek/capability-exchange/rank` | Rank capabilities contextually by task class and role |
| `POST` | `/edgek/capability-exchange/submit` | Submit evidence after opt-in and explicit approval |
| `GET` | `/edgek/meta-tool-commons` | Report local Commons evidence, candidate, and adoption state |
| `POST` | `/edgek/meta-tool-commons/ingest` | Validate and deduplicate privacy-safe capability evidence |
| `POST` | `/edgek/meta-tool-commons/rank` | Rank schema-pinned capabilities by task class and role |
| `POST` | `/edgek/meta-tool-commons/candidates` | Stage a local or shared promotion candidate |
| `POST` | `/edgek/meta-tool-commons/adopt` | Adopt a staged recipe after explicit local approval |
| `GET` | `/edgek/meta-tool-commons/snapshot` | Export an integrity-hashed advisory ranking snapshot |
| `GET` | `/edgek/compute` | Report Phase 1 shadow Compute Governor state |
| `GET` | `/edgek/compute/metrics` | Summarize observed usage and counterfactual avoidable-compute estimates |
| `GET` | `/edgek/compute/savings-summary` | Project weekly shadow savings only with call-volume and first-party cost evidence |
| `GET` | `/edgek/compute/plans` | List privacy-safe Compute Plans |
| `GET` | `/edgek/compute/receipts` | List Compute Receipts linked to runtime attempts |
| `GET` | `/edgek/compute/receipts/{receipt_id}` | Read one Compute Receipt |
| `GET` | `/edgek/compute/counterfactuals` | List rejected-route counterfactual crystals and calibration summary |
| `GET` | `/edgek/compute/escrows` | List compute escrow reservations, settlements, and refunds |
| `GET` | `/edgek/crystal-compute` | Report negative evidence, friction profiles, counterfactuals, escrows, and temporal forks |
| `POST` | `/edgek/crystal-compute/outcomes` | Record privacy-safe outcome evidence |
| `POST` | `/edgek/crystal-compute/maintenance` | Expire or prune local Crystal Compute evidence |
| `POST` | `/edgek/crystal-compute/negative/{record_id}/override` | Apply auditable local negative-evidence override |
| `GET` | `/edgek/crystal-compute/forks` | List stable, candidate, and experimental temporal crystal forks |
| `POST` | `/edgek/crystal-compute/forks` | Create a temporal crystal fork |
| `POST` | `/edgek/crystal-compute/forks/anneal` | Merge duplicate, split multimodal, and retire stale fork lineages |
| `GET` | `/edgek/crystal-compute/semantic-raid` | Report durable semantic shard integrity |
| `POST` | `/edgek/crystal-compute/semantic-raid/shards` | Store one durable intelligence shard |
| `POST` | `/edgek/crystal-compute/semantic-raid/reconstruct` | Repair corrupt or missing shard refs from mirrors |
| `GET` | `/edgek/crystal-compute/fossils/replay` | Replay fossilized artifact decision lineage |
| `GET` | `/edgek/crystal-reuse` | Report crystal reuse gateway inventory and public integration adapter state |
| `GET` | `/edgek/crystal-reuse/integrations` | Report first-class LMCache/GPTCache/LiteLLM/OpenLLMetry/Langfuse/TensorZero/Promptfoo adapter health |
| `POST` | `/edgek/crystal-reuse/decide` | Decide whether a prompt can reuse a semantic credit, exact answer, KV prefill, or KV transport block before provider execution |
| `POST` | `/edgek/crystal-reuse/export` | Build integration export envelopes for LMCache, GPTCache, LiteLLM, OpenLLMetry, Langfuse, TensorZero, and Promptfoo |
| `POST` | `/edgek/crystal-reuse/record` | Store a provider response as an exact answer crystal and optionally a verified semantic crystal |
| `POST` | `/edgek/crystal-reuse/prefill` | Register a durable prefill identity for model/tokenizer/prompt-prefix reuse |
| `POST` | `/edgek/crystal-reuse/kv-block` | Register and pin a KV block in the BEAST LMCache-style transport adapter |

## Providers And Routes

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/edgek/providers/state` | Provider runtime state |
| `GET` | `/edgek/providers/registry` | Provider registry |
| `GET` | `/edgek/providers/adapters` | Adapter inventory |
| `GET` | `/edgek/providers/secrets` | Secret presence metadata, not raw secrets |
| `GET` | `/edgek/route/cards` | Provider route cards |
| `GET` | `/edgek/route/cards/{route_id}` | Route card detail |
| `POST` | `/edgek/route/provider-diagnostic/{provider}` | Provider diagnostic run |
| `POST` | `/edgek/provider-economist/select` | Select a route by role, hidden-clean economics, rescue rate, latency, auth confidence, and cost envelope |

## Context, Tools, And Workspace

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/edgek/context/packet` | Build governed context packet |
| `POST` | `/edgek/tools/intercept` | Semantic tool-call interception |
| `GET` | `/edgek/tools/integrations` | Tool integration inventory |
| `GET` | `/edgek/workspace` | Workspace graph state |
| `POST` | `/edgek/workspace/index` | Index a repository |
| `GET` | `/edgek/workspace/search` | Workspace search |
| `GET` | `/edgek/workspace/semantic-context` | Retrieve semantic context |
| `POST` | `/edgek/tool-laziness/record` | Record tool-call value, cost, and latency evidence |
| `POST` | `/edgek/tool-laziness/recommend-tools` | Identify candidate tools BEAST recommends not calling |

## Runtime And Budgets

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/edgek/runtime/state` | Runtime governance state |
| `GET` | `/edgek/runtime/metrics` | Runtime metrics |
| `GET` | `/edgek/runtime/attempts` | Recent attempts |
| `POST` | `/edgek/runtime/circuit-breakers/{provider}/reset` | Reset a provider circuit breaker |

## OS Bypass And Packet Experiments

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/edgek/os-bypass/capabilities` | Report AF_PACKET, DPDK, AF_XDP, interface, and privilege readiness |
| `POST` | `/edgek/os-bypass/af-packet/probe` | Open and close an AF_PACKET TPACKET_V3 mmap ring |
| `POST` | `/edgek/os-bypass/af-packet/capture-probe` | Emit a marked loopback UDP datagram and verify AF_PACKET sees it |
| `POST` | `/edgek/os-bypass/dpdk/probe` | Initialize DPDK EAL and report available ethdev ports |
| `POST` | `/edgek/os-bypass/af-xdp/probe` | Load AF_XDP/libxdp and report socket-create readiness |

The AF_PACKET capture probe requires Linux packet sockets and `CAP_NET_RAW` or root. It is intended as a live host experiment: BEAST sends a small marked UDP packet to loopback, sniffs the raw packet path, parses captured frames, and reports whether the marker was observed.

## MCP Broker

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/edgek/mcp/evaluate` | Evaluate an MCP tool request |
| `POST` | `/edgek/mcp/execute` | Execute an approved MCP request |
| `GET` | `/edgek/mcp/state` | MCP broker state |
| `GET` | `/edgek/mcp/audit` | MCP audit log |
| `GET` | `/edgek/mcp/approvals` | Pending MCP approvals |

## Enterprise

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/edgek/enterprise/teams` | Create or update a team |
| `GET` | `/edgek/enterprise/teams` | List teams |
| `POST` | `/edgek/enterprise/virtual-keys` | Create virtual provider keys |
| `GET` | `/edgek/enterprise/observability` | Observability events |

## Notes

- `/edgek/providers/secrets` reports configured secret status only. It does not expose raw secret values.
- The live coding flow is `/sourceplan -> Action IR -> BEAST resolver -> diff preview -> selected apply -> verify -> Chronicle`.
- For the complete implementation surface, see [app/main.py](../app/main.py).
# Commons Compute Spaces

Local Compute Spaces are advisory, content-addressed packages with signed
compute-reduction receipts.

- `GET /edgek/commons-spaces` lists local Spaces, artifact provenance, and the
  reduction scoreboard.
- `GET /edgek/commons-spaces/{space_id}` returns the manifest, receipt,
  validation results, and adoption history.
- `POST /edgek/commons-spaces/import` previews or imports a workspace-local
  bundle. Live import requires `approved=true` and `dry_run=false`.
- `POST /edgek/commons-spaces/{space_id}/adopt` records signed artifact
  references after explicit approval and an operator reason.
- `POST /edgek/commons-spaces/{space_id}/replay` performs deterministic
  integrity replay or explicitly approved allowlisted verifier replay.
- `GET /edgek/commons-spaces/{space_id}/reproductions` lists the local receipts
  used to derive the Space trust score.

The local policy learner exposes:

- `GET /edgek/commons-policy/examples`
- `GET /edgek/commons-policy/model`
- `GET /edgek/commons-policy/evaluation`
- `POST /edgek/commons-policy/recommend`

Policy recommendations are shadow-only and never change the active route.

Federated Commons endpoints:

- `GET /edgek/federated-commons` reports allowlists, quarantined hypotheses,
  reproduction reputation, expiry, revocations, and abuse-control limits.
- `POST /edgek/federated-commons/prepare/{space_id}` creates a signed expiring
  envelope. Ed25519 is always used; a post-quantum seal is attached when
  `liboqs` is available.
- `POST /edgek/federated-commons/allowlist` locally approves a contributor and
  pins its Ed25519 public-key hash.
- `POST /edgek/federated-commons/ingest` admits an allowlisted signed envelope
  as a quarantined hypothesis.
- `POST /edgek/federated-commons/{envelope_id}/reproduce` records local replay
  and updates contributor reputation.
- `POST /edgek/federated-commons/{envelope_id}/revoke` applies an auditable
  local revocation.
