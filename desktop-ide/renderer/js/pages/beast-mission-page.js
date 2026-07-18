(() => {
  const stageCopy = {
    mission: 'Define goal and success criteria',
    models: 'Select and route local models',
    agents: 'Assign agents and roles',
    workspace: 'Bind tools and capabilities',
    review: 'Plan checks and review gates',
    evidence: 'Collect and verify evidence',
    crystallization: 'Synthesize durable residue'
  };

  function card(title, className = '') {
    const node = document.createElement('section');
    node.className = `beast-card ${className}`.trim();
    const heading = document.createElement('h3'); heading.textContent = title;
    node.append(heading);
    return node;
  }

  function createTemplate() {
    const root = document.createElement('div');
    root.className = 'beast-page beast-mission-page';
    root.innerHTML = `
      <header class="beast-page-head">
        <div><h2>Mission Overview</h2><div class="sub">LIVE GATEWAY STATE // GRANULAR PATCHING // NO DOUBLE RENDER</div></div>
        <div class="beast-page-actions"><button class="beast-button" data-mission-action="refresh">Refresh Mission</button></div>
      </header>
      <div class="beast-mission-hero">
        <section class="beast-card wide beast-mission-brief">
          <div class="tiny">ACTIVE MISSION</div><strong class="metric" data-mission-title>Loading…</strong>
          <p data-mission-id></p><div class="beast-progress"><span data-mission-progress-bar></span></div>
          <footer><span data-mission-status></span><span data-mission-progress></span></footer>
        </section>
        <section class="beast-card beast-health-card">
          <h3>Structural Health</h3><div class="beast-ring" data-health-ring><span data-health-value>0%</span></div>
          <p data-health-copy></p>
        </section>
        <section class="beast-card warning beast-next-card">
          <h3>Next Best Action</h3><strong class="metric" data-mission-next-action>Awaiting mission telemetry</strong>
          <p data-mission-next-copy>Connect to the gateway to identify the next governed action.</p>
          <button class="beast-button amber" data-mission-action="focus-launch">Start a coding task</button>
        </section>
      </div>
      <section class="beast-card wide beast-mission-launch" data-mission-launch>
        <header class="beast-panel-head"><div><h3>Start a Coding Task</h3><span>Bind the workspace, check trust, plan safely, then isolate the implementation.</span></div><span class="beast-pill live">GUIDED</span></header>
        <ol class="beast-mission-launch-steps"><li><b>1. Define</b><span>State the outcome and the part of the workspace it affects.</span></li><li><b>2. Trust</b><span>Review workspace identity and trust evidence before routing work.</span></li><li><b>3. Plan</b><span>Use a normal chat stream to inspect and plan before writing.</span></li><li><b>4. Implement</b><span>Create a governed worktree mission for multi-file or risky changes.</span></li></ol>
        <label class="beast-mission-objective"><span>Task outcome</span><textarea data-mission-objective rows="3" placeholder="Example: Add a searchable provider catalog to the desktop IDE and verify it in Electron."></textarea></label>
        <div class="beast-page-actions">
          <button class="beast-button secondary" data-mission-action="plan-chat">Plan in Chat</button>
          <button class="beast-button secondary" data-mission-action="verify-trust">Verify Trust</button>
          <button class="beast-button hot" data-mission-action="create-worktree">Create Worktree Mission</button>
          <button class="beast-button secondary" data-mission-action="open-workspace">Open Workspace</button>
        </div>
        <p class="beast-mission-launch-status" data-mission-launch-status>Nothing is created until you choose a path.</p>
      </section>
      <section class="beast-metric-grid" data-mission-metrics></section>
      <section class="beast-stage-flow" data-mission-stages></section>
      <section class="beast-card wide beast-migration-status">
        <h3>Live Surface Status</h3>
        <div class="beast-check-grid">
          <div><b data-mission-gateway-mark>○</b><span>Gateway contract</span></div><div><b data-mission-workspace-mark>○</b><span>Workspace identity</span></div>
          <div><b data-mission-editor-mark>○</b><span>Editor surface</span></div><div><b data-mission-sourceplan-mark>○</b><span>SourcePlan lifecycle</span></div>
          <div><b data-mission-review-mark>○</b><span>Review telemetry</span></div><div><b data-mission-evidence-mark>○</b><span>Evidence telemetry</span></div>
        </div>
      </section>
    `;
    return root;
  }

  function renderer({ signal }) {
    const root = createTemplate();
    let lastMetrics = '';
    let lastStages = '';
    let disposed = false;

    function patch(state) {
      if (disposed) return;
      const mission = state.mission;
      root.querySelector('[data-mission-title]').textContent = mission.title;
      root.querySelector('[data-mission-id]').textContent = `${mission.id} · Owner ${mission.owner || 'Byron'} · Risk ${mission.risk}`;
      root.querySelector('[data-mission-status]').textContent = mission.loading ? 'Refreshing…' : mission.error || mission.status;
      root.querySelector('[data-mission-progress]').textContent = `${mission.progress}%`;
      root.querySelector('[data-mission-progress-bar]').style.width = `${Math.max(0, Math.min(100, mission.progress))}%`;
      root.querySelector('[data-health-ring]').style.setProperty('--value', Math.max(0, Math.min(100, mission.health)));
      root.querySelector('[data-health-value]').textContent = `${mission.health}%`;
      root.querySelector('[data-health-copy]').textContent = `${mission.confidence} confidence · ${mission.risk} risk`;
      const live=state.connection?.status==='online';
      root.querySelector('[data-mission-next-action]').textContent=live?(mission.status==='Unassigned'?'Assign a governed mission':'Open the current mission workspace'):'Restore a verified gateway connection';
      root.querySelector('[data-mission-next-copy]').textContent=live?(mission.status==='Unassigned'?'No live mission is assigned yet. Use Workspace or Swarm to begin governed work.':'Use the workspace to inspect current mission context and SourcePlan readiness.'):'The desktop will not infer a mission or progress while its gateway is unavailable.';
      const launchStatus=root.querySelector('[data-mission-launch-status]');
      launchStatus.textContent=state.worktrees?.creating ? 'Creating the isolated worktree mission…' : state.worktrees?.error ? `Worktree status: ${state.worktrees.error}` : state.workspace?.root ? `Workspace bound: ${state.workspace.root}` : 'Choose a workspace before creating an isolated worktree mission.';
      const objectiveField=root.querySelector('[data-mission-objective]');
      if (document.activeElement!==objectiveField && objectiveField.value!==String(mission.draftObjective||'')) objectiveField.value=String(mission.draftObjective||'');
      const marks={gateway:live,workspace:Boolean(state.workspace?.root),editor:Boolean(state.editor?.activePath||state.editor?.openTabs?.length),sourceplan:Boolean(state.sourcePlan?.updatedAt),review:Boolean(state.review?.updatedAt),evidence:Boolean(state.evidence?.updatedAt)};
      Object.entries(marks).forEach(([key,ok])=>{const node=root.querySelector(`[data-mission-${key}-mark]`);if(node){node.textContent=ok?'✓':'○';node.classList.toggle('live',ok);}});

      const metrics = [
        ['Artifacts', mission.metrics.artifacts, 'evidence'],
        ['Checks', mission.metrics.checks, 'trust'],
        ['Traces', mission.metrics.traces, 'map'],
        ['Evidence', mission.metrics.evidenceItems, 'evidence'],
        ['Agents', mission.metrics.agents, 'agents']
      ];
      const metricsKey = JSON.stringify(metrics);
      if (metricsKey !== lastMetrics) {
        lastMetrics = metricsKey;
        const host = root.querySelector('[data-mission-metrics]');
        host.replaceChildren(...metrics.map(([label, value, icon]) => {
          const item = card(label, 'compact');
          const image = new Image(); image.src = BeastAssets.icon(icon); image.alt = '';
          const strong = document.createElement('strong'); strong.className = 'metric'; strong.textContent = String(value);
          item.append(image, strong);
          return item;
        }));
      }

      const stagesKey = JSON.stringify(mission.path);
      if (stagesKey !== lastStages) {
        lastStages = stagesKey;
        const host = root.querySelector('[data-mission-stages]');
        host.replaceChildren(...mission.path.map((stage, index) => {
          const button = document.createElement('button');
          button.className = `beast-card beast-stage-card ${stage.status === 'Complete' ? 'complete' : ''} ${stage.status === 'In Progress' ? 'active' : ''}`;
          button.dataset.nav = stage.id;
          const number = document.createElement('span'); number.className = 'number'; number.textContent = `0${index + 1}`;
          const image = new Image(); image.src = BeastAssets.icon(stage.id); image.alt = '';
          const heading = document.createElement('h3'); heading.textContent = stage.title;
          const copy = document.createElement('p'); copy.textContent = stageCopy[stage.id] || '';
          const status = document.createElement('em'); status.textContent = stage.status;
          button.append(number, image, heading, copy, status);
          return button;
        }));
      }
    }

    const unsubscribe = BeastStore.subscribe(patch);
    root.addEventListener('click', async event => {
      const action=event.target.closest('[data-mission-action]')?.dataset.missionAction;
      if (action === 'refresh') {
        BeastDesktopBridge.snapshot({ signal });
        BeastFX.trigger('ring', event.target, { size: 230 });
      }
      if (action === 'focus-launch') {
        root.querySelector('[data-mission-launch]')?.scrollIntoView({behavior:'smooth',block:'start'});
        root.querySelector('[data-mission-objective]')?.focus({preventScroll:true});
      }
      if (action === 'open-workspace') BeastRouter.navigate('workspace');
      if (action === 'verify-trust') BeastRouter.navigate('trust');
      if (action === 'plan-chat') {
        const objective=(root.querySelector('[data-mission-objective]')?.value||BeastStore.get().mission.draftObjective||'').trim();
        if (!objective) { root.querySelector('[data-mission-objective]')?.focus(); return; }
        BeastTerminalToolingDoctorBridge.setChatPrompt(`Help me plan this coding task. First inspect the relevant workspace context; do not make changes yet.\n\nTask: ${objective}`);
        BeastRouter.navigate('terminal');
      }
      if (action === 'create-worktree') {
        const objective=(root.querySelector('[data-mission-objective]')?.value||BeastStore.get().mission.draftObjective||'').trim();
        if (!objective) { root.querySelector('[data-mission-objective]')?.focus(); return; }
        try {
          await BeastUtilityOrchestrationBridge.worktreeAction('create','',{objective});
          BeastRouter.navigate('worktrees');
        } catch (error) {
          BeastStore.patch('worktrees',{error:String(error.message || error)});
        }
      }
    });
    root.addEventListener('input', event => {
      if (!event.target.matches('[data-mission-objective]')) return;
      const draft=event.target.value;
      localStorage.setItem('beast.mission.draft',draft);
      BeastStore.patch('mission',{draftObjective:draft});
    });

    if (!BeastStore.get().mission.loading && !BeastStore.get().mission.lastRefreshAt) queueMicrotask(() => BeastDesktopBridge.snapshot({ signal }));

    return { node: root, dispose() { disposed = true; unsubscribe(); } };
  }

  window.BeastMissionPage = { renderer };
})();
