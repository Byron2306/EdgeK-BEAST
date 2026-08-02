# Phase 4 Patch Integration Notes

Apply the Phase 4 patch over a clean Phase 3 package.

## Added

```text
css/beast-review-evidence.css
js/beast-review-evidence-bridge.js
js/pages/beast-review-page.js
js/pages/beast-evidence-page.js
js/beast-phase4-app.js
migration/MIGRATION_MAP_PHASE4.json
```

## Replaced or updated

```text
index.html
index-v2.html
preview.html
js/beast-store.js
js/beast-desktop-bridge.js
js/pages/beast-mission-page.js
css/beast-shell.css
assets/manifest.json
README.md
PHASE_ROADMAP.md
```

## Delete after applying the patch

```text
js/beast-phase3-app.js
```

The updated HTML does not load the Phase 3 app, but deleting it avoids accidental double ownership during later integration.
