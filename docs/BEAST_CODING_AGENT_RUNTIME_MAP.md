# BEAST Coding Agent Runtime Map

Evidence snapshot: GitHub Actions run `35281718864`, commit `c69bfb63d26620b6710633ac4a5fc2a190ab5816`.
Runtime artifact: `beast-phase0-runtime-journeys`, artifact ID `10522738695`, ZIP digest `sha256:be7c307ec30a5d28ca3254a9e90c3c1d88eb6f68df4e84d8acf6d6957e91b8c2`.

## Evidence boundary

### Observed production backend path (scripted provider)

These journeys execute the real `AgentRunEngine`, `AgentPlannerRuntime`, typed tool runtime, worktree lifecycle and durable AgentRun ledger. The model-decision source is deliberately scripted so this evidence proves backend composition and lifecycle behavior without pretending to prove a real model/provider or desktop ingress.

- Desktop renderer / Pair Programmer ingress: **not proven by this harness**
- Real Ollama/NIM provider execution: **not proven by this harness**
- Sensorium mirror receipt: **not proven by AgentRun ledger events alone**

## Observed component producers

- `app/kernel/agents/planner_runtime.py`
- `app/kernel/agents/run_store.py`
- `app/kernel/agents/tool_runtime.py`

## Journey results

| Journey | Final state | Durable events | Tool observations |
|---|---|---:|---:|
| `analysis_only` | `completed` | 18 | 2 |
| `single_file_mutation` | `completed` | 95 | 6 |
| `cross_file_mutation` | `completed` | 124 | 8 |
| `verification_failure_repair` | `completed` | 127 | 8 |

All four AgentRun chains verified with matching heads in the pinned workflow run.

## Observed gaps

- `completed_with_unresolved_cross_file_objective`: unresolved path `consumer.py`.

The cross-file finding is an observation of current behavior, not a Phase 0 repair. The planner can satisfy its latest-mutation verification and SourcePlan guard while part of the original multi-file objective remains unresolved. In the observed journey, the first mutation was followed by phase-enforced verification and SourcePlan handling, while the second requested file mutation did not occur.

## Observed backend route

`AgentRunStore` → `AgentPlannerRuntime` → `AgentToolRuntime` → typed workspace/worktree tools → verification / SourcePlan → durable hash-chained AgentRun evidence.

Sensorium mirroring is intentionally not promoted from these events because the current AgentRun engine treats that mirror as best-effort. A distinct Sensorium receipt is required before that edge becomes observed.

## Static/runtime separation

The deterministic full-system census remains a static source-of-truth projection with runtime fields initialized to `unverified`. This runtime map is an evidence-backed overlay. Runtime promotion into any derived census must occur through `scripts/trace_beast_coding_agent_runtime.py`, never from imports, documentation, tests, or this prose map alone.
