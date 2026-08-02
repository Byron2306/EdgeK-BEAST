#!/usr/bin/env node
'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const { handle } = require('./beast-extension-host');

async function main() {
  const scratchBase = path.resolve(__dirname, '..', '..', '.tmp');
  fs.mkdirSync(scratchBase, { recursive: true });
  const root = fs.mkdtempSync(path.join(scratchBase, 'beast-real-vscode-extension-'));
  const workspaceRoot = path.join(root, 'workspace');
  const hostRoot = path.join(workspaceRoot, '.beast', 'extensions');
  const targetRoot = path.join(hostRoot, 'edgek-beast');
  fs.mkdirSync(hostRoot, { recursive: true });
  fs.cpSync(path.resolve(__dirname, '..', '..', 'vscode-extension'), targetRoot, {
    recursive: true,
    filter: source => {
      const normalized = String(source).replace(/\\/g, '/');
      return !normalized.includes('/.vscode-test/') && !normalized.endsWith('/.vscode-test');
    },
  });
  const uglyRoot = path.join(hostRoot, 'publisher.asset-runtime-check');
  fs.mkdirSync(path.join(uglyRoot, 'assets'), { recursive: true });
  fs.mkdirSync(path.join(uglyRoot, 'node_modules', 'tiny-helper', 'lib'), { recursive: true });
  fs.writeFileSync(path.join(uglyRoot, 'package.json'), JSON.stringify({
    publisher: 'publisher',
    name: 'asset-runtime-check',
    displayName: 'Asset Runtime Check',
    version: '1.0.0',
    main: 'extension.js',
    activationEvents: ['onCommand:publisher.assetRuntime.run', 'onView:publisher.assetRuntime.view'],
    capabilities: ['workspace.read'],
    contributes: {
      commands: [{ command: 'publisher.assetRuntime.run', title: 'Run Asset Runtime Check' }],
      views: { 'beast.views': [{ id: 'publisher.assetRuntime.view', name: 'Asset Runtime View' }] },
    },
  }, null, 2));
  fs.writeFileSync(path.join(uglyRoot, 'assets', 'banner.txt'), 'BEAST asset runtime ready\n', 'utf8');
  fs.writeFileSync(path.join(uglyRoot, 'node_modules', 'tiny-helper', 'package.json'), JSON.stringify({
    name: 'tiny-helper',
    version: '1.0.0',
    exports: {
      '.': './index.js',
      './subpath': './lib/subpath.js',
    },
  }, null, 2));
  fs.writeFileSync(path.join(uglyRoot, 'node_modules', 'tiny-helper', 'index.js'), 'module.exports = { score(value) { return String(value || "").length; } };\n', 'utf8');
  fs.writeFileSync(path.join(uglyRoot, 'node_modules', 'tiny-helper', 'lib', 'subpath.js'), 'exports.score = value => String(value || "").trim().length;\n', 'utf8');
  fs.writeFileSync(path.join(uglyRoot, 'extension.js'), `
const fs = require('fs');
const vscode = require('vscode');
const helper = require('tiny-helper/subpath');
exports.activate = function activate(context) {
  const banner = fs.readFileSync(context.asAbsolutePath('assets/banner.txt'), 'utf8').trim();
  context.subscriptions.push(vscode.commands.registerCommand('publisher.assetRuntime.run', async () => {
    const panel = vscode.window.createWebviewPanel('publisher.assetRuntime.panel', 'Asset Runtime', {}, { enableScripts: false });
    panel.webview.html = '<section>' + banner + '</section>';
    await panel.webview.postMessage({ type: 'hydrate', score: helper.score(banner) });
    panel.dispose();
    await vscode.window.showInformationMessage('asset score ' + helper.score(banner));
  }));
  context.subscriptions.push(vscode.window.registerWebviewViewProvider('publisher.assetRuntime.view', {
    resolveWebviewView(view) {
      view.webview.html = '<strong>' + banner + '</strong>';
      view.show(true);
    },
  }, { webviewOptions: { retainContextWhenHidden: true } }));
  return { banner, score: helper.score(banner) };
};
`, 'utf8');

  const roots = [{ path: hostRoot, origin: 'workspace' }];
  const discovered = await handle({ operation: 'discover', roots });
  const activation = await handle({
    operation: 'activateByEvent',
    roots,
    workspaceRoot,
    activationEvent: 'onStartupFinished',
  });
  const uglyViewActivation = await handle({
    operation: 'activateByEvent',
    roots,
    workspaceRoot,
    activationEvent: 'onView:publisher.assetRuntime.view',
    grantsByExtension: { 'publisher.asset-runtime-check': ['workspace.read'] },
  });
  const uglyExecution = await handle({
    operation: 'execute',
    roots,
    workspaceRoot,
    extensionId: 'publisher.asset-runtime-check',
    command: 'publisher.assetRuntime.run',
    granted: ['workspace.read'],
  });
  const extension = (discovered.extensions || []).find(item => item.id === 'edgek.edgek-beast') || null;
  const ugly = (discovered.extensions || []).find(item => item.id === 'publisher.asset-runtime-check') || null;
  const commandNames = new Set((activation.results || []).flatMap(item => item.registeredCommands || []));
  const actionKinds = new Set((activation.actions || []).map(item => item.kind));
  const checks = [
    Boolean(extension && extension.compatibility === 'vscode-package-json'),
    Boolean(ugly && ugly.compatibility === 'vscode-package-json'),
    activation.matched === 1 && activation.activated === 1 && activation.failed === 0,
    commandNames.has('edgekBeast.openMissionControl'),
    commandNames.has('edgekBeast.showAgentSessions'),
    commandNames.has('edgekBeast.showWorktrees'),
    actionKinds.has('tree'),
    actionKinds.has('status'),
    actionKinds.has('language'),
    uglyViewActivation.ok === true && uglyViewActivation.results?.some(item => item.id === 'publisher.asset-runtime-check' && item.ok === true) && uglyViewActivation.actions?.some(item => item.kind === 'webview' && item.payload?.viewType === 'publisher.assetRuntime.view'),
    uglyExecution.extensionId === 'publisher.asset-runtime-check' && uglyExecution.actionKinds?.includes('webview') && uglyExecution.actions?.some(item => item.kind === 'webview' && item.payload?.postMessage) && uglyExecution.actions?.some(item => item.kind === 'notice' && /asset score/i.test(item.payload?.message || '')),
  ];
  const failed = checks.map((ok, index) => ok ? null : index + 1).filter(Boolean);
  const report = {
    ok: failed.length === 0,
    checks: checks.length,
    failed,
    extensionId: extension?.id || '',
    uglyExtensionId: ugly?.id || '',
    registeredCommands: [...commandNames].slice(0, 80),
    actionKinds: [...actionKinds].sort(),
  };
  const repoRoot = path.resolve(__dirname, '..', '..');
  fs.mkdirSync(path.join(repoRoot, 'build'), { recursive: true });
  fs.writeFileSync(
    path.join(repoRoot, 'build', 'REAL_VSCODE_EXTENSION_HOST_PARITY.json'),
    `${JSON.stringify(report, null, 2)}\n`,
    'utf8',
  );
  console.log(JSON.stringify(report, null, 2));
  process.exit(failed.length === 0 ? 0 : 1);
}

main().catch(error => {
  console.error(error.stack || String(error));
  process.exit(1);
});
