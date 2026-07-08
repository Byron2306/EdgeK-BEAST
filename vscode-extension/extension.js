const vscode = require('vscode');
const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');

const DEFAULT_PROXY = 'http://127.0.0.1:8000';

let currentPlan = null;
let lastChronicles = [];
let lastFitness = [];
let lastMaintenance = null;

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
    vscode.window.showInformationMessage(`BEAST SourcePlan ready: ${result.summary || currentPlan.plan_id || 'draft'}`);
}

async function previewHunks() {
    if (!currentPlan) {
        await prepareSourcePlan();
    }
    if (!currentPlan) {
        return;
    }
    const result = await callMcpTool('beast_sourceplan_preview_hunks', { plan: currentPlan });
    const data = actionData(result);
    await showVirtualDocument(`BEAST-${currentPlan.plan_id || 'sourceplan'}.diff`, 'diff', data.diff || result.summary || result.error || '');
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
    const statusProvider = new BeastStatusProvider();
    const chronicleProvider = new ChronicleProvider();
    const routeFitnessProvider = new RouteFitnessProvider();
    vscode.window.registerTreeDataProvider('beastStatus', statusProvider);
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
                    '1.2.0',
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
        vscode.commands.registerCommand('edgekBeast.openChronicleRecord', item => showVirtualDocument('BEAST-Chronicle.json', 'json', JSON.stringify(item, null, 2))),
        vscode.commands.registerCommand('edgekBeast.prepareHandoff', async () => {
            vscode.window.showInformationMessage('BEAST: use beast_prepare_handoff or beast_sourceplan_prepare from MCP agent mode.');
        }),
        vscode.commands.registerCommand('edgekBeast.openDashboard', async () => {
            await vscode.env.openExternal(vscode.Uri.parse(`${gatewayUrl()}/`));
        }),
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
    statusBarItem.command = 'edgekBeast.openDashboard';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    context.subscriptions.push(vscode.workspace.onDidChangeWorkspaceFolders(() => {
        statusProvider.refresh();
        vscode.window.showInformationMessage('BEAST: workspace changed; MCP definitions will refresh on next agent session.');
    }));
}

function deactivate() {}

module.exports = { activate, deactivate };
