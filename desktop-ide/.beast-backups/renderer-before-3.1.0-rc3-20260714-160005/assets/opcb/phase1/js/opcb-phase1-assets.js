// OPCB Phase 1 Assets: Workspace + Mission helpers.
// Drop this after app.js if you want quick icon/background injection.

window.OPCB_ASSETS = {
  svgBase: "assets/svg/",
  icons: {
    workspace: "workspace-flow.svg",
    mission: "mission-target.svg",
    models: "models-cube.svg",
    agents: "agents-bot.svg",
    tools: "tools-crossed.svg",
    review: "review-lens.svg",
    evidence: "evidence-doc.svg",
    crystallization: "crystal-diamond.svg",
    health: "health-ring.svg",
    nextAction: "next-action-bolt.svg",
    approval: "approval-gate.svg",
    timeline: "timeline-node.svg"
  },
  cubePulse: {
    workspace: "cube-pulse-workspace.svg",
    mission: "cube-pulse-mission.svg"
  },
  mascot: {
    idle: "mascot-idle.svg",
    working: "mascot-working.svg",
    alert: "mascot-alert.svg",
    success: "mascot-success.svg"
  }
};

window.opcbIcon = function opcbIcon(name, className = "opcb-svg-icon") {
  const file = window.OPCB_ASSETS.icons[name] || name;
  return `<img class="${className}" src="${window.OPCB_ASSETS.svgBase}${file}" alt="">`;
};

window.opcbCubePulse = function opcbCubePulse(page = "workspace") {
  const file = window.OPCB_ASSETS.cubePulse[page] || window.OPCB_ASSETS.cubePulse.workspace;
  return `<img class="opcb-cube-pulse-asset" src="${window.OPCB_ASSETS.svgBase}${file}" alt="Cube Pulse">`;
};

window.opcbSetPageArt = function opcbSetPageArt(page) {
  document.querySelectorAll(".opcb-page-art").forEach(el => el.remove());
  const host = document.querySelector(`[data-page-panel="${page}"]`);
  if (!host) return;
  host.style.position = host.style.position || "relative";
  const art = document.createElement("div");
  art.className = `opcb-page-art ${page}`;
  host.prepend(art);
};

window.opcbSetMascotState = function opcbSetMascotState(state = "idle") {
  const container = document.getElementById("spriteContainer");
  if (!container) return;
  const file = window.OPCB_ASSETS.mascot[state] || window.OPCB_ASSETS.mascot.idle;
  container.innerHTML = `<img class="sprite-frame active opcb-mascot-state" src="${window.OPCB_ASSETS.svgBase}${file}" alt="BEAST">`;
  const mascot = document.getElementById("brandMascot");
  const dot = document.getElementById("spriteStateDot");
  if (mascot) mascot.dataset.state = state;
  if (dot) dot.dataset.state = state;
};
