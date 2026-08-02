# Phase 1C: Electron Composition Root

**Date:** 2026-07-18  
**Status:** Implemented and verified  
**Scope:** Complete the Electron-main decomposition started in Phase 1A and Phase 1B without changing public IPC, preload, route, workspace, target, Git, SourcePlan, or extension contracts.

## Outcome

`desktop-ide/main.js` is now a composition root rather than the owner of desktop business logic.

| Stage | `main.js` lines |
|---|---:|
| Before Phase 1 | 2,030 |
| After Phase 1A | 1,831 |
| After Phase 1B | 1,350 |
| After Phase 1C | **155** |

The entrypoint now performs six jobs:

1. Load the build identity.
2. Resolve the BEAST repository and packaged resources.
3. Construct desktop services.
4. Connect the few circular dependencies through getter functions.
5. Register IPC handlers.
6. Register application lifecycle hooks.

## New modules

### `workspace-state-host.js`

Owns:

- active workspace root;
- multi-root workspace identities;
- folder persistence and restoration;
- `@root-id/path` references;
- root-aware file aggregation;
- registered-root resolution for IPC operations.

### `desktop-diagnostics-host.js`

Owns:

- local release-readiness inspection;
- desktop smoke invocation;
- syntax checks;
- local tooling snapshots;
- system-inspector invocation;
- BEAST Python discovery.

The readiness inspector reads the composed Electron module graph rather than assuming all implementation remains in `main.js`.

### `gateway-host.js`

Owns:

- service-registry gateway discovery;
- gateway request transport;
- event-stream host lifecycle;
- health and capability probes;
- compatible-port discovery;
- bounded process startup and shutdown;
- runtime-stack reset;
- local IDE fallback;
- gateway logs and status recovery.

Gateway state is private to this host. Consumers receive methods and immutable snapshots instead of mutating process-global variables.

### `window-host.js`

Owns:

- the application-window registry;
- focused/main window identity;
- menu creation;
- window-state restoration;
- window-state persistence;
- renderer loading;
- desktop identity handoff;
- additional workspace windows.

This extraction also corrected a dormant ownership defect: the former entrypoint referenced `DEFAULT_WINDOW_BOUNDS` and `windowStateWriteTimer` after those had moved into `window-state.js`. The new host uses the state store's exported defaults and persistence methods directly.

### `ipc-registry.js`

Owns all `beast:*` desktop IPC handler registration.

It is an adapter only. Operations are delegated to:

- workspace state;
- workspace files;
- Git;
- tasks and tests;
- execution targets;
- terminals and forwards;
- notebooks;
- protocol compatibility;
- extensions;
- diagnostics;
- gateway control;
- window control.

The public channel names are unchanged.

### `application-lifecycle.js`

Owns:

- `app.whenReady()`;
- window-state initialization;
- workspace restoration;
- initial window creation;
- bounded shutdown of all managed services;
- macOS activation behaviour.

## Compatibility guarantees

Phase 1C intentionally preserves:

- every preload method;
- every existing `beast:*` IPC channel;
- renderer-facing payload shapes;
- active workspace and multi-root semantics;
- local, SSH, and Dev Container target identities;
- Git and task/test contracts;
- extension grants and execution mediation;
- SourcePlan authority and promotion boundaries;
- gateway fallback and compatible-port behaviour.

## Verification modernization

Static verifiers now inspect the composed `main/` module graph. They no longer reward implementation for remaining inside one monolithic source file.

The Phase 1 boundary verifier additionally:

- instantiates the new workspace-state factory;
- instantiates the gateway host without opening a listener;
- verifies window-menu composition;
- verifies diagnostics construction;
- registers and counts the full IPC surface;
- verifies lifecycle hook registration;
- asserts that `main.js` contains no direct `ipcMain.handle()` calls;
- enforces a 240-line ceiling on the composition root.

## Current remaining concentration

The Electron entrypoint is complete as a composition root. The largest focused desktop module is now `gateway-host.js` at approximately 669 lines. It is cohesive enough for Phase 1, but can later be divided into probe, supervisor, request, and runtime-reset services during gateway reliability work.

The next primary Phase 1 target is the backend `app/routes/ide.py` monolith.
