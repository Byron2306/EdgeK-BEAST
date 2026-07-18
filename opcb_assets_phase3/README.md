# OPCB Phase 3 Asset Pack

Assets for the next BEAST Studio pages:

1. Crystallization
2. Trust

## Contents

```text
assets/svg/
  crystal-chamber.svg
  crystal-candidate.svg
  crystal-ready.svg
  crystal-seal.svg
  immutable-lock.svg
  artifact-commit.svg
  event-ledger.svg
  quality-prism.svg
  crystal-export.svg

  crystal-chamber-idle.svg
  crystal-chamber-ready.svg
  crystal-chamber-committed.svg

  trust-shield.svg
  trust-posture.svg
  data-boundary.svg
  integrity-check.svg
  policy-guardrail.svg
  fingerprint.svg
  canary-status.svg
  attestation.svg
  audit-timeline.svg
  local-first.svg
  permissions-lock.svg
  provenance-chain.svg
  trust-report.svg

  crystallization-bg.svg
  trust-posture-bg.svg
  cube-pulse-crystal.svg
  cube-pulse-trust.svg
  mascot-crystal.svg
  mascot-trust.svg
  mascot-sealed.svg

assets/css/opcb-phase3-assets.css
assets/js/opcb-phase3-assets.js
preview.html
manifest.json
```

## Install

Copy the `assets` folder into your UI root, then add after earlier phase assets:

```html
<link rel="stylesheet" href="assets/css/opcb-phase3-assets.css">
<script src="assets/js/opcb-phase3-assets.js"></script>
```

## Quick use

```js
opcbSetPageArt('crystallization');
opcbSetPageArt('trust');

opcbPhase3Icon('crystalReady');
opcbPhase3Icon('trustShield');

opcbCrystalHero('idle');
opcbCrystalHero('ready');
opcbCrystalHero('committed');

opcbPhase3Pulse('crystallization');
opcbPhase3Pulse('trust');

opcbSetPhase3MascotState('crystal');
opcbSetPhase3MascotState('trust');
opcbSetPhase3MascotState('sealed');
```

## Suggested mapping

Crystallization:
- `crystal-chamber-idle.svg`, `crystal-chamber-ready.svg`, `crystal-chamber-committed.svg` for central chamber state.
- `crystal-candidate.svg` for candidate queue rows.
- `quality-prism.svg` for quality gate cards.
- `artifact-commit.svg`, `immutable-lock.svg`, `crystal-seal.svg` for finalization actions.
- `event-ledger.svg` for the event ledger.

Trust:
- `trust-posture.svg` for score/overview.
- `data-boundary.svg` for local-first boundary.
- `integrity-check.svg` for verified state.
- `policy-guardrail.svg` for guardrail cards.
- `fingerprint.svg`, `provenance-chain.svg`, `attestation.svg` for provenance/signatures.
- `canary-status.svg` for canary health.
- `audit-timeline.svg` for audit trail.
