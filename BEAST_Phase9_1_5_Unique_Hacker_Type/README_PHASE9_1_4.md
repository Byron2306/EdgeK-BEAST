# BEAST Phase 9.1.4 — Hacker Type + Visible Atmosphere

This is a code-only corrective release for the Phase 9.1.3 renderer.

## Corrects

- replaces the remaining generic desktop UI font language with a condensed industrial UI stack and hard monospace telemetry stack
- raises minimum operational text sizes without touching Monaco's internal font rendering
- makes matrix rain visibly present through and above glass panels
- adds a moving square-grid overlay plus a stronger perspective floor grid
- removes the heavy backdrop blur that was smearing the rain and grid into blackness
- retains dark tints behind dense editors, diffs and terminals
- preserves pointer behavior, page ownership and gateway contracts

## Install

```bash
chmod +x APPLY_PHASE9_1_4_PATCH.sh
./APPLY_PHASE9_1_4_PATCH.sh /path/to/your/beast/renderer
```

Fully restart Electron afterward.
