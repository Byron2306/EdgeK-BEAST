# BEAST Phase 8 — Utility and Orchestration Plane

Phase 8 completes the remaining utility surfaces on BEAST Core Shell v2 without reviving the legacy multi-renderer stack.

## Transplanted pages

1. **BEAST Studio** — unified operator overview, phase progress, system topology, health, and quick launch.
2. **Provider Plane** — provider registry, local-first cascade, provider economist, route trials, compression, and KV cache controls.
3. **System Plane** — runtime health, resources, ports, processes, environment contract, and PREC lifecycle.
4. **IDE Controls** — typography, density, motion, atmosphere, audio, and governance defaults.
5. **Worktree Missions** — isolated branches, agent ownership, progress, tests, diff inspection, SourcePlan drafting, and closure.
6. **Release Forge** — release-readiness checks, pipeline gates, runbook export/verification, port contract, blockers, and rollback manifest.
7. **Chronicle** — searchable operational ledger, event inspector, receipt categories, and compiled insights.
8. **Compute Economy** — token displacement, crystal reuse, compression, KV-cache efficiency, provider mix, and cost avoidance.

## New runtime files

- `css/beast-phase8-utility-orchestration.css`
- `js/beast-utility-orchestration-bridge.js`
- `js/pages/beast-phase8-pages.js`
- `js/beast-phase8-app.js`

## Endpoint bridges

Phase 8 normalizes these available gateway contracts when present:

- `/edgek/providers/registry`
- `/edgek/providers/state`
- `/edgek/provider-economist/select`
- `/edgek/providers/compression/toggle`
- `/edgek/providers/kv-cache/clear`
- `/edgek/providers/nvidia-nim/live-smoke`
- `/edgek/ide/system-snapshot`
- `/edgek/runtime/state`
- `/edgek/runtime/sweep`
- `/edgek/prec/state`
- `/edgek/ide/ports`
- `/edgek/ide/ports/free`
- `/edgek/ide/system/kill`
- `/edgek/ide/worktree-mission/*`
- `/edgek/ide/release-readiness/check`
- `/edgek/ide/mission-runbook/export`
- `/edgek/ide/mission-runbook/verify`
- `/edgek/chronicle`
- `/edgek/insights/compile`
- `/edgek/commons-economy`
- `/edgek/crystal-reuse`
- `/edgek/compression/pipeline`
- `/edgek/kv-cache/state`

All pages include deterministic capture/demo normalization so an unavailable endpoint does not collapse the layout.

## Render ownership

Each new page has one renderer and one store subscription. Navigation disposes the previous page through the existing render scheduler. Phase 8 does not load `beast-phase7-app.js`, `app.js`, or the legacy OPCB renderers.

## Presentation refinements

- Readable 100% zoom scale and responsive page stacking.
- Bounded premium PNG icons in every primary action and major empty state.
- Neutral chrome surfaces with living green signal rather than permanent green paint.
- Purposeful matrix/grid atmosphere controlled from Settings.
- Dense tables own their own scroll regions; the document does not require horizontal scrolling.
- Worktree, release, and system mutations retain explicit operator confirmation paths.

## Acceptance boundary

Static syntax, reference, route-owner, duplicate-ID, and archive-integrity validation is included. Chromium navigation is blocked by the execution environment's administrator policy, so live Electron preload and gateway behavior must be accepted in the real BEAST desktop runtime.
