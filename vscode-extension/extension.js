const vscode = require('vscode');
const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');

const DEFAULT_PROXY = 'http://127.0.0.1:8000';

let currentPlan = null;
let currentScorecard = null;
let lastChronicles = [];
let lastFitness = [];
let lastMaintenance = null;
let lastIdeSnapshot = null;
let currentPreview = null;
let extensionContext = null;
let sourceWorkbenchPanel = null;
let ideEventAbort = null;
let ideEventProvider = null;
let latestIdeEvents = {};
let beastDiagnostics = null;
let currentAgentSession = null;
const virtualDocuments = new Map();
let dragonMascotDataUri = null;

const selectedHunkDecoration = vscode.window.createTextEditorDecorationType({
    backgroundColor: 'rgba(166, 255, 63, 0.16)',
    overviewRulerColor: '#a6ff3f',
    overviewRulerLane: vscode.OverviewRulerLane.Right,
    border: '1px solid rgba(166, 255, 63, 0.35)',
});

const skippedHunkDecoration = vscode.window.createTextEditorDecorationType({
    backgroundColor: 'rgba(122, 140, 141, 0.12)',
    overviewRulerColor: '#7a8c8d',
    overviewRulerLane: vscode.OverviewRulerLane.Right,
    border: '1px solid rgba(122, 140, 141, 0.25)',
});

const staleHunkDecoration = vscode.window.createTextEditorDecorationType({
    backgroundColor: 'rgba(255, 77, 109, 0.14)',
    overviewRulerColor: '#ff4d6d',
    overviewRulerLane: vscode.OverviewRulerLane.Right,
    border: '1px solid rgba(255, 77, 109, 0.35)',
});

function config() {
    return vscode.workspace.getConfiguration('edgekBeast');
}

function gatewayUrl() {
    return String(config().get('proxyUrl') || DEFAULT_PROXY).replace(/\/+$/, '');
}

function workspaceFolderPath() {
    return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '';
}

function findBeastRepoRoot(startPath) {
    let current = startPath ? path.resolve(startPath) : '';
    for (let i = 0; current && i < 8; i += 1) {
        const beastBin = path.join(current, 'bin', 'beast');
        const appMain = path.join(current, 'app', 'main.py');
        if (fs.existsSync(beastBin) && fs.existsSync(appMain)) {
            return current;
        }
        const next = path.dirname(current);
        if (!next || next === current) {
            break;
        }
        current = next;
    }
    return startPath || '';
}

function beastWorkspaceRoot() {
    return findBeastRepoRoot(workspaceFolderPath());
}

function workspaceRelative(filePath) {
    const folder = workspaceFolderPath();
    if (!folder || !filePath) {
        return '';
    }
    return path.relative(folder, filePath).replace(/\\/g, '/');
}

function beastCommand() {
    const configured = String(config().get('mcpServerCommand') || '');
    if (configured && configured !== 'beast') {
        return configured;
    }
    const root = beastWorkspaceRoot();
    if (root) {
        const local = path.join(root, 'bin', 'beast');
        if (fs.existsSync(local)) {
            return local;
        }
    }
    return 'beast';
}

function beastTerminal(cwd) {
    return vscode.window.activeTerminal || vscode.window.createTerminal({ name: 'BEAST Gateway', cwd });
}

