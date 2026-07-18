# RC4 runtime acceptance checklist

## Shell and ownership

- [ ] Exactly one active `.beast-page` after every route transition.
- [ ] No duplicate IDs, mascot owners, Matrix owners or animation loops.
- [ ] Header mission title remains readable without colliding with state controls.
- [ ] Focus, scroll, selected nodes and open Monaco tabs survive refreshes.

## Visual operation

- [ ] Matrix background and sparse foreground rain are visible in Matrix + Grid mode.
- [ ] The square wall grid and perspective floor grid animate without covering controls.
- [ ] Header current and card heartbeat effects remain active after route changes.
- [ ] Reduced motion pauses expensive effects.
- [ ] Text uses the hacker-family typography after web fonts load.
- [ ] All 22 routes remain readable at 1920×1080, 1600×900 and 1366×768.
- [ ] 125% and 150% zoom equivalents retain owned scrolling and no document overflow.

## Gateway and Electron

- [ ] Electron preload capabilities are detected.
- [ ] Gateway health, route manifest and system snapshot load.
- [ ] Offline/degraded mode remains navigable and explicit.
- [ ] Runtime diagnostics export with `Ctrl/Cmd + Shift + D`.

## Mutating workflows

- [ ] SourcePlan draft, verify, apply and rollback contracts.
- [ ] Governed terminal allow, approval and blocked decisions.
- [ ] File create, rename and delete confirmations.
- [ ] Agent create/pause/resume/cancel and provider selection.
- [ ] Worktree creation and controlled close.
- [ ] Release runbook generation and verification.

## Evidence and sign-off

- [ ] Run `acceptance/release-runner.html` over HTTP and retain the exported JSON.
- Operator:
- Date:
- Electron version:
- Gateway version:
- Remaining issues:
