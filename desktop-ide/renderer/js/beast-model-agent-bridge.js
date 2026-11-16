(() => {
  const demoModels = [
    { id:'qwen2.5-coder:7b', provider:'local_ollama', role:'Primary', confidence:94.7, latency:'1.24s', speed:'14.2 tok/s', size:'4.7 GB', context:'32K', quantization:'Q4_K_M', status:'Ready', runtime:'Ollama' },
    { id:'deepseek-coder:6.7b', provider:'local_ollama', role:'Fallback', confidence:83.1, latency:'1.98s', speed:'11.0 tok/s', size:'3.8 GB', context:'32K', quantization:'Q4_K_M', status:'Ready', runtime:'Ollama' },
    { id:'mistral-nemo:12b', provider:'local_ollama', role:'Fallback', confidence:78.6, latency:'2.12s', speed:'8.4 tok/s', size:'7.1 GB', context:'128K', quantization:'Q4_K_M', status:'Warm', runtime:'llama.cpp' },
    { id:'phi-3.5-mini-instruct:3.8b', provider:'local_ollama', role:'Economy', confidence:71.2, latency:'0.82s', speed:'19.4 tok/s', size:'2.4 GB', context:'128K', quantization:'Q4_K_M', status:'Ready', runtime:'Ollama' },
    { id:'nemotron-super', provider:'nvidia_nim', role:'Escalation', confidence:97.4, latency:'cloud', speed:'managed', size:'remote', context:'128K', quantization:'NIM', status:'Standby', runtime:'NVIDIA NIM' }
  ];
  const localCodingFallbackModels = [
    { id:'qwen2.5-coder:1.5b', provider:'ollama', role:'Local coding · recommended', confidence:86, latency:'CPU/GPU local', speed:'1.5B coder', size:'986 MB', context:'32K', quantization:'Qwen Coder · Ollama', status:'Local Ollama · probe on use', selectable:true, runtime:'Ollama' },
    { id:'qwen2.5:0.5b', provider:'ollama', role:'Emergency low-memory fallback', confidence:68, latency:'local', speed:'CPU local', size:'397 MB', context:'32K', quantization:'Ollama', status:'Fallback · probe on use', selectable:true, runtime:'Ollama' }
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

  const hostedNemotron = 'nvidia/nemotron-3.5-lightning-30b-a3b';
  let verifiedHostedGateway = '';
  let hostedVerificationPending = false;
  function currentGateway() {
    return String(BeastStore.get().connection?.gatewayUrl || '').replace(/\/$/, '');
  }


  const AUTO_ID = 'auto';
  function isAutoRoute(id) {
    const value = String(id || '').trim();
    return !value || value === AUTO_ID || value === 'beast-auto';
  }
  function routeLabel(row) {
    if (!row) return '';
    if (row.governedAuto || row.governed_auto || isAutoRoute(row.id)) return 'Auto (BEAST governed)';
    return String(row.label || `${row.model || row.id} · ${row.provider || ''}`.trim());
  }
  function inventoryRows(state) {
    return (state?.models?.registry || []).filter(row => row && row.selectable !== false);
  }
  function findRoute(id, state) {
    const rows = inventoryRows(state || BeastStore.get());
    const requested = String(id || '').trim();
    if (isAutoRoute(requested)) return rows.find(row => row.governedAuto || isAutoRoute(row.id)) || {
      id: AUTO_ID, model: AUTO_ID, provider: 'beast', label: 'Auto (BEAST governed)',
      governedAuto: true, selectable: true, configured: true, reachable: true, role: 'Capability router'
    };
    return rows.find(row => row.id === requested)
      || rows.find(row => row.model === requested)
      || null;
  }
  function fillModelSelect(select, state) {
    if (!select) return;
    const rows = inventoryRows(state);
    const withAuto = rows.some(row => row.governedAuto || isAutoRoute(row.id))
      ? rows
      : [{ id: AUTO_ID, model: AUTO_ID, provider: 'beast', label: 'Auto (BEAST governed)', governedAuto: true, selectable: true }, ...rows];
    const key = JSON.stringify(withAuto.map(row => [row.id, row.provider, row.label, (row.best_for || []).join(',')]));
    if (select.dataset.optionsKey !== key) {
      select.dataset.optionsKey = key;
      const options = withAuto.map(row => {
        const option = document.createElement('option');
        option.value = row.id;
        const best = (row.best_for || []).slice(0, 3);
        option.textContent = row.governedAuto || isAutoRoute(row.id)
          ? 'Auto (BEAST governed)'
          : `${routeLabel(row)}${best.length ? ` · best: ${best.join(', ')}` : ''}`;
        return option;
      });
      select.replaceChildren(...options);
    }
    const current = String(state.aiCoding?.model || state.models?.selectedId || state.models?.selectedModel || '').trim();
    const match = withAuto.find(row => row.id === current)
      || withAuto.find(row => row.model === current && (!state.aiCoding?.provider || row.provider === state.aiCoding.provider || (row.provider === 'ollama' && state.aiCoding.provider === 'local_ollama')))
      || withAuto.find(row => row.governedAuto || isAutoRoute(row.id));
    select.value = match?.id || AUTO_ID;
  }
  function normalizeInventory(inventory={}) {
    const rows = Array.isArray(inventory.registry) ? inventory.registry.map(row => ({
      id: String(row.id || ''),
      model: String(row.model || row.id || ''),
      provider: String(row.provider || ''),
      label: String(row.label || routeLabel(row)),
      role: String(row.role || ''),
      status: String(row.status || ''),
      runtime: String(row.runtime || row.provider || ''),
      confidence: Number(row.confidence || 0) || 0,
      latency: String(row.latency || 'n/a'),
      speed: String(row.speed || 'n/a'),
      size: String(row.size || ''),
      context: String(row.context || 'n/a'),
      quantization: String(row.quantization || ''),
      placement: String(row.placement || ''),
      key_env: String(row.key_env || ''),
      selectable: row.selectable !== false,
      configured: row.configured !== false,
      reachable: row.reachable !== false,
      installed: row.installed === true,
      live: row.live,
      governedAuto: row.governed_auto === true || row.governedAuto === true || row.id === AUTO_ID,
      families: row.families || {},
      best_for: Array.isArray(row.best_for) ? row.best_for : [],
      usd_per_mtok_in: row.usd_per_mtok_in,
      usd_per_mtok_out: row.usd_per_mtok_out,
      gatewayUrl: currentGateway()
    })).filter(row => row.id) : [];
    if (currentGateway() && currentGateway() === verifiedHostedGateway) {
      const hosted = rows.find(row => row.model === hostedNemotron || row.id === hostedNemotron || (row.provider === 'nvidia_nim' && String(row.model||'').includes('nemotron-3.5-lightning')));
      if (hosted) {
        hosted.hostedCoding = true;
        hosted.hostedProvider = true;
        hosted.inferenceVerified = true;
        hosted.reachable = true;
        hosted.id = hostedNemotron;
        hosted.model = hostedNemotron;
        hosted.provider = 'nvidia_nim';
      } else {
        rows.push({
          id: hostedNemotron, model: hostedNemotron, provider: 'nvidia_nim',
          label: 'Nemotron 3.5 Lightning 30B A3B · NVIDIA hosted',
          role: 'Hosted · verified coding', status: 'Verified hosted inference', runtime: 'NVIDIA NIM',
          confidence: 0, latency: 'n/a', speed: 'n/a', size: 'remote', context: 'n/a', quantization: '',
          selectable: true, configured: true, reachable: true, installed: false, live: null,
          governedAuto: false, hostedCoding: true, hostedProvider: true, inferenceVerified: true,
          families: {}, best_for: [], gatewayUrl: currentGateway()
        });
      }
    }
    if (!rows.some(row => row.governedAuto)) {
      rows.unshift({
        id: AUTO_ID, model: AUTO_ID, provider: 'beast', label: 'Auto (BEAST governed)',
        role: 'Capability router picks the best available lane per task family',
        status: 'Default route', runtime: 'BEAST governed', confidence: 0, latency: 'routed per call',
        speed: 'n/a', size: '', context: 'n/a', quantization: '', selectable: true, configured: true,
        reachable: true, installed: false, live: null, governedAuto: true, families: inventory.family_leaders || {},
        best_for: Object.keys(inventory.family_leaders || {})
      });
    }
    const preferred = String(BeastStore.get().models.selectedId || BeastStore.get().models.selectedModel || BeastStore.get().aiCoding?.model || localStorage.getItem('beast.model') || '').trim();
    const selected = rows.find(row => row.id === preferred || row.model === preferred) || rows.find(row => row.governedAuto) || rows[0];
    const hardware = BeastStore.get().models.hardware || { name: 'Local compute', vram: 'n/a', temperature: 'n/a', status: 'Unknown' };
    const live = inventory.live || {};
    const runtimes = [];
    if (live.tgi) runtimes.push({ id: 'tgi', label: 'TGI', status: live.tgi.up ? 'Live' : 'Down', detail: live.tgi.model || live.tgi.base_url || '' });
    if (live.ollama) runtimes.push({ id: 'ollama', label: 'Ollama', status: live.ollama.up ? 'Live' : 'Down', detail: `${(live.ollama.models || []).length} installed` });
    return {
      active: selected?.id || AUTO_ID,
      selectedId: selected?.id || AUTO_ID,
      selectedModel: selected?.governedAuto ? AUTO_ID : (selected?.model || ''),
      selectedProvider: selected?.provider || 'beast',
      provider: selected?.provider || 'beast',
      policy: String(inventory.policy || 'Auto (BEAST governed)'),
      reason: selected?.governedAuto
        ? 'Capability router will pick a lane per task family.'
        : `${selected?.label || selected?.id} pinned through the governed path.`,
      confidence: Number(selected?.confidence || 0) || 0,
      latency: selected?.latency || 'n/a',
      throughput: selected?.speed || 'n/a',
      contextWindow: selected?.context || 'n/a',
      cloudAllowed: rows.some(row => row.provider && !['ollama','tgi','beast','local_ollama'].includes(row.provider)),
      registry: rows,
      runtimes: runtimes.length ? runtimes : (BeastStore.get().models.runtimes || []),
      hardware,
      tests: Object.entries(inventory.family_leaders || {}).map(([family, leader]) => ({
        id: family, model: `${leader.provider}/${leader.model}`, accuracy: Math.round((Number(leader.pass_rate) || 0) * 100),
        latency: 'scorecard', throughput: `rank 1 · ${family}`, status: 'Family leader'
      })),
      familyLeaders: inventory.family_leaders || {},
      families: inventory.families || [],
      lastRefreshAt: Date.now(), loading: false, error: ''
    };
  }


  async function verifyHostedNemotron(options={}) {
    const gateway = currentGateway();
    if (!gateway || BeastDesktopBridge.demoMode) throw new Error('A live BEAST gateway is required.');
    if (hostedVerificationPending) throw new Error('Hosted model verification is already running.');
    hostedVerificationPending = true;
    verifiedHostedGateway = '';
    BeastStore.patch('models', {registry:BeastStore.get().models.registry.filter(row => !row.hostedProvider)});
    try {
      const receipt = await BeastDesktopBridge.fetchJson('/edgek/providers/nvidia-nim/verify-picker-model', {
        ...options, timeoutMs:22000, method:'POST', body:{confirm_live:true}
      });
      if (currentGateway() !== gateway) throw new Error('Gateway changed during hosted model verification.');
      if (receipt?.ok !== true || receipt.provider !== 'nvidia_nim' ||
          receipt.model !== hostedNemotron || receipt.status !== 'verified') {
        throw new Error(`Hosted model verification failed: ${receipt?.status || 'invalid_receipt'}`);
      }
      verifiedHostedGateway = gateway;
      const result = await refreshModels(options);
      if (!result.registry.some(row => row.id === hostedNemotron && row.inferenceVerified === true)) {
        throw new Error('Hosted model verified but unavailable in this gateway inventory.');
      }
      return result;
    } finally {
      hostedVerificationPending = false;
    }
  }

  function normalizeModels(registry={}, providerState={}, tooling={}, integrations={}, stats={}, ollamaInventory={}) {
    registry=registry ?? {}; providerState=providerState ?? {}; tooling=tooling ?? {}; integrations=integrations ?? {}; stats=stats ?? {}; ollamaInventory=ollamaInventory ?? {};
    registry = registry ?? {};
    providerState = providerState ?? {};
    tooling = tooling ?? {};
    integrations = integrations ?? {};
    stats = stats ?? {};
    // Provider registry rows are NOT model instances. Only explicit model inventories qualify.
    const route = providerState.route || providerState.active_route || providerState.routing || {};
    const installed = Array.isArray(ollamaInventory?.models) ? ollamaInventory.models : [];
    const rows = installed.filter(m => m && typeof m.name === 'string' && m.name.trim()).slice(0, 64).map(m => ({
      id: m.name, provider:'ollama', role:'Installed', confidence:0,
      latency:'n/a', speed:'n/a', size:String(m.size || ''),
      context:'n/a', quantization:String(m.details?.quantization_level || ''),
      status:'Installed · inference unverified', runtime:'Ollama',
      installed:true, reachable: Boolean(ollamaInventory?.ok), inferenceVerified:false
    }));
    const providerRows = firstArray(registry.providers, registry.items, registry.registry);
    const credentials = providerState.credentials && typeof providerState.credentials === 'object' ? providerState.credentials : {};
    // A credential-ready registry default is a selectable route.  It is not
    // represented as installed or inference-verified: those claims require a
    // provider-specific probe.
    providerRows.forEach(record => {
      const provider = String(record?.provider_id || record?.id || '');
      const model = String(record?.default_model || '');
      if (!provider || !model || record.enabled === false || provider === 'ollama' ||
          credentials[provider] !== true || rows.some(row => row.id === model && row.provider === provider)) return;
      const hostedCoding = provider === 'nvidia_nim' && model === hostedNemotron && currentGateway() === verifiedHostedGateway;
      rows.push({
        id:model, provider, role:'Configured provider default', confidence:0,
        latency:'unverified', speed:'provider managed', size:'remote', context:'provider managed',
        quantization:'n/a', status:'Credentials ready · inference unverified', runtime:String(record.backend || 'provider'),
        configured:true, reachable:true, gatewayUrl:currentGateway(), inferenceVerified:hostedCoding,
        hostedProvider:provider === 'nvidia_nim', hostedCoding, baseUrl:String(record.base_url || '')
      });
    });
    const gateway = currentGateway();
    const hosted = providerState.providers?.nvidia_nim;
    if (gateway && gateway === verifiedHostedGateway &&
        hosted?.enabled === true && providerState.credentials?.nvidia_nim === true &&
        !rows.some(row => row.id === hostedNemotron)) {
      rows.push({
        id:hostedNemotron, provider:'nvidia_nim', role:'Hosted · verified coding',
        status:'Verified hosted inference', runtime:'NVIDIA NIM', size:'remote',
        configured:true, gatewayUrl:gateway, reachable:true, inferenceVerified:true,
        hostedProvider:true, hostedCoding:true
      });
    }
    const preferred = String(BeastStore.get().models.selectedId || '');
    const selectedId = rows.some(row => row.id === preferred) ? preferred : '';
    // Active means a verified executing route, never the first configured provider.
    const active = '';
    const runtimeRows = firstArray(tooling.runtimes, tooling.model_runtimes, providerState.runtimes, registry.runtimes, integrations.runtimes);
    const runtimes = runtimeRows.length ? runtimeRows.slice(0, 8).map((runtime, index) => ({
      id: label(runtime, `runtime-${index + 1}`),
      label: label(runtime, `Runtime ${index + 1}`),
      status: String(runtime.status || runtime.health || (runtime.ready === false ? 'Offline' : 'Ready')),
      detail: String(runtime.version || runtime.backend || runtime.device || runtime.endpoint || '')
    })) : [];
    const gpu = tooling.gpu || tooling.hardware?.gpu || tooling.system?.gpu || {};
    const hardware = {
      name: label(gpu, String(tooling.hardware?.name || tooling.device || 'Local compute')),
      vram: String(gpu.vram || gpu.memory || tooling.hardware?.vram || 'n/a'),
      temperature: String(gpu.temperature || tooling.temperature || 'n/a'),
      status: String(gpu.status || tooling.hardware?.status || 'Unknown')
    };
    const testRows = firstArray(stats.tests, stats.benchmarks, stats.route_tests, providerState.tests);
    const tests = testRows.length ? testRows.slice(0, 8).map((test, index) => ({
      id: label(test, `test-${index + 1}`), model: label(test.model || test.model_id, rows[index % Math.max(1, rows.length)]?.id || 'model'),
      accuracy: percent(test.accuracy ?? test.score, 70), latency: String(test.latency || test.latency_p50 || 'n/a'),
      throughput: String(test.throughput || test.speed || 'n/a'), status: String(test.status || 'Passed')
    })) : [];
    return {
      active,
      selectedId,
      provider: rows.find(row => row.id === selectedId)?.provider || '',
      policy: String(route.policy || providerState.policy || registry.policy || 'Local First'),
      reason: 'Model inventory only; no inference route is currently executing.',
      confidence: 0,
      latency: 'n/a',
      throughput: 'n/a',
      contextWindow: 'n/a',
      cloudAllowed: false,
      registry: rows,
      runtimes, hardware, tests,
      lastRefreshAt: Date.now(), loading:false, error:''
    };
  }

  async function refreshModels(options={}) {
    BeastStore.patch('models', { loading:true, error:'' });
    if (BeastDesktopBridge.demoMode) {
      const normalized = normalizeInventory({
        registry: [
          {id:AUTO_ID, model:AUTO_ID, provider:'beast', label:'Auto (BEAST governed)', role:'Capability router', status:'Default route', governed_auto:true, selectable:true, configured:true, reachable:true, confidence:0, latency:'routed per call'},
          ...localCodingFallbackModels
        ],
        policy: 'Auto (BEAST governed)',
        family_leaders: {}
      });
      BeastStore.patch('models', normalized);
      BeastStore.addLedger('Model Router refreshed from demo telemetry');
      return normalized;
    }
    try {
      const refreshGateway = currentGateway();
      try {
        const inventory = await BeastDesktopBridge.fetchJson('/edgek/ide/model-inventory', { ...options, timeoutMs: options.timeoutMs || 8000, cacheTtl: 0 });
        if (currentGateway() !== refreshGateway) throw new Error('Gateway changed during model refresh.');
        if (inventory && Array.isArray(inventory.registry) && inventory.registry.length) {
          const normalized = normalizeInventory(inventory);
          BeastStore.patch('models', normalized);
          BeastStore.addLedger(`Model Router refreshed: ${normalized.registry.length} governed lanes`);
          return normalized;
        }
      } catch (inventoryError) {
        // Older gateways (live 8101) do not serve this inventory yet; fall through.
        if (!String(inventoryError.message || inventoryError).includes('404') && !String(inventoryError.message || inventoryError).includes('Failed to fetch') && !String(inventoryError.message || inventoryError).includes('unavailable')) {
          BeastStore.addLedger(`Governed inventory unavailable: ${String(inventoryError.message || inventoryError)}`);
        }
      }
      const query = rootQuery();
      const results = await Promise.allSettled([
        BeastDesktopBridge.fetchJson('/edgek/providers/registry', options),
        BeastDesktopBridge.fetchJson('/edgek/providers/state', options),
        BeastDesktopBridge.fetchJson(`/edgek/ide/tooling-snapshot${query}`, options),
        BeastDesktopBridge.fetchJson('/edgek/tools/integrations', options)
      ]);
      if (results[0].status !== 'fulfilled' || !results[0].value) {
        throw new Error('Provider registry unavailable: ' +
          String(results[0].reason?.message || results[0].reason || 'empty response'));
      }
      const missing = results.map((result, index) =>
        result.status === 'rejected' ? index : -1
      ).filter(index => index >= 0);
      const payloads = results.map(result => settledValue(result) ?? {});
      const ollamaInventory = typeof window.beastDesktop?.listOllamaModels === 'function'
        ? await window.beastDesktop.listOllamaModels().catch(error => ({ok:false,error:String(error.message || error)}))
        : {ok:false,error:'Ollama inventory IPC unavailable'};
      if (currentGateway() !== refreshGateway) throw new Error('Gateway changed during model refresh.');
      const normalized = normalizeModels(...payloads, {}, ollamaInventory);
      if (!ollamaInventory.ok) normalized.error = `Ollama inventory unavailable: ${ollamaInventory.error || 'unknown error'}`;
      if (missing.length) {
        normalized.error = [normalized.error, 'Partial discovery: unavailable endpoint(s) ' +
          missing.map(index => [
            'registry', 'state', 'tooling', 'integrations'
          ][index]).join(', ')].filter(Boolean).join(' | ');
      }
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
    const model = findRoute(id, state);
    if (!model) return model;
    const auto = Boolean(model.governedAuto || isAutoRoute(model.id));
    const selectedId = auto ? AUTO_ID : model.id;
    const provider = auto ? 'beast' : String(model.provider || '');
    const selectedModel = auto ? AUTO_ID : String(model.model || model.id);
    BeastStore.patch('models', {
      selectedId, selectedModel, selectedProvider: provider, provider, active: selectedId,
      reason: auto ? 'Capability router will pick a lane per task family.' : `${routeLabel(model)} pinned through the governed path.`,
      confidence: Number(model.confidence || 0) || 0,
      latency: model.latency || 'n/a',
      throughput: model.speed || 'n/a'
    });
    try {
      localStorage.setItem('beast.model', selectedId);
      localStorage.setItem('beast.provider', provider);
      window.BeastAICoding?.syncModel?.(selectedId,{explicitSelection:true});
      BeastStore.addLedger(auto ? 'Agent Coder route selected: Auto (BEAST governed)' : `Agent Coder route selected: ${provider}/${selectedModel}`);
    } catch (error) {
      BeastStore.addLedger(`Model selected for inspection: ${id} (${String(error.message || error)})`);
    }
    return model;
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
    const orchestrator = snapshot.orchestrator && typeof snapshot.orchestrator === 'object' ? snapshot.orchestrator : {};
    const permissions = firstArray(snapshot.permissions, snapshot.agent_permissions, tooling.permissions, tooling.agent_permissions).map(value => label(value, 'Permission'));
    return {
      sessions:rows,
      selectedId: BeastStore.get().agents.selectedId || rows[0]?.id || '',
      tools: [...new Set(allTools)].slice(0, 12),
      permissions,
      handoffs,
      orchestrator:{
        label:'Mission Orchestrator',
        status:String(orchestrator.status || (rows.some(row => /active|working|running/i.test(row.status)) ? 'Coordinating' : rows.length ? 'Online' : 'No active sessions')),
        health:Number(orchestrator.health ?? (rows.length ? Math.round(rows.reduce((sum,row)=>sum+row.confidence,0)/rows.length) : 0))
      },
      loading:false, error:'', lastRefreshAt:Date.now()
    };
  }

  function normalizeSwarm(snapshot={}, runsPayload={}) {
    const lanes = snapshot.role_lanes && typeof snapshot.role_lanes === 'object' ? snapshot.role_lanes : {};
    const runs = firstArray(runsPayload.runs, runsPayload.items);
    const roleLanes = Object.entries(lanes).map(([id, lane]) => ({
      id,
      label: String(id).replace(/[-_]/g, ' ').replace(/\b\w/g, char => char.toUpperCase()),
      purpose: String(lane?.purpose || ''),
      risk: String(lane?.default_risk || 'unverified')
    }));
    return {
      loading: false,
      error: '',
      enabled: typeof snapshot.enabled === 'boolean' ? snapshot.enabled : null,
      runs: Number(snapshot.runs || 0),
      statuses: snapshot.statuses || {},
      roleEvents: snapshot.role_events || {},
      value: snapshot.value || {},
      profiles: snapshot.profiles || {},
      roleLanes,
      recentRuns: runs.slice(0, 12),
      updatedAt: Date.now()
    };
  }

  async function refreshAgents(options={}) {
    BeastStore.patch('agents', { loading:true, error:'' });
    BeastStore.patch('agents', { swarm:{ ...BeastStore.get().agents.swarm, loading:true, error:'' } });
    if (BeastDesktopBridge.demoMode) {
      const normalized = normalizeAgents({ agent_sessions:{ sessions:demoAgents } }, { tools:['Code Graph','Profiler','Evidence Parser','File System','Shell','Runbook'] });
      BeastStore.patch('agents', normalized);
      BeastStore.patch('agents', { swarm:{ ...BeastStore.get().agents.swarm, loading:false, error:'Swarm service is unavailable in demo mode.', updatedAt:Date.now() } });
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
        BeastDesktopBridge.fetchJson(`/edgek/ide/tooling-snapshot${root ? `?root_path=${encodeURIComponent(root)}` : ''}`, options),
        BeastDesktopBridge.fetchJson('/edgek/swarm/state', options),
        BeastDesktopBridge.fetchJson('/edgek/swarm/runs?limit=20', options)
      ]);
      const failures = results.slice(0, 2).flatMap((result, index) => result.status === 'rejected'
        ? [`${index === 0 ? 'IDE snapshot' : 'Tooling snapshot'}: ${String(result.reason?.message || result.reason)}`]
        : []);
      if (failures.length) throw new Error(failures.join('; '));
      const normalized = normalizeAgents(settledValue(results[0]) || {}, settledValue(results[1]) || {});
      BeastStore.patch('agents', normalized);
      const swarmState = settledValue(results[2]) || {};
      const swarmRuns = settledValue(results[3]) || {};
      const swarmError = results[2].status === 'rejected' && results[3].status === 'rejected'
        ? `Swarm state: ${String(results[2].reason?.message || results[2].reason)}; swarm runs: ${String(results[3].reason?.message || results[3].reason)}`
        : results[2].status === 'rejected'
          ? `Swarm state: ${String(results[2].reason?.message || results[2].reason)}`
          : results[3].status === 'rejected' ? `Swarm runs: ${String(results[3].reason?.message || results[3].reason)}` : '';
      BeastStore.patch('agents', { swarm:{ ...normalizeSwarm(swarmState, swarmRuns), error:swarmError } });
      BeastStore.patch('mission', { metrics:{ ...BeastStore.get().mission.metrics, agents:normalized.sessions.length } });
      BeastStore.addLedger(`Agent Constellation refreshed: ${normalized.sessions.length} sessions`);
      return normalized;
    } catch (error) {
      BeastStore.patch('agents', { loading:false, error:String(error.message || error), lastRefreshAt:Date.now() });
      throw error;
    }
  }

  async function runSwarm(objective, options={}) {
    const text = String(objective || '').trim();
    if (!text) throw new Error('Swarm objective is required.');
    if (BeastDesktopBridge.demoMode) throw new Error('Swarm runs are unavailable in demo mode.');
    if (BeastStore.get().connection.status !== 'online') throw new Error('Gateway offline: no swarm run was started.');
    const result = await BeastDesktopBridge.fetchJson('/edgek/swarm/run', {
      ...options,
      method:'POST',
      body:{
        objective:text,
        profile:'hermes',
        metadata:{ initiated_by:'desktop_ide', workspace_root:BeastStore.get().workspace.root || '' }
      }
    });
    const current = BeastStore.get().agents.swarm;
    BeastStore.patch('agents', { swarm:{
      ...current,
      error:'',
      runs:current.runs + 1,
      recentRuns:[result, ...current.recentRuns.filter(run => run.run_id !== result.run_id)].slice(0, 12),
      updatedAt:Date.now()
    }});
    BeastStore.addLedger(`Governed swarm run ${result.run_id || 'completed'} · ${result.status || 'status unavailable'}`);
    await refreshAgents(options).catch(() => {});
    return result;
  }

  async function runSwarmCoding(objective, options={}) {
    const state=BeastStore.get();
    if (state.aiCoding.streaming) throw new Error('Finish or cancel the current coding run first.');
    if (!state.editor.activePath && !state.aiCoding.contextFiles?.length) throw new Error('Open or attach the target file in Agent Coder before starting a coding mission.');
    const coder=window.BeastAICoding;
    if (!coder?.send) throw new Error('Agent Coder is unavailable.');
    coder.syncModel(state.aiCoding.model || state.models.selectedId);
    const plan=await runSwarm(objective,options);
    if (plan.status !== 'ready') throw new Error(`Swarm planning returned ${plan.status || 'unknown'}; coding was not started.`);
    coder.setOpen(true);
    await coder.setMode('agent');
    if (BeastStore.get().aiCoding.mode !== 'agent') throw new Error('Agent mode transition was not completed.');
    const run=await coder.send(objective,{preserveContext:true,swarmRunId:plan.run_id});
    BeastStore.addLedger(`Swarm ${plan.run_id} handed off to coding run ${run?.run_id || 'starting'}`);
    return {plan,run};
  }

  async function createAgent(objective, options={}) {
    const text = String(objective || '').trim();
    if (!text) throw new Error('Agent objective is required.');
    const state = BeastStore.get();
    if (!BeastDesktopBridge.demoMode && state.connection.status !== 'online') {
      throw new Error('Agent session not created: BEAST gateway is offline. No execution was queued.');
    }
    if (BeastDesktopBridge.demoMode) {
      const id = `local-${Date.now()}`;
      const local = { id, label:'Local Architect', role:'Architect', status:'Queued Locally', confidence:82, task:text, provider:state.models.provider, model:state.models.selectedId || state.models.active, tools:['Code Graph','Evidence','Runbook'], files:state.editor.activePath ? 1 : 0, budget:'120K tok' };
      BeastStore.patch('agents', { sessions:[local, ...state.agents.sessions], selectedId:id, handoffs:[{time:'now',label:`Local Architect queued: ${text}`,tone:'idle'}, ...state.agents.handoffs] });
      BeastStore.addLedger(`Agent queued locally: ${text}`);
      return local;
    }
    const selectedModel = findRoute(state.models.selectedId, state);
    if (!selectedModel || !state.workspace.root) {
      throw new Error('Agent session not created: select an available model and a workspace first.');
    }
    const auto = Boolean(selectedModel.governedAuto || isAutoRoute(selectedModel.id));
    const result = await BeastDesktopBridge.fetchJson('/edgek/ide/agent-sessions/create', {
      ...options, method:'POST', body:{ root_path:state.workspace.root, objective:text, mode:'architect', provider:auto ? 'beast' : selectedModel.provider, model:auto ? 'auto' : (selectedModel.model || selectedModel.id), governed_auto:auto, files:state.editor.activePath ? [state.editor.activePath] : [], budget:{ tokens:120000, seconds:3600, cost_usd:0 } }
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
    if (!BeastDesktopBridge.demoMode && (state.connection.status !== 'online' || String(id).startsWith('local-'))) {
      throw new Error('Agent control refused: no confirmed live agent session is available.');
    }
    if (BeastDesktopBridge.demoMode) {
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

  window.BeastModelAgentBridge = { refreshModels, verifyHostedNemotron, selectModel, refreshAgents, createAgent, runSwarm, runSwarmCoding, selectAgent, controlAgent, fillModelSelect, findRoute, isAutoRoute, routeLabel, AUTO_ID };
})();
