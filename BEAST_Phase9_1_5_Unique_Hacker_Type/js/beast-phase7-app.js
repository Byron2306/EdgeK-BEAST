(() => {
  const pages = ['workspace','source','mission','models','agents','review','trust','memory','evidence','crystallization','map','terminal','tooling','doctor','settings'];
  let railKey = '';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[char]);

  function placeholder({ page }) {
    const label = page[0].toUpperCase() + page.slice(1);
    const node = document.createElement('div');
    node.className = 'beast-page';
    node.innerHTML = `<header class="beast-page-head"><div><h2>${esc(label)}</h2><div class="sub">QUEUED FOR CONTROLLED PAGE TRANSPLANT</div></div></header><section class="beast-card wide"><h3>${esc(label)} migration slot</h3><strong class="metric">Queued</strong><p>Terminal Nexus, Tooling Forge and Doctor Diagnostics now run on the clean shell. This remaining utility surface stays isolated until its dedicated migration.</p></section>`;
    return node;
  }

  function updateHeader(page) {
    const state = BeastStore.get();
    const label = page === 'source' ? 'SourcePlan' : page[0].toUpperCase() + page.slice(1);
    document.getElementById('beastPageName').textContent = label;
    document.getElementById('beastMissionTitle').textContent = state.mission.title;
    document.getElementById('beastMissionMeta').textContent = `${state.mission.id} · ${state.workspace.root || 'no workspace'} · ${state.editor.openTabs.length} tabs · ${state.connection.status}`;
    const compact = document.getElementById('beastCompactRoute');
    if (compact) compact.value = page;
    const pill = document.getElementById('beastConnectionPill');
    pill.textContent = state.connection.status === 'online' ? '● SYSTEM ONLINE' : '○ GATEWAY OFFLINE';
    pill.classList.toggle('live', state.connection.status === 'online');
    pill.classList.toggle('bad', state.connection.status === 'offline');
    const activeWork = ['workspace','source','models','agents','evidence','trust','memory','map','terminal','tooling','doctor'];
    const mascotState = page === 'review' ? 'alert' : activeWork.includes(page) ? 'working' : page === 'crystallization' ? 'finished' : 'idle';
    BeastMascot.setState(mascotState);
  }

  function facts(title, rows, action='') {
    return `<section class="beast-card beast-rail-card"><h3>${esc(title)}</h3><div class="beast-rail-facts">${rows.map(([label,value]) => `<div><span>${esc(label)}</span><b>${esc(value)}</b></div>`).join('')}</div>${action}</section>`;
  }

  function editorFacts(state) {
    return facts('Editor Cortex', [
      ['Owner',state.editor.owner],['Open tabs',state.editor.openTabs.length],['Dirty buffers',state.editor.dirtyPaths.length],
      ['Models',state.editor.modelCount],['Split view',state.editor.split ? 'armed' : 'single'],['Cursor',`${state.editor.cursor.line}:${state.editor.cursor.column}`]
    ], '<button class="beast-button rail-action" data-nav="workspace">Open Editor Cortex</button>');
  }

  function planFacts(state) {
    const plan = state.sourcePlan.plan || {};
    const lifecycle = state.sourcePlan.lifecycle || {};
    return facts('SourcePlan Contract', [
      ['Plan',plan.plan_id || 'none'],['Status',state.sourcePlan.status],['Selected ops',state.sourcePlan.selectedOperationIds.length],
      ['Can verify',lifecycle.can_verify ? 'yes':'no'],['Can apply',lifecycle.can_apply ? 'yes':'no'],['Rollback',lifecycle.action_contract?.rollback_required === false ? 'optional':'required']
    ], `<button class="beast-button rail-action ${lifecycle.can_apply ? 'hot':''}" data-nav="source">Open SourcePlan Forge</button>`);
  }

  function modelFacts(state) {
    const selected = state.models.registry.find(model => model.id === state.models.selectedId) || state.models.registry[0] || {};
    return facts('Model Route', [
      ['Active',state.models.active || 'none'],['Selected',selected.id || 'none'],['Provider',state.models.provider || 'n/a'],
      ['Policy',state.models.policy],['Latency',state.models.latency],['Throughput',state.models.throughput]
    ], '<button class="beast-button rail-action hot" data-nav="models">Open Model Router</button>');
  }

  function agentFacts(state) {
    const selected = state.agents.sessions.find(agent => agent.id === state.agents.selectedId) || state.agents.sessions[0] || {};
    return facts('Agent Session', [
      ['Sessions',state.agents.sessions.length],['Selected',selected.label || 'none'],['Status',selected.status || 'idle'],
      ['Role',selected.role || 'n/a'],['Model',selected.model || 'n/a'],['Tools',selected.tools?.length || 0]
    ], '<button class="beast-button rail-action hot" data-nav="agents">Open Constellation</button>');
  }

  function reviewFacts(state) {
    const gates = state.review?.gates || [];
    const passed = gates.filter(gate => gate.status === 'Passed').length;
    const unresolved = (state.review?.contradictions || []).filter(item => !/resolved/i.test(item.status)).length;
    return facts('Review Center', [
      ['Confidence',`${state.review?.confidence || 0}%`],['Gates',`${passed}/${gates.length}`],['Recommendation',state.review?.recommendation || 'pending'],
      ['Contradictions',unresolved],['Risks',(state.review?.risks || []).length],['Tests',`${state.review?.tests?.passed || 0}/${state.review?.tests?.total || 0}`]
    ], '<button class="beast-button rail-action hot" data-nav="review">Open Review Center</button>');
  }

  function evidenceFacts(state) {
    const pack = state.evidence?.pack || {};
    return facts('Evidence Forge', [
      ['Artifacts',(state.evidence?.files || []).length],['Selected',(state.evidence?.selectedIds || []).length],['Validity',`${state.evidence?.validity || 0}%`],
      ['Pack',pack.ready ? 'ready':'building'],['Validated',pack.validationPassed || 0],['Traces',(state.evidence?.traceLinks || []).length]
    ], '<button class="beast-button rail-action hot" data-nav="evidence">Open Evidence Forge</button>');
  }

  function trustFacts(state) {
    const trust = state.trust || {};
    return facts('Trust Posture', [
      ['Score',`${trust.score || 0}%`],['Status',trust.status || 'checking'],['Policy',trust.policy || 'Local First'],
      ['Healthy',`${trust.systemsHealthy || 0}/${trust.systemsTotal || 0}`],['Warnings',trust.warnings || 0],['Failures',trust.failedChecks || 0]
    ], '<button class="beast-button rail-action hot" data-nav="trust">Open Trust Posture</button>');
  }

  function mapFacts(state) {
    const map = state.map || {};
    const selected = map.nodes?.find(node => node.id === map.selectedId) || map.nodes?.[0] || {};
    return facts('Mission Map', [
      ['Health',`${map.health || 0}%`],['Nodes',map.nodes?.length || 0],['Links',map.edges?.length || 0],
      ['Coverage',`${map.coverage || 0}%`],['Orphans',map.orphaned || 0],['Selected',selected.label || 'none']
    ], '<button class="beast-button rail-action hot" data-nav="map">Open Mission Map</button>');
  }

  function crystalFacts(state) {
    const crystal = state.crystal || {};
    const passed = (crystal.gates || []).filter(gate => gate.status === 'Passed').length;
    return facts('Crystallization', [
      ['Readiness',`${crystal.readiness || 0}%`],['Candidates',crystal.candidates?.length || 0],['Gates',`${passed}/${crystal.gates?.length || 0}`],
      ['Chain blocks',crystal.chain?.blocks || 0],['Checkpoints',crystal.lattice?.checkpoints || 0],['Immutable',crystal.immutable ? 'sealed':'pending']
    ], '<button class="beast-button rail-action hot" data-nav="crystallization">Open Chamber</button>');
  }

  function memoryFacts(state) {
    const memory = state.memory || {};
    return facts('Memory Observatory', [
      ['Records',Number(memory.records || 0).toLocaleString()],['Recall',`${memory.recallHealth || 0}%`],['Freshness',`${memory.freshness || 0}%`],
      ['Residue',`${memory.residueQuality || 0}%`],['Compaction',memory.compactionQueue || 0],['Skills',memory.skillCandidates || 0]
    ], '<button class="beast-button rail-action hot" data-nav="memory">Open Memory Observatory</button>');
  }

  function terminalFacts(state) {
    const terminal = state.terminal || {};
    const receipt = terminal.lastReceipt || {};
    return facts('Terminal Nexus', [
      ['Status',terminal.status || 'idle'],['Decision',terminal.decision || 'unclassified'],['Risk',terminal.risk || 'pending'],
      ['Exit',terminal.returncode ?? 'n/a'],['History',(terminal.history || []).length],['Receipt',receipt.receipt_id || receipt.id || 'none']
    ], '<button class="beast-button rail-action hot" data-nav="terminal">Open Terminal Nexus</button>');
  }

  function toolingFacts(state) {
    const tooling = state.tooling || {};
    const mcp = tooling.mcp || {};
    const plugins = tooling.plugins || {};
    return facts('Tooling Forge', [
      ['Status',tooling.status || 'checking'],['Source',tooling.source || 'unresolved'],['Actions',(tooling.actions || []).length],
      ['MCP servers',(tooling.servers || []).length || mcp.server_count || 0],['Plugins',plugins.count || plugins.items?.length || plugins.plugins?.length || plugins.length || 0],['Approvals',(tooling.approvals || []).length]
    ], '<button class="beast-button rail-action hot" data-nav="tooling">Open Tooling Forge</button>');
  }

  function doctorFacts(state) {
    const doctor = state.doctor || {};
    const healthy = (doctor.checks || []).filter(check => check.ok || ['healthy','online'].includes(String(check.status || '').toLowerCase())).length;
    return facts('Doctor Diagnostics', [
      ['Score',`${doctor.score || 0}%`],['Status',doctor.status || 'checking'],['Checks',`${healthy}/${(doctor.checks || []).length}`],
      ['Routes',(doctor.routes || []).length],['Recommendations',(doctor.recommendations || []).length],['Last scan',doctor.lastScanAt ? new Date(doctor.lastScanAt).toLocaleTimeString() : 'never']
    ], '<button class="beast-button rail-action hot" data-nav="doctor">Open Doctor Diagnostics</button>');
  }

  function contextFacts(state) {
    return state.route === 'source' ? planFacts(state) :
      state.route === 'models' ? modelFacts(state) :
      state.route === 'agents' ? agentFacts(state) :
      state.route === 'review' ? reviewFacts(state) :
      state.route === 'evidence' ? evidenceFacts(state) :
      state.route === 'trust' ? trustFacts(state) :
      state.route === 'memory' ? memoryFacts(state) :
      state.route === 'map' ? mapFacts(state) :
      state.route === 'crystallization' ? crystalFacts(state) :
      state.route === 'terminal' ? terminalFacts(state) :
      state.route === 'tooling' ? toolingFacts(state) :
      state.route === 'doctor' ? doctorFacts(state) :
      state.route === 'workspace' ? editorFacts(state) :
      state.route === 'mission' ? mapFacts(state) : editorFacts(state);
  }

  function secondaryFacts(state) {
    return state.route === 'models' ? agentFacts(state) :
      state.route === 'agents' ? modelFacts(state) :
      state.route === 'review' ? evidenceFacts(state) :
      state.route === 'evidence' ? reviewFacts(state) :
      state.route === 'trust' ? memoryFacts(state) :
      state.route === 'memory' ? trustFacts(state) :
      state.route === 'map' ? crystalFacts(state) :
      state.route === 'crystallization' ? mapFacts(state) :
      state.route === 'workspace' ? planFacts(state) :
      state.route === 'source' ? editorFacts(state) :
      state.route === 'terminal' ? doctorFacts(state) :
      state.route === 'tooling' ? doctorFacts(state) :
      state.route === 'doctor' ? toolingFacts(state) : crystalFacts(state);
  }

  function renderRail(state) {
    const key = JSON.stringify({
      route:state.route, connection:state.connection.status, health:state.mission.health,
      workspace:{root:state.workspace.root,files:state.workspace.files.length}, editor:state.editor,
      sourcePlan:{status:state.sourcePlan.status,id:state.sourcePlan.plan?.plan_id,selected:state.sourcePlan.selectedOperationIds,lifecycle:state.sourcePlan.lifecycle},
      models:state.models, agents:state.agents, review:state.review, evidence:state.evidence, trust:state.trust,
      memory:state.memory, map:state.map, crystal:state.crystal, terminal:state.terminal, tooling:state.tooling,
      doctor:state.doctor, ledger:state.ledger, diagnostics:state.diagnostics
    });
    if (key === railKey) return;
    railKey = key;
    const rail = document.getElementById('beastContextRail');
    rail.innerHTML = `<div class="beast-rail-stack">
      <section class="beast-card beast-rail-card"><h3>Core Health</h3><div class="beast-ring" style="--value:${Math.max(0,Math.min(100,state.mission.health))}"><span>${state.mission.health}%</span></div><p class="centered">${esc(state.mission.status)}</p></section>
      ${contextFacts(state)}
      ${secondaryFacts(state)}
      <section class="beast-card beast-rail-card"><h3>Layout Guard</h3><div class="beast-rail-facts"><div><span>Viewport</span><b>${esc(state.diagnostics.viewport || 'checking')}</b></div><div><span>Duplicate IDs</span><b>${state.diagnostics.duplicateIds}</b></div><div><span>Outlet children</span><b>${state.diagnostics.outletChildren}</b></div><div><span>Code editors</span><b>${state.diagnostics.activeEditors}</b></div><div><span>Diff editors</span><b>${state.diagnostics.activeDiffEditors}</b></div><div><span>Overflow</span><b>${state.diagnostics.horizontalOverflow ? 'detected':'clear'}</b></div></div></section>
      <section class="beast-card beast-rail-card"><h3>Event Ledger</h3><div class="beast-ledger">${state.ledger.slice(0,8).map(event => `<div><time>${esc(event.time)}</time><span>${esc(event.label)}</span></div>`).join('')}</div></section>
    </div>`;
  }

  async function runCommand(command) {
    const normalized = command.trim().toLowerCase();
    try {
      if (['/workspace','/editor'].includes(normalized)) return await BeastRouter.navigate('workspace');
      if (['/sourceplan','/sourceplan open'].includes(normalized)) return await BeastRouter.navigate('source');
      if (['/models','/models open'].includes(normalized)) return await BeastRouter.navigate('models');
      if (['/agents','/agents open'].includes(normalized)) return await BeastRouter.navigate('agents');
      if (['/review','/review open'].includes(normalized)) return await BeastRouter.navigate('review');
      if (['/evidence','/evidence open'].includes(normalized)) return await BeastRouter.navigate('evidence');
      if (['/trust','/trust open'].includes(normalized)) return await BeastRouter.navigate('trust');
      if (['/memory','/memory open'].includes(normalized)) return await BeastRouter.navigate('memory');
      if (['/map','/map open'].includes(normalized)) return await BeastRouter.navigate('map');
      if (['/crystal','/crystallization','/crystal open'].includes(normalized)) return await BeastRouter.navigate('crystallization');
      if (['/terminal','/terminal open'].includes(normalized)) return await BeastRouter.navigate('terminal');
      if (['/tooling','/tooling open'].includes(normalized)) return await BeastRouter.navigate('tooling');
      if (['/doctor','/doctor open'].includes(normalized)) return await BeastRouter.navigate('doctor');
      if (normalized === '/models refresh') { await BeastModelAgentBridge.refreshModels(); return await BeastRouter.navigate('models'); }
      if (normalized === '/agents refresh') { await BeastModelAgentBridge.refreshAgents(); return await BeastRouter.navigate('agents'); }
      if (normalized === '/review refresh') { await BeastReviewEvidenceBridge.refreshReview(); return await BeastRouter.navigate('review'); }
      if (normalized === '/evidence refresh') { await BeastReviewEvidenceBridge.refreshEvidence(); return await BeastRouter.navigate('evidence'); }
      if (normalized === '/trust refresh') { await BeastTrustMemoryBridge.refreshTrust(); return await BeastRouter.navigate('trust'); }
      if (normalized === '/integrity verify') { await BeastTrustMemoryBridge.verifyIntegrity(); return await BeastRouter.navigate('trust'); }
      if (normalized === '/memory refresh') { await BeastTrustMemoryBridge.refreshMemory(); return await BeastRouter.navigate('memory'); }
      if (normalized === '/memory compact') { await BeastTrustMemoryBridge.compact(); return await BeastRouter.navigate('memory'); }
      if (normalized === '/map refresh') { await BeastMapCrystalBridge.refreshMap(); return await BeastRouter.navigate('map'); }
      if (normalized === '/map fit') { BeastMapCrystalBridge.setMapZoom(1); return await BeastRouter.navigate('map'); }
      if (normalized === '/crystal refresh') { await BeastMapCrystalBridge.refreshCrystal(); return await BeastRouter.navigate('crystallization'); }
      if (normalized === '/crystal verify') { await BeastMapCrystalBridge.verifyCandidate(); return await BeastRouter.navigate('crystallization'); }
      if (normalized === '/crystal commit') { await BeastMapCrystalBridge.commitCrystal(); return await BeastRouter.navigate('crystallization'); }
      if (normalized === '/tooling refresh') { await BeastTerminalToolingDoctorBridge.refreshTooling(); return await BeastRouter.navigate('tooling'); }
      if (normalized === '/tooling benchmark') { await BeastTerminalToolingDoctorBridge.runBenchmark(); return await BeastRouter.navigate('tooling'); }
      if (normalized === '/doctor scan') { await BeastTerminalToolingDoctorBridge.refreshDoctor(); return await BeastRouter.navigate('doctor'); }
      if (normalized === '/terminal clear') { BeastTerminalToolingDoctorBridge.clearOutput(); return await BeastRouter.navigate('terminal'); }
      if (normalized.startsWith('/terminal ')) { BeastTerminalToolingDoctorBridge.setCommand(command.trim().slice(10)); return await BeastRouter.navigate('terminal'); }
      if (normalized.startsWith('/memory recall ')) { await BeastTrustMemoryBridge.recall(command.trim().slice(15)); return await BeastRouter.navigate('memory'); }
      if (normalized === '/audit pack') { BeastReviewEvidenceBridge.buildAuditPack(); return await BeastRouter.navigate('evidence'); }
      if (normalized === '/agent create') { const objective = window.prompt('Agent objective','BEAST mission support'); if (objective) await BeastModelAgentBridge.createAgent(objective); return await BeastRouter.navigate('agents'); }
      if (normalized === '/editor split') { BeastEditorCortex.toggleSplit(); return; }
      if (normalized === '/sourceplan draft') { await BeastEditorCortex.draftSourcePlan(); return await BeastRouter.navigate('source'); }
      if (normalized === '/sourceplan lifecycle') { await BeastEditorCortex.refreshLifecycle(); return await BeastRouter.navigate('source'); }
      if (normalized === '/sourceplan verify') { await BeastEditorCortex.verifyPlan(); return await BeastRouter.navigate('source'); }
      if (normalized === '/sourceplan apply') { await BeastEditorCortex.applyPlan(); return await BeastRouter.navigate('source'); }
      if (normalized === '/refresh files') { await BeastDesktopBridge.listFiles(); return; }
      BeastStore.addLedger(`Command queued: ${command}`);
      document.dispatchEvent(new CustomEvent('beast:command',{detail:{command}}));
    } catch (error) {
      BeastStore.addLedger(`Command failed: ${String(error.message || error)}`);
      BeastFX.trigger('warning',document.getElementById('beastCommandSend'),{size:220});
    }
  }

  function bindCommandDock() {
    const input = document.getElementById('beastCommandInput');
    const send = document.getElementById('beastCommandSend');
    async function execute() {
      const command = input.value.trim();
      if (!command) return;
      await runCommand(command);
      BeastFX.trigger('burst',send,{size:190});
      input.value='';
    }
    input.addEventListener('keydown',event => { if (event.key === 'Enter') execute(); });
    send.addEventListener('click',execute);
    document.querySelectorAll('[data-command-chip]').forEach(chip => chip.addEventListener('click',() => { input.value=chip.dataset.commandChip; input.focus(); }));
  }

  function refreshPhase7Surfaces() {
    return Promise.allSettled([
      BeastTerminalToolingDoctorBridge.refreshTooling(),
      BeastTerminalToolingDoctorBridge.refreshDoctor()
    ]);
  }

  function bindGlobalEvents() {
    document.querySelectorAll('[data-beast-route]').forEach(button => button.addEventListener('click',() => BeastRouter.navigate(button.dataset.beastRoute)));
    document.getElementById('beastCompactRoute')?.addEventListener('change',event => BeastRouter.navigate(event.target.value));
    document.addEventListener('click',event => {
      const nav = event.target.closest('[data-nav]');
      if (nav) BeastRouter.navigate(nav.dataset.nav);
      const button = event.target.closest('button');
      if (button && !button.closest('[data-file-path]') && !button.closest('[data-editor-tab]') && !button.closest('[data-model-id]') && !button.closest('[data-agent-id]') && !button.closest('[data-map-node]') && !button.closest('[data-crystal-candidate]')) BeastFX.trigger('burst',button,{size:110});
    });
    document.addEventListener('beast:route-start',event => {
      BeastStore.set('route',event.detail.page);
      localStorage.setItem('beast.v2.route',event.detail.page);
      updateHeader(event.detail.page);
    });
    BeastDesktopBridge.on('workspace',async () => {
      BeastEditorCortex.destroyAll();
      await BeastDesktopBridge.listFiles();
      await BeastDesktopBridge.snapshot();
      await BeastEditorCortex.restoreTabs();
      await Promise.allSettled([
        BeastModelAgentBridge.refreshModels(),BeastModelAgentBridge.refreshAgents(),
        BeastReviewEvidenceBridge.refreshReview(),BeastReviewEvidenceBridge.refreshEvidence(),
        BeastTrustMemoryBridge.refreshTrust(),BeastTrustMemoryBridge.refreshMemory(),
        BeastMapCrystalBridge.refreshMap(),BeastMapCrystalBridge.refreshCrystal(),
        BeastTerminalToolingDoctorBridge.refreshTooling(),BeastTerminalToolingDoctorBridge.refreshDoctor()
      ]);
      if (BeastRouter.active !== 'workspace') BeastRouter.navigate('workspace');
    });
    BeastDesktopBridge.on('refresh',async () => {
      await Promise.allSettled([
        BeastDesktopBridge.status(),BeastDesktopBridge.snapshot(),BeastDesktopBridge.listFiles(),
        BeastModelAgentBridge.refreshModels(),BeastModelAgentBridge.refreshAgents(),
        BeastReviewEvidenceBridge.refreshReview(),BeastReviewEvidenceBridge.refreshEvidence(),
        BeastTrustMemoryBridge.refreshTrust(),BeastTrustMemoryBridge.refreshMemory(),
        BeastMapCrystalBridge.refreshMap(),BeastMapCrystalBridge.refreshCrystal(),
        BeastTerminalToolingDoctorBridge.refreshTooling(),BeastTerminalToolingDoctorBridge.refreshDoctor()
      ]);
    });
    document.addEventListener('beast:sourceplan-request',async () => {
      try { await BeastEditorCortex.draftSourcePlan(); await BeastRouter.navigate('source'); }
      catch (error) { BeastStore.patch('sourcePlan',{status:'error',message:String(error.message || error),error:String(error.message || error)}); }
    });
    window.addEventListener('beforeunload',() => {
      BeastEditorCortex.persist();
      BeastTerminalToolingDoctorBridge.destroy();
    });
  }

  async function boot() {
    pages.forEach(page => BeastRouter.register(page,
      page === 'workspace' ? BeastWorkspacePage.renderer :
      page === 'source' ? BeastSourcePlanPage.renderer :
      page === 'mission' ? BeastMissionPage.renderer :
      page === 'models' ? BeastModelsPage.renderer :
      page === 'agents' ? BeastAgentsPage.renderer :
      page === 'review' ? BeastReviewPage.renderer :
      page === 'evidence' ? BeastEvidencePage.renderer :
      page === 'trust' ? BeastTrustPage.renderer :
      page === 'memory' ? BeastMemoryPage.renderer :
      page === 'map' ? BeastMapPage.renderer :
      page === 'crystallization' ? BeastCrystallizationPage.renderer :
      page === 'terminal' ? BeastTerminalPage.renderer :
      page === 'tooling' ? BeastToolingPage.renderer :
      page === 'doctor' ? BeastDoctorPage.renderer : placeholder
    ));
    BeastMascot.init();
    BeastFX.matrix();
    BeastFX.logoFlicker();
    BeastLayoutGuard.init();
    BeastDesktopBridge.bindDesktopEvents();
    BeastTerminalToolingDoctorBridge.loadTerminalState();
    bindCommandDock();
    bindGlobalEvents();
    BeastStore.subscribe(state => { updateHeader(state.route); renderRail(state); });
    const captureMode = new URLSearchParams(location.search).get('capture') === '1';
    if (!captureMode) {
      await BeastDesktopBridge.status();
      await Promise.allSettled([
        BeastDesktopBridge.actionsManifest(),BeastDesktopBridge.snapshot(),
        BeastModelAgentBridge.refreshModels(),BeastModelAgentBridge.refreshAgents(),
        BeastReviewEvidenceBridge.refreshReview(),BeastReviewEvidenceBridge.refreshEvidence(),
        BeastTrustMemoryBridge.refreshTrust(),BeastTrustMemoryBridge.refreshMemory(),
        BeastMapCrystalBridge.refreshMap(),BeastMapCrystalBridge.refreshCrystal(),
        BeastTerminalToolingDoctorBridge.refreshTooling(),BeastTerminalToolingDoctorBridge.refreshDoctor()
      ]);
      if (BeastStore.get().workspace.root) { await BeastDesktopBridge.listFiles(); await BeastEditorCortex.restoreTabs(); }
    } else {
      BeastStore.patch('connection',{status:'offline',message:'Capture preview · seeded local state'});
      await refreshPhase7Surfaces();
    }
    const requested = new URLSearchParams(location.search).get('page') || location.hash.replace(/^#/,'') || localStorage.getItem('beast.v2.route') || 'terminal';
    await BeastRouter.navigate(pages.includes(requested) ? requested : 'terminal');
    BeastStore.set('booted',true);
    BeastStore.addLedger('Phase 7 Terminal, Tooling and Doctor transplant boot complete');
  }

  window.addEventListener('DOMContentLoaded',() => boot().catch(error => {
    console.error('[BEAST Phase 7]',error);
    document.body.dataset.bootError='true';
  }));
})();
