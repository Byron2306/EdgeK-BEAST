const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const repo = path.resolve(__dirname, '..', '..');
const desktop = path.join(repo, 'desktop-ide');
const { IdeCompatibilityHost } = require('../ide-compatibility-host');
const { createGitHost } = require('../main/git-host');
const { createTaskTestHost } = require('../main/task-test-host');
const { createIdeServicesHost } = require('../main/ide-services-host');
const { createWorkspaceFileHost } = require('../main/workspace-file-host');
const { createWorkspaceIndexHost } = require('../main/workspace-index-host');
const { createWorkspacePathTools } = require('../main/workspace-paths');
const { createBoundedProcess } = require('../main/process-host');
const { handle: extensionHostHandle } = require('./beast-extension-host');

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd || repo,
    encoding: 'utf8',
    timeout: options.timeout || 20000,
    maxBuffer: 1024 * 1024,
    input: options.input || undefined,
  });
  if (options.check && result.status !== 0) {
    throw new Error(`${command} ${args.join(' ')} failed: ${result.stderr || result.stdout || result.error}`);
  }
  return result;
}

function write(file, text) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, text, 'utf8');
}

const root = fs.mkdtempSync(path.join(os.tmpdir(), 'beast-ide-services-'));
write(path.join(root, 'package.json'), JSON.stringify({ scripts: { test: 'node --test', check: 'node --check src/index.js' } }, null, 2));
write(path.join(root, 'tests', 'test_sample.py'), 'def test_sample():\n    assert True\n');
write(path.join(root, 'tests', 'sample.test.js'), "const test = require('node:test');\nconst assert = require('node:assert/strict');\ntest('sample answer', () => assert.equal(42, 42));\n");
write(path.join(root, 'src', 'helper.js'), '// TODO: tighten helper coverage\nfunction double(value) { return value * 2; }\nmodule.exports = { double };\n');
write(path.join(root, 'src', 'index.js'), "const { double } = require('./helper');\nconst answer = double(21);\nfunction answerLabel() { return String(answer); }\nmodule.exports = { answer, answerLabel };\n");
write(path.join(root, 'src', 'beast_math.nim'), 'proc triple*(value: int): int = value * 3\n');
write(path.join(root, 'src', 'math.nim'), 'import std/strutils\nimport beast_math\n\ntype BeastNumber* = object\n  value*: int\n\nproc beastAdd*(left: int, right: int): int =\n  beast_math.triple(left) + right\n');
write(path.join(root, '.vscode', 'tasks.json'), JSON.stringify({
  version: '2.0.0',
  tasks: [
    {
      label: 'prep',
      type: 'shell',
      command: 'node',
      args: ['--check', 'src/index.js'],
      problemMatcher: {
        pattern: {
          regexp: '^(.+):(\\d+):(\\d+):\\s+(error):\\s+(.+)$',
          file: 1,
          line: 2,
          column: 3,
          severity: 4,
          message: 5,
        },
      },
    },
    {
      label: 'aggregate',
      type: 'shell',
      command: 'node',
      args: ['--test', 'tests/sample.test.js'],
      dependsOn: ['prep'],
      dependsOrder: 'sequence',
      presentation: { reveal: 'always', panel: 'shared', clear: true },
    },
  ],
}, null, 2));
write(path.join(root, '.vscode', 'launch.json'), JSON.stringify({
  version: '0.2.0',
  configurations: [
    { name: 'Debug sample Python', type: 'python', request: 'launch', program: '${workspaceFolder}/tests/test_sample.py', cwd: '${workspaceFolder}' },
    { name: 'Debug node sample', type: 'node', request: 'launch', program: '${workspaceFolder}/tests/sample.test.js' },
  ],
  compounds: [
    { name: 'Debug all samples', configurations: ['Debug sample Python', 'Debug node sample'] },
  ],
}, null, 2));
run('git', ['init', '-q'], { cwd: root, check: true });
run('git', ['config', 'user.email', 'beast@example.test'], { cwd: root, check: true });
run('git', ['config', 'user.name', 'BEAST Test'], { cwd: root, check: true });
run('git', ['add', '.'], { cwd: root, check: true });
run('git', ['commit', '-qm', 'base'], { cwd: root, check: true });
write(path.join(root, 'src', 'index.js'), "const { double } = require('./helper');\nconst answer = double(22);\nfunction answerLabel() { return String(answer); }\nmodule.exports = { answer, answerLabel };\n");
write(path.join(root, '.beast', 'extensions', 'beast-workload-check', 'beast-extension.json'), JSON.stringify({
  id: 'beast-workload-check',
  name: 'BEAST Workload Check',
  version: '1.0.0',
  main: 'extension.js',
  capabilities: ['workspace.read', 'terminal.execute'],
  activationEvents: ['onStartupFinished', 'workspaceContains:src/*.js'],
  extensionDependencies: ['beast.workload-dependency'],
  contributes: { commands: [{ id: 'beast.workloadCheck.run', title: 'Run Workload Check' }] },
}, null, 2));
write(path.join(root, '.beast', 'extensions', 'beast-workload-dependency', 'beast-extension.json'), JSON.stringify({
  id: 'beast.workload-dependency',
  name: 'BEAST Workload Dependency',
  version: '1.0.0',
  main: 'extension.js',
  capabilities: ['workspace.read'],
  activationEvents: ['onStartupFinished'],
  contributes: { commands: [{ id: 'beast.workloadDependency.touch', title: 'Touch Dependency State' }] },
}, null, 2));
write(path.join(root, '.beast', 'extensions', 'beast-workload-dependency', 'extension.js'), `
exports.activate = async function activate(context) {
  await context.globalState.update('dependency.started', true);
  await context.workspaceState.update('dependency.workspace', 'ready');
  await context.secrets.store('dependency.secret', 'present');
};
`);
write(path.join(root, '.beast', 'extensions', 'beast-workload-check', 'extension.js'), `
const vscode = require('vscode');
exports.activate = function activate(context) {
  context.subscriptions.push(vscode.commands.registerCommand('beast.workloadCheck.run', async () => {
  const files = vscode.workspace.findFiles('src/*.js', '', 5);
  const status = vscode.window.createStatusBarItem('beast.workload.status');
  status.text = 'BEAST workload ready';
  status.command = 'beast.openCompatibility';
  status.show();
  const watcher = vscode.workspace.createFileSystemWatcher('src/*.js');
  const tree = vscode.window.createTreeView('beast.workload.tree', { canSelectMany: false });
  vscode.window.registerTreeDataProvider('beast.workload.tree', { getChildren: () => [] });
  await tree.reveal({ id: 'root', label: 'BEAST workload root' });
  const panel = vscode.window.createWebviewPanel('beast.workload.webview', 'BEAST Workload', vscode.ViewColumn.Active, { enableScripts: false });
  panel.webview.html = '<h1>BEAST workload</h1>';
  await panel.webview.postMessage({ type: 'hydrate', files: files.length });
  panel.reveal(vscode.ViewColumn.Active);
  const terminal = vscode.window.createTerminal({ name: 'BEAST workload terminal' });
  terminal.sendText('echo workload');
  const config = vscode.workspace.getConfiguration('beast.workload');
  await config.update('enabled', true, vscode.ConfigurationTarget.Workspace);
  await vscode.languages.setTextDocumentLanguage(await vscode.workspace.openTextDocument(vscode.Uri.file('src/index.js')), 'javascript');
  await vscode.tasks.executeTask(new vscode.Task({ type: 'beast' }, vscode.TaskScope.Workspace, 'Workload Task', 'beast', new vscode.ShellExecution('echo workload')));
  await vscode.workspace.getConfiguration('beast.workload').update('mode', 'active', vscode.ConfigurationTarget.Workspace);
  await vscode.env.clipboard.writeText('beast workload');
  await context.globalState.update('workload.lastRun', files.length);
  await context.workspaceState.update('workload.fileCount', files.length);
  await context.secrets.store('workload.secret', 'stored');
  await vscode.window.showInformationMessage('workload files: ' + files.length);
  await vscode.commands.executeCommand('beast.openCompatibility');
  panel.dispose();
  watcher.dispose();
  tree.dispose();
  }));
};
`);
write(path.join(root, '.beast', 'extensions', 'beast-persistence-check', 'beast-extension.json'), JSON.stringify({
  id: 'beast-persistence-check',
  name: 'BEAST Persistence Check',
  version: '1.0.0',
  main: 'extension.js',
  capabilities: ['workspace.read'],
  activationEvents: ['onCommand:beast.persistenceCheck.report'],
  contributes: { commands: [{ id: 'beast.persistenceCheck.report', title: 'Report Persistence State' }] },
}, null, 2));
write(path.join(root, '.beast', 'extensions', 'beast-persistence-check', 'extension.js'), `
const vscode = require('vscode');
exports.activate = async function activate(context) {
  const launches = Number(context.globalState.get('launches', 0) || 0) + 1;
  await context.globalState.update('launches', launches);
  const previous = String(await context.secrets.get('session') || '');
  await context.workspaceState.update('lastLaunch', launches);
  await context.secrets.store('session', 'persisted-' + launches);
  context.subscriptions.push(vscode.commands.registerCommand('beast.persistenceCheck.report', async () => {
    const currentLaunches = Number(context.globalState.get('launches', 0) || 0);
    const lastLaunch = Number(context.workspaceState.get('lastLaunch', 0) || 0);
    const secret = String(await context.secrets.get('session') || '');
    await vscode.window.showInformationMessage('persist launches=' + currentLaunches + ' last=' + lastLaunch + ' previous=' + previous + ' secret=' + secret);
  }));
  return { launches, previous };
};
`);
write(path.join(root, '.beast', 'extensions', 'publisher.vscode-shim-check', 'package.json'), JSON.stringify({
  publisher: 'publisher',
  name: 'vscode-shim-check',
  displayName: 'VS Code Shim Check',
  version: '1.0.0',
  main: 'extension.js',
  activationEvents: ['onCommand:publisher.vscodeShim.run'],
  capabilities: ['workspace.read'],
  contributes: { commands: [{ command: 'publisher.vscodeShim.run', title: 'Run VS Code Shim Check' }] },
}, null, 2));
write(path.join(root, '.beast', 'extensions', 'publisher.vscode-shim-check', 'extension.js'), `
const vscode = require('vscode');
exports.activate = function activate(context) {
  context.subscriptions.push(vscode.commands.registerCommand('publisher.vscodeShim.run', async () => {
    const uri = vscode.Uri.file('src/index.js');
    const bytes = await vscode.workspace.fs.readFile(uri);
    const text = new TextDecoder().decode(bytes);
    vscode.window.showInformationMessage('shim bytes: ' + bytes.length + ' answer=' + text.includes('answer'));
    await vscode.commands.executeCommand('beast.openWorkspace');
  }));
};
`);
write(path.join(root, '.beast', 'extensions', 'publisher.asset-runtime-check', 'package.json'), JSON.stringify({
  publisher: 'publisher',
  name: 'asset-runtime-check',
  displayName: 'Asset Runtime Check',
  version: '1.0.0',
  main: 'extension.js',
  activationEvents: ['onLanguage:javascript', 'onCommand:publisher.assetRuntime.run'],
  capabilities: ['workspace.read'],
  contributes: {
    commands: [{ command: 'publisher.assetRuntime.run', title: 'Run Asset Runtime Check' }],
    languages: [{ id: 'javascript', extensions: ['.js'] }],
  },
}, null, 2));
write(path.join(root, '.beast', 'extensions', 'publisher.asset-runtime-check', 'extension.js'), `
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const helper = require('tiny-helper/subpath');
exports.activate = function activate(context) {
  const assetPath = context.asAbsolutePath('assets/banner.txt');
  const banner = fs.readFileSync(assetPath, 'utf8').trim();
  context.subscriptions.push(vscode.commands.registerCommand('publisher.assetRuntime.run', async () => {
    await vscode.window.showInformationMessage('asset banner: ' + String(vscode.extensions.getExtension('publisher.asset-runtime-check')?.exports?.banner || 'missing'));
    await vscode.commands.executeCommand('beast.openCompatibility');
  }));
  return {
    banner,
    score: helper.score(banner),
    extensionPath: context.extensionPath,
  };
};
`);
write(path.join(root, '.beast', 'extensions', 'publisher.asset-runtime-check', 'assets', 'banner.txt'), 'BEAST asset runtime ready\n');
write(path.join(root, '.beast', 'extensions', 'publisher.asset-runtime-check', 'node_modules', 'tiny-helper', 'package.json'), JSON.stringify({
  name: 'tiny-helper',
  version: '1.0.0',
  exports: {
    '.': './index.js',
    './subpath': './lib/subpath.js',
  },
}, null, 2));
write(path.join(root, '.beast', 'extensions', 'publisher.asset-runtime-check', 'node_modules', 'tiny-helper', 'index.js'), `
exports.identity = function identity(value) { return value; };
`);
write(path.join(root, '.beast', 'extensions', 'publisher.asset-runtime-check', 'node_modules', 'tiny-helper', 'lib', 'subpath.js'), `
exports.score = function score(text) {
  return String(text || '').includes('BEAST') ? 100 : 0;
};
`);
write(path.join(root, '.beast', 'extensions', 'publisher.lifecycle-workload', 'package.json'), JSON.stringify({
  publisher: 'publisher',
  name: 'lifecycle-workload',
  displayName: 'Lifecycle Workload',
  version: '1.0.0',
  main: 'extension.js',
  activationEvents: [
    'onView:publisher.lifecycle.tree',
    'onDebug:node',
    'onTaskType:beast',
    'onCommand:publisher.lifecycle.run',
  ],
  capabilities: ['workspace.read'],
  contributes: {
    commands: [{ command: 'publisher.lifecycle.run', title: 'Run Lifecycle Workload' }],
    views: { explorer: [{ id: 'publisher.lifecycle.tree', name: 'Lifecycle Tree' }] },
    debuggers: [{ type: 'node', label: 'Node Debugger' }],
    taskDefinitions: [{ type: 'beast', required: [] }],
  },
}, null, 2));
write(path.join(root, '.beast', 'extensions', 'publisher.lifecycle-workload', 'extension.js'), `
const vscode = require('vscode');
exports.activate = function activate(context) {
  const tree = vscode.window.createTreeView('publisher.lifecycle.tree', { canSelectMany: false });
  vscode.window.registerTreeDataProvider('publisher.lifecycle.tree', { getChildren: () => [] });
  vscode.debug.registerDebugConfigurationProvider('node', { provideDebugConfigurations: () => [] });
  vscode.tasks.registerTaskProvider('beast', { provideTasks: () => [], resolveTask: task => task });
  context.subscriptions.push(vscode.commands.registerCommand('publisher.lifecycle.run', async () => {
    await tree.reveal({ id: 'lifecycle-node', label: 'Lifecycle node' });
    await vscode.window.showInformationMessage('lifecycle workload ready');
  }));
  return { ok: true };
};
`);
write(path.join(root, '.beast', 'extensions', 'publisher.webview-state-workload', 'package.json'), JSON.stringify({
  publisher: 'publisher',
  name: 'webview-state-workload',
  displayName: 'Webview State Workload',
  version: '1.0.0',
  main: 'extension.js',
  activationEvents: ['onCommand:publisher.webviewState.run'],
  capabilities: ['workspace.read'],
  contributes: {
    commands: [{ command: 'publisher.webviewState.run', title: 'Run Webview State Workload' }],
    views: { explorer: [{ id: 'publisher.webviewState.tree', name: 'Webview State Tree' }] },
  },
}, null, 2));
write(path.join(root, '.beast', 'extensions', 'publisher.webview-state-workload', 'extension.js'), `
const vscode = require('vscode');
exports.activate = async function activate(context) {
  const restoreCount = Number(context.globalState.get('restoreCount', 0) || 0) + 1;
  await context.globalState.update('restoreCount', restoreCount);
  await context.workspaceState.update('selectedNode', 'node-' + restoreCount);
  const tree = vscode.window.createTreeView('publisher.webviewState.tree', { canSelectMany: false });
  vscode.window.registerTreeDataProvider('publisher.webviewState.tree', { getChildren: () => [] });
  const panel = vscode.window.createWebviewPanel('publisher.webviewState.panel', 'Webview State', vscode.ViewColumn.Active, { enableScripts: false, retainContextWhenHidden: true });
  panel.webview.html = '<main data-restore="' + restoreCount + '">state ' + restoreCount + '</main>';
  await panel.webview.postMessage({ type: 'restore', restoreCount, selectedNode: 'node-' + restoreCount });
  context.subscriptions.push(vscode.commands.registerCommand('publisher.webviewState.run', async () => {
    const selectedNode = String(context.workspaceState.get('selectedNode', 'node-' + restoreCount) || '');
    await tree.reveal({ id: selectedNode, label: 'State node ' + restoreCount });
    await panel.webview.postMessage({ type: 'refresh', restoreCount, selectedNode });
    await panel.webview.postMessage({ type: 'snapshot', restoreCount, selectedNode, persisted: true });
    await vscode.window.showInformationMessage('webview state restore=' + restoreCount + ' node=' + selectedNode);
  }));
  return { restoreCount };
};
`);
write(path.join(root, '.beast', 'extensions', 'publisher.webview-view-workload', 'package.json'), JSON.stringify({
  publisher: 'publisher',
  name: 'webview-view-workload',
  displayName: 'Webview View Workload',
  version: '1.0.0',
  main: 'extension.js',
  activationEvents: ['onView:publisher.webviewView.host', 'onCommand:publisher.webviewView.run'],
  capabilities: ['workspace.read'],
  contributes: {
    commands: [{ command: 'publisher.webviewView.run', title: 'Run Webview View Workload' }],
    views: { explorer: [{ id: 'publisher.webviewView.host', name: 'Webview View Host' }] },
  },
}, null, 2));
write(path.join(root, '.beast', 'extensions', 'publisher.webview-view-workload', 'extension.js'), `
const vscode = require('vscode');
exports.activate = function activate(context) {
  const output = vscode.window.createOutputChannel('Webview View Workload');
  const status = vscode.window.createStatusBarItem('publisher.webviewView.status');
  status.text = 'Webview view ready';
  status.tooltip = 'Hosted webview view provider active';
  status.show();
  vscode.window.registerWebviewViewProvider('publisher.webviewView.host', {
    resolveWebviewView(view) {
      view.webview.html = '<section>Hosted webview view</section>';
      return view.webview.postMessage({ type: 'restore', scope: 'hosted-view' });
    },
  }, { webviewOptions: { retainContextWhenHidden: true } });
  context.subscriptions.push(vscode.commands.registerCommand('publisher.webviewView.run', async () => {
    output.appendLine('running webview view workload');
    await vscode.commands.executeCommand('beast.openCompatibility');
    await vscode.window.showInformationMessage('webview view workload ready');
  }));
  return { ok: true };
};
`);
write(path.join(root, '.beast', 'extensions', 'publisher.event-lifecycle-workload', 'package.json'), JSON.stringify({
  publisher: 'publisher',
  name: 'event-lifecycle-workload',
  displayName: 'Event Lifecycle Workload',
  version: '1.0.0',
  main: 'extension.js',
  activationEvents: ['onCommand:publisher.eventLifecycle.run'],
  capabilities: ['workspace.read', 'workspace.write'],
  contributes: {
    commands: [{ command: 'publisher.eventLifecycle.run', title: 'Run Event Lifecycle Workload' }],
  },
}, null, 2));
write(path.join(root, '.beast', 'extensions', 'publisher.event-lifecycle-workload', 'extension.js'), `
const vscode = require('vscode');
exports.activate = function activate(context) {
  const seen = { open: 0, change: 0, save: 0, config: 0, watcherCreate: 0, watcherChange: 0 };
  const watcher = vscode.workspace.createFileSystemWatcher('src/generated*.js');
  context.subscriptions.push(
    watcher,
    vscode.workspace.onDidOpenTextDocument(() => { seen.open += 1; }),
    vscode.workspace.onDidChangeTextDocument(() => { seen.change += 1; }),
    vscode.workspace.onDidSaveTextDocument(() => { seen.save += 1; }),
    vscode.workspace.onDidChangeConfiguration(event => { if (event.affectsConfiguration('publisher.eventLifecycle.mode')) seen.config += 1; }),
    watcher.onDidCreate(() => { seen.watcherCreate += 1; }),
    watcher.onDidChange(() => { seen.watcherChange += 1; }),
  );
  context.subscriptions.push(vscode.commands.registerCommand('publisher.eventLifecycle.run', async () => {
    const existing = await vscode.workspace.openTextDocument(vscode.Uri.file('src/index.js'));
    await vscode.workspace.getConfiguration('publisher.eventLifecycle').update('mode', 'armed', vscode.ConfigurationTarget.Workspace);
    await vscode.workspace.fs.writeFile(vscode.Uri.file('src/generated.js'), Buffer.from('module.exports = 1;\\n'));
    await vscode.workspace.fs.writeFile(vscode.Uri.file('src/generated.js'), Buffer.from('module.exports = 2;\\n'));
    await vscode.window.showInformationMessage('events open=' + seen.open + ' change=' + seen.change + ' save=' + seen.save + ' config=' + seen.config + ' create=' + seen.watcherCreate + ' watcherChange=' + seen.watcherChange + ' file=' + existing.fileName.split('/').pop());
  }));
  return { ok: true };
};
`);
write(path.join(root, '.beast', 'extensions', 'publisher.tree-file-workload', 'package.json'), JSON.stringify({
  publisher: 'publisher',
  name: 'tree-file-workload',
  displayName: 'Tree File Workload',
  version: '1.0.0',
  main: 'extension.js',
  activationEvents: ['onCommand:publisher.treeFile.run'],
  capabilities: ['workspace.read', 'workspace.write'],
  contributes: {
    commands: [{ command: 'publisher.treeFile.run', title: 'Run Tree File Workload' }],
    views: { explorer: [{ id: 'publisher.treeFile.tree', name: 'Tree File View' }] },
  },
}, null, 2));
write(path.join(root, '.beast', 'extensions', 'publisher.tree-file-workload', 'extension.js'), `
const vscode = require('vscode');
exports.activate = function activate(context) {
  const treeEmitter = new vscode.EventEmitter();
  const seen = { create: 0, rename: 0, del: 0, refresh: 0, watcherDelete: 0 };
  const watcher = vscode.workspace.createFileSystemWatcher('src/tree-*.js');
  const provider = { onDidChangeTreeData: treeEmitter.event, getChildren: () => [] };
  vscode.window.registerTreeDataProvider('publisher.treeFile.tree', provider);
  const tree = vscode.window.createTreeView('publisher.treeFile.tree', { canSelectMany: false });
  context.subscriptions.push(
    tree,
    watcher,
    vscode.workspace.onDidCreateFiles(() => { seen.create += 1; }),
    vscode.workspace.onDidRenameFiles(() => { seen.rename += 1; }),
    vscode.workspace.onDidDeleteFiles(() => { seen.del += 1; }),
    watcher.onDidDelete(() => { seen.watcherDelete += 1; }),
    provider.onDidChangeTreeData(() => { seen.refresh += 1; }),
  );
  context.subscriptions.push(vscode.commands.registerCommand('publisher.treeFile.run', async () => {
    const source = vscode.Uri.file('src/tree-source.js');
    const moved = vscode.Uri.file('src/tree-moved.js');
    await vscode.workspace.fs.writeFile(source, Buffer.from('module.exports = "source";\\n'));
    treeEmitter.fire({ id: 'tree-refresh-1' });
    await vscode.workspace.fs.rename(source, moved);
    treeEmitter.fire({ id: 'tree-refresh-2' });
    await tree.reveal({ id: 'tree-node', label: 'Tree node' });
    await vscode.workspace.fs.delete(moved);
    await vscode.window.showInformationMessage('tree files create=' + seen.create + ' rename=' + seen.rename + ' delete=' + seen.del + ' refresh=' + seen.refresh + ' watcherDelete=' + seen.watcherDelete);
  }));
  return { ok: true };
};
`);
write(path.join(root, '.beast', 'extensions', 'publisher.terminal-task-workload', 'package.json'), JSON.stringify({
  publisher: 'publisher',
  name: 'terminal-task-workload',
  displayName: 'Terminal Task Workload',
  version: '1.0.0',
  main: 'extension.js',
  activationEvents: ['onCommand:publisher.terminalTask.run'],
  capabilities: ['terminal.execute'],
  contributes: {
    commands: [{ command: 'publisher.terminalTask.run', title: 'Run Terminal Task Workload' }],
    taskDefinitions: [{ type: 'publisher-terminal', required: [] }],
  },
}, null, 2));
write(path.join(root, '.beast', 'extensions', 'publisher.terminal-task-workload', 'extension.js'), `
const vscode = require('vscode');
exports.activate = function activate(context) {
  const seen = { terminalOpen: 0, terminalClose: 0, taskStart: 0, taskEnd: 0 };
  vscode.tasks.registerTaskProvider('publisher-terminal', { provideTasks: () => [], resolveTask: task => task });
  context.subscriptions.push(
    vscode.window.onDidOpenTerminal(() => { seen.terminalOpen += 1; }),
    vscode.window.onDidCloseTerminal(() => { seen.terminalClose += 1; }),
    vscode.tasks.onDidStartTaskProcess(() => { seen.taskStart += 1; }),
    vscode.tasks.onDidEndTaskProcess(() => { seen.taskEnd += 1; }),
  );
  context.subscriptions.push(vscode.commands.registerCommand('publisher.terminalTask.run', async () => {
    const terminal = vscode.window.createTerminal({ name: 'Parity terminal' });
    terminal.show();
    terminal.sendText('echo parity');
    await vscode.tasks.executeTask(new vscode.Task({ type: 'publisher-terminal' }, vscode.TaskScope.Workspace, 'Parity Task', 'publisher', new vscode.ShellExecution('echo parity-task')));
    terminal.dispose();
    await vscode.window.showInformationMessage('terminal events open=' + seen.terminalOpen + ' close=' + seen.terminalClose + ' taskStart=' + seen.taskStart + ' taskEnd=' + seen.taskEnd);
  }));
  return { ok: true };
};
`);

  const { safeWorkspacePath, taskCwd } = createWorkspacePathTools({ repoRoot: root });
