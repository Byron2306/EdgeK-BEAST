# BEAST Phase 11 — Responsive, Accessibility and Performance Acceptance

Phase 11 converts the Phase 10 production candidate into a viewport-aware and operator-comfort-aware renderer. It does not introduce a second page renderer or second stylesheet.

## Delivered

- Container-query layouts for the real page outlet width.
- Shell breakpoints for wide desktop, compact rail, single-column and mobile-width operation.
- 100% zoom readability baseline with 14px operational copy and 12px metadata floor.
- User-selectable text scale, contrast, motion and atmosphere.
- Keyboard navigation and a skip link.
- Runtime ARIA repair for dynamically mounted pages and controls.
- Adaptive Matrix renderer capped at 30fps, 24fps or 18fps according to measured performance.
- Visibility-aware animation suspension.
- Reduced-motion and forced-colour support.
- Scroll containment, table overflow ownership and touch-target minimums.
- Browser-based acceptance runner for all 22 pages and five viewport/zoom profiles.

## Key ownership contract

- One production stylesheet: `css/beast-production.css`
- One application owner: `js/beast-phase11-app.js`
- One accessibility/performance owner: `js/beast-phase11-accessibility-performance.js`
- One page outlet and one context rail.

## Honest boundary

Static validation was executed in this environment. The supplied runtime matrix must be run in the actual Chrome/Electron environment because the container Chromium process does not complete local renderer capture reliably.
