# BEAST Phase 1C: Agent and Host Boundary Closure

**Date:** 18 July 2026  
**Status:** PASS  
**Scope:** Behaviour-preserving extraction of the remaining safe Phase 1 seams after the Phase 1A/1B patch bundles.

## Objective

Finish the rest of the practical Phase 1 decomposition without changing public contracts. This slice keeps the IDE operational while moving gateway registry parsing, workspace-root normalization, Pair Programmer narration/profile logic, and IDE event formatting into named modules.

## New boundaries

### Electron main process

`desktop-ide/main.js` now additionally composes:

- `main/bootstrap.js` for BrowserWindow option construction;
- `main/security-policy.js` for renderer web-preferences invariants;
- `main/gateway-host.js` for local service-registry parsing and gateway/port resolution;
- `main/workspace-host.js` for workspace folder state-path and root normalization contracts;
- `main/ipc-registry.js` for duplicate-safe IPC channel registration;
- `main/diagnostics-host.js` for desktop script probes used by readiness snapshots;
- `main/menu-host.js` for application menu construction;
- `main/window-host.js` for BrowserWindow creation, renderer load, window-state hooks, and initial workspace notifications;
- `main/application-lifecycle.js` for Electron ready/window-all-closed/activate registration.

The entrypoint no longer owns the gateway service-registry parser, workspace-root normalization implementation, renderer security option construction, raw IPC channel registration, desktop diagnostic script runner, menu template, BrowserWindow construction flow, or Electron lifecycle registration.

### Pair Programmer renderer

`beast-ai-coding.js` now additionally composes:

- `renderer/js/ai/beast-ai-narration.js` for first-person turn narration and terminal run summaries;
- `renderer/js/ai/beast-ai-profile.js` for Ask/Edit/Agent intent profiling, analysis-run detection, initial live turns, and verification progress scaffolding.

The public `window.BeastAICoding` API remains unchanged.

### Backend IDE facade

`app/routes/ide.py` now additionally imports:

- `app/routes/ide_support/action_ir.py` for Action IR retry prompt construction, anchor hints, and incomplete-function replacement rejection;
- `app/routes/ide_support/agent_session_routes.py` for agent-session CRUD, capability grant, conductor dispatch listing, SourcePlan draft, Action IR SourcePlan, and isolated verification route registration;
- `app/routes/ide_support/context.py` for the shared `IdeRouteContext` and root resolver;
- `app/routes/ide_support/events.py` for the canonical BEAST IDE SSE event envelope.
- `app/routes/ide_support/system_routes.py` for read-only system inspection route registration;
- `app/routes/ide_support/worktree_routes.py` for isolated worktree mission route registration.

All route paths and the `build_ide_router()` compatibility entry point remain unchanged.

## Measured result

| Entrypoint | Phase 1B | Phase 1C | Change |
|---|---:|---:|---:|
| `desktop-ide/main.js` | 1,350 | 1,254 | -96 |
| `beast-ai-coding.js` | 1,282 | 1,160 | -122 |
| `app/routes/ide.py` | 4,312 | 3,966 | -346 |

The important win is not raw line count; it is that the agent cockpit’s human-readable turn language and prompt-mode profiling are now independently loadable and testable.

## Verification

- Phase 1 module-boundary suite: **PASS**
- Direct desktop modules: **21**
- Renderer AI modules: **4**
- `main.js` decomposition ceiling: **1,254 lines**, below the 1,500-line gate
- Local parity foundation: **89/89**
- Execution-target parity: **12 passed, 3 environment-gated skips, 0 failed**
- Focused backend/release tests: **15 passed**
- Phase 0 release contract: **PASS**
- JavaScript/Python syntax checks: **PASS**
- Diff whitespace hygiene: **PASS**

## Invariants preserved

- No route path changed.
- No IPC channel changed.
- No preload contract changed.
- No renderer public API changed.
- No SourcePlan authority rule changed.
- No execution-target semantics changed.
- No workspace mutation authority was broadened.

## Remaining deeper Phase 1 work

The remaining decomposition is larger and should be handled as follow-up slices:

1. additional route-family registrars for SourcePlan, terminal, mission-runbook, and the remaining agent run-events stream;
2. window/menu/application lifecycle extraction from `desktop-ide/main.js`;
3. Pair Programmer event reduction, persistence, run creation, and SourcePlan handoff modules.

Those are intentionally not bundled into this slice because they are broader behavioral surfaces.