const boundedProcess = createBoundedProcess({ repoRoot: root });
const workspaceFileHost = createWorkspaceFileHost({ repoRoot: root, safeWorkspacePath });
const gitHost = createGitHost({ repoRoot: root, boundedProcess, safeWorkspacePath });
const targetHost = {
  executionTargetSummary: target => target?.kind ? target : { kind: 'local', root, transport: 'local-stdio' },
  getActiveExecutionTarget: () => ({ kind: 'local', root, transport: 'local-stdio' }),
  remotePath: value => String(value || ''),
  shellQuote: value => `'${String(value ?? '').replace(/'/g, `'\\''`)}'`,
  runOnExecutionTarget: async (_target, cwd, command, args = [], options = {}) => {
    const result = run(command, args, { cwd, timeout: options.timeoutMs || 20000 });
    return { ok: result.status === 0, returncode: result.status, stdout: result.stdout || '', stderr: result.stderr || '', error: result.error ? String(result.error.message || result.error) : '' };
  },
  targetRelativePath: value => String(value || '').replace(/^\.\//, ''),
};
const taskTestHost = createTaskTestHost({
  repoRoot: root,
  workspaceFileCandidates: workspaceFileHost.workspaceFileCandidates,
  safeWorkspacePath,
  taskCwd,
  getTargetHost: () => targetHost,
});
const workspaceIndexHost = createWorkspaceIndexHost({
  repoRoot: root,
  workspaceFileHost,
  taskTestHost,
  gitHost,
  executionTargetHost: targetHost,
});
const beastExtensionHost = {
  lifecycleStatus: () => ({
    ok: true,
    active: { status: 'idle', health: 'healthy', mode: 'declarative-manifests', extensionCount: 0 },
    targets: [],
  }),
};

async function main() {
  const loadExtensionHostHandle = () => {
    const file = require.resolve('./beast-extension-host');
    delete require.cache[file];
    return require('./beast-extension-host').handle;
  };
  const host = createIdeServicesHost({
    repoRoot: root,
    ideCompatibilityHost: new IdeCompatibilityHost(desktop),
    gitHost,
    taskTestHost,
    executionTargetHost: targetHost,
    beastExtensionHost,
    workspaceIndexHost,
  });
  const focusedNodeTest = await taskTestHost.runWorkspaceTest(root, { id: 'npm:test', file: 'tests/sample.test.js', target: { kind: 'local', root } });
  const npmTask = await taskTestHost.runWorkspaceTask(root, { id: 'npm:check', target: { kind: 'local', root } });
  const aggregateTask = await taskTestHost.runWorkspaceTask(root, { id: 'aggregate', target: { kind: 'local', root } });
  const snapshot = await host.snapshot(root, { target: { kind: 'local', root } });
  const symbolQuery = await workspaceIndexHost.query(root, { target: { kind: 'local', root }, query: 'answer' });
  const definitionQuery = await workspaceIndexHost.query(root, { target: { kind: 'local', root }, query: 'double', mode: 'definition' });
  const referenceQuery = await workspaceIndexHost.query(root, { target: { kind: 'local', root }, query: 'triple', mode: 'references' });
  const dependentsQuery = await workspaceIndexHost.query(root, { target: { kind: 'local', root }, file: 'src/helper.js', mode: 'dependents' });
  const renamePreview = await workspaceIndexHost.query(root, { target: { kind: 'local', root }, query: 'double', newName: 'doubleValue', mode: 'renamePreview' });
  const roots = [{ path: path.join(root, '.beast', 'extensions'), origin: 'workspace' }];
  const discoveryResponse = await extensionHostHandle({ operation: 'discover', roots });
  const startupActivationResponse = await extensionHostHandle({
    operation: 'activateByEvent',
    roots,
    workspaceRoot: root,
    activationEvent: 'onStartupFinished',
    grantsByExtension: {
      'beast-workload-check': ['workspace.read', 'terminal.execute'],
      'beast.workload-dependency': ['workspace.read'],
    },
  });
  const executeResponse = await extensionHostHandle({
    operation: 'execute',
    roots,
    workspaceRoot: root,
    extensionId: 'beast-workload-check',
    command: 'beast.workloadCheck.run',
    granted: ['workspace.read', 'terminal.execute'],
  });
  const vscodeShimResponse = await extensionHostHandle({
    operation: 'execute',
    roots,
    workspaceRoot: root,
    extensionId: 'publisher.vscode-shim-check',
    command: 'publisher.vscodeShim.run',
    granted: ['workspace.read'],
  });
  const languageActivationResponse = await extensionHostHandle({
    operation: 'activateByEvent',
    roots,
    workspaceRoot: root,
    activationEvent: 'onLanguage:javascript',
    grantsByExtension: {
      'publisher.asset-runtime-check': ['workspace.read'],
    },
  });
  const assetRuntimeResponse = await extensionHostHandle({
    operation: 'execute',
    roots,
    workspaceRoot: root,
    extensionId: 'publisher.asset-runtime-check',
    command: 'publisher.assetRuntime.run',
    granted: ['workspace.read'],
  });
  const viewActivationResponse = await extensionHostHandle({
    operation: 'activateByEvent',
    roots,
    workspaceRoot: root,
    activationEvent: 'onView:publisher.lifecycle.tree',
    grantsByExtension: {
      'publisher.lifecycle-workload': ['workspace.read'],
    },
  });
  const webviewViewActivationResponse = await extensionHostHandle({
    operation: 'activateByEvent',
    roots,
    workspaceRoot: root,
    activationEvent: 'onView:publisher.webviewView.host',
    grantsByExtension: {
      'publisher.webview-view-workload': ['workspace.read'],
    },
  });
  const debugActivationResponse = await extensionHostHandle({
    operation: 'activateByEvent',
    roots,
    workspaceRoot: root,
    activationEvent: 'onDebug:node',
    grantsByExtension: {
      'publisher.lifecycle-workload': ['workspace.read'],
    },
  });
  const taskActivationResponse = await extensionHostHandle({
    operation: 'activateByEvent',
    roots,
    workspaceRoot: root,
    activationEvent: 'onTaskType:beast',
    grantsByExtension: {
      'publisher.lifecycle-workload': ['workspace.read'],
    },
  });
  const lifecycleCommandResponse = await extensionHostHandle({
    operation: 'execute',
    roots,
    workspaceRoot: root,
    extensionId: 'publisher.lifecycle-workload',
    command: 'publisher.lifecycle.run',
    granted: ['workspace.read'],
  });
  const firstPersistenceHostHandle = loadExtensionHostHandle();
  const persistenceWarmResponse = await firstPersistenceHostHandle({
    operation: 'activate',
    roots,
    workspaceRoot: root,
    extensionId: 'beast-persistence-check',
    activationEvent: 'onCommand:beast.persistenceCheck.report',
    granted: ['workspace.read'],
  });
  const secondPersistenceHostHandle = loadExtensionHostHandle();
  const persistenceReportResponse = await secondPersistenceHostHandle({
    operation: 'execute',
    roots,
    workspaceRoot: root,
    extensionId: 'beast-persistence-check',
    command: 'beast.persistenceCheck.report',
    granted: ['workspace.read'],
  });
  const firstWebviewStateHostHandle = loadExtensionHostHandle();
  const webviewStateWarmResponse = await firstWebviewStateHostHandle({
    operation: 'activate',
    roots,
    workspaceRoot: root,
    extensionId: 'publisher.webview-state-workload',
    activationEvent: 'onCommand:publisher.webviewState.run',
    granted: ['workspace.read'],
  });
  const secondWebviewStateHostHandle = loadExtensionHostHandle();
  const webviewStateReportResponse = await secondWebviewStateHostHandle({
    operation: 'execute',
    roots,
    workspaceRoot: root,
    extensionId: 'publisher.webview-state-workload',
    command: 'publisher.webviewState.run',
    granted: ['workspace.read'],
  });
  const webviewViewCommandResponse = await extensionHostHandle({
    operation: 'execute',
    roots,
    workspaceRoot: root,
    extensionId: 'publisher.webview-view-workload',
    command: 'publisher.webviewView.run',
    granted: ['workspace.read'],
  });
  const eventLifecycleResponse = await extensionHostHandle({
    operation: 'execute',
    roots,
    workspaceRoot: root,
    extensionId: 'publisher.event-lifecycle-workload',
    command: 'publisher.eventLifecycle.run',
    granted: ['workspace.read', 'workspace.write'],
  });
  const treeFileResponse = await extensionHostHandle({
    operation: 'execute',
    roots,
    workspaceRoot: root,
    extensionId: 'publisher.tree-file-workload',
    command: 'publisher.treeFile.run',
    granted: ['workspace.read', 'workspace.write'],
  });
  const terminalTaskResponse = await extensionHostHandle({
    operation: 'execute',
    roots,
    workspaceRoot: root,
    extensionId: 'publisher.terminal-task-workload',
    command: 'publisher.terminalTask.run',
    granted: ['terminal.execute'],
  });
  const stressResponse = await extensionHostHandle({ operation: 'stressProbe', roots, limit: 10, commandLimit: 5 });
  await taskTestHost.runWorkspaceTest(root, { id: 'npm:test', file: 'tests/sample.test.js', target: { kind: 'local', root }, retryOnFailure: true });
  const richSnapshot = await host.snapshot(root, { target: { kind: 'local', root } });
  const checks = [
    ['snapshot object type', snapshot.beast_object_type === 'beast_ide_services_snapshot'],
    ['LSP service rows', snapshot.services.lsp.languages.length >= 5],
    ['DAP service rows', snapshot.services.debug.adapters.length >= 2],
    ['workspace index detects Nim symbols', snapshot.services.index.ok && snapshot.services.index.languages.nim >= 2 && snapshot.services.index.symbolCount >= 4],
    ['semantic index resolves imports and references', snapshot.services.index.semantic.importEdgeCount >= 2 && snapshot.services.index.semantic.referenceCount >= 4 && snapshot.services.index.semantic.dependents['src/helper.js']?.includes('src/index.js')],
    ['semantic navigation queries work', symbolQuery.symbols.some(item => item.name === 'answer') && definitionQuery.definitions.some(item => item.file === 'src/helper.js' && /double/.test(item.preview || '')) && referenceQuery.references.some(item => item.file === 'src/math.nim') && dependentsQuery.dependents.includes('src/index.js')],
    ['IDE services expose navigation readiness', snapshot.services.navigation.ok && snapshot.services.navigation.supports.workspaceSymbols && snapshot.services.navigation.supports.references && snapshot.services.navigation.supports.dependents],
    ['diagnostics and code actions are indexed', snapshot.services.diagnostics.ok && snapshot.services.diagnostics.count >= 1 && snapshot.services.diagnostics.codeActionCount >= 1 && snapshot.services.index.diagnostics.some(item => item.code === 'todo-comment')],
    ['rename preview and refactor readiness work', snapshot.services.refactor.ok && snapshot.services.refactor.supportsRenamePreview && renamePreview.renamePreview.ok && renamePreview.renamePreview.editCount >= 2 && renamePreview.renamePreview.files.some(item => item.file === 'src/index.js')],
    ['focused node test run passed', focusedNodeTest.ok && focusedNodeTest.receipt?.id?.startsWith('TEST-')],
    ['npm task run passed', npmTask.ok && npmTask.receipt?.id?.startsWith('TASK-')],
    ['dependent aggregate task run passed', aggregateTask.ok && aggregateTask.dependencies?.length === 1 && aggregateTask.dependencies[0].ok && aggregateTask.task.dependsOrder === 'sequence'],
    ['test explorer detects pytest/npm/js nodes/history', snapshot.services.tests.testCount >= 2 && snapshot.services.tests.fileCount >= 2 && snapshot.services.tests.nodeCount >= 2 && snapshot.services.tests.frameworks.includes('node:test') && snapshot.services.tests.historyCount >= 1],
    ['language service matrix is present', richSnapshot.services.lsp.matrix.length >= 2 && richSnapshot.services.lsp.matrix.some(row => row.language === 'javascript')],
    ['debug handoff profiles are present', Array.isArray(richSnapshot.services.debug.profiles) && richSnapshot.services.debug.profiles.some(profile => profile.id === 'launch:Debug sample Python') && richSnapshot.services.debug.launch.compounds.length === 1],
    ['test history includes retry metadata', richSnapshot.services.tests.recent.some(row => Array.isArray(row.attempts) || Number(row.retryCount || 0) >= 0)],
    ['task service reports task history and dependency semantics', snapshot.services.tasks.ok && snapshot.services.tasks.taskCount >= 4 && snapshot.services.tasks.historyCount >= 3 && snapshot.services.tasks.dependencyTaskCount >= 1 && snapshot.services.tasks.problemMatcherCount >= 1 && snapshot.services.tasks.presentationCount >= 1],
    ['SCM detects worktree change', snapshot.services.scm.ok && snapshot.services.scm.counts.unstaged >= 1],
    ['extension lifecycle included', Boolean(snapshot.services.extensions.lifecycle)],
    ['extension workload is discovered', (discoveryResponse.extensions || []).some(extension => extension.id === 'beast-workload-check')],
    ['extension startup activation covers dependency chain', startupActivationResponse.ok && startupActivationResponse.activated >= 2 && (startupActivationResponse.results || []).some(row => row.id === 'beast-workload-check' && row.ok) && (startupActivationResponse.results || []).some(row => row.id === 'beast.workload-dependency' && row.ok) && ['storage','secret'].every(kind => (startupActivationResponse.actionKinds || []).includes(kind))],
    ['extension workload executes mediated actions', executeResponse.extensionId === 'beast-workload-check' && (executeResponse.actions || []).some(action => action.kind === 'notice') && (executeResponse.actions || []).some(action => action.kind === 'navigate') && (executeResponse.actions || []).some(action => action.kind === 'webview' && action.payload?.postMessage) && (executeResponse.actions || []).some(action => action.kind === 'tree' && action.payload?.reveal) && ['status','tree','webview','terminal','config','task','watcher','storage','secret'].every(kind => (executeResponse.actionKinds || []).includes(kind))],
    ['VS Code package shim is discovered', (discoveryResponse.extensions || []).some(extension => extension.id === 'publisher.vscode-shim-check' && extension.manifestKind === 'package.json' && extension.compatibility === 'vscode-package-json')],
    ['VS Code package shim activates registered command', vscodeShimResponse.compatibility === 'vscode-package-json' && (vscodeShimResponse.registeredCommands || []).includes('publisher.vscodeShim.run') && (vscodeShimResponse.actions || []).some(action => action.kind === 'notice') && (vscodeShimResponse.actions || []).some(action => action.kind === 'navigate')],
    ['language activation covers packaged extension workloads', languageActivationResponse.ok && (languageActivationResponse.results || []).some(row => row.id === 'publisher.asset-runtime-check' && row.ok)],
    ['packaged extension assets and node_modules resolve inside sandbox', assetRuntimeResponse.compatibility === 'vscode-package-json' && (assetRuntimeResponse.registeredCommands || []).includes('publisher.assetRuntime.run') && (assetRuntimeResponse.actions || []).some(action => action.kind === 'notice' && String(action.payload?.message || '').includes('asset banner: BEAST asset runtime ready')) && (assetRuntimeResponse.actions || []).some(action => action.kind === 'navigate')],
    ['view activation covers packaged lifecycle workloads', viewActivationResponse.ok && (viewActivationResponse.results || []).some(row => row.id === 'publisher.lifecycle-workload' && row.ok) && (viewActivationResponse.actionKinds || []).includes('tree')],
    ['view activation covers hosted webview view providers', webviewViewActivationResponse.ok && (webviewViewActivationResponse.results || []).some(row => row.id === 'publisher.webview-view-workload' && row.ok) && (webviewViewActivationResponse.actions || []).some(action => action.kind === 'webview' && action.payload?.viewProvider === true) && (webviewViewActivationResponse.actions || []).some(action => action.kind === 'webview' && action.payload?.htmlBytes > 0) && (webviewViewActivationResponse.actions || []).some(action => action.kind === 'webview' && action.payload?.postMessage?.type === 'restore') && (webviewViewActivationResponse.actionKinds || []).includes('status')],
    ['debug activation covers packaged lifecycle workloads', debugActivationResponse.ok && debugActivationResponse.matched >= 1 && debugActivationResponse.activated >= 1 && (debugActivationResponse.results || []).some(row => row.id === 'publisher.lifecycle-workload' && row.ok && (row.contributionSummary?.debuggers || 0) >= 1)],
    ['task activation covers packaged lifecycle workloads', taskActivationResponse.ok && taskActivationResponse.matched >= 1 && taskActivationResponse.activated >= 1 && (taskActivationResponse.results || []).some(row => row.id === 'publisher.lifecycle-workload' && row.ok && (row.contributionSummary?.taskDefinitions || 0) >= 1)],
    ['packaged lifecycle workload command restores tree interaction', lifecycleCommandResponse.compatibility === 'vscode-package-json' && (lifecycleCommandResponse.registeredCommands || []).includes('publisher.lifecycle.run') && (lifecycleCommandResponse.actions || []).some(action => action.kind === 'tree' && action.payload?.reveal?.id === 'lifecycle-node') && (lifecycleCommandResponse.actions || []).some(action => action.kind === 'notice' && String(action.payload?.message || '').includes('lifecycle workload ready'))],
    ['extension persistence survives fresh host lifecycles', persistenceWarmResponse.extensionId === 'beast-persistence-check' && (persistenceWarmResponse.registeredCommands || []).includes('beast.persistenceCheck.report') && ['storage','secret'].every(kind => (persistenceWarmResponse.actionKinds || []).includes(kind)) && (persistenceReportResponse.actions || []).some(action => action.kind === 'notice' && String(action.payload?.message || '').includes('persist launches=2') && String(action.payload?.message || '').includes('previous=persisted-1') && String(action.payload?.message || '').includes('secret=persisted-2'))],
    ['packaged webview state workload restores persisted UI state', webviewStateWarmResponse.compatibility === 'vscode-package-json' && (webviewStateWarmResponse.registeredCommands || []).includes('publisher.webviewState.run') && (webviewStateWarmResponse.actions || []).some(action => action.kind === 'webview' && action.payload?.postMessage?.type === 'restore' && action.payload?.postMessage?.restoreCount === 1) && (webviewStateWarmResponse.actions || []).some(action => action.kind === 'tree' && action.payload?.provider === true) && ['storage','tree','webview'].every(kind => (webviewStateWarmResponse.actionKinds || []).includes(kind))],
    ['packaged webview state workload emits refresh and snapshot choreography', webviewStateReportResponse.compatibility === 'vscode-package-json' && (webviewStateReportResponse.actions || []).some(action => action.kind === 'tree' && action.payload?.reveal?.id === 'node-2') && (webviewStateReportResponse.actions || []).some(action => action.kind === 'webview' && action.payload?.postMessage?.type === 'refresh' && action.payload?.postMessage?.selectedNode === 'node-2') && (webviewStateReportResponse.actions || []).some(action => action.kind === 'webview' && action.payload?.postMessage?.type === 'snapshot' && action.payload?.postMessage?.persisted === true) && (webviewStateReportResponse.actions || []).some(action => action.kind === 'notice' && String(action.payload?.message || '').includes('webview state restore=2 node=node-2'))],
    ['hosted webview view workload command preserves output and command routing', webviewViewCommandResponse.compatibility === 'vscode-package-json' && (webviewViewCommandResponse.registeredCommands || []).includes('publisher.webviewView.run') && (webviewViewCommandResponse.actions || []).some(action => action.kind === 'notice' && action.payload?.channel === 'Webview View Workload') && (webviewViewCommandResponse.actions || []).some(action => action.kind === 'navigate') && (webviewViewCommandResponse.actions || []).some(action => action.kind === 'notice' && String(action.payload?.message || '').includes('webview view workload ready'))],
    ['event lifecycle workload receives document, config, save, and watcher callbacks', eventLifecycleResponse.compatibility === 'vscode-package-json' && (eventLifecycleResponse.actionKinds || []).includes('watcher') && (eventLifecycleResponse.actionKinds || []).includes('config') && (eventLifecycleResponse.actions || []).some(action => action.kind === 'language' && action.payload?.feature === 'textDocument.open') && (eventLifecycleResponse.actions || []).some(action => action.kind === 'language' && action.payload?.feature === 'textDocument.save') && (eventLifecycleResponse.actions || []).some(action => action.kind === 'notice' && String(action.payload?.message || '').includes('events open=1 change=2 save=2 config=1 create=1 watcherChange=1 file=index.js'))],
    ['tree/file workload receives create rename delete and tree refresh callbacks', treeFileResponse.compatibility === 'vscode-package-json' && (treeFileResponse.actions || []).some(action => action.kind === 'tree' && action.payload?.refresh === true) && (treeFileResponse.actions || []).some(action => action.kind === 'tree' && action.payload?.reveal?.id === 'tree-node') && (treeFileResponse.actions || []).some(action => action.kind === 'language' && action.payload?.feature === 'textDocument.rename') && (treeFileResponse.actions || []).some(action => action.kind === 'language' && action.payload?.feature === 'textDocument.delete') && (treeFileResponse.actions || []).some(action => action.kind === 'notice' && String(action.payload?.message || '').includes('tree files create=1 rename=1 delete=1 refresh=2 watcherDelete=2'))],
    ['terminal/task workload receives lifecycle callbacks', terminalTaskResponse.compatibility === 'vscode-package-json' && (terminalTaskResponse.actionKinds || []).includes('terminal') && (terminalTaskResponse.actionKinds || []).includes('task') && (terminalTaskResponse.actions || []).some(action => action.kind === 'terminal' && action.payload?.created === true && action.payload?.name === 'Parity terminal') && (terminalTaskResponse.actions || []).some(action => action.kind === 'terminal' && action.payload?.disposed === true && action.payload?.name === 'Parity terminal') && (terminalTaskResponse.actions || []).some(action => action.kind === 'task' && action.payload?.execute === true && action.payload?.name === 'Parity Task') && (terminalTaskResponse.actions || []).some(action => action.kind === 'notice' && String(action.payload?.message || '').includes('terminal events open=1 close=1 taskStart=1 taskEnd=1'))],
    ['extension stress probe passes', stressResponse.ok && stressResponse.extensionCount >= 2 && stressResponse.commandCount >= 2],
    ['score is bounded', snapshot.score.total === 8 && snapshot.score.percent >= 80],
  ];
  const failed = checks.filter(([, ok]) => !ok).map(([name]) => name);
  const report = { ok: failed.length === 0, checks: checks.length, failed, snapshot: richSnapshot, semanticQueries: { symbolQuery, definitionQuery, referenceQuery, dependentsQuery, renamePreview }, extensionWorkload: { discoveryResponse, startupActivationResponse, executeResponse, vscodeShimResponse, languageActivationResponse, assetRuntimeResponse, viewActivationResponse, webviewViewActivationResponse, debugActivationResponse, taskActivationResponse, lifecycleCommandResponse, persistenceWarmResponse, persistenceReportResponse, webviewStateWarmResponse, webviewStateReportResponse, webviewViewCommandResponse, eventLifecycleResponse, treeFileResponse, terminalTaskResponse, stressResponse } };
  const reportPath = path.join(repo, 'build', 'IDE_SERVICES_PARITY.json');
  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  fs.writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
  console.log(JSON.stringify({ ok: report.ok, checks: report.checks, failed: report.failed }, null, 2));
  process.exit(report.ok ? 0 : 1);
}

main().catch(error => {
  console.error(error.stack || String(error));
  process.exit(1);
});
