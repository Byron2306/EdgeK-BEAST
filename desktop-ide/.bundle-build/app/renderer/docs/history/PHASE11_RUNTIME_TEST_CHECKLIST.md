# Phase 11 Runtime Acceptance Checklist

## Viewport matrix

Test every route at:

- 1920×1080, 100%
- 1600×900, 100%
- 1366×768, 100%
- 1920×1080, 125% zoom
- 1920×1080, 150% zoom

Use `acceptance/phase11-runner.html` and retain its downloaded JSON.

## Manual checks

- No page-level horizontal scrollbar.
- SourcePlan, Map, pipelines and flow canvases scroll only within their own surface.
- Active page has one renderer root.
- F6 cycles main regions.
- Ctrl/Cmd+K focuses the command input.
- Ctrl/Cmd+Shift+L opens display controls.
- Alt+Left/Right navigates routes.
- Keyboard focus remains visible.
- Text is readable at 100% without browser zoom assistance.
- Large and extra-large text do not cover action buttons.
- High contrast retains panel hierarchy.
- Reduced motion pauses Matrix rain, scan and heartbeat motion.
- Adaptive performance switches tier without remounting the page.
- Electron preload, Monaco, terminal and gateway actions remain operational.
