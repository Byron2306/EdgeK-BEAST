# OPCB Phase 5 Asset Pack

Assets for the next BEAST Studio pages:

1. Map
2. Memory

## Contents

```text
assets/svg/
  map-canvas.svg
  graph-node-entry.svg
  graph-node-parser.svg
  graph-node-detector.svg
  graph-node-validator.svg
  graph-node-store.svg
  graph-node-agent.svg
  graph-node-test.svg
  graph-node-docs.svg
  graph-node-config.svg
  graph-node-external.svg
  orphan-node.svg
  edge-calls.svg
  edge-depends.svg
  edge-produces.svg
  map-search.svg
  map-filter.svg
  map-health.svg
  dependency-impact.svg
  path-focus.svg

  memory-observatory.svg
  memory-archive.svg
  recall-query.svg
  recall-health.svg
  residue-quality.svg
  skill-tree.svg
  memory-freshness.svg
  compaction-queue.svg
  memory-graph.svg
  reuse-suggestion.svg
  decay-meter.svg
  retention-lock.svg
  promote-skill.svg
  memory-event.svg
  source-linked.svg

  map-graph-hero.svg
  memory-cube-hero.svg
  map-page-bg.svg
  memory-page-bg.svg
  cube-pulse-map.svg
  cube-pulse-memory.svg
  mascot-map.svg
  mascot-memory.svg
  mascot-recall.svg

assets/css/opcb-phase5-assets.css
assets/js/opcb-phase5-assets.js
preview.html
manifest.json
```

## Install

Copy the `assets` folder into your UI root, then add after earlier phase assets:

```html
<link rel="stylesheet" href="assets/css/opcb-phase5-assets.css">
<script src="assets/js/opcb-phase5-assets.js"></script>
```

## Quick use

```js
opcbSetPageArt('map');
opcbSetPageArt('memory');

opcbPhase5Icon('mapCanvas');
opcbPhase5Icon('memoryObservatory');

opcbNodeIconByType('parser');
opcbNodeIconByType('external');

opcbPhase5Hero('map');
opcbPhase5Hero('memory');

opcbPhase5Pulse('map');
opcbPhase5Pulse('memory');

opcbSetPhase5MascotState('map');
opcbSetPhase5MascotState('memory');
opcbSetPhase5MascotState('recall');
```

## Suggested mapping

Map:
- `map-canvas.svg` for page hero/title
- node icons by type: entry, parser, detector, validator, store, agent, test, docs, config, external, orphan
- `edge-calls.svg`, `edge-depends.svg`, `edge-produces.svg` for legend/edge type controls
- `map-search.svg`, `map-filter.svg`, `path-focus.svg`, `dependency-impact.svg` for toolbar/actions
- `map-health.svg` for right rail health

Memory:
- `memory-observatory.svg` for page hero/title
- `memory-archive.svg` for record count
- `recall-query.svg` for recall control
- `recall-health.svg`, `memory-freshness.svg`, `decay-meter.svg` for metrics
- `residue-quality.svg` for evidence residue
- `skill-tree.svg`, `promote-skill.svg` for skill candidates
- `compaction-queue.svg`, `memory-event.svg` for right rail