async function getJson(pathname) {
    const response = await fetch(`${gatewayUrl()}${pathname}`);
    if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText}`);
    }
    return response.json();
}

async function postJson(pathname, payload) {
    const response = await fetch(`${gatewayUrl()}${pathname}`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload || {}),
    });
    if (!response.ok) {
        const text = await response.text();
        throw new Error(`${response.status} ${response.statusText}: ${text.slice(0, 500)}`);
    }
    return response.json();
}

async function isGatewayRunning() {
    try {
        const response = await fetch(`${gatewayUrl()}/health`);
        return response.ok;
    } catch {
        return false;
    }
}

function gatewayCommandLine() {
    return `"${beastCommand()}" gateway --host 127.0.0.1 --port 8000`;
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function ensureGateway() {
    if (await isGatewayRunning()) {
        return true;
    }

    const cwd = beastWorkspaceRoot() || workspaceFolderPath();
    const terminal = beastTerminal(cwd);
    terminal.show();
    terminal.sendText(gatewayCommandLine());
    vscode.window.showInformationMessage('BEAST: starting gateway on http://127.0.0.1:8000');
    for (let attempt = 0; attempt < 10; attempt += 1) {
        await sleep(500);
        if (await isGatewayRunning()) {
            return true;
        }
    }
    vscode.window.showWarningMessage('BEAST gateway did not answer /health yet. Opening IDE Doctor.', 'Open Doctor')
        .then(choice => {
            if (choice === 'Open Doctor') {
                showIdeDoctor();
            }
        });
    return false;
}

async function callMcpTool(name, args = {}) {
    const ready = await ensureGateway();
    if (!ready) {
        throw new Error(`BEAST gateway is not reachable at ${gatewayUrl()}. Run BEAST: Diagnose IDE Shell for details.`);
    }
    const payload = await postJson('/mcp/tools/call', { name, arguments: args });
    const text = payload?.content?.[0]?.text || '{}';
    try {
        return JSON.parse(text);
    } catch {
        return { ok: false, error: text };
    }
}

function activeContextFiles() {
    const editor = vscode.window.activeTextEditor;
    const rel = editor ? workspaceRelative(editor.document.uri.fsPath) : '';
    return rel ? [rel] : [];
}

function chatModel() {
    return String(config().get('model') || 'beast-auto');
}

async function promptObjective(defaultObjective) {
    return vscode.window.showInputBox({
        title: 'BEAST SourcePlan Objective',
        prompt: 'What should BEAST prepare a governed patch for?',
        value: defaultObjective || 'Prepare a safe governed source patch',
    });
}

async function promptProvider() {
    return String(config().get('provider') || 'litellm');
}

function actionData(result) {
    return result?.data || result || {};
}

function sessionPayload() {
    return {
        plan: currentPlan,
        scorecard: currentScorecard,
        preview: currentPreview,
        savedAt: Date.now(),
    };
}

function saveIdeSession() {
    if (extensionContext) {
        extensionContext.workspaceState.update('edgekBeast.ideSession', sessionPayload());
        if (currentPlan?.plan_id) {
            const sessions = extensionContext.workspaceState.get('edgekBeast.planSessions') || {};
            sessions[currentPlan.plan_id] = sessionPayload();
            extensionContext.workspaceState.update('edgekBeast.planSessions', sessions);
        }
    }
}

function restoreIdeSession(context) {
    const saved = context.workspaceState.get('edgekBeast.ideSession') || {};
    currentPlan = saved.plan || null;
    currentScorecard = saved.scorecard || null;
    currentPreview = saved.preview || null;
}

async function showVirtualDocument(name, language, content) {
    const uri = vscode.Uri.parse(`untitled:${name}`);
    const doc = await vscode.workspace.openTextDocument(uri);
    const editor = await vscode.window.showTextDocument(doc, { preview: true });
    await editor.edit(edit => edit.insert(new vscode.Position(0, 0), content || ''));
    await vscode.languages.setTextDocumentLanguage(doc, language);
}

class BeastVirtualDocumentProvider {
    provideTextDocumentContent(uri) {
        return virtualDocuments.get(uri.toString()) || '';
    }
}

function virtualDocumentUri(label, content) {
    const uri = vscode.Uri.parse(`beast-preview:/${encodeURIComponent(label)}`);
    virtualDocuments.set(uri.toString(), content || '');
    return uri;
}

class BeastStatusProvider {
    constructor() {
        this._onDidChangeTreeData = new vscode.EventEmitter();
        this.onDidChangeTreeData = this._onDidChangeTreeData.event;
    }
    refresh() { this._onDidChangeTreeData.fire(); }
    getTreeItem(element) { return element; }
    getChildren() {
        return [
            new vscode.TreeItem(`Gateway: ${gatewayUrl()}`),
            new vscode.TreeItem(`BEAST Root: ${beastWorkspaceRoot() || 'not detected'}`),
            new vscode.TreeItem(`Start: ${gatewayCommandLine()}`),
            new vscode.TreeItem(`Provider: ${config().get('provider') || 'litellm'}`),
            new vscode.TreeItem(`Role: ${config().get('providerRole') || 'rescued_patch_provider'}`),
            new vscode.TreeItem('MCP Lane: stdio + HTTP facade'),
            new vscode.TreeItem(`Workspace: ${workspaceFolderPath() || 'none'}`),
        ];
    }
}

class ChronicleProvider {
    constructor() {
        this._onDidChangeTreeData = new vscode.EventEmitter();
        this.onDidChangeTreeData = this._onDidChangeTreeData.event;
    }
    refresh() { this._onDidChangeTreeData.fire(); }
    getTreeItem(element) { return element; }
    getChildren() {
        if (!lastChronicles.length) {
            return [new vscode.TreeItem('No Chronicle records loaded')];
        }
        return lastChronicles.map(item => {
            const label = `${item.task_id || item.id || 'task'} · ${item.provider || 'local'} · ${item.category || item.status || 'record'}`;
            const treeItem = new vscode.TreeItem(label);
            treeItem.tooltip = item.summary || JSON.stringify(item, null, 2);
            treeItem.command = {
                command: 'edgekBeast.openChronicleRecord',
                title: 'Open Chronicle Record',
                arguments: [item],
            };
            return treeItem;
        });
    }
}

class RouteFitnessProvider {
    constructor() {
        this._onDidChangeTreeData = new vscode.EventEmitter();
        this.onDidChangeTreeData = this._onDidChangeTreeData.event;
    }
    refresh() { this._onDidChangeTreeData.fire(); }
    getTreeItem(element) { return element; }
    getChildren() {
        if (!lastFitness.length) {
            return [new vscode.TreeItem('No provider fitness loaded')];
        }
        return lastFitness.map(item => {
            const label = `${item.provider}: ${item.provider_fitness_score ?? 0} · ${item.recommended_role || 'scout_only'}`;
            const treeItem = new vscode.TreeItem(label);
            treeItem.tooltip = JSON.stringify(item, null, 2);
            return treeItem;
        });
    }
}

class BeastIdeProvider {
    constructor() {
        this._onDidChangeTreeData = new vscode.EventEmitter();
        this.onDidChangeTreeData = this._onDidChangeTreeData.event;
    }
    refresh() { this._onDidChangeTreeData.fire(); }
    getTreeItem(element) { return element; }
    getChildren(element) {
        const snap = lastIdeSnapshot;
        if (!snap) {
            const item = new vscode.TreeItem('Open Mission Control', vscode.TreeItemCollapsibleState.None);
            item.description = 'Phase 1 IDE shell';
            item.command = { command: 'edgekBeast.openMissionControl', title: 'Open Mission Control' };
            return [item];
        }
        if (!element) {
            return [
                this.section('Mission', `${snap.mission_cockpit?.cards?.length || 0} cards`, 'edgekBeast.openMissionControl'),
                this.section('SourcePlans', `${snap.sourceplan_queue?.length || 0} queued`, 'edgekBeast.openSourceWorkbench'),
                this.section('Evidence', `${snap.evidence_bus?.total || snap.evidence_bus?.count || 0} receipts`, 'edgekBeast.showEvidence'),
                this.section('Code Cortex', snap.code_cortex?.adapter || snap.code_cortex?.front_door || 'ready', 'edgekBeast.showCodeCortex'),
                this.section('Agent Sessions', `${snap.agent_sessions?.count || 0} sessions`, 'edgekBeast.showAgentSessions'),
                this.section('Worktrees', `${snap.worktrees?.count || 0} active`, 'edgekBeast.showWorktrees'),
                this.section('Policy Gate', snap.policy?.mode_route?.selected_mode || 'mode ready', 'edgekBeast.showPolicyGate'),
                this.section('IDE Doctor', snap.gateway_url || gatewayUrl(), 'edgekBeast.diagnoseIdeShell'),
                this.section('Lattice', `${snap.mission_lattice?.cell_count || 0} cells`, 'edgekBeast.replayLatticeCandidate'),
                this.section('Live Events', latestIdeEvents.connected ? 'connected' : 'start stream', 'edgekBeast.startIdeEventBus'),
            ];
        }
        return [];
    }
    section(label, description, command) {
        const item = new vscode.TreeItem(label, vscode.TreeItemCollapsibleState.None);
        item.description = description;
        item.tooltip = description;
        item.command = { command, title: label };
        return item;
    }
}

function activeObjective() {
    const editor = vscode.window.activeTextEditor;
    const selection = editor && !editor.selection.isEmpty ? editor.document.getText(editor.selection).trim() : '';
    const rel = editor ? workspaceRelative(editor.document.uri.fsPath) : '';
    if (selection) {
        return `Update selected code in ${rel}: ${selection.slice(0, 160)}`;
    }
    return rel ? `Work on ${rel}` : 'BEAST IDE mission';
}

async function refreshIdeSnapshot(provider, { quiet = false } = {}) {
    await ensureGateway();
    const params = new URLSearchParams();
    const root = workspaceFolderPath();
    const files = activeContextFiles();
    if (root) params.set('root_path', root);
    if (files[0]) params.set('active_file', files[0]);
    params.set('objective', activeObjective());
    const snapshot = await getJson(`/edgek/ide/snapshot?${params.toString()}`);
    lastIdeSnapshot = snapshot;
    if (provider) {
        provider.refresh();
    }
    if (!quiet) {
        vscode.window.showInformationMessage('BEAST IDE snapshot refreshed.');
    }
    return snapshot;
}

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function mascotDataUri() {
    if (dragonMascotDataUri) {
        return dragonMascotDataUri;
    }
    if (!extensionContext) {
        return '';
    }
    try {
        const file = path.join(extensionContext.extensionPath, 'media', 'beast-dragon-mascot.png');
        const encoded = fs.readFileSync(file).toString('base64');
        dragonMascotDataUri = `data:image/png;base64,${encoded}`;
    } catch {
        dragonMascotDataUri = '';
    }
    return dragonMascotDataUri;
}

function mascotHtml(label = 'BEAST dragon mascot') {
    const src = mascotDataUri();
    return src ? `<img class="mascot" src="${src}" alt="${escapeHtml(label)}">` : '';
}

function tuiCss() {
    return `
        body { background:#050607; color:#d7fbe8; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; padding:18px; }
        .shell { max-width: 1180px; margin:0 auto; }
        .hero { border:1px solid #1f3a3d; background:#071012; padding:16px; box-shadow:0 0 24px rgba(51,246,255,.08); }
        .hero { position:relative; overflow:hidden; }
        .hero .mascot { position:absolute; right:14px; top:10px; width:112px; max-height:82px; object-fit:contain; opacity:.92; filter: drop-shadow(0 0 10px rgba(166,255,63,.22)); }
        .hero-content { padding-right:132px; min-height:74px; }
        h1 { color:#a6ff3f; font-size:22px; margin:0 0 6px; letter-spacing:0; }
        h2 { color:#33f6ff; font-size:14px; margin:0 0 10px; }
        .muted { color:#7a8c8d; }
        .grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap:10px; margin-top:12px; }
        .card { border:1px solid #1f3a3d; background:#0b1113; padding:12px; border-radius:6px; min-height:82px; }
        .metric { color:#a6ff3f; font-size:24px; font-weight:700; }
        .warn { color:#ffd166; }
        .danger { color:#ff4d6d; }
        .cyan { color:#33f6ff; }
        pre { white-space:pre-wrap; background:#030506; border:1px solid #1f3a3d; padding:12px; overflow:auto; }
        button { background:#0b1113; color:#d7fbe8; border:1px solid #33f6ff; padding:7px 10px; border-radius:4px; margin:3px 5px 3px 0; cursor:pointer; }
        button:hover { color:#050607; background:#a6ff3f; border-color:#a6ff3f; }
        .row { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
        .pill { border:1px solid #1f3a3d; padding:3px 7px; border-radius:999px; color:#33f6ff; }
        .op { border:1px solid #1f3a3d; background:#050809; padding:10px; border-radius:4px; margin:8px 0; }
        .op.selected { border-color:#a6ff3f; }
        .op.skipped { opacity:.72; }
        .op.stale { border-color:#ff4d6d; }
        input[type="checkbox"] { accent-color:#a6ff3f; width:16px; height:16px; }
        @media (max-width: 720px) { .hero .mascot { position:static; display:block; width:96px; margin:0 0 8px auto; } .hero-content { padding-right:0; } }
        ul { padding-left:18px; }
    `;
}

function missionControlHtml(snapshot) {
    const cards = snapshot?.mission_cockpit?.cards || [];
    const queue = snapshot?.sourceplan_queue || [];
    const evidence = snapshot?.evidence_bus || {};
    const lattice = snapshot?.mission_lattice || {};
    const sessions = snapshot?.agent_sessions || {};
    const mode = snapshot?.policy?.mode_route?.selected_mode || 'scout';
    const actionScript = `
        const vscode = acquireVsCodeApi();
        document.querySelectorAll('[data-command]').forEach(button => {
            button.addEventListener('click', () => vscode.postMessage({ command: button.dataset.command }));
        });
    `;
    return `<!doctype html><html><head><meta charset="utf-8"><style>${tuiCss()}</style></head><body>
    <div class="shell">
      <div class="hero">
        ${mascotHtml()}
        <div class="hero-content">
        <h1>BEAST Mission Control</h1>
        <div class="muted">Phase 1 VS Code shell · TUI look and feel · ${escapeHtml(snapshot?.workspace_root || '')}</div>
        <div class="row">
          <span class="pill">mode ${escapeHtml(mode)}</span>
          <span class="pill">Code Cortex ${escapeHtml(snapshot?.code_cortex?.front_door || 'code_cortex')}</span>
          <span class="pill">ADR ${escapeHtml(snapshot?.policy?.architecture_decisions?.status || 'accepted_implemented')}</span>
        </div>
        <div class="row" style="margin-top:10px">
          <button data-command="sourcePlanFromSelection">SourcePlan from Selection</button>
          <button data-command="openSourceWorkbench">Source Workbench</button>
          <button data-command="showEvidence">Evidence</button>
          <button data-command="showCodeCortex">Code Cortex</button>
          <button data-command="showPolicyGate">Policy Gate</button>
          <button data-command="showAgentSessions">Agent Sessions</button>
          <button data-command="showWorktrees">Worktrees</button>
          <button data-command="startIdeEventBus">Live Events</button>
          <button data-command="createAgentSession">New Agent Session</button>
          <button data-command="createWorktreeMission">Create Worktree</button>
          <button data-command="replayLatticeCandidate">Replay Lattice</button>
        </div>
        </div>
      </div>
      <div class="grid">
        <div class="card"><h2>SourcePlans</h2><div class="metric">${queue.length}</div><div class="muted">queued plans</div></div>
        <div class="card"><h2>Evidence</h2><div class="metric">${evidence.total || evidence.count || 0}</div><div class="muted">indexed receipts</div></div>
        <div class="card"><h2>Lattice</h2><div class="metric">${lattice.cell_count || 0}</div><div class="muted">verified edit cells</div></div>
        <div class="card"><h2>Agent Sessions</h2><div class="metric">${sessions.count || 0}</div><div class="muted">mode, budget, evidence, tools</div></div>
        <div class="card"><h2>Worktrees</h2><div class="metric">${snapshot?.worktrees?.count || 0}</div><div class="muted">mission sandboxes</div></div>
      </div>
      <div class="grid">
        ${cards.slice(0, 12).map(card => `<div class="card"><h2>${escapeHtml(card.title || card.card_id)}</h2><div class="cyan">${escapeHtml(card.value ?? card.status ?? '')}</div><div class="muted">${escapeHtml(card.detail || card.summary || '')}</div></div>`).join('')}
      </div>
      <div class="card" style="margin-top:12px"><h2>SourcePlan Queue</h2>
        ${queue.length ? `<ul>${queue.slice(0, 8).map(plan => `<li><span class="cyan">${escapeHtml(plan.plan_id || 'plan')}</span> <span class="muted">${escapeHtml(plan.status || '')}</span></li>`).join('')}</ul>` : '<div class="muted">No queued SourcePlans yet.</div>'}
      </div>
    </div><script>${actionScript}</script></body></html>`;
}

function sourceWorkbenchHtml(plan, scorecard) {
    const workbench = scorecard?.source_workbench || {};
    const policy = workbench.policy_decision || {};
    const replay = workbench.lattice_replay || {};
    const tests = workbench.verification?.suggested_tests || scorecard?.suggested_tests || [];
    const preview = currentPreview || {};
    const operations = preview.operations || [];
    const sourceOps = operations.filter(op => op.source_edit || !op.beast_managed);
    const selectedCount = sourceOps.filter(op => op.selected).length;
    const operationRows = sourceOps.length ? sourceOps.map(op => {
        const checked = op.selected ? 'checked' : '';
        const stale = op.stale_reason ? `<div class="danger">${escapeHtml(op.stale_reason)}</div>` : '';
        const ranges = (op.changed_ranges || []).map(r => `${r.new_start || '?'}-${r.new_end || '?'}`).join(', ');
        return `<div class="op ${op.selected ? 'selected' : 'skipped'} ${op.stale_reason ? 'stale' : ''}">
          <label class="row">
            <input type="checkbox" data-op-id="${escapeHtml(op.op_id)}" ${checked}>
            <span class="cyan">${escapeHtml(op.op_id)}</span>
            <span>${escapeHtml(op.path)}</span>
            <span class="pill">${escapeHtml(op.changed_line_count || 0)} lines</span>
          </label>
          <div class="muted">${escapeHtml(op.description || op.op || '')}</div>
          ${ranges ? `<div class="muted">ranges ${escapeHtml(ranges)}</div>` : ''}
          ${stale}
        </div>`;
    }).join('') : '<div class="muted">Preview the plan to load selectable operations.</div>';
    return `<!doctype html><html><head><meta charset="utf-8"><style>${tuiCss()}</style></head><body>
    <div class="shell">
      <div class="hero">
        ${mascotHtml()}
        <div class="hero-content">
        <h1>Source Workbench</h1>
        <div class="muted">${escapeHtml(plan?.plan_id || 'draft')} · ${escapeHtml(plan?.objective || '')}</div>
        <div class="row"><span class="pill">risk ${escapeHtml(scorecard?.risk_level || 'unknown')}</span><span class="pill">decision ${escapeHtml(scorecard?.decision || '')}</span><span class="pill">policy ${escapeHtml(policy.decision || '')}</span></div>
        <div class="row" style="margin-top:10px"><button data-command="previewHunks">Preview Hunks</button><button data-command="openSideBySidePreview">Side-by-Side</button><button data-command="switchSourcePlanSession">Sessions</button><button data-command="selectAllHunks">Select All</button><button data-command="clearHunks">Clear</button><button data-command="applySelectedHunks">Apply Selected</button><button data-command="showEvidence">Evidence</button><button data-command="replayLatticeCandidate">Replay Lattice</button></div>
        </div>
      </div>
      <div class="grid">
        <div class="card"><h2>Selected Hunks</h2><div class="metric">${escapeHtml(selectedCount)}</div><div class="muted">${escapeHtml(sourceOps.length)} source operations · ${escapeHtml(preview.stale_count || 0)} stale</div></div>
        <div class="card"><h2>Policy Gate</h2><div class="${policy.approval_required ? 'warn' : 'cyan'}">${escapeHtml(policy.decision || 'unknown')}</div><div class="muted">approval ${policy.approval_required ? 'required' : 'not required'} · verify ${policy.verification_required !== false}</div></div>
        <div class="card"><h2>Lattice Replay</h2><div class="${replay.visible ? 'cyan' : 'muted'}">${escapeHtml(replay.reuse_mode || 'none')}</div><div class="muted">strength ${escapeHtml(replay.match_strength || 0)}</div></div>
        <div class="card"><h2>Rollback</h2><div class="cyan">${workbench.rollback?.required ? 'required' : 'not required'}</div><div class="muted">worktree ${workbench.rollback?.worktree_recommended ? 'recommended' : 'optional'}</div></div>
      </div>
      <div class="card" style="margin-top:12px"><h2>Selectable Operations</h2>${operationRows}</div>
      <div class="card" style="margin-top:12px"><h2>Suggested Tests</h2>${tests.length ? `<ul>${tests.map(t => `<li>${escapeHtml(t)}</li>`).join('')}</ul>` : '<div class="muted">No targeted tests suggested yet.</div>'}</div>
      <div class="card" style="margin-top:12px"><h2>Raw Scorecard</h2><pre>${escapeHtml(JSON.stringify(scorecard || {}, null, 2))}</pre></div>
    </div><script>
      const vscode = acquireVsCodeApi();
      document.querySelectorAll('[data-command]').forEach(b=>b.addEventListener('click',()=>vscode.postMessage({command:b.dataset.command})));
      document.querySelectorAll('input[data-op-id]').forEach(input=>input.addEventListener('change',()=>vscode.postMessage({command:'toggleOperation', opId: input.dataset.opId, selected: input.checked})));
    </script></body></html>`;
}

async function runMaintenanceCascade({ showReport = true } = {}) {
    const result = await callMcpTool('beast_run_maintenance_cascade', {
        workspace_root: workspaceFolderPath(),
        run_tests: false,
        include_extension_checks: true,
        include_markdown: true,
        timeout_seconds: 60,
    });
    lastMaintenance = result;
    const summary = result.summary || {};
    const status = String(result.status || 'unknown').toUpperCase();
    const message = `BEAST maintenance ${status}: ${summary.failed || 0} failed, ${summary.warnings || 0} warning(s), ${summary.passed || 0} passed`;
    if (result.status === 'failed') {
        vscode.window.showErrorMessage(message, 'Open report').then(choice => {
            if (choice === 'Open report') {
                openMaintenanceReport();
            }
        });
    } else if (result.status === 'warning') {
        vscode.window.showWarningMessage(message, 'Open report').then(choice => {
            if (choice === 'Open report') {
                openMaintenanceReport();
            }
        });
    } else {
        vscode.window.showInformationMessage(message);
    }
    if (showReport) {
        await openMaintenanceReport();
    }
    return result;
}

async function openMaintenanceReport() {
    if (!lastMaintenance) {
        await runMaintenanceCascade({ showReport: false });
        return;
    }
    const lines = [
        '# BEAST Maintenance Cascade',
        '',
        `Status: ${lastMaintenance.status || 'unknown'}`,
        `Workspace: ${lastMaintenance.workspace || workspaceFolderPath() || 'unknown'}`,
        '',
        '## Checks',
        '',
    ];
    for (const check of lastMaintenance.checks || []) {
        lines.push(`- ${check.name}: ${check.status} - ${check.summary || ''}`);
    }
    const next = lastMaintenance.next_actions || [];
    if (next.length) {
        lines.push('', '## Next Actions', '');
        for (const action of next) {
            lines.push(`- ${action}`);
        }
    }
    lines.push('', '## Raw JSON', '', '```json', JSON.stringify(lastMaintenance, null, 2), '```', '');
    await showVirtualDocument('BEAST-Maintenance.md', 'markdown', lines.join('\n'));
}

async function ideDoctorSnapshot() {
    const health = { ok: false, error: '' };
    try {
        const response = await fetch(`${gatewayUrl()}/health`);
        health.ok = response.ok;
        health.status = response.status;
        health.statusText = response.statusText;
        if (response.ok) {
            try {
                health.payload = await response.json();
            } catch {
                health.payload = await response.text();
            }
        }
    } catch (error) {
        health.error = error.message;
    }
    return {
        beast_object_type: 'beast_vscode_ide_doctor',
        version: '1.0',
        extension_version: '1.6.1',
        gateway_url: gatewayUrl(),
        workspace_folder: workspaceFolderPath(),
        detected_beast_root: beastWorkspaceRoot(),
        beast_command: beastCommand(),
        gateway_command: gatewayCommandLine(),
        gateway_health: health,
        mcp_registration_supported: Boolean(vscode.lm?.registerMcpServerDefinitionProvider && vscode.McpStdioServerDefinition),
        next_actions: health.ok ? [
            'Run BEAST: Open Mission Control.',
            'Run BEAST: Start Live IDE Event Bus for live cockpit updates.',
        ] : [
            'Run BEAST: Start Local Governor.',
            'If the terminal shows an old serve command, reload the window or reinstall edgek-beast-1.6.1.vsix.',
            'Confirm the terminal starts from the BEAST repo root, not only vscode-extension/.',
            `Manual fallback: ${gatewayCommandLine()}`,
        ],
    };
}

async function showIdeDoctor() {
    const snapshot = await ideDoctorSnapshot();
    const ok = snapshot.gateway_health?.ok;
    const html = `<!doctype html><html><head><meta charset="utf-8"><style>${tuiCss()}</style></head><body>
      <div class="shell">
        <div class="hero">${mascotHtml()}<div class="hero-content"><h1>BEAST IDE Doctor</h1><div class="muted">Bootstrap, gateway, extension, and workspace diagnostics.</div>
          <div class="row" style="margin-top:10px"><button data-command="start">Start Gateway</button><button data-command="refreshDoctor">Refresh</button><button data-command="openMissionControl">Mission Control</button></div>
        </div></div>
        <div class="grid">
          <div class="card"><h2>Gateway</h2><div class="${ok ? 'cyan' : 'danger'}">${ok ? 'healthy' : 'offline'}</div><div class="muted">${escapeHtml(snapshot.gateway_url)}</div></div>
          <div class="card"><h2>Extension</h2><div class="cyan">${escapeHtml(snapshot.extension_version)}</div><div class="muted">MCP registration ${snapshot.mcp_registration_supported ? 'supported' : 'fallback mode'}</div></div>
          <div class="card"><h2>BEAST Root</h2><div class="cyan">${escapeHtml(snapshot.detected_beast_root || 'not found')}</div><div class="muted">workspace ${escapeHtml(snapshot.workspace_folder || 'none')}</div></div>
          <div class="card"><h2>Command</h2><div class="cyan">${escapeHtml(snapshot.beast_command)}</div><div class="muted">${escapeHtml(snapshot.gateway_command)}</div></div>
        </div>
        <div class="card" style="margin-top:12px"><h2>Next Actions</h2><ul>${snapshot.next_actions.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul></div>
        <div class="card" style="margin-top:12px"><h2>Raw Doctor Snapshot</h2><pre>${escapeHtml(JSON.stringify(snapshot, null, 2))}</pre></div>
      </div><script>
        const vscode = acquireVsCodeApi();
        document.querySelectorAll('[data-command]').forEach(b=>b.addEventListener('click',()=>vscode.postMessage({command:b.dataset.command})));
      </script></body></html>`;
    const panel = vscode.window.createWebviewPanel('beastIdeDoctor', 'BEAST IDE Doctor', vscode.ViewColumn.Beside, { enableScripts: true });
    panel.webview.html = html;
    panel.webview.onDidReceiveMessage(async message => {
        if (message?.command === 'start') {
            await ensureGateway();
            panel.webview.html = (await doctorHtml()).html;
        } else if (message?.command === 'refreshDoctor') {
            panel.webview.html = (await doctorHtml()).html;
        } else if (message?.command === 'openMissionControl') {
            await openMissionControl(ideEventProvider);
        }
    });
}

async function doctorHtml() {
    const snapshot = await ideDoctorSnapshot();
    const ok = snapshot.gateway_health?.ok;
    return {
        snapshot,
        html: `<!doctype html><html><head><meta charset="utf-8"><style>${tuiCss()}</style></head><body>
          <div class="shell">
            <div class="hero">${mascotHtml()}<div class="hero-content"><h1>BEAST IDE Doctor</h1><div class="muted">Bootstrap, gateway, extension, and workspace diagnostics.</div>
              <div class="row" style="margin-top:10px"><button data-command="start">Start Gateway</button><button data-command="refreshDoctor">Refresh</button><button data-command="openMissionControl">Mission Control</button></div>
            </div></div>
            <div class="grid">
              <div class="card"><h2>Gateway</h2><div class="${ok ? 'cyan' : 'danger'}">${ok ? 'healthy' : 'offline'}</div><div class="muted">${escapeHtml(snapshot.gateway_url)}</div></div>
              <div class="card"><h2>Extension</h2><div class="cyan">${escapeHtml(snapshot.extension_version)}</div><div class="muted">MCP registration ${snapshot.mcp_registration_supported ? 'supported' : 'fallback mode'}</div></div>
              <div class="card"><h2>BEAST Root</h2><div class="cyan">${escapeHtml(snapshot.detected_beast_root || 'not found')}</div><div class="muted">workspace ${escapeHtml(snapshot.workspace_folder || 'none')}</div></div>
              <div class="card"><h2>Command</h2><div class="cyan">${escapeHtml(snapshot.beast_command)}</div><div class="muted">${escapeHtml(snapshot.gateway_command)}</div></div>
            </div>
            <div class="card" style="margin-top:12px"><h2>Next Actions</h2><ul>${snapshot.next_actions.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul></div>
            <div class="card" style="margin-top:12px"><h2>Raw Doctor Snapshot</h2><pre>${escapeHtml(JSON.stringify(snapshot, null, 2))}</pre></div>
          </div><script>
            const vscode = acquireVsCodeApi();
            document.querySelectorAll('[data-command]').forEach(b=>b.addEventListener('click',()=>vscode.postMessage({command:b.dataset.command})));
          </script></body></html>`
    };
}

async function prepareSourcePlan() {
    const objective = await promptObjective();
    if (!objective) {
        return;
    }
    const files = activeContextFiles();
    if (!files.length) {
        vscode.window.showWarningMessage('BEAST: open a workspace file before preparing a SourcePlan.');
        return;
    }
    const provider = await promptProvider();
    const result = await callMcpTool('beast_sourceplan_prepare', { objective, files, provider });
    if (!result.ok) {
        vscode.window.showWarningMessage(`BEAST SourcePlan failed: ${result.error || result.summary || 'unknown error'}`);
        return;
    }
    currentPlan = actionData(result);
    currentScorecard = null;
    currentPreview = null;
    saveIdeSession();
    vscode.window.showInformationMessage(`BEAST SourcePlan ready: ${result.summary || currentPlan.plan_id || 'draft'}`);
}

async function sourcePlanFromSelection() {
    const objective = await promptObjective(activeObjective());
    if (!objective) {
        return;
    }
    const files = activeContextFiles();
    if (!files.length) {
        vscode.window.showWarningMessage('BEAST: open a workspace file before preparing a SourcePlan.');
        return;
    }
    const provider = await promptProvider();
    const result = await callMcpTool('beast_sourceplan_prepare', { objective, files, provider });
    if (!result.ok) {
        vscode.window.showWarningMessage(`BEAST SourcePlan failed: ${result.error || result.summary || 'unknown error'}`);
        return;
    }
    currentPlan = actionData(result);
    currentScorecard = null;
    currentPreview = null;
    saveIdeSession();
    vscode.window.showInformationMessage(`BEAST SourcePlan ready: ${result.summary || currentPlan.plan_id || 'draft'}`);
    await scoreCurrentPlan({ quiet: true });
    await previewCurrentPlan({ quiet: true });
    await openSourceWorkbench();
}

async function scoreCurrentPlan({ quiet = false } = {}) {
    if (!currentPlan) {
        vscode.window.showWarningMessage('BEAST: prepare a SourcePlan before scoring.');
        return null;
    }
    const result = await callMcpTool('beast_sourceplan_scorecard', {
        workspace_root: workspaceFolderPath(),
        plan: currentPlan,
    });
    if (!result.ok) {
        vscode.window.showWarningMessage(`BEAST scorecard failed: ${result.error || result.summary || 'unknown error'}`);
        return null;
    }
    currentScorecard = actionData(result);
    saveIdeSession();
    if (!quiet) {
        vscode.window.showInformationMessage(`BEAST scorecard ready: ${currentScorecard.decision || currentScorecard.risk_level || 'review'}`);
    }
    return currentScorecard;
}

function selectedOperationIdsFromPreview() {
    const ops = currentPreview?.operations || [];
    return ops.filter(op => op.selected).map(op => String(op.op_id || '')).filter(Boolean);
}

function syncPlanSelectionFromPreview() {
    if (!currentPlan || !currentPreview) {
        return;
    }
    currentPlan = {
        ...currentPlan,
        selected_operations: selectedOperationIdsFromPreview(),
    };
}

async function previewCurrentPlan({ quiet = false } = {}) {
    if (!currentPlan) {
        return null;
    }
    const result = await callMcpTool('beast_sourceplan_preview_hunks', { plan: currentPlan });
    const data = actionData(result);
    currentPreview = data;
    syncPlanSelectionFromPreview();
    applyPreviewDecorations();
    updateBeastDiagnostics();
    saveIdeSession();
    if (!quiet) {
        vscode.window.showInformationMessage(result.summary || `BEAST preview ready: ${data.selected_count || 0} selected hunk(s).`);
    }
    return data;
}

function updateSourceWorkbenchHtml() {
    if (sourceWorkbenchPanel) {
        sourceWorkbenchPanel.webview.html = sourceWorkbenchHtml(currentPlan || {}, currentScorecard || {});
    }
}

function setOperationSelected(opId, selected) {
    if (!currentPreview?.operations?.length) {
        return;
    }
    currentPreview.operations = currentPreview.operations.map(op => {
        if (String(op.op_id || '') === String(opId || '')) {
            return { ...op, selected: Boolean(selected) };
        }
        return op;
    });
    currentPreview.selected_count = currentPreview.operations.filter(op => op.ok !== false && op.selected).length;
    syncPlanSelectionFromPreview();
    applyPreviewDecorations();
    updateBeastDiagnostics();
    saveIdeSession();
    updateSourceWorkbenchHtml();
}

function setAllSourceOperations(selected) {
    if (!currentPreview?.operations?.length) {
        return;
    }
    currentPreview.operations = currentPreview.operations.map(op => {
        if (op.source_edit || !op.beast_managed) {
            return { ...op, selected: Boolean(selected) };
        }
        return op;
    });
    currentPreview.selected_count = currentPreview.operations.filter(op => op.ok !== false && op.selected).length;
    syncPlanSelectionFromPreview();
    applyPreviewDecorations();
    updateBeastDiagnostics();
    saveIdeSession();
    updateSourceWorkbenchHtml();
}

function applyPreviewDecorations() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        return;
    }
    const rel = workspaceRelative(editor.document.uri.fsPath);
    const selectedRanges = [];
    const skippedRanges = [];
    const staleRanges = [];
    for (const op of currentPreview?.operations || []) {
        if (op.path !== rel) {
            continue;
        }
        for (const changed of op.changed_ranges || []) {
            const start = Math.max(0, Number(changed.new_start || changed.old_start || 1) - 1);
            const endLine = Math.min(
                Math.max(start, Number(changed.new_end || changed.old_end || start + 1) - 1),
                Math.max(0, editor.document.lineCount - 1),
            );
            const endCharacter = editor.document.lineAt(endLine).text.length;
            const range = new vscode.Range(Math.min(start, endLine), 0, endLine, endCharacter);
            const decoration = { range, hoverMessage: `BEAST ${op.op_id || 'hunk'}: ${op.selected ? 'selected' : 'skipped'}${op.stale_reason ? ` (${op.stale_reason})` : ''}` };
            if (op.stale_reason) {
                staleRanges.push(decoration);
            } else if (op.selected) {
                selectedRanges.push(decoration);
            } else {
                skippedRanges.push(decoration);
            }
        }
    }
    editor.setDecorations(selectedHunkDecoration, selectedRanges);
    editor.setDecorations(skippedHunkDecoration, skippedRanges);
    editor.setDecorations(staleHunkDecoration, staleRanges);
}

function activeDocumentRelative(document) {
    if (!document || document.uri.scheme !== 'file') {
        return '';
    }
    return workspaceRelative(document.uri.fsPath);
}

function previewOperationsForDocument(document) {
    const rel = activeDocumentRelative(document);
    if (!rel) {
        return [];
    }
    return (currentPreview?.operations || []).filter(op => op.path === rel);
}

function updateBeastDiagnostics() {
    if (!beastDiagnostics) {
        return;
    }
    beastDiagnostics.clear();
    for (const document of vscode.workspace.textDocuments) {
        const diagnostics = [];
        const rel = activeDocumentRelative(document);
        if (rel && currentScorecard?.risk_level === 'high') {
            const risk = new vscode.Diagnostic(
                new vscode.Range(0, 0, 0, document.lineAt(0).text.length),
                'BEAST high-risk SourcePlan: review Policy Gate and consider worktree isolation before apply.',
                vscode.DiagnosticSeverity.Information,
            );
            risk.source = 'BEAST';
            risk.code = 'high-risk-sourceplan';
            diagnostics.push(risk);
        }
        if (rel && currentScorecard?.worktree_recommendation?.recommended) {
            const worktree = new vscode.Diagnostic(
                new vscode.Range(0, 0, 0, document.lineAt(0).text.length),
                'BEAST recommends an isolated worktree for this SourcePlan.',
                vscode.DiagnosticSeverity.Information,
            );
            worktree.source = 'BEAST';
            worktree.code = 'worktree-recommended';
            diagnostics.push(worktree);
        }
        for (const op of previewOperationsForDocument(document)) {
            if (!op.stale_reason) {
                continue;
            }
            const changed = (op.changed_ranges || [])[0] || {};
            const start = Math.max(0, Number(changed.new_start || changed.old_start || 1) - 1);
            const line = Math.min(start, Math.max(0, document.lineCount - 1));
            const range = new vscode.Range(line, 0, line, document.lineAt(line).text.length);
            const diagnostic = new vscode.Diagnostic(
                range,
                `BEAST stale SourcePlan context: ${op.stale_reason}`,
                vscode.DiagnosticSeverity.Warning,
            );
            diagnostic.source = 'BEAST';
            diagnostic.code = 'stale-sourceplan-context';
            diagnostics.push(diagnostic);
        }
        if (diagnostics.length) {
            beastDiagnostics.set(document.uri, diagnostics);
        }
    }
}

class BeastCodeLensProvider {
    provideCodeLenses(document) {
        if (document.uri.scheme !== 'file' || !workspaceFolderPath()) {
            return [];
        }
        const top = new vscode.Range(0, 0, 0, 0);
        const lenses = [
            new vscode.CodeLens(top, { title: 'BEAST: SourcePlan from selection', command: 'edgekBeast.sourcePlanFromSelection' }),
            new vscode.CodeLens(top, { title: 'BEAST: Related tests/routes', command: 'edgekBeast.jumpRelatedContext' }),
            new vscode.CodeLens(top, { title: 'BEAST: switch plan session', command: 'edgekBeast.switchSourcePlanSession' }),
        ];
        const ops = previewOperationsForDocument(document);
        const selected = ops.filter(op => op.selected).length;
        if (ops.length) {
            lenses.push(new vscode.CodeLens(top, { title: `BEAST: ${selected}/${ops.length} hunks selected`, command: 'edgekBeast.openSourceWorkbench' }));
            lenses.push(new vscode.CodeLens(top, { title: 'BEAST: side-by-side preview', command: 'edgekBeast.openSideBySidePreview' }));
        }
        if (ops.some(op => op.stale_reason)) {
            lenses.push(new vscode.CodeLens(top, { title: 'BEAST: refresh stale preview', command: 'edgekBeast.refreshSourcePlanPreview' }));
        }
        return lenses;
    }
}

class BeastHoverProvider {
    provideHover(document, position) {
        const hits = [];
        for (const op of previewOperationsForDocument(document)) {
            for (const changed of op.changed_ranges || []) {
                const start = Math.max(0, Number(changed.new_start || changed.old_start || 1) - 1);
                const end = Math.max(start, Number(changed.new_end || changed.old_end || start + 1) - 1);
                if (position.line >= start && position.line <= end) {
                    hits.push(op);
                }
            }
        }
        if (!hits.length) {
            return undefined;
        }
        const md = new vscode.MarkdownString();
        md.isTrusted = true;
        md.appendMarkdown('**BEAST SourcePlan**\n\n');
        for (const op of hits.slice(0, 4)) {
            md.appendMarkdown(`- \`${op.op_id || 'hunk'}\` ${op.selected ? 'selected' : 'skipped'}: ${op.description || op.op || 'operation'}\n`);
            if (op.stale_reason) {
                md.appendMarkdown(`  - stale: ${op.stale_reason}\n`);
            }
        }
        md.appendMarkdown('\n[Open Source Workbench](command:edgekBeast.openSourceWorkbench)');
        return new vscode.Hover(md);
    }
}

async function jumpRelatedContext() {
    const file = activeContextFiles()[0];
    if (!file) {
        vscode.window.showWarningMessage('BEAST: open a workspace file before asking Code Cortex for related context.');
        return;
    }
    const params = new URLSearchParams();
    const root = workspaceFolderPath();
    if (root) params.set('root_path', root);
    params.set('path', file);
    params.set('limit', '80');
    const data = await getJson(`/edgek/ide/related-context?${params.toString()}`);
    const candidates = (data.related || []).map(item => ({
        label: item.path,
        description: item.relationship_kind || 'related',
        detail: item.summary || item.reason || '',
    })).filter(item => item.label);
    const choices = candidates.slice(0, 40);
    if (!choices.length) {
        await showVirtualDocument('BEAST-Related-Context.json', 'json', JSON.stringify(data, null, 2));
        return;
    }
    const picked = await vscode.window.showQuickPick(choices, {
        title: 'BEAST Related Tests / Routes',
        placeHolder: 'Choose a related file from Code Cortex',
    });
    if (!picked) {
        return;
    }
    const full = path.join(workspaceFolderPath(), picked.label);
    const doc = await vscode.workspace.openTextDocument(vscode.Uri.file(full));
    await vscode.window.showTextDocument(doc, { preview: true });
}

async function openSideBySidePreview() {
    if (!currentPreview) {
        await previewCurrentPlan({ quiet: true });
    }
    const file = activeContextFiles()[0];
    const op = (currentPreview?.operations || []).find(item => item.path === file && item.selected)
        || (currentPreview?.operations || []).find(item => item.path === file)
        || (currentPreview?.operations || []).find(item => item.source_edit || !item.beast_managed);
    if (!op) {
        vscode.window.showWarningMessage('BEAST: no preview operation is available for side-by-side view.');
        return;
    }
    const label = `${op.op_id || 'hunk'}-${path.basename(op.path || 'preview')}`;
    const oldUri = virtualDocumentUri(`${label}.old`, op.old_text || '');
    const newUri = virtualDocumentUri(`${label}.new`, op.new_text || op.next_text || '');
    await vscode.commands.executeCommand('vscode.diff', oldUri, newUri, `BEAST Preview: ${op.path || label}`);
}

async function switchSourcePlanSession() {
    const sessions = extensionContext?.workspaceState.get('edgekBeast.planSessions') || {};
    const choices = Object.entries(sessions).map(([planId, session]) => ({
        label: planId,
        description: session?.plan?.objective || '',
        detail: session?.savedAt ? new Date(session.savedAt).toLocaleString() : '',
        session,
    }));
    if (!choices.length) {
        vscode.window.showInformationMessage('BEAST: no saved SourcePlan sessions yet.');
        return;
    }
    const picked = await vscode.window.showQuickPick(choices, {
        title: 'BEAST SourcePlan Sessions',
        placeHolder: 'Switch active governed edit session',
    });
    if (!picked) {
        return;
    }
    currentPlan = picked.session.plan || null;
    currentScorecard = picked.session.scorecard || null;
    currentPreview = picked.session.preview || null;
    applyPreviewDecorations();
    updateBeastDiagnostics();
    updateSourceWorkbenchHtml();
    vscode.window.showInformationMessage(`BEAST SourcePlan session restored: ${picked.label}`);
}

async function refreshSourcePlanPreview() {
    if (!currentPlan) {
        vscode.window.showWarningMessage('BEAST: no active SourcePlan session to refresh.');
        return;
    }
    await scoreCurrentPlan({ quiet: true });
    await previewCurrentPlan({ quiet: true });
    updateSourceWorkbenchHtml();
    vscode.window.showInformationMessage('BEAST SourcePlan scorecard and preview refreshed.');
}

async function openMissionControl(ideProvider) {
    const snapshot = await refreshIdeSnapshot(ideProvider, { quiet: true });
    const panel = vscode.window.createWebviewPanel(
        'beastMissionControl',
        'BEAST Mission Control',
        vscode.ViewColumn.Beside,
        { enableScripts: true },
    );
    panel.webview.html = missionControlHtml(snapshot);
    panel.webview.onDidReceiveMessage(async message => {
        await handleIdeWebviewCommand(message, ideProvider);
    });
}

async function openSourceWorkbench() {
    if (!currentPlan) {
        await sourcePlanFromSelection();
        return;
    }
    if (!currentScorecard) {
        await scoreCurrentPlan({ quiet: true });
    }
    if (!currentPreview) {
        await previewCurrentPlan({ quiet: true });
    }
    const panel = vscode.window.createWebviewPanel(
        'beastSourceWorkbench',
        'BEAST Source Workbench',
        vscode.ViewColumn.Beside,
        { enableScripts: true },
    );
    sourceWorkbenchPanel = panel;
    panel.webview.html = sourceWorkbenchHtml(currentPlan, currentScorecard || {});
    panel.webview.onDidReceiveMessage(async message => {
        await handleIdeWebviewCommand(message);
    });
    panel.onDidDispose(() => {
        if (sourceWorkbenchPanel === panel) {
            sourceWorkbenchPanel = null;
        }
    });
}

async function showEvidence() {
    const root = workspaceFolderPath();
    const params = new URLSearchParams();
    if (root) {
        params.set('root_path', root);
    }
    params.set('limit', '30');
    const data = await getJson(`/edgek/evidence-bus/summary?${params.toString()}`);
    const rows = data.items || data.receipts || data.records || data.recent || [];
    const html = `<!doctype html><html><head><meta charset="utf-8"><style>${tuiCss()}</style></head><body>
      <div class="shell">
        <div class="hero">${mascotHtml()}<div class="hero-content"><h1>Evidence Bus</h1><div class="muted">${escapeHtml(root || 'workspace')} · ${escapeHtml(data.total || data.count || rows.length)} receipt(s)</div></div></div>
        <div class="card" style="margin-top:12px"><h2>Recent Receipts</h2>
          ${rows.length ? rows.slice(0, 30).map(item => `<pre>${escapeHtml(JSON.stringify(item, null, 2))}</pre>`).join('') : '<div class="muted">No evidence receipts returned by the gateway.</div>'}
        </div>
      </div></body></html>`;
    const panel = vscode.window.createWebviewPanel('beastEvidenceBus', 'BEAST Evidence Bus', vscode.ViewColumn.Beside, { enableScripts: true });
    panel.webview.html = html;
}

async function showCodeCortex() {
    const root = workspaceFolderPath();
    const file = activeContextFiles()[0] || '';
    const query = activeObjective();
    const params = new URLSearchParams();
    if (root) params.set('root_path', root);
    params.set('q', query);
    params.set('limit', '20');
    const context = await getJson(`/edgek/code-cortex/editing-context?${params.toString()}`);
    let fileSummary = {};
    let dependents = {};
    if (file) {
        const fileParams = new URLSearchParams();
        if (root) fileParams.set('root_path', root);
        fileParams.set('path', file);
        fileSummary = await getJson(`/edgek/code-cortex/file-summary?${fileParams.toString()}`);
        dependents = await getJson(`/edgek/code-cortex/dependents?${fileParams.toString()}&limit=30`);
    }
    const html = `<!doctype html><html><head><meta charset="utf-8"><style>${tuiCss()}</style></head><body>
      <div class="shell">
        <div class="hero">${mascotHtml()}<div class="hero-content"><h1>Code Cortex</h1><div class="muted">${escapeHtml(file || query)}</div>
          <div class="row" style="margin-top:10px"><button data-command="jumpRelatedContext">Related Tests/Routes</button><button data-command="sourcePlanFromSelection">SourcePlan from Selection</button></div>
        </div></div>
        <div class="grid">
          <div class="card"><h2>Front Door</h2><div class="cyan">${escapeHtml(context.front_door || context.context_front_door || 'code_cortex')}</div><div class="muted">${escapeHtml(context.adapter || '')}</div></div>
          <div class="card"><h2>Dependents</h2><div class="metric">${escapeHtml(dependents.dependent_count || (dependents.dependents || []).length || 0)}</div><div class="muted">related files</div></div>
        </div>
        <div class="card" style="margin-top:12px"><h2>File Summary</h2><pre>${escapeHtml(JSON.stringify(fileSummary, null, 2))}</pre></div>
        <div class="card" style="margin-top:12px"><h2>Editing Context</h2><pre>${escapeHtml(JSON.stringify(context, null, 2))}</pre></div>
      </div><script>const vscode = acquireVsCodeApi(); document.querySelectorAll('[data-command]').forEach(b=>b.addEventListener('click',()=>vscode.postMessage({command:b.dataset.command})));</script></body></html>`;
    const panel = vscode.window.createWebviewPanel('beastCodeCortex', 'BEAST Code Cortex', vscode.ViewColumn.Beside, { enableScripts: true });
    panel.webview.html = html;
    panel.webview.onDidReceiveMessage(async message => handleIdeWebviewCommand(message));
}

async function showPolicyGate() {
    if (currentPlan && !currentScorecard) {
        await scoreCurrentPlan({ quiet: true });
    }
    const policy = currentScorecard?.policy_gate_result || currentScorecard?.source_workbench?.policy_decision || lastIdeSnapshot?.policy || {};
    const mode = lastIdeSnapshot?.policy?.mode_route || currentScorecard?.mode_route || {};
    const html = `<!doctype html><html><head><meta charset="utf-8"><style>${tuiCss()}</style></head><body>
      <div class="shell">
        <div class="hero">${mascotHtml()}<div class="hero-content"><h1>Policy Gate</h1><div class="muted">One decision surface for mode, SourcePlan, safety, and ADR state.</div></div></div>
        <div class="grid">
          <div class="card"><h2>Decision</h2><div class="cyan">${escapeHtml(policy.decision || mode.decision || 'not scored')}</div><div class="muted">approval ${policy.approval_required ? 'required' : 'not required'}</div></div>
          <div class="card"><h2>Mode</h2><div class="cyan">${escapeHtml(mode.selected_mode || mode.mode || 'unknown')}</div><div class="muted">${escapeHtml(mode.why || '')}</div></div>
        </div>
        <div class="card" style="margin-top:12px"><h2>Policy Details</h2><pre>${escapeHtml(JSON.stringify({ policy, mode, architecture: lastIdeSnapshot?.policy?.architecture_decisions || {} }, null, 2))}</pre></div>
      </div></body></html>`;
    const panel = vscode.window.createWebviewPanel('beastPolicyGate', 'BEAST Policy Gate', vscode.ViewColumn.Beside, { enableScripts: true });
    panel.webview.html = html;
}

async function fetchAgentSessions() {
    await ensureGateway();
    const params = new URLSearchParams();
    const root = workspaceFolderPath();
    if (root) params.set('root_path', root);
    return getJson(`/edgek/ide/agent-sessions?${params.toString()}`);
}

function agentSessionCardsHtml(data) {
    const sessions = data.sessions || [];
    if (!sessions.length) {
        return '<div class="card" style="margin-top:12px"><h2>No Agent Sessions</h2><div class="muted">Create a session to track mode, budget, tools, files, evidence, and outputs.</div></div>';
    }
    return `<div class="grid">${sessions.map(session => `
      <div class="card">
        <h2>${escapeHtml(session.agent_id || session.session_id)}</h2>
        <div class="row"><span class="pill">${escapeHtml(session.status || 'unknown')}</span><span class="pill">${escapeHtml(session.mode || 'mode')}</span><span class="pill">${escapeHtml(session.provider || 'local')}</span></div>
        <div class="muted" style="margin-top:6px">${escapeHtml(session.objective || '')}</div>
        <div class="muted">files ${(session.files || []).length} · tools ${(session.tools || []).length} · evidence ${(session.evidence || []).length}</div>
        <div class="row" style="margin-top:10px">
          <button data-command="pauseAgentSession" data-session-id="${escapeHtml(session.session_id)}">Pause</button>
          <button data-command="resumeAgentSession" data-session-id="${escapeHtml(session.session_id)}">Resume</button>
          <button data-command="agentSessionToSourcePlan" data-session-id="${escapeHtml(session.session_id)}">SourcePlan</button>
          <button data-command="cancelAgentSession" data-session-id="${escapeHtml(session.session_id)}">Cancel</button>
        </div>
      </div>`).join('')}</div>`;
}

async function showAgentSessions() {
    const data = await fetchAgentSessions();
    const html = `<!doctype html><html><head><meta charset="utf-8"><style>${tuiCss()}</style></head><body>
      <div class="shell">
        <div class="hero">${mascotHtml()}<div class="hero-content"><h1>Agent Session Workspace</h1><div class="muted">Persistent agent mode, budget, evidence, tools, files, and SourcePlan conversion.</div>
          <div class="row" style="margin-top:10px"><button data-command="createAgentSession">Create Session</button><button data-command="refreshIdeSnapshot">Refresh</button></div>
        </div></div>
        ${agentSessionCardsHtml(data)}
        <div class="card" style="margin-top:12px"><h2>Registry</h2><pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre></div>
      </div><script>
        const vscode = acquireVsCodeApi();
        document.querySelectorAll('[data-command]').forEach(b=>b.addEventListener('click',()=>vscode.postMessage({command:b.dataset.command, sessionId:b.dataset.sessionId})));
      </script></body></html>`;
    const panel = vscode.window.createWebviewPanel('beastAgentSessions', 'BEAST Agent Sessions', vscode.ViewColumn.Beside, { enableScripts: true });
    panel.webview.html = html;
    panel.webview.onDidReceiveMessage(async message => handleIdeWebviewCommand(message));
}

async function createAgentSession() {
    const objective = await promptObjective(activeObjective());
    if (!objective) return;
    const mode = await vscode.window.showQuickPick(['architect', 'implementer', 'reviewer', 'scout', 'evidence'], {
        title: 'BEAST Agent Session Mode',
        placeHolder: 'Modes are permission boundaries',
    }) || 'architect';
    const result = await postJson('/edgek/ide/agent-sessions/create', {
        root_path: workspaceFolderPath(),
        objective,
        mode,
        provider: await promptProvider(),
        files: activeContextFiles(),
        tools: mode === 'implementer' ? ['sourceplan', 'code_cortex', 'evidence_bus'] : ['code_cortex', 'evidence_bus'],
        budget: { tokens: Number(config().get('maxTokens') || 4000), seconds: 0, cost_usd: 0.0 },
    });
    currentAgentSession = result.session || null;
    vscode.window.showInformationMessage(`BEAST agent session created: ${currentAgentSession?.session_id || 'session'}`);
    await showAgentSessions();
}

async function pickAgentSession(title = 'BEAST Agent Session') {
    const data = await fetchAgentSessions();
    const sessions = data.sessions || [];
    if (!sessions.length) {
        vscode.window.showInformationMessage('BEAST: no agent sessions yet.');
        return null;
    }
    const picked = await vscode.window.showQuickPick(sessions.map(session => ({
        label: session.agent_id || session.session_id,
        description: `${session.status || 'unknown'} · ${session.mode || 'mode'}`,
        detail: session.objective || '',
        session,
    })), { title });
    return picked?.session || null;
}

async function agentSessionAction(action, sessionId) {
    const session = sessionId ? { session_id: sessionId } : await pickAgentSession(`BEAST ${action} Agent Session`);
    if (!session?.session_id) return null;
    let payload = { root_path: workspaceFolderPath(), session_id: session.session_id };
    if (action === 'cancel') {
        const reason = await vscode.window.showInputBox({ title: 'Cancel BEAST Agent Session', prompt: 'Reason for evidence receipt', value: 'operator cancelled from VS Code' });
        if (!reason) return null;
        payload.reason = reason;
    }
    const result = await postJson(`/edgek/ide/agent-sessions/${action}`, payload);
    currentAgentSession = result.session || currentAgentSession;
    vscode.window.showInformationMessage(`BEAST agent session ${action}: ${session.session_id}`);
    return result;
}

async function agentSessionToSourcePlan(sessionId) {
    const session = sessionId ? { session_id: sessionId } : await pickAgentSession('Convert Agent Session to SourcePlan');
    if (!session?.session_id) return;
    const output = await vscode.window.showInputBox({
        title: 'BEAST Agent Output Summary',
        prompt: 'Optional: paste/summarize the agent output. BEAST will create an advisory SourcePlan draft, not apply edits.',
        value: '',
    });
    const result = await postJson('/edgek/ide/agent-sessions/sourceplan-draft', {
        root_path: workspaceFolderPath(),
        session_id: session.session_id,
        output: output || '',
    });
    if (!result.ok) {
        vscode.window.showWarningMessage(`BEAST SourcePlan draft failed: ${result.error || 'unknown error'}`);
        return;
    }
    currentPlan = result.plan;
    currentScorecard = null;
    currentPreview = null;
    saveIdeSession();
    vscode.window.showInformationMessage(`BEAST SourcePlan draft ready: ${currentPlan.plan_id}`);
    await openSourceWorkbench();
}

async function showWorktrees() {
    const result = await callMcpTool('beast_worktree_list', { workspace_root: workspaceFolderPath() });
    const data = actionData(result);
    const tasks = data.tasks || data.worktrees || [];
    const cards = tasks.length ? `<div class="grid">${tasks.map(task => `
      <div class="card">
        <h2>${escapeHtml(task.task_id || task.branch || 'mission')}</h2>
        <div class="row"><span class="pill">${escapeHtml(task.status || 'unknown')}</span><span class="pill">${escapeHtml(task.active_mode || task.mode || 'mode')}</span><span class="pill">${escapeHtml(task.risk || 'risk')}</span></div>
        <div class="muted" style="margin-top:6px">${escapeHtml(task.objective || '')}</div>
        <div class="muted">${escapeHtml(task.branch || '')}</div>
        <div class="row" style="margin-top:10px">
          <button data-command="openWorktreeMission" data-task-id="${escapeHtml(task.task_id)}">Open</button>
          <button data-command="runWorktreeVerifier" data-task-id="${escapeHtml(task.task_id)}">Verify</button>
          <button data-command="promoteWorktreeMission" data-task-id="${escapeHtml(task.task_id)}">Promote</button>
          <button data-command="closeWorktreeMission" data-task-id="${escapeHtml(task.task_id)}">Close</button>
        </div>
      </div>`).join('')}</div>` : '<div class="card" style="margin-top:12px"><h2>No Worktree Missions</h2><div class="muted">Create a mission worktree to isolate risky or parallel edits.</div></div>';
    const html = `<!doctype html><html><head><meta charset="utf-8"><style>${tuiCss()}</style></head><body>
      <div class="shell">
        <div class="hero">${mascotHtml()}<div class="hero-content"><h1>Worktrees</h1><div class="muted">Isolated BEAST missions and promotion surfaces.</div>
          <div class="row" style="margin-top:10px"><button data-command="createWorktreeMission">Create Worktree</button></div>
        </div></div>
        ${cards}
        <div class="card" style="margin-top:12px"><h2>Worktree Registry</h2><pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre></div>
      </div><script>const vscode = acquireVsCodeApi(); document.querySelectorAll('[data-command]').forEach(b=>b.addEventListener('click',()=>vscode.postMessage({command:b.dataset.command, taskId:b.dataset.taskId})));</script></body></html>`;
    const panel = vscode.window.createWebviewPanel('beastWorktrees', 'BEAST Worktrees', vscode.ViewColumn.Beside, { enableScripts: true });
    panel.webview.html = html;
    panel.webview.onDidReceiveMessage(async message => handleIdeWebviewCommand(message));
}

async function createWorktreeMission() {
    const objective = await promptObjective(activeObjective());
    if (!objective) {
        return;
    }
    const result = await callMcpTool('beast_worktree_create', {
        workspace_root: workspaceFolderPath(),
        objective,
        risk: 'medium',
        mode: 'implementer',
        provider: await promptProvider(),
    });
    const task = actionData(result).task || result.task || {};
    const open = await vscode.window.showInformationMessage(
        `BEAST worktree mission created: ${task.task_id || 'mission'}`,
        'Open Worktree',
        'Show Missions',
    );
    if (open === 'Open Worktree') {
        await openWorktreeMission(task.task_id);
    } else if (open === 'Show Missions') {
        await showWorktrees();
    } else {
        await showVirtualDocument('BEAST-Worktree-Mission.json', 'json', JSON.stringify(result, null, 2));
    }
}

async function pickWorktreeTask(title = 'BEAST Worktree Mission') {
    const result = await callMcpTool('beast_worktree_list', { workspace_root: workspaceFolderPath() });
    const tasks = (actionData(result).tasks || []).filter(task => task.task_id);
    if (!tasks.length) {
        vscode.window.showInformationMessage('BEAST: no worktree missions yet.');
        return null;
    }
    const picked = await vscode.window.showQuickPick(tasks.map(task => ({
        label: task.task_id,
        description: `${task.status || 'unknown'} · ${task.risk || 'risk'} · ${task.active_mode || 'mode'}`,
        detail: task.objective || task.worktree_path || '',
        task,
    })), { title });
    return picked?.task || null;
}

async function openWorktreeMission(taskId) {
    const task = taskId ? { task_id: taskId } : await pickWorktreeTask('Open BEAST Worktree Mission');
    if (!task?.task_id) return;
    const result = await callMcpTool('beast_worktree_status', { workspace_root: workspaceFolderPath(), task_id: task.task_id });
    const data = actionData(result);
    const target = data.worktree_path || data.task?.worktree_path || '';
    if (!target) {
        vscode.window.showWarningMessage('BEAST: worktree path unavailable.');
        return;
    }
    const choice = await vscode.window.showInformationMessage(`Open worktree ${task.task_id}?`, 'Open Current Window', 'Open New Window');
    if (choice === 'Open Current Window') {
        await vscode.commands.executeCommand('vscode.openFolder', vscode.Uri.file(target), false);
    } else if (choice === 'Open New Window') {
        await vscode.commands.executeCommand('vscode.openFolder', vscode.Uri.file(target), true);
    }
}

async function runWorktreeVerifier(taskId) {
    const task = taskId ? { task_id: taskId } : await pickWorktreeTask('Verify BEAST Worktree Mission');
    if (!task?.task_id) return;
    const commandText = await vscode.window.showInputBox({
        title: 'BEAST Worktree Verifier',
        prompt: 'Command to run in the mission worktree',
        value: 'python3 -m pytest -q',
    });
    if (!commandText) return;
    const result = await postJson('/edgek/ide/worktree-mission/test', {
        root_path: workspaceFolderPath(),
        task_id: task.task_id,
        command: commandText.split(/\s+/).filter(Boolean),
        timeout: 120,
    });
    await showVirtualDocument('BEAST-Worktree-Verifier.json', 'json', JSON.stringify(result, null, 2));
}

async function promoteWorktreeMission(taskId) {
    const task = taskId ? { task_id: taskId } : await pickWorktreeTask('Promote BEAST Worktree Mission');
    if (!task?.task_id) return;
    const answer = await vscode.window.showWarningMessage(
        'Promote this worktree? BEAST requires explicit approval and passing verifier evidence.',
        { modal: true },
        'Promote',
    );
    if (answer !== 'Promote') return;
    const result = await postJson('/edgek/ide/worktree-mission/promote', {
        root_path: workspaceFolderPath(),
        task_id: task.task_id,
        approved: true,
        require_tests: true,
    });
    await showVirtualDocument('BEAST-Worktree-Promotion.json', 'json', JSON.stringify(result, null, 2));
}

async function closeWorktreeMission(taskId) {
    const task = taskId ? { task_id: taskId } : await pickWorktreeTask('Close BEAST Worktree Mission');
    if (!task?.task_id) return;
    const reason = await vscode.window.showInputBox({ title: 'Close BEAST Worktree Mission', prompt: 'Evidence closure reason', value: 'closed from VS Code mission panel' });
    if (!reason) return;
    const result = await postJson('/edgek/ide/worktree-mission/close', {
        root_path: workspaceFolderPath(),
        task_id: task.task_id,
        reason,
    });
    await showVirtualDocument('BEAST-Worktree-Closure.json', 'json', JSON.stringify(result, null, 2));
}

async function startIdeEventBus(provider) {
    await ensureGateway();
    if (ideEventAbort) {
        ideEventAbort.abort();
    }
    ideEventAbort = new AbortController();
    latestIdeEvents = { connected: true, startedAt: Date.now() };
    if (provider) provider.refresh();
    const params = new URLSearchParams();
    const root = workspaceFolderPath();
    const file = activeContextFiles()[0] || '';
    if (root) params.set('root_path', root);
    if (file) params.set('active_file', file);
    params.set('objective', activeObjective());
    fetch(`${gatewayUrl()}/edgek/ide/events?${params.toString()}`, { signal: ideEventAbort.signal })
        .then(async response => {
            if (!response.ok || !response.body) {
                throw new Error(`${response.status} ${response.statusText}`);
            }
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const chunks = buffer.split('\n\n');
                buffer = chunks.pop() || '';
                for (const chunk of chunks) {
                    const line = chunk.split('\n').find(item => item.startsWith('data: '));
                    if (!line) continue;
                    const event = JSON.parse(line.slice(6));
                    latestIdeEvents[event.event_type] = event;
                    latestIdeEvents.connected = true;
                    if (event.event_type === 'policy' || event.event_type === 'context') {
                        updateBeastDiagnostics();
                    }
                    if (provider) provider.refresh();
                }
            }
        })
        .catch(error => {
            if (error.name !== 'AbortError') {
                latestIdeEvents = { ...latestIdeEvents, connected: false, error: error.message };
                if (provider) provider.refresh();
                vscode.window.showWarningMessage(`BEAST live event bus stopped: ${error.message}`);
            }
        });
    vscode.window.showInformationMessage('BEAST IDE live event bus connected.');
}

async function replayLatticeCandidate() {
    if (!currentPlan) {
        vscode.window.showWarningMessage('BEAST: prepare a SourcePlan before scaffolding lattice replay.');
        return;
    }
    if (!currentScorecard) {
        await scoreCurrentPlan({ quiet: true });
    }
    const result = await callMcpTool('beast_mission_lattice_replay_scaffold', {
        workspace_root: workspaceFolderPath(),
        plan: currentPlan,
        scorecard: currentScorecard || {},
    });
    await showVirtualDocument('BEAST-Lattice-Replay.json', 'json', JSON.stringify(result, null, 2));
}

async function handleIdeWebviewCommand(message, ideProvider) {
    const command = typeof message === 'string' ? message : message?.command;
    if (command === 'sourcePlanFromSelection') {
        return sourcePlanFromSelection();
    }
    if (command === 'openSourceWorkbench') {
        return openSourceWorkbench();
    }
    if (command === 'showEvidence') {
        return showEvidence();
    }
    if (command === 'showCodeCortex') {
        return showCodeCortex();
    }
    if (command === 'showPolicyGate') {
        return showPolicyGate();
    }
    if (command === 'showAgentSessions') {
        return showAgentSessions();
    }
    if (command === 'createAgentSession') {
        return createAgentSession();
    }
    if (command === 'pauseAgentSession') {
        return agentSessionAction('pause', message?.sessionId);
    }
    if (command === 'resumeAgentSession') {
        return agentSessionAction('resume', message?.sessionId);
    }
    if (command === 'cancelAgentSession') {
        return agentSessionAction('cancel', message?.sessionId);
    }
    if (command === 'agentSessionToSourcePlan') {
        return agentSessionToSourcePlan(message?.sessionId);
    }
    if (command === 'showWorktrees') {
        return showWorktrees();
    }
    if (command === 'startIdeEventBus') {
        return startIdeEventBus(ideEventProvider);
    }
    if (command === 'jumpRelatedContext') {
        return jumpRelatedContext();
    }
    if (command === 'openSideBySidePreview') {
        return openSideBySidePreview();
    }
    if (command === 'switchSourcePlanSession') {
        return switchSourcePlanSession();
    }
    if (command === 'refreshSourcePlanPreview') {
        return refreshSourcePlanPreview();
    }
    if (command === 'createWorktreeMission') {
        return createWorktreeMission();
    }
    if (command === 'openWorktreeMission') {
        return openWorktreeMission(message?.taskId);
    }
    if (command === 'runWorktreeVerifier') {
        return runWorktreeVerifier(message?.taskId);
    }
    if (command === 'promoteWorktreeMission') {
        return promoteWorktreeMission(message?.taskId);
    }
    if (command === 'closeWorktreeMission') {
        return closeWorktreeMission(message?.taskId);
    }
    if (command === 'replayLatticeCandidate') {
        return replayLatticeCandidate();
    }
    if (command === 'previewHunks') {
        return previewHunks();
    }
    if (command === 'selectAllHunks') {
        return setAllSourceOperations(true);
    }
    if (command === 'clearHunks') {
        return setAllSourceOperations(false);
    }
    if (command === 'toggleOperation') {
        return setOperationSelected(message.opId, message.selected);
    }
    if (command === 'applySelectedHunks') {
        return applySelectedHunks();
    }
    if (command === 'refreshIdeSnapshot') {
        return refreshIdeSnapshot(ideProvider);
    }
    return undefined;
}

async function previewHunks() {
    if (!currentPlan) {
        await prepareSourcePlan();
    }
    if (!currentPlan) {
        return;
    }
    const data = await previewCurrentPlan({ quiet: true });
    updateSourceWorkbenchHtml();
    await showVirtualDocument(`BEAST-${currentPlan.plan_id || 'sourceplan'}.diff`, 'diff', data?.diff || 'No BEAST diff returned.');
}

async function applySelectedHunks() {
    if (!currentPlan) {
        vscode.window.showWarningMessage('BEAST: prepare a SourcePlan before applying hunks.');
        return;
    }
    const answer = await vscode.window.showWarningMessage(
        'Apply selected BEAST hunks? BEAST will verify first and write rollback + Chronicle artifacts.',
        { modal: true },
        'Apply selected hunks',
    );
    if (answer !== 'Apply selected hunks') {
        return;
    }
    const result = await callMcpTool('beast_sourceplan_apply_selected', { plan: currentPlan, approved: true });
    if (!result.ok) {
        vscode.window.showErrorMessage(`BEAST apply failed: ${result.error || result.summary || 'unknown error'}`);
        return;
    }
    currentPlan = actionData(result).plan || currentPlan;
    currentPreview = null;
    currentScorecard = null;
    saveIdeSession();
    updateBeastDiagnostics();
    updateSourceWorkbenchHtml();
    vscode.window.showInformationMessage(result.summary || 'BEAST apply completed');
    await runMaintenanceCascade({ showReport: false });
}

async function selectProviderRole(statusProvider) {
    const roles = [
        'primary_patch_provider',
        'rescued_patch_provider',
        'refs_only_action_ir_generator',
        'semantic_transform_selector',
        'scout_only',
    ];
    const selected = await vscode.window.showQuickPick(roles, {
        title: 'BEAST Provider Role',
        placeHolder: 'Choose runtime role for the selected provider',
    });
    if (!selected) {
        return;
    }
    await config().update('providerRole', selected, vscode.ConfigurationTarget.Workspace);
    statusProvider.refresh();
}

async function refreshChronicle(provider) {
    try {
        const data = await getJson('/edgek/chronicle?limit=30');
        lastChronicles = data.chronicles || data.records || data.items || [];
        provider.refresh();
        vscode.window.showInformationMessage(`BEAST Chronicle loaded ${lastChronicles.length} record(s).`);
    } catch (error) {
        vscode.window.showWarningMessage(`BEAST Chronicle refresh failed: ${error.message}`);
    }
}

async function refreshRouteFitness(provider) {
    const result = await callMcpTool('beast_provider_fitness', { limit: 80 });
    lastFitness = result.providers || [];
    provider.refresh();
    vscode.window.showInformationMessage(`BEAST route fitness loaded ${lastFitness.length} provider(s).`);
}

function extractAssistantText(payload) {
    const choice = payload?.choices?.[0] || {};
    if (choice.message?.content) {
        return String(choice.message.content);
    }
    if (choice.text) {
        return String(choice.text);
    }
    if (payload?.response) {
        return String(payload.response);
    }
    return JSON.stringify(payload, null, 2);
}

async function beastChatCompletion(prompt, history = []) {
    await ensureGateway();
    const provider = await promptProvider();
    const messages = [];
    for (const item of history.slice(-8)) {
        const text = item?.content || item?.message || '';
        if (text) {
            messages.push({ role: item?.role === 'user' ? 'user' : 'assistant', content: String(text).slice(0, 4000) });
        }
    }
    messages.push({
        role: 'system',
        content: 'You are BEAST inside VS Code Chat. Route advice through BEAST governance. For file writes, instruct Copilot agent mode to use the BEAST MCP SourcePlan tools or the explicit BEAST SourcePlan/apply commands.',
    });
    messages.push({ role: 'user', content: prompt });
    const response = await fetch(`${gatewayUrl()}/proxy/v1/chat/completions?provider=${encodeURIComponent(provider)}`, {
        method: 'POST',
        headers: {
            'content-type': 'application/json',
            'X-EdgeK-Provider': provider,
        },
        body: JSON.stringify({
            model: chatModel(),
            messages,
            stream: false,
            max_tokens: Number(config().get('maxTokens') || 4000),
            temperature: 0.2,
            metadata: {
                edgek_surface: 'vscode_copilot_chat_participant',
                edgek_provider: provider,
                context_files: activeContextFiles(),
                workspace_root: workspaceFolderPath(),
                governance_level: 'governed',
            },
        }),
    });
    if (!response.ok) {
        const text = await response.text();
        throw new Error(`${response.status} ${response.statusText}: ${text.slice(0, 500)}`);
    }
    return response.json();
}

function registerBeastChatParticipant(context) {
    if (!vscode.chat?.createChatParticipant) {
        return;
    }
    const participant = vscode.chat.createChatParticipant('edgekBeast.beast', async (request, chatContext, stream) => {
        const prompt = String(request.prompt || '').trim();
        if (!prompt) {
            stream.markdown('Give BEAST a prompt, or ask Copilot agent mode to call the BEAST MCP SourcePlan tools for governed edits.');
            return;
        }
        stream.progress('Routing through BEAST governance...');
        try {
            const payload = await beastChatCompletion(prompt, chatContext.history || []);
            stream.markdown(extractAssistantText(payload));
        } catch (error) {
            stream.markdown(`BEAST route failed: ${error.message}`);
        }
    });
    participant.iconPath = vscode.Uri.file(path.join(context.extensionPath, 'media', 'beast-dragon-mascot.png'));
    participant.followupProvider = {
        provideFollowups: () => [
            { prompt: 'Prepare a governed SourcePlan for the active file', label: 'Prepare SourcePlan' },
            { prompt: 'Review the current route and explain whether Nemotron is selected', label: 'Check route' },
        ],
    };
    context.subscriptions.push(participant);
}

function activate(context) {
    extensionContext = context;
    restoreIdeSession(context);
    const statusProvider = new BeastStatusProvider();
    const chronicleProvider = new ChronicleProvider();
    const routeFitnessProvider = new RouteFitnessProvider();
    const ideProvider = new BeastIdeProvider();
    ideEventProvider = ideProvider;
    beastDiagnostics = vscode.languages.createDiagnosticCollection('BEAST');
    vscode.window.registerTreeDataProvider('beastStatus', statusProvider);
    vscode.window.registerTreeDataProvider('beastDashboard', ideProvider);
    vscode.window.registerTreeDataProvider('beastChronicle', chronicleProvider);
    vscode.window.registerTreeDataProvider('beastRouteFitness', routeFitnessProvider);

    if (vscode.lm?.registerMcpServerDefinitionProvider && vscode.McpStdioServerDefinition) {
        const provider = vscode.lm.registerMcpServerDefinitionProvider('edgekBeast', {
            provideMcpServerDefinitions: async () => {
                const folder = workspaceFolderPath();
                return [
                    new vscode.McpStdioServerDefinition(
                        'EdgeK BEAST',
                        beastCommand(),
                        ['mcp', '--workspace', folder || '.'],
                        { BEAST_WORKSPACE: folder || '.' },
                        '1.6.1',
                    )
                ];
            },
            resolveMcpServerDefinition: async (server) => {
                const folder = workspaceFolderPath();
                if (folder) {
                    server.cwd = vscode.Uri.file(folder);
                    server.env = { ...(server.env || {}), BEAST_WORKSPACE: folder };
                }
                return server;
            },
        });
        context.subscriptions.push(provider);
    }
    registerBeastChatParticipant(context);

    context.subscriptions.push(
        vscode.commands.registerCommand('edgekBeast.start', ensureGateway),
        vscode.commands.registerCommand('edgekBeast.diagnoseIdeShell', showIdeDoctor),
        vscode.commands.registerCommand('edgekBeast.sourcePlan', prepareSourcePlan),
        vscode.commands.registerCommand('edgekBeast.previewHunks', previewHunks),
        vscode.commands.registerCommand('edgekBeast.applySelectedHunks', applySelectedHunks),
        vscode.commands.registerCommand('edgekBeast.selectProviderRole', () => selectProviderRole(statusProvider)),
        vscode.commands.registerCommand('edgekBeast.refreshChronicle', () => refreshChronicle(chronicleProvider)),
        vscode.commands.registerCommand('edgekBeast.refreshRouteFitness', () => refreshRouteFitness(routeFitnessProvider)),
        vscode.commands.registerCommand('edgekBeast.runMaintenance', () => runMaintenanceCascade({ showReport: true })),
        vscode.commands.registerCommand('edgekBeast.openMaintenanceReport', openMaintenanceReport),
        vscode.commands.registerCommand('edgekBeast.refreshIdeSnapshot', () => refreshIdeSnapshot(ideProvider)),
        vscode.commands.registerCommand('edgekBeast.openMissionControl', () => openMissionControl(ideProvider)),
        vscode.commands.registerCommand('edgekBeast.sourcePlanFromSelection', sourcePlanFromSelection),
        vscode.commands.registerCommand('edgekBeast.scoreCurrentPlan', () => scoreCurrentPlan()),
        vscode.commands.registerCommand('edgekBeast.openSourceWorkbench', openSourceWorkbench),
        vscode.commands.registerCommand('edgekBeast.selectAllHunks', () => setAllSourceOperations(true)),
        vscode.commands.registerCommand('edgekBeast.clearHunks', () => setAllSourceOperations(false)),
        vscode.commands.registerCommand('edgekBeast.showEvidence', showEvidence),
        vscode.commands.registerCommand('edgekBeast.showCodeCortex', showCodeCortex),
        vscode.commands.registerCommand('edgekBeast.showPolicyGate', showPolicyGate),
        vscode.commands.registerCommand('edgekBeast.showAgentSessions', showAgentSessions),
        vscode.commands.registerCommand('edgekBeast.createAgentSession', createAgentSession),
        vscode.commands.registerCommand('edgekBeast.pauseAgentSession', () => agentSessionAction('pause')),
        vscode.commands.registerCommand('edgekBeast.resumeAgentSession', () => agentSessionAction('resume')),
        vscode.commands.registerCommand('edgekBeast.cancelAgentSession', () => agentSessionAction('cancel')),
        vscode.commands.registerCommand('edgekBeast.agentSessionToSourcePlan', () => agentSessionToSourcePlan()),
        vscode.commands.registerCommand('edgekBeast.showWorktrees', showWorktrees),
        vscode.commands.registerCommand('edgekBeast.startIdeEventBus', () => startIdeEventBus(ideProvider)),
        vscode.commands.registerCommand('edgekBeast.jumpRelatedContext', jumpRelatedContext),
        vscode.commands.registerCommand('edgekBeast.openSideBySidePreview', openSideBySidePreview),
        vscode.commands.registerCommand('edgekBeast.switchSourcePlanSession', switchSourcePlanSession),
        vscode.commands.registerCommand('edgekBeast.refreshSourcePlanPreview', refreshSourcePlanPreview),
        vscode.commands.registerCommand('edgekBeast.createWorktreeMission', createWorktreeMission),
        vscode.commands.registerCommand('edgekBeast.openWorktreeMission', () => openWorktreeMission()),
        vscode.commands.registerCommand('edgekBeast.runWorktreeVerifier', () => runWorktreeVerifier()),
        vscode.commands.registerCommand('edgekBeast.promoteWorktreeMission', () => promoteWorktreeMission()),
        vscode.commands.registerCommand('edgekBeast.closeWorktreeMission', () => closeWorktreeMission()),
        vscode.commands.registerCommand('edgekBeast.replayLatticeCandidate', replayLatticeCandidate),
        vscode.commands.registerCommand('edgekBeast.openChronicleRecord', item => showVirtualDocument('BEAST-Chronicle.json', 'json', JSON.stringify(item, null, 2))),
        vscode.commands.registerCommand('edgekBeast.prepareHandoff', async () => {
            vscode.window.showInformationMessage('BEAST: use beast_prepare_handoff or beast_sourceplan_prepare from MCP agent mode.');
        }),
        vscode.commands.registerCommand('edgekBeast.openDashboard', () => openMissionControl(ideProvider)),
        vscode.commands.registerCommand('edgekBeast.configureGateway', async () => {
            const cwd = workspaceFolderPath();
            const terminal = beastTerminal(cwd);
            terminal.show();
            terminal.sendText(`export ANTHROPIC_BASE_URL="${gatewayUrl()}/proxy/anthropic"`);
            terminal.sendText(`export OPENAI_BASE_URL="${gatewayUrl()}/proxy/openai/v1"`);
            terminal.sendText('export ENABLE_TOOL_SEARCH=true');
            terminal.sendText(`export BEAST_WORKSPACE="${cwd || '.'}"`);
            vscode.window.showInformationMessage('BEAST: terminal gateway configured.');
        }),
        vscode.commands.registerCommand('edgekBeast.installMcpConfig', async () => {
            const cwd = workspaceFolderPath();
            if (!cwd) {
                vscode.window.showWarningMessage('BEAST: open a workspace folder before installing MCP config.');
                return;
            }
            await new Promise((resolve, reject) => {
                execFile(beastCommand(), ['--workspace', cwd, 'mcp-install'], { cwd }, error => error ? reject(error) : resolve());
            });
            vscode.window.showInformationMessage('BEAST: workspace MCP config installed.');
        })
    );

    const statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
    statusBarItem.text = '$(pulse) BEAST';
    statusBarItem.tooltip = 'EdgeK BEAST Mission Control';
    statusBarItem.command = 'edgekBeast.openMissionControl';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    context.subscriptions.push(vscode.workspace.onDidChangeWorkspaceFolders(() => {
        statusProvider.refresh();
        vscode.window.showInformationMessage('BEAST: workspace changed; MCP definitions will refresh on next agent session.');
    }));
    context.subscriptions.push(vscode.window.onDidChangeActiveTextEditor(() => applyPreviewDecorations()));
    context.subscriptions.push(vscode.workspace.onDidChangeTextDocument(() => {
        applyPreviewDecorations();
        updateBeastDiagnostics();
    }));
    context.subscriptions.push(vscode.languages.registerCodeLensProvider({ scheme: 'file' }, new BeastCodeLensProvider()));
    context.subscriptions.push(vscode.languages.registerHoverProvider({ scheme: 'file' }, new BeastHoverProvider()));
    context.subscriptions.push(vscode.workspace.registerTextDocumentContentProvider('beast-preview', new BeastVirtualDocumentProvider()));
    context.subscriptions.push(selectedHunkDecoration, skippedHunkDecoration, staleHunkDecoration, beastDiagnostics);
    applyPreviewDecorations();
    updateBeastDiagnostics();
}

function deactivate() {
    if (ideEventAbort) {
        ideEventAbort.abort();
    }
    saveIdeSession();
}

module.exports = { activate, deactivate };
