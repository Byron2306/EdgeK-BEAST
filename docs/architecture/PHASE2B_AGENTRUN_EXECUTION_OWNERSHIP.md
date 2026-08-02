# Phase 2B: Durable AgentRun Execution Ownership

**Date:** 18 July 2026  
**Status:** Implemented and verified  
**Predecessor:** Phase 2A Durable AgentRun Foundation

## Purpose

Phase 2A gave each Pair Programmer execution a durable identity and a hash-chained replay ledger, but the initiating GET SSE request still owned provider execution. Phase 2B separates execution from observation.

The new path is:

```text
POST /edgek/agent-runs
        ↓
create durable run and persist full execution request
        ↓
launch backend AgentRun worker
        ↓
worker drives the proven Pair Programmer adapter
        ↓
legacy events are projected into the durable ledger
        ↓
GET /edgek/agent-runs/{run_id}/events?follow=true
        ↓
any renderer or client replays by sequence
```

The renderer is now a subscriber, not the owner of provider life.

## New canonical component

```text
app/kernel/agents/run_worker.py
```

`AgentRunWorkerRegistry` owns live asyncio task handles only. It does not own durable business state. The SQLite AgentRun ledger remains authoritative and can recover after the registry is lost during process restart.

The registry provides:

- one active worker per `run_id`;
- duplicate-launch suppression;
- cancellation registration;
- process-local worker status;
- automatic handle cleanup after completion.

## POST-created execution

`POST /edgek/agent-runs` accepts `launch: true` and a persisted request object:

```json
{
  "session_id": "...",
  "objective": "...",
  "provider": "...",
  "model": "...",
  "launch": true,
  "request": {
    "transport": "durable_agent_run_v2",
    "prompt": "...",
    "context_files": ["..."],
    "simulate": false,
    "max_tokens": 16000,
    "context_max_chars_each": 50000,
    "max_repair_rounds": 3,
    "approval_timeout_seconds": 3600
  }
}
```

The prompt and context paths are no longer passed through the renderer's SSE URL.

## Compatibility worker

The Phase 2B worker uses an internal ASGI call to the existing Pair Programmer execution adapter:

```text
/edgek/ide/agent-sessions/{session_id}/run-events
```

This preserves the proven provider, Action IR, Quality Cascade, repair, evidence, and SourcePlan behaviour while moving lifecycle ownership to the durable run.

This adapter is explicitly transitional. Phase 2C will replace its direct provider/tool implementation with the provider-neutral model/tool loop.

## Replay projections

The AgentRun event endpoint supports:

```text
projection=canonical
projection=legacy
```

Canonical projection serves AgentRun-native clients. Legacy projection lets the existing Pair Programmer event handlers consume the durable event ledger without duplicating the old execution stream.

Both projections include the exact durable event sequence as the SSE `id` field.

## Renderer cursor and reconnect

Electron's gateway stream host now parses and forwards SSE `id` fields. The renderer persists:

```text
activeRunId
activeRunSequence
```

A renderer transport failure:

- closes only the local event subscription;
- preserves the durable run identity;
- preserves the latest sequence;
- marks the UI interrupted;
- does not send backend cancellation;
- reconnects from the stored sequence after restoration.

Operator Cancel remains explicit and invokes the backend cancellation route.

## Durable approval wait

The old four-second approval race has been removed.

The execution worker now waits against the durable approval row for a bounded policy interval, defaulting to one hour. During the wait:

- run state is `waiting_for_approval`;
- cancellation remains active;
- the renderer may disconnect and reconnect;
- approval or rejection is consumed by the same `run_id`;
- rejection continues within the original operator-selected scope;
- an expired optional approval continues within the original scope.

The approval decision is not replayed as a new capability after restart.

## Resume behaviour

After backend restart, active runs are safely paused by the Phase 2A runtime-instance claim.

`POST /edgek/agent-runs/{run_id}/resume` now:

1. clears stale cancellation intent;
2. transitions the run to scoping;
3. relaunches the persisted execution request;
4. reuses existing durable approvals;
5. appends new events to the existing hash chain.

This is deterministic restart from the pre-dispatch request. It does not claim serialization of an in-flight provider coroutine.

## Governance preserved

Phase 2B does not change:

- SourcePlan as the promotion boundary;
- human approval for workspace mutation;
- existing exact-content validation;
- existing provider and model routing;
- worktree routes;
- capability separation;
- direct workspace mutation prohibition.

## Verification

The implementation passed:

- Phase 2A verifier: 16/16;
- Phase 2B verifier: 18/18;
- focused AgentRun tests: 10 passed;
- Python compilation: 381 files, zero failures;
- JavaScript syntax: 109 files, zero failures;
- local parity foundation: 89/89;
- enterprise runtime contract: PASS;
- execution targets: 12 passed, 3 environment-gated skips, 0 failures;
- desktop static smoke: 24/24;
- desktop launch smoke: 9/9;
- visual acceptance: 110/110.

Two broad app-level tests were not collected in the extracted inspection tree because `.byron/services.yaml` was not supplied. No replacement machine-local registry was fabricated.

## Deliberate Phase 2B limits

Phase 2B does not yet claim:

- provider-neutral model-selected tool calls;
- a typed tool registry as the sole execution path;
- worktree-first mutations for every Agent run;
- iterative model → tool → observation → repair cycles;
- serialized provider continuation after process restart;
- durable approval cards replacing the current renderer confirmation dialog;
- SourcePlan synthesis from a final verified worktree diff.

Those form the Phase 2C and Phase 2D program.
