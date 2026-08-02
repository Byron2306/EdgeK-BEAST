(() => {
  const pages = ['studio','workspace','compatibility','source','mission','models','compute-fabric','live-fabric','compute-control','agents','review','grand-closure','trust','memory','evidence','crystallization','commons','map','terminal','testing','tooling','doctor','reality','providers','system','atlas','worktrees','deploy','chronicle','economy','settings'];
  let railKey = '';
  let gatewayRecoveryAttempts = 0;
  let gatewayRecoveryTimer = 0;
  let liveRefreshTimer = 0;
  let liveRefreshBusy = false;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[char]);

  function placeholder({ page }) {
    const label = page[0].toUpperCase() + page.slice(1);
    const node = document.createElement('div');
    node.className = 'beast-page';
    node.innerHTML = `<header class="beast-page-head"><div><h2>${esc(label)}</h2><div class="sub">SURFACE UNAVAILABLE</div></div></header><section class="beast-card wide"><h3>${esc(label)} is not registered</h3><strong class="metric">Unavailable</strong><p>This route has no renderer in the current build. Choose a registered surface from the navigation.</p></section>`;
    return node;
  }

  function updateHeader(page) {
    const state = BeastStore.get();
    const label = page === 'source' ? 'SourcePlan' : page[0].toUpperCase() + page.slice(1);
    document.getElementById('beastPageName').textContent = label;
    const missionTitle = document.getElementById('beastMissionTitle');
    missionTitle.textContent = state.mission.title;
    missionTitle.title = state.mission.title;
    document.getElementById('beastMissionMeta').textContent = `${state.mission.id} · ${state.workspace.root || 'no workspace'} · ${state.editor.openTabs.length} tabs · ${state.connection.status}`;
    const compact = document.getElementById('beastCompactRoute');
    if (compact) compact.value = page;
    const pill = document.getElementById('beastConnectionPill');
    pill.textContent = state.connection.status === 'online' ? '● SYSTEM ONLINE' : '○ GATEWAY OFFLINE';
    pill.classList.toggle('live', state.connection.status === 'online');
    pill.classList.toggle('bad', state.connection.status === 'offline');
    const activeWork = ['studio','workspace','source','models','agents','evidence','trust','memory','map','terminal','tooling','doctor','reality','providers','system','worktrees','deploy','chronicle','economy','settings'];
    const mascotState = page === 'review' ? 'alert' : activeWork.includes(page) ? 'working' : page === 'crystallization' ? 'finished' : 'idle';
    BeastMascot.setState(mascotState);
  }

  function operationNotice(message, tone='ok') {
    const node = document.getElementById('beastOperationNotice');
    if (!node) return;
    node.textContent = String(message || 'Ready');
    node.dataset.tone = tone;
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
  function compatibilityFacts(state) {
    const c=state.compatibility||{};
    return facts('IDE Compatibility', [
      ['Coverage',`${c.summary?.coverage||0}%`],['Language servers',(c.languages||[]).filter(x=>x.available).length],
      ['Debug adapters',(c.debug||[]).filter(x=>x.available).length],['Protocol sessions',(c.sessions||[]).length],
      ['Extension host',c.extensionHost?.status||'checking'],['Remote transports',(c.remote||[]).filter(x=>x.available).length]
    ], '<button class="beast-button rail-action hot" data-nav="compatibility">Open Compatibility Center</button>');
  }

  function doctorFacts(state) {
    const doctor = state.doctor || {};
    const healthy = (doctor.checks || []).filter(check => check.ok || ['healthy','online'].includes(String(check.status || '').toLowerCase())).length;
    return facts('Doctor Diagnostics', [
      ['Score',`${doctor.score || 0}%`],['Status',doctor.status || 'checking'],['Checks',`${healthy}/${(doctor.checks || []).length}`],
      ['Routes',(doctor.routes || []).length],['Recommendations',(doctor.recommendations || []).length],['Last scan',doctor.lastScanAt ? new Date(doctor.lastScanAt).toLocaleTimeString() : 'never']
    ], '<button class="beast-button rail-action hot" data-nav="doctor">Open Doctor Diagnostics</button>');
  }

  function providerFacts(state) {
    const p=state.providers||{}; const selected=(p.registry||[]).find(row=>row.id===p.selectedId)||{};
    return facts('Provider Plane', [['Active',p.activeId||'none'],['Selected',selected.label||'none'],['Policy',p.policy||'Local First'],['Routes',(p.registry||[]).length],['Compression',p.compression?'armed':'off'],['Cache',p.kvCache?'ready':'off']], '<button class="beast-button rail-action hot" data-nav="providers">Open Provider Plane</button>');
  }
  function systemFacts(state) {
    const s=state.system||{};
    const platform=state.platform||{};
    return facts('System Plane', [['Score',`${s.score||0}%`],['Status',s.status||'checking'],['CPU',`${Math.round(s.cpu||0)}%`],['Memory',`${Math.round(s.memory||0)}%`],['Ports',(s.ports||[]).length],['PREC',s.prec?.stage||'discover'],['Atlas',(platform.sections||[]).length]], '<button class="beast-button rail-action hot" data-nav="system">Open System Plane</button>');
  }
  function worktreeFacts(state) {
    const w=state.worktrees||{}; const selected=(w.items||[]).find(row=>row.id===w.selectedId)||{};
    return facts('Worktree Missions', [['Missions',(w.items||[]).length],['Selected',selected.label||'none'],['Branch',selected.branch||'n/a'],['Progress',`${selected.progress||0}%`],['Tests',selected.tests||'pending'],['Changes',selected.changes||0]], '<button class="beast-button rail-action hot" data-nav="worktrees">Open Worktrees</button>');
  }
  function deployFacts(state) {
    const d=state.deploy||{};
    return facts('Release Forge', [['Score',`${d.score||0}%`],['Status',d.status||'not checked'],['Stages',(d.stages||[]).length],['Blockers',(d.blockers||[]).length],['Ports',(d.ports||[]).length],['Runbook',d.lastRunbook?'ready':'none']], '<button class="beast-button rail-action hot" data-nav="deploy">Open Release Forge</button>');
  }
  function chronicleFacts(state) {
    const c=state.chronicle||{};
    return facts('Chronicle', [['Events',(c.events||[]).length],['Visible',(c.filtered||[]).length],['Filter',c.filter||'all'],['Insights',(c.insights||[]).length],['Selected',c.selectedId||'none'],['Updated',c.updatedAt?new Date(c.updatedAt).toLocaleTimeString():'never']], '<button class="beast-button rail-action hot" data-nav="chronicle">Open Chronicle</button>');
  }
  function economyFacts(state) {
    const e=state.economy||{};
    return facts('Compute Economy', [['Tokens',Number(e.tokensSaved||0).toLocaleString()],['Reuse',`${Math.round(e.reuseRate||0)}%`],['Compression',`${Math.round(e.compression||0)}%`],['Cache hit',`${Math.round(e.cacheHit||0)}%`],['Calls displaced',e.callsDisplaced||0],['Cost avoided',e.costAvoided||'R0']], '<button class="beast-button rail-action hot" data-nav="economy">Open Compute Economy</button>');
  }
  function studioFacts(state) {
    const s=state.studio||{};
    return facts('BEAST Studio', [['Health',`${s.health||0}%`],['Phase',`${s.phase||8}/${s.total||12}`],['Completed',s.completed||0],['Systems',(s.systems||[]).length],['Online',(s.systems||[]).filter(x=>x.ready).length],['Mission',state.mission.status]], '<button class="beast-button rail-action hot" data-nav="studio">Open Studio Overview</button>');
  }
  function settingsFacts(state) {
    const s=state.settings||{};
    return facts('IDE Controls', [['Type',`${Math.round((s.typeScale||1)*100)}%`],['Density',s.density||'comfortable'],['Motion',s.motion||'balanced'],['Atmosphere',s.atmosphere||'matrix-grid'],['Audio',s.audio?'armed':'muted'],['Governance',s.sourcePlanRequired?'strict':'custom']], '<button class="beast-button rail-action hot" data-nav="settings">Open IDE Controls</button>');
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
      state.route === 'compatibility' ? compatibilityFacts(state) :
      state.route === 'doctor' ? doctorFacts(state) :
      state.route === 'providers' ? providerFacts(state) :
      state.route === 'system' ? systemFacts(state) :
      state.route === 'worktrees' ? worktreeFacts(state) :
      state.route === 'deploy' ? deployFacts(state) :
      state.route === 'chronicle' ? chronicleFacts(state) :
      state.route === 'economy' ? economyFacts(state) :
      state.route === 'settings' ? settingsFacts(state) :
      state.route === 'studio' ? studioFacts(state) :
      state.route === 'workspace' ? editorFacts(state) :
      state.route === 'mission' ? mapFacts(state) : editorFacts(state);
  }

  function secondaryFacts(state) {
    return state.route === 'models' ? providerFacts(state) :
      state.route === 'providers' ? modelFacts(state) :
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
      state.route === 'tooling' ? systemFacts(state) :
      state.route === 'compatibility' ? toolingFacts(state) :
      state.route === 'doctor' ? systemFacts(state) :
      state.route === 'system' ? doctorFacts(state) :
      state.route === 'worktrees' ? deployFacts(state) :
      state.route === 'deploy' ? worktreeFacts(state) :
      state.route === 'chronicle' ? economyFacts(state) :
      state.route === 'economy' ? providerFacts(state) :
      state.route === 'settings' ? studioFacts(state) :
      state.route === 'studio' ? economyFacts(state) : crystalFacts(state);
  }

  function runtimeFacts(state) {
    const runtime=state.runtime||{}; const caps=runtime.desktopCapabilities||{}; const available=Object.values(caps).filter(Boolean).length;
    return facts('Runtime Contract', [['Mode',runtime.mode||'offline'],['Gateway',runtime.gatewayUrl||'unresolved'],['IPC methods',`${available}/${Object.keys(caps).length||0}`],['In flight',runtime.inFlight||0],['Errors',(runtime.errors||[]).length],['Visibility',runtime.visible===false?'paused':'active']], '<button class="beast-button rail-action" data-runtime-probe>Probe Runtime</button>');
  }

  function renderRail(state) {
    // Rail content only depends on these compact facts. Serializing full map,
    // evidence, and memory arrays here made every live refresh an O(n) stall.
    const compact = value => value == null ? '' : String(value);
    const key = [
      state.route, state.connection.status, state.mission.health, state.mission.status,
      state.workspace.root, state.workspace.files.length, state.editor.activePath,
      state.sourcePlan.status, state.sourcePlan.plan?.plan_id, state.sourcePlan.selectedOperationIds.length,
      state.models.active, state.models.registry.length, state.agents.sessions.length,
      state.review.updatedAt, state.evidence.updatedAt, state.trust.updatedAt, state.memory.updatedAt,
      state.map.updatedAt, state.crystal.updatedAt, state.terminal.status, state.tooling.updatedAt,
      state.doctor.updatedAt, state.providers.updatedAt, state.system.updatedAt, state.platform.updatedAt,
      state.worktrees.updatedAt, state.deploy.updatedAt, state.chronicle.updatedAt, state.economy.updatedAt,
      state.studio.updatedAt, state.runtime.inFlight, state.diagnostics.viewport,
      state.diagnostics.duplicateIds, state.diagnostics.outletChildren, state.diagnostics.activeEditors,
      state.diagnostics.activeDiffEditors, state.diagnostics.horizontalOverflow,
      state.ledger[0]?.time, state.ledger[0]?.label
    ].map(compact).join('|');
    if (key === railKey) return;
    railKey = key;
    const rail = document.getElementById('beastContextRail');
    rail.innerHTML = `<div class="beast-rail-context-head"><span>CONTEXT</span><b>${esc(String(state.route||'studio').toUpperCase())}</b></div><div class="beast-rail-stack">
      <section class="beast-card beast-rail-card"><h3>Core Health</h3><div class="beast-ring" style="--value:${Math.max(0,Math.min(100,state.mission.health))}"><span>${state.mission.health}%</span></div><p class="centered">${esc(state.mission.status)}</p></section>
      ${contextFacts(state)}
      ${secondaryFacts(state)}
      ${runtimeFacts(state)}
      <section class="beast-card beast-rail-card"><h3>Layout Guard</h3><div class="beast-rail-facts"><div><span>Viewport</span><b>${esc(state.diagnostics.viewport || 'checking')}</b></div><div><span>Duplicate IDs</span><b>${state.diagnostics.duplicateIds}</b></div><div><span>Outlet children</span><b>${state.diagnostics.outletChildren}</b></div><div><span>Code editors</span><b>${state.diagnostics.activeEditors}</b></div><div><span>Diff editors</span><b>${state.diagnostics.activeDiffEditors}</b></div><div><span>Overflow</span><b>${state.diagnostics.horizontalOverflow ? 'detected':'clear'}</b></div></div></section>
      <section class="beast-card beast-rail-card"><h3>Event Ledger</h3><div class="beast-ledger">${state.ledger.slice(0,8).map(event => `<div><time>${esc(event.time)}</time><span>${esc(event.label)}</span></div>`).join('')}</div></section>
    </div>`;
  }

  async function runCommand(command) {
    const normalized = command.trim().toLowerCase();
    try {
      if (['/workspace','/editor'].includes(normalized)) return await BeastRouter.navigate('workspace');
      if (['/mission','/mission cockpit'].includes(normalized)) return await BeastRouter.navigate('mission');
      if (['/workspace registry','/workspaces'].includes(normalized)) return await BeastRouter.navigate('worktrees');
      if (['/compatibility','/lsp','/dap'].includes(normalized)) { await BeastIDECompatibility.refresh(); return await BeastRouter.navigate('compatibility'); }
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
      if (['/providers','/providers open'].includes(normalized)) return await BeastRouter.navigate('providers');
      if (['/platform','/platform open'].includes(normalized)) return await BeastRouter.navigate('atlas');
      if (['/system','/system open'].includes(normalized)) return await BeastRouter.navigate('system');
      if (['/atlas','/atlas open','/systems'].includes(normalized)) return await BeastRouter.navigate('atlas');
      if (['/swarm','/swarm open'].includes(normalized)) return await BeastRouter.navigate('agents');
      if (['/sensorium','/sensorium open'].includes(normalized)) return await BeastRouter.navigate('chronicle');
      if (['/memory atlas','/memory atlas open'].includes(normalized)) return await BeastRouter.navigate('memory');
      if (['/worktrees','/worktrees open'].includes(normalized)) return await BeastRouter.navigate('worktrees');
      if (['/deploy','/release','/deploy open'].includes(normalized)) return await BeastRouter.navigate('deploy');
      if (['/chronicle','/chronicle open'].includes(normalized)) return await BeastRouter.navigate('chronicle');
      if (['/economy','/compute economy'].includes(normalized)) return await BeastRouter.navigate('economy');
      if (['/compute control','/control plane','/interception'].includes(normalized)) { await BeastUtilityOrchestrationBridge.refreshControl(); return await BeastRouter.navigate('compute-control'); }
      if (['/settings','/settings open'].includes(normalized)) return await BeastRouter.navigate('settings');
      if (normalized === '/remote dev') { await BeastRouter.navigate('compatibility'); document.dispatchEvent(new CustomEvent('beast:remote-dev-focus')); return; }
      if (normalized === '/extensions discover') { await BeastRouter.navigate('compatibility'); await BeastIDERuntime.discoverExtensions(); return; }
      if (['/session levers','/levers'].includes(normalized)) return await BeastRouter.navigate('settings');
      if (['/studio','/overview'].includes(normalized)) return await BeastRouter.navigate('studio');
      if (['/approvals','/approval queue'].includes(normalized)) { await BeastReviewEvidenceBridge.refreshReview(); return await BeastRouter.navigate('review'); }
      if (['/intelligence','/agent awareness'].includes(normalized)) { await BeastRouter.navigate('workspace'); BeastAICoding.setOpen(true); BeastAICoding.addActiveFile(); return; }
      if (['/context','/context picker','/handoff','/prepare handoff'].includes(normalized)) { await BeastRouter.navigate('workspace'); BeastAICoding.setOpen(true); BeastAICoding.addActiveFile(); return; }
      if (normalized === '/models refresh') { await BeastModelAgentBridge.refreshModels(); return await BeastRouter.navigate('models'); }
      if (normalized === '/agents refresh') { await BeastModelAgentBridge.refreshAgents(); return await BeastRouter.navigate('agents'); }
      if (normalized === '/review refresh') { await BeastReviewEvidenceBridge.refreshReview(); return await BeastRouter.navigate('review'); }
      if (normalized === '/review risks') { await BeastReviewEvidenceBridge.refreshReview(); return await BeastRouter.navigate('review'); }
      if (normalized === '/evidence refresh') { await BeastReviewEvidenceBridge.refreshEvidence(); return await BeastRouter.navigate('evidence'); }
      if (normalized === '/trust refresh') { await BeastTrustMemoryBridge.refreshTrust(); return await BeastRouter.navigate('trust'); }
      if (normalized === '/integrity verify') { await BeastTrustMemoryBridge.verifyIntegrity(); return await BeastRouter.navigate('trust'); }
      if (normalized === '/trust access') { await BeastTrustMemoryBridge.refreshTrust(); return await BeastRouter.navigate('trust'); }
      if (normalized === '/policy matrix' || normalized === '/policy show') { await BeastTrustMemoryBridge.refreshTrust(); return await BeastRouter.navigate('trust'); }
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
      if (normalized === '/providers refresh') { await BeastUtilityOrchestrationBridge.refreshProviders(); return await BeastRouter.navigate('providers'); }
      if (normalized === '/providers import-secrets' || normalized === '/providers secrets import') {
        const sourcePath = window.prompt('Local secrets file to import (for example: /home/me/.config/beast/providers.env)', '');
        if (!sourcePath?.trim()) return;
        const result = await BeastRuntime.request('/edgek/providers/secrets/import', {
          method:'POST', timeoutMs:30000,
          body:{ source_path:sourcePath.trim(), overwrite:false, merge:true, load:true }
        });
        BeastStore.addLedger(`Provider secrets imported from ${sourcePath.trim()} · ${Number(result?.imported || result?.loaded || 0)} value(s) loaded`);
        await BeastUtilityOrchestrationBridge.refreshProviders();
        return await BeastRouter.navigate('providers');
      }
      if (normalized === '/platform refresh' || normalized === '/atlas refresh') { await BeastUtilityOrchestrationBridge.refreshPlatform(); return await BeastRouter.navigate('atlas'); }
      if (normalized === '/system refresh') { await BeastUtilityOrchestrationBridge.refreshSystem(); return await BeastRouter.navigate('system'); }
      if (normalized === '/system sweep') { await BeastUtilityOrchestrationBridge.systemAction('sweep'); return await BeastRouter.navigate('system'); }
      if (normalized === '/worktrees refresh') { await BeastUtilityOrchestrationBridge.refreshWorktrees(); return await BeastRouter.navigate('worktrees'); }
      if (normalized === '/deploy check') { await BeastUtilityOrchestrationBridge.refreshDeploy(); return await BeastRouter.navigate('deploy'); }
      if (normalized === '/chronicle refresh') { await BeastUtilityOrchestrationBridge.refreshChronicle(); return await BeastRouter.navigate('chronicle'); }
      if (normalized === '/economy refresh') { await BeastUtilityOrchestrationBridge.refreshEconomy(); return await BeastRouter.navigate('economy'); }
      if (normalized === '/studio refresh') { await BeastUtilityOrchestrationBridge.refreshStudio(); return await BeastRouter.navigate('studio'); }
      if (normalized === '/terminal clear') { BeastTerminalToolingDoctorBridge.clearOutput(); return await BeastRouter.navigate('terminal'); }
      if (normalized.startsWith('/terminal ')) { BeastTerminalToolingDoctorBridge.setCommand(command.trim().slice(10)); return await BeastRouter.navigate('terminal'); }
      if (normalized === '/chat open' || normalized === '/chat') { BeastTerminalToolingDoctorBridge.syncModelSelection(); return await BeastRouter.navigate('terminal'); }
      if (normalized === '/chat clear') { BeastTerminalToolingDoctorBridge.clearChat(); return await BeastRouter.navigate('terminal'); }
      if (normalized.startsWith('/chat ')) { BeastTerminalToolingDoctorBridge.setChatPrompt(command.trim().slice(6)); return await BeastRouter.navigate('terminal'); }
      if (normalized.startsWith('/memory recall ')) { await BeastTrustMemoryBridge.recall(command.trim().slice(15)); return await BeastRouter.navigate('memory'); }
      if (normalized === '/audit pack') { BeastReviewEvidenceBridge.buildAuditPack(); return await BeastRouter.navigate('evidence'); }
      if (normalized === '/agent create') { const objective = window.prompt('Agent objective','BEAST mission support'); if (objective) await BeastModelAgentBridge.createAgent(objective); return await BeastRouter.navigate('agents'); }
      if (normalized === '/editor split') { BeastEditorCortex.toggleSplit(); return; }
      if (normalized === '/sourceplan draft') { await BeastEditorCortex.draftSourcePlan(); return await BeastRouter.navigate('source'); }
      if (normalized === '/sourceplan upgrade') { await BeastEditorCortex.draftSourcePlan(); return await BeastRouter.navigate('source'); }
      if (normalized === '/sourceplan preview') return await BeastRouter.navigate('source');
      if (normalized === '/sourceplan lifecycle') { await BeastEditorCortex.refreshLifecycle(); return await BeastRouter.navigate('source'); }
      if (normalized === '/sourceplan verify') { await BeastEditorCortex.verifyPlan(); return await BeastRouter.navigate('source'); }
      if (normalized === '/sourceplan apply') { await BeastEditorCortex.applyPlan(); return await BeastRouter.navigate('source'); }
      if (normalized === '/sourceplan rollback') { await BeastEditorCortex.rollbackLatestPlan(); return await BeastRouter.navigate('source'); }
      if (normalized === '/refresh files') { await BeastDesktopBridge.listFiles(); return; }
      if (normalized === '/refresh') { await Promise.allSettled([BeastDesktopBridge.status(),BeastModelAgentBridge.refreshModels(),BeastIDECompatibility.refresh(),BeastTerminalToolingDoctorBridge.refreshTooling()]); return; }
      if (normalized === '/layout reset') { window.BeastShellLayout?.reset?.(); window.BeastWorkbenchPanels?.reset?.(); BeastStore.addLedger('Workbench layout reset'); return; }
      if (normalized === '/runtime probe') { await BeastRuntime.probe(); await BeastDesktopBridge.status(); BeastRuntimeWatchdog.inspect(); return; }
      if (normalized === '/runtime reset' || normalized === '/runtime restart all') {
        if (!BeastRuntime.hasDesktop('resetRuntimeStack')) throw new Error('Runtime stack reset is available only inside the BEAST Electron shell.');
        if (!window.confirm('Reset the BEAST runtime stack? This interrupts active model streams, terminals, gateway requests, Guardian consumers, Commons, LiteLLM, MCP, Ollama, and proxy traffic.')) return;
        BeastStore.addLedger('Runtime stack reset started: Guardian, Commons, daemon, gateway, proxy, LiteLLM, MCP, Ollama, Nginx.');
        const result = await BeastRuntime.desktopCall('resetRuntimeStack', [], { required:true });
        const summary = (result?.components || []).map(item => `${item.component}: ${item.ok ? 'ok' : item.status}`).join(' · ');
        BeastStore.addLedger(`Runtime stack reset ${result?.ok ? 'completed' : 'needs attention'}${summary ? ` · ${summary}` : ''}`);
        await BeastDesktopBridge.status();
        await Promise.allSettled([BeastTerminalToolingDoctorBridge.refreshDoctor(), BeastIDECompatibility.refresh(), BeastUtilityOrchestrationBridge.refreshProviders()]);
        return await BeastRouter.navigate('doctor');
      }
      if (normalized === '/runtime report') { console.table(BeastRuntime.diagnostics()); BeastStore.addLedger('Runtime report emitted to console'); return; }
      BeastStore.addLedger(`Command queued: ${command}`);
      document.dispatchEvent(new CustomEvent('beast:command',{detail:{command}}));
    } catch (error) {
      BeastStore.addLedger(`Command failed: ${String(error.message || error)}`);
      BeastFX.trigger('warning',document.getElementById('beastCommandSend'),{size:220});
    }
  }
  window.BeastCommand = { run: runCommand };

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
    document.querySelectorAll('[data-command-tab]').forEach(tab => tab.addEventListener('click', async () => {
      const mode=tab.dataset.commandTab;
      document.querySelectorAll('[data-command-tab]').forEach(item=>item.classList.toggle('active',item===tab));
      if (mode==='command') { input.placeholder='Ask or command BEAST IDE…'; input.focus(); return; }
      if (mode==='ask') { await BeastRouter.navigate('terminal'); document.querySelector('[data-terminal-chat-prompt]')?.focus(); return; }
      if (mode==='runbook') { await BeastRouter.navigate('deploy'); return; }
      if (mode==='notes') { await BeastRouter.navigate('chronicle'); }
    }));
  }

  function refreshReleaseSurfaces() {
    return Promise.allSettled([
      BeastTerminalToolingDoctorBridge.refreshTooling(),
      BeastTerminalToolingDoctorBridge.refreshDoctor(),
      BeastUtilityOrchestrationBridge.refreshAll()
    ]);
  }

  async function refreshProductionState(reason='manual') {
    return BeastRuntime.runExclusive('refresh:production', async () => {
      if (!BeastRuntime.visible && reason !== 'workspace') return [];
      const coreTasks=[
        BeastDesktopBridge.status({ lightweight:true }),BeastDesktopBridge.snapshot(),BeastDesktopBridge.listFiles(),
      ];
      // A full simultaneous sweep creates a local request convoy (especially
      // against the single-worker direct gateway).  Pages own their detailed
      // refreshes; boot only establishes connection/workspace identity.
      if (reason === 'boot' || reason === 'gateway-retry') {
        const result=await Promise.allSettled(coreTasks);
        // These are the terminal's route prerequisites. Hydrate them after the
        // bounded identity probe, not only after an operator manually visits
        // their individual pages.
        await Promise.allSettled([
          BeastModelAgentBridge.refreshModels(),
          BeastUtilityOrchestrationBridge.refreshProviders(),
          BeastMapCrystalBridge.refreshMap()
        ]);
        // Keep boot cheap. Route pages own their detailed refresh; hydrating
        // every page here created a request convoy and repainted hidden DOM.
        await Promise.allSettled([
          BeastModelAgentBridge.refreshAgents(),
          BeastUtilityOrchestrationBridge.refreshPlatform(),
          BeastUtilityOrchestrationBridge.refreshControl()
        ]);
        // A managed direct gateway can take a few seconds to come up after the
        // Guardian listener has been rejected as incompatible.  Retry only the
        // bounded boot probe; never claim connectivity until status confirms it.
        if (BeastStore.get().connection.status === 'online') {
          gatewayRecoveryAttempts = 0;
          if (gatewayRecoveryTimer) { clearTimeout(gatewayRecoveryTimer); gatewayRecoveryTimer = 0; }
        } else if (gatewayRecoveryAttempts < 4 && !gatewayRecoveryTimer) {
          const delays = [2500, 4000, 6000, 8000];
          const delay = delays[gatewayRecoveryAttempts++];
          gatewayRecoveryTimer = setTimeout(() => {
            gatewayRecoveryTimer = 0;
            refreshProductionState('gateway-retry').catch(error => operationNotice(`Gateway recovery probe failed · ${String(error.message || error)}`, 'error'));
          }, delay);
        }
        BeastStore.addLedger(`Production refresh complete · ${reason}`);
        return result;
      }
      const tasks=[
        ...coreTasks,
        BeastModelAgentBridge.refreshModels(),BeastModelAgentBridge.refreshAgents(),
        BeastReviewEvidenceBridge.refreshReview(),BeastReviewEvidenceBridge.refreshEvidence(),
        BeastTrustMemoryBridge.refreshTrust(),BeastTrustMemoryBridge.refreshMemory(),
        BeastMapCrystalBridge.refreshMap(),BeastMapCrystalBridge.refreshCrystal(),
        BeastTerminalToolingDoctorBridge.refreshTooling(),BeastTerminalToolingDoctorBridge.refreshDoctor(),
        BeastUtilityOrchestrationBridge.refreshAll()
      ];
      const result=await Promise.allSettled(tasks);BeastStore.addLedger(`Production refresh complete · ${reason}`);return result;
    });
  }

  // Keep open pages honest after boot.  This is deliberately slower than the
  // render loop and serialized through the runtime so live telemetry cannot
  // create a request convoy or replace a page while it is being painted.
  async function refreshLiveState() {
    if (document.hidden || liveRefreshBusy || !BeastRuntime.visible) return;
    liveRefreshBusy = true;
    try {
      await BeastRuntime.runExclusive('refresh:live', async () => {
        await Promise.allSettled([
          BeastDesktopBridge.status({ lightweight:true }),
          BeastDesktopBridge.snapshot()
        ]);
        const route=BeastRouter.active;
        const routeRefresh={
          agents:()=>BeastModelAgentBridge.refreshAgents(),
          review:()=>BeastReviewEvidenceBridge.refreshReview(),
          evidence:()=>BeastReviewEvidenceBridge.refreshEvidence(),
          trust:()=>BeastTrustMemoryBridge.refreshTrust(),
          memory:()=>BeastTrustMemoryBridge.refreshMemory(),
          map:()=>BeastMapCrystalBridge.refreshMap(),
          crystallization:()=>BeastMapCrystalBridge.refreshCrystal(),
          providers:()=>BeastUtilityOrchestrationBridge.refreshProviders(),
          deploy:()=>BeastUtilityOrchestrationBridge.refreshDeploy(),
          chronicle:()=>BeastUtilityOrchestrationBridge.refreshChronicle(),
          economy:()=>BeastUtilityOrchestrationBridge.refreshEconomy(),
          system:()=>BeastUtilityOrchestrationBridge.refreshSystem(),
          atlas:()=>BeastUtilityOrchestrationBridge.refreshPlatform()
        }[route];
        if(routeRefresh) await Promise.allSettled([routeRefresh()]);
      });
    } finally { liveRefreshBusy=false; }
  }

  function startLiveRefresh() {
    clearInterval(liveRefreshTimer);
    liveRefreshTimer=setInterval(()=>{ refreshLiveState().catch(error=>BeastStore.addLedger(`Live refresh failed · ${String(error.message||error)}`)); },15000);
  }

  function bindGlobalEvents() {
    document.querySelectorAll('[data-beast-route]').forEach(button => button.addEventListener('click',() => BeastRouter.navigate(button.dataset.beastRoute)));
    document.getElementById('beastCompactRoute')?.addEventListener('change',event => BeastRouter.navigate(event.target.value));
    document.addEventListener('click',event => {
      const nav = event.target.closest('[data-nav]');
      if (nav) BeastRouter.navigate(nav.dataset.nav);
      const probe = event.target.closest('[data-runtime-probe]');
      if (probe) { BeastRuntime.probe().then(()=>BeastDesktopBridge.status({ lightweight:false })).then(()=>BeastRuntimeWatchdog.inspect()).catch(error=>BeastStore.addLedger(`Runtime probe failed: ${String(error.message||error)}`)); }
      const chip = event.target.closest('[data-command-chip]');
      if (chip) { const input=document.getElementById('beastCommandInput'); if(input){input.value=chip.dataset.commandChip||'';input.focus();} }
      const button = event.target.closest('button');
      if (button && !button.closest('[data-file-path]') && !button.closest('[data-editor-tab]') && !button.closest('[data-model-id]') && !button.closest('[data-agent-id]') && !button.closest('[data-map-node]') && !button.closest('[data-crystal-candidate]')) BeastFX.trigger('burst',button,{size:110});
    });
    document.addEventListener('beast:route-start',event => {
      BeastStore.set('route',event.detail.page);
      localStorage.setItem('beast.v2.route',event.detail.page);
      updateHeader(event.detail.page);
    });
    document.addEventListener('beast:operation', event => {
      operationNotice(event.detail?.message || 'Operation updated', event.detail?.tone || 'ok');
    });
    window.addEventListener('unhandledrejection', event => {
      const message = String(event.reason?.message || event.reason || 'Unknown operation failure');
      operationNotice(`Action failed · ${message}`, 'error');
    });
    BeastDesktopBridge.on('workspace',async () => {
      BeastEditorCortex.destroyAll();
      await refreshProductionState('workspace');
      await BeastEditorCortex.restoreTabs();
      if (BeastRouter.active !== 'workspace') BeastRouter.navigate('workspace');
    });
    BeastDesktopBridge.on('refresh',async () => { await refreshProductionState('desktop'); });
    document.addEventListener('beast:sourceplan-request',async () => {
      try { await BeastEditorCortex.draftSourcePlan(); await BeastRouter.navigate('source'); }
      catch (error) { BeastStore.patch('sourcePlan',{status:'error',message:String(error.message || error),error:String(error.message || error)}); }
    });
    window.addEventListener('beforeunload',() => {
      BeastEditorCortex.persist();
      BeastTerminalToolingDoctorBridge.destroy();
      window.BeastVisualRuntime?.destroy?.();
      BeastRuntimeWatchdog.destroy();
      BeastRuntime.destroy();
      window.BeastAccessibility?.destroy?.();
    });
  }

  async function boot() {
    pages.forEach(page => BeastRouter.register(page,
      page === 'workspace' ? BeastWorkspacePage.renderer :
      page === 'compatibility' ? BeastCompatibilityPage.renderer :
      page === 'source' ? BeastSourcePlanPage.renderer :
      page === 'mission' ? BeastMissionPage.renderer :
      page === 'models' ? BeastModelsPage.renderer :
      page === 'compute-fabric' ? BeastComputeFabricPage.renderer :
      page === 'live-fabric' ? BeastLiveFabricPage.renderer :
      page === 'compute-control' ? BeastComputeControlPage.renderer :
      page === 'agents' ? BeastAgentsPage.renderer :
      page === 'review' ? BeastReviewPage.renderer :
      page === 'grand-closure' ? BeastGrandClosurePage.renderer :
      page === 'evidence' ? BeastEvidencePage.renderer :
      page === 'trust' ? BeastTrustPage.renderer :
      page === 'memory' ? BeastMemoryPage.renderer :
      page === 'map' ? BeastMapPage.renderer :
      page === 'crystallization' ? BeastCrystallizationPage.renderer :
      page === 'commons' ? BeastCommonsPage.renderer :
      page === 'terminal' ? BeastTerminalPage.renderer :
      page === 'testing' ? BeastTestingPage.renderer :
      page === 'tooling' ? BeastToolingPage.renderer :
      page === 'doctor' ? BeastDoctorPage.renderer :
      page === 'reality' ? BeastRealityPage.renderer :
      page === 'providers' ? BeastProvidersPage.renderer :
      page === 'system' ? BeastSystemPage.renderer :
      page === 'atlas' ? BeastAtlasPage.renderer :
      page === 'settings' ? BeastSettingsPage.renderer :
      page === 'worktrees' ? BeastWorktreesPage.renderer :
      page === 'deploy' ? BeastDeployPage.renderer :
      page === 'chronicle' ? BeastChroniclePage.renderer :
      page === 'economy' ? BeastEconomyPage.renderer :
      page === 'studio' ? BeastStudioPage.renderer : placeholder
    ));
    await BeastRuntime.init();
    BeastPageSession.init();
    BeastRuntimeWatchdog.init();
    BeastMascot.init();
    BeastFX.matrix();
    window.BeastVisualRuntime?.init?.();
    window.BeastAccessibility?.init?.();
    BeastLayoutGuard.init();
    BeastDesktopBridge.bindDesktopEvents();
    BeastTerminalToolingDoctorBridge.loadTerminalState();
    bindCommandDock();
    bindGlobalEvents();
    let visualRoute = '';
    BeastStore.subscribe(state => {
      updateHeader(state.route);
      renderRail(state);
      if (state.route !== visualRoute) {
        visualRoute = state.route;
        window.BeastVisualRuntime?.update?.(document.getElementById('beastPageOutlet') || document);
      }
    });
    const captureMode = new URLSearchParams(location.search).get('capture') === '1';
    const requested = new URLSearchParams(location.search).get('page') || location.hash.replace(/^#/,'') || localStorage.getItem('beast.v2.route') || 'studio';
    if (captureMode) {
      BeastStore.patch('connection',{status:'offline',message:'Capture preview · seeded local state'});
      await refreshReleaseSurfaces();
    }
    await BeastRouter.navigate(pages.includes(requested) ? requested : 'studio');
    BeastStore.set('booted',true);
    window.BeastOnboarding?.init?.();
    BeastStore.addLedger('Desktop shell booted; awaiting live subsystem contracts');
    if (!captureMode) {
      startLiveRefresh();
      queueMicrotask(async () => {
        try {
          await refreshProductionState('boot');
          if (BeastStore.get().workspace.root) {
            await BeastDesktopBridge.listFiles();
            await BeastEditorCortex.restoreTabs();
          }
        } catch (error) { BeastStore.addLedger(`Background refresh failed: ${String(error.message || error)}`); }
      });
    }
  }

  window.addEventListener('beforeunload',()=>clearInterval(liveRefreshTimer));
  window.addEventListener('DOMContentLoaded',() => boot().catch(error => {
    console.error('[BEAST RELEASE]',error);
    document.body.dataset.bootError='true';
  }));
})();
