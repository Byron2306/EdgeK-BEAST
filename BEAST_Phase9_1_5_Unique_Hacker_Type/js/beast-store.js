(() => {
  const initialState = {
    booted: false,
    route: 'mission',
    connection: {
      status: 'checking',
      gatewayUrl: 'http://127.0.0.1:8000',
      localMode: false,
      demoMode: new URLSearchParams(location.search).get('demo') === '1',
      build: 'BEAST Phase 6',
      checkedAt: 0,
      error: ''
    },
    workspace: {
      root: localStorage.getItem('beast.v2.workspace.root') || '',
      files: [],
      loading: false,
      selectedPath: '',
      currentText: '',
      originalText: '',
      dirty: false,
      language: 'plaintext',
      error: '',
      indexedAt: 0
    },
    editor: {
      openTabs: [],
      activePath: '',
      dirtyPaths: [],
      recentFiles: [],
      split: false,
      explorerMode: 'tree',
      explorerTab: 'files',
      collapsedFolders: [],
      outline: [],
      cursor: { line: 1, column: 1 },
      modelCount: 0,
      owner: 'unmounted'
    },
    sourcePlan: {
      status: 'idle',
      message: 'No editor draft yet.',
      plan: null,
      lifecycle: null,
      selectedOperationIds: [],
      previewText: '',
      originalText: '',
      proposedText: '',
      activeOperationId: '',
      stale: false,
      error: '',
      verifying: false,
      applying: false,
      lastApply: null,
      updatedAt: 0
    },

    models: {
      loading: false,
      error: '',
      active: localStorage.getItem('beast.model') || 'qwen2.5-coder:7b',
      selectedId: localStorage.getItem('beast.model') || 'qwen2.5-coder:7b',
      provider: localStorage.getItem('beast.provider') || 'local_ollama',
      policy: 'Local First',
      reason: 'Prefer the smallest capable local route before escalation.',
      confidence: 94.7,
      latency: '1.24s',
      throughput: '14.2 tok/s',
      contextWindow: '32K',
      cloudAllowed: false,
      registry: [],
      runtimes: [],
      hardware: { name: 'Local CPU/GPU', vram: 'n/a', temperature: 'n/a', status: 'checking' },
      tests: [],
      rules: [
        { label: 'Prefer local models', detail: 'Always try a capable local route first', enabled: true },
        { label: 'Auto-fallback', detail: 'Fail over on error or timeout', enabled: true },
        { label: 'Context fit', detail: 'Reject routes with insufficient context', enabled: true },
        { label: 'Latency guard', detail: 'Escalate above the configured latency ceiling', enabled: true }
      ],
      lastRefreshAt: 0
    },
    agents: {
      loading: false,
      error: '',
      selectedId: '',
      sessions: [],
      orchestrator: { label: 'Mission Orchestrator', status: 'Online', health: 96 },
      handoffs: [],
      permissions: ['Evidence Read', 'Mission Write', 'Verify Only', 'Local Tools'],
      tools: ['Code Graph', 'Profiler', 'Evidence Parser', 'File System', 'Shell'],
      lastRefreshAt: 0
    },

    review: {
      loading: false,
      error: '',
      confidence: 0,
      evidenceSufficiency: 0,
      parserRobustness: 0,
      qualityScore: 0,
      gates: [],
      contradictions: [],
      risks: [],
      tests: { total: 0, passed: 0, failed: 0, skipped: 0, rows: [] },
      diff: { files: 0, additions: 0, deletions: 0, operations: 0 },
      approval: { status: 'Review in Progress', approvers: [], pending: 0 },
      selectedGateId: '',
      selectedContradictionId: '',
      recommendation: 'Review in Progress',
      updatedAt: 0
    },
    evidence: {
      loading: false,
      error: '',
      files: [],
      filteredIds: [],
      selectedId: '',
      selectedIds: [],
      query: '',
      filter: 'all',
      validity: 0,
      traceLinks: [],
      preview: '',
      previewPath: '',
      pack: { ready: false, selected: 0, total: 0, validationPassed: 0, generatedAt: 0, manifest: null },
      updatedAt: 0
    },
    trust: {
      loading: false,
      error: '',
      score: 0,
      status: 'Checking',
      policy: 'Local First',
      systemsTotal: 0,
      systemsHealthy: 0,
      warnings: 0,
      failedChecks: 0,
      boundary: { mode: 'Local-First', network: 'Restricted', telemetry: 'Disabled', airGap: true },
      integrity: { status: 'Checking', agents: 0, models: 0, evidence: 0, files: 0, lastChecked: '' },
      guardrails: { status: 'Checking', decisions: 0, approvals: 0, violations: 0, leastPrivilege: true },
      provenance: { rootId: 'unresolved', algorithm: 'SHA-256', signedBy: 'BEAST Operator', signedAt: 'pending', valid: false },
      canaries: [],
      controls: [],
      permissions: [],
      attestations: [],
      security: { hull: {verified:0,failed:0,status:'Checking'}, seal:{exists:false,mode:'unavailable',status:'Checking'}, passport:{policies:0,valid:false,status:'Checking'} },
      selectedControlId: '',
      updatedAt: 0
    },
    memory: {
      loading: false,
      error: '',
      records: 0,
      evidenceItems: 0,
      recallHealth: 0,
      freshness: 0,
      compactionQueue: 0,
      skillCandidates: 0,
      residueQuality: 0,
      layers: [],
      truthStores: [],
      retrievalViews: [],
      events: [],
      recallResults: [],
      query: '',
      selectedLayerId: '',
      selectedRecordId: '',
      security: { hull: {verified:0,failed:0,status:'Checking'}, seal:{exists:false,mode:'unavailable',status:'Checking'}, passport:{policies:0,valid:false,status:'Checking'} },
      updatedAt: 0
    },
    map: {
      loading: false,
      error: '',
      query: '',
      filter: 'all',
      zoom: 1,
      health: 0,
      coverage: 0,
      freshness: 0,
      consistency: 0,
      orphaned: 0,
      selectedId: '',
      nodes: [],
      edges: [],
      impact: [],
      updatedAt: 0
    },
    crystal: {
      loading: false,
      error: '',
      readiness: 0,
      immutable: false,
      selectedId: '',
      candidates: [],
      gates: [],
      chain: { blocks: 0, valid: false, headHash: 'unresolved', authority: 'BEAST', attestedAt: '' },
      lattice: { checkpoints: 0, valid: false, headHash: 'unresolved', claim: 'append-only', checkpointAt: '' },
      artifacts: [],
      events: [],
      verifying: false,
      committing: false,
      updatedAt: 0
    },

    terminal: {
      command: '',
      cwd: localStorage.getItem('beast.v2.workspace.root') || '',
      timeout: 120,
      status: 'idle',
      decision: '',
      risk: '',
      reasons: [],
      streaming: false,
      stdout: '',
      stderr: '',
      history: [],
      executions: [],
      lastReceipt: null,
      returncode: null,
      durationMs: 0,
      startedAt: 0,
      error: ''
    },
    tooling: {
      loading: false,
      error: '',
      status: 'checking',
      source: 'unresolved',
      syntax: {},
      linting: {},
      mcp: {},
      plugins: {},
      environments: [],
      catalog: {},
      servers: [],
      approvals: [],
      schemaPins: [],
      audit: [],
      executions: [],
      actions: [],
      selectedModule: 'overview',
      benchmark: null,
      raw: {},
      updatedAt: 0
    },
    doctor: {
      loading: false,
      error: '',
      score: 0,
      status: 'Checking',
      checks: [],
      routes: [],
      system: {},
      recommendations: [],
      report: {},
      lastScanAt: 0
    },
    mission: {
      id: 'M-BEAST-PHASE7-001',
      title: 'Transplant Terminal Nexus, Tooling Forge and Doctor Diagnostics into BEAST Core Shell v2',
      owner: 'Byron',
      status: 'In Progress',
      progress: 82,
      health: 96,
      confidence: 'High',
      risk: 'Low',
      metrics: { artifacts: 0, checks: 0, traces: 0, evidenceItems: 0, agents: 0 },
      path: [
        { id: 'mission', title: 'Mission', status: 'Complete' },
        { id: 'workspace', title: 'Editor Cortex', status: 'Complete' },
        { id: 'source', title: 'SourcePlan', status: 'Complete' },
        { id: 'models', title: 'Models', status: 'Complete' },
        { id: 'agents', title: 'Agents', status: 'Complete' },
        { id: 'review', title: 'Review', status: 'Complete' },
        { id: 'evidence', title: 'Evidence', status: 'Complete' },
        { id: 'trust', title: 'Trust', status: 'Complete' },
        { id: 'memory', title: 'Memory', status: 'Complete' },
        { id: 'map', title: 'Map', status: 'In Progress' },
        { id: 'crystallization', title: 'Crystal', status: 'Complete' },
        { id: 'terminal', title: 'Terminal', status: 'In Progress' },
        { id: 'tooling', title: 'Tooling', status: 'In Progress' },
        { id: 'doctor', title: 'Doctor', status: 'In Progress' }
      ],
      timeline: [],
      loading: false,
      error: '',
      lastRefreshAt: 0
    },
    actions: [],
    ledger: [
      { time: 'BOOT', label: 'Phase 6 shell armed' },
      { time: 'EDITOR', label: 'Editor Cortex and SourcePlan retained' },
      { time: 'ROUTER', label: 'Models and Agents retained' },
      { time: 'REVIEW', label: 'Review Center retained' },
      { time: 'EVIDENCE', label: 'Evidence Forge retained' },
      { time: 'TRUST', label: 'Trust Posture bridge ready' },
      { time: 'MEMORY', label: 'Memory Observatory retained' },
      { time: 'MAP', label: 'Mission Map bridge ready' },
      { time: 'CRYSTAL', label: 'Crystallization Chamber bridge ready' },
      { time: 'TERMINAL', label: 'Governed Terminal Nexus armed' },
      { time: 'TOOLING', label: 'Tooling Forge bridge ready' },
      { time: 'DOCTOR', label: 'Doctor Diagnostics queued' }
    ],
    diagnostics: {
      duplicateIds: 0,
      outletChildren: 0,
      horizontalOverflow: false,
      nestedScrollOwners: 0,
      viewport: '',
      activeEditors: 0,
      activeDiffEditors: 0
    }
  };

  let state = structuredClone(initialState);
  const listeners = new Set();
  let pending = false;

  function emit() {
    if (pending) return;
    pending = true;
    queueMicrotask(() => {
      pending = false;
      listeners.forEach(listener => {
        try { listener(state); } catch (error) { console.error('[BEAST Store]', error); }
      });
      document.dispatchEvent(new CustomEvent('beast:state', { detail: state }));
    });
  }

  function get() { return state; }

  function set(path, value) {
    const parts = Array.isArray(path) ? path : String(path).split('.');
    const next = structuredClone(state);
    let cursor = next;
    for (let index = 0; index < parts.length - 1; index += 1) {
      const key = parts[index];
      cursor[key] = cursor[key] ?? {};
      cursor = cursor[key];
    }
    cursor[parts.at(-1)] = typeof value === 'function' ? value(cursor[parts.at(-1)], next) : value;
    state = next;
    emit();
    return state;
  }

  function patch(path, partial) {
    const parts = Array.isArray(path) ? path : String(path).split('.');
    const next = structuredClone(state);
    let cursor = next;
    for (const key of parts) {
      cursor[key] = cursor[key] ?? {};
      cursor = cursor[key];
    }
    Object.assign(cursor, partial);
    state = next;
    emit();
    return state;
  }

  function transaction(mutator) {
    const next = structuredClone(state);
    mutator(next);
    state = next;
    emit();
    return state;
  }

  function subscribe(listener, options = {}) {
    listeners.add(listener);
    if (options.immediate !== false) listener(state);
    return () => listeners.delete(listener);
  }

  function addLedger(label, time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })) {
    transaction(next => {
      next.ledger = [{ time, label }, ...next.ledger].slice(0, 30);
    });
  }

  window.BeastStore = { get, set, patch, transaction, subscribe, addLedger };
})();
