(() => {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[char]);
  const safe = value => Math.max(0, Math.min(100, Number(value) || 0));
  const nodePositions = [
    {x:50,y:7},{x:79,y:22},{x:89,y:53},{x:72,y:80},{x:40,y:87},{x:12,y:67},{x:11,y:31},{x:32,y:15}
  ];

  function template() {
    const root = document.createElement('div');
    root.className = 'beast-page beast-agents-page';
    root.innerHTML = `
      <header class="beast-page-head">
        <div><h2>Agent Constellation</h2><div class="sub">MISSION ORCHESTRATION // HANDOFF BUS // TOOL BOUNDARIES // PERSISTENT SESSION STATE</div></div>
        <div class="beast-page-actions"><button class="beast-button secondary" data-agent-action="refresh"><img src="${BeastAssets.icon('network')}" alt="">Refresh</button><button class="beast-button hot" data-agent-action="create"><img src="${BeastAssets.icon('agents')}" alt="">Assign Agent</button></div>
      </header>
      <section class="agent-summary-grid">
        <article class="beast-card agent-summary-card"><img src="${BeastAssets.icon('agents')}" alt=""><div><h3>Active Sessions</h3><strong data-agent-count>0</strong><span data-agent-running>0 running</span></div></article>
        <article class="beast-card agent-summary-card"><img src="${BeastAssets.icon('network')}" alt=""><div><h3>Coordination Bus</h3><strong data-orchestrator-status>Online</strong><span data-orchestrator-health>100% health</span></div></article>
        <article class="beast-card agent-summary-card"><img src="${BeastAssets.icon('tools')}" alt=""><div><h3>Tool Inventory</h3><strong data-agent-tool-count>0</strong><span>mission-scoped capabilities</span></div></article>
        <article class="beast-card agent-summary-card"><img src="${BeastAssets.icon('trust')}" alt=""><div><h3>Trust Boundary</h3><strong>Local First</strong><span>signed mission access</span></div></article>
      </section>

      <div class="agents-main-grid">
        <section class="beast-card wide agent-constellation-panel">
          <header class="beast-panel-head"><div><h3>Mission Swarm</h3><span>Live role and handoff topology</span></div><span class="beast-pill live" data-agent-state>CONSTELLATION READY</span></header>
          <div class="agent-orbit" data-agent-orbit>
            <div class="agent-orbit-grid"></div>
            <div class="agent-core-node"><img src="${BeastAssets.icon('orchestrator')}" alt=""><b>Mission Orchestrator</b><span data-core-copy>Coordination bus online</span><i></i></div>
            <canvas class="premium-orbit-canvas" data-premium-canvas="orbit" aria-hidden="true"></canvas>
            <div data-agent-nodes></div>
          </div>
        </section>

        <section class="beast-card agent-detail-panel" data-agent-detail></section>
      </div>

      <div class="agents-lower-grid">
        <section class="beast-card agent-session-list-panel">
          <header class="beast-panel-head"><div><h3>Session Stack</h3><span data-session-count>0 sessions</span></div><button class="beast-button secondary" data-agent-action="refresh"><img src="${BeastAssets.icon('network')}" alt="">Sync</button></header>
          <div class="agent-session-list" data-agent-list></div>
        </section>
        <section class="beast-card agent-handoff-panel">
          <header class="beast-panel-head"><div><h3>Handoff Stream</h3><span>Newest first</span></div><span class="beast-pill live">LIVE</span></header>
          <div class="agent-handoff-list" data-handoff-list></div>
        </section>
        <section class="beast-card agent-capability-panel">
          <header class="beast-panel-head"><div><h3>Capability Matrix</h3><span>Governed tools</span></div></header>
          <div class="agent-tool-cloud" data-agent-tools></div>
          <h3 class="agent-boundary-title">Trust Boundary</h3>
          <div class="agent-permission-grid" data-agent-permissions></div>
        </section>
      </div>`;
    return root;
  }

  function renderer({ signal }) {
    const root = template();
    let disposed = false;
    let nodesKey = '';
    let listKey = '';
    let lowerKey = '';
    const disposeCanvas = BeastVisualCanvas.auto(root);

    function renderNodes(state) {
      const key = JSON.stringify([state.agents.sessions, state.agents.selectedId]);
      if (key === nodesKey) return; nodesKey = key;
      root.querySelector('[data-agent-nodes]').innerHTML = state.agents.sessions.slice(0,8).map((agent,index) => {
        const pos = nodePositions[index];
        const active = /active|working|running/i.test(agent.status);
        return `<button class="agent-orbit-node ${active ? 'active' : ''} ${agent.id === state.agents.selectedId ? 'selected' : ''}" style="--x:${pos.x}%;--y:${pos.y}%;--delay:${index * -.35}s" data-agent-id="${esc(agent.id)}"><img src="${BeastAssets.icon(index % 3 === 0 ? 'agent' : index % 3 === 1 ? 'context' : 'tools')}" alt=""><b>${esc(agent.label)}</b><span>${esc(agent.status)}</span><i>${safe(agent.confidence)}%</i></button>`;
      }).join('') || '<div class="agent-empty-orbit">No live sessions. Assign an agent to populate the constellation.</div>';
    }

    function renderList(state) {
      const key = JSON.stringify([state.agents.sessions, state.agents.selectedId]);
      if (key === listKey) return; listKey = key;
      root.querySelector('[data-agent-list]').innerHTML = state.agents.sessions.map(agent => `<button class="agent-session-row ${agent.id === state.agents.selectedId ? 'selected' : ''}" data-agent-id="${esc(agent.id)}"><img src="${BeastAssets.icon('agents')}" alt=""><span><b>${esc(agent.label)}</b><small>${esc(agent.role)} · ${esc(agent.model)}</small></span><em>${esc(agent.status)}</em><i>${safe(agent.confidence)}%</i></button>`).join('') || '<div class="cortex-empty-list">No persistent agent sessions reported.</div>';
    }

    function renderLower(state) {
      const key = JSON.stringify([state.agents.handoffs,state.agents.tools,state.agents.permissions]);
      if (key === lowerKey) return; lowerKey = key;
      root.querySelector('[data-handoff-list]').innerHTML = state.agents.handoffs.map(item => `<div class="agent-handoff-row ${esc(item.tone)}"><time>${esc(item.time)}</time><span>${esc(item.label)}</span><i></i></div>`).join('') || '<div class="cortex-empty-list">No handoffs recorded.</div>';
      root.querySelector('[data-agent-tools]').innerHTML = state.agents.tools.map(tool => `<span><img src="${BeastAssets.icon('tools')}" alt="">${esc(tool)}</span>`).join('');
      root.querySelector('[data-agent-permissions]').innerHTML = state.agents.permissions.map(permission => `<span><b>✓</b>${esc(permission)}</span>`).join('');
    }

    function patch(state) {
      if (disposed) return;
      const agents = state.agents;
      const selected = agents.sessions.find(agent => agent.id === agents.selectedId) || agents.sessions[0];
      const running = agents.sessions.filter(agent => /active|working|running/i.test(agent.status)).length;
      root.querySelector('[data-agent-count]').textContent = agents.sessions.length;
      root.querySelector('[data-agent-running]').textContent = `${running} running`;
      root.querySelector('[data-orchestrator-status]').textContent = agents.orchestrator.status;
      root.querySelector('[data-orchestrator-health]').textContent = `${safe(agents.orchestrator.health)}% health`;
      root.querySelector('[data-agent-tool-count]').textContent = agents.tools.length;
      root.querySelector('[data-agent-state]').textContent = agents.loading ? 'SCANNING SESSIONS' : agents.error ? 'CONSTELLATION DEGRADED' : 'CONSTELLATION READY';
      root.querySelector('[data-agent-state]').classList.toggle('bad', Boolean(agents.error));
      root.querySelector('[data-core-copy]').textContent = `${agents.sessions.length} sessions · ${running} active`;
      root.querySelector('[data-session-count]').textContent = `${agents.sessions.length} sessions`;
      root.querySelector('[data-agent-detail]').innerHTML = selected ? `<header class="beast-panel-head"><div><h3>Selected Agent</h3><span>${esc(selected.role)}</span></div><span class="beast-pill ${/active|working|running/i.test(selected.status) ? 'live' : ''}">${esc(selected.status)}</span></header><div class="agent-detail-hero"><img src="${BeastAssets.icon('agents')}" alt=""><div><strong>${esc(selected.label)}</strong><span>${esc(selected.provider)} · ${esc(selected.model)}</span></div></div><p class="agent-task-copy">${esc(selected.task)}</p><div class="beast-rail-facts"><div><span>Confidence</span><b>${safe(selected.confidence)}%</b></div><div><span>Context files</span><b>${esc(selected.files)}</b></div><div><span>Budget</span><b>${esc(selected.budget)}</b></div><div><span>Updated</span><b>${esc(selected.updatedAt || 'live')}</b></div></div><div class="agent-detail-tools">${selected.tools.map(tool => `<span>${esc(tool)}</span>`).join('')}</div><div class="agent-control-row"><button class="beast-button secondary" data-agent-action="pause"><img src="${BeastAssets.icon('policies')}" alt="">Pause</button><button class="beast-button" data-agent-action="resume"><img src="${BeastAssets.icon('agents')}" alt="">Resume</button><button class="beast-button danger-button" data-agent-action="cancel"><img src="${BeastAssets.icon('alerts')}" alt="">Cancel</button></div>` : `<h3>Selected Agent</h3><p>No session selected. Assign an agent to begin.</p><button class="beast-button hot" data-agent-action="create"><img src="${BeastAssets.icon('agents')}" alt="">Assign Agent</button>`;
      renderNodes(state); renderList(state); renderLower(state);
    }

    const unsubscribe = BeastStore.subscribe(patch);
    root.addEventListener('click', async event => {
      const agent = event.target.closest('[data-agent-id]');
      if (agent) { BeastModelAgentBridge.selectAgent(agent.dataset.agentId); BeastFX.trigger('ring',agent,{size:150}); return; }
      const action = event.target.closest('[data-agent-action]')?.dataset.agentAction;
      if (!action) return;
      try {
        if (action === 'refresh') { await BeastModelAgentBridge.refreshAgents({signal}); BeastFX.trigger('burst',event.target,{size:210}); }
        if (action === 'create') { const objective = window.prompt('Agent objective', BeastStore.get().editor.activePath ? `Work on ${BeastStore.get().editor.activePath}` : 'BEAST mission support'); if (!objective) return; await BeastModelAgentBridge.createAgent(objective,{signal}); BeastFX.trigger('success',event.target,{size:280}); BeastMascot.setState('working'); setTimeout(()=>BeastMascot.setState('idle'),1200); }
        if (['pause','resume','cancel'].includes(action)) { await BeastModelAgentBridge.controlAgent(BeastStore.get().agents.selectedId,action,{signal}); BeastFX.trigger(action === 'cancel' ? 'warning' : 'success',event.target,{size:220}); }
      } catch (error) { BeastStore.patch('agents',{loading:false,error:String(error.message || error)}); BeastFX.trigger('warning',event.target,{size:240}); }
    });
    if (!BeastStore.get().agents.lastRefreshAt) queueMicrotask(() => BeastModelAgentBridge.refreshAgents({signal}).catch(() => {}));
    return { node:root, dispose(){ disposed = true; unsubscribe(); disposeCanvas(); } };
  }

  window.BeastAgentsPage = { renderer };
})();
