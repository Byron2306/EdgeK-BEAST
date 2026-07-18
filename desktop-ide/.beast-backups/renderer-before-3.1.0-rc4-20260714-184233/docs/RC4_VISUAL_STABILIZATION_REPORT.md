# RC4 visual stabilization report

## Why RC4 exists

RC3 passed static syntax and reference checks, but real 1920×1080 rendering exposed uneven layouts, clipped headings, tiny metadata, oversized frame interiors and missing or inconsistent animations. RC4 treats visual acceptance as an engineering test, not a decorative afterthought.

## Architectural corrections

- **One stylesheet owner:** `css/beast-production.css`
- **One application owner:** `js/beast-release-app.js`
- **One visual loop owner:** `js/beast-visual-runtime.js`
- **One page outlet:** `#beastPageOutlet`
- **One context rail:** `#beastContextRail`

The visual runtime owns both Matrix canvases, the moving grid, adaptive frame timing, visibility pause, reduced motion, header current and card heartbeat canvases. Obsolete `beast-atmosphere.js` and `beast-production-visual.js` owners are removed.

## Layout corrections

- Fixed header mission-title clipping and restored a large BEAST wordmark.
- Standardized desktop page heads and compact viewport wrapping.
- Added container-based route collapse rather than relying only on monitor width.
- Made SourcePlan titles and controls non-colliding.
- Corrected Settings toggle alignment and Tooling lower-grid collapse.
- Allowed long right-rail facts and operational headings to wrap safely.
- Reduced command-dock vertical occupation.
- Preserved owned horizontal scrolling for mission flows, maps and pipelines.

## Automated evidence

- Routes: **22**
- Viewport profiles: **5**
- Scenarios: **110**
- Scenarios passing structural/geometry checks: **110/110**
- Duplicate IDs: **0**
- Page-header title/action collisions: **0**
- Document horizontal overflow scenarios: **0**
- Boot/runtime errors in capture harness: **0**
- Operational leaf text below 9px: **0**
- Unexpected clipping candidates: **0**
- Temporal animation probe: **PASS**, 9.6689% of pixels changed over 1.25 seconds (1.0814% strong change)

Intentional candidates are restricted to the owned mission-stage scroller and radial memory-star labels. See `acceptance/RC4_VISUAL_ACCEPTANCE_SUMMARY.json` and the profile metric files for exact evidence.

## Honest boundary

The CDP harness exercises the renderer DOM, route navigation, responsive geometry and visual runtime. It does not prove Electron preload wiring, Monaco loading, live gateway mutations, terminal streaming, provider operations, worktree changes or SourcePlan application. Those remain in the runtime checklist.
