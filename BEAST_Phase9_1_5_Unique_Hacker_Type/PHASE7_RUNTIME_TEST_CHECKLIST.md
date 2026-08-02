# BEAST Phase 7 Runtime Acceptance Checklist

## Installation

1. Back up the current renderer directory.
2. Test the full Phase 7 package in isolation first.
3. For an existing clean Phase 6.5 tree, use the Phase 7 patch script.
4. Launch through the normal Electron entry point so preload methods are available.

## Shell ownership

- [ ] Exactly one page exists under `#beastPageOutlet` after every route change.
- [ ] Exactly one context rail exists.
- [ ] Only `beast-phase7-app.js` owns application boot.
- [ ] No legacy page panels appear behind Terminal, Tooling, or Doctor.
- [ ] Navigation does not reset unrelated Monaco buffers.

## Terminal Nexus

- [ ] A harmless command classifies successfully.
- [ ] A governed mutation requests explicit approval.
- [ ] A destructive command is blocked.
- [ ] stdout and stderr stream without whole-page repainting.
- [ ] Cancel closes the active event stream.
- [ ] Timeout is respected.
- [ ] CWD remains inside or relative to the selected workspace.
- [ ] Command history survives a restart for the same workspace.
- [ ] History remains separate between workspaces.
- [ ] An execution receipt can be copied.
- [ ] The mascot enters working, success, and alert states correctly.

## Tooling Forge

- [ ] Tooling snapshot loads from Electron or the gateway.
- [ ] Syntax and lint contracts display real values.
- [ ] MCP server count and status are accurate.
- [ ] Pending approvals appear.
- [ ] Approve and deny actions update without duplicating the page.
- [ ] Plugin registry displays all installed plugins.
- [ ] Manifest validation reports valid and invalid manifests clearly.
- [ ] Environment versions are readable at 100% zoom.
- [ ] Benchmark execution produces a result or a grounded error.
- [ ] Missing optional endpoints degrade to warnings rather than runtime exceptions.

## Doctor Diagnostics

- [ ] Deep scan runs all route checks once.
- [ ] Health score matches check outcomes.
- [ ] Port and process tables populate from the system snapshot.
- [ ] Recommendations correspond to failed or warning checks.
- [ ] Report copying works.
- [ ] Gateway restart appears only inside Electron.
- [ ] Restart requires operator confirmation.
- [ ] The page remains usable while the gateway is offline.

## Visual and responsive acceptance

Test each of Terminal, Tooling, and Doctor at:

- [ ] 1920×1080, 100%
- [ ] 1600×900, 100%
- [ ] 1366×768, 100%
- [ ] 1920×1080, 125%
- [ ] 1920×1080, 150%

For each configuration:

- [ ] Body text is readable without zoom rescue.
- [ ] No document-level horizontal overflow exists.
- [ ] The main viewport is the only page scroll owner.
- [ ] Buttons remain reachable.
- [ ] Right-rail cards do not clip their content.
- [ ] High-definition frame corners remain continuous.
- [ ] Signal animation is visible but does not obscure text.
- [ ] Reduced-motion mode removes continuous movement.

## Console acceptance

- [ ] No uncaught JavaScript errors.
- [ ] No missing icon or frame requests.
- [ ] No duplicate-ID warnings.
- [ ] No stale stream attempts after leaving Terminal.
- [ ] No repeated subscription growth after route cycling.
