# BEAST Coding Agent Phase 3 — Least-Authority Model-Directed Tool Use

**Branch:** `agent/beast-coding-agent-phase3-least-authority`  
**Phase 2 base:** `2f9825c576a79de5ff47b54a95bd33a4aa9a3201`  
**Source programme:** `4.0/BEAST_Next_Level_Upgrade_Master_Plan_2026-07-18.md`

## Objective

Turn the Phase 2 durable AgentRun loop into a bounded inspect, act, observe,
verify, diagnose and repair runtime in which the model receives only the
authority required for the current tool call.

Phase 3 must preserve these non-negotiable boundaries:

- the operator workspace is never directly model-mutated;
- isolated mutation requires Worktree Forge plus request-bound approval;
- consequential execution follows the declared tool risk/approval policy;
- SourcePlan promotion, remote push, publication, global policy mutation,
  evidence disabling and audit erasure are never model-authorized;
- every tool decision is receipt-backed before execution;
- failure does not widen authority.

## Phase 3 slices

### 3.1 Typed least-authority tool plane

Status: **IN PROGRESS**

Deliverables:

- every AgentRun tool publishes an authority class;
- every tool publishes redaction and evidence metadata;
- authority classes map to the Phase 3 A-E contract;
- runtime emits a hash-bound authority receipt before handler execution;
- Class E is structurally refused;
- Class C requires request-bound approval;
- existing worktree and target boundaries remain enforced.

### 3.2 Policy-profile budgets

Deliverables:

- move model turns, tool calls, mutation calls, verification cycles, changed
  files/lines, wall time, token and cost limits into explicit run policy
  profiles;
- make exhaustion a typed terminal or replan condition;
- emit budget deltas into the AgentRun ledger.

### 3.3 Stagnation and oscillation detection

Deliverables:

- detect equivalent repeated tool calls;
- detect turns that add no new evidence;
- detect repeated verifier failures;
- detect plan-state oscillation;
- require narrowed requests after repeated truncation;
- stop or replan without widening scope.

### 3.4 Verification ladder

Deliverables:

- cheapest relevant verification first;
- structured verification observations feed the same run;
- repeated failures enter bounded repair;
- successful verification is required before SourcePlan synthesis.

### 3.5 End-to-end seeded defect gauntlet

Exit journey:

```text
seeded multi-file defect
  -> inspect
  -> bounded tool calls
  -> isolated edits
  -> focused verification failure
  -> diagnosis
  -> bounded repair
  -> verification success
  -> worktree diff
  -> SourcePlan draft
```

## Phase 3 exit gate

Phase 3 is complete only when a multi-file seeded defect is solved through
repeated inspect, tool, edit, test, diagnose and repair turns in an isolated
worktree and converted into a reviewable SourcePlan, while an independent
acceptance test proves that:

1. Class E actions cannot be model-authorized.
2. Mutation never escapes the mission worktree.
3. Tool authority cannot widen after a failure.
4. Run budgets and stagnation controls terminate pathological loops.
5. Verification evidence is bound to the resulting SourcePlan.
6. The same AgentRun ledger records the complete journey.

## Phase 2 inherited evidence

The Phase 3 branch starts only after the Phase 2 completion gate passed on the
base head. Phase 2 already proves the durable backend request path, bounded
cross-file work, Sensorium admission, desktop renderer ingress, a real Ollama
planner exchange, hosted Docker/SSH return path, planner endurance, and the
closure receipt. Native Android/Termux acceptance is separately recorded in
`docs/BEAST_PHASE2_TERMUX_ANDROID_ACCEPTANCE.md`.
