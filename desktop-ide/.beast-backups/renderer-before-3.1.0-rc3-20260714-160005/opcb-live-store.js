(function () {
  const dashboardPages = new Set([
    'workspace',
    'mission',
    'models',
    'agents',
    'review',
    'evidence',
    'trust',
    'memory',
    'map',
    'crystallization',
    'doctor'
  ]);

  const requiredGatewayRoutes = [
    { id: 'root', path: '/edgek/root-info', method: 'GET', required: true },
    { id: 'ide_snapshot', path: '/edgek/ide/snapshot', method: 'GET', root: true, required: true, params: { objective: 'desktop-health' } },
    { id: 'actions_manifest', path: '/edgek/ide/actions/manifest', method: 'GET', required: true },
    { id: 'tooling_snapshot', path: '/edgek/ide/tooling-snapshot', method: 'GET', root: true, required: true },
    { id: 'system_snapshot', path: '/edgek/ide/system-snapshot', method: 'GET', root: true, required: true, params: { port_limit: '10', process_limit: '10' } },
    { id: 'mcp_state', path: '/edgek/mcp/state', method: 'GET', required: true },
    { id: 'plugins', path: '/edgek/plugins', method: 'GET', required: true },
    { id: 'tools_integrations', path: '/edgek/tools/integrations', method: 'GET', required: false },
    { id: 'workspace_files', path: '/edgek/workspace/files', method: 'GET', root: true, required: false, params: { limit: '10' } },
    { id: 'mcp_servers', path: '/edgek/mcp/servers', method: 'GET', required: false },
    { id: 'mcp_approvals', path: '/edgek/mcp/approvals', method: 'GET', required: false, params: { limit: '20' } }
  ];

  const pageRoutes = {
    workspace: ['ide_snapshot', 'workspace_files', 'actions_manifest'],
    mission: ['ide_snapshot', 'actions_manifest'],
    models: ['ide_snapshot', 'tooling_snapshot', 'tools_integrations'],
    agents: ['ide_snapshot', 'tooling_snapshot'],
    review: ['ide_snapshot', 'actions_manifest'],
    evidence: ['ide_snapshot', 'workspace_files'],
    crystallization: ['ide_snapshot', 'actions_manifest'],
    trust: ['ide_snapshot', 'system_snapshot'],
    memory: ['ide_snapshot', 'mcp_state'],
    map: ['ide_snapshot', 'workspace_files'],
    doctor: []
  };

  const store = {
    gateway: {
      ok: false,
      checkedAt: 0,
      url: '',
      status: null,
      routes: {}
    },
    pages: {},
    loading: {},
    errors: {},
    applied: {}
  };

  function workspaceRoot() {
    return window.workspaceRoot || window.lastGatewayStatus?.repoRoot || '';
  }

  function routeUrl(baseUrl, route) {
    const url = new URL(route.path, baseUrl);
    if (route.root && workspaceRoot()) url.searchParams.set('root_path', workspaceRoot());
    Object.entries(route.params || {}).forEach(([key, value]) => url.searchParams.set(key, value));
    if (route.id === 'workspace_files' && !url.searchParams.has('limit')) url.searchParams.set('limit', '10');
    if (route.id === 'workspace_graph') {
      url.searchParams.set('node_limit', '80');
      url.searchParams.set('edge_limit', '160');
    }
    if (route.id === 'evidence_bus' || route.id === 'evidence_summary') url.searchParams.set('limit', '25');
    if (route.id === 'mission_route') {
      url.searchParams.set('objective', window.opcbState?.mission?.title || 'Use Code Graph and Profiler to plan local evidence parser');
    }
    return url.toString();
  }

  async function fetchJson(url, options = {}) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), options.timeoutMs || 3500);
    try {
      const response = await fetch(url, { signal: controller.signal, method: options.method || 'GET' });
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`.trim());
      return await response.json();
    } finally {
      window.clearTimeout(timeout);
    }
  }

  async function refreshGatewayContract() {
    const status = await window.beastDesktop?.status?.();
    const gatewayUrl = status?.gatewayUrl || window.gatewayUrl || 'http://127.0.0.1:8000';
    const routeResults = {};
    await Promise.all(requiredGatewayRoutes.map(async route => {
      try {
        const payload = await fetchJson(routeUrl(gatewayUrl, route), { method: route.method, timeoutMs: 2500 });
        routeResults[route.id] = { ok: true, path: route.path, required: route.required !== false, payload };
      } catch (error) {
        routeResults[route.id] = { ok: false, path: route.path, required: route.required !== false, error: String(error.message || error) };
      }
    }));
    store.gateway = {
      ok: Boolean(status?.health?.ok && status?.health?.capabilities?.ok !== false),
      checkedAt: Date.now(),
      url: gatewayUrl,
      status,
      routes: routeResults
    };
    normalizeGatewayDoctor(store.gateway);
    return store.gateway;
  }

  function firstArray(...values) {
    return values.find(value => Array.isArray(value)) || [];
  }

  function numberFrom(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function percentFrom(value, fallback = 0) {
    const parsed = numberFrom(value, fallback);
    return Math.max(0, Math.min(100, Math.round(parsed <= 1 ? parsed * 100 : parsed)));
  }

  function countFrom(value, fallback = 0) {
    if (Array.isArray(value)) return value.length;
    if (value && typeof value === 'object') return Object.keys(value).length;
    return numberFrom(value, fallback);
  }

  function firstObject(...values) {
    return values.find(value => value && typeof value === 'object' && !Array.isArray(value)) || {};
  }

  function labelFrom(value, fallback = '') {
    if (typeof value === 'string') return value;
    if (value && typeof value === 'object') return String(value.label || value.name || value.id || value.model || value.provider || fallback);
    return fallback;
  }

  function normalizeGatewayDoctor(gateway = store.gateway) {
    if (!window.opcbState) return false;
    const routes = Object.entries(gateway.routes || {}).map(([id, result]) => ({
      id,
      path: result.path || '',
      ok: Boolean(result.ok),
      required: result.required !== false,
      error: result.error || ''
    }));
    const requiredRoutes = routes.filter(route => route.required !== false);
    const passed = requiredRoutes.filter(route => route.ok).length;
    const optionalRoutes = routes.filter(route => route.required === false);
    window.opcbState.gatewayDoctor = {
      ok: Boolean(gateway.ok && requiredRoutes.every(route => route.ok)),
      url: gateway.url || window.gatewayUrl || '',
      checkedAt: gateway.checkedAt ? new Date(gateway.checkedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : 'not checked',
      mode: gateway.status?.health?.capabilities?.mode || gateway.status?.health?.mode || 'contract_probe',
      pid: gateway.status?.pid || gateway.status?.gatewayPid || '',
      port: gateway.status?.port || '',
      localMode: Boolean(gateway.status?.health?.local_mode),
      passed,
      total: requiredRoutes.length,
      optionalPassed: optionalRoutes.filter(route => route.ok).length,
      optionalTotal: optionalRoutes.length,
      routes
    };
    window.opcbRefreshReadiness?.({ runRelease: false }).catch(() => {});
    return true;
  }

  function normalizeMission(snapshot = {}, route = {}, timeline = {}) {
    if (!window.opcbState?.mission) return false;
    const mission = window.opcbState.mission;
    mission.title = snapshot.objective || mission.title;
    mission.id = snapshot.mission_cockpit?.mission_id || snapshot.mission_id || mission.id;
    const receipts = firstArray(snapshot.evidence_bus?.receipts, snapshot.evidence_bus?.items);
    const agents = firstArray(snapshot.agent_sessions?.sessions, snapshot.agent_sessions, snapshot.sessions);
    const graphNodes = firstArray(snapshot.code_cortex?.nodes, snapshot.code_cortex?.files);
    mission.metrics = {
      artifacts: countFrom(snapshot.evidence_bus?.total, receipts.length || mission.metrics?.artifacts),
      checks: countFrom(snapshot.policy?.architecture_decisions?.decision_count, mission.metrics?.checks),
      traces: countFrom(snapshot.mission_lattice?.nodes, graphNodes.length || mission.metrics?.traces),
      evidenceItems: countFrom(snapshot.workspace_files?.files, receipts.length || mission.metrics?.evidenceItems),
      agents: agents.length || mission.metrics?.agents
    };
    const routeSteps = firstArray(route.steps, route.route, route.faces);
    if (routeSteps.length) {
      const ids = ['mission', 'models', 'agents', 'workspace', 'review', 'evidence', 'crystallization'];
      mission.path = routeSteps.slice(0, ids.length).map((step, index) => ({
        id: ids[index],
        title: String(step.title || step.face || step.name || mission.path?.[index]?.title || ids[index]),
        status: step.status || mission.path?.[index]?.status || (index < 4 ? 'Complete' : index === 4 ? 'In Progress' : 'Pending')
      }));
    }
    const events = firstArray(timeline.events, timeline.timeline, timeline.items);
    if (events.length) {
      mission.timeline = events.slice(0, 6).map(event => ({
        label: event.label || event.title || event.kind || 'Mission event',
        time: event.time || event.timestamp || event.created_at || ''
      }));
    }
    const health = snapshot.mission_cockpit?.health || snapshot.policy?.reintegration_health;
    if (health && typeof health === 'object') {
      mission.health = percentFrom(health.score ?? health.overall ?? health.health, mission.health);
      mission.confidence = health.confidence || mission.confidence;
      mission.risk = health.risk || mission.risk;
    }
    return true;
  }

  function normalizeWorkspace(snapshot = {}, files = {}, route = {}) {
    const appliedMission = normalizeMission(snapshot, route, {});
    const rows = firstArray(files.files, files.items, files.entries);
    if (rows.length && window.opcbState?.workspace) {
      window.opcbState.workspace.files = rows.slice(0, 24).map(row => ({
        name: String(row.path || row.name || row.file || '').split('/').pop(),
        path: row.path || row.name || row.file || '',
        type: row.type || row.kind || 'file',
        size: row.size || row.bytes || ''
      }));
    }
    return appliedMission || Boolean(rows.length);
  }

  function normalizeEvidence(payload = {}, summary = {}) {
    const rows = firstArray(payload.receipts, payload.recent, payload.items);
    if (!rows.length || !window.opcbState?.evidence) return false;
    window.opcbState.evidence.files = rows.slice(0, 24).map((row, index) => {
      const name = row.path || row.file || row.receipt_id || row.artifact_type || `receipt_${index + 1}.json`;
      const ext = String(name).split('.').pop() || 'json';
      return {
        id: String(row.receipt_id || row.id || name),
        name: String(name).split('/').pop(),
        type: String(row.artifact_type || row.source || ext).toUpperCase(),
        ext,
        size: row.size || row.bytes ? `${row.size || row.bytes} B` : 'receipt',
        confidence: percentFrom(row.score ?? row.confidence, 92),
        status: row.status || 'Verified',
        raw: row
      };
    });
    window.opcbState.evidence.total = rows.length;
    window.opcbState.evidence.selected = Math.min(window.opcbState.evidence.selected, rows.length);
    window.opcbState.evidence.selectedId = window.opcbState.evidence.files[0]?.id || window.opcbState.evidence.selectedId;
    window.opcbState.evidence.validity = percentFrom(summary.validity ?? summary.validity_score ?? summary.overall_validity, window.opcbState.evidence.validity);
    window.opcbState.evidence.warnings = countFrom(summary.warnings, window.opcbState.evidence.warnings);
    window.opcbState.evidence.errors = countFrom(summary.errors, window.opcbState.evidence.errors);
    return true;
  }

  function normalizeGraph(payload = {}, integrity = {}) {
    const rawNodes = payload.nodes || payload.graph?.nodes || [];
    const rawEdges = payload.edges || payload.graph?.edges || [];
    if (!Array.isArray(rawNodes) || !rawNodes.length || !window.opcbState?.graph) return false;
    const cols = 6;
    window.opcbState.graph.nodes = rawNodes.slice(0, 80).map((node, index) => {
      const id = String(node.id || node.path || node.label || `node_${index}`);
      return {
        id,
        label: String(node.label || node.name || id).split('/').pop(),
        sub: String(node.kind || node.type || node.language || 'Node'),
        type: ['entry', 'parser', 'detector', 'db', 'agent', 'external'].includes(node.type) ? node.type : 'parser',
        x: 12 + (index % cols) * 15,
        y: 12 + Math.floor(index / cols) * 12
      };
    });
    window.opcbState.graph.edges = rawEdges.slice(0, 160).map(edge => ({
      from: String(edge.from || edge.source || edge.src || ''),
      to: String(edge.to || edge.target || edge.dst || ''),
      type: edge.type || edge.kind || 'calls'
    })).filter(edge => edge.from && edge.to);
    window.opcbState.graph.selected = window.opcbState.graph.nodes[0]?.id || window.opcbState.graph.selected;
    window.opcbState.graph.coverage = percentFrom(integrity.coverage ?? payload.coverage, window.opcbState.graph.coverage);
    window.opcbState.graph.health = percentFrom(integrity.health ?? payload.health, window.opcbState.graph.health);
    window.opcbState.graph.orphaned = countFrom(integrity.orphaned_nodes ?? integrity.orphans, window.opcbState.graph.orphaned);
    window.opcbState.graph.stats = { nodes: rawNodes.length, edges: rawEdges.length };
    return true;
  }

  function normalizeModels(snapshot = {}, registry = {}, providerState = {}, tooling = {}) {
    if (!window.opcbState?.route) return false;
    const route = window.opcbState.route;
    const snapshotRoute = firstObject(snapshot.model_route, snapshot.providers, snapshot.route);
    const providers = firstArray(
      registry.providers,
      registry.registry,
      registry.adapters,
      registry.items,
      providerState.providers,
      providerState.routes,
      snapshotRoute.providers
    );
    const stateModels = firstArray(
      providerState.models,
      providerState.local_models,
      registry.models,
      registry.local_models,
      snapshotRoute.models
    );
    const candidates = (stateModels.length ? stateModels : providers).filter(Boolean);
    const fallbackModels = route.fallback || [];
    const active = labelFrom(snapshotRoute.active, '') ||
      labelFrom(providerState.active_model, '') ||
      labelFrom(providerState.active, '') ||
      labelFrom(registry.active, '') ||
      labelFrom(candidates[0], route.active);
    route.active = active || route.active;
    const fallback = firstArray(snapshotRoute.fallback, providerState.fallback, providerState.fallbacks, registry.fallback, registry.fallbacks);
    route.fallback = fallback.length ? fallback.map(item => labelFrom(item)).filter(Boolean).slice(0, 3) : fallbackModels;
    route.policy = snapshotRoute.policy || providerState.policy || registry.policy || route.policy;
    route.cloud = providerState.cloud || providerState.cloud_access || route.cloud;
    route.reason = snapshotRoute.reason || providerState.reason || providerState.route_reason || route.reason;
    route.hardware = tooling.gpu?.name || tooling.hardware?.gpu || providerState.hardware || route.hardware;
    route.runtime = tooling.model_server?.status || providerState.runtime || route.runtime;
    route.models = candidates.length ? candidates.slice(0, 8).map((model, index) => {
      const id = labelFrom(model, index === 0 ? route.active : `model-${index + 1}`);
      return {
        id,
        role: id === route.active || index === 0 ? 'Primary' : 'Fallback',
        confidence: percentFrom(model.confidence ?? model.score ?? model.readiness, index === 0 ? route.confidence : 82),
        latency: model.latency || model.latency_p50 || model.response_time || (index === 0 ? route.latency : 'n/a'),
        speed: model.speed || model.throughput || model.tokens_per_second || (index === 0 ? route.throughput : 'n/a'),
        size: model.size || model.disk_size || model.vram || ''
      };
    }) : route.models;
    const runtimeRows = firstArray(tooling.runtimes, tooling.model_runtimes, providerState.runtimes, registry.runtimes);
    if (runtimeRows.length) {
      route.runtimes = runtimeRows.slice(0, 6).map(item => ({
        label: labelFrom(item, 'Runtime'),
        status: item.status || item.health || item.ready || 'Ready',
        icon: item.icon || ''
      }));
    }
    return Boolean(active || candidates.length || runtimeRows.length);
  }

  function normalizeAgents(payload = {}, snapshot = {}, tooling = {}) {
    if (!window.opcbState?.agents) return false;
    const sessions = firstArray(payload.sessions, payload.agent_sessions, payload.items, snapshot.agent_sessions?.sessions, snapshot.agent_sessions);
    if (!sessions.length) return false;
    window.opcbState.agents = sessions.slice(0, 8).map((session, index) => {
      const id = String(session.session_id || session.id || session.agent_id || `agent-${index + 1}`);
      const name = session.name || session.label || session.mode || session.agent || id;
      const tools = firstArray(session.tools, session.tool_names, session.allowed_tools, tooling.tools).slice(0, 4);
      return {
        id,
        label: String(name).replace(/[-_]/g, ' ').replace(/\b\w/g, char => char.toUpperCase()),
        role: session.role || session.permission || session.mode || 'Mission Agent',
        status: session.status || session.state || 'Online',
        confidence: percentFrom(session.confidence ?? session.score ?? session.health, 86),
        task: session.objective || session.task || session.last_prompt || 'Mission support',
        tools: tools.length ? tools.map(tool => labelFrom(tool, 'Tool')) : ['Code Graph', 'Evidence', 'Runbook']
      };
    });
    return true;
  }

  function normalizeMemory(memory = {}, snapshot = {}, summary = {}) {
    if (!window.opcbState?.memory) return false;
    const state = window.opcbState.memory;
    const records = firstArray(memory.records, memory.items, memory.memories, memory.stack);
    const events = firstArray(memory.events, memory.recent, memory.timeline);
    const receipts = firstArray(snapshot.evidence_bus?.receipts, snapshot.evidence_bus?.items, summary.receipts, summary.items);
    state.records = countFrom(memory.total ?? memory.count ?? records, state.records);
    state.evidenceItems = countFrom(summary.total ?? summary.evidence_items ?? receipts, state.evidenceItems);
    state.recallHealth = percentFrom(memory.health ?? memory.recall_health ?? memory.score, state.recallHealth);
    state.freshness = percentFrom(memory.freshness ?? memory.freshness_score, state.freshness);
    state.compactionQueue = countFrom(memory.compaction_queue ?? memory.queue, state.compactionQueue);
    state.skillCandidates = countFrom(memory.skill_candidates ?? memory.skills, state.skillCandidates);
    state.residueQuality = percentFrom(memory.residue_quality ?? summary.validity, state.residueQuality);
    if (events.length) {
      state.events = events.slice(0, 8).map(event => ({
        time: event.time || event.timestamp || event.created_at || 'live',
        label: event.label || event.title || event.kind || event.type || 'Memory event'
      }));
    } else if (records.length) {
      state.events = records.slice(0, 6).map(record => ({
        time: record.updated_at || record.created_at || 'live',
        label: record.label || record.title || record.key || record.id || 'Memory record retained'
      }));
    }
    return Boolean(records.length || events.length || memory.total || memory.count || summary.total);
  }

  function normalizeReview(snapshot = {}, evidence = {}, summary = {}) {
    if (!window.opcbState?.review) return false;
    const rows = firstArray(evidence.receipts, evidence.items, snapshot.evidence_bus?.receipts);
    const evidenceScore = percentFrom(summary.validity ?? summary.validity_score, Math.min(96, 62 + rows.length * 2));
    const decisions = countFrom(snapshot.policy?.architecture_decisions?.decision_count, 0);
    const risks = countFrom(snapshot.policy?.reintegration_health?.risks, window.opcbState.review.risks);
    window.opcbState.review.evidenceSufficiency = evidenceScore;
    window.opcbState.review.overallConfidence = Math.max(70, Math.min(98, Math.round((evidenceScore + 88 + Math.min(decisions, 20)) / 2)));
    window.opcbState.review.risks = risks;
    window.opcbState.review.contradictions = countFrom(summary.contradictions, window.opcbState.review.contradictions);
    return true;
  }

  function normalizeTrust(snapshot = {}, integrity = {}) {
    if (!window.opcbState?.trust) return false;
    const decisions = countFrom(snapshot.policy?.architecture_decisions?.decision_count, 0);
    const failed = countFrom(integrity.failed ?? integrity.failures, window.opcbState.trust.failedChecks);
    const warnings = countFrom(integrity.warnings, window.opcbState.trust.warnings);
    const health = percentFrom(integrity.health ?? snapshot.policy?.reintegration_health?.score, window.opcbState.trust.score);
    window.opcbState.trust.score = health;
    window.opcbState.trust.systemsTotal = Math.max(window.opcbState.trust.systemsTotal || 0, decisions || 31);
    window.opcbState.trust.failedChecks = failed;
    window.opcbState.trust.warnings = warnings;
    window.opcbState.trust.systemsHealthy = Math.max(0, window.opcbState.trust.systemsTotal - failed);
    return true;
  }

  function normalizeCrystallization(crystal = {}, lattice = {}) {
    if (!window.opcbState?.crystal) return false;
    const summary = crystal.summary || crystal;
    const candidates = firstArray(summary.candidates, crystal.candidates, lattice.candidates, lattice.items);
    const negative = countFrom(crystal.negative_capabilities, 0);
    const forks = countFrom(crystal.temporal_forks, 0);
    window.opcbState.crystal.readiness = percentFrom(summary.readiness ?? summary.readiness_score, window.opcbState.crystal.readiness);
    window.opcbState.crystal.candidates = countFrom(summary.candidate_count, candidates.length || window.opcbState.crystal.candidates);
    window.opcbState.crystal.events = [
      { time: 'live', label: `Crystal compute loaded: ${negative} negative capabilities` },
      { time: 'live', label: `Temporal forks tracked: ${forks}` },
      { time: 'live', label: `Mission lattice records: ${countFrom(lattice.nodes ?? lattice.records, 0)}` }
    ];
    if (candidates.length) {
      window.opcbState.crystal.candidateList = candidates.slice(0, 7).map((item, index) => ({
        id: String(item.id || item.name || item.title || `candidate-${index + 1}`),
        label: item.label || item.title || item.name || item.id || `Candidate ${index + 1}`,
        domain: item.domain || item.meta || item.kind || 'Evidence',
        value: item.value || item.priority || 'Candidate',
        ready: percentFrom(item.readiness ?? item.ready ?? item.score, 80)
      }));
      window.opcbState.crystal.selectedCandidate = window.opcbState.crystal.candidateList[0]?.id || window.opcbState.crystal.selectedCandidate;
    }
    return true;
  }

  function applyPagePayload(page, payloads) {
    const snapshot = payloads.ide_snapshot || payloads.snapshot || {};
    if (page === 'workspace') return normalizeWorkspace(snapshot, payloads.workspace_files, payloads.mission_route);
    if (page === 'mission') return normalizeMission(snapshot, payloads.mission_route, payloads.mission_timeline);
    if (page === 'models') return normalizeModels(snapshot, payloads.providers_registry, payloads.providers_state, payloads.tooling_snapshot);
    if (page === 'agents') return normalizeAgents(payloads.agent_sessions, snapshot, payloads.tooling_snapshot);
    if (page === 'review') return normalizeReview(snapshot, payloads.evidence_bus, payloads.evidence_summary);
    if (page === 'evidence') return normalizeEvidence(payloads.evidence_bus, payloads.evidence_summary);
    if (page === 'map') return normalizeGraph(payloads.workspace_graph, payloads.workspace_integrity);
    if (page === 'trust') return normalizeTrust(snapshot, payloads.workspace_integrity);
    if (page === 'crystallization') return normalizeCrystallization(payloads.crystal_compute, payloads.mission_lattice);
    if (page === 'memory') return normalizeMemory(payloads.memory_stack, snapshot, payloads.evidence_summary);
    if (page === 'doctor') return normalizeGatewayDoctor(store.gateway);
    return false;
  }

  async function refreshPage(page, options = {}) {
    if (!dashboardPages.has(page)) return null;
    store.loading[page] = true;
    store.errors[page] = '';
    try {
      if (options.forceGateway || !store.gateway.checkedAt || Date.now() - store.gateway.checkedAt > 10000) {
        await refreshGatewayContract();
      }
      const routeIds = pageRoutes[page] || [];
      const payloads = {};
      await Promise.all(routeIds.map(async id => {
        const route = requiredGatewayRoutes.find(item => item.id === id);
        if (!route || !store.gateway.url) return;
        try {
          payloads[id] = await fetchJson(routeUrl(store.gateway.url, route), { method: route.method });
        } catch (error) {
          payloads[id] = null;
          store.errors[page] = String(error.message || error);
        }
      }));
      store.pages[page] = { checkedAt: Date.now(), payloads };
      store.applied[page] = applyPagePayload(page, payloads);
      return store.pages[page];
    } catch (error) {
      store.errors[page] = String(error.message || error);
      return null;
    } finally {
      store.loading[page] = false;
    }
  }

  window.opcbLiveStore = {
    state: store,
    requiredGatewayRoutes,
    refreshGatewayContract,
    refreshPage,
    applyPagePayload,
    normalizeGatewayDoctor
  };

  window.opcbRecheckGatewayContract = async function opcbRecheckGatewayContract() {
    const result = await refreshGatewayContract();
    window.opcbApplyPage?.('doctor', { skipLiveRefresh: true });
    return result;
  };

  window.opcbRefreshPage = async function opcbRefreshPage(page, options = {}) {
    const result = await refreshPage(page, options);
    if (store.applied[page]) window.opcbApplyPage?.(page, { skipLiveRefresh: true });
    return result;
  };
})();
