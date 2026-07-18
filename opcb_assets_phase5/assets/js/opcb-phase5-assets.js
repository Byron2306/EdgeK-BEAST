// OPCB Phase 5 Assets: Map + Memory helpers.

window.OPCB_PHASE5_ASSETS = {
  svgBase: "assets/svg/",
  icons: {
    mapCanvas: "map-canvas.svg",
    graphNodeEntry: "graph-node-entry.svg",
    graphNodeParser: "graph-node-parser.svg",
    graphNodeDetector: "graph-node-detector.svg",
    graphNodeValidator: "graph-node-validator.svg",
    graphNodeStore: "graph-node-store.svg",
    graphNodeAgent: "graph-node-agent.svg",
    graphNodeTest: "graph-node-test.svg",
    graphNodeDocs: "graph-node-docs.svg",
    graphNodeConfig: "graph-node-config.svg",
    graphNodeExternal: "graph-node-external.svg",
    edgeCalls: "edge-calls.svg",
    edgeDepends: "edge-depends.svg",
    edgeProduces: "edge-produces.svg",
    mapSearch: "map-search.svg",
    mapFilter: "map-filter.svg",
    mapHealth: "map-health.svg",
    dependencyImpact: "dependency-impact.svg",
    orphanNode: "orphan-node.svg",
    pathFocus: "path-focus.svg",

    memoryObservatory: "memory-observatory.svg",
    memoryArchive: "memory-archive.svg",
    recallQuery: "recall-query.svg",
    recallHealth: "recall-health.svg",
    residueQuality: "residue-quality.svg",
    skillTree: "skill-tree.svg",
    memoryFreshness: "memory-freshness.svg",
    compactionQueue: "compaction-queue.svg",
    memoryGraph: "memory-graph.svg",
    reuseSuggestion: "reuse-suggestion.svg",
    decayMeter: "decay-meter.svg",
    retentionLock: "retention-lock.svg",
    promoteSkill: "promote-skill.svg",
    memoryEvent: "memory-event.svg",
    sourceLinked: "source-linked.svg"
  },
  heroes: {
    map: "map-graph-hero.svg",
    memory: "memory-cube-hero.svg"
  },
  cubePulse: {
    map: "cube-pulse-map.svg",
    memory: "cube-pulse-memory.svg"
  },
  mascot: {
    map: "mascot-map.svg",
    memory: "mascot-memory.svg",
    recall: "mascot-recall.svg"
  }
};

window.opcbPhase5Icon = function opcbPhase5Icon(name, className = "opcb-svg-icon") {
  const file = window.OPCB_PHASE5_ASSETS.icons[name] || name;
  return `<img class="${className}" src="${window.OPCB_PHASE5_ASSETS.svgBase}${file}" alt="">`;
};

window.opcbPhase5Hero = function opcbPhase5Hero(page = "map") {
  const file = window.OPCB_PHASE5_ASSETS.heroes[page] || window.OPCB_PHASE5_ASSETS.heroes.map;
  const klass = page === "memory" ? "opcb-memory-hero" : "opcb-map-hero";
  return `<img class="${klass}" src="${window.OPCB_PHASE5_ASSETS.svgBase}${file}" alt="">`;
};

window.opcbPhase5Pulse = function opcbPhase5Pulse(page = "map") {
  const file = window.OPCB_PHASE5_ASSETS.cubePulse[page] || window.OPCB_PHASE5_ASSETS.cubePulse.map;
  const klass = page === "memory" ? "opcb-memory-pulse" : "opcb-map-pulse";
  return `<img class="${klass}" src="${window.OPCB_PHASE5_ASSETS.svgBase}${file}" alt="Cube Pulse">`;
};

window.opcbSetPhase5MascotState = function opcbSetPhase5MascotState(state = "map") {
  const container = document.getElementById("spriteContainer");
  if (!container) return;
  const file = window.OPCB_PHASE5_ASSETS.mascot[state] || window.OPCB_PHASE5_ASSETS.mascot.map;
  container.innerHTML = `<img class="sprite-frame active opcb-mascot-state" src="${window.OPCB_PHASE5_ASSETS.svgBase}${file}" alt="BEAST">`;
  const mascot = document.getElementById("brandMascot");
  const dot = document.getElementById("spriteStateDot");
  if (mascot) mascot.dataset.state = state === "recall" ? "finished" : "working";
  if (dot) dot.dataset.state = state === "recall" ? "finished" : "working";
};

window.opcbNodeIconByType = function opcbNodeIconByType(type, className = "opcb-svg-icon") {
  const map = {
    entry: "graphNodeEntry",
    parser: "graphNodeParser",
    detector: "graphNodeDetector",
    validator: "graphNodeValidator",
    store: "graphNodeStore",
    database: "graphNodeStore",
    agent: "graphNodeAgent",
    test: "graphNodeTest",
    docs: "graphNodeDocs",
    document: "graphNodeDocs",
    config: "graphNodeConfig",
    external: "graphNodeExternal",
    orphan: "orphanNode"
  };
  return window.opcbPhase5Icon(map[type] || "mapCanvas", className);
};
