(function () {
  const dashboardPages = new Set([
    'workspace',
    'mission',
    'models',
    'agents',
    'review',
    'evidence',
    'trust',
    'memory',
    'map',
    'crystallization',
    'doctor'
  ]);

  const asset = (phase, file) => `assets/opcb/phase${phase}/svg/${file}`;

  const pageArt = {
    workspace: ['phase1', 'workspace-flow-canvas-bg.svg'],
    mission: ['phase1', 'mission-overview-bg.svg'],
    review: ['phase2', 'review-center-bg.svg'],
    evidence: ['phase2', 'evidence-library-bg.svg'],
    crystallization: ['phase3', 'crystallization-bg.svg'],
    trust: ['phase3', 'trust-posture-bg.svg'],
    models: ['phase4', 'models-page-bg.svg'],
    agents: ['phase4', 'agents-page-bg.svg'],
    map: ['phase5', 'map-page-bg.svg'],
    memory: ['phase5', 'memory-page-bg.svg'],
    doctor: ['phase6', 'doctor-page-bg.svg']
  };

  const pagePulse = {
    workspace: asset(1, 'cube-pulse-workspace.svg'),
    mission: asset(1, 'cube-pulse-mission.svg'),
    review: asset(2, 'cube-pulse-review.svg'),
    evidence: asset(2, 'cube-pulse-evidence.svg'),
    crystallization: asset(3, 'cube-pulse-crystal.svg'),
    trust: asset(3, 'cube-pulse-trust.svg'),
    models: asset(4, 'cube-pulse-models.svg'),
    agents: asset(4, 'cube-pulse-agents.svg'),
    map: asset(5, 'cube-pulse-map.svg'),
    memory: asset(5, 'cube-pulse-memory.svg'),
    terminal: asset(6, 'cube-pulse-terminal.svg'),
    providers: asset(6, 'cube-pulse-providers.svg'),
    tooling: asset(6, 'cube-pulse-tooling.svg'),
    doctor: asset(6, 'cube-pulse-doctor.svg'),
    settings: asset(6, 'cube-pulse-settings.svg')
  };

  const spriteBase = 'assets/sprites';

  const pageIcon = {
    workspace: asset(1, 'workspace-flow.svg'),
    mission: asset(1, 'mission-target.svg'),
    review: asset(2, 'review-center.svg'),
    evidence: asset(2, 'evidence-library.svg'),
    crystallization: asset(3, 'crystal-chamber.svg'),
    trust: asset(3, 'trust-shield.svg'),
    models: asset(4, 'models-route.svg'),
    agents: asset(4, 'agents-squad.svg'),
    map: asset(5, 'map-canvas.svg'),
    memory: asset(5, 'memory-observatory.svg'),
    doctor: asset(6, 'doctor-shield.svg')
  };

  const labelIcons = [
    [/mission brief|mission$/i, asset(1, 'mission-target.svg')],
    [/objective|target/i, asset(1, 'approval-gate.svg')],
    [/scope|toolbelt|tools/i, asset(1, 'tools-crossed.svg')],
    [/model|route|fallback/i, asset(4, 'models-route.svg')],
    [/agent|squad|planner|analyst|profiler|verifier/i, asset(4, 'agents-squad.svg')],
    [/review|gate|quality/i, asset(2, 'quality-gate.svg')],
    [/contradiction/i, asset(2, 'contradiction-alert.svg')],
    [/risk|blocker/i, asset(2, 'risk-blocker.svg')],
    [/diff/i, asset(2, 'diff-review.svg')],
    [/test/i, asset(2, 'test-summary.svg')],
    [/evidence|parser_requirements|selected/i, asset(2, 'selected-evidence.svg')],
    [/schema|valid/i, asset(2, 'schema-valid.svg')],
    [/trace/i, asset(2, 'trace-link.svg')],
    [/audit|pack/i, asset(2, 'audit-pack.svg')],
    [/crystal|crystallization/i, asset(3, 'crystal-ready.svg')],
    [/candidate/i, asset(3, 'crystal-candidate.svg')],
    [/integrity|checks/i, asset(3, 'integrity-check.svg')],
    [/policy|guardrail/i, asset(3, 'policy-guardrail.svg')],
    [/boundary|local/i, asset(3, 'local-first.svg')],
    [/trust|secure/i, asset(3, 'trust-posture.svg')],
    [/memory|recall/i, asset(5, 'memory-archive.svg')],
    [/freshness/i, asset(5, 'memory-freshness.svg')],
    [/handoff/i, asset(4, 'handoff-queue.svg')],
    [/runtime/i, asset(4, 'runtime-ready.svg')],
    [/hardware|gpu/i, asset(4, 'hardware-chip.svg')]
  ];

  const fileIcons = {
    md: asset(2, 'file-md.svg'),
    json: asset(2, 'file-json.svg'),
    csv: asset(2, 'file-csv.svg'),
    html: asset(2, 'file-html.svg'),
    yaml: asset(2, 'file-yaml.svg'),
    zip: asset(2, 'file-zip.svg'),
    log: asset(2, 'file-log.svg'),
    db: asset(2, 'file-db.svg'),
    pcap: asset(2, 'file-pcap.svg'),
    ndjson: asset(2, 'file-ndjson.svg')
  };

  const graphIcons = {
    entry: asset(5, 'graph-node-entry.svg'),
    parser: asset(5, 'graph-node-parser.svg'),
    detector: asset(5, 'graph-node-detector.svg'),
    db: asset(5, 'graph-node-store.svg'),
    agent: asset(5, 'graph-node-agent.svg'),
    external: asset(5, 'graph-node-external.svg')
  };

  window.opcbState = window.opcbState || {
    mission: {
      id: 'M-2025-05-24-0017',
      title: 'Use Code Graph and Profiler to plan local evidence parser',
      owner: 'You',
      updated: '2m ago',
      status: 'In Progress',
      progress: 68,
      health: 82,
      risk: 'Medium',
      confidence: 'High',
      nextAction: {
        title: 'Run Profiler on Target Module',
        impact: 'High Impact',
        eta: '~18 min',
        reason: 'Profiler data reduces a key evidence gap and unlocks downstream review gates.'
      },
      metrics: { artifacts: 12, checks: 28, traces: 184, evidenceItems: 96 },
      timeline: { elapsed: '00:28:11', remaining: '02:01:49', eta: '1h 33m' },
      path: [
        { id: 'mission', number: 1, label: 'Mission', status: 'Complete', tone: 'teal' },
        { id: 'models', number: 2, label: 'Models', status: 'Complete', tone: 'teal' },
        { id: 'agents', number: 3, label: 'Agents', status: 'Complete', tone: 'violet' },
        { id: 'workspace', number: 4, label: 'Tools', status: 'Complete', tone: 'cyan' },
        { id: 'review', number: 5, label: 'Review', status: 'In Progress', tone: 'amber' },
        { id: 'evidence', number: 6, label: 'Evidence', status: 'Pending', tone: 'blue' },
        { id: 'crystallization', number: 7, label: 'Crystallization', status: 'Pending', tone: 'amber' }
      ]
    },
    route: {
      active: 'deepseek-coder:6.7b',
      fallback: ['mistral-nemo:12b', 'qwen2.5-coder:7b'],
      policy: 'Local First',
      cloud: 'Blocked',
      confidence: 94.7,
      latency: '1.24s',
      throughput: '14.2 tok/s',
      reason: 'Best quality for code graph',
      hardware: 'RTX 4090 · 24GB',
      runtime: 'Healthy · 8m 42s uptime',
      models: [
        { id: 'deepseek-coder:6.7b', role: 'Primary', confidence: 94.7, latency: '1.24s', speed: '14.2 tok/s', size: '24.1 GB' },
        { id: 'mistral-nemo:12b', role: 'Fallback', confidence: 83.1, latency: '1.98s', speed: '11.0 tok/s', size: '23.3 GB' },
        { id: 'qwen2.5-coder:7b', role: 'Fallback', confidence: 68.4, latency: '2.31s', speed: '9.3 tok/s', size: '14.3 GB' }
      ],
      runtimes: [
        { label: 'Ollama v0.4.3', status: 'Running · Healthy' },
        { label: 'LM Studio v0.3.7', status: 'Running · Healthy' },
        { label: 'llama.cpp b5123', status: 'Ready · Optimized' },
        { label: 'ExllamaV2 v0.2.8', status: 'Ready · Optimized' }
      ]
    },
    review: {
      confidence: 87,
      evidenceSufficiency: 82,
      risks: 2,
      contradictions: 1,
      gatesPassed: 4,
      gatesTotal: 5,
      gates: [
        { label: 'Plan Validity', status: 'Passed' },
        { label: 'Evidence Sufficiency', status: 'Passed' },
        { label: 'Parser Robustness', status: 'Passed' },
        { label: 'Risk Assessment', status: 'Passed' },
        { label: 'Operational Readiness', status: 'Needs Approval', tone: 'amber' }
      ],
      risksList: [
        { id: 'R-007', level: 'blocker', label: 'Missing performance benchmark for large file parsing' },
        { id: 'R-013', level: 'high', label: 'No rollback plan for schema migration changes' }
      ],
      contradictionsList: [
        { id: 'C-001', severity: 'high', label: 'Mismatch between parser error handling in design docs and implementation notes' }
      ]
    },
    evidence: {
      selected: 7,
      total: 25,
      selectedId: 'parser_requirements',
      validity: 96,
      warnings: 1,
      errors: 0,
      files: [
        { id: 'parser_requirements', name: 'parser_requirements.md', type: 'Markdown', ext: 'md', size: '2.4 KB', confidence: 98, status: 'Verified' },
        { id: 'parser_design', name: 'parser_design.json', type: 'JSON', ext: 'json', size: '18.7 KB', confidence: 96, status: 'Verified' },
        { id: 'benchmark_results', name: 'benchmark_results.csv', type: 'CSV', ext: 'csv', size: '12.1 KB', confidence: 93, status: 'Verified' },
        { id: 'validation_report', name: 'validation_report.html', type: 'HTML', ext: 'html', size: '34.9 KB', confidence: 95, status: 'Verified' },
        { id: 'api_contract', name: 'api_contract.yaml', type: 'YAML', ext: 'yaml', size: '6.8 KB', confidence: 91, status: 'Verified' }
      ],
      traceLinks: [
        { label: 'parser_design.json', status: 'Spec' },
        { label: 'validation_report.html', status: 'Validation' },
        { label: 'api_contract.yaml', status: 'Contract' },
        { label: 'benchmark_results.csv', status: 'Results' }
      ]
    },
    crystal: {
      readiness: 94,
      candidates: 7,
      gatesPassed: 6,
      gatesTotal: 6,
      immutable: true,
      selectedCandidate: 'local-evidence-parser',
      candidateList: [
        { id: 'local-evidence-parser', label: 'Local evidence parser', value: 'Highest Value', ready: 94, domain: 'Evidence · Code Graph' },
        { id: 'profiler-agent', label: 'Profiler agent integration', value: 'High Value', ready: 91, domain: 'Agent · Orchestration' },
        { id: 'decision-trace', label: 'Decision trace analyzer', value: 'High Value', ready: 88, domain: 'Review · Trace' },
        { id: 'memory-integrity', label: 'Memory integrity verifier', value: 'Medium', ready: 72, domain: 'Trust · Verification' }
      ],
      gates: [
        { label: 'Evidence Integrity', status: 'Passed' },
        { label: 'Graph Consistency', status: 'Passed' },
        { label: 'Trace Completeness', status: 'Passed' },
        { label: 'Agent Validation', status: 'Passed' },
        { label: 'Risk Assessment', status: 'Passed' }
      ],
      events: [
        { time: '14:32', label: 'Candidate selected' },
        { time: '14:31', label: 'Quality gates passed' },
        { time: '14:30', label: 'Evidence linked' },
        { time: '14:29', label: 'Candidate queued' }
      ]
    },
    trust: {
      score: 91,
      systemsHealthy: 28,
      systemsTotal: 31,
      failedChecks: 1,
      warnings: 2,
      boundary: 'Local-First',
      integrity: 'Verified',
      guardrails: 'Enforced',
      provenance: { rootId: 'c3b7e2f0...9a17d2e1', algorithm: 'SHA-256', signedBy: 'You', signedAt: '2025-05-24 14:31:05' },
      canaries: [
        { label: 'File Canary', status: 'Healthy' },
        { label: 'Network Canary', status: 'Healthy' },
        { label: 'Agent Canary', status: 'Healthy' }
      ],
      timeline: [
        { time: '14:32', label: 'Policy guardrail checked' },
        { time: '14:31', label: 'Evidence verified' },
        { time: '14:31', label: 'Agent signed event' },
        { time: '14:30', label: 'Trust posture recalculated' }
      ]
    },
    memory: {
      records: 184,
      evidenceItems: 96,
      recallHealth: 92,
      freshness: 88,
      compactionQueue: 12,
      skillCandidates: 5,
      residueQuality: 94,
      events: [
        { time: '14:32', label: 'Evidence parser plan updated' },
        { time: '14:28', label: 'Review gate outcome stored' },
        { time: '14:24', label: 'Model route snapshot retained' },
        { time: '14:19', label: 'Skill candidate promoted' }
      ]
    },
    actionLedger: [
      { at: 'ready', label: 'OPCB control contract loaded', status: 'ready', page: 'workspace' }
    ],
    graph: {
      health: 92,
      selected: 'evidence_parser.py',
      coverage: 94,
      orphaned: 2,
      nodes: [
        { id: 'main.py', type: 'entry', x: 48, y: 10, label: 'main.py', sub: 'Entry Point' },
        { id: 'code_graph.py', type: 'agent', x: 22, y: 30, label: 'code_graph.py', sub: 'Module' },
        { id: 'parser.py', type: 'parser', x: 34, y: 24, label: 'parser.py', sub: 'Parser' },
        { id: 'evidence_parser.py', type: 'parser', x: 50, y: 28, label: 'evidence_parser.py', sub: 'Parser' },
        { id: 'profiling_parser.py', type: 'parser', x: 66, y: 24, label: 'profiling_parser.py', sub: 'Parser' },
        { id: 'profiler.py', type: 'agent', x: 76, y: 33, label: 'profiler.py', sub: 'Module' },
        { id: 'anomaly_detector.py', type: 'detector', x: 36, y: 48, label: 'anomaly_detector.py', sub: 'Detector' },
        { id: 'pattern_detector.py', type: 'detector', x: 66, y: 48, label: 'pattern_detector.py', sub: 'Detector' },
        { id: 'schema_validator.py', type: 'entry', x: 28, y: 61, label: 'schema_validator.py', sub: 'Validator' },
        { id: 'evidence_validator.py', type: 'entry', x: 76, y: 61, label: 'evidence_validator.py', sub: 'Validator' },
        { id: 'evidence_index.db', type: 'db', x: 52, y: 50, label: 'evidence_index.db', sub: 'Store' },
        { id: 'evidence_agent', type: 'agent', x: 52, y: 68, label: 'evidence_agent', sub: 'Online' },
        { id: 'graph_builder.py', type: 'agent', x: 34, y: 82, label: 'graph_builder.py', sub: 'Module' },
        { id: 'dependency_resolver.py', type: 'agent', x: 52, y: 82, label: 'dependency_resolver.py', sub: 'Module' },
        { id: 'link_analyzer.py', type: 'agent', x: 68, y: 82, label: 'link_analyzer.py', sub: 'Module' },
        { id: 'README.md', type: 'external', x: 28, y: 93, label: 'README.md', sub: 'Doc' },
        { id: 'config.yaml', type: 'detector', x: 44, y: 93, label: 'config.yaml', sub: 'Config' },
        { id: 'tests', type: 'entry', x: 60, y: 93, label: 'tests/', sub: 'Tests' },
        { id: 'networkx', type: 'external', x: 86, y: 28, label: 'networkx', sub: 'External' },
        { id: 'pydantic', type: 'external', x: 86, y: 46, label: 'pydantic', sub: 'External' },
        { id: 'sqlite3', type: 'external', x: 86, y: 64, label: 'sqlite3', sub: 'External' }
      ],
      edges: [
        { from: 'main.py', to: 'evidence_parser.py', type: 'calls' },
        { from: 'main.py', to: 'code_graph.py', type: 'calls' },
        { from: 'main.py', to: 'profiler.py', type: 'calls' },
        { from: 'parser.py', to: 'evidence_parser.py', type: 'imports' },
        { from: 'evidence_parser.py', to: 'profiling_parser.py', type: 'imports' },
        { from: 'evidence_parser.py', to: 'evidence_index.db', type: 'produces' },
        { from: 'anomaly_detector.py', to: 'evidence_index.db', type: 'depends' },
        { from: 'pattern_detector.py', to: 'evidence_index.db', type: 'depends' },
        { from: 'schema_validator.py', to: 'anomaly_detector.py', type: 'depends' },
        { from: 'evidence_validator.py', to: 'pattern_detector.py', type: 'depends' },
        { from: 'evidence_agent', to: 'evidence_parser.py', type: 'calls' },
        { from: 'evidence_agent', to: 'graph_builder.py', type: 'calls' },
        { from: 'evidence_agent', to: 'dependency_resolver.py', type: 'calls' },
        { from: 'evidence_agent', to: 'link_analyzer.py', type: 'calls' },
        { from: 'graph_builder.py', to: 'README.md', type: 'produces' },
        { from: 'dependency_resolver.py', to: 'config.yaml', type: 'produces' },
        { from: 'link_analyzer.py', to: 'tests', type: 'produces' },
        { from: 'profiler.py', to: 'networkx', type: 'depends' },
        { from: 'evidence_parser.py', to: 'pydantic', type: 'depends' },
        { from: 'evidence_index.db', to: 'sqlite3', type: 'depends' }
      ]
    },
    agents: [
      { id: 'planner', label: 'Planner Agent', role: 'Mission Write', status: 'Online', confidence: 92, task: 'Prepare parser validation path', tools: ['Code Graph', 'Runbook', 'SourcePlan'] },
      { id: 'graph', label: 'Graph Analyst', role: 'Evidence Read', status: 'Approved', confidence: 89, task: 'Link evidence to graph nodes', tools: ['Code Graph', 'Trace Links', 'Evidence Parser'] },
      { id: 'profiler', label: 'Profiler Agent', role: 'Evidence Read', status: 'Online', confidence: 86, task: 'Capture target module hot paths', tools: ['Profiler', 'Runtime Logs', 'Benchmarks'] },
      { id: 'verifier', label: 'Verifier Agent', role: 'Verify Only', status: 'Pending', confidence: 84, task: 'Validate review gates', tools: ['Test Runner', 'Evidence Pack', 'Policy'] }
    ],
    gatewayDoctor: {
      ok: false,
      url: '',
      checkedAt: 'not checked',
      mode: 'contract_probe',
      pid: '',
      port: '',
      localMode: false,
      passed: 0,
      total: 0,
      routes: []
    },
    readiness: {
      score: 0,
      status: 'Not Checked',
      checkedAt: 'not checked',
      routes: { passed: 0, total: 0 },
      actions: { passed: 0, total: 0, checks: [] },
      release: null,
      blockers: []
    },
    ui: {
      workspaceCanvas: 'fit',
      mapFilter: 'all',
      mapGroup: 'type',
      mapLayout: 'force',
      mapCanvas: 'fit',
      gatewayRoute: ''
    }
  };

  const pageCommands = {
    workspace: ['/plan next', '/review gates', '/evidence list', '/graph analyze', '/crystallize preview'],
    mission: ['/plan next', '/review gates', '/evidence list', '/graph analyze', '/profiler run'],
    models: ['/test route', '/benchmark models', '/add fallback', '/model scan', '/route explain'],
    agents: ['/assign agent', '/agent status', '/handoff queue', '/tool bindings', '/memory access'],
    review: ['/review summary', '/show contradictions', '/show risks', '/diff changed', '/run tests'],
    evidence: ['/validate all', '/extract fields', '/find links', '/build pack', '/export'],
    crystallization: ['/crystallize now', '/verify candidate', '/show gates', '/export preview', '/open ledger'],
    trust: ['/verify integrity', '/trust report', '/view attestations', '/policy check', '/canary status'],
    map: ['/map focus', '/map paths', '/map impact', '/map orphans', '/map export png'],
    memory: ['/recall query', '/compact memory', '/promote skill', '/reuse suggestions', '/freshness'],
    doctor: ['/readiness check', '/gateway recheck', '/gateway restart', '/copy doctor', '/open gateway']
  };

  function img(src, className = 'opcb-asset-icon') {
    return `<img class="${className}" src="${src}" alt="">`;
  }

  function iconForLabel(text) {
    const found = labelIcons.find(([pattern]) => pattern.test(text || ''));
    return found ? found[1] : asset(1, 'workspace-flow.svg');
  }

  function railCard(title, body, action = '') {
    return window.opcbComponents.rightRailCard(title, body, action, iconForLabel(title));
  }

  function ringMetric(value, label, tone = 'teal') {
    return window.opcbComponents.ringMetric({ value, label, tone });
  }

  function rows(items) {
    return items.map(([label, value]) => `<div class="opcb-rail-row"><span>${label}</span><em>${value}</em></div>`).join('');
  }

  function ledger(events) {
    return window.opcbComponents.eventLedger(events.map(([time, label]) => ({ time, label })));
  }

  const railRenderers = {
    workspace: s => railPulse('workspace') + railCard('Local Model Route', rows([[s.route.active, 'Local'], [s.route.fallback[0], 'Fallback'], [s.route.fallback[1], 'Local']]), '<button class="opcb-rail-action" data-page-target="models">Manage Route</button>') +
      railCard('Sandbox Status', rows([['Sandbox', 'Secure'], ['CPU', '18%'], ['Memory', '42%'], ['Disk', '26%']]), '<button class="opcb-rail-action" data-page-target="terminal">Open Ledger</button>'),
    mission: s => railPulse('mission') + railCard('Mission Health', ringMetric(s.mission.health, 'Healthy') + rows([['Progress', `${s.mission.progress}%`], ['Confidence', s.mission.confidence], ['Risk', s.mission.risk], ['Blockers', '0']]), '<button class="opcb-rail-action" data-opcb-refresh="mission">View Health Details</button>') +
      railCard('Next Best Action', `<h4>${s.mission.nextAction.title}</h4><p>${s.mission.nextAction.reason}</p><div class="opcb-chipline"><span>${s.mission.nextAction.impact}</span><span>${s.mission.nextAction.eta}</span><span>Unblocked</span></div>`, '<button class="opcb-rail-action" data-ide-action="code.intel">Take Action</button>'),
    models: s => railPulse('models') + railCard('Hardware Profile', `<div class="hardware-profile-mini"><img src="${asset(4, 'hardware-profile.svg')}" alt=""><div><b>OPCB-DEV-01</b><span>Intel Core i9 · RTX 4090 · 64 GB RAM</span></div><em>Optimal</em></div>`) +
      railCard('System Utilization', `<div class="utilization-stack"><span style="--w:18">CPU <em>18%</em></span><span style="--w:42">RAM <em>42%</em></span><span style="--w:26">GPU <em>26%</em></span></div>`) +
      railCard('Readiness', rows([['Ollama Runtime', 'Running'], ['LM Studio Runtime', 'Running'], ['CUDA Acceleration', 'Available'], ['Disk Cache', 'Healthy'], ['Network', 'Offline (Policy)']])) +
      railCard('Local-First Policy', `<p>All inference requests resolve to local models. Cloud access is blocked.</p><span class="badge ready">Enforced</span>`, '<button class="opcb-rail-action" data-page-target="providers">Policy Settings</button>') +
      railCard('Recent Route Tests', ledger([['14:31', 'Primary route test passed'], ['14:28', 'Fallback simulation passed'], ['14:26', 'Latency guard test passed'], ['14:24', 'Context fit test passed']])),
    agents: s => railPulse('agents') + railCard('Permissions Overview', rows(s.agents.map(agent => [agent.label, agent.role])), '<button class="opcb-rail-action" data-page-target="trust">Manage Access</button>') +
      railCard('Agent Activity', ledger([['14:32', 'Planner updated mission'], ['14:31', 'Graph analyst linked evidence'], ['14:30', 'Verifier queued review']])),
    review: s => railPulse('review') + railCard('Approval State', `<div class="approval-state-card"><strong>Review in Progress</strong><span>Pending final approval</span><div><b>2<small>Blockers</small></b><b>3<small>Warnings</small></b><b>1/3<small>Approvers</small></b></div></div>`, '<button class="opcb-rail-action warn" data-ide-action="sourceplan.verify">Request Final Approval</button>') +
      railCard('Review Blockers', rows([['Contradiction detected in timestamp', 'High'], ['Missing evidence for edge case P-17', 'High']]), '<button class="opcb-rail-action" data-ide-action="evidence.search">View all blockers (2)</button>') +
      railCard('Approvers', rows([['Planner Agent', 'Pending'], ['Graph Analyst', 'Approved'], ['Verifier Agent', 'Pending']]), '<button class="opcb-rail-action" data-ide-action="tooling.mcp_ops">Manage Approvals</button>') +
      railCard('Review Notes', `<div class="review-note-card">Parser handles most formats well. Need evidence for timestamp normalization edge case and memory usage under large-file stress.<br><em>Graph Analyst · 14:31</em></div>`, '<button class="opcb-rail-action" data-page-target="agents">Add Note</button>'),
    evidence: s => railPulse('evidence') + railCard('Validation Summary', ringMetric(s.evidence.validity, 'Overall Validity') + rows([['Valid', '23'], ['Warnings', s.evidence.warnings], ['Errors', s.evidence.errors]]), '<button class="opcb-rail-action" data-opcb-refresh="evidence">Revalidate All</button>') +
      railCard('Export Evidence', `<div class="export-format-grid"><span>Markdown</span><span>JSON</span><span>HTML</span><span>DOCX</span><span>ZIP</span><span>CSV</span></div>${rows([['Trace links', 'Included'], ['Validation report', 'Included'], ['Schema details', 'Included'], ['Artifacts', 'Included']])}`, '<button class="opcb-rail-action" data-ide-action="sourceplan.export_runbook">Export Evidence</button>') +
      railCard('Audit Pack Readiness', rows([['Evidence Files', 'Ready'], ['Validation', 'Passed'], ['Traceability', 'Verified'], ['Artifacts', 'Ready']]), '<button class="opcb-rail-action" data-ide-action="sourceplan.handoff_package">Generate Audit Pack</button>'),
    crystallization: s => railPulse('crystallization') + railCard('Readiness', ringMetric(s.crystal.readiness, 'Exceptional', 'violet') + rows([['Candidates', s.crystal.candidates], ['Quality Gates', `${s.crystal.gatesPassed}/${s.crystal.gatesTotal}`], ['Immutable', s.crystal.immutable ? 'Enabled' : 'Pending']]), '<button class="opcb-rail-action" data-ide-action="sourceplan.propose_learning">Commit Crystal</button>') +
      railCard('Event Ledger', ledger([['14:32', 'Candidate selected'], ['14:31', 'Quality gates passed'], ['14:30', 'Evidence linked']])),
    trust: s => railPulse('trust') + railCard('Permissions Overview', rows([['You (Owner)', 'Full Control'], ['Planner Agent', 'Mission Write'], ['Graph Analyst', 'Evidence Read'], ['Profiler Agent', 'Evidence Read'], ['Verifier Agent', 'Verify Only']]), '<button class="opcb-rail-action" data-ide-action="tooling.mcp_ops">Manage Access</button>') +
      railCard('Audit Timeline', ledger([['14:32', 'Policy guardrail checked'], ['14:31', 'Evidence verified'], ['14:31', 'Agent signed event'], ['14:31', 'Integrity check passed'], ['14:30', 'Policy updated'], ['14:29', 'Trust posture recalculated']]), '<button class="opcb-rail-action" data-page-target="tooling">View Full Audit Log</button>'),
    memory: s => railPulse('memory') + railCard('Recall Health', ringMetric(s.memory.recallHealth, 'Fresh') + rows([['Records', s.memory.records], ['Evidence Items', s.memory.evidenceItems], ['Freshness', `${s.memory.freshness}%`], ['Compaction Queue', s.memory.compactionQueue]]), '<button class="opcb-rail-action" data-opcb-refresh="memory">Run Recall Query</button>') +
      railCard('Residue Quality', rows([['Source Linked', '96%'], ['Reusable', 'High'], ['Skill Candidates', '5']])),
    map: s => railPulse('map') + railCard('Map Health', ringMetric(s.graph.health, 'Excellent') + `<div class="map-health-spark"></div>` + rows([['Coverage', `${s.graph.coverage}%`], ['Freshness', '88%'], ['Consistency', '92%'], ['Test Coverage', '86%'], ['Orphaned Nodes', s.graph.orphaned]]), '<button class="opcb-rail-action" data-opcb-refresh="map">View Map Health</button>') +
      railCard('Selected Node', `<h4>${s.graph.selected}</h4><p>src/parsers/evidence_parser.py</p>${rows([['Type', 'Parser'], ['Language', 'Python'], ['Size', '12.4 KB'], ['Functions', '18'], ['Classes', '3'], ['Freshness', 'Fresh'], ['Coverage', '92%']])}`, '<button class="opcb-rail-action" data-ide-action="code.intel">View Dependencies</button>') +
      railCard('Dependencies', rows([['parser.py', 'src/parsers/parser.py'], ['schema_validator.py', 'src/validators/schema_validator.py'], ['evidence_index.db', 'data/evidence_index.db'], ['pydantic', 'v2.7.0 External']])),
    doctor: s => railPulse('doctor') + railCard('Gateway Contract', ringMetric(s.gatewayDoctor.total ? Math.round((s.gatewayDoctor.passed / s.gatewayDoctor.total) * 100) : 0, s.gatewayDoctor.ok ? 'Online' : 'Needs Attention', s.gatewayDoctor.ok ? 'teal' : 'amber') + rows([['URL', s.gatewayDoctor.url || 'unknown'], ['Checked', s.gatewayDoctor.checkedAt], ['Routes', `${s.gatewayDoctor.passed}/${s.gatewayDoctor.total}`], ['Mode', s.gatewayDoctor.mode]]), '<button class="opcb-rail-action" data-opcb-recheck-gateway>Recheck Routes</button>') +
      railCard('Process', rows([['PID', s.gatewayDoctor.pid || 'unknown'], ['Port', s.gatewayDoctor.port || 'unknown'], ['Local Mode', s.gatewayDoctor.localMode ? 'Yes' : 'No']]), '<button class="opcb-rail-action warn" data-opcb-restart-gateway>Restart Gateway</button>')
  };

  function railPulse(page) {
    const src = pagePulse[page] || pagePulse.mission;
    return railCard('Cube Pulse', `<div class="opcb-rail-pulse"><div><strong>Live</strong><div class="opcb-chipline"><span>${window.opcbState.mission.status}</span></div></div><img src="${src}" alt=""></div>`);
  }

  function renderRightRail(page) {
    const host = document.getElementById('opcbRightRail');
    if (!host) return;
    const renderer = railRenderers[page] || railRenderers.mission;
    const actionEvents = (window.opcbState.actionLedger || []).slice(0, 5).map(item => [
      item.at || '',
      `${item.label || item.id || 'Action'} · ${item.status || 'started'}`
    ]);
    const actionLedger = actionEvents.length
      ? railCard('Action Ledger', ledger(actionEvents), '<button class="opcb-rail-action" data-page-target="doctor">Open Gateway Doctor</button>')
      : '';
    host.innerHTML = renderer(window.opcbState) + actionLedger;
  }

  function renderCommandChips(page) {
    const host = document.querySelector('.command-chips');
    if (!host || !dashboardPages.has(page)) return;
    const commands = pageCommands[page] || pageCommands.mission;
    host.innerHTML = commands.map(command => `<span class="command-chip" data-command="${command}">${command}</span>`).join('') +
      '<span class="command-chip" data-command="/files">/files</span><span class="command-chip" data-command="/tooling">/tooling</span><span class="command-chip" data-command="/mcp">/mcp</span><span class="command-chip" data-command="/system">/system</span><span class="command-chip" data-command="/doctor">/doctor</span><span class="command-chip" id="commandChipRefresh">/refresh</span><span class="command-chip" id="commandChipPalette">/commands</span>';
  }

  function hasControlContract(button) {
    return button.hasAttribute('data-command') ||
      button.hasAttribute('data-ide-action') ||
      button.hasAttribute('data-opcb-refresh') ||
      button.hasAttribute('data-opcb-select') ||
      button.hasAttribute('data-page-target') ||
      button.hasAttribute('data-evidence-id') ||
      button.hasAttribute('data-review-action') ||
      button.hasAttribute('data-agent-id') ||
      button.hasAttribute('data-crystal-candidate') ||
      button.hasAttribute('data-graph-node') ||
      button.hasAttribute('data-opcb-recheck-gateway') ||
      button.hasAttribute('data-opcb-restart-gateway') ||
      button.hasAttribute('data-opcb-readiness') ||
      button.hasAttribute('data-prototype-reason');
  }

  function enforceOpcbControlContract(page) {
    const hosts = [
      document.querySelector(`.opcb-dashboard[data-page-panel="${page}"]`),
      document.getElementById('opcbRightRail')
    ].filter(Boolean);
    hosts.forEach(host => {
      host.querySelectorAll('button').forEach(button => {
        if (button.dataset.ideAction) {
          const reason = window.opcbActionBlockReason?.(button.dataset.ideAction) || '';
          if (reason) {
            button.dataset.liveBlockReason = reason;
            button.disabled = true;
            button.setAttribute('aria-disabled', 'true');
            button.title = reason;
          } else if (button.dataset.liveBlockReason) {
            delete button.dataset.liveBlockReason;
            button.disabled = false;
            button.removeAttribute('aria-disabled');
            button.title = '';
          }
          return;
        }
        if (hasControlContract(button)) return;
        const label = button.textContent.replace(/\s+/g, ' ').trim() || 'OPCB control';
        button.dataset.prototypeReason = `${label} still needs a live backend binding`;
        button.disabled = true;
        button.setAttribute('aria-disabled', 'true');
        button.title = button.dataset.prototypeReason;
      });
    });
  }

  function applyPageArt(page) {
    document.querySelectorAll('.opcb-page-art').forEach(el => el.remove());
    const host = document.querySelector(`.opcb-dashboard[data-page-panel="${page}"]`);
    if (!host || !pageArt[page]) return;
    const art = document.createElement('div');
    art.className = `opcb-page-art ${page}`;
    host.prepend(art);
  }

  function addIcon(target, src, className = 'opcb-asset-icon') {
    if (!target || target.querySelector(':scope > .opcb-injected-icon')) return;
    target.insertAdjacentHTML('afterbegin', `<img class="${className} opcb-injected-icon" src="${src}" alt="">`);
  }

  function injectVisibleIcons(page) {
    const host = document.querySelector(`.opcb-dashboard[data-page-panel="${page}"]`);
    if (!host) return;
    host.querySelectorAll('.opcb-injected-icon').forEach(icon => icon.remove());

    const head = host.querySelector('.opcb-section-head > div:first-child');
    const oldSymbol = head?.querySelector(':scope > .nav-icon, :scope > .dot-grid');
    if (oldSymbol) oldSymbol.style.display = 'none';
    if (head) addIcon(head, pageIcon[page] || asset(1, 'workspace-flow.svg'));

    host.querySelectorAll('.opcb-card > b, .hero-metric > b, .flow-node > strong, .candidate > b, .model-row > b, .agent-card > b').forEach(label => {
      addIcon(label, iconForLabel(label.textContent));
    });

    host.querySelectorAll('.evidence-row > b').forEach(label => {
      const name = label.textContent.trim().toLowerCase();
      const ext = name.split('.').pop();
      addIcon(label, fileIcons[ext] || asset(2, 'selected-evidence.svg'));
    });

    host.querySelectorAll('.graph-node').forEach(node => {
      const type = [...node.classList].find(cls => graphIcons[cls]);
      addIcon(node, graphIcons[type] || asset(5, 'map-canvas.svg'));
    });

    const crystal = host.querySelector('.crystal-chamber');
    if (crystal) crystal.classList.add('has-asset');
  }

  function applyPulse(page) {
    const pulse = document.getElementById('cubePulse');
    const wrap = pulse?.closest('.cube-pulse-wrap');
    if (!pulse || !wrap) return;
    const src = pagePulse[page] || pagePulse.mission;
    pulse.innerHTML = `<img class="opcb-cube-asset" src="${src}" alt="Cube Pulse">`;
    wrap.classList.add('has-opcb-asset');
  }

  function applyMascot(page) {
    const container = document.getElementById('spriteContainer');
    if (!container) return;
    const state = page === 'review' ? 'alert' : page === 'crystallization' ? 'finished' : page === 'workspace' ? 'working' : 'idle';
    const frames = Array.from({ length: 10 }, (_, index) => {
      const suffix = String(index).padStart(2, '0');
      return `<img class="sprite-frame${index === 0 ? ' active' : ''}" src="${spriteBase}/${state}/frame_${suffix}.png" alt="BEAST">`;
    }).join('');
    container.innerHTML = frames;
    container.dataset.spriteState = state;
    container.dataset.spriteIndex = '0';
    const mascot = document.getElementById('brandMascot');
    const dot = document.getElementById('spriteStateDot');
    if (mascot) mascot.dataset.state = state;
    if (dot) dot.dataset.state = state;
  }

  function startSpriteAnimator() {
    if (window.__opcbSpriteAnimator) return;
    window.__opcbSpriteAnimator = window.setInterval(() => {
      const container = document.getElementById('spriteContainer');
      if (!container) return;
      const frames = Array.from(container.querySelectorAll('.sprite-frame'));
      if (frames.length <= 1) return;
      const current = Number(container.dataset.spriteIndex || 0);
      const next = (current + 1) % frames.length;
      frames[current]?.classList.remove('active');
      frames[next]?.classList.add('active');
      container.dataset.spriteIndex = String(next);
    }, 130);
  }

  function updateMissionHeader() {
    const title = document.getElementById('missionTitle');
    if (title) title.textContent = window.opcbState.mission.title;
  }

  const commandActionMap = new Map([
    ['/refresh', 'mission.refresh_snapshot'],
    ['/commands', 'tooling.refresh'],
    ['/assign agent', 'agents.create'],
    ['/evidence list', 'evidence.search'],
    ['/evidence validate', 'evidence.search'],
    ['/evidence pack', 'sourceplan.handoff_package'],
    ['/evidence add', 'evidence.search'],
    ['/export markdown', 'sourceplan.export_runbook'],
    ['/find links', 'evidence.search'],
    ['/build pack', 'sourceplan.handoff_package'],
    ['/trace graph', 'code.intel'],
    ['/graph analyze', 'code.intel'],
    ['/map export png', 'sourceplan.export_runbook'],
    ['/map orphans', 'code.intel'],
    ['/route test', 'providers.refresh'],
    ['/benchmark models', 'providers.smoke_nvidia'],
    ['/model scan', 'providers.refresh'],
    ['/runtime status', 'providers.refresh'],
    ['/verify candidate', 'settings.release_readiness'],
    ['/crystallize now', 'sourceplan.propose_learning'],
    ['/seal artifact', 'sourceplan.propose_learning'],
    ['/export preview', 'sourceplan.export_runbook'],
    ['/verify integrity', 'settings.release_readiness'],
    ['/policy check', 'settings.release_readiness'],
    ['/trust report', 'settings.release_readiness'],
    ['/view attestations', 'settings.release_readiness'],
    ['/canary status', 'settings.release_readiness'],
    ['/show gates', 'settings.release_readiness'],
    ['/open ledger', 'tooling.refresh'],
    ['/add fallback', 'providers.refresh'],
    ['/route explain', 'providers.refresh'],
    ['/agent status', 'agents.create'],
    ['/handoff queue', 'agents.output_to_sourceplan'],
    ['/tool bindings', 'tooling.refresh'],
    ['/memory access', 'tooling.mcp_ops'],
    ['/promote skill', 'sourceplan.propose_learning'],
    ['/recall query', 'sourceplan.propose_learning'],
    ['/compact memory', 'settings.release_readiness'],
    ['/reuse suggestions', 'sourceplan.propose_learning'],
    ['/freshness', 'settings.release_readiness'],
    ['/copy doctor', 'doctor.copy_report'],
    ['/tooling', 'tooling.refresh'],
    ['/tools', 'tooling.refresh'],
    ['/mcp', 'tooling.mcp'],
    ['/mcp ops', 'tooling.mcp_ops'],
    ['/system', 'system.refresh'],
    ['/ports', 'system.ports'],
    ['/processes', 'system.processes'],
  ]);

  function resolveCommandAction(command) {
    const normalized = String(command || '').trim().toLowerCase();
    if (commandActionMap.has(normalized)) return commandActionMap.get(normalized);
    if (normalized.startsWith('/agent inspect')) return 'agents.create';
    if (normalized.startsWith('/review')) return 'evidence.search';
    if (normalized.startsWith('/map')) return 'code.intel';
    return '';
  }

  function applyOpcbSelection(kind, id) {
    if (!window.opcbState) return;
    window.opcbState.ui = window.opcbState.ui || {};
    const normalizedKind = String(kind || 'control');
    const normalizedId = String(id || '').trim();
    const keyMap = {
      'workspace-canvas': 'workspaceCanvas',
      'map-filter': 'mapFilter',
      'map-group': 'mapGroup',
      'map-layout': 'mapLayout',
      'map-canvas': 'mapCanvas',
      'gateway-route': 'gatewayRoute'
    };
    const stateKey = keyMap[normalizedKind];
    if (stateKey) window.opcbState.ui[stateKey] = normalizedId;
    window.opcbRecordAction?.({
      id: `select.${normalizedKind}`,
      label: `${normalizedKind.replace(/-/g, ' ')}: ${normalizedId}`,
      status: 'selected',
      page: document.querySelector('.app-shell')?.dataset?.desktopPage || 'workspace'
    });
    window.opcbApplyPage?.(document.querySelector('.app-shell')?.dataset?.desktopPage || 'workspace', { skipLiveRefresh: true });
  }

  window.opcbRunCommand = async function opcbRunCommand(command) {
    const input = document.getElementById('commandBarInput');
    if (input) input.value = command;
    const normalized = String(command || '').trim().toLowerCase();
    if (normalized === '/gateway recheck') {
      document.querySelector('[data-opcb-recheck-gateway]')?.click();
      return;
    }
    if (normalized === '/gateway restart') {
      document.querySelector('[data-opcb-restart-gateway]')?.click();
      return;
    }
    if (normalized === '/readiness check') {
      document.querySelector('[data-opcb-readiness]')?.click();
      return;
    }
    if (normalized === '/files') {
      window.setDesktopPage?.('source');
      window.refreshFiles?.();
      window.beastDesktopLog?.('OPCB command /files -> Source file explorer');
      return;
    }
    if (normalized === '/doctor') {
      window.setDesktopPage?.('doctor');
      return;
    }
    if (normalized === '/open gateway') {
      window.beastDesktop?.openGateway?.();
      window.opcbRecordAction?.({ id: 'gateway.open', label: 'Open Gateway', status: 'completed', page: 'doctor' });
      return;
    }
    const actionId = resolveCommandAction(command);
    if (actionId && window.runIdeActionById) {
      window.beastDesktopLog?.(`OPCB command ${command} -> ${actionId}`);
      const page = document.querySelector('.app-shell')?.dataset?.desktopPage || '';
      await (window.opcbRunIdeActionById || window.runIdeActionById)(actionId, { refreshPage: page, page });
      return;
    }
    window.beastDesktopLog?.(`OPCB prototype command staged: ${command}`);
    input?.focus();
  };

  window.opcbApplyPage = function opcbApplyPage(page, options = {}) {
    const shell = document.querySelector('.app-shell');
    if (shell) shell.dataset.dashboardPage = dashboardPages.has(page) ? 'true' : 'false';
    if (document.body) document.body.dataset.opcbActive = dashboardPages.has(page) ? 'true' : 'false';
    updateMissionHeader();
    window.opcbRenderPage?.(page, window.opcbState);
    applyPageArt(page);
    injectVisibleIcons(page);
    applyPulse(page);
    applyMascot(page);
    startSpriteAnimator();
    renderRightRail(page);
    renderCommandChips(page);
    enforceOpcbControlContract(page);
    if (!options.skipLiveRefresh && dashboardPages.has(page)) {
      window.opcbRefreshPage?.(page).catch(error => {
        window.beastDesktopLog?.(`OPCB live refresh failed for ${page}: ${error.message || error}`);
      });
    }
  };

  document.addEventListener('click', event => {
    const prototypeControl = event.target.closest('[data-prototype-reason]');
    if (prototypeControl) {
      window.beastDesktopLog?.(`OPCB disabled control: ${prototypeControl.dataset.prototypeReason}`);
      return;
    }
    const liveBlockedControl = event.target.closest('[data-live-block-reason]');
    if (liveBlockedControl) {
      window.beastDesktopLog?.(`OPCB blocked control: ${liveBlockedControl.dataset.liveBlockReason}`);
      return;
    }
    const refreshControl = event.target.closest('[data-opcb-refresh]');
    if (refreshControl) {
      const page = refreshControl.dataset.opcbRefresh;
      window.opcbRecordAction?.({ id: `refresh.${page}`, label: `Refresh ${page}`, status: 'started', page });
      window.opcbRefreshPage?.(page, { forceGateway: true }).then(() => {
        window.opcbRecordAction?.({ id: `refresh.${page}`, label: `Refresh ${page}`, status: 'completed', page });
      }).catch(error => {
        window.opcbRecordAction?.({ id: `refresh.${page}`, label: `Refresh ${page}`, status: 'failed', page, detail: String(error.message || error) });
      });
      return;
    }
    if (event.target.closest('[data-opcb-recheck-gateway]')) {
      window.opcbRecordAction?.({ id: 'gateway.recheck', label: 'Recheck Gateway Routes', status: 'started', page: 'doctor' });
      window.opcbRecheckGatewayContract?.().then(() => {
        window.opcbRecordAction?.({ id: 'gateway.recheck', label: 'Recheck Gateway Routes', status: 'completed', page: 'doctor' });
      }).catch(error => {
        window.opcbRecordAction?.({ id: 'gateway.recheck', label: 'Recheck Gateway Routes', status: 'failed', page: 'doctor', detail: String(error.message || error) });
      });
      return;
    }
    if (event.target.closest('[data-opcb-restart-gateway]')) {
      window.opcbRecordAction?.({ id: 'gateway.restart', label: 'Restart Gateway', status: 'started', page: 'doctor' });
      window.beastDesktop?.restartGateway?.().then(async () => {
        await window.refreshSnapshot?.({ force: true });
        await window.opcbRecheckGatewayContract?.();
        window.opcbRecordAction?.({ id: 'gateway.restart', label: 'Restart Gateway', status: 'completed', page: 'doctor' });
      }).catch(error => {
        window.opcbRecordAction?.({ id: 'gateway.restart', label: 'Restart Gateway', status: 'failed', page: 'doctor', detail: String(error.message || error) });
      });
      return;
    }
    if (event.target.closest('[data-opcb-readiness]')) {
      window.opcbRecordAction?.({ id: 'readiness.check', label: 'Run Readiness Check', status: 'started', page: 'doctor' });
      window.opcbRefreshReadiness?.({ runRelease: true }).then(() => {
        window.opcbRecordAction?.({ id: 'readiness.check', label: 'Run Readiness Check', status: 'completed', page: 'doctor' });
      }).catch(error => {
        window.opcbRecordAction?.({ id: 'readiness.check', label: 'Run Readiness Check', status: 'failed', page: 'doctor', detail: String(error.message || error) });
      });
      return;
    }
    const selectControl = event.target.closest('[data-opcb-select]');
    if (selectControl) {
      const kind = selectControl.dataset.opcbSelect || 'control';
      const id = selectControl.dataset.id || selectControl.textContent.replace(/\s+/g, ' ').trim();
      applyOpcbSelection(kind, id);
      return;
    }
    if (event.target.closest('#commandChipRefresh')) {
      window.refreshSnapshot?.({ force: true });
      return;
    }
    if (event.target.closest('#commandChipPalette')) {
      window.focusCommandPalette?.();
      return;
    }
    const dashboardCommand = event.target.closest('.opcb-dashboard [data-command], #opcbRightRail [data-command]');
    if (dashboardCommand) {
      window.opcbRunCommand(dashboardCommand.dataset.command);
      return;
    }
    const commandChip = event.target.closest('.command-chip[data-command]');
    if (commandChip) {
      window.opcbRunCommand(commandChip.dataset.command);
      return;
    }
    const actionControl = event.target.closest('.opcb-dashboard [data-ide-action], #opcbRightRail [data-ide-action]');
    if (actionControl) {
      const page = document.querySelector('.app-shell')?.dataset?.desktopPage || '';
      (window.opcbRunIdeActionById || window.runIdeActionById)?.(actionControl.dataset.ideAction, { refreshPage: page, page });
      return;
    }
    const inertDashboardButton = event.target.closest('.opcb-dashboard button, #opcbRightRail button');
    if (inertDashboardButton) {
      const label = inertDashboardButton.textContent.replace(/\s+/g, ' ').trim() || 'unnamed control';
      window.beastDesktopLog?.(`Prototype-only OPCB control: ${label}`);
    }
  });
})();
