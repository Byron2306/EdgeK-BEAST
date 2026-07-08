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
    const folder = workspaceFolderPath();
    if (folder) {
        const local = path.join(folder, 'bin', 'beast');
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

async function ensureGateway() {
    if (await isGatewayRunning()) {
        return true;
    }

    const cwd = workspaceFolderPath();
    const terminal = beastTerminal(cwd);
    terminal.show();
    terminal.sendText(`"${beastCommand()}" serve --host 127.0.0.1 --port 8000`);
    vscode.window.showInformationMessage('BEAST: starting gateway on http://127.0.0.1:8000');
    return false;
}

async function callMcpTool(name, args = {}) {
    await ensureGateway();
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
                this.section('Code Cortex', snap.code_cortex?.adapter || snap.code_cortex?.front_door || 'ready', 'edgekBeast.refreshIdeSnapshot'),
                this.section('Lattice', `${snap.mission_lattice?.cell_count || 0} cells`, 'edgekBeast.replayLatticeCandidate'),
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

function tuiCss() {
    return `
        body { background:#050607; color:#d7fbe8; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; padding:18px; }
        .shell { max-width: 1180px; margin:0 auto; }
        .hero { border:1px solid #1f3a3d; background:#071012; padding:16px; box-shadow:0 0 24px rgba(51,246,255,.08); }
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
        ul { padding-left:18px; }
    `;
}

function missionControlHtml(snapshot) {
    const cards = snapshot?.mission_cockpit?.cards || [];
    const queue = snapshot?.sourceplan_queue || [];
    const evidence = snapshot?.evidence_bus || {};
    const lattice = snapshot?.mission_lattice || {};
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
          <button data-command="createWorktreeMission">Create Worktree</button>
          <button data-command="replayLatticeCandidate">Replay Lattice</button>
        </div>
      </div>
      <div class="grid">
        <div class="card"><h2>SourcePlans</h2><div class="metric">${queue.length}</div><div class="muted">queued plans</div></div>
        <div class="card"><h2>Evidence</h2><div class="metric">${evidence.total || evidence.count || 0}</div><div class="muted">indexed receipts</div></div>
        <div class="card"><h2>Lattice</h2><div class="metric">${lattice.cell_count || 0}</div><div class="muted">verified edit cells</div></div>
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
        <h1>Source Workbench</h1>
        <div class="muted">${escapeHtml(plan?.plan_id || 'draft')} · ${escapeHtml(plan?.objective || '')}</div>
        <div class="row"><span class="pill">risk ${escapeHtml(scorecard?.risk_level || 'unknown')}</span><span class="pill">decision ${escapeHtml(scorecard?.decision || '')}</span><span class="pill">policy ${escapeHtml(policy.decision || '')}</span></div>
        <div class="row" style="margin-top:10px"><button data-command="previewHunks">Preview Hunks</button><button data-command="selectAllHunks">Select All</button><button data-command="clearHunks">Clear</button><button data-command="applySelectedHunks">Apply Selected</button><button data-command="showEvidence">Evidence</button><button data-command="replayLatticeCandidate">Replay Lattice</button></div>
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
        <div class="hero"><h1>Evidence Bus</h1><div class="muted">${escapeHtml(root || 'workspace')} · ${escapeHtml(data.total || data.count || rows.length)} receipt(s)</div></div>
        <div class="card" style="margin-top:12px"><h2>Recent Receipts</h2>
          ${rows.length ? rows.slice(0, 30).map(item => `<pre>${escapeHtml(JSON.stringify(item, null, 2))}</pre>`).join('') : '<div class="muted">No evidence receipts returned by the gateway.</div>'}
        </div>
      </div></body></html>`;
    const panel = vscode.window.createWebviewPanel('beastEvidenceBus', 'BEAST Evidence Bus', vscode.ViewColumn.Beside, { enableScripts: true });
    panel.webview.html = html;
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
    await showVirtualDocument('BEAST-Worktree-Mission.json', 'json', JSON.stringify(result, null, 2));
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
    if (command === 'createWorktreeMission') {
        return createWorktreeMission();
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
    participant.iconPath = vscode.Uri.file(path.join(context.extensionPath, 'media', 'beast-icon.svg'));
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
    vscode.window.registerTreeDataProvider('beastStatus', statusProvider);
    vscode.window.registerTreeDataProvider('beastDashboard', ideProvider);
    vscode.window.registerTreeDataProvider('beastChronicle', chronicleProvider);
    vscode.window.registerTreeDataProvider('beastRouteFitness', routeFitnessProvider);

    const provider = vscode.lm.registerMcpServerDefinitionProvider('edgekBeast', {
        provideMcpServerDefinitions: async () => {
            const folder = workspaceFolderPath();
            return [
                new vscode.McpStdioServerDefinition(
                    'EdgeK BEAST',
                    beastCommand(),
                    ['mcp', '--workspace', folder || '.'],
                    { BEAST_WORKSPACE: folder || '.' },
                    '1.4.0',
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
    registerBeastChatParticipant(context);

    context.subscriptions.push(
        vscode.commands.registerCommand('edgekBeast.start', ensureGateway),
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
        vscode.commands.registerCommand('edgekBeast.createWorktreeMission', createWorktreeMission),
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
    context.subscriptions.push(vscode.workspace.onDidChangeTextDocument(() => applyPreviewDecorations()));
    context.subscriptions.push(selectedHunkDecoration, skippedHunkDecoration, staleHunkDecoration);
    applyPreviewDecorations();
}

function deactivate() {
    saveIdeSession();
}

module.exports = { activate, deactivate };
