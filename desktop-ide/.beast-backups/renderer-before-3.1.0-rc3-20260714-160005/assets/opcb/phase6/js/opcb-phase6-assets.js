// OPCB Phase 6 Assets: Utility + Polish helpers.

window.OPCB_PHASE6_ASSETS = {
  svgBase: "assets/svg/",
  icons: {
    terminalConsole: "terminal-console.svg",
    terminalSafety: "terminal-safety.svg",
    terminalRun: "terminal-run.svg",
    terminalHistory: "terminal-history.svg",
    terminalCwd: "terminal-cwd.svg",
    terminalClear: "terminal-clear.svg",

    providersHub: "providers-hub.svg",
    providerLocal: "provider-local.svg",
    providerCloud: "provider-cloud.svg",
    providerKey: "provider-key.svg",
    providerQuota: "provider-quota.svg",
    providerLatency: "provider-latency.svg",
    providerHealth: "provider-health.svg",

    toolingGears: "tooling-gears.svg",
    toolRegistry: "tool-registry.svg",
    pluginBlock: "plugin-block.svg",
    mcpServer: "mcp-server.svg",
    apiContract: "api-contract.svg",
    webhook: "webhook.svg",

    doctorShield: "doctor-shield.svg",
    diagnosticScan: "diagnostic-scan.svg",
    fixWrench: "fix-wrench.svg",
    warningTriangle: "warning-triangle.svg",
    logsSearch: "logs-search.svg",
    repairRoute: "repair-route.svg",

    settingsSliders: "settings-sliders.svg",
    themePalette: "theme-palette.svg",
    layoutGrid: "layout-grid.svg",
    keyboardShortcuts: "keyboard-shortcuts.svg",
    saveProfile: "save-profile.svg",

    sourceplanDraft: "sourceplan-draft.svg",
    sourceplanApply: "sourceplan-apply.svg",
    sourceplanRollback: "sourceplan-rollback.svg",
    sourceplanRunbook: "sourceplan-runbook.svg",
    worktreeBranch: "worktree-branch.svg",
    worktreeMerge: "worktree-merge.svg",
    studioDiamond: "studio-diamond.svg",
    commandPalette: "command-palette.svg",
    navPolish: "nav-polish.svg"
  },
  cubePulse: {
    terminal: "cube-pulse-terminal.svg",
    providers: "cube-pulse-providers.svg",
    tooling: "cube-pulse-tooling.svg",
    doctor: "cube-pulse-doctor.svg",
    settings: "cube-pulse-settings.svg",
    source: "cube-pulse-tooling.svg",
    worktrees: "cube-pulse-tooling.svg",
    studio: "cube-pulse-settings.svg"
  },
  mascot: {
    terminal: "mascot-terminal.svg",
    providers: "mascot-providers.svg",
    tooling: "mascot-polish.svg",
    doctor: "mascot-doctor.svg",
    settings: "mascot-settings.svg",
    source: "mascot-polish.svg",
    worktrees: "mascot-polish.svg",
    studio: "mascot-polish.svg"
  }
};

window.opcbPhase6Icon = function opcbPhase6Icon(name, className = "opcb-svg-icon") {
  const file = window.OPCB_PHASE6_ASSETS.icons[name] || name;
  return `<img class="${className}" src="${window.OPCB_PHASE6_ASSETS.svgBase}${file}" alt="">`;
};

window.opcbPhase6Pulse = function opcbPhase6Pulse(page = "terminal") {
  const file = window.OPCB_PHASE6_ASSETS.cubePulse[page] || window.OPCB_PHASE6_ASSETS.cubePulse.terminal;
  return `<img class="opcb-utility-pulse" src="${window.OPCB_PHASE6_ASSETS.svgBase}${file}" alt="Cube Pulse">`;
};

window.opcbSetPhase6MascotState = function opcbSetPhase6MascotState(state = "terminal") {
  const container = document.getElementById("spriteContainer");
  if (!container) return;
  const file = window.OPCB_PHASE6_ASSETS.mascot[state] || window.OPCB_PHASE6_ASSETS.mascot.terminal;
  container.innerHTML = `<img class="sprite-frame active opcb-mascot-state" src="${window.OPCB_PHASE6_ASSETS.svgBase}${file}" alt="BEAST">`;
  const mascot = document.getElementById("brandMascot");
  const dot = document.getElementById("spriteStateDot");
  const alertStates = new Set(["doctor"]);
  if (mascot) mascot.dataset.state = alertStates.has(state) ? "alert" : "working";
  if (dot) dot.dataset.state = alertStates.has(state) ? "alert" : "working";
};

window.opcbUtilityIconByPage = function opcbUtilityIconByPage(page, className = "opcb-svg-icon") {
  const map = {
    terminal: "terminalConsole",
    providers: "providersHub",
    tooling: "toolingGears",
    doctor: "doctorShield",
    settings: "settingsSliders",
    source: "sourceplanDraft",
    worktrees: "worktreeBranch",
    studio: "studioDiamond"
  };
  return window.opcbPhase6Icon(map[page] || "navPolish", className);
};
