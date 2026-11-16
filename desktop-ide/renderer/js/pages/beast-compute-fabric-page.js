(() => {
  const esc = value => String(value ?? '—').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));
  const routes = [
    ['semantic_result', 'Semantic Result', 'read_verified'],
    ['promoted_crystal', 'Promoted Crystal', 'one_use_execute'],
    ['native_context', 'Native Context', 'context_only'],
    ['prefix_replay', 'Prefix Cache', 'context_only'],
    ['warm_model', 'Warm Model', 'inference_only'],
    ['fresh_ollama', 'Fresh Ollama', 'inference_only'],
    ['fresh_llamacpp', 'Fresh llama.cpp', 'inference_only'],
    ['remote_residual', 'Remote Residual', 'reconstruction_only'],
    ['provider', 'Provider', 'provider_call'],
  ];
  let refreshPromise = null;

  function statusFor(state, key) {
    const route = state.computeFabric?.routes?.[key] || state.control?.prism?.routes?.[key] || {};
    const selected = state.computeFabric?.selectedRoute || state.models?.activeRoute || state.models?.route || '';
    return { ...route, active:selected === key, verified:typeof route.eligible === 'boolean' };
  }

  async function refreshFabric() {
    if (refreshPromise) return refreshPromise;
    BeastStore.patch('computeFabric', { loading:true, error:'' });
    const bridge = window.BeastUtilityOrchestrationBridge;
    const jobs = [
      ['platform', bridge?.refreshPlatform],
      ['control', bridge?.refreshControl],
      ['economy', bridge?.refreshEconomy],
    ];
    const results = await Promise.allSettled(jobs.map(([name, refresh]) => (
      typeof refresh === 'function'
        ? refresh()
        : Promise.reject(new Error(`${name} refresh is unavailable`))
    )));
    const errors = results.flatMap((result, index) => {
      if (result.status === 'rejected') return [`${jobs[index][0]}: ${String(result.reason?.message || result.reason)}`];
      return Object.entries(result.value?.errors || {}).map(([key, message]) => `${key}: ${message}`);
    });
    const state = BeastStore.get();
    for (const key of ['platform', 'control', 'economy']) {
      if (state[key]?.error) errors.push(`${key}: ${state[key].error}`);
    }
    const uniqueErrors = [...new Set(errors)];
    const error = uniqueErrors.join('; ');
    BeastStore.patch('computeFabric', { loading:false, error, updatedAt:Date.now() });
    return { ok:!error, error };
  }

  function renderer() {
    const root = document.createElement('div');
    root.className = 'beast-page beast-compute-fabric-page';
    root.innerHTML = `<header class="beast-page-head"><div><h2>Compute Fabric</h2><div class="sub">PRISM ROUTING // KV RESIDUE // CAPSULE ECONOMICS // REMOTE RECONSTRUCTION</div></div><div class="beast-page-actions"><button class="beast-button secondary" data-nav="live-fabric">Live Fabric</button><button class="beast-button secondary" data-nav="reality">Reality Matrix</button><button class="beast-button hot" data-fabric-refresh>Refresh Fabric</button></div></header><div class="cortex-empty-list" data-fabric-status role="status" aria-live="polite"></div><section class="fabric-route-map" data-route-map></section><div class="fabric-grid"><section class="beast-card wide"><header class="beast-panel-head"><div><h3>Decision Trace</h3><span>Why this route won</span></div><span class="beast-pill" data-selected-route>UNRESOLVED</span></header><div data-decision-trace></div></section><section class="beast-card"><header class="beast-panel-head"><div><h3>KV & Context</h3><span>Engine-local residue</span></div></header><div data-kv-stack></div></section><section class="beast-card"><header class="beast-panel-head"><div><h3>Economics</h3><span>Value after real costs</span></div></header><div data-economics></div></section><section class="beast-card"><header class="beast-panel-head"><div><h3>Pressure</h3><span>Retention and eviction</span></div></header><div data-pressure></div></section></div>`;
    let disposed = false;

    const render = state => {
      if (disposed) return;
      const compute = state.computeFabric || {};
      const selected = compute.selectedRoute || state.control?.prism?.selected_route || state.models?.activeRoute || state.models?.route || 'unresolved';
      root.querySelector('[data-selected-route]').textContent = String(selected).toUpperCase();
      root.querySelector('[data-route-map]').innerHTML = routes.map(([key, label, authority], index) => {
        const route = statusFor(state, key);
        const outcome = route.active ? 'SELECTED' : route.eligible === true ? 'ELIGIBLE' : route.eligible === false ? 'REFUSED' : 'UNVERIFIED';
        const className = route.active ? 'active' : route.eligible === true ? 'eligible' : route.eligible === false ? 'ineligible' : 'unverified';
        const cost = route.cost ?? route.estimated_cost ?? 'cost not reported';
        return `<button class="fabric-route ${className}" data-capsule-route="${key}"><span>${index + 1}</span><b>${label}</b><small>${esc(cost)} · ${authority}</small><em>${outcome}</em></button>`;
      }).join('<i>›</i>');

      const trace = compute.decisionTrace || state.control?.prism?.decision_trace || [];
      root.querySelector('[data-decision-trace]').innerHTML = (trace.length ? trace : ['No verified decision trace received.']).map((item, index) => (
        `<div class="fabric-trace-row"><span>${index + 1}</span><b>${esc(typeof item === 'string' ? item : item.message || item.reason)}</b><em>${esc(typeof item === 'object' ? item.status || 'unverified' : 'unverified')}</em></div>`
      )).join('');

      const kv = state.providers?.kv || state.models?.kv || {};
      root.querySelector('[data-kv-stack]').innerHTML = [
        ['llama.cpp', kv.llamacpp || state.models?.llamacpp],
        ['Local Prefix', kv.local_prefix], ['LMCache', kv.lmcache],
        ['vLLM', kv.vllm], ['SGLang', kv.sglang],
        ['TensorRT-LLM', kv.tensorrt], ['TGI', kv.tgi],
      ].map(([name, value]) => `<div class="fabric-status-row"><b>${name}</b><span>${esc(value?.status || value || 'UNREPORTED')}</span><em>${esc(value?.cache_n ?? value?.reuse ?? '—')}</em></div>`).join('');

      const economy = state.economy || {};
      root.querySelector('[data-economics]').innerHTML = `<div class="fabric-big-number">${esc(economy.netSavings ?? economy.savedTokens ?? 'not reported')}</div><p>Net avoided compute</p><div class="fabric-mini-grid"><span>Debt <b>${esc(economy.preparationDebt ?? '—')}</b></span><span>Break-even <b>${esc(economy.breakEven ?? '—')}</b></span><span>Credits <b>${esc(economy.credits ?? '—')}</b></span></div>`;
      const pressure = state.system?.pressure || state.system?.psi || {};
      root.querySelector('[data-pressure]').innerHTML = `<div class="pressure-orb ${esc((pressure.status || 'unknown').toLowerCase())}"><b>${esc(pressure.status || 'UNREPORTED')}</b></div><div class="fabric-mini-grid"><span>Memory <b>${esc(pressure.memory ?? '—')}</b></span><span>Pins <b>${esc(pressure.pins ?? '—')}</b></span><span>Evictions <b>${esc(pressure.evictions ?? '—')}</b></span></div>`;

      const status = root.querySelector('[data-fabric-status]');
      status.textContent = compute.loading ? 'Checking live compute contracts…'
        : compute.error ? `Refresh failed: ${compute.error}`
          : compute.updatedAt ? 'Snapshot loaded; routes without an explicit eligibility result remain unverified.'
            : 'No compute-fabric snapshot loaded yet.';
    };

    const unsubscribe = BeastStore.subscribe(render);
    render(BeastStore.get());
    if (!BeastStore.get().computeFabric?.updatedAt) {
      queueMicrotask(() => {
        refreshPromise = refreshFabric().finally(() => { refreshPromise = null; });
      });
    }
    root.addEventListener('click', async event => {
      const routeKey = event.target.closest('[data-capsule-route]')?.dataset.capsuleRoute;
      if (routeKey) {
        const state = BeastStore.get();
        const route = statusFor(state, routeKey);
        const metadata = routes.find(item => item[0] === routeKey);
        BeastCapsuleInspector.open({
          name:metadata?.[1],
          identity:`route:${routeKey}`,
          sealed:routeKey === 'promoted_crystal',
          authorized:route.eligible === true && route.active,
          authority:metadata?.[2],
          digest:route.digest,
          workspace:state.workspace?.root,
          policy:state.trust?.policyGeneration,
          promotion:routeKey === 'promoted_crystal' ? 'promoted' : 'not applicable',
          pressure:state.system?.pressure?.status,
        });
      }
      if (event.target.closest('[data-fabric-refresh]')) {
        document.dispatchEvent(new CustomEvent('beast:operation', { detail:{ message:'Compute Fabric refresh requested', tone:'ok' } }));
        if (!refreshPromise) {
          refreshPromise = refreshFabric().finally(() => { refreshPromise = null; });
        } else await refreshPromise;
      }
    });
    return {
      node:root,
      dispose() { disposed = true; unsubscribe?.(); },
    };
  }

  window.BeastComputeFabricPage = { renderer };
})();
