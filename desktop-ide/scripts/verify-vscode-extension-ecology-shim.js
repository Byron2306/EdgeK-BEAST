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
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'beast-vscode-extension-ecology-'));
  const extensionRoot = path.join(root, '.beast', 'extensions', 'acme.ecology');
  const apiRoot = path.join(root, '.beast', 'extensions', 'acme.api');
  const languageRoot = path.join(root, '.beast', 'extensions', 'acme.nimtools');
  const brokenRoot = path.join(root, '.beast', 'extensions', 'acme.broken');
  write(path.join(root, 'src', 'main.nim'), 'echo "beast"\n');
  write(path.join(extensionRoot, 'media', 'panel.html'), '<strong>BEAST ecology</strong>');
  write(path.join(extensionRoot, 'lib', 'helper.js'), `
exports.decorate = value => 'decorated:' + value;
`);
  write(path.join(extensionRoot, 'node_modules', 'tiny-pad', 'package.json'), JSON.stringify({ name: 'tiny-pad', version: '1.0.0', main: 'index.js' }, null, 2));
  write(path.join(extensionRoot, 'node_modules', 'tiny-pad', 'index.js'), `
module.exports = value => '[' + value + ']';
`);
  write(path.join(extensionRoot, 'package.json'), JSON.stringify({
    publisher: 'acme',
    name: 'ecology',
    displayName: 'Ecology Extension',
    version: '2.0.0',
    main: 'extension.js',
    activationEvents: ['onStartupFinished', 'workspaceContains:src/main.nim', 'onLanguage:nim', 'onCommand:acme.ecology.run'],
    capabilities: ['workspace.read', 'workspace.write', 'terminal.execute', 'language.client'],
    contributes: {
      commands: [{ command: 'acme.ecology.run', title: 'Run Ecology' }],
      viewsContainers: { activitybar: [{ id: 'acme-container', title: 'Acme' }] },
      views: { 'acme-container': [{ id: 'acme.tree', name: 'Acme Tree' }] },
      menus: { 'view/title': [{ command: 'acme.ecology.run', when: 'view == acme.tree' }] },
      configuration: { title: 'Acme', properties: { 'acme.enabled': { type: 'boolean', default: true } } },
      languages: [{ id: 'nim', extensions: ['.nim'] }],
      debuggers: [{ type: 'nim', label: 'Nim Debug' }],
      taskDefinitions: [{ type: 'nim' }],
      grammars: [{ language: 'nim', scopeName: 'source.nim', path: './syntaxes/nim.tmLanguage.json' }],
      jsonValidation: [{ fileMatch: 'beast.json', url: './schema.json' }],
    },
  }, null, 2));
  write(path.join(extensionRoot, 'extension.js'), `
const vscode = require('vscode');
const path = require('path');
const helper = require('./lib/helper');
const tinyPad = require('tiny-pad');

exports.activate = function(context) {
  const media = context.asAbsolutePath('media/panel.html');
  context.subscriptions.push(vscode.window.registerTreeDataProvider('acme.tree', { getChildren: () => [] }));
  context.subscriptions.push(vscode.window.createTreeView('acme.tree', { canSelectMany: true }));
  context.subscriptions.push(vscode.languages.registerHoverProvider({ language: 'nim' }, {}));
  context.subscriptions.push(vscode.debug.registerDebugConfigurationProvider('nim', {}));
  context.subscriptions.push(vscode.workspace.createFileSystemWatcher('**/*.nim'));
  context.subscriptions.push(vscode.tasks.registerTaskProvider('nim', { provideTasks: () => [] }));
  context.subscriptions.push(vscode.commands.registerCommand('acme.ecology.run', async () => {
    const uri = vscode.Uri.joinPath(vscode.Uri.file('src'), 'main.nim');
    const bytes = await vscode.workspace.fs.readFile(uri);
    const previousFile = context.workspaceState.get('lastFile', 'none');
    const previousSecret = await context.secrets.get('token') || 'none';
    const previousConfig = vscode.workspace.getConfiguration('acme').get('enabled', false);
    await context.workspaceState.update('lastFile', path.basename(uri.fsPath));
    await context.globalState.update('media', media);
    await context.secrets.store('token', 'redacted');
    await vscode.workspace.getConfiguration('acme').update('enabled', true, vscode.ConfigurationTarget.Workspace);
    const status = vscode.window.createStatusBarItem('acme.status', vscode.StatusBarAlignment.Left);
    status.text = tinyPad(helper.decorate(new TextDecoder().decode(bytes).trim())) + ' prev=' + previousFile + ':' + previousSecret + ':' + previousConfig;
    status.show();
    const panel = vscode.window.createWebviewPanel('acme.panel', 'Acme Panel', {}, { enableScripts: false });
    panel.webview.html = '<html><body>' + media + '</body></html>';
    const terminal = vscode.window.createTerminal({ name: 'Acme Terminal' });
    terminal.show();
    terminal.sendText('nim check src/main.nim');
    await vscode.tasks.executeTask(new vscode.Task({ type: 'nim' }, vscode.TaskScope.Workspace, 'Nim Check', 'acme', new vscode.ShellExecution('nim check src/main.nim')));
    vscode.window.showInformationMessage('ecology ready ' + status.text);
  }));
};
`);
  write(path.join(apiRoot, 'package.json'), JSON.stringify({
    publisher: 'acme',
    name: 'api',
    displayName: 'Acme API',
    version: '1.0.0',
    main: 'extension.js',
    activationEvents: [],
    capabilities: [],
  }, null, 2));
  write(path.join(apiRoot, 'extension.js'), `
exports.activate = function() {
  return { label: () => 'api-ready' };
};
`);
  write(path.join(languageRoot, 'package.json'), JSON.stringify({
    publisher: 'acme',
    name: 'nimtools',
    displayName: 'Nim Tools',
    version: '1.0.0',
    main: 'extension.js',
    extensionDependencies: ['acme.api'],
    activationEvents: ['workspaceContains:src/main.nim', 'onLanguage:nim'],
    capabilities: ['workspace.read'],
    contributes: {
      commands: [{ command: 'acme.nimtools.scan', title: 'Scan Nim' }],
      languages: [{ id: 'nim', extensions: ['.nim'] }],
    },
  }, null, 2));
  write(path.join(languageRoot, 'extension.js'), `
const vscode = require('vscode');
exports.activate = function(context) {
  const api = vscode.extensions.getExtension('acme.api');
  vscode.window.showInformationMessage('nimtools dependency ' + api.exports.label());
  context.subscriptions.push(vscode.languages.registerCompletionItemProvider({ language: 'nim' }, {}));
  context.subscriptions.push(vscode.commands.registerCommand('acme.nimtools.scan', async () => {
    const files = await vscode.workspace.findFiles('**/*.nim', '', 10);
    vscode.window.showInformationMessage('nim files ' + files.length);
  }));
};
`);
  const activityRoot = path.join(root, '.beast', 'extensions', 'acme.activity');
  write(path.join(activityRoot, 'package.json'), JSON.stringify({
    publisher: 'acme',
    name: 'activity',
    displayName: 'Acme Activity',
    version: '1.0.0',
    main: 'extension.js',
    extensionDependencies: ['acme.api'],
    activationEvents: ['onView:acme.activity.view', 'onDebug:nim', 'onTaskType:nim'],
    capabilities: ['workspace.read', 'terminal.execute'],
    contributes: {
      views: { 'acme-container': [{ id: 'acme.activity.view', name: 'Acme Activity View' }] },
      debuggers: [{ type: 'nim', label: 'Nim Debug Activity' }],
      taskDefinitions: [{ type: 'nim' }],
    },
  }, null, 2));
  write(path.join(activityRoot, 'extension.js'), `
const vscode = require('vscode');
exports.activate = function(context) {
  const api = vscode.extensions.getExtension('acme.api');
  const channel = vscode.window.createOutputChannel('Acme Activity');
  channel.appendLine('activity ' + api.exports.label());
  const provider = {
    resolveWebviewView(view) {
      view.webview.html = '<section>activity-view</section>';
      view.show(true);
    }
  };
  context.subscriptions.push(vscode.window.registerWebviewViewProvider('acme.activity.view', provider, { webviewOptions: { retainContextWhenHidden: true } }));
  context.subscriptions.push(vscode.debug.registerDebugConfigurationProvider('nim', {}));
  context.subscriptions.push(vscode.tasks.registerTaskProvider('nim', { provideTasks: () => [] }));
  vscode.window.showWarningMessage('activity ' + api.exports.label());
};
`);
  write(path.join(brokenRoot, 'package.json'), JSON.stringify({
    publisher: 'acme',
    name: 'broken',
    displayName: 'Broken Extension',
    version: '1.0.0',
    main: 'extension.js',
    activationEvents: ['onStartupFinished'],
    contributes: { commands: [{ command: 'acme.broken.noop', title: 'Broken' }] },
  }, null, 2));
  write(path.join(brokenRoot, 'extension.js'), `
exports.activate = function() { throw new Error('intentional lifecycle failure'); };
`);

  const roots = [{ path: path.join(root, '.beast', 'extensions'), origin: 'workspace' }];
  const discovered = await handle({ operation: 'discover', roots });
  const activated = await handle({
    operation: 'activate',
    roots,
    workspaceRoot: root,
    extensionId: 'acme.ecology',
    activationEvent: 'onStartupFinished',
    granted: ['workspace.read', 'workspace.write', 'terminal.execute', 'language.client'],
  });
  const startupBatch = await handle({
    operation: 'activateByEvent',
    roots,
    workspaceRoot: root,
    activationEvent: 'onStartupFinished',
    grantsByExtension: { 'acme.ecology': ['workspace.read', 'workspace.write', 'terminal.execute', 'language.client'] },
  });
  const workspaceBatch = await handle({
    operation: 'activateByEvent',
    roots,
    workspaceRoot: root,
    activationEvent: 'workspaceContains',
    grantsByExtension: { 'acme.nimtools': ['workspace.read'] },
  });
  const languageBatch = await handle({
    operation: 'activateByEvent',
    roots,
    workspaceRoot: root,
    activationEvent: 'onLanguage:nim',
    grantsByExtension: { 'acme.ecology': ['workspace.read', 'workspace.write', 'terminal.execute', 'language.client'], 'acme.nimtools': ['workspace.read'] },
  });
  const viewBatch = await handle({
    operation: 'activateByEvent',
    roots,
    workspaceRoot: root,
    activationEvent: 'onView:acme.activity.view',
    grantsByExtension: { 'acme.activity': ['workspace.read', 'terminal.execute'] },
  });
  const debugBatch = await handle({
    operation: 'activateByEvent',
    roots,
    workspaceRoot: root,
    activationEvent: 'onDebug:nim',
    grantsByExtension: { 'acme.activity': ['workspace.read', 'terminal.execute'] },
  });
  const taskBatch = await handle({
    operation: 'activateByEvent',
    roots,
    workspaceRoot: root,
    activationEvent: 'onTaskType:nim',
    grantsByExtension: { 'acme.activity': ['workspace.read', 'terminal.execute'] },
  });
  const executed = await handle({
    operation: 'execute',
    roots,
    workspaceRoot: root,
    extensionId: 'acme.ecology',
    command: 'acme.ecology.run',
    granted: ['workspace.read', 'workspace.write', 'terminal.execute', 'language.client'],
  });
  const executedAgain = await handle({
    operation: 'execute',
    roots,
    workspaceRoot: root,
    extensionId: 'acme.ecology',
    command: 'acme.ecology.run',
    granted: ['workspace.read', 'workspace.write', 'terminal.execute', 'language.client'],
  });
  const stress = await handle({ operation: 'stressProbe', roots, workspaceRoot: root });
  const actions = executed.actions || [];
  const secondActions = executedAgain.actions || [];
  const ecology = (discovered.extensions || []).find(extension => extension.id === 'acme.ecology') || {};
  const summary = ecology.contributionSummary || {};
  const checks = [
    ecology.compatibility === 'vscode-package-json',
    discovered.extensions?.length === 5,
    summary.views === 1 && summary.languages === 1 && summary.debuggers === 1 && summary.taskDefinitions === 1,
    activated.registeredCommands?.includes('acme.ecology.run'),
    startupBatch.matched === 2 && startupBatch.activated === 1 && startupBatch.failed === 1 && startupBatch.results?.some(item => item.id === 'acme.broken' && item.ok === false),
    workspaceBatch.ok === true && workspaceBatch.results?.some(item => item.id === 'acme.nimtools' && item.ok === true),
    workspaceBatch.actions?.some(action => action.extensionId === 'acme.nimtools' && action.kind === 'notice' && /api-ready/.test(action.payload?.message || '')),
    languageBatch.ok === true && languageBatch.activated === 2 && languageBatch.results?.some(item => item.id === 'acme.nimtools' && item.dependencies?.includes('acme.api')),
    viewBatch.ok === true && viewBatch.results?.some(item => item.id === 'acme.activity' && item.ok === true) && viewBatch.actions?.some(action => action.extensionId === 'acme.activity' && action.kind === 'webview'),
    stress.results?.some(item => item.id === 'acme.activity' && item.lifecycleMatches?.onDebug === true && item.contributionSummary?.debuggers >= 1),
    stress.results?.some(item => item.id === 'acme.activity' && item.lifecycleMatches?.onTaskType === true && item.contributionSummary?.taskDefinitions >= 1),
    actions.some(action => action.kind === 'status' && /decorated:echo/.test(action.payload?.text || '')),
    actions.some(action => action.kind === 'webview' && action.payload?.htmlBytes > 0),
    actions.some(action => action.kind === 'tree' && action.payload?.id === 'acme.tree'),
    actions.some(action => action.kind === 'watcher'),
    actions.some(action => action.kind === 'language' && action.payload?.feature === 'hover'),
    actions.some(action => action.kind === 'debug' && action.payload?.type === 'nim'),
    actions.some(action => action.kind === 'task' && action.payload?.execute === true),
    actions.some(action => action.kind === 'terminal' && /nim check/.test(action.payload?.text || '')),
    actions.some(action => action.kind === 'config' && action.payload?.section === 'acme'),
    actions.some(action => action.kind === 'secret' && action.payload?.stored === true),
    executed.actionSummary?.actionCount >= actions.length
      && executed.actionSummary?.webviews?.length >= 1
      && executed.actionSummary?.trees?.length >= 1
      && executed.actionSummary?.statuses?.length >= 1
      && executed.actionSummary?.watchers >= 1
      && executed.actionSummary?.tasks >= 1,
    secondActions.some(action => action.kind === 'status' && /prev=main\.nim:redacted:true/.test(action.payload?.text || '')),
    stress.ok === true && stress.contributionSummary?.languages === 2 && stress.results?.some(item => item.id === 'acme.nimtools' && item.extensionDependencies?.includes('acme.api') && item.lifecycleMatches?.workspaceContains === true) && stress.results?.some(item => item.id === 'acme.activity' && item.lifecycleMatches?.onView === true && item.lifecycleMatches?.onDebug === true && item.lifecycleMatches?.onTaskType === true),
  ];
  const failed = checks.map((ok, index) => ok ? null : index + 1).filter(Boolean);
  console.log(JSON.stringify({ ok: failed.length === 0, checks: checks.length, failed }, null, 2));
  if (failed.length) {
    console.error(JSON.stringify({ discovered, activated, startupBatch, workspaceBatch, languageBatch, viewBatch, debugBatch, taskBatch, executed, executedAgain, stress }, null, 2));
  }
  process.exit(failed.length === 0 ? 0 : 1);
}

main().catch(error => {
  console.error(error.stack || String(error));
  process.exit(1);
});
