# BEAST RC4 live UI contract audit

## Evidence interpretation

This is a route-discovery probe, not a full API contract test. `200` means the
GET probe returned successfully. `405` means the route was discovered but the
declared mutating verb was not exercised by this audit. It does **not** prove
schema validation, authorization, service reachability, mutation effects, or
response-contract validity. RC5 must add method-aware harmless-fixture probes.

Generated: 2026-07-15T01:03:57.070446+00:00

| Route | GET probe | Interpretation |
|---|---:|---|
| `/edgek/benchmarks/public-grading-daemon` | 405 | wired |
| `/edgek/chronicle` | 200 | wired |
| `/edgek/commons-economy` | 200 | wired |
| `/edgek/compression/pipeline` | 200 | wired |
| `/edgek/crystal-chain` | 200 | wired |
| `/edgek/crystal-chain/attest` | 405 | wired |
| `/edgek/crystal-lattice` | 200 | wired |
| `/edgek/crystal-lattice/checkpoint` | 405 | wired |
| `/edgek/crystal-reuse` | 200 | wired |
| `/edgek/evidence-bus/query` | 200 | wired |
| `/edgek/ide/actions/manifest` | 200 | wired |
| `/edgek/ide/agent-sessions/cancel` | 200 | wired |
| `/edgek/ide/agent-sessions/create` | 200 | wired |
| `/edgek/ide/agent-sessions/pause` | 200 | wired |
| `/edgek/ide/agent-sessions/resume` | 200 | wired |
| `/edgek/ide/mission-runbook/export` | 405 | wired |
| `/edgek/ide/mission-runbook/verify` | 405 | wired |
| `/edgek/ide/ports/free` | 405 | wired |
| `/edgek/ide/ports` | 200 | wired |
| `/edgek/ide/release-readiness/check` | 405 | wired |
| `/edgek/ide/sourceplan/from-editor` | 405 | wired |
| `/edgek/ide/sourceplan/lifecycle` | 405 | wired |
| `/edgek/ide/system/kill` | 405 | wired |
| `/edgek/ide/worktree-mission/close` | 405 | wired |
| `/edgek/ide/worktree-mission/create` | 405 | wired |
| `/edgek/ide/worktree-mission/diff` | 405 | wired |
| `/edgek/ide/worktree-mission/sourceplan-draft` | 405 | wired |
| `/edgek/ide/worktree-mission/test` | 405 | wired |
| `/edgek/insights/compile` | 405 | wired |
| `/edgek/kv-cache/state` | 200 | wired |
| `/edgek/mcp/approvals` | 200 | wired |
| `/edgek/mcp/audit` | 200 | wired |
| `/edgek/mcp/executions` | 200 | wired |
| `/edgek/mcp/schema-pins` | 200 | wired |
| `/edgek/mcp/servers` | 200 | wired |
| `/edgek/mcp/state` | 200 | wired |
| `/edgek/memory-security` | 200 | wired |
| `/edgek/memory/compact` | 405 | wired |
| `/edgek/plugins` | 200 | wired |
| `/edgek/plugins/manifest/validate` | 405 | wired |
| `/edgek/prec/state` | 200 | wired |
| `/edgek/provider-economist/select` | 405 | wired |
| `/edgek/providers/compression/toggle` | 405 | wired |
| `/edgek/providers/kv-cache/clear` | 405 | wired |
| `/edgek/providers/nvidia-nim/live-smoke` | 405 | wired |
| `/edgek/providers/registry` | 200 | wired |
| `/edgek/providers/state` | 200 | wired |
| `/edgek/root-info` | 200 | wired |
| `/edgek/runtime/state` | 200 | wired |
| `/edgek/runtime/sweep` | 405 | wired |
| `/edgek/safety-governor/classify-command` | 405 | wired |
| `/edgek/skills/promote` | 405 | wired |
| `/edgek/sourceplan/apply` | 405 | wired |
| `/edgek/sourceplan/verify` | 405 | wired |
| `/edgek/tools/integrations` | 200 | wired |
