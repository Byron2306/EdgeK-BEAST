# BEAST Studio Overhaul Plan
_Source: OPCB369S Phase 0–12 delivery + Obsidian BEAST IDE Blueprint_
_Target: desktop-ide/renderer — Electron renderer replacing the cramped green TUI-style UI_

---

## What this replaces

The current renderer is a monochrome green monospace dashboard that was iteratively patched.
It does not reflect the documented BEAST Studio vision. The OPCB369S delivery provides
the exact design language that should drive the renderer.

---

## Phase 1 — Design system + CSS overhaul (THIS PHASE)

**File:** `desktop-ide/renderer/styles.css`

Replace the entire stylesheet with the OPCB369S design system:

| Token | Old | New |
|---|---|---|
| Background | `#030504` mono-green | `#06101d` deep navy |
| Panel | `rgba(3,17,13)` | `#0b1728cc` blue-panel |
| Text | `#c7ffd2` green | `#eaf4ff` blue-white |
| Accent | `--acid: #a6ff3f` | `--cyan: #39d7ff` |
| Secondary | `--green: #6eff9d` | `--teal: #39f0c2` |
| Tertiary | none | `--gold: #ffc857`, `--violet: #b36bff` |
| Font | `ui-monospace` everywhere | `Inter, Segoe UI` body; monospace only in editors |
| Base size | 14px (patched from 12px) | 14px confirmed |
| Dot grid bg | none | `radial-gradient(#2a8cff44 1px,transparent 1px)` at 22% opacity |

**Layout shell:**
```
250px sidebar  |  flexible main (3 rows: header 96px / content 1fr / command-bar 152px)  |  190px cube-zone
```
Replace current 7-column compressed splitter grid.

**Nav items:** 52px height, icon + label + arrow, active glow border — not tiny 32px rail buttons.

**Cards:** Full card system with `card-head`, `card-body`, `badge`, `active-chip` classes.

**Cube Pulse:** Animated 3D wire cube + BEAST head mascot as right-column state indicator.

**Command bar:** Bottom input + chips row, replacing the hidden modal command palette.

---

## Phase 2 — HTML structure overhaul

**File:** `desktop-ide/renderer/index.html`

Restructure from current 5-rail layout to OPCB369S three-column shell:

```
.app-shell  →  grid: 250px 1fr 190px
  .sidebar          ← nav + brand + footer
  .main             ← mission-header + workspace-grid + command-bar
    .content-panel  ← primary page content (file explorer, editor, etc)
    .context-panel  ← cube state, event ledger, policy
  .cube-zone        ← animated Cube Pulse + gateway state
```

All existing `app.js` DOM IDs preserved via hidden elements or renamed to new locations.
New nav items map to existing BEAST pages: Workspace → Mission → SourcePlan → Agents →
Worktrees → Evidence → Terminal → Providers → Tooling → Doctor → Settings.

---

## Phase 3 — app.js wiring to new DOM

**File:** `desktop-ide/renderer/app.js`

- Update `setDesktopPage()` to drive `.nav-item.active` highlighting and set `data-active-face` on body for Cube Pulse
- Update `updateStatusChips()` to populate new `#cubeStateChips` in cube-zone
- Wire command-bar input (`#commandBarInput`) to command palette search
- Wire command-bar chips to common actions
- Update `setStreamState()` to update `#cubeStreamState` in cube-zone
- Keep all existing refresh/snapshot/governance functions unchanged

---

## Phase 4 — Verify + launch

- Run `npm run start` in `desktop-ide`
- Confirm 3-column layout renders
- Confirm Cube Pulse animates
- Confirm file explorer fills content panel
- Confirm nav switching works
- Confirm gateway status updates in cube-zone

---

## What is NOT changing in this overhaul

- `app.js` business logic (snapshot, refresh throttle, governance flows) — already improved
- `main.js` Electron shell
- All backend BEAST services and gateway
- All existing DOM IDs that `app.js` queries (all preserved by mapping to new positions)
