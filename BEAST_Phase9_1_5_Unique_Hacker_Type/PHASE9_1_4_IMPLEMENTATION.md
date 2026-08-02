# Phase 9.1.4 implementation notes

## Root causes fixed

1. **Backdrop blur erased the atmosphere.** The Phase 9.1.3 glass contract used 11–15px blur on most surfaces. Even with transparent tint, the matrix characters and square grid were diffused into a nearly uniform black-green field.
2. **The foreground rain was too sparse and too faint.** It used a 58px column step and 0.065 CSS opacity.
3. **The grid remained mostly behind the shell.** It was technically active but did not survive opaque/tinted nested page surfaces.
4. **Typography fell back to ordinary desktop sans fonts.** Many surfaces inherited Segoe UI/Arial-like fallbacks, while dense legacy modules hard-coded tiny 8–10px labels.

## Corrective architecture

- one replacement atmosphere controller owns the two existing canvases
- one pointer-transparent front grid is inserted at runtime
- matrix/grid are screen-composited without owning page layout
- glass blur is replaced by saturation/contrast with only 1.5px blur on shell regions
- dense editor and terminal surfaces retain dark readable tints
- no remote or bundled fonts are required
- Monaco remains under Monaco's own font renderer
