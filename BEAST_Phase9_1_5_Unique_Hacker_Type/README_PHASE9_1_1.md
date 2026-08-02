# BEAST Phase 9.1.1 — Overlay Ownership Fix

This corrective patch fixes the visual collision shown in the Phase 9.1 header and SourcePlan strip.

## Root causes fixed

- The large metallic wordmark and live mission title occupied overlapping vertical bands.
- SourcePlan retained an older sticky-header skin underneath the Phase 9.1 plate.
- Page action clusters had no dedicated grid column and could drift across headings.
- The ornamental page strip already contained a generic terminal glyph while a page-specific icon was painted over it.
- Hot reloads or stale mounts had no final visual ownership guard.

## Corrections

- Separate top-brand and mission-copy bands in the premium header.
- A two-column page-header layout with responsive action wrapping.
- An opaque page-icon socket that cleanly replaces the strip's generic glyph.
- Explicit SourcePlan reset for its legacy sticky header rules.
- DOM ownership guard: one header component, one active page root, one page header.
- No images were generated or changed. This is code-only layout repair.

## Install

Use the patch over a clean Phase 9.1 renderer and fully restart Electron.
