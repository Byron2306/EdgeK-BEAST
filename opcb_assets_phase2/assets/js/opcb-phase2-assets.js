// OPCB Phase 2 Assets: Review + Evidence helpers.
// Load after phase 1 helpers, or use standalone with the same assets/svg path.

window.OPCB_PHASE2_ASSETS = {
  svgBase: "assets/svg/",
  icons: {
    reviewCenter: "review-center.svg",
    qualityGate: "quality-gate.svg",
    contradiction: "contradiction-alert.svg",
    riskBlocker: "risk-blocker.svg",
    diffReview: "diff-review.svg",
    testSummary: "test-summary.svg",
    approvalWorkflow: "approval-workflow.svg",
    approver: "approver.svg",
    reviewNotes: "review-notes.svg",
    reportExport: "report-export.svg",
    evidenceLibrary: "evidence-library.svg",
    selectedEvidence: "selected-evidence.svg",
    schemaValid: "schema-valid.svg",
    traceLink: "trace-link.svg",
    validationSummary: "validation-summary.svg",
    exportEvidence: "export-evidence.svg",
    auditPack: "audit-pack.svg",
    extractFields: "extract-fields.svg",
    completeness: "completeness.svg",
    openFile: "open-file.svg",
    download: "download.svg",
    searchFilter: "search-filter.svg"
  },
  fileTypes: {
    md: "file-md.svg",
    markdown: "file-md.svg",
    json: "file-json.svg",
    yaml: "file-yaml.svg",
    yml: "file-yaml.svg",
    csv: "file-csv.svg",
    html: "file-html.svg",
    zip: "file-zip.svg",
    log: "file-log.svg",
    db: "file-db.svg",
    sqlite: "file-db.svg",
    sqlite3: "file-db.svg",
    pcap: "file-pcap.svg",
    ndjson: "file-ndjson.svg"
  },
  cubePulse: {
    review: "cube-pulse-review.svg",
    evidence: "cube-pulse-evidence.svg"
  },
  mascot: {
    review: "mascot-review.svg",
    evidence: "mascot-evidence.svg",
    blocked: "mascot-blocked.svg"
  }
};

window.opcbPhase2Icon = function opcbPhase2Icon(name, className = "opcb-svg-icon") {
  const file = window.OPCB_PHASE2_ASSETS.icons[name] || name;
  return `<img class="${className}" src="${window.OPCB_PHASE2_ASSETS.svgBase}${file}" alt="">`;
};

window.opcbFileIcon = function opcbFileIcon(ext = "md", className = "opcb-file-icon") {
  const key = String(ext).toLowerCase().replace(/^\./, "");
  const file = window.OPCB_PHASE2_ASSETS.fileTypes[key] || "selected-evidence.svg";
  return `<img class="${className}" src="${window.OPCB_PHASE2_ASSETS.svgBase}${file}" alt="">`;
};

window.opcbPhase2Pulse = function opcbPhase2Pulse(page = "review") {
  const file = window.OPCB_PHASE2_ASSETS.cubePulse[page] || window.OPCB_PHASE2_ASSETS.cubePulse.review;
  const klass = page === "evidence" ? "opcb-evidence-pulse" : "opcb-review-pulse";
  return `<img class="${klass}" src="${window.OPCB_PHASE2_ASSETS.svgBase}${file}" alt="Cube Pulse">`;
};

window.opcbSetPhase2MascotState = function opcbSetPhase2MascotState(state = "review") {
  const container = document.getElementById("spriteContainer");
  if (!container) return;
  const file = window.OPCB_PHASE2_ASSETS.mascot[state] || window.OPCB_PHASE2_ASSETS.mascot.review;
  container.innerHTML = `<img class="sprite-frame active opcb-mascot-state" src="${window.OPCB_PHASE2_ASSETS.svgBase}${file}" alt="BEAST">`;
  const mascot = document.getElementById("brandMascot");
  const dot = document.getElementById("spriteStateDot");
  if (mascot) mascot.dataset.state = state === "blocked" ? "alert" : "working";
  if (dot) dot.dataset.state = state === "blocked" ? "alert" : "working";
};
