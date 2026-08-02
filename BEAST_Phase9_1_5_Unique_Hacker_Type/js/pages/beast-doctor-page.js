(() => {
  const esc = value => String(value ?? '').replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  const clamp = value => Math.max(0,Math.min(100,Number(value)||0));

  function template() {
    const root=document.createElement('div');
    root.className='beast-page beast-doctor-page';
    root.innerHTML=`
      <header class="beast-page-head">
        <div><h2>Doctor Diagnostics</h2><div class="sub">GATEWAY CONTRACTS // SYSTEM PLANE // ROUTE HEALTH // REPAIR GUIDANCE // OPERATOR REPORT</div></div>
        <div class="beast-page-actions">
          <button class="beast-button secondary" data-doctor-action="copy"><img src="${BeastAssets.icon('files')}" alt="">Copy Report</button>
          <button class="beast-button secondary" data-doctor-action="restart"><img src="${BeastAssets.icon('system')}" alt="">Restart Gateway</button>
          <button class="beast-button hot" data-doctor-action="scan"><img src="${BeastAssets.icon('doctor')}" alt="">Run Deep Scan</button>
        </div>
      </header>

      <div class="doctor-hero-grid">
        <section class="beast-card doctor-score-panel is-active">
          <header class="beast-panel-head"><div><h3>BEAST Health Score</h3><span data-doctor-scan-time>Awaiting diagnostic run</span></div><span class="beast-pill" data-doctor-status>CHECKING</span></header>
          <div class="doctor-core-display">
            <div class="doctor-orbit"><img src="${BeastAssets.icon('doctor')}" alt=""><i></i><i></i><i></i></div>
            <div class="doctor-score-ring" style="--score:0"><strong data-doctor-score>0%</strong><span data-doctor-grade>CHECKING</span></div>
          </div>
          <div class="doctor-score-caption">Every route is checked independently. One failed endpoint does not repaint the entire interface.</div>
        </section>

        <section class="beast-card wide doctor-check-panel">
          <header class="beast-panel-head"><div><h3>Core Contract Checks</h3><span>Live gateway and local fallback surfaces</span></div><span class="beast-pill live" data-doctor-check-count>0/0</span></header>
          <div class="doctor-check-grid" data-doctor-checks></div>
        </section>
      </div>

      <section class="doctor-resource-grid">
        <article class="beast-card compact doctor-resource-card"><img src="${BeastAssets.icon('network')}" alt=""><div><h3>Listening Ports</h3><strong data-doctor-ports>0</strong><span>attributed endpoints</span></div></article>
        <article class="beast-card compact doctor-resource-card"><img src="${BeastAssets.icon('system')}" alt=""><div><h3>Processes</h3><strong data-doctor-processes>0</strong><span>observed runtime tasks</span></div></article>
        <article class="beast-card compact doctor-resource-card"><img src="${BeastAssets.icon('context')}" alt=""><div><h3>Python</h3><strong data-doctor-python>n/a</strong><span data-doctor-venv>environment</span></div></article>
        <article class="beast-card compact doctor-resource-card"><img src="${BeastAssets.icon('plugins')}" alt=""><div><h3>Editor Commands</h3><strong data-doctor-vscode>0</strong><span>VS Code integration</span></div></article>
      </section>

      <div class="doctor-main-grid">
        <section class="beast-card doctor-routes-panel">
          <header class="beast-panel-head"><div><h3>Route Health Matrix</h3><span>Latency and failure isolation</span></div><button class="beast-button secondary" data-nav="tooling"><img src="${BeastAssets.icon('tooling')}" alt="">Tooling Forge</button></header>
          <div class="doctor-route-list" data-doctor-routes></div>
        </section>
        <section class="beast-card doctor-recommend-panel">
          <header class="beast-panel-head"><div><h3>Recommended Actions</h3><span>Ranked by operational leverage</span></div><span class="beast-pill" data-doctor-recommend-count>0 ITEMS</span></header>
          <div class="doctor-recommendations" data-doctor-recommendations></div>
        </section>
      </div>

      <div class="doctor-system-grid">
        <section class="beast-card doctor-ports-panel">
          <header class="beast-panel-head"><div><h3>Port Ownership</h3><span>Listening services</span></div><button class="beast-button secondary" data-nav="terminal"><img src="${BeastAssets.icon('terminal')}" alt="">Open Terminal</button></header>
          <div class="doctor-table" data-doctor-port-list></div>
        </section>
        <section class="beast-card doctor-process-panel">
          <header class="beast-panel-head"><div><h3>Runtime Processes</h3><span>Memory and status overview</span></div><span class="beast-pill live">LOCAL VIEW</span></header>
          <div class="doctor-table" data-doctor-process-list></div>
        </section>
      </div>

      <details class="beast-card doctor-raw-panel"><summary><img src="${BeastAssets.icon('diagnostics')}" alt="">Doctor Report Payload</summary><pre data-doctor-raw></pre></details>`;
    return root;
  }

  function renderer() {
    const root=template();
    let disposed=false;
    let renderKey='';

    function patch(state) {
      if (disposed) return;
      const doctor=state.doctor;
      const key=JSON.stringify(doctor);
      if (key===renderKey) return; renderKey=key;
      const score=clamp(doctor.score);
      root.querySelector('[data-doctor-score]').textContent=`${score}%`;
      root.querySelector('[data-doctor-grade]').textContent=String(doctor.status || 'checking').toUpperCase();
      root.querySelector('.doctor-score-ring').style.setProperty('--score',score);
      root.querySelector('[data-doctor-scan-time]').textContent=doctor.lastScanAt?`Last scan ${new Date(doctor.lastScanAt).toLocaleTimeString()}`:'Awaiting diagnostic run';
      const status=root.querySelector('[data-doctor-status]');
      status.textContent=doctor.loading?'SCANNING':String(doctor.status || 'checking').toUpperCase();
      status.className=`beast-pill ${score>=90?'live':score>=60?'warn':'bad'}`;
      const healthy=doctor.checks.filter(item=>item.ok || item.status==='healthy').length;
      root.querySelector('[data-doctor-check-count]').textContent=`${healthy}/${doctor.checks.length}`;
      root.querySelector('[data-doctor-checks]').innerHTML=doctor.checks.length ? doctor.checks.map((item,index)=>`<article class="${item.ok || item.status==='healthy'?'ok':'failed'}"><span>${String(index+1).padStart(2,'0')}</span><img src="${BeastAssets.icon(item.ok || item.status==='healthy'?'trust':'alerts')}" alt=""><div><b>${esc(item.label)}</b><small>${esc(item.detail || item.status || '')}</small></div><em>${esc(item.latency || 'n/a')}</em></article>`).join('') : '<div class="cortex-empty-list">Run a deep scan to populate contract checks.</div>';
      const system=doctor.system || {};
      const summary=system.summary || {};
      const ports=system.ports?.ports || [];
      const processes=system.processes?.processes || [];
      root.querySelector('[data-doctor-ports]').textContent=String(summary.listening_ports ?? ports.length ?? 0);
      root.querySelector('[data-doctor-processes]').textContent=String(summary.processes_total ?? processes.length ?? 0);
      root.querySelector('[data-doctor-python]').textContent=String(summary.python || system.environment?.python?.version || 'n/a').replace(/^Python\s*/i,'');
      root.querySelector('[data-doctor-venv]').textContent=summary.in_virtualenv || system.environment?.python?.in_virtualenv ? 'virtual environment' : 'system environment';
      root.querySelector('[data-doctor-vscode]').textContent=String(summary.vscode_commands ?? system.extensions?.vscode_extension?.command_count ?? 0);
      root.querySelector('[data-doctor-routes]').innerHTML=doctor.routes.length ? doctor.routes.map(route=>`<article class="${route.ok?'ok':'failed'}"><img src="${BeastAssets.icon(route.ok?'network':'alerts')}" alt=""><span><b>${esc(route.path || route.label || route.id)}</b><small>${esc(route.detail || route.error || route.status || '')}</small></span><em>${esc(route.latency || (route.ok?'READY':'OFFLINE'))}</em></article>`).join('') : '<div class="cortex-empty-list">No route diagnostics loaded.</div>';
      root.querySelector('[data-doctor-recommend-count]').textContent=`${doctor.recommendations.length} ITEMS`;
      root.querySelector('[data-doctor-recommendations]').innerHTML=doctor.recommendations.length ? doctor.recommendations.map((item,index)=>`<article class="${item.tone || ''}"><span>${String(index+1).padStart(2,'0')}</span><img src="${BeastAssets.icon(item.tone==='good'?'trust':'alerts')}" alt=""><div><b>${esc(item.title)}</b><small>${esc(item.detail)}</small></div><button data-doctor-recommend-action="${esc(item.action || '')}">${esc(item.action || 'Inspect')}</button></article>`).join('') : '<div class="cortex-empty-list">No repair action is currently recommended.</div>';
      root.querySelector('[data-doctor-port-list]').innerHTML=ports.length ? ports.slice(0,12).map(item=>`<div><span><b>${esc(item.proto || 'tcp')} :${esc(item.port)}</b><small>${esc(item.address || '')}</small></span><em>${esc(item.process || 'unattributed')} ${item.pid?`· ${esc(item.pid)}`:''}</em></div>`).join('') : '<div class="cortex-empty-list">No listening ports reported.</div>';
      root.querySelector('[data-doctor-process-list]').innerHTML=processes.length ? processes.slice(0,12).map(item=>`<div><span><b>${esc(item.name || 'process')}</b><small>pid ${esc(item.pid || 'n/a')} · ${esc(item.user || item.status || '')}</small></span><em>${esc(item.rss_mb ?? item.memory_mb ?? 0)} MB</em></div>`).join('') : '<div class="cortex-empty-list">No process inventory reported.</div>';
      root.querySelector('[data-doctor-raw]').textContent=JSON.stringify(doctor.report || {},null,2);
    }

    const unsubscribe=BeastStore.subscribe(patch);
    root.addEventListener('click',async event=>{
      const recommendation=event.target.closest('[data-doctor-recommend-action]');
      if (recommendation) {
        const action=recommendation.dataset.doctorRecommendAction.toLowerCase();
        if (action.includes('tooling')) return BeastRouter.navigate('tooling');
        if (action.includes('terminal')) return BeastRouter.navigate('terminal');
        if (action.includes('refresh')) return BeastTerminalToolingDoctorBridge.refreshDoctor();
      }
      const action=event.target.closest('[data-doctor-action]')?.dataset.doctorAction;
      if (!action) return;
      try {
        if (action==='scan') await BeastTerminalToolingDoctorBridge.refreshDoctor();
        if (action==='restart') await BeastTerminalToolingDoctorBridge.restartGateway();
        if (action==='copy') await BeastTerminalToolingDoctorBridge.copyDoctorReport();
        BeastFX.trigger('success',event.target,{size:210});
      } catch(error){ BeastStore.patch('doctor',{loading:false,error:String(error.message||error),status:'Degraded'}); BeastFX.trigger('warning',event.target,{size:230}); }
    });
    if (!BeastStore.get().doctor.lastScanAt) queueMicrotask(()=>BeastTerminalToolingDoctorBridge.refreshDoctor().catch(()=>{}));
    return {node:root,dispose(){disposed=true;unsubscribe();}};
  }

  window.BeastDoctorPage={renderer};
})();
