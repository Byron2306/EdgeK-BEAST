(() => {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[char]);
  const safe = value => Math.max(0, Math.min(100, Number(value) || 0));

  function template() {
    const root = document.createElement('div');
    root.className = 'beast-page beast-models-page';
    root.innerHTML = `
      <header class="beast-page-head">
        <div><h2>Model Router</h2><div class="sub">LOCAL-FIRST CASCADE // CAPABILITY FIT // LATENCY GUARD // GOVERNED ESCALATION</div></div>
        <div class="beast-page-actions"><button class="beast-button secondary" data-model-action="control"><img src="${BeastAssets.icon('compute')}" alt="">Compute Control</button><button class="beast-button secondary" data-model-action="policy"><img src="${BeastAssets.icon('policies')}" alt="">Route Policy</button><button class="beast-button hot" data-model-action="refresh"><img src="${BeastAssets.icon('diagnostics')}" alt="">Refresh Router</button></div>
      </header>
      <section class="model-summary-grid">
        <article class="beast-card model-summary-card"><img src="${BeastAssets.icon('target-lock')}" alt=""><div><h3>Active Route</h3><strong data-model-active>checking</strong><span data-model-provider>provider</span></div></article>
        <article class="beast-card model-summary-card"><img src="${BeastAssets.icon('models')}" alt=""><div><h3>Route Confidence</h3><strong data-model-confidence>0%</strong><span data-model-reason>capability fit</span></div></article>
        <article class="beast-card model-summary-card"><img src="${BeastAssets.icon('compute')}" alt=""><div><h3>Throughput</h3><strong data-model-throughput>n/a</strong><span data-model-latency>latency n/a</span></div></article>
        <article class="beast-card model-summary-card"><img src="${BeastAssets.icon('policies')}" alt=""><div><h3>Routing Policy</h3><strong data-model-policy>Local First</strong><span data-model-cloud>cloud locked</span></div></article>
        <article class="beast-card model-summary-card"><img src="${BeastAssets.icon('compute')}" alt=""><div><h3>Hardware</h3><strong data-model-hardware>local compute</strong><span data-model-hardware-state>checking</span></div></article>
      </section>

      <div class="models-main-grid">
        <section class="beast-card wide model-route-panel">
          <header class="beast-panel-head"><div><h3>Inference Cascade</h3><span>Request classification and fallback ladder</span></div><span class="beast-pill live" data-route-state>ROUTE READY</span></header>
          <div class="model-route-map">
            <canvas class="premium-route-canvas" data-premium-canvas="route" aria-hidden="true"></canvas>
            <article class="route-map-node request"><img src="${BeastAssets.icon('terminal')}" alt=""><b>Operator Request</b><span>Code · Reason · Plan</span></article>
            <article class="route-map-node decision"><img src="${BeastAssets.icon('context')}" alt=""><b>Route Governor</b><span data-route-decision>Capability + policy</span><em>LOCAL FIRST</em></article>
            <article class="route-map-node primary"><img src="${BeastAssets.icon('models')}" alt=""><b data-primary-name>Primary model</b><span data-primary-meta>context · speed</span><em>ACTIVE</em></article>
            <article class="route-map-node fallback"><img src="${BeastAssets.icon('network')}" alt=""><b data-fallback-name>Fallback model</b><span data-fallback-meta>standby route</span><em>STANDBY</em></article>
            <article class="route-map-node escalation"><img src="${BeastAssets.icon('network')}" alt=""><b>Escalation Gate</b><span data-cloud-gate>Cloud blocked by policy</span><em>GOVERNED</em></article>
          </div>
          <div class="routing-rule-grid" data-routing-rules></div>
        </section>

        <section class="beast-card model-registry-panel">
          <header class="beast-panel-head"><div><h3>Model Registry</h3><span data-model-count>0 routes</span></div><button class="beast-button secondary" data-model-action="refresh"><img src="${BeastAssets.icon('diagnostics')}" alt="">Scan</button></header>
          <div class="model-filter-row"><input class="beast-filter" data-model-filter placeholder="Filter model routes…"><select data-model-runtime-filter><option value="all">All runtimes</option></select></div>
          <div class="model-registry-list" data-model-list></div>
        </section>
      </div>

      <section class="model-runtime-grid" data-runtime-list></section>

      <div class="models-lower-grid">
        <section class="beast-card wide model-benchmark-panel">
          <header class="beast-panel-head"><div><h3>Route Trials</h3><span>Observed quality, latency and throughput</span></div><button class="beast-button secondary" data-model-action="test"><img src="${BeastAssets.icon('diagnostics')}" alt="">Run Diagnostic</button></header>
          <div class="model-benchmark-list" data-model-tests></div>
        </section>
        <section class="beast-card model-detail-panel" data-model-detail></section>
      </div>`;
    return root;
  }

  function renderer({ signal }) {
    const root = template();
    let disposed = false;
    let filterText = '';
    let runtimeFilter = 'all';
    let registryKey = '';
    let runtimeKey = '';
    let testKey = '';
    const disposeCanvas = BeastVisualCanvas.auto(root);

    function renderRegistry(state) {
      const models = state.models.registry || [];
      const key = JSON.stringify([models, state.models.selectedId, filterText, runtimeFilter]);
      if (key === registryKey) return;
      registryKey = key;
      const runtimes = [...new Set(models.map(model => model.runtime).filter(Boolean))];
      const select = root.querySelector('[data-model-runtime-filter]');
      const selected = select.value || runtimeFilter;
      select.innerHTML = `<option value="all">All runtimes</option>${runtimes.map(runtime => `<option value="${esc(runtime)}">${esc(runtime)}</option>`).join('')}`;
      select.value = runtimes.includes(selected) ? selected : 'all';
      runtimeFilter = select.value;
      const visible = models.filter(model => (!filterText || `${model.id} ${model.provider} ${model.runtime}`.toLowerCase().includes(filterText)) && (runtimeFilter === 'all' || model.runtime === runtimeFilter));
      root.querySelector('[data-model-count]').textContent = `${models.length} routes`;
      root.querySelector('[data-model-list]').innerHTML = visible.length ? visible.map(model => `
        <button class="model-registry-row ${model.id === state.models.active ? 'primary' : ''} ${model.id === state.models.selectedId ? 'selected' : ''}" data-model-id="${esc(model.id)}">
          <img src="${BeastAssets.icon(model.id === state.models.active ? 'models' : 'model-cube')}" alt="">
          <span><b>${esc(model.id)}</b><small>${esc(model.provider)} · ${esc(model.runtime)} · ${esc(model.quantization || 'native')}</small></span>
          <em>${esc(model.role)}</em><i>${safe(model.confidence)}%</i>
        </button>`).join('') : '<div class="cortex-empty-list">No model routes match this filter.</div>';
    }

    function renderRuntimes(state) {
      const key = JSON.stringify(state.models.runtimes || []);
      if (key === runtimeKey) return; runtimeKey = key;
      root.querySelector('[data-runtime-list]').innerHTML = (state.models.runtimes || []).map((runtime, index) => `
        <article class="beast-card compact model-runtime-card ${/offline|error|failed/i.test(runtime.status) ? 'danger' : ''}">
          <img src="${BeastAssets.icon(index % 2 ? 'compute' : 'providers')}" alt=""><div><h3>${esc(runtime.label)}</h3><b>${esc(runtime.status)}</b><span>${esc(runtime.detail || 'Runtime route')}</span></div><i></i>
        </article>`).join('');
    }

    function renderTests(state) {
      const key = JSON.stringify(state.models.tests || []);
      if (key === testKey) return; testKey = key;
      root.querySelector('[data-model-tests]').innerHTML = (state.models.tests || []).map(test => `
        <div class="model-benchmark-row"><span><b>${esc(test.model)}</b><small>${esc(test.status)}</small></span><div class="model-score-track"><i style="--score:${safe(test.accuracy)}%"></i></div><strong>${safe(test.accuracy)}%</strong><em>${esc(test.latency)}</em><em>${esc(test.throughput)}</em></div>`).join('') || '<div class="cortex-empty-list">No route trials reported.</div>';
    }

    function patch(state) {
      if (disposed) return;
      const models = state.models;
      const primary = models.registry.find(model => model.id === models.active) || models.registry[0] || {};
      const fallback = models.registry.find(model => model.id !== primary.id && /fallback/i.test(model.role)) || models.registry.find(model => model.id !== primary.id) || {};
      const selected = models.registry.find(model => model.id === models.selectedId) || primary;
      root.querySelector('[data-model-active]').textContent = models.active || 'no route';
      root.querySelector('[data-model-provider]').textContent = `${models.provider || 'provider'} · ${primary.runtime || 'runtime'}`;
      root.querySelector('[data-model-confidence]').textContent = `${safe(models.confidence)}%`;
      root.querySelector('[data-model-reason]').textContent = models.reason || 'capability fit';
      root.querySelector('[data-model-throughput]').textContent = models.throughput || 'n/a';
      root.querySelector('[data-model-latency]').textContent = `latency ${models.latency || 'n/a'}`;
      root.querySelector('[data-model-policy]').textContent = models.policy || 'Local First';
      root.querySelector('[data-model-cloud]').textContent = models.cloudAllowed ? 'cloud gate armed' : 'cloud locked';
      root.querySelector('[data-model-hardware]').textContent = models.hardware?.name || 'local compute';
      root.querySelector('[data-model-hardware-state]').textContent = `${models.hardware?.status || 'checking'} · ${models.hardware?.vram || 'n/a'}`;
      root.querySelector('[data-route-state]').textContent = models.loading ? 'SCANNING' : models.error ? 'ROUTE DEGRADED' : 'ROUTE READY';
      root.querySelector('[data-route-state]').classList.toggle('bad', Boolean(models.error));
      root.querySelector('[data-route-decision]').textContent = models.reason || 'Capability + policy';
      root.querySelector('[data-primary-name]').textContent = primary.id || 'Primary model';
      root.querySelector('[data-primary-meta]').textContent = `${primary.context || models.contextWindow || 'n/a'} · ${primary.speed || models.throughput || 'n/a'}`;
      root.querySelector('[data-fallback-name]').textContent = fallback.id || 'No fallback';
      root.querySelector('[data-fallback-meta]').textContent = fallback.id ? `${fallback.context || 'n/a'} · ${fallback.speed || 'n/a'}` : 'Standby route absent';
      root.querySelector('[data-cloud-gate]').textContent = models.cloudAllowed ? 'Escalation route available' : 'Cloud blocked by policy';
      root.querySelector('[data-routing-rules]').innerHTML = (models.rules || []).map(rule => `<div class="routing-rule ${rule.enabled ? 'enabled' : ''}"><span>${rule.enabled ? '✓' : '○'}</span><b>${esc(rule.label)}</b><small>${esc(rule.detail)}</small></div>`).join('');
      root.querySelector('[data-model-detail]').innerHTML = selected ? `<header class="beast-panel-head"><div><h3>Selected Model</h3><span>${esc(selected.role || 'Route')}</span></div><span class="beast-pill ${selected.status === 'Ready' ? 'live' : ''}">${esc(selected.status || 'Unknown')}</span></header><div class="model-detail-hero"><img src="${BeastAssets.icon('models')}" alt=""><div><strong>${esc(selected.id || 'No model selected')}</strong><span>${esc(selected.provider || '')}</span></div></div><div class="beast-rail-facts"><div><span>Context</span><b>${esc(selected.context || 'n/a')}</b></div><div><span>Quantization</span><b>${esc(selected.quantization || 'n/a')}</b></div><div><span>Confidence</span><b>${safe(selected.confidence)}%</b></div><div><span>Latency</span><b>${esc(selected.latency || 'n/a')}</b></div><div><span>Throughput</span><b>${esc(selected.speed || 'n/a')}</b></div><div><span>Runtime</span><b>${esc(selected.runtime || 'n/a')}</b></div></div><div class="model-detail-actions"><button class="beast-button hot model-stage-button" data-model-action="stage" ${selected.id === models.active ? 'disabled' : ''}>${selected.id === models.active ? 'Active Primary' : 'Stage as Primary'}</button><button class="beast-button secondary" data-model-action="terminal">Use in Terminal Chat</button></div>` : '<h3>Selected Model</h3><p>No model route available.</p>';
      renderRegistry(state); renderRuntimes(state); renderTests(state);
    }

    const unsubscribe = BeastStore.subscribe(patch);
    root.addEventListener('input', event => { if (event.target.matches('[data-model-filter]')) { filterText = event.target.value.trim().toLowerCase(); registryKey = ''; patch(BeastStore.get()); } });
    root.addEventListener('change', event => { if (event.target.matches('[data-model-runtime-filter]')) { runtimeFilter = event.target.value; registryKey = ''; patch(BeastStore.get()); } });
    root.addEventListener('click', async event => {
      const model = event.target.closest('[data-model-id]');
      if (model) { BeastModelAgentBridge.selectModel(model.dataset.modelId); BeastFX.trigger('ring', model, {size:160}); return; }
      const action = event.target.closest('[data-model-action]')?.dataset.modelAction;
      if (!action) return;
      try {
        if (action === 'refresh') { await BeastModelAgentBridge.refreshModels({signal}); document.dispatchEvent(new CustomEvent('beast:operation',{detail:{message:'Model Router refreshed from live provider registry',tone:'ok'}})); BeastFX.trigger('burst',event.target,{size:220}); }
        if (action === 'test') {
          await BeastModelAgentBridge.refreshModels({signal});
          const model=BeastStore.get().models.registry.find(item=>item.id===BeastStore.get().models.selectedId)||BeastStore.get().models.registry.find(item=>item.id===BeastStore.get().models.active);
          if(!model?.provider) throw new Error('Select a model with a live provider route before running a diagnostic.');
          await BeastUtilityOrchestrationBridge.refreshProviders();
          BeastStore.patch('providers',{selectedId:model.provider});
          const result=await BeastUtilityOrchestrationBridge.providerAction('smoke');
          const trial={model:model.id,status:result?.ok===false?'Failed':'Route analyzed',accuracy:Number(result?.route_quality_score??result?.quality??result?.score??0)*((Number(result?.route_quality_score??result?.quality??result?.score??0)<=1)?100:1),latency:String(result?.latency_ms??result?.latency??'diagnostic complete'),throughput:String(result?.throughput??'governed')};
          BeastStore.patch('models',{tests:[trial,...(BeastStore.get().models.tests||[]).filter(item=>item.model!==model.id)].slice(0,8),error:''});
          document.dispatchEvent(new CustomEvent('beast:operation',{detail:{message:`Model diagnostic complete · ${model.id} · ${Math.round(trial.accuracy)}% route quality`,tone:'ok'}}));
          BeastFX.trigger('success',event.target,{size:220});
        }
        if (action === 'policy') { BeastStore.addLedger('Routing policy inspection requested'); document.dispatchEvent(new CustomEvent('beast:command',{detail:{command:'/policy show'}})); }
        if (action === 'control') { await BeastUtilityOrchestrationBridge.refreshControl(); await BeastRouter.navigate('compute-control'); }
        if (action === 'stage') { const id = BeastStore.get().models.selectedId; if (id) { BeastStore.patch('models',{active:id}); localStorage.setItem('beast.model',id); BeastStore.addLedger(`Primary route staged locally: ${id}`); BeastFX.trigger('success', event.target,{size:250}); } }
        if (action === 'terminal') { BeastTerminalToolingDoctorBridge.syncModelSelection(BeastStore.get().models.selectedId || BeastStore.get().models.active || ''); BeastStore.addLedger('Terminal chat primed from selected model'); await BeastRouter.navigate('terminal'); BeastFX.trigger('success', event.target,{size:250}); }
      } catch (error) { const message=String(error.message||error); BeastStore.patch('models',{loading:false,error:message}); document.dispatchEvent(new CustomEvent('beast:operation',{detail:{message:`Model action failed · ${message}`,tone:'error'}})); BeastFX.trigger('warning',event.target,{size:230}); }
    });
    if (!BeastStore.get().models.lastRefreshAt) queueMicrotask(() => BeastModelAgentBridge.refreshModels({signal}).catch(() => {}));
    return { node:root, dispose(){ disposed = true; unsubscribe(); disposeCanvas(); } };
  }

  window.BeastModelsPage = { renderer };
})();
