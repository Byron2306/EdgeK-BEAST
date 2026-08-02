# Phase 9.1.1 implementation notes

## Visual ownership

The top header now has two non-overlapping vertical zones:

1. static BEAST wordmark / identity zone
2. live route, mission title and metadata zone

The route title remains editable HTML and is truncated safely instead of painting through the identity artwork.

## Page header ownership

Every `.beast-page-head` is a grid with a title column and an action column. SourcePlan's older sticky header declarations are reset in the final cascade. The icon socket has an opaque backing, so the page-specific PNG replaces rather than visually stacks with the generic terminal glyph in the ornamental strip.

## Runtime guard

`beast-phase9-1-1-overlay-fix.js` performs a conservative ownership check after mounts and route completion. It keeps one top-header component of each type, one active page root, and one direct page header. It does not rebuild page content or touch gateway state.
