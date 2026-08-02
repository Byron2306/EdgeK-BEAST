(() => {
  const DEFAULT_GATEWAY = 'http://127.0.0.1:8000';
  const listeners = { workspace: new Set(), refresh: new Set(), log: new Set() };
  const demoMode = new URLSearchParams(location.search).get('demo') === '1';
  const DEMO_FILES = {
    'src/core/router.py': `from dataclasses import dataclass\n\n@dataclass\nclass RouteDecision:\n    provider: str\n    model: str\n    reason: str\n\ndef choose_route(task: str) -> RouteDecision:\n    \"\"\"Prefer local inference, escalate only when evidence demands it.\"\"\"\n    if len(task) < 240:\n        return RouteDecision('ollama', 'qwen2.5-coder:7b', 'local-first')\n    return RouteDecision('nvidia_nim', 'nemotron', 'complexity escalation')\n`,
    'src/core/evidence_parser.py': `import json\nfrom pathlib import Path\n\ndef parse_evidence(path: Path) -> list[dict]:\n    rows: list[dict] = []\n    for line in path.read_text(encoding='utf-8').splitlines():\n        if not line.strip():\n            continue\n        rows.append(json.loads(line))\n    return rows\n`,
    'src/ui/mission.ts': `export type MissionState = 'idle' | 'working' | 'alert' | 'complete';\n\nexport function missionLabel(state: MissionState): string {\n  return state === 'complete' ? 'CRYSTALLIZED' : state.toUpperCase();\n}\n`,
    'config/beast.yaml': `runtime:\n  local_first: true\n  max_context_files: 64\n  token_budget: 4000\ngovernance:\n  sourceplan_required: true\n  evidence_closure: true\n`,
    'README.md': `# BEAST Editor Cortex\n\nPhase 2 demonstrates multi-tab editing, persistent dirty buffers, governed SourcePlan drafting, diff review, verification, and apply readiness.\n`
  };

  function desktop() { return window.beastDesktop || null; }
  function workspaceRoot() { return BeastStore.get().workspace.root || ''; }
  function gatewayUrl() { return BeastStore.get().connection.gatewayUrl || window.gatewayUrl || DEFAULT_GATEWAY; }

  function withTimeout(signal, timeoutMs = 5000) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort('timeout'), timeoutMs);
    if (signal) signal.addEventListener('abort', () => controller.abort(signal.reason), { once: true });
    return { signal: controller.signal, done: () => window.clearTimeout(timer) };
  }

  async function fetchJson(path, options = {}) {
    const target = new URL(path, gatewayUrl());
    const timer = withTimeout(options.signal, options.timeoutMs || 5000);
    try {
      const response = await fetch(target, {
        method: options.method || 'GET',
        headers: options.body ? { 'Content-Type': 'application/json' } : undefined,
        body: options.body ? JSON.stringify(options.body) : undefined,
        signal: timer.signal
      });
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`.trim());
      return await response.json();
    } finally { timer.done(); }
  }

  async function status(options = {}) {
    if (demoMode) {
      const result = { gatewayUrl: DEFAULT_GATEWAY, repoRoot: '/demo/BEAST', version: 'phase6-demo', health: { ok: true, local_mode: true } };
      BeastStore.patch('connection', { status: 'online', gatewayUrl: DEFAULT_GATEWAY, localMode: true, demoMode: true, build: 'BEAST Phase 6 Demo', checkedAt: Date.now(), error: '' });
      if (workspaceRoot() !== '/demo/BEAST') setRoot('/demo/BEAST');
      return result;
    }
    const api = desktop();
    try {
      const result = api?.status ? await api.status() : await fetchJson('/edgek/root-info', options);
      const gateway = result?.gatewayUrl || window.gatewayUrl || DEFAULT_GATEWAY;
      BeastStore.patch('connection', {
        status: result?.health?.ok === false ? 'offline' : 'online', gatewayUrl: gateway,
        localMode: Boolean(result?.health?.local_mode), build: result?.desktopVersion || result?.version || 'BEAST Phase 6',
        checkedAt: Date.now(), error: ''
      });
      if (!workspaceRoot() && result?.repoRoot) setRoot(result.repoRoot);
      window.gatewayUrl = gateway;
      return result;
    } catch (error) {
      BeastStore.patch('connection', { status: 'offline', checkedAt: Date.now(), error: String(error.message || error) });
      return null;
    }
  }

  function setRoot(root) {
    const value = String(root || '');
    localStorage.setItem('beast.v2.workspace.root', value);
    BeastStore.transaction(next => {
      next.workspace = { ...next.workspace, root: value, selectedPath: '', currentText: '', originalText: '', dirty: false, error: '', indexedAt: 0 };
      next.editor = { ...next.editor, openTabs: [], activePath: '', dirtyPaths: [], outline: [], owner: 'unmounted' };
      next.sourcePlan = { ...next.sourcePlan, status: 'idle', message: 'No editor draft yet.', plan: null, lifecycle: null, selectedOperationIds: [], previewText: '', originalText: '', proposedText: '', activeOperationId: '', stale: false, error: '', lastApply: null };
    });
    window.workspaceRoot = value;
    return value;
  }

  async function chooseWorkspace() {
    if (demoMode) return setRoot('/demo/BEAST');
    const api = desktop();
    if (!api?.chooseWorkspace) throw new Error('Workspace chooser is available only inside the BEAST desktop shell.');
    const selected = await api.chooseWorkspace();
    if (selected) {
      setRoot(selected);
      listeners.workspace.forEach(listener => listener(selected));
      BeastStore.addLedger(`Workspace selected: ${selected}`);
    }
    return selected;
  }

  function normalizeFiles(payload) {
    const rows = Array.isArray(payload) ? payload : payload?.files || payload?.items || payload?.entries || [];
    return rows.map(row => {
      if (typeof row === 'string') return { path: row, name: row.split('/').pop(), type: 'file', size: '' };
      const path = row.path || row.name || row.file || '';
      return { ...row, path, name: row.name || path.split('/').pop(), type: row.type || row.kind || (path.endsWith('/') ? 'directory' : 'file'), size: row.size ?? row.bytes ?? '' };
    }).filter(row => row.path);
  }

  async function listFiles(options = {}) {
    const root = workspaceRoot();
    if (!root) return [];
    BeastStore.patch('workspace', { loading: true, error: '' });
    try {
      let files;
      if (demoMode) files = Object.entries(DEMO_FILES).map(([path, text]) => ({ path, name: path.split('/').pop(), type: 'file', size: text.length }));
      else {
        const api = desktop();
        let payload;
        if (api?.listFiles) payload = await api.listFiles(root, options.limit || 2000);
        else payload = await fetchJson(`/edgek/workspace/files?${new URLSearchParams({ root_path: root, limit: String(options.limit || 1000) })}`, options);
        files = normalizeFiles(payload);
      }
      BeastStore.patch('workspace', { files, loading: false, error: '', indexedAt: Date.now() });
      BeastStore.addLedger(`Workspace indexed: ${files.length} entries`);
      return files;
    } catch (error) {
      BeastStore.patch('workspace', { loading: false, error: String(error.message || error) });
      return [];
    }
  }

  async function loadFile(path, options = {}) {
    const root = workspaceRoot();
    if (!root || !path) return null;
    if (demoMode) return { path, text: DEMO_FILES[path] ?? '', payload: { content: DEMO_FILES[path] ?? '', demo: true } };
    const api = desktop();
    let payload;
    if (api?.readFile) payload = await api.readFile(root, path, options.maxChars || 1000000);
    else payload = await fetchJson(`/edgek/workspace/file?${new URLSearchParams({ root_path: root, path, max_chars: String(options.maxChars || 1000000) })}`, options);
    const text = typeof payload === 'string' ? payload : payload?.content ?? payload?.text ?? '';
    return { path, text, payload };
  }

  async function readFile(path, options = {}) {
    try {
      const loaded = await loadFile(path, options);
      if (!loaded) return null;
      BeastStore.patch('workspace', { selectedPath: path, currentText: loaded.text, originalText: loaded.text, dirty: false, language: inferLanguage(path), error: '' });
      BeastStore.addLedger(`Opened ${path}`);
      return loaded;
    } catch (error) {
      BeastStore.patch('workspace', { error: String(error.message || error) });
      return null;
    }
  }

  function inferLanguage(path) {
    const ext = String(path || '').split('.').pop().toLowerCase();
    return ({ js:'javascript', jsx:'javascript', ts:'typescript', tsx:'typescript', py:'python', json:'json', md:'markdown', html:'html', css:'css', yml:'yaml', yaml:'yaml', sh:'shell', rs:'rust', go:'go', java:'java', c:'c', cpp:'cpp' })[ext] || 'plaintext';
  }

  function normalizeMission(snapshot = {}, route = {}) {
    const current = BeastStore.get().mission;
    const receipts = snapshot.evidence_bus?.receipts || snapshot.evidence_bus?.items || [];
    const agents = snapshot.agent_sessions?.sessions || (Array.isArray(snapshot.agent_sessions) ? snapshot.agent_sessions : []);
    const graphNodes = snapshot.code_cortex?.nodes || snapshot.code_cortex?.files || [];
    const steps = route.steps || route.route || route.faces || [];
    const ids = ['mission','workspace','source','models','agents','review','crystallization'];
    const path = steps.length ? steps.slice(0, ids.length).map((step, index) => ({ id: ids[index], title: step.title || step.face || step.name || current.path[index]?.title || ids[index], status: step.status || current.path[index]?.status || (index < 1 ? 'Complete' : index < 3 ? 'In Progress' : 'Pending') })) : current.path;
    const health = snapshot.mission_cockpit?.health || snapshot.policy?.reintegration_health || {};
    return {
      id: snapshot.mission_cockpit?.mission_id || snapshot.mission_id || current.id,
      title: snapshot.objective || current.title,
      status: snapshot.status || current.status,
      progress: Number(snapshot.progress ?? snapshot.mission_cockpit?.progress ?? current.progress),
      health: Number(health.score ?? health.overall ?? health.health ?? current.health),
      confidence: health.confidence || current.confidence, risk: health.risk || current.risk,
      metrics: {
        artifacts: Number(snapshot.evidence_bus?.total ?? receipts.length ?? current.metrics.artifacts),
        checks: Number(snapshot.policy?.architecture_decisions?.decision_count ?? current.metrics.checks),
        traces: Number(snapshot.mission_lattice?.nodes ?? graphNodes.length ?? current.metrics.traces),
        evidenceItems: Number(snapshot.workspace_files?.files ?? receipts.length ?? current.metrics.evidenceItems),
        agents: Number(agents.length || current.metrics.agents)
      }, path, timeline: current.timeline
    };
  }

  async function snapshot(options = {}) {
    if (demoMode) {
      BeastStore.patch('mission', { progress: 58, health: 96, status: 'In Progress', lastRefreshAt: Date.now(), loading: false, error: '', metrics: { artifacts: 18, checks: 31, traces: 1842, evidenceItems: 96, agents: 7 } });
      return { demo: true };
    }
    const root = workspaceRoot();
    BeastStore.patch('mission', { loading: true, error: '' });
    try {
      const params = new URLSearchParams();
      if (root) params.set('root_path', root);
      const selected = BeastStore.get().workspace.selectedPath;
      if (selected) params.set('active_file', selected);
      params.set('objective', selected ? `Work on ${selected}` : 'BEAST desktop mission');
      const snap = await fetchJson(`/edgek/ide/snapshot?${params}`, options);
      let route = {};
      try { route = await fetchJson(`/edgek/mission/route?${params}`, { ...options, timeoutMs: 3000 }); } catch (_) {}
      const normalized = normalizeMission(snap, route || {});
      BeastStore.transaction(next => { next.mission = { ...next.mission, ...normalized, loading: false, error: '', lastRefreshAt: Date.now() }; });
      BeastStore.addLedger('Mission snapshot refreshed');
      return snap;
    } catch (error) {
      BeastStore.patch('mission', { loading: false, error: String(error.message || error) });
      return null;
    }
  }

  async function actionsManifest(options = {}) {
    if (demoMode) return [];
    try {
      const payload = await fetchJson('/edgek/ide/actions/manifest', options);
      const actions = payload?.actions || payload?.items || (Array.isArray(payload) ? payload : []);
      BeastStore.set('actions', actions);
      return actions;
    } catch (_) { return []; }
  }

  function operationCommand(operation) {
    const q = value => `"${String(value || '').replace(/(["\\$`])/g, '\\$1')}"`;
    if (operation.op === 'create_file') return `touch ${q(operation.path)}`;
    if (operation.op === 'create_folder') return `mkdir -p ${q(operation.path)}`;
    if (operation.op === 'rename') return `mv ${q(operation.path)} ${q(operation.target)}`;
    if (operation.op === 'delete_file') return `rm ${q(operation.path)}`;
    return `workspace-file-op ${q(operation.path)}`;
  }

  async function classifyFileOperation(operation, options = {}) {
    if (demoMode || BeastStore.get().connection.status !== 'online') return { decision: 'warn', risk_level: 'local', reasons: [{ detail: 'Gateway unavailable or demo mode; operator confirmation required.' }] };
    return await fetchJson('/edgek/safety-governor/classify-command', { ...options, method: 'POST', body: { root_path: workspaceRoot(), command: operationCommand(operation), mode: 'operator', task_id: '', operator_override: 'BEAST Phase 2 file mutation requires explicit operator confirmation.' } });
  }

  async function fileOperation(operation, options = {}) {
    const api = desktop();
    if (demoMode) return { ok: false, error: 'Demo workspace is read-only.' };
    if (!api?.fileOperation) throw new Error('Desktop fileOperation API is unavailable.');
    return await api.fileOperation(workspaceRoot(), operation, options);
  }

  async function draftSourcePlan({ path, originalText, newText, selectedHunks = [] }, options = {}) {
    if (!path) throw new Error('Select a file before drafting SourcePlan.');
    if (demoMode || BeastStore.get().connection.status !== 'online') {
      const opId = `op-${Date.now().toString(36)}`;
      return {
        ok: true, local: true,
        plan: { plan_id: `LOCAL-${Date.now().toString(36).toUpperCase()}`, status: 'draft_requires_gateway', path, operations: [{ operation_id: opId, op: 'replace_file', path, selected: true, risk: 'medium', summary: 'Replace active editor buffer through governed apply.' }], selected_operations: [opId] },
        preview_text: localDiff(originalText, newText),
        preview: { operations: [{ operation_id: opId, diff_lines: localDiff(originalText, newText).split('\n') }] }
      };
    }
    return await fetchJson('/edgek/ide/sourceplan/from-editor', { ...options, method: 'POST', body: { root_path: workspaceRoot(), path, original_text: originalText, new_text: newText, objective: `Apply governed BEAST editor changes to ${path}`, provider: localStorage.getItem('beast.provider') || 'nvidia_nim', model: localStorage.getItem('beast.model') || 'meta/llama-3.1-8b-instruct', selected_hunks: selectedHunks } });
  }

  async function sourcePlanLifecycle(plan, options = {}) {
    if (!plan) return null;
    if (demoMode || BeastStore.get().connection.status !== 'online') {
      const ops = plan.operations || [];
      return { plan_id: plan.plan_id, status: 'draft_requires_gateway', can_verify: false, can_apply: false, score: 72, risk: 'medium', stale_operations: [], operations: ops, checks: [{ label: 'Editor diff compiled', status: 'pass' }, { label: 'Gateway verification', status: 'pending' }, { label: 'Rollback receipt', status: 'pending' }], action_contract: { requires_approval: true, evidence_closure: true, rollback_required: true } };
    }
    return await fetchJson('/edgek/ide/sourceplan/lifecycle', { ...options, method: 'POST', body: { root_path: workspaceRoot(), plan } });
  }

  async function verifySourcePlan(plan, options = {}) {
    if (!plan) throw new Error('No SourcePlan draft to verify.');
    if (demoMode || BeastStore.get().connection.status !== 'online') throw new Error('Verification requires the BEAST gateway.');
    return await fetchJson('/edgek/sourceplan/verify', { ...options, method: 'POST', body: { root_path: workspaceRoot(), plan } });
  }

  async function applySourcePlan(plan, options = {}) {
    if (!plan) throw new Error('No SourcePlan draft to apply.');
    if (demoMode || BeastStore.get().connection.status !== 'online') throw new Error('Apply requires the BEAST gateway.');
    return await fetchJson('/edgek/sourceplan/apply', { ...options, method: 'POST', body: { root_path: workspaceRoot(), plan, approved: true } });
  }

  function localDiff(originalText = '', newText = '') {
    const before = String(originalText).split('\n');
    const after = String(newText).split('\n');
    const out = ['--- original', '+++ proposed'];
    const max = Math.max(before.length, after.length);
    for (let i = 0; i < max; i += 1) {
      if (before[i] === after[i]) { if (before[i] !== undefined) out.push(`  ${before[i]}`); continue; }
      if (before[i] !== undefined) out.push(`- ${before[i]}`);
      if (after[i] !== undefined) out.push(`+ ${after[i]}`);
    }
    return out.join('\n');
  }

  function bindDesktopEvents() {
    const api = desktop();
    api?.onWorkspaceSelected?.(root => { setRoot(root); listeners.workspace.forEach(listener => listener(root)); });
    api?.onRefresh?.(() => listeners.refresh.forEach(listener => listener()));
    api?.onGatewayLog?.(lines => listeners.log.forEach(listener => listener(lines)));
  }

  function on(type, listener) { listeners[type]?.add(listener); return () => listeners[type]?.delete(listener); }

  window.BeastDesktopBridge = {
    status, chooseWorkspace, setRoot, listFiles, loadFile, readFile, snapshot, actionsManifest,
    inferLanguage, classifyFileOperation, fileOperation, draftSourcePlan, sourcePlanLifecycle,
    verifySourcePlan, applySourcePlan, localDiff, bindDesktopEvents, on, fetchJson,
    get workspaceRoot() { return workspaceRoot(); }, get gatewayUrl() { return gatewayUrl(); }, get demoMode() { return demoMode; }
  };
})();
