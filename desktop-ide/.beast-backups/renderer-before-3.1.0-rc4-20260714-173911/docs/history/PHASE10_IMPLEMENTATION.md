# BEAST Phase 10 — Production Integration and Legacy Purge

Phase 10 turns the reconstructed renderer into a production candidate.

## Runtime contract
- One request broker for gateway HTTP and optional Electron IPC proxy transport.
- GET deduplication, short cache, bounded retries, timeouts, abort propagation, endpoint health, and request cancellation.
- Single binding for preload events.
- Runtime capability detection for all expected `window.beastDesktop` methods.

## Rendering hardening
- Atomic render commits retain the old page if a replacement renderer fails.
- Route navigation commits only after a successful render.
- Page scroll and focused controls are restored per route.
- Watchdog removes stale duplicate page roots and reports overflow, duplicate IDs, active editors, and runtime mode.
- Bulk refreshes are single-flight to prevent overlapping gateway storms.

## Legacy purge
- Twenty cascading CSS files are consolidated into `css/beast-production.css`.
- Seven Phase 9 visual correction controllers are consolidated into `js/beast-production-visual.js`.
- Phase 7, Phase 8, and Phase 9 app owners are removed from the production tree.
- Historical preview files and inactive migration debris are excluded from the production candidate.

## Electron integration
The `integration/` directory contains a contract manifest and non-destructive preload/main-process examples. Merge them into the current Electron host only where equivalent handlers do not already exist.
