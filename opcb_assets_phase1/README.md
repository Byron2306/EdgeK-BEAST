# OPCB Phase 1 Asset Pack

Assets for the first two BEAST Studio pages:

1. Workspace / Flow Canvas
2. Mission Overview

## Contents

```text
assets/svg/
  workspace-flow.svg
  mission-target.svg
  models-cube.svg
  agents-bot.svg
  tools-crossed.svg
  review-lens.svg
  evidence-doc.svg
  crystal-diamond.svg
  health-ring.svg
  next-action-bolt.svg
  approval-gate.svg
  timeline-node.svg
  workspace-flow-canvas-bg.svg
  mission-overview-bg.svg
  cube-pulse-workspace.svg
  cube-pulse-mission.svg
  mascot-idle.svg
  mascot-working.svg
  mascot-alert.svg
  mascot-success.svg

assets/css/opcb-phase1-assets.css
assets/js/opcb-phase1-assets.js
```

## Install

Copy the `assets` folder into your UI root, then add:

```html
<link rel="stylesheet" href="assets/css/opcb-phase1-assets.css">
<script src="assets/js/opcb-phase1-assets.js"></script>
```

## Quick use

```js
opcbSetPageArt('workspace');
opcbSetPageArt('mission');
opcbSetMascotState('working');
```

Use icons in renderers:

```js
opcbIcon('mission')
opcbIcon('health', 'opcb-big-glyph')
opcbCubePulse('workspace')
```

## Notes

All icons are SVG, transparent, and theme-aligned to the OPCB cyan/teal/violet/gold palette.
The mascot SVGs are deliberately aligned to a consistent 160x160 canvas to prevent animation wobble.
