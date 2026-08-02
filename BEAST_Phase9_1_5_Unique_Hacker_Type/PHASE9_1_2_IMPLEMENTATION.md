# Phase 9.1.2 implementation notes

## Root causes

1. The metallic heading effect depended on transparent background-clipped text. Several inherited visual layers and browser compositing states made that fill appear nearly black.
2. `#beastPageScan` was a fixed z-index 8 overlay, so its green band travelled over labels and controls.
3. The ornamental page-header PNG contains a bright right-side signal treatment. Page action buttons were placed directly over it without an opaque control socket.
4. Animated `.beast-card` and `.beast-surface` pseudo-elements could sit above normal descendants because their z-index exceeded the controls.

## Correction

The final cascade uses solid silver text fill, moves the scanner beneath `#beastPageOutlet`, gives page actions an isolated dark backing plate, applies high-contrast button treatments, and restores safe pseudo-element stacking.
