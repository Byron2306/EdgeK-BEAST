(() => {
  const esc = value => String(value ?? '').replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  const count = value => Array.isArray(value) ? value.length : Number(value || 0);

  function template() {
    const root=document.createElement('div');
    root.className='beast-page beast-tooling-page';
    root.innerHTML=`
      <header class="beast-page-head">
        <div><h2>Tooling Forge</h2><div class="sub">SYNTAX // LINT // MCP BROKER // PLUGIN REGISTRY // ENVIRONMENT // CAPABILITY MANIFEST</div></div>
        <div class="beast-page-actions">
          <button class="beast-button secondary" data-tooling-action="manifest"><img src="${BeastAssets.icon('policies')}" alt="">Validate Manifest</button>
          <button class="beast-button secondary" data-tooling-action="benchmark"><img src="${BeastAssets.icon('diagnostics')}" alt="">Benchmark Daemon</button>
          <button class="beast-button hot" data-tooling-action="refresh"><img src="${BeastAssets.icon('tooling')}" alt="">Refresh Forge</button>
        </div>
      </header>

      <section class="tooling-summary-grid">
        <article class="beast-card compact tooling-summary-card"><img src="${BeastAssets.icon('source')}" alt=""><div><h3>Syntax</h3><strong data-tooling-syntax>CHECKING</strong><span data-tooling-syntax-detail>active file</span></div></article>
        <article class="beast-card compact tooling-summary-card"><img src="${BeastAssets.icon('policies')}" alt=""><div><h3>Lint Contract</h3><strong data-tooling-lint>UNKNOWN</strong><span data-tooling-lint-detail>workspace scripts</span></div></article>
        <article class="beast-card compact tooling-summary-card"><img src="${BeastAssets.icon('network')}" alt=""><div><h3>MCP Broker</h3><strong data-tooling-mcp>CHECKING</strong><span data-tooling-mcp-detail>0 servers</span></div></article>
        <article class="beast-card compact tooling-summary-card"><img src="${BeastAssets.icon('plugins')}" alt=""><div><h3>Plugins</h3><strong data-tooling-plugins>0</strong><span data-tooling-plugins-detail>registry entries</span></div></article>
        <article class="beast-card compact tooling-summary-card"><img src="${BeastAssets.icon('tools')}" alt=""><div><h3>Capabilities</h3><strong data-tooling-actions>0</strong><span>registered capability records</span></div></article>
      </section>

      <div class="tooling-main-grid">
        <section class="beast-card wide tooling-modules-panel is-active">
          <header class="beast-panel-head"><div><h3>Forge Modules</h3><span>Operational tooling surfaces</span></div><span class="beast-pill" data-tooling-status>CHECKING</span></header>
          <div class="tooling-module-grid">
            <button data-tooling-module="syntax"><img src="${BeastAssets.icon('source')}" alt=""><span><b>Code Scan</b><small>Syntax, parser and active-file validation</small></span><em data-module-syntax>CHECK</em></button>
            <button data-tooling-module="lint"><img src="${BeastAssets.icon('policies')}" alt=""><span><b>Lint Contract</b><small>Workspace scripts and desktop smoke checks</small></span><em data-module-lint>CHECK</em></button>
            <button data-tooling-module="mcp"><img src="${BeastAssets.icon('network')}" alt=""><span><b>MCP Operations</b><small>Servers, approvals, schema pins and executions</small></span><em data-module-mcp>CHECK</em></button>
            <button data-tooling-module="plugins"><img src="${BeastAssets.icon('plugins')}" alt=""><span><b>Plugin Registry</b><small>Manifest validation and tool surfaces</small></span><em data-module-plugins>CHECK</em></button>
            <button data-tooling-module="environment"><img src="${BeastAssets.icon('system')}" alt=""><span><b>Environment</b><small>Python, Node, npm, Git and local runtimes</small></span><em data-module-env>CHECK</em></button>
            <button data-tooling-module="catalog"><img src="${BeastAssets.icon('tools')}" alt=""><span><b>Capability Catalog</b><small>Installed tools, extensions and governed actions</small></span><em data-module-catalog>CHECK</em></button>
          </div>
          <div class="tooling-feed" data-tooling-feed></div>
        </section>

        <section class="beast-card tooling-inspector-panel">
          <header class="beast-panel-head"><div><h3>Module Inspector</h3><span data-tooling-selected-label>Overview</span></div><button class="beast-button secondary" data-tooling-action="copy"><img src="${BeastAssets.icon('files')}" alt="">Copy Report</button></header>
          <div class="tooling-inspector" data-tooling-inspector></div>
        </section>
      </div>

      <div class="tooling-lower-grid">
        <section class="beast-card tooling-mcp-panel">
          <header class="beast-panel-head"><div><h3>MCP Control Plane</h3><span>Broker state and operator approvals</span></div><span class="beast-pill live" data-mcp-health>READY</span></header>
          <div class="tooling-mcp-stats" data-mcp-stats></div>
          <div class="tooling-approval-list" data-mcp-approvals></div>
        </section>
        <section class="beast-card tooling-plugin-panel">
          <header class="beast-panel-head"><div><h3>Plugin Registry</h3><span>Installed and validated manifests</span></div><button class="beast-button secondary" data-tooling-action="manifest"><img src="${BeastAssets.icon('plugins')}" alt="">Validate</button></header>
          <div class="tooling-plugin-list" data-plugin-list></div>
        </section>
        <section class="beast-card tooling-env-panel">
          <header class="beast-panel-head"><div><h3>Runtime Environment</h3><span>Local developer toolchain</span></div><button class="beast-button secondary" data-nav="doctor"><img src="${BeastAssets.icon('doctor')}" alt="">Doctor</button></header>
          <div class="tooling-env-list" data-environment-list></div>
        </section>
      </div>

      <section class="beast-card wide tooling-capability-panel">
        <header class="beast-panel-head"><div><h3>Live Capability Inventory</h3><span>Every registered provider, tool, CLI, MCP surface, workflow, parser, database, plugin, and skill.</span></div><span class="beast-pill live" data-tooling-capability-count>0 RECORDS</span></header>
        <div class="tooling-capability-list" data-tooling-capability-list></div>
      </section>

      <details class="beast-card tooling-raw-panel"><summary><img src="${BeastAssets.icon('context')}" alt="">Raw Tooling Snapshot</summary><pre data-tooling-raw></pre></details>`;
    return root;
  }

  function renderer({signal}) {
    const root=template();
    let disposed=false;
    let renderKey='';

    function moduleData(tooling,module) {
      if (module==='syntax') return tooling.syntax;
      if (module==='lint') return tooling.linting;
      if (module==='mcp') return {state:tooling.mcp,servers:tooling.servers,approvals:tooling.approvals,schemaPins:tooling.schemaPins,audit:tooling.audit,executions:tooling.executions};
      if (module==='plugins') return tooling.plugins;
      if (module==='environment') return tooling.environments;
      if (module==='catalog') return {catalog:tooling.catalog,desktop_actions:tooling.actions,registered_capabilities:tooling.capabilities,benchmark:tooling.benchmark};
      return tooling;
    }

    function patch(state) {
      if (disposed) return;
      const tooling=state.tooling;
      const capabilities=Array.isArray(tooling.capabilities)?tooling.capabilities:[];
      const key=JSON.stringify(tooling);
      if (key===renderKey) return; renderKey=key;
      const syntaxStatus=tooling.syntax?.status || (tooling.loading?'scanning':'unknown');
      const lintReady=Boolean(tooling.linting?.has_root_lint || tooling.linting?.has_desktop_smoke);
      const mcpStatus=tooling.mcp?.status || tooling.mcp?.health || (tooling.loading?'checking':'unknown');
      root.querySelector('[data-tooling-syntax]').textContent=String(syntaxStatus).toUpperCase();
      root.querySelector('[data-tooling-syntax-detail]').textContent=tooling.syntax?.path || tooling.syntax?.detail || 'active file';
      root.querySelector('[data-tooling-lint]').textContent=lintReady?'READY':'MISSING';
      root.querySelector('[data-tooling-lint-detail]').textContent=tooling.linting?.recommendation || 'workspace scripts';
      root.querySelector('[data-tooling-mcp]').textContent=String(mcpStatus).toUpperCase();
      root.querySelector('[data-tooling-mcp-detail]').textContent=`${tooling.servers.length || tooling.mcp?.registered_servers || 0} servers · ${tooling.approvals.length || tooling.mcp?.pending_approvals || 0} approvals`;
      root.querySelector('[data-tooling-plugins]').textContent=String(tooling.plugins?.count || tooling.plugins?.items?.length || 0);
      root.querySelector('[data-tooling-plugins-detail]').textContent=tooling.plugins?.status || 'registry entries';
      root.querySelector('[data-tooling-actions]').textContent=String(capabilities.length || tooling.catalog?.summary?.tools || 0);
      const status=root.querySelector('[data-tooling-status]');
      status.textContent=tooling.loading?'SCANNING':tooling.error?'DEGRADED':String(tooling.status || 'ready').toUpperCase();
      status.className=`beast-pill ${tooling.error?'bad':tooling.loading?'warn':'live'}`;
      root.querySelector('[data-module-syntax]').textContent=String(syntaxStatus).toUpperCase();
      root.querySelector('[data-module-lint]').textContent=lintReady?'READY':'MISSING';
      root.querySelector('[data-module-mcp]').textContent=`${tooling.servers.length || 0} ONLINE`;
      root.querySelector('[data-module-plugins]').textContent=`${tooling.plugins?.count || tooling.plugins?.items?.length || 0} ACTIVE`;
      root.querySelector('[data-module-env]').textContent=`${tooling.environments.filter(item=>item.ok!==false).length}/${tooling.environments.length || 0}`;
      root.querySelector('[data-module-catalog]').textContent=`${capabilities.length || tooling.catalog?.summary?.tools || 0} RECORDS`;
      root.querySelectorAll('[data-tooling-module]').forEach(button=>button.classList.toggle('selected',button.dataset.toolingModule===tooling.selectedModule));
      root.querySelector('[data-tooling-selected-label]').textContent=tooling.selectedModule[0].toUpperCase()+tooling.selectedModule.slice(1);
      const selected=moduleData(tooling,tooling.selectedModule);
      root.querySelector('[data-tooling-inspector]').innerHTML=`<div class="tooling-inspector-hero"><img src="${BeastAssets.icon(tooling.selectedModule==='mcp'?'network':tooling.selectedModule==='plugins'?'plugins':tooling.selectedModule==='environment'?'system':'tools')}" alt=""><div><strong>${esc(tooling.selectedModule.toUpperCase())}</strong><span>${esc(tooling.source || 'unresolved source')}</span></div></div><pre>${esc(JSON.stringify(selected,null,2))}</pre>`;
      root.querySelector('[data-tooling-feed]').innerHTML=(tooling.audit.length ? tooling.audit : [{time:'NOW',label:tooling.error || `Tooling snapshot refreshed from ${tooling.source || 'runtime'}`}]).slice(0,6).map(item=>`<div><time>${esc(item.time || item.at || 'NOW')}</time><span>${esc(item.label || item.action || item.event || JSON.stringify(item))}</span></div>`).join('');
      const mcpExecuted=tooling.mcp?.executions?.executed || tooling.executions.length || 0;
      const mcpBlocked=tooling.mcp?.executions?.blocked || 0;
      root.querySelector('[data-mcp-stats]').innerHTML=`<div><strong>${tooling.servers.length || tooling.mcp?.registered_servers || 0}</strong><span>Servers</span></div><div><strong>${tooling.schemaPins.length || 0}</strong><span>Schema Pins</span></div><div><strong>${tooling.approvals.length || tooling.mcp?.pending_approvals || 0}</strong><span>Approvals</span></div><div><strong>${mcpExecuted}</strong><span>Executed</span></div><div><strong>${mcpBlocked}</strong><span>Blocked</span></div>`;
      root.querySelector('[data-mcp-approvals]').innerHTML=tooling.approvals.length ? tooling.approvals.slice(0,6).map(item=>`<article><img src="${BeastAssets.icon('policies')}" alt=""><span><b>${esc(item.request_id || item.id || 'approval')}</b><small>${esc(item.tool || item.server || 'MCP tool')} · ${esc(item.status || 'pending')}</small></span><div><button data-mcp-decision="approve" data-mcp-id="${esc(item.request_id || item.id || '')}">Approve</button><button data-mcp-decision="deny" data-mcp-id="${esc(item.request_id || item.id || '')}">Deny</button></div></article>`).join('') : '<div class="cortex-empty-list">No MCP approvals waiting.</div>';
      const plugins=tooling.plugins?.items || [];
      root.querySelector('[data-plugin-list]').innerHTML=plugins.length ? plugins.slice(0,8).map(item=>`<article><img src="${BeastAssets.icon('plugins')}" alt=""><span><b>${esc(item.name || item.id || 'plugin')}</b><small>${esc(item.risk_class || item.status || 'installed')} · ${count(item.tools)} tools</small></span><em>${/high|critical/i.test(item.risk_class || '')?'GOVERNED':'READY'}</em></article>`).join('') : '<div class="cortex-empty-list">No plugin manifests reported.</div>';
      root.querySelector('[data-environment-list]').innerHTML=tooling.environments.length ? tooling.environments.map(item=>`<article class="${item.ok===false?'warn':''}"><img src="${BeastAssets.icon(item.command==='git'?'source':item.command==='python'?'context':'system')}" alt=""><span><b>${esc(item.command || 'runtime')}</b><small>${esc(item.version || item.error || 'unavailable')}</small></span><em>${item.ok===false?'MISSING':'READY'}</em></article>`).join('') : '<div class="cortex-empty-list">Environment scan not loaded.</div>';
      root.querySelector('[data-tooling-capability-count]').textContent=`${capabilities.length} RECORDS · ${tooling.actions.length} IDE ACTIONS`;
      root.querySelector('[data-tooling-capability-list]').innerHTML=capabilities.length ? capabilities.slice(0,36).map(item=>`<article><img src="${BeastAssets.icon(item.kind==='provider'?'providers':item.kind==='mcp_tool'?'network':item.kind==='skill'?'agents':'tools')}" alt=""><span><b>${esc(item.name || item.capability_id || 'capability')}</b><small>${esc(item.kind || 'capability')} · ${esc(item.family || 'general')} · ${esc(item.status || 'available')}</small></span><em>${item.requires_approval?'APPROVAL':item.read_only===false?'GOVERNED':'READ'}</em></article>`).join('') : '<div class="cortex-empty-list">Capability inventory has not loaded. Refresh Tooling Forge.</div>';
      root.querySelector('[data-tooling-raw]').textContent=JSON.stringify(tooling.raw || {},null,2);
    }

    const unsubscribe=BeastStore.subscribe(patch);
    root.addEventListener('click',async event=>{
      const module=event.target.closest('[data-tooling-module]');
      if (module) { BeastStore.patch('tooling',{selectedModule:module.dataset.toolingModule}); BeastFX.trigger('ring',module,{size:150}); return; }
      const approval=event.target.closest('[data-mcp-decision]');
      if (approval) {
        try { await BeastTerminalToolingDoctorBridge.resolveMcpApproval(approval.dataset.mcpId,approval.dataset.mcpDecision); BeastFX.trigger('success',approval,{size:170}); }
        catch(error){ BeastStore.patch('tooling',{error:String(error.message||error)}); BeastFX.trigger('warning',approval,{size:180}); }
        return;
      }
      const action=event.target.closest('[data-tooling-action]')?.dataset.toolingAction;
      if (!action) return;
      try {
        if (action==='refresh') await BeastTerminalToolingDoctorBridge.refreshTooling({signal});
        if (action==='manifest') await BeastTerminalToolingDoctorBridge.validatePluginManifest();
        if (action==='benchmark') await BeastTerminalToolingDoctorBridge.runBenchmark();
        if (action==='copy') { await navigator.clipboard?.writeText(JSON.stringify(BeastStore.get().tooling,null,2)); BeastStore.addLedger('Tooling report copied'); }
        BeastFX.trigger('success',event.target,{size:190});
      } catch(error){ BeastStore.patch('tooling',{loading:false,error:String(error.message||error)}); BeastFX.trigger('warning',event.target,{size:210}); }
    });
    if (!BeastStore.get().tooling.updatedAt) queueMicrotask(()=>BeastTerminalToolingDoctorBridge.refreshTooling({signal}).catch(()=>{}));
    return {node:root,dispose(){disposed=true;unsubscribe();}};
  }

  window.BeastToolingPage={renderer};
})();
