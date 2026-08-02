# Phase 2A: Durable AgentRun Foundation

**Date:** 18 July 2026  
**Status:** Implemented and compatibility-wrapped

## Purpose

Phase 2A gives every Pair Programmer execution a durable identity and a replayable event history without replacing the existing provider, validation, repair, or SourcePlan implementation.

The current `agent_run_stream.py` remains the execution compatibility adapter. `AgentRunEngine` now owns durable run identity, lifecycle projection, event sequencing, approval records, checkpoints, cancellation intent, and replay.

## New runtime modules

```text
app/kernel/agents/
├── run_state.py
├── run_events.py
├── run_cancel.py
├── run_store.py
└── run_engine.py
```

## Durable storage

Each workspace receives:

```text
.beast/agent_runs/agent_runs.sqlite3
```

The database uses SQLite WAL, `synchronous=FULL`, transactional sequence allocation, and an application-level SHA-256 event chain.

Tables:

- `agent_runs`
- `agent_run_events`
- `agent_run_approvals`
- `agent_run_meta`

## Compatibility path

```text
Pair Programmer GET stream
        ↓
agent_run_stream.py
        ↓ creates run before context loading
AgentRunEngine
        ↓
legacy SSE event + canonical durable event
        ↓
current renderer and replay API
```

The old SSE event names remain unchanged for the existing renderer. Each frame is additionally projected to a canonical event such as:

- `agent.run.registered`
- `agent.model.delta`
- `agent.tool.started`
- `agent.tool.completed`
- `agent.approval.requested`
- `agent.verification.completed`
- `agent.sourceplan.ready`
- `agent.run.completed`

## New API

```text
POST /edgek/agent-runs
GET  /edgek/agent-runs
GET  /edgek/agent-runs/{run_id}
GET  /edgek/agent-runs/{run_id}/events
POST /edgek/agent-runs/{run_id}/cancel
POST /edgek/agent-runs/{run_id}/resume
GET  /edgek/agent-runs/{run_id}/verify
GET  /edgek/agent-runs/{run_id}/approvals
POST /edgek/agent-runs/{run_id}/approvals/{approval_id}
```

The events endpoint supports JSON replay and SSE follow mode with sequence cursors.

## Cancellation

The renderer captures `run_id` from the earliest `agent_run_registered` event. Its Cancel action now:

1. posts a durable cancellation request;
2. marks the run `cancelling`;
3. signals the in-process cancellation registry;
4. cancels registered async provider/tool work;
5. closes the local stream;
6. records the final cancellation event when execution unwinds.

The older session-cancel endpoint also cancels active durable runs for that session.

## Approval durability

Capability requests are stored by `(run_id, approval_id)`. The renderer persists both approvals and rejections through the AgentRun API. Approved optional capabilities are projected back into the existing session grant store so the current provider loop can use them in the same turn.

SourcePlan approval remains entirely separate.

## Sensorium relationship

AgentRunStore is the authoritative replay ledger for coding runs. AgentRunEngine mirrors metadata-only events into the Sensorium journal on a best-effort basis. Source text, prompts, and token content are not duplicated into the Sensorium mirror.

## Honest boundaries

Phase 2A does not yet claim the complete AgentRunEngine described in the master plan.

Still remaining:

- POST-created execution rather than GET query transport;
- mandatory pause/resume approval interruptions;
- provider-neutral model/tool turn orchestration;
- process-tree and remote-target execution handles;
- enforced budgets and stagnation detection;
- worktree-first iterative edit, test, diagnose, and repair;
- reconnecting renderer timeline and automatic replay;
- SourcePlan generation from a verified worktree diff.

Those are Phase 2B and Phase 2C rather than hidden claims inside this foundation.
