# OPCB Phase 4 Asset Pack

Assets for the next BEAST Studio pages:

1. Models
2. Agents

## Contents

```text
assets/svg/
  models-route.svg
  fallback-ladder.svg
  local-model.svg
  runtime-ready.svg
  hardware-chip.svg
  gpu-core.svg
  cpu-stack.svg
  benchmark-bars.svg
  policy-route.svg
  provider-gateway.svg
  route-test.svg
  model-rack.svg
  route-explain.svg

  agents-squad.svg
  agent-planner.svg
  agent-verifier.svg
  agent-graph.svg
  agent-profiler.svg
  agent-patch.svg
  agent-memory.svg
  tool-binding.svg
  handoff-queue.svg
  activity-pulse.svg
  permissions-agent.svg
  agent-online.svg
  task-stream.svg

  models-page-bg.svg
  agents-page-bg.svg
  cube-pulse-models.svg
  cube-pulse-agents.svg
  mascot-models.svg
  mascot-agents.svg
  mascot-assign.svg

assets/css/opcb-phase4-assets.css
assets/js/opcb-phase4-assets.js
preview.html
manifest.json
```

## Install

Copy the `assets` folder into your UI root, then add after earlier phase assets:

```html
<link rel="stylesheet" href="assets/css/opcb-phase4-assets.css">
<script src="assets/js/opcb-phase4-assets.js"></script>
```

## Quick use

```js
opcbSetPageArt('models');
opcbSetPageArt('agents');

opcbPhase4Icon('modelsRoute');
opcbPhase4Icon('agentsSquad');

opcbPhase4Pulse('models');
opcbPhase4Pulse('agents');

opcbSetPhase4MascotState('models');
opcbSetPhase4MascotState('agents');
opcbSetPhase4MascotState('assign');
```

## Suggested mapping

Models:
- `models-route.svg` for active route
- `fallback-ladder.svg` for fallback ladder
- `local-model.svg`, `model-rack.svg` for local models list
- `runtime-ready.svg` for runtime state
- `hardware-chip.svg`, `gpu-core.svg`, `cpu-stack.svg` for hardware panel
- `benchmark-bars.svg`, `route-test.svg`, `route-explain.svg` for test/benchmark cards

Agents:
- `agents-squad.svg` for page hero
- agent role icons for planner, verifier, graph analyst, profiler, patch, memory
- `tool-binding.svg` for bound tools
- `handoff-queue.svg` for handoff panel
- `activity-pulse.svg` for agent activity
- `permissions-agent.svg` and `agent-online.svg` for permissions/online state
- `task-stream.svg` for live task queue
