# BEAST Phase 6.5 — Visual Systems and Legibility Refit

## Purpose

Phase 6.5 is a corrective production pass between the Map/Crystallization transplant and the remaining utility-page migration. It addresses four regressions observed in the Phase 6 runtime:

1. the animated edge treatment was layered over permanently green frame artwork, producing excessive neon density;
2. typography inherited hundreds of 7–10 px declarations from dense page styles, making the IDE uncomfortable at 100% browser zoom;
3. Models and Agents contained dynamic icon names with no matching PNG files, creating blank icon squares;
4. Models, Agents, Trust and Memory still used basic inline SVG or elementary CSS geometry for their central visual systems.

## Implemented changes

### Neutral frame architecture

Five new neutral gunmetal nine-slice masters replace permanent green paint on normal panels:

- `panel-card-neutral.png`
- `panel-card-compact-neutral.png`
- `panel-wide-neutral.png`
- `panel-tall-neutral.png`
- `banner-neutral.png`

Amber and red state frames remain colour-coded. Green is now introduced by a travelling top/side signal, focus state, active selection, and deliberate status effects.

### Hacker current and atmosphere

- subtle full-screen matrix rain canvas;
- moving perspective grid behind the shell;
- low-opacity matrix veil inside graph surfaces;
- travelling panel-edge current;
- restrained shell current and breathing trace;
- stronger energy only on hover, focus, active or selected state;
- reduced-motion support.

### Legibility baseline

The phase adds a final cascade layer that establishes:

- 16 px body baseline at desktop sizes;
- 14 px operational body copy;
- 12 px minimum metadata target;
- larger navigation, buttons, page headings and panel headings;
- brighter silver contrast tiers;
- increased row heights, padding and line-height;
- responsive stacking instead of shrinking dense layouts.

The override layer covers 495 legacy microtype declarations without modifying each older stylesheet in place.

### Premium icon completion

New production PNGs:

- `agent.png`
- `cube.png`
- `orchestrator.png`
- `model-cube.png`
- `trust-core.png`
- `memory-core.png`
- `skill-core.png`
- `diagnostics.png`
- `route.png`

A MutationObserver-based icon coverage guard adds icons to known action buttons that arrive through dynamic renderers and supplies a premium fallback when an image fails.

### Visual-system replacement

The following inline SVG systems were removed:

- Model inference-cascade links;
- Agent constellation rings and links;
- Memory constellation links.

They are now drawn by one DPR-aware Canvas runtime with ResizeObserver layout and moving signal particles.

Trust provenance and Memory recall identity now use premium transparent PNG emblems with controlled CSS motion rather than basic fingerprint/cube geometry.

## New runtime files

- `css/beast-phase6-5-visual-legibility.css`
- `js/beast-atmosphere.js`
- `js/beast-visual-canvas.js`
- `js/beast-icon-coverage.js`
- `js/beast-phase6-5-app.js`
- `preview-phase6-5.html`

## Ownership contract

Phase 6.5 retains:

- one page outlet;
- one context rail;
- one mascot root/controller;
- one active page renderer;
- one Canvas owner per mounted visual system;
- renderer disposal on route change.

## Acceptance boundary

Static syntax, references, ownership, icon coverage and inline-SVG removal were validated in the build environment. Electron preload, Monaco and live gateway behaviour still require the runtime checklist on the target BEAST installation.

The sandbox administrator blocked local Chromium navigation during this build, so an automated browser screenshot was not represented as a successful runtime test. A self-contained animated preview and visual QA board are included instead.
