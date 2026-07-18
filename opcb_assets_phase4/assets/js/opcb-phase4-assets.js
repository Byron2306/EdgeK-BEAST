// OPCB Phase 4 Assets: Models + Agents helpers.

window.OPCB_PHASE4_ASSETS = {
  svgBase: "assets/svg/",
  icons: {
    modelsRoute: "models-route.svg",
    fallbackLadder: "fallback-ladder.svg",
    localModel: "local-model.svg",
    runtimeReady: "runtime-ready.svg",
    hardwareChip: "hardware-chip.svg",
    gpuCore: "gpu-core.svg",
    cpuStack: "cpu-stack.svg",
    benchmarkBars: "benchmark-bars.svg",
    policyRoute: "policy-route.svg",
    providerGateway: "provider-gateway.svg",
    routeTest: "route-test.svg",
    modelRack: "model-rack.svg",
    routeExplain: "route-explain.svg",

    agentsSquad: "agents-squad.svg",
    agentPlanner: "agent-planner.svg",
    agentVerifier: "agent-verifier.svg",
    agentGraph: "agent-graph.svg",
    agentProfiler: "agent-profiler.svg",
    agentPatch: "agent-patch.svg",
    agentMemory: "agent-memory.svg",
    toolBinding: "tool-binding.svg",
    handoffQueue: "handoff-queue.svg",
    activityPulse: "activity-pulse.svg",
    permissionsAgent: "permissions-agent.svg",
    agentOnline: "agent-online.svg",
    taskStream: "task-stream.svg"
  },
  cubePulse: {
    models: "cube-pulse-models.svg",
    agents: "cube-pulse-agents.svg"
  },
  mascot: {
    models: "mascot-models.svg",
    agents: "mascot-agents.svg",
    assign: "mascot-assign.svg"
  }
};

window.opcbPhase4Icon = function opcbPhase4Icon(name, className = "opcb-svg-icon") {
  const file = window.OPCB_PHASE4_ASSETS.icons[name] || name;
  return `<img class="${className}" src="${window.OPCB_PHASE4_ASSETS.svgBase}${file}" alt="">`;
};

window.opcbPhase4Pulse = function opcbPhase4Pulse(page = "models") {
  const file = window.OPCB_PHASE4_ASSETS.cubePulse[page] || window.OPCB_PHASE4_ASSETS.cubePulse.models;
  const klass = page === "agents" ? "opcb-agents-pulse" : "opcb-models-pulse";
  return `<img class="${klass}" src="${window.OPCB_PHASE4_ASSETS.svgBase}${file}" alt="Cube Pulse">`;
};

window.opcbSetPhase4MascotState = function opcbSetPhase4MascotState(state = "models") {
  const container = document.getElementById("spriteContainer");
  if (!container) return;
  const file = window.OPCB_PHASE4_ASSETS.mascot[state] || window.OPCB_PHASE4_ASSETS.mascot.models;
  container.innerHTML = `<img class="sprite-frame active opcb-mascot-state" src="${window.OPCB_PHASE4_ASSETS.svgBase}${file}" alt="BEAST">`;
  const mascot = document.getElementById("brandMascot");
  const dot = document.getElementById("spriteStateDot");
  if (mascot) mascot.dataset.state = state === "assign" ? "finished" : "working";
  if (dot) dot.dataset.state = state === "assign" ? "finished" : "working";
};
