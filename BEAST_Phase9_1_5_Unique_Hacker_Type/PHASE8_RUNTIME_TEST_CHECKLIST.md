# Phase 8 Runtime Acceptance Checklist

## Startup

- [ ] Fully restart Electron after installing Phase 8.
- [ ] Confirm the sidebar shows Studio, Providers, System, Worktrees, Deploy, Chronicle, Compute Economy, and Settings.
- [ ] Confirm only `beast-phase8-app.js` owns shell boot.
- [ ] Confirm one child exists under `#beastPageOutlet` after every navigation.

## Provider Plane

- [ ] Provider registry loads or degrades to a clearly labelled local snapshot.
- [ ] Selecting a route updates the selected and active provider correctly.
- [ ] Compression toggle persists.
- [ ] KV-cache clear creates a ledger event.
- [ ] NVIDIA NIM smoke test returns a receipt or a legible failure.

## System Plane

- [ ] CPU, memory, disk, network, ports, and processes populate.
- [ ] PREC stage and health populate.
- [ ] Runtime Sweep completes without replacing the page DOM.
- [ ] Free-port and stop-process actions require explicit operator confirmation.

## Worktree Missions

- [ ] Existing missions populate from the live snapshot.
- [ ] Create, test, diff, SourcePlan, and close actions call the correct contracts.
- [ ] Selected mission and scroll position remain stable after live refresh.

## Release Forge

- [ ] Readiness score and gates populate.
- [ ] Port conflicts are visible.
- [ ] Runbook export and verification return receipts.
- [ ] Rollback/manifest details remain readable at 100% zoom.

## Chronicle

- [ ] Ledger events load and can be searched and filtered.
- [ ] Selecting an event updates only the inspector.
- [ ] Insight compilation produces findings or a legible endpoint failure.

## Compute Economy

- [ ] Token savings, reuse, compression, cache and provider mix populate.
- [ ] No bar or icon exceeds its container.
- [ ] Offline/demo values are clearly distinguished from live data.

## Settings

- [ ] Typography scale, density, motion, atmosphere, audio and glow persist after restart.
- [ ] Reduced-motion system preference disables continuous animations.
- [ ] Quiet atmosphere removes matrix and grid layers.
- [ ] Governance defaults remain enabled unless explicitly changed.

## Responsive acceptance

Test every Phase 8 page at:

- [ ] 1920×1080 at 100%
- [ ] 1600×900 at 100%
- [ ] 1366×768 at 100%
- [ ] 1920×1080 at 125%
- [ ] 1920×1080 at 150%

For each size verify:

- [ ] no document horizontal scrollbar
- [ ] no oversized injected icons
- [ ] all operational text remains legible
- [ ] the right rail and command dock remain reachable
- [ ] only one page renderer is mounted
