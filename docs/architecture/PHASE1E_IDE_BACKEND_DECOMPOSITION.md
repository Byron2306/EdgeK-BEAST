# Phase 1E: IDE Backend Route Decomposition

**Date:** 18 July 2026  
**Status:** PASS  
**Scope:** `app/routes/ide.py`

## Outcome

The IDE backend facade has been converted from a 4,312-line closure into a 40-line composition root with an explicit dependency capsule and nine route-family modules.

The public API is unchanged:

- 52 routes before;
- 52 routes after;
- identical route order;
- identical HTTP methods;
- identical URL templates;
- identical FastAPI handler names.

## New structure

```text
app/routes/
├── ide.py                       # 40-line composition root
├── ide_context.py               # shared state and helper behaviour
├── ide_support/
│   └── common.py                # previously extracted pure utilities
└── ide_routes/
    ├── __init__.py
    ├── overview.py              # snapshot, events, context and code intelligence
    ├── mission.py               # timeline, lifecycle, runbooks, handoff and readiness
    ├── system.py                # process, port, environment and terminal surfaces
    ├── learning.py              # verified learning queue proposal
    ├── actions.py               # action manifest and governed action planning
    ├── agent_sessions.py        # session CRUD, grants, pause/resume and SourcePlan helpers
    ├── agent_run_stream.py      # current provider stream and repair loop seam
    ├── editor_sourceplans.py    # editor and selection SourcePlan drafting
    └── worktrees.py             # mission worktree lifecycle
```

## Canonical composition

`build_ide_router()` now performs only composition:

1. create `APIRouter`;
2. create `IdeRouteContext`;
3. register route families in the original order;
4. expose the mission lifecycle handler to the learning registrar;
5. return the router.

No route implementation remains in `ide.py`.

## Explicit route context

`IdeRouteContext` replaces the implicit lexical closure that formerly surrounded every handler. It owns:

- the resolved fallback workspace root;
- the Code Cortex router dependency;
- shared helper behaviour;
- small cross-family handler references required for behaviour compatibility.

This makes dependencies visible and gives Phase 2 a stable injection point for a durable AgentRunEngine.

## Agent runtime seam

The existing 1,100-line live provider/tool/repair stream has been isolated in:

```text
app/routes/ide_routes/agent_run_stream.py
```

This is intentional. Phase 1 preserves behaviour; Phase 2 replaces this seam with a canonical durable runtime. Session CRUD and SourcePlan helper routes no longer need to be reopened during that transplant.

## Proof-harness correction

The desktop parity and enterprise verifiers now inspect the composed IDE route graph:

- `app/routes/ide.py`;
- `app/routes/ide_context.py`;
- `app/routes/ide_support/*.py`;
- `app/routes/ide_routes/*.py`.

They no longer reward keeping all backend behaviour in one file.

## Verification

| Check | Result |
|---|---:|
| Backend decomposition contract | 11 / 11 |
| Public IDE routes | 52 / 52 unchanged |
| Focused Python regression tests | 25 passed |
| Local parity foundation | 89 / 89 |
| Enterprise runtime contract | PASS |
| Execution-target verification | 12 passed, 3 environment skips, 0 failed |
| Desktop static smoke | 24 / 24 |
| Desktop launch smoke | 9 / 9 |
| Visual acceptance | 110 / 110 |
| Full `app/` Python compilation | PASS |

## Behavioural comparison

A selected live read-path comparison was run against the original monolith and the decomposed router. Normalized responses matched for:

- symbol outline;
- symbol search;
- text search;
- mission route;
- action manifest;
- agent-session registry;
- worktree registry.

## Next boundary

Phase 2 should not further enlarge route modules. It should extract the provider/tool loop from `agent_run_stream.py` into:

```text
app/kernel/agents/run_engine.py
```

The route then becomes an adapter over durable run creation and sequenced event replay.
