(() => {
  const initialState = {
    booted: false,
    route: 'mission',
    runtime: { mode:'offline', gatewayUrl:'http://127.0.0.1:8101', desktopCapabilities:{}, inFlight:0, errors:[], lastProbeAt:0, visible:true },
    connection: {
      status: 'checking',
      gatewayUrl: 'http://127.0.0.1:8101',
      localMode: false,
      demoMode: window.BEAST_ENABLE_DEMO === true && new URLSearchParams(location.search).get('demo') === '1',
      build: 'unverified',
      checkedAt: 0,
      error: ''
    },
    workspace: {
      root: localStorage.getItem('beast.v2.workspace.root') || '',
      executionTarget: (() => { try { const value=JSON.parse(localStorage.getItem('beast.v2.workspace.execution-target')||'{"kind":"local"}');return ['local','ssh','container'].includes(value?.kind)?value:{kind:'local'}; } catch (_) { return {kind:'local'}; } })(),
      roots: (() => { try { const rows=JSON.parse(localStorage.getItem('beast.v2.workspace.folders')||'[]'); return Array.isArray(rows)?rows:[]; } catch (_) { return []; } })(),
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
      activeGroupId: 'group_primary',
      editorGroups: null,
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
    aiCoding: {
      open: false,
      expanded: false,
      mode: 'agent',
      prompt: '',
      sessionId: '',
      streaming: false,
      status: 'idle',
      error: '',
      messages: [],
      trace: [],
      contextFiles: [],
      contextSuggestions: [],
      contextSuggestionStatus: 'idle',
      selection: null,
      provider: localStorage.getItem('beast.provider') || '',
      model: localStorage.getItem('beast.model') || '',
      crystal: { action:'', source:'', confidence:0, reused:false, avoidedTokens:0, decisionId:'', recorded:false, candidate:false },
      compute: { selectedFiles:0, readableFiles:0, sourceChars:0, suppliedChars:0, truncatedFiles:0, policy:'', kvCache:'', crystal:'', historyOriginalTokens:0, historyFinalTokens:0, historyChanged:false },
      sourcePlanReady: false,
      sourcePlanId: '',
      activeRunId: '',
      activeRunSequence: 0,
      updatedAt: 0
    },

    models: {
      loading: false,
      error: '',
      active: localStorage.getItem('beast.model') || '',
      selectedId: localStorage.getItem('beast.model') || '',
      provider: localStorage.getItem('beast.provider') || '',
      policy: 'Unverified',
      reason: 'Awaiting live provider policy.',
      confidence: 0,
      latency: 'not measured',
      throughput: 'not measured',
      contextWindow: 'unreported',
      cloudAllowed: false,
      registry: [],
      runtimes: [],
      hardware: { name: 'Unreported', vram: 'n/a', temperature: 'n/a', status: 'checking' },
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
      orchestrator: { label: 'Swarm unavailable', status: 'Unverified', health: 0 },
      handoffs: [],
      swarmProof: { runId:'', status:'not reported', metrics:[], events:[], updatedAt:0 },
      goldenPath: { status:'not run', timeline:[], result:null, updatedAt:0 },
      permissions: [],
      tools: [],
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
    system: {
      loading: false,
      error: '',
      score: 0,
      status: 'Checking',
      cpu: 0,
      memory: 0,
      disk: 0,
      network: 0,
      ports: [],
      processes: [],
      environment: [],
      prec: { stage: 'Discover', health: 0, traces: 0 },
      runtime: { status: 'checking', circuits: 0 },
      updatedAt: 0
    },
    platform: {
      loading: false,
      error: '',
      status: 'checking',
      health: 0,
      summary: {},
      sections: [],
      snapshots: {},
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
      chatPrompt: '',
      chatOutput: '',
      chatTrace: [],
      chatStatus: 'idle',
      chatStreaming: false,
      chatSessionId: '',
      selectedModel: localStorage.getItem('beast.model') || '',
      selectedProvider: localStorage.getItem('beast.provider') || '',
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
      capabilities: [],
      selectedModule: 'overview',
      benchmark: null,
      raw: {},
      updatedAt: 0
    },
    compatibility: {
      loading: false,
      error: '',
      source: 'unresolved',
      summary: { available: 0, total: 0, coverage: 0 },
      extensionHost: { available:false, companion:false, status:'checking' },
      languages: [],
      debug: [],
      notebooks: [],
      remote: [],
      sessions: [],
      activeLanguage: '',
      diagnostics: {},
      runtime: {
        debug: { status:'idle', error:'', sessionId:'', program:'', breakpoints:[], output:[], threads:[], stack:[], scopes:[], threadId:0 },
        notebook: { status:'idle', error:'', cells:[], lastReceipt:null },
        remote: { status:'idle', error:'', host:'', path:'~', remoteRoot:'', verification:'', files:[] },
      },
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
      id: 'UNASSIGNED',
      title: 'Awaiting live mission',
      owner: 'Unverified',
      status: 'Awaiting live data',
      progress: 0,
      health: 0,
      confidence: 'Unverified',
      risk: 'Low',
      draftObjective: localStorage.getItem('beast.mission.draft') || '',
      metrics: { artifacts: 0, checks: 0, traces: 0, evidenceItems: 0, agents: 0 },
      path: [
        { id: 'mission', title: 'Mission', status: 'Unverified' },
        { id: 'workspace', title: 'Editor Cortex', status: 'Unverified' },
        { id: 'source', title: 'SourcePlan', status: 'Unverified' },
        { id: 'models', title: 'Models', status: 'Unverified' },
        { id: 'agents', title: 'Agents', status: 'Unverified' },
        { id: 'review', title: 'Review', status: 'Unverified' },
        { id: 'evidence', title: 'Evidence', status: 'Unverified' },
        { id: 'trust', title: 'Trust', status: 'Unverified' },
        { id: 'memory', title: 'Memory', status: 'Unverified' },
        { id: 'map', title: 'Map', status: 'Unverified' },
        { id: 'crystallization', title: 'Crystal', status: 'Unverified' },
        { id: 'terminal', title: 'Terminal', status: 'Unverified' },
        { id: 'tooling', title: 'Tooling', status: 'Unverified' },
        { id: 'doctor', title: 'Doctor', status: 'Unverified' }
      ],
      timeline: [],
      loading: false,
      error: '',
      lastRefreshAt: 0
    },
    actions: [],
    ledger: [],
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
  let pendingHandle = 0;

  function cloneContainer(value) {
    if (Array.isArray(value)) return value.slice();
    if (value && typeof value === 'object') return { ...value };
    return value;
  }

  // Most UI updates touch one small branch. Clone only that path so telemetry
  // cannot repeatedly copy editor buffers, chat history, and model metadata.
  function clonePath(parts) {
    const next = { ...state };
    let source = state;
    let target = next;
    for (let index = 0; index < parts.length - 1; index += 1) {
      const key = parts[index];
      const child = cloneContainer(source?.[key]);
      target[key] = child;
      source = source?.[key];
      target = child;
    }
    return { next, target };
  }

  function emit() {
    if (pending) return;
    pending = true;
    const flush = () => {
      pendingHandle = 0;
      pending = false;
      listeners.forEach(listener => {
        try { listener(state); } catch (error) { console.error('[BEAST Store]', error); }
      });
      document.dispatchEvent(new CustomEvent('beast:state', { detail: state }));
    };
    if (typeof requestAnimationFrame === 'function') pendingHandle = requestAnimationFrame(flush);
    else pendingHandle = setTimeout(flush, 16);
  }

  function get() { return state; }

  function set(path, value) {
    const parts = Array.isArray(path) ? path : String(path).split('.');
    const { next, target } = clonePath(parts);
    const key = parts.at(-1);
    const previous = target?.[key];
    const resolved = typeof value === 'function' ? value(previous, next) : value;
    if (Object.is(previous, resolved)) return state;
    target[key] = resolved;
    state = next;
    emit();
    return state;
  }

  function patch(path, partial) {
    const parts = Array.isArray(path) ? path : String(path).split('.');
    const { next, target } = clonePath(parts);
    const key = parts.at(-1);
    const current = cloneContainer(target[key]) || {};
    if (partial && typeof partial === 'object' && Object.keys(partial).every(name => Object.is(current[name], partial[name]))) return state;
    target[key] = current;
    Object.assign(current, partial);
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
