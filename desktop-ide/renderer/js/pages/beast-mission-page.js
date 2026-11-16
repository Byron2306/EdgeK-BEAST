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
          <h3>Next Best Action</h3><strong class="metric">Review Center + Evidence Forge</strong>
          <p>Validate quality gates, contradiction handling, evidence selection, traceability, and audit-pack assembly on the clean shell.</p>
          <button class="beast-button amber" data-nav="review">Open Review Center</button>
        </section>
      </div>
      <section class="beast-metric-grid" data-mission-metrics></section>
      <section class="beast-stage-flow" data-mission-stages></section>
      <section class="beast-card wide beast-migration-status">
        <h3>Phase 4 Migration Status</h3>
        <div class="beast-check-grid">
          <div><b>✓</b><span>Single route owner</span></div><div><b>✓</b><span>Single mascot timer</span></div>
          <div><b>✓</b><span>Editor Cortex + SourcePlan</span></div><div><b>✓</b><span>Zoom-safe page scroll</span></div>
          <div><b>✓</b><span>Review Center bridge</span></div><div><b>✓</b><span>Evidence Forge bridge</span></div>
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
    root.addEventListener('click', event => {
      if (event.target.closest('[data-mission-action="refresh"]')) {
        BeastDesktopBridge.snapshot({ signal });
        BeastFX.trigger('ring', event.target, { size: 230 });
      }
    });

    if (!BeastStore.get().mission.loading && !BeastStore.get().mission.lastRefreshAt) queueMicrotask(() => BeastDesktopBridge.snapshot({ signal }));

    return { node: root, dispose() { disposed = true; unsubscribe(); } };
  }

  window.BeastMissionPage = { renderer };
})();
