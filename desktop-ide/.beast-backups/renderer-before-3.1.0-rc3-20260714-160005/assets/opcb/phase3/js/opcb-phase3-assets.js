// OPCB Phase 3 Assets: Crystallization + Trust helpers.
// Load after Phase 1/2 helpers, or use standalone with assets/svg path.

window.OPCB_PHASE3_ASSETS = {
  svgBase: "assets/svg/",
  icons: {
    crystalChamber: "crystal-chamber.svg",
    crystalCandidate: "crystal-candidate.svg",
    crystalReady: "crystal-ready.svg",
    crystalSeal: "crystal-seal.svg",
    immutableLock: "immutable-lock.svg",
    artifactCommit: "artifact-commit.svg",
    eventLedger: "event-ledger.svg",
    qualityPrism: "quality-prism.svg",
    crystalExport: "crystal-export.svg",

    trustShield: "trust-shield.svg",
    trustPosture: "trust-posture.svg",
    dataBoundary: "data-boundary.svg",
    integrityCheck: "integrity-check.svg",
    policyGuardrail: "policy-guardrail.svg",
    fingerprint: "fingerprint.svg",
    canaryStatus: "canary-status.svg",
    attestation: "attestation.svg",
    auditTimeline: "audit-timeline.svg",
    localFirst: "local-first.svg",
    permissionsLock: "permissions-lock.svg",
    provenanceChain: "provenance-chain.svg",
    trustReport: "trust-report.svg"
  },
  crystalHero: {
    idle: "crystal-chamber-idle.svg",
    ready: "crystal-chamber-ready.svg",
    committed: "crystal-chamber-committed.svg"
  },
  cubePulse: {
    crystallization: "cube-pulse-crystal.svg",
    crystal: "cube-pulse-crystal.svg",
    trust: "cube-pulse-trust.svg"
  },
  mascot: {
    crystal: "mascot-crystal.svg",
    trust: "mascot-trust.svg",
    sealed: "mascot-sealed.svg"
  }
};

window.opcbPhase3Icon = function opcbPhase3Icon(name, className = "opcb-svg-icon") {
  const file = window.OPCB_PHASE3_ASSETS.icons[name] || name;
  return `<img class="${className}" src="${window.OPCB_PHASE3_ASSETS.svgBase}${file}" alt="">`;
};

window.opcbCrystalHero = function opcbCrystalHero(state = "idle") {
  const file = window.OPCB_PHASE3_ASSETS.crystalHero[state] || window.OPCB_PHASE3_ASSETS.crystalHero.idle;
  return `<img class="opcb-crystal-hero ${state}" src="${window.OPCB_PHASE3_ASSETS.svgBase}${file}" alt="Crystal Chamber">`;
};

window.opcbPhase3Pulse = function opcbPhase3Pulse(page = "crystallization") {
  const file = window.OPCB_PHASE3_ASSETS.cubePulse[page] || window.OPCB_PHASE3_ASSETS.cubePulse.crystallization;
  const klass = page === "trust" ? "opcb-trust-pulse" : "opcb-crystal-pulse";
  return `<img class="${klass}" src="${window.OPCB_PHASE3_ASSETS.svgBase}${file}" alt="Cube Pulse">`;
};

window.opcbSetPhase3MascotState = function opcbSetPhase3MascotState(state = "crystal") {
  const container = document.getElementById("spriteContainer");
  if (!container) return;
  const file = window.OPCB_PHASE3_ASSETS.mascot[state] || window.OPCB_PHASE3_ASSETS.mascot.crystal;
  container.innerHTML = `<img class="sprite-frame active opcb-mascot-state" src="${window.OPCB_PHASE3_ASSETS.svgBase}${file}" alt="BEAST">`;
  const mascot = document.getElementById("brandMascot");
  const dot = document.getElementById("spriteStateDot");
  if (mascot) mascot.dataset.state = state === "sealed" ? "finished" : "working";
  if (dot) dot.dataset.state = state === "sealed" ? "finished" : "working";
};
