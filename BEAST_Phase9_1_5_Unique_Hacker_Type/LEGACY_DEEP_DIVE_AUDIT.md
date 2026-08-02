# BEAST IDE Deep-Dive Architecture Audit

## Verdict

The current IDE should not receive another visual override layer. It already contains multiple overlapping UI systems, duplicate layout rules, and two competing sprite controllers. The correct next build is a structural consolidation that preserves gateway, editor, SourcePlan, agent, evidence, and tooling behavior while replacing the rendering shell.

## Audit scope

- `index.html`: 1,215 lines
- `styles.css`: 644 lines
- `opcb-reference.css`: 3,739 lines
- `app.js`: 5,746 lines
- `opcb-renderers.js`: 647 lines
- `opcb-live-store.js`: 507 lines
- `opcb-components.js`: 77 lines
- `beast-studio-integrations.js`: 1,411 lines
- `opcb-state.js`: 837 lines
- Total reviewed: 14,823 lines

Static analysis found 1,012 qualified CSS rule blocks, 53 exact duplicate selector blocks in the same cascade context, and several high-risk selectors with contradictory layout declarations.

## Critical findings

### 1. Two complete CSS systems occupy the same stylesheet

`styles.css` begins with one shell, sidebar, brand, workspace, command-bar, cube, and card system, then appends another “OPCB369S mission-control skin” redefining the same selectors. Final appearance depends on source order rather than a coherent component contract.

Examples include conflicting definitions for:

- `.app-shell`
- `.brand`
- `.brand-mascot`
- `.nav-item`
- `.workspace-grid`
- `.content-panel`
- `.command-input`
- `.cube-pulse`
- `.sidebar-footer`

### 2. `opcb-reference.css` is an override tower

The file begins with dashboard shell widths of 292px and a 300–340px right rail, then ends with a readability pass changing them to 236px and 340–400px. Additional 1450px, 1500px, 1250px, and 1100px breakpoints redefine the same grids with `!important`.

This causes abrupt layout changes and makes any later theme stylesheet hazardous.

### 3. The DOM contains new and legacy page systems simultaneously

The HTML includes one central OPCB dashboard for each page plus many legacy context-panel sections sharing the same `data-page-panel` values. The audit counted 60 page-panel nodes. `setDesktopPage()` toggles all matching nodes, and CSS is then relied on to suppress the legacy set for dashboard pages.

This explains page flashes, accidental stacking, and “render over render” behavior when state attributes or styles arrive out of sequence.

### 4. Full-page render occurs twice on normal navigation

The current navigation path is:

1. `setDesktopPage()` toggles every page panel.
2. `opcbApplyPage()` replaces the active dashboard with `innerHTML`.
3. It starts an asynchronous live refresh.
4. `opcbRefreshPage()` normalizes payloads and calls `opcbApplyPage()` again.

Selection handlers on Evidence and Crystallization can also render directly and then invoke the full page renderer again.

Consequences:

- scroll position resets
- focus and selections can disappear
- animations restart
- injected icons are removed and recreated
- large DOM regions reflow twice
- momentary old/new UI overlap becomes visible

### 5. Two mascot animation engines fight over one container

`opcb-state.js` replaces `#spriteContainer` with ten page-derived frames and runs a 130ms interval. `beast-studio-integrations.js` separately creates forty frame elements across four states and runs its own FPS-controlled timer.

Both target the same container. A page refresh can destroy the frame elements held by the second controller while its timer continues referencing them. This directly explains resets, drift, missing blinks, and inconsistent state animation.

### 6. Nested scroll ownership is inconsistent

The base shell gives `.content-panel` overflow control, while later rules set it to `overflow:auto`; the dashboard also gets its own `max-height` and `overflow:auto`. Several page-specific rules add another scroll container.

The result is nested scrollbars, clipped sticky controls, height calculations that differ by page, and panels that appear too short or too tall.

### 7. Several page grids contain hard minimums

Large fixed minimums such as 520px panels, 980px map canvases, 720px minimum heights, and fixed right rails conflict with the 1920×1080 target once sidebar, padding, command dock, and telemetry rail are subtracted.

These layouts need container-aware breakpoints, not only viewport media queries.

## Asset-production requirements

### Cursors

Do not use the concept sheet crops directly. Each cursor needs:

- a padded transparent master canvas
- consistent safe margin
- explicit hotspot coordinates
- 32px and 48px production exports
- larger preview exports stored separately
- no glow crossing the canvas boundary

### Mascot frames

All frames must share one identical canvas and baseline. Normalize each alpha bounding box into a fixed safe rectangle before animation. Never crop frames independently.

### Panels and cards

Do not use complete raster cards with baked-in text. Produce:

- transparent corner pieces
- horizontal and vertical rail segments
- a transparent or tileable center
- 9-slice / `border-image` definitions
- separate alert, amber, green, and neutral skins

### Effects

Effects should be isolated transparent overlays with no baked checkerboard. Animate them with transforms and opacity, not by repainting large blurred backgrounds every frame.

## Recommended architecture

### Stable DOM shell

Keep exactly one of each:

- sidebar
- mission header
- page outlet
- right rail outlet
- command dock
- modal layer
- effect layer

Legacy feature panels should be registered as page modules, not kept permanently in the DOM.

### Single render scheduler

Navigation changes state once. Live payloads update state once. A render scheduler batches changes with `requestAnimationFrame()` and patches only dirty regions.

### Single sprite service

One controller owns frame loading, state transitions, FPS, visibility pausing, and reduced-motion behavior.

### CSS layers

Split styling into:

1. tokens
2. reset
3. shell layout
4. components
5. page modules
6. effects and motion
7. responsive/container rules

Remove routine `!important` usage.

## Next implementation pass

1. Freeze current working behavior and add a renderer smoke harness.
2. Replace the duplicate page-panel DOM with page outlets.
3. Consolidate the page render lifecycle.
4. Replace the two mascot systems with one normalized sprite engine.
5. Consolidate shell sizing and scroll ownership.
6. Introduce production 9-slice assets and premium PNG icons.
7. Add effects only after stable 1920×1080, 1600×900, 1366×768, and ultrawide layout tests pass.
