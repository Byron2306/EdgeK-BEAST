'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const { handle } = require('./beast-extension-host');

function write(file, text) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, text, 'utf8');
}

async function main() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'beast-vscode-extension-shim-'));
  const extensionRoot = path.join(root, '.beast', 'extensions', 'acme.greeter');
  write(path.join(root, 'README.md'), '# Shim workspace\n');
  write(path.join(extensionRoot, 'package.json'), JSON.stringify({
    publisher: 'acme',
    name: 'greeter',
    displayName: 'Greeter',
    version: '1.2.3',
    main: 'extension.js',
    activationEvents: ['onCommand:acme.greeter.hello'],
    capabilities: ['workspace.read'],
    contributes: { commands: [{ command: 'acme.greeter.hello', title: 'Hello' }] },
  }, null, 2));
  write(path.join(extensionRoot, 'extension.js'), `
const vscode = require('vscode');
exports.activate = function(context) {
  context.subscriptions.push(vscode.commands.registerCommand('acme.greeter.hello', async () => {
    const bytes = await vscode.workspace.fs.readFile(vscode.Uri.file('README.md'));
    vscode.window.showInformationMessage('hello ' + new TextDecoder().decode(bytes).trim());
    await vscode.commands.executeCommand('beast.openWorkspace');
  }));
};
`);
  const roots = [{ path: path.join(root, '.beast', 'extensions'), origin: 'workspace' }];
  const discovered = await handle({ operation: 'discover', roots });
  const executed = await handle({
    operation: 'execute',
    roots,
    workspaceRoot: root,
    extensionId: 'acme.greeter',
    command: 'acme.greeter.hello',
    granted: ['workspace.read'],
  });
  const stress = await handle({ operation: 'stressProbe', roots });
  const checks = [
    discovered.extensions?.[0]?.manifestKind === 'package.json',
    discovered.extensions?.[0]?.compatibility === 'vscode-package-json',
    executed.registeredCommands?.includes('acme.greeter.hello'),
    executed.actions?.some(action => action.kind === 'notice' && /hello/.test(action.payload?.message || '')),
    executed.actions?.some(action => action.kind === 'navigate' && action.payload?.route === 'workspace'),
    stress.ok === true && stress.extensionCount === 1,
  ];
  const report = { ok: checks.every(Boolean), checks: checks.length, discovered, executed, stress };
  console.log(JSON.stringify({ ok: report.ok, checks: report.checks }, null, 2));
  process.exit(report.ok ? 0 : 1);
}

main().catch(error => {
  console.error(error.stack || String(error));
  process.exit(1);
});
