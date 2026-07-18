# OPCB Phase 2 Asset Pack

Assets for the next BEAST Studio pages:

1. Review Center
2. Evidence Library

## Contents

```text
assets/svg/
  review-center.svg
  quality-gate.svg
  contradiction-alert.svg
  risk-blocker.svg
  diff-review.svg
  test-summary.svg
  approval-workflow.svg
  approver.svg
  review-notes.svg
  report-export.svg

  evidence-library.svg
  selected-evidence.svg
  schema-valid.svg
  trace-link.svg
  validation-summary.svg
  export-evidence.svg
  audit-pack.svg
  extract-fields.svg
  completeness.svg
  open-file.svg
  download.svg
  search-filter.svg

  file-md.svg
  file-json.svg
  file-yaml.svg
  file-csv.svg
  file-html.svg
  file-zip.svg
  file-log.svg
  file-db.svg
  file-pcap.svg
  file-ndjson.svg

  review-center-bg.svg
  evidence-library-bg.svg
  cube-pulse-review.svg
  cube-pulse-evidence.svg
  mascot-review.svg
  mascot-evidence.svg
  mascot-blocked.svg

assets/css/opcb-phase2-assets.css
assets/js/opcb-phase2-assets.js
preview.html
manifest.json
```

## Install

Copy the `assets` folder into your UI root, then add after Phase 1 assets:

```html
<link rel="stylesheet" href="assets/css/opcb-phase2-assets.css">
<script src="assets/js/opcb-phase2-assets.js"></script>
```

## Quick use

```js
opcbSetPageArt('review');
opcbSetPageArt('evidence');

opcbPhase2Icon('qualityGate');
opcbPhase2Icon('contradiction', 'opcb-svg-icon review-danger');

opcbFileIcon('json');
opcbFileIcon('yaml');

opcbPhase2Pulse('review');
opcbPhase2Pulse('evidence');

opcbSetPhase2MascotState('review');
opcbSetPhase2MascotState('evidence');
opcbSetPhase2MascotState('blocked');
```

## Suggested mapping

Review page:
- `review-center.svg` for page title
- `quality-gate.svg` for gate cards
- `contradiction-alert.svg` for contradiction card
- `risk-blocker.svg` for blockers
- `diff-review.svg` for changed files/diff panel
- `approval-workflow.svg` for approve/request changes/rerun flow

Evidence page:
- `evidence-library.svg` for page title
- file icons in list rows
- `selected-evidence.svg` for selected evidence header
- `schema-valid.svg`, `trace-link.svg`, `validation-summary.svg`
- `export-evidence.svg` and `audit-pack.svg` for right rail
