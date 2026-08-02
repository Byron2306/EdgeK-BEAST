# BEAST Phase 1B: Desktop Service Decomposition

**Date:** 18 July 2026  
**Status:** PASS  
**Scope:** Behaviour-preserving extraction of the Electron workspace, Git, task/test, notebook execution, execution-target, terminal, Dev Container, and extension-host service families.

## Objective

Continue Phase 1 without changing public behaviour. The Electron entrypoint must become a composition root rather than the implementation home for every desktop capability.

This slice preserves:

- every existing Electron IPC channel;
- every preload method;
- local, SSH, and Dev Container execution semantics;
- task, test, terminal, Git, notebook, and extension behaviour;
- gateway and SourcePlan authority boundaries;
- the current renderer contract.

## New service boundaries

`desktop-ide/main.js` now composes the following Phase 1B modules:

| Module | Canonical responsibility |
|---|---|
| `main/workspace-paths.js` | Workspace path containment and task working-directory validation |
| `main/process-host.js` | Bounded child-process execution with timeout and output limits |
| `main/workspace-file-host.js` | File listing, reading, search, replace preview/apply, and bounded file mutation |
| `main/git-host.js` | Git status, diff, hunk, conflict, branch, history, remote, and operation contracts |
| `main/task-test-host.js` | Task parsing/execution, test discovery/execution, problem matching, and durable task sessions |
| `main/notebook-execution-host.js` | One-shot governed notebook-cell execution |
| `main/execution-target-host.js` | Local/SSH/container target identity, remote files, terminals, forwards, and Dev Container lifecycle |
| `main/extension-host.js` | Mediated extension discovery, grants, deployment, execution, enablement, and removal |

`main/execution-target-host.js` owns the transitive composition of `main/session-hosts.js`, so terminal and SSH-forward process ownership no longer leaks back into `main.js`.

## Composition order

```text
workspace path tools
        ↓
bounded process host
        ↓
workspace file host
        ↓
Git host
        ↓
task/test host ───────────────┐
        ↓                     │
execution-target host ◄───────┘
        ↓
notebook execution host
        ↓
extension host
        ↓
Electron IPC and window bootstrap
```

The task/test host receives the execution-target host through a lazy accessor. This breaks the former circular dependency without duplicating target state.

## Measured extraction

| Metric | Phase 1A | Phase 1B | Change |
|---|---:|---:|---:|
| `desktop-ide/main.js` lines | 1,831 | 1,350 | **-481** |
| `desktop-ide/main.js` bytes | 160,491 | 66,194 | **-94,297** |
| Focused desktop modules | 6 direct + 1 transitive | 13 direct + 1 transitive | **+7 direct modules** |
| New Phase 1B modules | 0 | 8 | **+8** |

From the original pre-Phase-1 entrypoint:

- `main.js` moved from 2,030 to 1,350 lines;
- 680 lines have left the entrypoint;
- the largest compressed service implementations are no longer embedded in the bootstrap.

Line count is not the primary goal. The important result is that each service can now be instantiated and exercised without launching Electron.

## Proof-suite correction

Two old verifiers still assumed that implementation functions must be sliced out of `main.js` as raw source text.

Phase 1B replaces that brittle pattern:

- the Git functional lifecycle now imports and exercises `createGitHost()` directly;
- execution-target verification reads the composed module graph;
- the module-boundary verifier instantiates all new factories in a disposable workspace;
- static tests now fail if service classes or implementation functions leak back into `main.js`.

This prevents the proof system from rewarding monolithic code structure.

## Verification results

- Phase 1 module-boundary suite: **PASS**
- New direct desktop modules: **13**
- Transitive session module: **1**
- `main.js` decomposition ceiling: **1,350 lines**, below the 1,500-line Phase 1B gate
- Local parity foundation: **89/89**
- Execution-target parity: **12 passed, 3 environment-gated skips, 0 failed**
- Enterprise runtime contract: **PASS**
- Visual acceptance: **110 scenarios, PASS**
- JavaScript syntax: **88 files checked, PASS**
- Focused Python regression tests: **10 passed**

The three execution-target skips remain live external-environment checks requiring configured SSH and container fixtures.

## Behavioural invariants

- No IPC channel was renamed or removed.
- No preload method changed.
- No renderer API changed.
- No route path changed.
- No SourcePlan rule changed.
- No target silently falls back to local execution.
- Workspace traversal excludes `.beast-*` installer backups so proof and search runs cannot recursively index repository copies.
- Agent and extension writes did not receive broader authority.
- Existing Git, task, test, terminal, remote, container, notebook, and extension fixtures remain green.

## Remaining `main.js` responsibilities

The entrypoint still owns several large families:

1. workspace-root persistence;
2. local readiness and diagnostic snapshots;
3. gateway health, process lifecycle, reset, and discovery;
4. menu and window creation;
5. IPC registration;
6. application startup and shutdown.

These are the targets for Phase 1C.

## Phase 1C target

Extract:

```text
main/workspace-state-host.js
main/diagnostics-host.js
main/gateway-host.js
main/window-host.js
main/ipc-registry.js
main/application-lifecycle.js
```

The completion target for the Electron side is a `main.js` that only:

1. loads identity and paths;
2. creates service instances;
3. registers IPC;
4. creates the first window;
5. delegates shutdown.

After that, Phase 1 moves to the backend `app/routes/ide.py` route-family decomposition and the Pair Programmer renderer runtime.
