# BEAST Coding Agent Recovery — Phase 3 Completion

**Programme:** BEAST Coding Agent Recovery Master Plan, 2026-09-17  
**Recovery phase:** 3 — Agent Core Repair  
**Status:** PASS  
**Base:** `agent/beast-coding-agent-phase2-runtime-trace` @ `2f9825c576a79de5ff47b54a95bd33a4aa9a3201`  
**Verified implementation head:** `92502aa7c58399acc862d74286ee56f40a9cb851`

> This is Recovery Phase 3 from the September Recovery Master Plan. It is not
> the older July "least-authority Phase 3" roadmap.

## Exit condition

Recovery Phase 3 closes when:

> A simple governed local-model mutation completes reliably with truthful telemetry.

That exit condition is **met**.

A real hosted Ollama `qwen2.5:0.5b` model ran the canonical
`AgentPlannerRuntime` against a seeded Git repository and completed the
governed lifecycle:

```text
inspect
  -> isolated worktree
  -> exact mutation
  -> verification PASS
  -> SourcePlan ready
  -> planner completion
```

The source workspace remained unchanged while the isolated worktree contained
the verified mutation.

## Repaired Phase 0 / Phase 2 defects

### 1. Planner lifecycle budget

Before repair, the local mutating renderer/backend path defaulted to five
planner turns even though the clean mandatory lifecycle itself requires more
turns.

Recovery Phase 3 now has one kernel-owned lifecycle budget policy:

- mutating lifecycle minimum: 8 turns;
- local Ollama mutation default: 12 turns;
- non-local mutation default: 10 turns;
- analysis default: 8 turns;
- explicit operator limits remain authoritative and are truthfully flagged
  when below the lifecycle minimum.

The runtime emits `agent.planner.turn_budget` with requested, effective,
minimum, source and below-minimum state.

### 2. Pair Programmer protocol conflict

Detached AgentRun planners no longer receive a frontend instruction demanding
BEAST Action IR while the backend simultaneously demands `PlannerDecision`.

For detached planner runs:

- the renderer identifies the canonical `PlannerDecision` backend contract;
- Action IR is explicitly not requested from the model;
- backend tools remain authoritative for repository discovery, mutation,
  verification and SourcePlan handoff.

Legacy non-detached Action IR behavior remains separate.

### 3. Premature three-file context clipping

Detached planner runs no longer truncate repository file hints to three files
before backend repository discovery begins.

The renderer may forward up to the existing normalized 48-file hint boundary,
while the backend repository tools remain authoritative for discovery. This
removes the artificial three-file tunnel without turning attachments into
mutation authority.

### 4. Compact prompt truncation

Compact-model prompts no longer use prefix-only truncation.

The repaired compactor preserves:

- the planner contract at the front;
- the newest authority, context, durable-plan and repair evidence at the tail;
- an explicit marker for omitted middle context.

This prevents late verification or authority evidence from disappearing under
context pressure.

### 5. Ollama runtime limits and native-context output

The canonical safe local planner defaults are now:

```text
num_ctx:     2048
num_predict: 128
```

The native KV-context path no longer hard-codes a 48-token generation limit. It
uses the same effective `num_predict` as the provider.

Provider usage and `agent.model.usage` now preserve the real effective:

- `num_ctx`;
- `num_predict`;
- `num_thread`;
- `num_batch`;
- prompt/completion evaluation counts;
- timeout;
- route / pressure / native-context evidence where present.

The renderer no longer claims an invented "8K context · 4K output" profile for
the detached planner.

### 6. Agentic Loop Endurance import surface

The endurance workflow now proves collection/import before executing planner
tests and installs the optional Python modules its exercised import graph
requires.

A red endurance result can therefore no longer be caused silently by the
planner test module failing before collection.

## Verification

On implementation head `92502aa7c58399acc862d74286ee56f40a9cb851`:

- **BEAST Recovery Phase 3 Core Repair:** PASS
- **BEAST Recovery Phase 3 Live Local Mutation:** PASS
- **Agentic Loop Endurance:** PASS
- **BEAST Phase 2 Completion Gate:** PASS
- **BEAST Phase 2 Hosted Ollama Acceptance:** PASS
- **BEAST Phase 2 Desktop Ingress Acceptance:** PASS

The Recovery Phase 2 evidence boundary therefore remains intact after the core
repairs.

## Live local-model artifact

```text
workflow_run: 35311883789
artifact: beast-recovery-phase3-live-local
artifact_id: 10533189844
digest: sha256:4a86b3dc4a14db850c688411136c5dc2485539ae355c574c927d2a581256c9d9
model: qwen2.5:0.5b
runtime: hosted Ollama native /api/generate
```

## Evidence boundary

This phase repairs deterministic agent-core defects. It does **not** claim that
Recovery Phase 4 repository intelligence is complete.

Sensorium, repository indexing and Code Cortex may already exist in the
organism, but the next Recovery phase must prove and consolidate their live
role in task discovery rather than assuming file presence or imports equal
runtime wiring.

## Next canonical phase

**Recovery Phase 4 — Perception & Repository Intelligence**

Exit target:

> Cross-file tasks discover relevant evidence without manual three-file
> attachment dependence.
