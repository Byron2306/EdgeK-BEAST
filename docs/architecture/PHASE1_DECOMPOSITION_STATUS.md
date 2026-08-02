# BEAST Phase 1 Decomposition Status

**Slice:** 1A through 1C  
**Date:** 18 July 2026  
**Status:** PASS

Latest closure note: see `docs/architecture/PHASE1C_AGENT_AND_HOST_BOUNDARIES.md`. Phase 1C adds the remaining safe bootstrap/security/IPC/diagnostics/menu/window/lifecycle/gateway/workspace host boundaries, Pair Programmer narration/profile modules, backend Action IR/context/event-envelope support, and real backend route-family registrars for agent sessions, system inspection, and worktree missions. The expanded verifier proves 21 direct desktop modules plus 4 renderer AI modules.

## Purpose

Begin breaking the three IDE orchestration monoliths into independently testable modules without changing route paths, IPC channel names, renderer public APIs, SourcePlan authority, or execution-target semantics.

## Extracted boundaries

### Electron main process

`desktop-ide/main.js` now composes:

- `main/build-identity.js`
- `main/runtime-paths.js`
- `main/window-state.js`
- `main/gateway-event-stream-host.js`
- `main/notebook-kernel-host.js`
- `main/session-hosts.js`

The packaged Electron build explicitly includes `main/**`.

### Pair Programmer renderer

`beast-ai-coding.js` now composes:

- `renderer/js/ai/beast-ai-transport.js`
- `renderer/js/ai/beast-ai-intent.js`

The public `window.BeastAICoding` API remains unchanged.

### Backend IDE facade

`app/routes/ide.py` now imports pure helpers from:

- `app/routes/ide_support/common.py`

The public `build_ide_router()` entry point and all existing route paths remain unchanged.

## Measured extraction

| Entrypoint | Before | After | Extracted |
|---|---:|---:|---:|
| `desktop-ide/main.js` | 2,030 | 1,831 | 199 |
| `beast-ai-coding.js` | 1,327 | 1,282 | 45 |
| `app/routes/ide.py` | 4,388 | 4,312 | 76 |
| **Total** | **7,745** | **7,425** | **320** |

This is deliberately a low-risk first cut. The goal is not to make the line count look pretty. The goal is to establish tested seams that allow deeper extraction without behavioural drift.

## Verification

- JavaScript syntax: passed
- Python compilation: passed
- New Phase 1 module-boundary verifier: passed
- New backend helper tests: 4 passed
- Enterprise runtime contract: passed
- Local parity foundation: 89/89
- Execution-target contract: 12 passed, 3 environment-gated skips, 0 failed

The parity verifier now reads the composed source graph rather than assuming all behaviour must remain inside `main.js` or `ide.py`.

## Invariants preserved

- No route paths changed.
- No IPC channels changed.
- No preload contract changed.
- No `window.BeastAICoding` method changed.
- No SourcePlan promotion rule changed.
- No direct workspace mutation was introduced.
- No local/SSH/container target semantics changed.

## Next decomposition slices

### 1B: Electron service plane

Extract workspace, Git, tasks, tests, local/remote terminal, Dev Container, extension, gateway, and protocol IPC registration into named service hosts. `main.js` should become bootstrap plus composition only.

### 1C: Backend route families

Introduce a shared `IdeRouteContext`, then move snapshot/search, system control, SourcePlan, agent session, terminal, and worktree routes into separate registrars. `app/routes/ide.py` remains a compatibility facade.

### 1D: Pair Programmer runtime

Extract state persistence, event reduction, context selection, approvals, run creation, verification, SourcePlan handoff, and presentation into dedicated modules while preserving the current external API.

## Phase 1 completion gate

Phase 1 is complete when the three entrypoints are composition roots, not implementation warehouses, and the existing parity, visual, execution-target, and agent proposal suites remain green.
