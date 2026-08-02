# BEAST Phase 6 Electron Acceptance Checklist

Run this checklist against the **full Phase 6 package** in the production BEAST Electron shell.

## Shell and routing

- [ ] Start BEAST with the live preload and gateway.
- [ ] Open Mission Map and verify exactly one page appears.
- [ ] Open Crystallization and verify exactly one page appears.
- [ ] Switch between Map, Crystallization, Models, Agents, and SourcePlan repeatedly.
- [ ] Confirm scroll position and keyboard focus do not jump because of a late second render.

## Pulsing hacker borders

- [ ] Card edge current travels smoothly without visible seams.
- [ ] Adjacent cards pulse at staggered intervals.
- [ ] Active/focused cards brighten without changing their dimensions.
- [ ] Amber and red cards retain their own tone.
- [ ] Reduced-motion mode removes movement while preserving visible borders.
- [ ] CPU/GPU usage remains reasonable during idle operation.

## Mission Map

- [ ] Live graph endpoint populates nodes and links.
- [ ] Search filters without rebuilding the entire page.
- [ ] Core, code, agent, store, external, and risk filters work.
- [ ] Zoom in/out and Fit Topology remain usable at 100–200% application zoom.
- [ ] Selecting a node updates the inspector and impact trace.
- [ ] Canvas edges stay aligned after resize, sidebar collapse, and context-rail changes.
- [ ] No horizontal document scrollbar appears.
- [ ] Large repositories remain responsive with the configured node/edge limits.

## Crystallization Chamber

- [ ] `/edgek/crystal-reuse` candidates appear and can be selected.
- [ ] Run Gates updates quality-gate states.
- [ ] Attest updates crystal-chain state.
- [ ] Checkpoint updates mission-lattice state.
- [ ] Commit Crystal creates or reports a governed durable artifact.
- [ ] Mascot changes to working, finished, and alert states correctly.
- [ ] Reactor motion stops under reduced-motion mode.
- [ ] The event ledger and committed-artifact list update without page replacement.

## Premium icons and cursors

- [ ] Assign Agent, refresh, pause, resume, sync, and cancel display PNG icons.
- [ ] Map and Crystal action icons are crisp at 100%, 125%, 150%, and 200% scaling.
- [ ] Claw, target, link, text, drag, blocked, busy, and resize cursors use correct hotspots.

## Failure behaviour

- [ ] Stop the gateway and refresh Map. A resilient local topology appears.
- [ ] Stop the gateway and refresh Crystal. The page retains a stable fallback state.
- [ ] Restore the gateway and refresh without restarting the renderer.
- [ ] No uncaught exceptions appear in DevTools.

## Acceptance record

Record:

- Electron version:
- Chromium version:
- Display scale:
- Gateway version:
- Workspace/repository:
- Map node/edge count:
- Crystal candidate count:
- Errors or screenshots:
