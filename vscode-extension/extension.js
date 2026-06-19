const vscode = require('vscode');
const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');

const DEFAULT_PROXY = 'http://127.0.0.1:8000';

async function isGatewayRunning(baseUrl = DEFAULT_PROXY) {
    try {
        const response = await fetch(`${baseUrl}/health`);
        return response.ok;
    } catch {
        return false;
    }
}

function workspaceFolderPath() {
    return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
}

function beastCommand() {
    const configured = vscode.workspace.getConfiguration().get('edgekBeast.mcpServerCommand', '');
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

async function ensureGateway(context) {
    const baseUrl = vscode.workspace.getConfiguration().get('edgekBeast.proxyUrl', DEFAULT_PROXY);
    if (await isGatewayRunning(baseUrl)) {
        return true;
    }

    const cwd = workspaceFolderPath();
    const terminal = beastTerminal(cwd);
    terminal.show();
    terminal.sendText(`"${beastCommand()}" serve --host 127.0.0.1 --port 8000`);
    vscode.window.showInformationMessage('BEAST: starting gateway on http://127.0.0.1:8000');
    return false;
}

class BeastStatusProvider {
    getTreeItem(element) { return element; }
    getChildren() {
        const proxy = vscode.workspace.getConfiguration().get('edgekBeast.proxyUrl', DEFAULT_PROXY);
        return [
            new vscode.TreeItem(`Gateway: ${proxy}`),
            new vscode.TreeItem('MCP Lane: stdio via beast mcp'),
            new vscode.TreeItem('Proxy Lane: /proxy/* on port 8000'),
            new vscode.TreeItem(`Workspace: ${workspaceFolderPath() || 'none'}`),
        ];
    }
}

function activate(context) {
    const statusProvider = new BeastStatusProvider();
    vscode.window.registerTreeDataProvider('beastStatus', statusProvider);

    // Register the dashboard provider
    const dashboardProvider = new BeastDashboardProvider();
    vscode.window.registerTreeDataProvider('beastDashboard', dashboardProvider);

    const provider = vscode.lm.registerMcpServerDefinitionProvider('edgekBeast', {
        provideMcpServerDefinitions: async () => {
            const folder = workspaceFolderPath();
            return [
                new vscode.McpStdioServerDefinition(
                    'EdgeK BEAST',
                    beastCommand(),
                    ['mcp', '--workspace', folder || '.'],
                    { BEAST_WORKSPACE: folder || '.' },
                    '1.1.0',
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

    context.subscriptions.push(
        vscode.commands.registerCommand('edgekBeast.start', async () => {
            await ensureGateway(context);
        }),
        vscode.commands.registerCommand('edgekBeast.prepareHandoff', async () => {
            vscode.window.showInformationMessage('BEAST: use the beast_prepare_handoff MCP tool from agent mode.');
        }),
        vscode.commands.registerCommand('edgekBeast.openDashboard', async () => {
            await vscode.env.openExternal(vscode.Uri.parse(`${DEFAULT_PROXY}/`));
        }),
        vscode.commands.registerCommand('edgekBeast.configureGateway', async () => {
            const cwd = workspaceFolderPath();
            const terminal = beastTerminal(cwd);
            terminal.show();
            terminal.sendText(`export ANTHROPIC_BASE_URL="${DEFAULT_PROXY}/proxy/anthropic"`);
            terminal.sendText(`export OPENAI_BASE_URL="${DEFAULT_PROXY}/proxy/openai/v1"`);
            terminal.sendText('export ENABLE_TOOL_SEARCH=true');
            terminal.sendText(`export BEAST_WORKSPACE="${cwd || '.'}"`);
            vscode.window.showInformationMessage('BEAST: terminal gateway configured for port 8000');
        }),
        vscode.commands.registerCommand('edgekBeast.installMcpConfig', async () => {
            const cwd = workspaceFolderPath();
            if (!cwd) {
                vscode.window.showWarningMessage('BEAST: open a workspace folder before installing MCP config.');
                return;
            }
            await new Promise((resolve, reject) => {
                execFile(beastCommand(), ['--workspace', cwd, 'mcp-install'], { cwd }, (error) => {
                    if (error) {
                        reject(error);
                    } else {
                        resolve();
                    }
                });
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

    context.subscriptions.push(
        vscode.workspace.onDidChangeWorkspaceFolders(() => {
            vscode.window.showInformationMessage('BEAST: workspace changed; MCP definitions will refresh on next agent session.');
        })
    );
}

function deactivate() {
}

module.exports = { activate, deactivate };
