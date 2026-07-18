(() => {
  const demoModels = [
    { id:'qwen2.5-coder:7b', provider:'local_ollama', role:'Primary', confidence:94.7, latency:'1.24s', speed:'14.2 tok/s', size:'4.7 GB', context:'32K', quantization:'Q4_K_M', status:'Ready', runtime:'Ollama' },
    { id:'deepseek-coder:6.7b', provider:'local_ollama', role:'Fallback', confidence:83.1, latency:'1.98s', speed:'11.0 tok/s', size:'3.8 GB', context:'32K', quantization:'Q4_K_M', status:'Ready', runtime:'Ollama' },
    { id:'mistral-nemo:12b', provider:'local_ollama', role:'Fallback', confidence:78.6, latency:'2.12s', speed:'8.4 tok/s', size:'7.1 GB', context:'128K', quantization:'Q4_K_M', status:'Warm', runtime:'llama.cpp' },
    { id:'phi-3.5-mini-instruct:3.8b', provider:'local_ollama', role:'Economy', confidence:71.2, latency:'0.82s', speed:'19.4 tok/s', size:'2.4 GB', context:'128K', quantization:'Q4_K_M', status:'Ready', runtime:'Ollama' },
    { id:'nemotron-super', provider:'nvidia_nim', role:'Escalation', confidence:97.4, latency:'cloud', speed:'managed', size:'remote', context:'128K', quantization:'NIM', status:'Standby', runtime:'NVIDIA NIM' }
  ];
  const demoAgents = [
    { id:'planner', label:'Planner Agent', role:'Architect', status:'Active', confidence:96, task:'Shape the mission route and approval gates', provider:'local_ollama', model:'qwen2.5-coder:7b', tools:['Runbook','Code Graph','Mission State'], files:3, budget:'42K tok' },
    { id:'graph', label:'Graph Analyst', role:'Analyst', status:'Active', confidence:92, task:'Resolve dependencies and impact paths', provider:'local_ollama', model:'qwen2.5-coder:7b', tools:['Code Graph','Symbols','Map'], files:12, budget:'31K tok' },
    { id:'profiler', label:'Profiler Agent', role:'Profiler', status:'Working', confidence:89, task:'Sample hot paths and runtime pressure', provider:'local_ollama', model:'deepseek-coder:6.7b', tools:['Profiler','Runtime','Telemetry'], files:7, budget:'28K tok' },
    { id:'verifier', label:'Verifier Agent', role:'Verifier', status:'Queued', confidence:94, task:'Check contradictions and evidence closure', provider:'local_ollama', model:'mistral-nemo:12b', tools:['Evidence','Trust','Tests'], files:5, budget:'36K tok' }
  ];

  function firstArray(...values) {
    for (const value of values) {
      if (Array.isArray(value)) return value;
      if (value && typeof value === 'object') {
        const entries = Object.entries(value);
        if (entries.length && entries.every(([, row]) => row && typeof row === 'object')) return entries.map(([key, row]) => ({ key, ...row }));
      }
    }
    return [];
  }
  function label(value, fallback='') {
    if (typeof value === 'string' || typeof value === 'number') return String(value);
    if (!value || typeof value !== 'object') return fallback;
    return String(value.model_id || value.provider_id || value.session_id || value.agent_id || value.id || value.name || value.label || value.key || fallback);
  }
  function percent(value, fallback=0) {
    const n = Number(value);
    if (!Number.isFinite(n)) return fallback;
    return Math.max(0, Math.min(100, n <= 1 ? n * 100 : n));
  }
  function rootQuery() {
    const root = BeastStore.get().workspace.root;
    return root ? `?root_path=${encodeURIComponent(root)}` : '';
  }
  function settledValue(row) { return row?.status === 'fulfilled' ? row.value : null; }

  function normalizeModels(registry={}, providerState={}, tooling={}, integrations={}, stats={}) {
    const route = providerState.route || providerState.active_route || providerState.routing || {};
    const candidates = firstArray(
      providerState.models, providerState.local_models, providerState.providers,
      registry.models, registry.local_models, registry.providers, registry.registry, registry.adapters, registry.records, registry.items,
      tooling.models, tooling.local_models
    );
    const fallback = BeastStore.get().models.registry.length ? BeastStore.get().models.registry : demoModels;
    const rows = candidates.length ? candidates.slice(0, 16).map((model, index) => {
      const id = label(model, `model-${index + 1}`);
      const activeHint = label(route.model || providerState.active_model || providerState.selected_model || registry.active_model || '');
      const isPrimary = id === activeHint || Boolean(model.primary || model.active || model.selected) || (!activeHint && index === 0);
      return {
        id,
        provider: label(model.provider || model.backend || model.route_provider, label(providerState.active_provider || providerState.provider, 'local')),
        role: isPrimary ? 'Primary' : String(model.role || model.route_role || 'Fallback'),
        confidence: percent(model.confidence ?? model.score ?? model.readiness, isPrimary ? 94 : 82),
        latency: String(model.latency || model.latency_p50 || model.response_time || (isPrimary ? route.latency || 'n/a' : 'n/a')),
        speed: String(model.speed || model.throughput || model.tokens_per_second || (isPrimary ? route.throughput || 'n/a' : 'n/a')),
        size: String(model.size || model.disk_size || model.vram || model.parameters || ''),
        context: String(model.context || model.context_window || model.context_length || 'n/a'),
        quantization: String(model.quantization || model.quant || model.format || ''),
        status: String(model.status || model.health || (model.ready === false ? 'Unavailable' : 'Ready')),
        runtime: String(model.runtime || model.engine || model.backend || 'Local runtime')
      };
    }) : fallback;
    const active = label(route.model || providerState.active_model || providerState.selected_model || registry.active_model, rows.find(row => row.role === 'Primary')?.id || rows[0]?.id || BeastStore.get().models.active);
    rows.forEach((row, index) => { row.role = row.id === active || (!active && index === 0) ? 'Primary' : row.role === 'Primary' ? 'Fallback' : row.role; });
    const runtimeRows = firstArray(tooling.runtimes, tooling.model_runtimes, providerState.runtimes, registry.runtimes, integrations.runtimes);
    const runtimes = runtimeRows.length ? runtimeRows.slice(0, 8).map((runtime, index) => ({
      id: label(runtime, `runtime-${index + 1}`),
      label: label(runtime, `Runtime ${index + 1}`),
      status: String(runtime.status || runtime.health || (runtime.ready === false ? 'Offline' : 'Ready')),
      detail: String(runtime.version || runtime.backend || runtime.device || runtime.endpoint || '')
    })) : [
      { id:'ollama', label:'Ollama', status:'Running', detail:'Local model server' },
      { id:'llamacpp', label:'llama.cpp', status:'Ready', detail:'CPU / GPU runtime' },
      { id:'litellm', label:'LiteLLM', status:'Ready', detail:'Governed proxy' },
      { id:'nim', label:'NVIDIA NIM', status:'Standby', detail:'Escalation route' }
    ];
    const gpu = tooling.gpu || tooling.hardware?.gpu || tooling.system?.gpu || {};
    const hardware = {
      name: label(gpu, String(tooling.hardware?.name || tooling.device || 'Local compute')),
      vram: String(gpu.vram || gpu.memory || tooling.hardware?.vram || 'n/a'),
      temperature: String(gpu.temperature || tooling.temperature || 'n/a'),
      status: String(gpu.status || tooling.hardware?.status || 'Healthy')
    };
    const testRows = firstArray(stats.tests, stats.benchmarks, stats.route_tests, providerState.tests);
    const tests = testRows.length ? testRows.slice(0, 8).map((test, index) => ({
      id: label(test, `test-${index + 1}`), model: label(test.model || test.model_id, rows[index % Math.max(1, rows.length)]?.id || 'model'),
      accuracy: percent(test.accuracy ?? test.score, 70), latency: String(test.latency || test.latency_p50 || 'n/a'),
      throughput: String(test.throughput || test.speed || 'n/a'), status: String(test.status || 'Passed')
    })) : rows.slice(0, 4).map((row, index) => ({ id:`demo-test-${index}`, model:row.id, accuracy:row.confidence, latency:row.latency, throughput:row.speed, status:'Passed' }));
    return {
      active,
      selectedId: BeastStore.get().models.selectedId || active,
      provider: label(providerState.active_provider || providerState.provider || route.provider, rows.find(row => row.id === active)?.provider || 'local'),
      policy: String(route.policy || providerState.policy || registry.policy || 'Local First'),
      reason: String(route.reason || providerState.reason || providerState.route_reason || 'Capability fit, latency guard, and local-first policy.'),
      confidence: rows.find(row => row.id === active)?.confidence || 90,
      latency: String(route.latency || rows.find(row => row.id === active)?.latency || 'n/a'),
      throughput: String(route.throughput || rows.find(row => row.id === active)?.speed || 'n/a'),
      contextWindow: String(route.context_window || rows.find(row => row.id === active)?.context || 'n/a'),
      cloudAllowed: Boolean(route.cloud_allowed ?? providerState.cloud_allowed ?? providerState.cloud),
      registry: rows,
      runtimes, hardware, tests,
      lastRefreshAt: Date.now(), loading:false, error:''
    };
  }

  async function refreshModels(options={}) {
    BeastStore.patch('models', { loading:true, error:'' });
    if (BeastDesktopBridge.demoMode) {
      const normalized = normalizeModels({ models:demoModels }, { active_model:'qwen2.5-coder:7b', active_provider:'local_ollama', policy:'Local First', route_reason:'Highest capability per local watt' }, { gpu:{ name:'RTX 4090', vram:'24 GB', temperature:'62°C', status:'Healthy' } }, {}, {});
      BeastStore.patch('models', normalized);
      BeastStore.addLedger('Model Router refreshed from demo telemetry');
      return normalized;
    }
    try {
      const query = rootQuery();
      const results = await Promise.allSettled([
        BeastDesktopBridge.fetchJson('/edgek/providers/registry', options),
        BeastDesktopBridge.fetchJson('/edgek/providers/state', options),
        BeastDesktopBridge.fetchJson(`/edgek/ide/tooling-snapshot${query}`, options),
        BeastDesktopBridge.fetchJson('/edgek/tools/integrations', options),
        BeastDesktopBridge.fetchJson(`/edgek/providers/inference-stats${query}`, options)
      ]);
      const normalized = normalizeModels(...results.map(settledValue));
      BeastStore.patch('models', normalized);
      BeastStore.addLedger(`Model Router refreshed: ${normalized.registry.length} routes`);
      return normalized;
    } catch (error) {
      BeastStore.patch('models', { loading:false, error:String(error.message || error), lastRefreshAt:Date.now() });
      throw error;
    }
  }

  function selectModel(id) {
    const state = BeastStore.get();
    const model = state.models.registry.find(row => row.id === id);
    if (!model) return;
    localStorage.setItem('beast.model', id);
    if (model.provider) localStorage.setItem('beast.provider', model.provider);
    BeastStore.patch('models', { selectedId:id });
    BeastStore.addLedger(`Model selected for inspection: ${id}`);
  }

  function normalizeAgents(snapshot={}, tooling={}) {
    const sessions = firstArray(snapshot.agent_sessions?.sessions, snapshot.agent_sessions, snapshot.sessions, snapshot.agents);
    const rows = sessions.length ? sessions.slice(0, 12).map((session, index) => {
      const id = label(session, `agent-${index + 1}`);
      const tools = firstArray(session.tools, session.tool_names, session.allowed_tools, session.capabilities).map(tool => label(tool, 'Tool')).slice(0, 6);
      return {
        id,
        label: String(session.name || session.label || session.agent || session.mode || id).replace(/[-_]/g,' ').replace(/\b\w/g, char => char.toUpperCase()),
        role: String(session.role || session.permission || session.mode || 'Mission Agent'),
        status: String(session.status || session.state || 'Online'),
        confidence: percent(session.confidence ?? session.score ?? session.health, 86),
        task: String(session.objective || session.task || session.last_prompt || 'Mission support'),
        provider: String(session.provider || 'local'), model: String(session.model || 'assigned route'),
        tools: tools.length ? tools : ['Code Graph','Evidence','Runbook'],
        files: Number(session.files?.length ?? session.file_count ?? 0),
        budget: String(session.budget?.tokens || session.token_budget || 'governed'),
        updatedAt: String(session.updated_at || session.last_event_at || 'live')
      };
    }) : (BeastDesktopBridge.demoMode ? demoAgents : []);
    const handoffs = rows.slice(0, 8).map((agent, index) => ({
      time: new Date(Date.now() - index * 65000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}),
      label: `${agent.label}: ${agent.task}`,
      tone: /error|alert|blocked/i.test(agent.status) ? 'danger' : /working|active|running/i.test(agent.status) ? 'live' : 'idle'
    }));
    const allTools = firstArray(tooling.tools, tooling.integrations, tooling.tool_inventory).map(tool => label(tool, 'Tool'));
    return {
      sessions:rows,
      selectedId: BeastStore.get().agents.selectedId || rows[0]?.id || '',
      tools: allTools.length ? [...new Set(allTools)].slice(0, 12) : BeastStore.get().agents.tools,
      handoffs,
      orchestrator:{ label:'Mission Orchestrator', status:rows.some(row => /active|working|running/i.test(row.status)) ? 'Coordinating' : 'Online', health: rows.length ? Math.round(rows.reduce((sum,row)=>sum+row.confidence,0)/rows.length) : 100 },
      loading:false, error:'', lastRefreshAt:Date.now()
    };
  }

  async function refreshAgents(options={}) {
    BeastStore.patch('agents', { loading:true, error:'' });
    if (BeastDesktopBridge.demoMode) {
      const normalized = normalizeAgents({ agent_sessions:{ sessions:demoAgents } }, { tools:['Code Graph','Profiler','Evidence Parser','File System','Shell','Runbook'] });
      BeastStore.patch('agents', normalized);
      BeastStore.patch('mission', { metrics:{ ...BeastStore.get().mission.metrics, agents:normalized.sessions.length } });
      BeastStore.addLedger('Agent Constellation refreshed from demo telemetry');
      return normalized;
    }
    try {
      const root = BeastStore.get().workspace.root;
      const params = new URLSearchParams();
      if (root) params.set('root_path', root);
      params.set('objective', BeastStore.get().mission.title);
      const suffix = params.toString() ? `?${params}` : '';
      const results = await Promise.allSettled([
        BeastDesktopBridge.fetchJson(`/edgek/ide/snapshot${suffix}`, options),
        BeastDesktopBridge.fetchJson(`/edgek/ide/tooling-snapshot${root ? `?root_path=${encodeURIComponent(root)}` : ''}`, options)
      ]);
      const normalized = normalizeAgents(settledValue(results[0]) || {}, settledValue(results[1]) || {});
      BeastStore.patch('agents', normalized);
      BeastStore.patch('mission', { metrics:{ ...BeastStore.get().mission.metrics, agents:normalized.sessions.length } });
      BeastStore.addLedger(`Agent Constellation refreshed: ${normalized.sessions.length} sessions`);
      return normalized;
    } catch (error) {
      BeastStore.patch('agents', { loading:false, error:String(error.message || error), lastRefreshAt:Date.now() });
      throw error;
    }
  }

  async function createAgent(objective, options={}) {
    const text = String(objective || '').trim();
    if (!text) throw new Error('Agent objective is required.');
    const state = BeastStore.get();
    if (BeastDesktopBridge.demoMode || state.connection.status !== 'online') {
      const id = `local-${Date.now()}`;
      const local = { id, label:'Local Architect', role:'Architect', status:'Queued Locally', confidence:82, task:text, provider:state.models.provider, model:state.models.selectedId || state.models.active, tools:['Code Graph','Evidence','Runbook'], files:state.editor.activePath ? 1 : 0, budget:'120K tok' };
      BeastStore.patch('agents', { sessions:[local, ...state.agents.sessions], selectedId:id, handoffs:[{time:'now',label:`Local Architect queued: ${text}`,tone:'idle'}, ...state.agents.handoffs] });
      BeastStore.addLedger(`Agent queued locally: ${text}`);
      return local;
    }
    const result = await BeastDesktopBridge.fetchJson('/edgek/ide/agent-sessions/create', {
      ...options, method:'POST', body:{ root_path:state.workspace.root, objective:text, mode:'architect', provider:state.models.provider || localStorage.getItem('beast.provider') || 'nvidia_nim', model:state.models.selectedId || state.models.active || localStorage.getItem('beast.model'), files:state.editor.activePath ? [state.editor.activePath] : [], budget:{ tokens:120000, seconds:3600, cost_usd:0 } }
    });
    await refreshAgents(options);
    const session = result?.session || result;
    if (session?.session_id || session?.id) BeastStore.patch('agents', { selectedId:session.session_id || session.id });
    BeastStore.addLedger(`Agent session created: ${session?.session_id || session?.id || text}`);
    return session;
  }

  function selectAgent(id) {
    BeastStore.patch('agents', { selectedId:id });
    BeastStore.addLedger(`Agent selected: ${id}`);
  }

  async function controlAgent(id, action, options={}) {
    const state = BeastStore.get();
    if (!id) throw new Error('Select an agent first.');
    if (BeastDesktopBridge.demoMode || state.connection.status !== 'online' || String(id).startsWith('local-')) {
      const mapped = action === 'resume' ? 'Active' : action === 'pause' ? 'Paused' : 'Cancelled';
      BeastStore.patch('agents', { sessions:state.agents.sessions.map(agent => agent.id === id ? {...agent,status:mapped} : agent) });
      BeastStore.addLedger(`Agent ${id}: ${mapped}`);
      return { ok:true, local:true };
    }
    const endpoint = action === 'pause' ? '/edgek/ide/agent-sessions/pause' : action === 'resume' ? '/edgek/ide/agent-sessions/resume' : '/edgek/ide/agent-sessions/cancel';
    const result = await BeastDesktopBridge.fetchJson(endpoint, { ...options, method:'POST', body:{ root_path:state.workspace.root, session_id:id, reason:action === 'cancel' ? 'Cancelled from BEAST Phase 4' : '' } });
    await refreshAgents(options);
    return result;
  }

  window.BeastModelAgentBridge = { refreshModels, selectModel, refreshAgents, createAgent, selectAgent, controlAgent };
})();
