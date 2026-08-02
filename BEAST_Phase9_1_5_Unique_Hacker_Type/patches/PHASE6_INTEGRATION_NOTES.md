# Phase 6 Integration Notes

## Full-package route

The safest path is to test the full `BEAST_Phase6_Map_Crystal` directory as an isolated renderer and then point the Electron BrowserWindow at its `index.html`.

## Overlay-patch route

Overlay the Phase 6 patch onto a clean Phase 5 installation. Then remove:

```text
js/beast-phase5-app.js
```

The HTML entry points must load `js/beast-phase6-app.js` only.

## New runtime files

```text
css/beast-phase6-polish.css
css/beast-map-crystal.css
js/beast-map-crystal-bridge.js
js/pages/beast-map-page.js
js/pages/beast-crystallization-page.js
js/beast-phase6-app.js
```

## Modified runtime files

```text
index.html
index-v2.html
preview.html
assets/manifest.json
js/beast-desktop-bridge.js
js/beast-fx.js
js/beast-store.js
js/pages/beast-agents-page.js
```

Do not re-add the old OPCB renderers or legacy `app.js`. They would restore the duplicate-render and overlapping-panel defects this reconstruction removes.
