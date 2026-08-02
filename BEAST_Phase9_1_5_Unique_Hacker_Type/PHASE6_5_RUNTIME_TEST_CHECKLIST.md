# BEAST Phase 6.5 Runtime Acceptance Checklist

## Installation

1. Back up the current renderer directory.
2. Test the full package in isolation first.
3. For an overlay installation, apply the patch to a clean Phase 6 tree.
4. Launch through the normal Electron entry point, not by double-clicking the HTML file.

## 100% zoom legibility

Test at 1920×1080 and browser zoom 100%:

- [ ] Sidebar labels can be read without leaning toward the display.
- [ ] Page subtitles and panel descriptions are visible against black.
- [ ] Model and Agent node labels are readable.
- [ ] Right-rail labels and values remain distinct.
- [ ] Buttons are at least comfortably finger/target sized.
- [ ] No essential information uses faint 7–10 px text.

Repeat at:

- [ ] 1600×900 at 100%.
- [ ] 1366×768 at 100%.
- [ ] 1920×1080 at 125%.
- [ ] 1920×1080 at 150%.

## Motion

- [ ] Matrix rain moves subtly behind the shell.
- [ ] Perspective grid advances without interfering with text.
- [ ] Normal panels use neutral chrome rather than solid green rails.
- [ ] A small green current travels across panel edges.
- [ ] Hover/focus intensifies the current without flooding the panel.
- [ ] Model route signals move between nodes.
- [ ] Agent handoff signals move between orchestrator and agents.
- [ ] Memory constellation signals move between memory nodes.
- [ ] Reduced-motion mode disables continuous movement.

## Icon coverage

- [ ] All Model Registry rows display an icon.
- [ ] All Agent constellation nodes display an icon.
- [ ] Assign Agent, Route Policy, Diagnostics, Verify, Compact and Export controls have icons.
- [ ] Broken images fall back to Diagnostics rather than showing an empty square.

## Trust and Memory

- [ ] Trust provenance uses the premium trust emblem.
- [ ] Provenance chain current animates.
- [ ] Memory recall core uses the premium memory emblem.
- [ ] No basic inline SVG constellation is visible.
- [ ] Memory nodes remain aligned during resize and zoom.

## Layout and rendering

- [ ] Exactly one page occupies `#beastPageOutlet`.
- [ ] No page paints over the previous route.
- [ ] Main viewport owns vertical scrolling.
- [ ] No document-level horizontal scrollbar appears.
- [ ] Context rail remains independently scrollable.
- [ ] Canvas links realign after resizing.
- [ ] No console errors occur during route changes.
