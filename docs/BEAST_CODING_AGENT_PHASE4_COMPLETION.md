# BEAST Coding Agent Phase 4 — Completion Record

**Status:** PASS  
**Phase:** 4 — Durable approval and autonomy controls  
**Implementation head:** `099dac9e60e678ddd18e60ea7b334716b99b0b37`  
**Base Phase 3 head:** `712b0b3d8720b2e0ad13a45e338f97d9b5194e63`

## Exit result

The Phase 4 exit gate defined in
`4.0/BEAST_Next_Level_Upgrade_Master_Plan_2026-07-18.md` is satisfied.

A live AgentRun approval now survives the durable approval stores and backend
restart boundary, resumes only the exact suspended tool step, and consumes one
request-bound single-use capability without widening future authority.

The unified Phase 4 completion compiler emitted:

```text
phase4_exit_met: true
```

All completion gates passed:

```text
canonical_phase4_subsystem: true
live_durable_approval_and_restart: true
permission_modes_and_bounded_autonomy: true
sensitive_and_external_content_controls: true
phase3_behavior_preserved: true
```

## 1. Durable live AgentRun approvals

The coding-agent planner now uses the canonical Phase 4 approval subsystem
rather than a separate transient approval dialect.

For a governed step it persists:

- run and exact plan step;
- tool id and version;
- exact arguments;
- execution target;
- workspace identity;
- risk classification;
- permission mode;
- budget impact;
- expiry and evidence policy;
- request, envelope and card digests.

The compatibility `agent_run_approvals` row remains a status mirror for older
surfaces. It is not the source of Phase 4 execution authority.

## 2. Request-bound single-use capability

An approved live step is converted through the canonical chain:

```text
approval request
  -> durable approval card
  -> operator decision
  -> bounded scope grant
  -> scope match
  -> request-bound capability
  -> durable capability consumption receipt
  -> exact suspended tool call
```

The tool runtime verifies the approval id, tool id/version, execution target,
canonical arguments, request digest and durable consumption receipt before the
handler is allowed to execute.

After execution, the resume checkpoint becomes either
`CONSUMED_COMPLETED` or `CONSUMED_FAILED`. The same ONCE capability cannot
authorize the call again.

## 3. Restart-safe exact-step resume

The Phase 4 runtime accepts a restart-recovered AgentRun only when it is
`PAUSED` specifically because of `runtime_restarted; resume required`.

The persisted suspended step must still match the capability's:

- run id;
- step id;
- approval id;
- tool id/version;
- request digest;
- call identity digest;
- workspace id;
- execution target.

The capability then resumes into `EXECUTING_TOOL`, not broad planning
authority.

## 4. Permission modes

The live tool runtime now evaluates the Phase 4 permission-mode engine.

### REVIEW

Configured actions are lifted into durable operator approval rather than being
silently executed.

### GUIDED

Ordinary read-only actions remain automatic. Isolated mutation, consequential
execution and sensitive access remain approval-gated.

### BOUNDED_AUTONOMY

Scoped worktree actions may be auto-authorized only while preserving:

- isolated worktree execution;
- explicit file allowlists;
- explicit command allowlists;
- Phase 3 turn/tool/mutation/cost budgets;
- network restrictions;
- evidence generation;
- SourcePlan promotion approval.

Out-of-scope files or commands fail closed.

### OBSERVE_ONLY

Mutation is denied.

### LOCKED

The agent is denied execution authority.

## 5. Sensitive-data controls

Sensitive resources such as `.env` are classified before tool execution.

Live acceptance proves:

- sensitive access requires explicit one-use approval;
- the sensitive classification digest is bound into the approval request;
- classification is rechecked at execution time;
- sensitive tool arguments are redacted from the AgentRun log path;
- sensitive tool results are redacted before model-visible observation;
- raw secret values are not persisted in the AgentRun event chain;
- raw sensitive persistence remains prohibited.

External providers receive only redacted sensitive context.

## 6. External-content admission

Tool output declaring external provenance is treated as untrusted external
content.

The live tool runtime separates fetch authorization from model-context
admission:

```text
external result
  -> provenance validation
  -> prompt-injection risk classification
  -> low-risk sanitized admission
       OR
     medium/high/critical quarantine
  -> provenance-labelled model observation
```

High-risk prompt-injection content is quarantined with zero model-visible
content. External content cannot alter policy or widen authority.

## 7. Authority boundaries preserved

Phase 4 does not grant model authority to:

- promote or apply a SourcePlan;
- push remote changes;
- publish packages or releases;
- mutate global approval policy;
- disable evidence generation;
- erase audit history;
- reuse a consumed ONCE capability.

Phase 3 least-authority, budget, stagnation and verification controls remain in
force underneath the Phase 4 capability layer.

## 8. Regression closure

On the Phase 4 implementation head, the following all completed successfully:

- BEAST Phase 4 Existing Approval Audit
- BEAST Phase 4 Completion Gate
- BEAST Phase 3 Completion Gate
- BEAST Phase 3 Least Authority
- Agentic Loop Endurance
- BEAST Phase 2 Desktop Ingress Acceptance
- BEAST Phase 2 Completion Gate

The Phase 4 implementation also caught and corrected:

1. an import cycle between AgentRun tool runtime and the approval capability
   runtime by moving the Phase 4 bridge to a lazy runtime dependency;
2. a synchronous test topology that could not concurrently submit an operator
   decision while the planner was waiting;
3. missing live binding between the previously standalone Phase 4 subsystem and
   the coding-agent planner/tool runtime;
4. the distinction between worktree bootstrap and already-isolated mutation;
5. live response admission for external prompt-injection content.

## Closure evidence

Unified Phase 4 completion workflow run:

```text
workflow_run: 35302635971
artifact: beast-phase4-completion-receipt
artifact_id: 10530303878
digest: sha256:4f7f734425410d3ab43644568d016efd2b35c206402a66d4d4272d6317368e98
```

The compiler emitted:

```json
{
  "phase4_exit_met": true,
  "gates": {
    "canonical_phase4_subsystem": true,
    "live_durable_approval_and_restart": true,
    "permission_modes_and_bounded_autonomy": true,
    "sensitive_and_external_content_controls": true,
    "phase3_behavior_preserved": true
  }
}
```

Additional same-head evidence:

```text
Phase 4 audit:             35302635970  PASS
Phase 3 completion:        35302637472  PASS
Agentic loop endurance:    35302637447  PASS
Phase 2 desktop ingress:   35302637462  PASS
Phase 2 completion:        35302637458  PASS
```

## Evidence boundary

This record proves the hosted Linux Phase 4 acceptance matrix.

The native Android/Termux evidence remains Phase 2 evidence. The complete Phase
4 approval/restart/permission/sensitive-data gauntlet has not yet been rerun on
Android/Termux and is not claimed here.

Phase 4 completion is an execution-governance proof. It does not itself grant
or imply SourcePlan promotion authority.
