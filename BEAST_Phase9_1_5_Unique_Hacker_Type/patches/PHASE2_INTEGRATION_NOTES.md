# Phase 2 Integration Notes

## Files added

- `css/beast-editor-cortex.css`
- `js/beast-editor-cortex.js`
- `js/pages/beast-sourceplan-page.js`
- `js/beast-phase2-app.js`

## Files replaced from Phase 1

- `index.html`
- `index-v2.html`
- `js/beast-store.js`
- `js/beast-desktop-bridge.js`
- `js/beast-layout-guard.js`
- `js/pages/beast-workspace-page.js`

## Legacy code intentionally not imported

- the global `app.js` Monaco ownership block
- duplicate `data-page-panel="source"` sections
- direct DOM references to SourcePlan IDs in the old HTML
- the old global file-model maps
- broad page visibility toggles
- legacy mascot timers

## Recommended first runtime test

1. Start the BEAST gateway.
2. Load Phase 2 in Electron.
3. Select a workspace.
4. Open two small text files.
5. Edit one file and switch tabs.
6. Navigate to Mission and back to Workspace.
7. Confirm the dirty buffer survives.
8. Draft SourcePlan.
9. Refresh lifecycle.
10. Verify and apply to a disposable test repository.
