# BEAST API Surface Contracts

Date: 2026-06-28

BEAST now publishes API stability groups at `GET /edgek/api/groups`.

## Stable Groups

Stable groups preserve `beast_object_type` and required request/response fields:

| Group | Routes |
| --- | --- |
| Health | `/health`, `/proxy/health`, `/mcp/health` |
| Providers | `/edgek/providers/registry`, `/edgek/providers/adapters`, `/edgek/providers/secrets/route/{provider_id}` |
| Integration Harness | `/edgek/integration-harness/run` |
| Crystal Reuse | `/edgek/crystal-reuse`, `/edgek/crystal-reuse/decide`, `/edgek/crystal-reuse/record`, `/edgek/crystal-reuse/prefill` |
| Memory Security | `/edgek/memory-security` |
| Readiness | `/edgek/readiness/federation-soak`, `/edgek/readiness/workload-frequency` |

## Experimental Groups

Experimental routes may add fields and evolve payloads while retaining local safety boundaries:

| Group | Routes |
| --- | --- |
| Commons Marketplace | `/edgek/commons-*`, `/edgek/proof-local/*` |
| Crystal Lattice | `/edgek/crystal-chain`, `/edgek/crystal-lattice` |
| Operator TUI Support | `/edgek/session/*`, `/edgek/insights/*`, `/edgek/handoff/*` |

## Deprecated Routes

No routes are deprecated as of 2026-06-28.
