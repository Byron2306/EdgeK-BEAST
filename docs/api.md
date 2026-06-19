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
