# OPCB Phase 6 Asset Pack

Final utility and polish assets for BEAST Studio.

Pages covered:

1. Terminal
2. Providers
3. Tooling
4. Doctor
5. Settings
6. SourcePlan
7. Worktrees
8. Studio / command palette / final nav polish

## Contents

```text
assets/svg/
  terminal-console.svg
  terminal-safety.svg
  terminal-run.svg
  terminal-history.svg
  terminal-cwd.svg
  terminal-clear.svg

  providers-hub.svg
  provider-local.svg
  provider-cloud.svg
  provider-key.svg
  provider-quota.svg
  provider-latency.svg
  provider-health.svg

  tooling-gears.svg
  tool-registry.svg
  plugin-block.svg
  mcp-server.svg
  api-contract.svg
  webhook.svg

  doctor-shield.svg
  diagnostic-scan.svg
  fix-wrench.svg
  warning-triangle.svg
  logs-search.svg
  repair-route.svg

  settings-sliders.svg
  theme-palette.svg
  layout-grid.svg
  keyboard-shortcuts.svg
  save-profile.svg

  sourceplan-draft.svg
  sourceplan-apply.svg
  sourceplan-rollback.svg
  sourceplan-runbook.svg
  worktree-branch.svg
  worktree-merge.svg
  studio-diamond.svg
  command-palette.svg
  nav-polish.svg

  terminal-page-bg.svg
  providers-page-bg.svg
  tooling-page-bg.svg
  doctor-page-bg.svg
  settings-page-bg.svg
  sourceplan-page-bg.svg

  cube-pulse-terminal.svg
  cube-pulse-providers.svg
  cube-pulse-tooling.svg
  cube-pulse-doctor.svg
  cube-pulse-settings.svg

  mascot-terminal.svg
  mascot-providers.svg
  mascot-doctor.svg
  mascot-settings.svg
  mascot-polish.svg

assets/css/opcb-phase6-assets.css
assets/js/opcb-phase6-assets.js
preview.html
manifest.json
```

## Install

Copy the `assets` folder into your UI root, then add after earlier phase assets:

```html
<link rel="stylesheet" href="assets/css/opcb-phase6-assets.css">
<script src="assets/js/opcb-phase6-assets.js"></script>
```

## Quick use

```js
opcbSetPageArt('terminal');
opcbSetPageArt('providers');
opcbSetPageArt('tooling');
opcbSetPageArt('doctor');
opcbSetPageArt('settings');
opcbSetPageArt('source');

opcbPhase6Icon('terminalConsole');
opcbPhase6Icon('providersHub');
opcbPhase6Icon('doctorShield');

opcbUtilityIconByPage('terminal');
opcbUtilityIconByPage('source');

opcbPhase6Pulse('terminal');
opcbPhase6Pulse('providers');
opcbPhase6Pulse('doctor');

opcbSetPhase6MascotState('terminal');
opcbSetPhase6MascotState('providers');
opcbSetPhase6MascotState('doctor');
opcbSetPhase6MascotState('settings');
```

## Suggested mapping

Terminal:
- console, safety, run, history, cwd, clear

Providers:
- hub, local/cloud, key, quota, latency, health

Tooling:
- gears, registry, plugins, MCP server, API contract, webhook

Doctor:
- shield, diagnostic scan, warning, repair, logs

Settings:
- sliders, theme palette, layout grid, shortcuts, save profile

SourcePlan / Worktrees:
- draft, apply, rollback, runbook, branch, merge

Studio:
- studio diamond, command palette, nav polish
