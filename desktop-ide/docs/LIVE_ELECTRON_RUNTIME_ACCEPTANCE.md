# Live Electron runtime acceptance

Run from `desktop-ide/`; Electron provisions the `.byron/services.yaml` BEAST
upstream at `127.0.0.1:8101` by default:

```bash
npm run smoke
npm run visual:audit
```

Acceptance requires: all declared routes navigate through `BeastRouter`, each
page sets `document.body.dataset.beastPage`, provider selection renders a
selected provider, agent assignment renders a session or an actionable error,
PREС/Insight/Compute Economy panels render their live state, and no page has
missing asset or JavaScript syntax failures. The audit screenshots and JSON
report are the runtime evidence; Chromium GLib handler warnings are non-fatal
when the checklist assertions pass.
