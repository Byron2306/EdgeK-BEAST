(function () {
  const c = () => window.opcbComponents;
  const asset = (phase, file) => `assets/opcb/phase${phase}/svg/${file}`;

  function fileIcon(file) {
    return asset(2, `file-${file.ext || 'md'}.svg`);
  }

  function metricStrip(metrics) {
    return `<div class="metric-strip">${metrics.map(metric => c().metricCard(metric)).join('')}</div>`;
  }

  function renderWorkspacePage(state) {
    const host = document.querySelector('.opcb-dashboard[data-page-panel="workspace"]');
    if (!host) return;
    const ui = state.ui || {};
    const nodes = state.mission.path;
    const stageCopy = {
      mission: ['Define goal and success criteria', asset(1, 'mission-target.svg')],
      models: ['Select and route local models', asset(1, 'models-cube.svg')],
      agents: ['Assign agents and roles', asset(1, 'agents-bot.svg')],
      workspace: ['Bind tools and capabilities', asset(1, 'tools-crossed.svg')],
      review: ['Plan checks and review gates', asset(1, 'review-lens.svg')],
      evidence: ['Collect and verify evidence', asset(1, 'evidence-doc.svg')],
      crystallization: ['Synthesize and make durable', asset(1, 'crystal-diamond.svg')]
    };
    const detailCards = [
      { id: 'mission', title: 'Mission Brief', copy: state.mission.title, action: 'Open Brief' },
      { id: 'models', title: 'Model Route', copy: `${state.route.active} · fallback ${state.route.fallback[0]}`, action: 'Edit Route' },
      { id: 'agents', title: 'Agent Squad', copy: state.agents.map(agent => agent.label).join(' · '), action: 'View Agents' },
      { id: 'workspace', title: 'Toolbelt', copy: 'Code Graph · Profiler · File System · Shell · Evidence Parser', action: 'Manage Tools' },
      { id: 'review', title: 'Review Gates', copy: `${state.review.gatesPassed}/${state.review.gatesTotal} gates passed · ${state.review.contradictions} contradiction under review.`, action: 'View Gates' },
      { id: 'evidence', title: 'Evidence Sink', copy: `${state.evidence.selected}/${state.evidence.total} selected · ${state.evidence.validity}% validity.`, action: 'Open Evidence' },
      { id: 'crystallization', title: 'Crystallization', copy: `${state.crystal.readiness}% readiness · immutable ${state.crystal.immutable ? 'enabled' : 'pending'}.`, action: 'View Candidates' }
    ];
    host.innerHTML = `
      <div class="opcb-section-head">
        <div><h2>Flow Canvas</h2></div>
        <div class="opcb-toolbar"><button class="ghost-button ${ui.workspaceCanvas === 'fit' ? 'active' : ''}" data-opcb-select="workspace-canvas" data-id="fit">Fit</button><button class="ghost-button ${ui.workspaceCanvas === 'zoom-reset' ? 'active' : ''}" data-opcb-select="workspace-canvas" data-id="zoom-reset">100%</button><button class="ghost-button ${ui.workspaceCanvas === 'list' ? 'active' : ''}" data-opcb-select="workspace-canvas" data-id="list">List</button></div>
      </div>
      <div class="workspace-flow-canvas canvas-mode-${c().escapeHtml(ui.workspaceCanvas || 'fit')}">
        <svg class="workspace-flow-lines" viewBox="0 0 1000 420" preserveAspectRatio="none" aria-hidden="true">
          <path class="flow-main" d="M75 93 H925" />
          <path d="M75 132 V280 H145" />
          <path d="M215 132 V280 H285" />
          <path d="M355 132 V280 H425" />
          <path d="M495 132 V280 H565" />
          <path d="M635 132 V280 H705" />
          <path d="M775 132 V280 H845" />
          <path d="M925 132 V280 H925" />
          <path class="flow-arc" d="M285 280 C410 205 565 205 705 280" />
        </svg>
        <div class="workspace-stage-row">
          ${nodes.map(node => {
            const [copy, icon] = stageCopy[node.id] || [`Operate ${node.label.toLowerCase()}`, asset(1, 'workspace-flow.svg')];
            return `
              <button class="workspace-stage ${node.status === 'Complete' ? 'done' : ''} ${node.status === 'In Progress' ? 'active' : ''} ${node.tone || ''}" data-page-target="${c().escapeHtml(node.id)}">
                <span class="stage-number">${node.number}</span>
                <img class="stage-icon" src="${icon}" alt="">
                <strong>${c().escapeHtml(node.label)}</strong>
                <small>${c().escapeHtml(copy)}</small>
                <em>${c().escapeHtml(node.status)}</em>
              </button>
            `;
          }).join('')}
        </div>
        <div class="workspace-detail-row">
          ${detailCards.map(card => `
            <button class="workspace-detail-card ${card.id === 'crystallization' ? 'candidate' : ''}" data-page-target="${c().escapeHtml(card.id)}">
              <b>${c().escapeHtml(card.title)}</b>
              <p>${c().escapeHtml(card.copy)}</p>
              <span>${c().escapeHtml(card.action)}</span>
            </button>
          `).join('')}
        </div>
      </div>
    `;
  }

  function renderMissionPage(state) {
    const host = document.querySelector('.opcb-dashboard[data-page-panel="mission"]');
    if (!host) return;
    const mission = state.mission;
    const pathCopy = {
      mission: 'Define goal and success criteria',
      models: 'Select and route local models',
      agents: 'Assign agents and roles',
      workspace: 'Bind tools and capabilities',
      review: 'Plan checks and review gates',
      evidence: 'Collect and verify evidence',
      crystallization: 'Synthesize and make durable'
    };
    host.innerHTML = `
      <div class="opcb-section-head">
        <div><h2>Mission Overview</h2></div>
        <span class="active-chip">${c().escapeHtml(mission.status)}</span>
      </div>
      <div class="mission-overview-grid">
        <div class="opcb-card"><b>Mission Brief</b><p>${c().escapeHtml(mission.title)}.</p><button class="ghost-button" data-ide-action="mission.route">Open Full Brief</button></div>
        <div class="opcb-card"><b>Objective</b><p>Design and validate a local evidence parser powered by Code Graph and Profiler.</p><span class="badge">Primary Objective</span></div>
        <div class="opcb-card"><b>Scope</b><div class="pill-row scope-control-row"><button data-page-target="map">Code Graph</button><button data-ide-action="code.intel">Profiler</button><button data-page-target="evidence">Evidence Parser</button><button data-page-target="review">Review Gates</button><button data-page-target="workspace">Local Artifacts</button><button data-opcb-refresh="mission">+2</button></div></div>
        <div class="opcb-card"><b>Hypothesis</b><p>Combining static and dynamic insights increases evidence precision and lowers summarization drift.</p><em>Confidence: ${c().escapeHtml(mission.confidence)}</em></div>
        <div class="opcb-card"><b>Key Gaps</b><p>No unified mapping between profiles and code nodes. Parser robustness on large codebases remains under test.</p><button class="ghost-button" data-ide-action="code.intel">View Gaps</button></div>
        <div class="opcb-card"><b>Success Criteria</b>${c().gateList([{ label: 'Evidence source traceability', status: 'Required' }, { label: 'Schema validation', status: 'Required' }, { label: 'Review gates clean', status: 'Required' }])}</div>
      </div>
      <div class="mission-path-panel">
        <div class="mini-section-title">Mission Path</div>
        <div class="mission-path">
          ${mission.path.map(step => `
            <button class="path-step ${step.status === 'Complete' ? 'done' : ''} ${step.status === 'In Progress' ? 'active' : ''} ${step.id === 'crystallization' ? 'candidate' : ''}" data-page-target="${c().escapeHtml(step.id)}">
              <span>${step.number}</span>
              <b>${c().escapeHtml(step.label)}</b>
              <small>${c().escapeHtml(pathCopy[step.id] || '')}</small>
              <em>${c().escapeHtml(step.status)}</em>
            </button>
          `).join('')}
        </div>
      </div>
      <div class="mission-lower-grid">
        <div class="opcb-card"><b>Approvals &amp; Review Gates</b>${c().gateList(state.review.gates)}</div>
        <div class="opcb-card mission-timeline-card"><b>Timeline</b><div class="mission-time-row"><span>Started<br><em>May 24, 14:29</em></span><span>Target Review<br><em>May 24, 15:30</em></span><span>Target Complete<br><em>May 24, 17:00</em></span></div><div class="mission-progress-line"><i></i></div>${c().gateList([{ label: 'Elapsed', status: mission.timeline.elapsed }, { label: 'Remaining', status: mission.timeline.remaining }, { label: 'ETA', status: mission.timeline.eta }])}</div>
        <div class="opcb-card"><b>Mission Metrics</b>${c().gateList(Object.entries(mission.metrics).map(([label, value]) => ({ label, status: String(value) })))}</div>
      </div>
    `;
  }

  function renderModelsPage(state) {
    const host = document.querySelector('.opcb-dashboard[data-page-panel="models"]');
    if (!host) return;
    const route = state.route;
    const runtimes = route.runtimes || [
      { label: 'Ollama v0.4.3', status: 'Running · Healthy' },
      { label: 'LM Studio v0.3.7', status: 'Running · Healthy' },
      { label: 'llama.cpp b5123', status: 'Ready · Optimized' },
      { label: 'ExllamaV2 v0.2.8', status: 'Ready · Optimized' }
    ];
    host.innerHTML = `
      <div class="opcb-section-head"><div><h2>Models</h2><span>Local LLM routing and system capability awareness</span></div><button class="ghost-button" data-ide-action="providers.refresh">Model Settings</button></div>
      <div class="models-tab-row"><span>Model Router</span><span>Model Registry</span><span>Runtimes</span><span>Benchmarks</span><span>Assignments</span><span>Policy</span></div>
      <div class="route-summary-grid">
        ${c().metricCard({ label: 'Active Route', value: 'Primary Local', sublabel: 'All systems nominal', tone: 'teal', icon: asset(4, 'active-model.svg') })}
        ${c().metricCard({ label: 'Primary Model', value: route.active, sublabel: 'LOCAL · GGUF · Q4_K_M', tone: 'violet', icon: asset(4, 'active-model.svg') })}
        ${c().metricCard({ label: 'Fallback Model', value: route.fallback[0], sublabel: 'LOCAL · GGUF · Q4_K_M', tone: 'cyan', icon: asset(4, 'fallback-ladder.svg') })}
        ${c().metricCard({ label: 'Route Reason', value: route.reason, sublabel: '+12% vs next candidate', tone: 'cyan', icon: asset(4, 'route-explain.svg') })}
        ${c().metricCard({ label: 'Policy', value: 'Local First', sublabel: 'Cloud disabled', tone: 'teal', icon: asset(4, 'runtime-ready.svg') })}
      </div>
      <div class="models-layout">
        <section class="route-planner-panel">
          <header><div><b>Route Planner</b><p>Design and test local model routing logic</p></div><button class="ghost-button" data-ide-action="providers.refresh">Test Route</button></header>
          <div class="route-flow">
            <svg class="route-flow-lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
              <path d="M24 28 H48 V20 H62" />
              <path d="M24 70 H48 V80 H62" />
              <path d="M62 28 V45" />
              <path d="M62 58 V74" />
              <path d="M68 52 H82" />
            </svg>
            <div class="route-card primary"><strong>Primary</strong><b>${c().escapeHtml(route.active)}</b><span>Context 32K · Speed ${c().escapeHtml(route.throughput)}</span><em>Active</em></div>
            <div class="route-card fallback"><strong>Fallback</strong><b>${c().escapeHtml(route.fallback[0])}</b><span>Context 32K · Speed 31 tok/s</span><em>Standby</em></div>
            <div class="route-logic"><span>User Request<br><em>Code / Reason / Plan</em></span><i>Router Logic<br><em>Local First Policy</em></i><b>Primary<br>Available?</b><small>Response<br><em>Stream to IDE</em></small></div>
            <div class="routing-rules"><b>Routing Rules</b>${c().gateList([{ label: 'Prefer local models', status: 'Always try primary first' }, { label: 'Auto-fallback', status: 'On failure or timeout' }, { label: 'Context fit', status: 'Prefer sufficient context' }, { label: 'Latency guard', status: 'Failover if latency > 2s' }])}</div>
          </div>
        </section>
        <section class="available-models-panel">
          <header><b>Available Models (Local)</b><button class="ghost-button" data-page-target="providers">+ Add Model</button></header>
          <div class="model-search-row"><span>Search models...</span><span>All Runtimes</span></div>
          <div class="model-ladder">
            ${route.models.map((model, index) => `<button class="model-row ${index === 0 ? 'primary' : ''}" data-page-target="providers"><b>${c().escapeHtml(model.id)}</b><span>${model.confidence}% · ${model.latency} · ${model.speed} · ${model.size}</span><em>${c().escapeHtml(model.role)}</em></button>`).join('')}
          </div>
        </section>
        <section class="runtime-strip">
          ${runtimes.map((runtime, index) => {
            const label = typeof runtime === 'string' ? runtime : runtime.label;
            const status = typeof runtime === 'string' ? (index < 2 ? 'Running · Healthy' : 'Ready · Optimized') : runtime.status;
            return `<button class="runtime-card" data-ide-action="providers.refresh"><img class="opcb-asset-icon" src="${asset(4, index < 2 ? 'provider-local.svg' : 'runtime-ready.svg')}" alt=""><b>${c().escapeHtml(label)}</b><span>${c().escapeHtml(status || 'Ready')}</span></button>`;
          }).join('')}
          <button class="runtime-card add-runtime" data-page-target="providers">+<span>Add Runtime</span></button>
        </section>
        <section class="route-tests-panel">
          <header><b>Recent Route Tests</b><button class="ghost-button" data-ide-action="providers.refresh">Run New Test</button></header>
          <div class="model-test-bars">
            <span style="--w:95">qwen2.5-coder:7b <em>94.7%</em></span>
            <span style="--w:83">deepseek-coder:6.7b <em>83.1%</em></span>
            <span style="--w:68">mistral-nemo:12b <em>68.4%</em></span>
          </div>
          <div class="model-test-metrics">${c().gateList([{ label: 'Accuracy', status: '94.7%' }, { label: 'Latency p50', status: route.latency }, { label: 'Throughput', status: route.throughput }, { label: 'Error Rate', status: '0.3%' }])}</div>
        </section>
        <section class="opcb-card model-details-card"><b>Model Details</b>${c().gateList([{ label: 'Context Window', status: '32K' }, { label: 'Quantization', status: 'Q4_K_M' }, { label: 'Latency', status: route.latency }, { label: 'Throughput', status: route.throughput }, { label: 'Policy', status: route.policy }])}</section>
      </div>
    `;
  }

  function renderAgentsPage(state) {
    const host = document.querySelector('.opcb-dashboard[data-page-panel="agents"]');
    if (!host) return;
    host.innerHTML = `
      <div class="opcb-section-head"><div><h2>Agent Constellation</h2><span>Planner, graph, profiler, and verifier agents operating as a local mission swarm.</span></div><button class="ghost-button" data-command="/assign agent">Assign Agent</button></div>
      <div class="agent-command-deck">
        <section class="agent-orbit-panel">
          <div class="agent-core"><img src="${asset(4, 'agents-squad.svg')}" alt=""><strong>Mission Orchestrator</strong><span>Live coordination bus</span></div>
          ${state.agents.map((agent, index) => `
            <button class="agent-orbit-node node-${index}" data-agent-id="${c().escapeHtml(agent.id)}">
              <img src="${asset(4, agent.id === 'planner' ? 'agent-planner.svg' : agent.id === 'graph' ? 'agent-graph.svg' : agent.id === 'profiler' ? 'agent-profiler.svg' : 'agent-verifier.svg')}" alt="">
              <b>${c().escapeHtml(agent.label)}</b>
              <span>${c().escapeHtml(agent.status)} · ${agent.confidence}%</span>
            </button>
          `).join('')}
        </section>
        <section class="agent-stream-panel">
          <b>Live Handoff Stream</b>
          ${c().eventLedger([['14:32', 'Planner shaped review gate path'], ['14:31', 'Graph analyst linked evidence nodes'], ['14:30', 'Profiler sampled hot paths'], ['14:29', 'Verifier queued contradiction check']])}
        </section>
        <section class="agent-capability-panel">
          <b>Capability Matrix</b>
          ${state.agents.map(agent => `<button data-agent-id="${c().escapeHtml(agent.id)}"><span>${c().escapeHtml(agent.label)}</span><em>${agent.tools.map(tool => c().escapeHtml(tool)).join(' · ')}</em></button>`).join('')}
        </section>
        <section class="agent-security-panel">
          <b>Memory &amp; Trust Boundary</b>
          <p>Agent memory access is local-first, scoped to mission artifacts, and signed through trust policy.</p>
          <div class="agent-permission-grid"><span>Evidence Read</span><span>Mission Write</span><span>Verify Only</span><span>Local Tools</span></div>
          <button class="ghost-button" data-page-target="trust">Review Access</button>
        </section>
      </div>
    `;
  }

  function renderReviewPage(state) {
    const host = document.querySelector('.opcb-dashboard[data-page-panel="review"]');
    if (!host) return;
    const review = state.review;
    const reviewStages = [
      ['1', 'Mission', 'done'],
      ['2', 'Models', 'done'],
      ['3', 'Agents', 'done'],
      ['4', 'Tools', 'done'],
      ['5', 'Review', 'active'],
      ['6', 'Evidence', ''],
      ['7', 'Crystallization', '']
    ];
    host.innerHTML = `
      <div class="opcb-section-head">
        <div><h2>Review</h2><span>Validate outputs, assess quality, and approve with confidence.</span></div>
        <button class="ghost-button" data-command="/review gates">Review Gates</button>
      </div>
      <div class="review-stage-rail">
        ${reviewStages.map(([number, label, status]) => `<button class="${status}" data-page-target="${label.toLowerCase() === 'tools' ? 'workspace' : label.toLowerCase()}"><span>${number}</span>${c().escapeHtml(label)}<em>${status === 'done' ? '✓' : status === 'active' ? 'Review' : ''}</em></button>`).join('')}
      </div>
      <div class="review-score-grid">
        <section class="review-score-card evidence">
          ${c().ringMetric({ value: review.evidenceSufficiency, label: 'Sufficient', tone: 'cyan' })}
          <div><b>Evidence Sufficiency</b>${c().gateList([{ label: 'Coverage', status: 'High' }, { label: 'Completeness', status: '82%' }, { label: 'Confidence', status: '84%' }])}</div>
          <button class="ghost-button" data-ide-action="evidence.search">View Details</button>
        </section>
        <section class="review-score-card parser">
          ${c().ringMetric({ value: 91, label: 'Robust', tone: 'violet' })}
          <div><b>Parser Robustness</b>${c().gateList([{ label: 'Validations Passed', status: '134 / 142' }, { label: 'Edge Cases', status: '18 / 20' }, { label: 'Failure Rate', status: '1.2%' }])}</div>
          <button class="ghost-button" data-ide-action="sourceplan.verify_runbook">View Report</button>
        </section>
        <section class="review-score-card quality">
          ${c().ringMetric({ value: 88, label: 'Good', tone: 'teal' })}
          <div><b>Quality Scorecard</b>${c().gateList([{ label: 'Accuracy', status: '90%' }, { label: 'Consistency', status: '86%' }, { label: 'Reproducibility', status: '88%' }])}</div>
          <button class="ghost-button" data-ide-action="sourceplan.lifecycle">Open Scorecard</button>
        </section>
        <section class="review-score-card confidence">
          ${c().ringMetric({ value: review.confidence, label: 'High', tone: 'teal' })}
          <div><b>Overall Confidence</b>${c().gateList([{ label: 'Evidence', status: '86%' }, { label: 'Robustness', status: '91%' }, { label: 'Quality', status: '88%' }])}</div>
          <button class="ghost-button" data-ide-action="sourceplan.lifecycle">Confidence Breakdown</button>
        </section>
      </div>
      <div class="review-ops-grid">
        <section class="opcb-card review-gates-card"><b>Review Gates</b>${c().gateList([
          { label: 'Plan Validity', status: 'Passed' },
          { label: 'Evidence Sufficiency', status: 'Passed' },
          { label: 'Parser Robustness', status: 'Passed' },
          { label: 'Contradiction Check', status: 'Warning', tone: 'amber' },
          { label: 'Risk Assessment', status: 'Failed', tone: 'danger' },
          { label: 'Test Coverage', status: '82% tests passed' }
        ])}<button class="ghost-button" data-ide-action="sourceplan.lifecycle">View Gate Details</button></section>
        <section class="opcb-card review-diff-card"><b>Diff Review</b><div class="diff-compare"><div><strong>Previous Plan</strong>${c().gateList([{ label: 'Files', status: '24' }, { label: 'Rules', status: '68' }, { label: 'Parser rules', status: '+6' }, { label: 'Removed items', status: '-2', tone: 'danger' }])}</div><i></i><div><strong>Current Plan</strong>${c().gateList([{ label: 'Files', status: '27' }, { label: 'Rules', status: '74' }, { label: 'Parser rules', status: '+12' }, { label: 'Removed items', status: '-1', tone: 'danger' }])}</div></div><button class="ghost-button" data-ide-action="sourceplan.lifecycle">View Full Diff</button></section>
        <section class="opcb-card review-risk-card"><b>Risk &amp; Flags</b>${c().gateList([{ label: 'High Risk', status: '2', tone: 'danger' }, { label: 'Medium Risk', status: '3', tone: 'amber' }, { label: 'Low Risk', status: '4' }, { label: 'Info', status: '2', tone: 'cyan' }])}<button class="ghost-button" data-ide-action="sourceplan.lifecycle">Open Risk Register</button></section>
        <section class="opcb-card test-summary-card"><b>Test Summary</b><div class="review-inline-ring">${c().ringMetric({ value: 82, label: 'Tests Passed' })}</div>${c().gateList([{ label: 'Total Tests', status: '156' }, { label: 'Passed', status: '128' }, { label: 'Failed', status: '18', tone: 'danger' }, { label: 'Skipped', status: '10' }])}<button class="ghost-button" data-ide-action="tooling.syntax">View Test Report</button></section>
        <section class="opcb-card contradiction-card"><b>Contradiction Check</b>${c().gateList([{ label: 'Contradictions Found', status: '3', tone: 'danger' }, { label: 'Resolved', status: '1' }, { label: 'Under Review', status: '2', tone: 'amber' }, { label: 'False Positives', status: '0' }])}<div class="top-contradictions"><span>Timestamp mismatch <em>High</em></span><span>Parser rule conflict (P-17) <em>High</em></span><span>File size limit inconsistency <em>Medium</em></span></div><button class="ghost-button" data-ide-action="evidence.search">Review Contradictions</button></section>
        <section class="opcb-card final-recommendation-card"><b>Final Recommendation</b><h3>Changes Requested</h3><p>The plan is strong but requires attention to blockers before approval.</p><ul><li>Resolve 2 high-risk blockers</li><li>Add evidence for edge case P-17</li><li>Review timestamp contradiction</li></ul><button class="ghost-button" data-ide-action="sourceplan.export_runbook">Generate Review Report</button></section>
      </div>
    `;
  }

  function selectedEvidence(state) {
    return state.evidence.files.find(file => file.id === state.evidence.selectedId) || state.evidence.files[0];
  }

  function renderEvidencePage(state) {
    const host = document.querySelector('.opcb-dashboard[data-page-panel="evidence"]');
    if (!host) return;
    const evidence = state.evidence;
    const selected = selectedEvidence(state);
    host.innerHTML = `
      <div class="opcb-section-head">
        <div><h2>Evidence</h2><span>Collect, validate, and package verifiable proof.</span></div>
        <div class="opcb-toolbar"><button class="ghost-button" data-ide-action="evidence.search">Search evidence...</button><button class="ghost-button" data-command="/find links">Filter</button></div>
      </div>
      <div class="evidence-tab-row"><span>Evidence Files</span><span>Evidence Packs</span><span>Artifacts</span><span>Traceability</span><span>Audit Trail</span></div>
      <div class="evidence-layout">
        <section class="evidence-list-panel">
          <header><b>Evidence Files</b><button class="ghost-button" data-command="/evidence add">+ Add Evidence</button></header>
          <div class="evidence-list">
          ${evidence.files.map(file => `
            <button class="evidence-row ${file.id === selected.id ? 'active' : ''}" data-evidence-id="${c().escapeHtml(file.id)}">
              <b><img class="opcb-asset-icon opcb-injected-icon" src="${fileIcon(file)}" alt="">${c().escapeHtml(file.name)}</b>
              <span>${c().escapeHtml(file.type)} · ${c().escapeHtml(file.size)}</span>
              <em>${file.confidence}%</em>
            </button>
          `).join('')}
          </div>
          <footer>Showing 1-7 of ${evidence.total}<span>‹ 1 2 3 ›</span></footer>
        </section>
        <section class="evidence-detail-panel">
          <header><div><b>Selected Evidence</b><h3>${c().escapeHtml(selected.name)} <span class="badge ready">${c().escapeHtml(selected.status)}</span></h3></div><button class="ghost-button" data-page-target="source">Open</button></header>
          <div class="evidence-meta-row"><span>Type: ${c().escapeHtml(selected.type)}</span><span>Size: ${c().escapeHtml(selected.size)}</span><span>Source: Local</span><span>Added: May 24, 2025 14:30</span></div>
          <div class="evidence-metric-grid">
            ${c().metricCard({ label: 'Extraction Confidence', value: `${selected.confidence}%`, sublabel: 'High Confidence', tone: 'teal', icon: asset(2, 'extract-fields.svg') })}
            ${c().metricCard({ label: 'Schema Validation', value: 'Valid', sublabel: '0 issues detected', tone: 'cyan', icon: asset(2, 'schema-valid.svg') })}
            ${c().metricCard({ label: 'Completeness', value: '96%', sublabel: 'Requirements met', tone: 'teal', icon: asset(2, 'completeness.svg') })}
            ${c().metricCard({ label: 'Trace Links', value: '14', sublabel: 'Linked artifacts', tone: 'violet', icon: asset(2, 'trace-link.svg') })}
          </div>
          <div class="opcb-tab-row"><span>Overview</span><span>Schema</span><span>Extracted Fields</span><span>Trace Links</span><span>Validation</span><span>Metadata</span></div>
          <div class="evidence-preview-grid">
            <pre># Parser Requirements
1. Parse raw evidence inputs
2. Extract structured entities
3. Validate against schema and rules
4. Preserve source traceability</pre>
            <aside><b>Key Entities (12)</b>${c().gateList([{ label: 'Requirement', status: '12' }, { label: 'Function', status: '8' }, { label: 'Constraint', status: '6' }, { label: 'Data Field', status: '24' }, { label: 'Rule', status: '10' }])}<button class="ghost-button" data-ide-action="code.symbol_search">View All Entities</button></aside>
          </div>
          <section class="trace-link-strip"><b>Trace Links</b>${evidence.traceLinks.map(link => `<button data-ide-action="evidence.search"><img class="opcb-asset-icon" src="${fileIcon({ ext: link.type || 'json' })}" alt=""><span>${c().escapeHtml(link.label)}</span><em>${c().escapeHtml(link.status)}</em></button>`).join('')}</section>
        </section>
      </div>
    `;
  }

  function renderCrystallizationPage(state) {
    const host = document.querySelector('.opcb-dashboard[data-page-panel="crystallization"]');
    if (!host) return;
    const crystal = state.crystal;
    const selected = crystal.candidateList.find(item => item.id === crystal.selectedCandidate) || crystal.candidateList[0];
    host.innerHTML = `
      <div class="opcb-section-head"><div><h2>Crystallization</h2><span>Transform verified intelligence into immutable, portable crystal artifacts.</span></div><span class="active-chip">All Passed</span></div>
      <div class="crystallize-board">
        <section class="crystal-queue-panel">
          <header><b>Candidate Queue</b><span>7</span><em>Auto-Prioritize</em></header>
          ${crystal.candidateList.map(candidate => `
            <button class="candidate ${candidate.id === selected.id ? 'active' : ''}" data-crystal-candidate="${c().escapeHtml(candidate.id)}">
              <img class="opcb-asset-icon" src="${asset(3, 'crystal-candidate.svg')}" alt="">
              <b>${c().escapeHtml(candidate.label)}</b>
              <span>${c().escapeHtml(candidate.domain)} · ${c().escapeHtml(candidate.value)}</span>
              <em>${candidate.ready}% Ready</em>
            </button>
          `).join('')}
          <button class="ghost-button" data-ide-action="sourceplan.propose_learning">+ Add Candidate</button>
        </section>
        <section class="crystal-chamber-panel">
          <header><b>Crystal Chamber</b><span>Ready</span></header>
          <div class="crystal-chamber-core">
            <aside class="crystal-readiness-card">
              ${c().ringMetric({ value: selected.ready, label: 'Exceptional', tone: 'violet' })}
              ${c().gateList([{ label: 'Completeness', status: '98%' }, { label: 'Consistency', status: '96%' }, { label: 'Evidence Depth', status: '93%' }, { label: 'Trace Quality', status: '89%' }, { label: 'Risk Level', status: 'Low' }])}
            </aside>
            <div class="crystal-chamber has-asset">
              <div class="crystal-glyph"></div>
              <span>Crystal Projection</span>
              <em>High Integrity · Portable · Verifiable</em>
            </div>
            <aside class="selected-candidate-card">
              <b>Selected Candidate</b>
              <h3>${c().escapeHtml(selected.label)}</h3>
              <div class="pill-row"><span>Evidence</span><span>Code Graph</span></div>
              ${c().gateList([{ label: 'Artifacts', status: '32' }, { label: 'Checks', status: '127' }, { label: 'Traces', status: '1,842' }, { label: 'Evidence Links', status: '48' }])}
              <button class="ghost-button" data-ide-action="settings.release_readiness">View Analysis</button>
            </aside>
          </div>
          <div class="crystal-stage-track"><span>Analyze</span><span>Validate</span><span>Simulate</span><span>Ready</span></div>
        </section>
        <section class="crystal-side-panel">
          <div class="opcb-card quality-gates-card"><b>Quality Gates</b>${c().gateList(crystal.gates)}</div>
          <div class="opcb-card committed-preview-card"><b>Committed Artifact Preview</b><div><span>Crystal ID</span><em>CRY-7F3A-982C-20250524</em></div><div><span>Size</span><em>18.7 MB</em></div><div><span>Format</span><em>OPCB Crystal v1.2</em></div><img src="${asset(3, 'crystal-chamber-committed.svg')}" alt=""></div>
        </section>
        <section class="crystal-ledger-panel">
          <header><b>Event Ledger</b><span>Live</span></header>
          ${c().eventLedger(crystal.events)}
        </section>
        <section class="crystal-final-actions">
          <div><b>Final Actions</b><p>Seal your intelligence. Make it undeniable.</p></div>
          <button data-command="/verify candidate"><img src="${asset(3, 'trust-shield.svg')}" alt="">Verify<span>Re-run full validation</span></button>
          <button class="primary-crystal-action" data-command="/crystallize now"><img src="${asset(3, 'crystal-ready.svg')}" alt="">Crystallize<span>Commit to immutable crystal</span></button>
          <button data-command="/seal artifact"><img src="${asset(3, 'immutable-lock.svg')}" alt="">Seal<span>Lock artifact immutably</span></button>
          <button data-command="/export preview"><img src="${asset(3, 'crystal-export.svg')}" alt="">Export<span>Share or deploy</span></button>
        </section>
      </div>
    `;
  }
  function renderTrustPage(state) {
    const host = document.querySelector('.opcb-dashboard[data-page-panel="trust"]');
    if (!host) return;
    const trust = state.trust;
    host.innerHTML = `
      <div class="opcb-section-head"><div><h2>Trust Posture</h2><span>Local-first boundaries, signatures, canaries, and policy guardrails.</span></div><span class="active-chip">Secure</span></div>
      <div class="trust-posture-grid">
        <section class="trust-hero-panel">
          <img src="${asset(3, 'trust-shield.svg')}" alt="">
          <div><h3>Secure</h3><p>Policy: Balanced</p></div>
          <label>Overall Trust Score <em>${trust.score} / 100</em></label>
          <div class="trust-bar"><i style="width:${trust.score}%"></i></div>
          ${c().gateList([{ label: 'Systems Healthy', status: `${trust.systemsHealthy} / ${trust.systemsTotal}` }, { label: 'No Critical Alerts', status: 'Verified' }])}
        </section>
        <section class="opcb-card trust-boundary-card"><b>Data Boundary</b><h3>Local-First</h3><ul><li>All mission data stays local</li><li>No external telemetry</li><li>Air-gapped capable</li></ul><button class="ghost-button" data-page-target="map">View Boundary Map</button></section>
        <section class="opcb-card trust-integrity-card"><b>Integrity</b><h3>${c().escapeHtml(trust.integrity)}</h3><ul><li>Agents verified</li><li>Models verified</li><li>Evidence verified</li></ul><button class="ghost-button" data-command="/verify integrity">Verify Now</button></section>
        <section class="opcb-card trust-policy-card"><b>Policy Guardrails</b><h3>${c().escapeHtml(trust.guardrails)}</h3><ul><li>Role-based access</li><li>Least privilege</li><li>Change approvals</li></ul><button class="ghost-button" data-command="/policy check">View Policies</button></section>
        <section class="opcb-card provenance-panel"><b>Provenance &amp; Signatures</b><div class="fingerprint-mark"></div>${c().gateList([{ label: 'Root ID', status: trust.provenance.rootId }, { label: 'Algorithm', status: trust.provenance.algorithm }, { label: 'Signed By', status: trust.provenance.signedBy }, { label: 'Signed At', status: trust.provenance.signedAt }])}<span class="badge ready">Valid Signature</span></section>
        <section class="opcb-card canary-panel"><b>Canary Status <em>Live</em></b><div class="canary-grid">${trust.canaries.map(item => `<button data-command="/canary status">${c().escapeHtml(item.label)}<em>${c().escapeHtml(item.status)}</em></button>`).join('')}</div><button class="ghost-button" data-opcb-refresh="trust">View Canary Details</button></section>
        <section class="opcb-card integrity-checks-panel"><b>Integrity Checks <em>Live</em></b><div class="integrity-checks-body">${c().ringMetric({ value: Math.round((trust.systemsHealthy / trust.systemsTotal) * 100), label: `${trust.systemsHealthy}/${trust.systemsTotal}` })}${c().gateList([{ label: 'Passed', status: trust.systemsHealthy }, { label: 'Warning', status: trust.warnings, tone: 'amber' }, { label: 'Failed', status: trust.failedChecks, tone: 'danger' }])}</div><button class="ghost-button" data-opcb-readiness>Run All Checks</button></section>
        <section class="opcb-card trust-controls-panel"><b>Trust Controls</b><div class="trust-control-grid">${['Evidence Verification', 'Agent Verification', 'Artifact Signing', 'Change Approvals', 'Policy Enforcement', 'Access Reviews'].map((label, index) => `<span>${c().escapeHtml(label)}<em>${index < 2 || index === 4 ? 'Enforced' : index === 5 ? 'Scheduled' : 'Required'}</em></span>`).join('')}</div></section>
        <section class="opcb-card attestations-panel"><b>Attestations</b><img src="${asset(3, 'attestation.svg')}" alt=""><div>${c().gateList([{ label: 'Attestation ID', status: 'att-9f2b7c4a' }, { label: 'Valid Until', status: '2025-05-24 15:31:05' }])}<em>Valid Attestation</em></div></section>
      </div>
    `;
  }

  function renderMemoryPage(state) {
    const host = document.querySelector('.opcb-dashboard[data-page-panel="memory"]');
    if (!host) return;
    const memory = state.memory;
    host.innerHTML = `
      <div class="opcb-section-head"><div><h2>Memory Observatory</h2><span>Recall graph, residue quality, and skill crystallization candidates.</span></div><span class="active-chip">Live</span></div>
      <div class="memory-observatory-deck">
        <section class="memory-cube-panel">
          <img src="${asset(5, 'memory-cube-hero.svg')}" alt="">
          <div><h3>${memory.recallHealth}%</h3><span>Recall Health</span></div>
          <p>${memory.records} records · ${memory.evidenceItems} evidence residues · ${memory.freshness}% freshness</p>
        </section>
        <section class="memory-recall-graph">
          <b>Recall Constellation</b>
          <div class="memory-starfield">
            <span style="--x:18%;--y:34%">Mission</span><span style="--x:42%;--y:18%">Evidence</span><span style="--x:66%;--y:34%">Review</span><span style="--x:34%;--y:70%">Routes</span><span style="--x:78%;--y:72%">Skills</span><span style="--x:52%;--y:50%">Residue</span>
          </div>
        </section>
        <section class="memory-metric-stack">
          ${c().metricCard({ label: 'Mission Memory', value: memory.records, sublabel: 'Trace-linked records', tone: 'cyan', icon: asset(5, 'memory-archive.svg') })}
          ${c().metricCard({ label: 'Evidence Residue', value: memory.evidenceItems, sublabel: 'Validated proof objects', tone: 'teal', icon: asset(5, 'residue-quality.svg') })}
          ${c().metricCard({ label: 'Freshness', value: `${memory.freshness}%`, sublabel: 'Decay under threshold', tone: 'violet', icon: asset(5, 'memory-freshness.svg') })}
        </section>
        <section class="memory-skill-panel"><b>Skill Candidates</b>${c().gateList([{ label: 'Parser heuristics', status: 'Promote' }, { label: 'Review gate recipe', status: 'Candidate' }, { label: 'Trace resolver', status: 'Candidate' }, { label: 'Map orphan detector', status: 'New' }])}<button class="ghost-button" data-command="/promote skill">Promote Skill</button></section>
        <section class="memory-event-panel"><b>Recent Memory Events</b>${c().eventLedger(memory.events)}</section>
      </div>
    `;
  }

  function renderMapPage(state) {
    const host = document.querySelector('.opcb-dashboard[data-page-panel="map"]');
    if (!host) return;
    const graph = state.graph;
    const ui = state.ui || {};
    const filteredNodes = ui.mapFilter && !['all', 'filters'].includes(ui.mapFilter)
      ? graph.nodes.filter(node => node.type === ui.mapFilter)
      : graph.nodes;
    const visibleIds = new Set(filteredNodes.map(node => node.id));
    const visibleEdges = graph.edges.filter(edge => visibleIds.has(edge.from) && visibleIds.has(edge.to));
    const nodesById = Object.fromEntries(filteredNodes.map(node => [node.id, node]));
    host.innerHTML = `
      <div class="opcb-section-head"><div><h2>Mission Map</h2><span>Code Graph · Mission Topology · Dependencies</span></div><div class="opcb-toolbar"><button class="ghost-button" data-ide-action="code.symbol_search">Search nodes, files, symbols...</button><button class="ghost-button ${!ui.mapFilter || ui.mapFilter === 'all' || ui.mapFilter === 'filters' ? 'active' : ''}" data-opcb-select="map-filter" data-id="all">All</button><button class="ghost-button ${ui.mapFilter === 'parser' ? 'active' : ''}" data-opcb-select="map-filter" data-id="parser">Parsers</button><button class="ghost-button ${ui.mapFilter === 'agent' ? 'active' : ''}" data-opcb-select="map-filter" data-id="agent">Agents</button><button class="ghost-button ${ui.mapGroup === 'type' ? 'active' : ''}" data-opcb-select="map-group" data-id="type">Group: Type</button><button class="ghost-button ${ui.mapLayout === 'force' ? 'active' : ''}" data-opcb-select="map-layout" data-id="force">Layout: Force</button><button class="ghost-button ${ui.mapCanvas === 'fit' ? 'active' : ''}" data-opcb-select="map-canvas" data-id="fit">Fit</button></div></div>
      <div class="graph-shell">
        <aside class="graph-legend">
          ${['entry', 'parser', 'detector', 'db', 'agent', 'external'].map(type => `<span><img class="opcb-asset-icon" src="${asset(5, type === 'db' ? 'graph-node-store.svg' : `graph-node-${type}.svg`)}" alt="">${type}</span>`).join('')}
          <hr>
          <span class="edge-swatch calls">Calls</span><span class="edge-swatch depends">Depends</span><span class="edge-swatch produces">Produces</span>
        </aside>
        <div class="graph-canvas">
          <svg class="graph-edges" viewBox="0 0 100 100" preserveAspectRatio="none">
            ${visibleEdges.map(edge => {
              const from = nodesById[edge.from];
              const to = nodesById[edge.to];
              if (!from || !to) return '';
              return `<line class="graph-edge edge-${edge.type}" x1="${from.x}" y1="${from.y}" x2="${to.x}" y2="${to.y}"></line>`;
            }).join('')}
          </svg>
          ${filteredNodes.map(node => `
            <button class="graph-node ${node.type} ${graph.selected === node.id ? 'selected' : ''}" data-graph-node="${c().escapeHtml(node.id)}" style="--x:${node.x}%;--y:${node.y}%">
              <img class="opcb-asset-icon" src="${asset(5, node.type === 'db' ? 'graph-node-store.svg' : `graph-node-${node.type}.svg`)}" alt="">
              <strong>${c().escapeHtml(node.label)}</strong><span>${c().escapeHtml(node.sub)}</span><em>${node.id === graph.selected ? '3m ago' : node.type === 'external' ? 'v2.7.0' : '5m ago'}</em>
            </button>
          `).join('')}
        </div>
      </div>
    `;
  }

  function renderDoctorPage(state) {
    const host = document.querySelector('.opcb-dashboard[data-page-panel="doctor"]')
      || document.querySelector('[data-page-panel="doctor"]');
    if (!host) return;
    const doctor = state.gatewayDoctor || {};
    const readiness = state.readiness || {};
    const routes = Array.isArray(doctor.routes) ? doctor.routes : [];
    const actionChecks = readiness.actions?.checks || [];
    const selectedRoute = routes.find(route => route.id === state.ui?.gatewayRoute)
      || routes.find(route => route.required !== false && !route.ok)
      || routes.find(route => !route.ok)
      || routes[0];
    host.className = 'opcb-dashboard page-panel';
    host.innerHTML = `
      <div class="opcb-section-head">
        <div><h2>Gateway Doctor</h2><span>Route contract, process health, and OPCB live-data readiness.</span></div>
        <div class="opcb-toolbar">
          <button class="ghost-button" data-opcb-readiness>Run Readiness</button>
          <button class="ghost-button" data-opcb-recheck-gateway>Recheck Routes</button>
          <button class="ghost-button warn" data-opcb-restart-gateway>Restart Gateway</button>
        </div>
      </div>
      <div class="doctor-grid">
        <section class="opcb-card readiness-summary-card">
          <b>Full Readiness</b>
          <div class="metric-strip compact">
            <div class="hero-metric ${readiness.score >= 80 ? '' : 'amber'}"><span>${readiness.score || 0}%</span><b>${c().escapeHtml(readiness.status || 'Not Checked')}</b></div>
            <div class="hero-metric"><span>${readiness.actions?.passed || 0}/${readiness.actions?.total || 0}</span><b>Critical Actions</b></div>
            <div class="hero-metric ${readiness.release?.ok ? '' : 'amber'}"><span>${readiness.release ? (readiness.release.ok ? 'Pass' : 'Warn') : 'Skip'}</span><b>Release Probe</b></div>
          </div>
          ${c().gateList([
            { label: 'Checked', status: readiness.checkedAt || 'not checked' },
            { label: 'Route Contract', status: `${readiness.routes?.passed || 0}/${readiness.routes?.total || 0}` },
            { label: 'Release Source', status: readiness.release?.source || 'not run' },
            { label: 'Release Checks', status: readiness.release ? `${readiness.release.passed}/${readiness.release.checks}` : 'not run' }
          ])}
          <button class="ghost-button" data-opcb-readiness>Run Full Readiness Check</button>
        </section>
        <section class="opcb-card gateway-summary-card">
          <b>Gateway Contract</b>
          <div class="metric-strip compact">
            <div class="hero-metric ${doctor.ok ? '' : 'amber'}"><span>${doctor.ok ? 'Online' : 'Attention'}</span><b>Status</b></div>
            <div class="hero-metric"><span>${doctor.passed || 0}/${doctor.total || 0}</span><b>Required Routes</b></div>
            <div class="hero-metric"><span>${c().escapeHtml(doctor.checkedAt || 'not checked')}</span><b>Checked</b></div>
          </div>
          ${c().gateList([
            { label: 'Gateway URL', status: doctor.url || 'unknown' },
            { label: 'Probe Mode', status: doctor.mode || 'contract_probe' },
            { label: 'Process ID', status: doctor.pid || 'unknown' },
            { label: 'Port', status: doctor.port || 'unknown' },
            { label: 'Local Mode', status: doctor.localMode ? 'Enabled' : 'No' }
          ])}
        </section>
        <section class="opcb-card route-contract-card">
          <b>Gateway Route Contract</b>
          <div class="doctor-route-list">
            ${routes.length ? routes.map(route => `
              <button class="doctor-route-row ${route.ok ? 'ok' : route.required === false ? 'warn' : 'fail'} ${selectedRoute?.id === route.id ? 'selected' : ''}" data-opcb-select="gateway-route" data-id="${c().escapeHtml(route.id)}">
                <span>${c().escapeHtml(route.id)}${route.required === false ? '<small>optional</small>' : ''}</span>
                <code>${c().escapeHtml(route.path)}</code>
                <em>${route.ok ? 'OK' : c().escapeHtml(route.error || 'Failed')}</em>
              </button>
            `).join('') : '<div class="status-box muted">No route contract has been checked yet.</div>'}
          </div>
        </section>
        <section class="opcb-card readiness-blockers-card">
          <b>Readiness Blockers</b>
          ${readiness.blockers?.length ? c().gateList(readiness.blockers.map(item => ({ label: item, status: 'Blocked', tone: 'amber' }))) : '<div class="status-box ready">No blockers recorded.</div>'}
        </section>
        <section class="opcb-card selected-route-card">
          <b>Selected Route</b>
          ${selectedRoute ? c().gateList([
            { label: 'Route ID', status: selectedRoute.id },
            { label: 'Path', status: selectedRoute.path },
            { label: 'Contract', status: selectedRoute.required === false ? 'Optional' : 'Required' },
            { label: 'State', status: selectedRoute.ok ? 'OK' : 'Fail', tone: selectedRoute.ok ? 'teal' : 'amber' },
            { label: 'Error', status: selectedRoute.error || 'none' }
          ]) : '<div class="status-box muted">Select a route to inspect it.</div>'}
        </section>
        <section class="opcb-card readiness-actions-card">
          <b>Critical Action Contract</b>
          ${actionChecks.length ? c().gateList(actionChecks.map(item => ({ label: item.id, status: item.ready ? 'Ready' : item.reason, tone: item.ready ? 'teal' : 'amber' }))) : '<div class="status-box muted">Run readiness to inspect critical actions.</div>'}
        </section>
        <section class="opcb-card gateway-actions-card">
          <b>Recovery Actions</b>
          <div class="crystal-action-row">
            <button data-opcb-readiness>Readiness<span>Probe route, actions, release</span></button>
            <button data-opcb-recheck-gateway>Recheck<span>Probe all OPCB routes</span></button>
            <button data-opcb-restart-gateway>Restart<span>Restart gateway and recheck</span></button>
            <button data-ide-action="doctor.copy_report">Copy Report<span>Copy current diagnostics</span></button>
          </div>
        </section>
        <section class="opcb-card gateway-ledger-card">
          <b>Action Ledger</b>
          ${c().eventLedger((state.actionLedger || []).slice(0, 8).map(item => ({ time: item.at || '', label: `${item.label || item.id} · ${item.status || 'started'}` })))}
        </section>
      </div>
    `;
  }

  window.opcbRenderPage = function opcbRenderPage(page, state) {
    if (page === 'workspace') renderWorkspacePage(state);
    if (page === 'mission') renderMissionPage(state);
    if (page === 'models') renderModelsPage(state);
    if (page === 'agents') renderAgentsPage(state);
    if (page === 'review') renderReviewPage(state);
    if (page === 'evidence') renderEvidencePage(state);
    if (page === 'crystallization') renderCrystallizationPage(state);
    if (page === 'trust') renderTrustPage(state);
    if (page === 'memory') renderMemoryPage(state);
    if (page === 'map') renderMapPage(state);
    if (page === 'doctor') renderDoctorPage(state);
  };

  document.addEventListener('click', event => {
    const row = event.target.closest('[data-evidence-id]');
    if (row && window.opcbState?.evidence) {
      window.opcbState.evidence.selectedId = row.dataset.evidenceId;
      renderEvidencePage(window.opcbState);
      window.opcbApplyPage?.('evidence');
      return;
    }
    const reviewAction = event.target.closest('[data-review-action]');
    if (reviewAction) {
      window.opcbRunCommand?.(`/review ${reviewAction.dataset.reviewAction}`);
      return;
    }
    const pageTarget = event.target.closest('[data-page-target]');
    if (pageTarget) {
      window.setDesktopPage?.(pageTarget.dataset.pageTarget);
      return;
    }
    const agent = event.target.closest('[data-agent-id]');
    if (agent && window.opcbState) {
      window.opcbState.selectedAgentId = agent.dataset.agentId;
      window.opcbRunCommand?.(`/agent inspect ${agent.dataset.agentId}`);
      return;
    }
    const candidate = event.target.closest('[data-crystal-candidate]');
    if (candidate && window.opcbState?.crystal) {
      window.opcbState.crystal.selectedCandidate = candidate.dataset.crystalCandidate;
      renderCrystallizationPage(window.opcbState);
      window.opcbApplyPage?.('crystallization');
      return;
    }
    const graphNode = event.target.closest('[data-graph-node]');
    if (graphNode && window.opcbState?.graph) {
      window.opcbState.graph.selected = graphNode.dataset.graphNode;
      renderMapPage(window.opcbState);
      window.opcbApplyPage?.('map');
    }
  });
})();
