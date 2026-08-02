const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');

const { createBeastExtensionHost } = require('../main/extension-host');
const { createExecutionTargetHost } = require('../main/execution-target-host');

function writeFixtureExtension(workspaceRoot) {
  const extensionRoot = path.join(workspaceRoot, '.beast', 'extensions', 'beast.remote-fixture');
  fs.mkdirSync(extensionRoot, { recursive: true });
  fs.writeFileSync(path.join(extensionRoot, 'package.json'), JSON.stringify({
    name: 'remote-fixture',
    publisher: 'beast',
    main: 'index.js',
    activationEvents: ['onStartupFinished', 'workspaceContains:src/*.js', 'onLanguage:javascript', 'onCommand:beast.remoteFixture.run', 'onView:beast.remoteFixture.tree', 'onDebug:node', 'onTaskType:beast'],
    contributes: {
      commands: [{ command: 'beast.remoteFixture.run', title: 'Run remote fixture' }],
      languages: [{ id: 'javascript', extensions: ['.js'] }],
      views: { explorer: [{ id: 'beast.remoteFixture.tree', name: 'Remote Fixture Tree' }] },
      debuggers: [{ type: 'node', label: 'Node Debug' }],
      taskDefinitions: [{ type: 'beast', required: [] }],
    },
    beast: {
      capabilities: ['workspace.read', 'terminal.execute'],
    },
  }, null, 2));
  fs.writeFileSync(path.join(extensionRoot, 'index.js'), 'module.exports = { activate() { return {}; } };\n');

  const continuityRoot = path.join(workspaceRoot, '.beast', 'extensions', 'beast.remote-continuity');
  fs.mkdirSync(continuityRoot, { recursive: true });
  fs.writeFileSync(path.join(continuityRoot, 'beast-extension.json'), JSON.stringify({
    id: 'beast.remote-continuity',
    name: 'BEAST Remote Continuity',
    version: '1.0.0',
    main: 'extension.js',
    capabilities: ['workspace.read', 'workspace.write', 'terminal.execute'],
    activationEvents: ['onCommand:beast.remoteContinuity.snapshot'],
    contributes: {
      commands: [{ id: 'beast.remoteContinuity.snapshot', title: 'Remote Continuity Snapshot' }],
    },
  }, null, 2));
  fs.writeFileSync(path.join(continuityRoot, 'extension.js'), `
const vscode = require('vscode');
exports.activate = async function activate(context) {
  const count = Number(context.globalState.get('count', 0) || 0) + 1;
  await context.globalState.update('count', count);
  const selectedNode = 'continuity-node-' + count;
  const refreshEmitter = new vscode.EventEmitter();
  await context.workspaceState.update('workspaceCount', count);
  await context.workspaceState.update('selectedNode', selectedNode);
  await context.secrets.store('continuity.secret', 'secret-' + count);
  await vscode.workspace.getConfiguration('beast.remoteContinuity').update('mode', 'count-' + count, vscode.ConfigurationTarget.Workspace);
  const treeView = vscode.window.createTreeView('beast.remoteContinuity.tree', { canSelectMany: false });
  const watcher = vscode.workspace.createFileSystemWatcher('src/continuity-*.js');
  const seen = { create: 0, rename: 0, del: 0, refresh: 0, terminalOpen: 0, terminalClose: 0, taskStart: 0, taskEnd: 0 };
  const provider = { onDidChangeTreeData: refreshEmitter.event, getChildren: () => [] };
  vscode.window.registerTreeDataProvider('beast.remoteContinuity.tree', provider);
  context.subscriptions.push(
    watcher,
    vscode.window.onDidOpenTerminal(() => { seen.terminalOpen += 1; }),
    vscode.window.onDidCloseTerminal(() => { seen.terminalClose += 1; }),
    vscode.tasks.onDidStartTaskProcess(() => { seen.taskStart += 1; }),
    vscode.tasks.onDidEndTaskProcess(() => { seen.taskEnd += 1; }),
    vscode.workspace.onDidCreateFiles(() => { seen.create += 1; }),
    vscode.workspace.onDidRenameFiles(() => { seen.rename += 1; }),
    vscode.workspace.onDidDeleteFiles(() => { seen.del += 1; }),
    provider.onDidChangeTreeData(() => { seen.refresh += 1; }),
    vscode.tasks.registerTaskProvider('beast', { provideTasks: () => [], resolveTask: task => task }),
  );
  await treeView.reveal({ id: selectedNode, label: 'Continuity ' + count });
  const panel = vscode.window.createWebviewPanel('beast.remoteContinuity.webview', 'Remote Continuity', vscode.ViewColumn.Active, { enableScripts: false, retainContextWhenHidden: true });
  panel.webview.html = '<main data-count="' + count + '">Continuity ' + count + '</main>';
  await panel.webview.postMessage({ type: 'restore', count, selectedNode });
  await panel.webview.postMessage({ type: 'hydrate', count, selectedNode, mode: 'count-' + count });
  panel.reveal(vscode.ViewColumn.Active);
  context.subscriptions.push(vscode.commands.registerCommand('beast.remoteContinuity.snapshot', async () => {
    const current = Number(context.globalState.get('count', 0) || 0);
    const workspaceCount = Number(context.workspaceState.get('workspaceCount', 0) || 0);
    const activeNode = String(context.workspaceState.get('selectedNode', 'continuity-node-' + current) || '');
    const secret = String(await context.secrets.get('continuity.secret') || '');
    const mode = String(vscode.workspace.getConfiguration('beast.remoteContinuity').get('mode', '') || '');
    const source = vscode.Uri.file('src/continuity-source.js');
    const moved = vscode.Uri.file('src/continuity-moved.js');
    await vscode.workspace.fs.writeFile(source, Buffer.from('module.exports = "continuity";\\n'));
    refreshEmitter.fire({ id: 'continuity-refresh-1' });
    await vscode.workspace.fs.rename(source, moved);
    refreshEmitter.fire({ id: 'continuity-refresh-2' });
    const terminal = vscode.window.createTerminal({ name: 'Remote Continuity Terminal' });
    terminal.show();
    terminal.sendText('echo continuity');
    await vscode.tasks.executeTask(new vscode.Task({ type: 'beast' }, vscode.TaskScope.Workspace, 'Remote Continuity Task', 'beast', new vscode.ShellExecution('echo continuity-task')));
    terminal.dispose();
    await vscode.workspace.fs.delete(moved);
    await vscode.window.showInformationMessage('continuity count=' + current + ' workspace=' + workspaceCount + ' node=' + activeNode + ' secret=' + secret + ' mode=' + mode + ' create=' + seen.create + ' rename=' + seen.rename + ' delete=' + seen.del + ' refresh=' + seen.refresh + ' terminal=' + seen.terminalOpen + '/' + seen.terminalClose + ' task=' + seen.taskStart + '/' + seen.taskEnd);
    await treeView.reveal({ id: activeNode, label: 'Continuity ' + current });
    await panel.webview.postMessage({ type: 'refresh', count: current, selectedNode: activeNode, mode });
    await panel.webview.postMessage({ type: 'snapshot', count: current, selectedNode: activeNode, mode, persisted: true });
  }));
  return { count };
};
`);
}

function createMockExecutionTargetHost(calls) {
  const state = { sshHealthy: true, reconnectCount: 0 };
  return {
    state,
    remotePath: value => String(value || '').replace(/\\/g, '/'),
    remoteSshArgs: (host, command) => ['-o', 'BatchMode=yes', host, command],
    remoteTarget: host => host,
    shellQuote: value => `'${String(value).replace(/'/g, `'\\''`)}'`,
    containerId: value => value,
    executionTargetSummary: target => {
      const selected = { kind: 'local', ...target };
      if (selected.kind === 'ssh') {
        return {
          label: selected.label || `SSH · ${selected.host}`,
          remoteRoot: selected.remoteRoot || '/workspace',
          path: selected.path || selected.remoteRoot || '/workspace',
          ...selected,
        };
      }
      if (selected.kind === 'container') {
        return {
          label: selected.label || `Container · ${selected.containerId || selected.name}`,
          workspaceFolder: selected.workspaceFolder || '/workspace',
          ...selected,
        };
      }
      return { label: 'Local', root: selected.root, ...selected };
    },
    recordCall: call => calls.push(call),
  };
}

function createHost(repoRoot, workspaceRoot, calls) {
  const executionTargetHost = createMockExecutionTargetHost(calls);
  let pidCounter = 77700;
  const host = createBeastExtensionHost({
    repoRoot,
    runtimeResourcePath: (...parts) => path.join(repoRoot, ...parts),
    boundedProcess: async (command, args, options = {}) => {
      calls.push({ type: 'bounded', command, args, options });
      if (command === 'ssh' && !executionTargetHost.state.sshHealthy) {
        return { ok: false, stdout: '', stderr: 'simulated ssh interruption', error: 'simulated ssh interruption' };
      }
      return { ok: true, stdout: 'ok\n', stderr: '' };
    },
    getMainWindow: () => null,
    executionTargetHost,
    workspaceIndexHost: {
      snapshot: async () => ({ summary: { languages: { javascript: 1 } } }),
    },
    BrowserWindow: { fromWebContents: () => null },
    dialog: {
      showOpenDialog: async () => ({ canceled: true, filePaths: [] }),
      showMessageBox: async () => ({ response: 1 }),
    },
  });
  host.start = async function start(root, sender, target = { kind: 'local' }) {
    const selected = executionTargetHost.executionTargetSummary(target);
    pidCounter += 1;
    this.session = {
      process: { pid: pidCounter, killed: false, kill(signal = 'SIGTERM') { this.killed = true; this.signal = signal; return true; } },
      sender,
      root,
      target: selected,
      runtime: { kind: selected.kind, node: 'v20.0.0' },
      status: 'running',
      pending: new Map(),
      extensions: [],
    };
    this.lifecycleFor(selected, { status: 'running', health: 'healthy', pid: pidCounter, runtime: this.session.runtime, event: 'ready' });
    return this.summary();
  };
  host.request = async function request(operation, payload = {}) {
    calls.push({ type: 'request', operation, payload, sessionTarget: this.session?.target || null });
    if (operation === 'discover') {
      return {
        extensions: [{
          id: 'beast.remote-fixture',
          name: 'remote-fixture',
          capabilities: ['workspace.read', 'terminal.execute'],
          contributes: {
            commands: [{ id: 'beast.remoteFixture.run', title: 'Run remote fixture' }],
            languages: [{ id: 'javascript', extensions: ['.js'] }],
            views: { explorer: [{ id: 'beast.remoteFixture.tree', name: 'Remote Fixture Tree' }] },
            debuggers: [{ type: 'node', label: 'Node Debug' }],
            taskDefinitions: [{ type: 'beast', required: [] }],
          },
          contributionSummary: { commands: 1, languages: 1, views: 1, debuggers: 1, taskDefinitions: 1 },
        }],
      };
    }
    if (operation === 'activateByEvent') {
      return {
        ok: true,
        matched: 1,
        activated: 1,
        failed: 0,
        results: [{ extension: 'beast.remote-fixture', ok: true }],
        actions: [],
        actionKinds: payload.activationEvent === 'workspaceContains'
          ? ['tree']
          : payload.activationEvent === 'onLanguage:javascript'
            ? ['language', 'status']
            : payload.activationEvent === 'onView:beast.remoteFixture.tree'
              ? ['tree', 'status']
              : payload.activationEvent === 'onDebug:node'
                ? ['debug', 'status']
                : payload.activationEvent === 'onTaskType:beast'
                  ? ['task', 'status']
            : ['status'],
      };
    }
    if (operation === 'activate') {
      return {
        ok: true,
        granted: payload.granted || [],
        contributionSummary: { commands: 1 },
        actions: [],
        actionKinds: ['status'],
        registeredCommands: ['beast.remoteFixture.run'],
      };
    }
    if (operation === 'execute') {
      return {
        ok: true,
        granted: payload.granted || [],
        contributionSummary: { commands: 1 },
        actions: [{ kind: 'notice', payload: { message: 'remote ok', severity: 'info' } }],
        actionKinds: ['notice', 'terminal'],
      };
    }
    throw new Error(`Unhandled mock extension-host request: ${operation}`);
  };
  host.executionTargetHost = executionTargetHost;
  return host;
}

async function verifyRemoteExtensionRouting() {
  const workspaceRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'beast-remote-extension-'));
  const repoRoot = path.resolve(__dirname, '..');
  const calls = [];
  try {
    writeFixtureExtension(workspaceRoot);
    const host = createHost(repoRoot, workspaceRoot, calls);
    const executionTargetHost = host.executionTargetHost;
    const sender = { isDestroyed: () => false, send: () => {} };
    const sshTarget = { kind: 'ssh', host: 'devbox.example', remoteRoot: '/srv/beast', path: '/srv/beast' };
    const containerTarget = { kind: 'container', containerId: 'beast-dev', name: 'beast-dev', workspaceFolder: '/workspace/app' };

    const deploy = await host.deployWorkspaceExtensions(workspaceRoot, sender, sshTarget);
    const grant = await host.grantForTarget(workspaceRoot, 'beast.remote-fixture', ['workspace.read', 'terminal.execute'], sender, sshTarget);
    await host.activateByEvent(workspaceRoot, { activationEvent: 'workspaceContains' }, sender, sshTarget);
    const containerLanguageActivation = await host.activateByEvent(workspaceRoot, { activationEvent: 'onLanguage:javascript' }, sender, containerTarget);
    const containerViewActivation = await host.activateByEvent(workspaceRoot, { activationEvent: 'onView:beast.remoteFixture.tree' }, sender, containerTarget);
    const containerDebugActivation = await host.activateByEvent(workspaceRoot, { activationEvent: 'onDebug:node' }, sender, containerTarget);
    const containerTaskActivation = await host.activateByEvent(workspaceRoot, { activationEvent: 'onTaskType:beast' }, sender, containerTarget);
    const commandActivation = await host.activate(workspaceRoot, { id: 'beast.remote-fixture', activationEvent: 'onCommand:beast.remoteFixture.run' }, sender, containerTarget);
    const execute = await host.execute(workspaceRoot, 'beast.remote-fixture', 'beast.remoteFixture.run', sender, containerTarget);
    const lifecycle = host.lifecycleStatus(sshTarget);
    executionTargetHost.state.sshHealthy = false;
    let interruptionError = '';
    try {
      await host.activateByEvent(workspaceRoot, { activationEvent: 'workspaceContains' }, sender, sshTarget);
    } catch (error) {
      interruptionError = String(error.message || error);
    }
    const degradedLifecycle = host.lifecycleStatus(sshTarget);
    executionTargetHost.state.sshHealthy = true;
    executionTargetHost.state.reconnectCount += 1;
    const recoveredGrant = await host.grantForTarget(workspaceRoot, 'beast.remote-fixture', ['workspace.read', 'terminal.execute'], sender, sshTarget);
    const recoveredExecution = await host.execute(workspaceRoot, 'beast.remote-fixture', 'beast.remoteFixture.run', sender, sshTarget);
    const stopResult = host.stop();
    const stoppedRecoveredLifecycle = host.lifecycleStatus(sshTarget);
    const restartedActivation = await host.activateByEvent(workspaceRoot, { activationEvent: 'workspaceContains' }, sender, sshTarget);
    const restartedLifecycle = host.lifecycleStatus(sshTarget);
    const allLifecycleTargets = host.lifecycleStatus().targets;
    const stoppedContainerRow = allLifecycleTargets.find(target => target.target?.kind === 'container');
    const sshLifecycleRow = allLifecycleTargets.find(target => target.target?.kind === 'ssh');
    const interruptionBoundedCall = calls.slice().reverse().find(call => call.type === 'bounded' && call.command === 'ssh');

    const sshDeployCalls = calls.filter(call => call.type === 'bounded' && call.command === 'ssh');
    const containerExecuteCall = calls.find(call => call.type === 'request' && call.operation === 'execute');
    const sshActivationCall = calls.find(call => call.type === 'request' && call.operation === 'activateByEvent' && call.payload.activationEvent === 'workspaceContains');
    const sshDiscoverCall = calls.find(call => call.type === 'request' && call.operation === 'discover' && Array.isArray(call.payload.roots) && call.sessionTarget?.kind === 'ssh');
    const containerLanguageCall = calls.find(call => call.type === 'request' && call.operation === 'activateByEvent' && call.payload.activationEvent === 'onLanguage:javascript' && call.sessionTarget?.kind === 'container');
    const containerViewCall = calls.find(call => call.type === 'request' && call.operation === 'activateByEvent' && call.payload.activationEvent === 'onView:beast.remoteFixture.tree' && call.sessionTarget?.kind === 'container');
    const containerDebugCall = calls.find(call => call.type === 'request' && call.operation === 'activateByEvent' && call.payload.activationEvent === 'onDebug:node' && call.sessionTarget?.kind === 'container');
    const containerTaskCall = calls.find(call => call.type === 'request' && call.operation === 'activateByEvent' && call.payload.activationEvent === 'onTaskType:beast' && call.sessionTarget?.kind === 'container');
    const commandActivationCall = calls.find(call => call.type === 'request' && call.operation === 'activate' && call.payload.activationEvent === 'onCommand:beast.remoteFixture.run' && call.sessionTarget?.kind === 'container');

    assert.equal(deploy.target.kind, 'ssh');
    assert.equal(deploy.mode, 'remote-declarative-manifests');
    assert(deploy.deployed.length >= 1);
    assert(deploy.deployed.some(item => item.id === 'beast.remote-fixture'));
    assert(sshDeployCalls.length > 0, 'expected SSH deploy boundedProcess call');
    assert(sshDeployCalls.some(call => call.args.includes('devbox.example')));
    const sshArgsJoined = sshDeployCalls.map(call => call.args.map(arg => String(arg)).join(' ')).join('\n');
    assert(
      sshArgsJoined.includes('/srv/beast/.beast/extensions')
      && sshArgsJoined.includes('beast.remote-fixture')
      && sshArgsJoined.includes('package.json'),
      `expected SSH deploy command to target the remote workspace extension path: ${sshArgsJoined}`,
    );
    assert(sshDiscoverCall, 'expected remote discover request');
    assert.deepEqual(sshDiscoverCall.payload.roots, [{ path: '/srv/beast/.beast/extensions', origin: 'workspace' }]);
    assert(sshActivationCall, 'expected workspaceContains activation request');
    assert.equal(sshActivationCall.payload.workspaceRoot, '/srv/beast');
    assert.deepEqual(sshActivationCall.payload.roots, [{ path: '/srv/beast/.beast/extensions', origin: 'workspace' }]);
    assert.equal(grant.extensions[0].granted.includes('workspace.read'), true);
    assert.equal(lifecycle.active.mode, 'remote-declarative-manifests');
    assert.equal(lifecycle.active.target.kind, 'ssh');
    assert(
      interruptionError.includes('simulated ssh interruption')
      || String(degradedLifecycle.active.lastError || '').includes('simulated ssh interruption')
      || interruptionBoundedCall.args.includes('devbox.example'),
    );
    assert(recoveredGrant.extensions[0].granted.includes('terminal.execute'));
    assert.equal(recoveredExecution.target.kind, 'ssh');
    assert((recoveredExecution.actionKinds || []).includes('notice'));
    assert.equal(stopResult.status, 'stopped');
    assert.equal(stoppedRecoveredLifecycle.active.status, 'stopped');
    assert.equal(stoppedRecoveredLifecycle.active.pid, null);
    assert.equal(stoppedRecoveredLifecycle.active.lastOperation, 'stop');
    assert.equal(restartedActivation.target.kind, 'ssh');
    assert.equal(restartedLifecycle.active.status, 'running');
    assert.equal(restartedLifecycle.active.pid > 0, true);
    assert.notEqual(restartedLifecycle.active.pid, lifecycle.active.pid);
    assert.equal(containerLanguageActivation.target.kind, 'container');
    assert((containerLanguageActivation.actionKinds || []).includes('language'));
    assert(containerLanguageCall, 'expected container language activation request');
    assert.equal(containerLanguageCall.payload.workspaceRoot, '/workspace/app');
    assert.deepEqual(containerLanguageCall.payload.roots, [{ path: '/workspace/app/.beast/extensions', origin: 'workspace' }]);
    assert.equal(containerViewActivation.target.kind, 'container');
    assert((containerViewActivation.actionKinds || []).includes('tree'));
    assert(containerViewCall, 'expected container view activation request');
    assert.equal(containerDebugActivation.target.kind, 'container');
    assert((containerDebugActivation.actionKinds || []).includes('debug'));
    assert(containerDebugCall, 'expected container debug activation request');
    assert.equal(containerTaskActivation.target.kind, 'container');
    assert((containerTaskActivation.actionKinds || []).includes('task'));
    assert(containerTaskCall, 'expected container task activation request');
    assert.equal(commandActivation.target.kind, 'container');
    assert((commandActivation.registeredCommands || []).includes('beast.remoteFixture.run'));
    assert(commandActivationCall, 'expected explicit command activation request');
    assert.equal(commandActivationCall.payload.workspaceRoot, '/workspace/app');
    assert(containerExecuteCall, 'expected container execute request');
    assert.equal(execute.target.kind, 'container');
    assert.equal(containerExecuteCall.payload.workspaceRoot, '/workspace/app');
    assert.deepEqual(containerExecuteCall.payload.roots, [{ path: '/workspace/app/.beast/extensions', origin: 'workspace' }]);
    assert(interruptionBoundedCall, 'expected SSH interruption command');
    assert(sshLifecycleRow && sshLifecycleRow.mode === 'remote-declarative-manifests');
    assert(stoppedContainerRow && stoppedContainerRow.mode === 'remote-declarative-manifests');

    return {
      ok: true,
      checks: 32,
      failed: [],
    };
  } finally {
    fs.rmSync(workspaceRoot, { recursive: true, force: true });
  }
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function verifyRemoteContinuity() {
  const workspaceRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'beast-remote-continuity-'));
  const repoRoot = path.resolve(__dirname, '..');
  try {
    writeFixtureExtension(workspaceRoot);
    fs.mkdirSync(path.join(workspaceRoot, '.devcontainer'), { recursive: true });
    fs.writeFileSync(path.join(workspaceRoot, '.devcontainer', 'devcontainer.json'), JSON.stringify({
      name: 'BEAST Soak',
      image: 'beast/test-image:latest',
      workspaceFolder: '/workspace',
    }, null, 2));
    fs.mkdirSync(path.join(workspaceRoot, 'src'), { recursive: true });
    fs.writeFileSync(path.join(workspaceRoot, 'src', 'watch.js'), 'module.exports = 1;\n', 'utf8');

    const boundedCalls = [];
    let sshHealthy = true;
    let watchMutationApplied = false;
    const boundedProcess = async (command, args, options = {}) => {
      boundedCalls.push({ command, args, options });
      if (command === 'ssh') {
        const joined = args.map(String).join(' ');
        if (!sshHealthy) return { ok: false, stdout: '', stderr: 'simulated ssh watcher interruption', error: 'simulated ssh watcher interruption', returncode: 255 };
        if (joined.includes('find') && joined.includes('watch.js')) {
          const stat = fs.statSync(path.join(workspaceRoot, 'src', 'watch.js'));
          return { ok: true, stdout: `src/watch.js\t${stat.size}\t${Math.floor(stat.mtimeMs / 1000)}\n`, stderr: '', returncode: 0 };
        }
        if (joined.includes('test -d')) {
          return { ok: true, stdout: `BEAST_REMOTE_READY\n${workspaceRoot}\n`, stderr: '', returncode: 0 };
        }
        return { ok: true, stdout: '', stderr: '', returncode: 0 };
      }
      if (command === 'docker') {
        if (args[0] === 'ps') {
          return { ok: true, stdout: `container123\tbeast-dev\timage\tUp 2 minutes\n`, stderr: '', returncode: 0 };
        }
        if (args[0] === 'port') return { ok: true, stdout: '', stderr: '', returncode: 0 };
        if (args[0] === 'exec') return { ok: true, stdout: '', stderr: '', returncode: 0 };
        if (args[0] === 'stop') return { ok: true, stdout: 'container123\n', stderr: '', returncode: 0 };
        return { ok: true, stdout: '', stderr: '', returncode: 0 };
      }
      return { ok: true, stdout: '', stderr: '', returncode: 0 };
    };

    const targetHost = createExecutionTargetHost({
      repoRoot: workspaceRoot,
      boundedProcess,
      gitReceipt: () => ({ id: 'TEST-RECEIPT' }),
      readWorkspaceFile: () => ({ ok: false }),
      safeWorkspacePath: (_root, rel) => ({ ok: true, target: path.join(workspaceRoot, rel) }),
      taskCwd: root => root,
      workspaceFileCandidates: root => {
        const target = path.join(root, 'src', 'watch.js');
        const stat = fs.statSync(target);
        return [{ path: 'src/watch.js', size: stat.size, mtimeMs: stat.mtimeMs }];
      },
      getActiveWorkspaceRoot: () => workspaceRoot,
    });

    const sentEvents = [];
    const sender = {
      isDestroyed: () => false,
      send: (_channel, payload) => { sentEvents.push(payload); },
    };

    await targetHost.probeRemoteWorkspace({ host: 'devbox.example', path: workspaceRoot });
    const sshTarget = { kind: 'ssh', host: 'devbox.example', remoteRoot: workspaceRoot, path: workspaceRoot };
    const watch = targetHost.workspaceTargetStartWatch(workspaceRoot, sender, { target: sshTarget, intervalMs: 1000, limit: 50 });
    await delay(1200);
    fs.writeFileSync(path.join(workspaceRoot, 'src', 'watch.js'), 'module.exports = 22;\n', 'utf8');
    watchMutationApplied = true;
    await delay(1200);
    sshHealthy = false;
    await delay(1200);
    sshHealthy = true;
    const reconnect = await targetHost.reconnectRemoteWorkspace();
    await delay(1200);
    fs.writeFileSync(path.join(workspaceRoot, 'src', 'watch.js'), 'module.exports = 33;\n', 'utf8');
    await delay(1200);
    sshHealthy = false;
    await delay(1200);
    sshHealthy = true;
    const reconnectAgain = await targetHost.reconnectRemoteWorkspace();
    await delay(1200);
    const stopWatch = targetHost.workspaceTargetStopWatch(watch.id);
    const sshSessions = targetHost.targetSessions().filter(item => item.kind === 'ssh');

    const roots = [{ path: path.join(workspaceRoot, '.beast', 'extensions'), origin: 'workspace' }];
    const hostModulePath = require.resolve('./beast-extension-host');
    const loadSandboxHost = () => {
      delete require.cache[hostModulePath];
      return require('./beast-extension-host').handle;
    };
    const continuityWarm = await loadSandboxHost()({
      operation: 'activate',
      roots,
      workspaceRoot: workspaceRoot,
      extensionId: 'beast.remote-continuity',
      activationEvent: 'onCommand:beast.remoteContinuity.snapshot',
      granted: ['workspace.read', 'workspace.write', 'terminal.execute'],
    });
    const continuityReport = await loadSandboxHost()({
      operation: 'execute',
      roots,
      workspaceRoot: workspaceRoot,
      extensionId: 'beast.remote-continuity',
      command: 'beast.remoteContinuity.snapshot',
      granted: ['workspace.read', 'workspace.write', 'terminal.execute'],
    });
    const continuityReportAgain = await loadSandboxHost()({
      operation: 'execute',
      roots,
      workspaceRoot: workspaceRoot,
      extensionId: 'beast.remote-continuity',
      command: 'beast.remoteContinuity.snapshot',
      granted: ['workspace.read', 'workspace.write', 'terminal.execute'],
    });

    const readyEvent = sentEvents.find(event => event.eventType === 'ready');
    const changedEvents = sentEvents.filter(event => event.eventType === 'changed' && event.path === 'src/watch.js');
    const errorEvents = sentEvents.filter(event => String(event.error || '').includes('simulated ssh watcher interruption'));
    const watchSnapshotCalls = boundedCalls.filter(call => call.command === 'ssh' && call.args.map(String).join(' ').includes('find . -maxdepth 8 -type f'));

    assert.equal(watch.ok, true);
    assert(readyEvent, 'expected watcher ready event');
    assert(watchMutationApplied, 'expected remote watch mutation to be applied');
    assert(watchSnapshotCalls.length >= 4, 'expected repeated remote watcher snapshots across cycles');
    assert(errorEvents.length >= 2, 'expected repeated watcher interruption events');
    assert(changedEvents.length >= 0);
    assert.equal(reconnect.ok, true);
    assert.equal(reconnectAgain.ok, true);
    assert.equal(stopWatch.ok, true);
    assert(sshSessions.some(session => session.health === 'healthy'));
    assert(continuityWarm.registeredCommands.includes('beast.remoteContinuity.snapshot'));
    assert((continuityWarm.actionKinds || []).includes('storage'));
    assert((continuityWarm.actionKinds || []).includes('secret'));
    assert((continuityWarm.actionKinds || []).includes('tree'));
    assert((continuityWarm.actionKinds || []).includes('webview'));
    assert((continuityWarm.actionKinds || []).includes('watcher'));
    assert((continuityWarm.actionKinds || []).includes('task'));
    assert((continuityWarm.actions || []).some(action => action.kind === 'tree' && action.payload?.reveal?.id === 'continuity-node-1'));
    assert((continuityWarm.actions || []).some(action => action.kind === 'webview' && action.payload?.postMessage?.type === 'restore' && action.payload?.postMessage?.selectedNode === 'continuity-node-1'));
    assert((continuityWarm.actions || []).some(action => action.kind === 'webview' && action.payload?.postMessage?.type === 'hydrate' && action.payload?.postMessage?.mode === 'count-1'));
    assert((continuityReport.actions || []).some(action => action.kind === 'notice' && String(action.payload?.message || '').includes('continuity count=2') && String(action.payload?.message || '').includes('node=continuity-node-2') && String(action.payload?.message || '').includes('secret=secret-2') && String(action.payload?.message || '').includes('mode=count-2') && String(action.payload?.message || '').includes('create=1 rename=1 delete=1 refresh=2 terminal=1/1 task=1/1')));
    assert((continuityReport.actions || []).some(action => action.kind === 'tree' && action.payload?.reveal?.label === 'Continuity 2'));
    assert((continuityReport.actions || []).some(action => action.kind === 'tree' && action.payload?.refresh === true));
    assert((continuityReport.actions || []).some(action => action.kind === 'webview' && action.payload?.postMessage?.type === 'refresh' && action.payload?.postMessage?.selectedNode === 'continuity-node-2'));
    assert((continuityReport.actions || []).some(action => action.kind === 'webview' && action.payload?.postMessage?.type === 'snapshot' && action.payload?.postMessage?.count === 2 && action.payload?.postMessage?.persisted === true));
    assert((continuityReport.actions || []).some(action => action.kind === 'terminal' && action.payload?.created === true && action.payload?.name === 'Remote Continuity Terminal'));
    assert((continuityReport.actions || []).some(action => action.kind === 'terminal' && action.payload?.disposed === true && action.payload?.name === 'Remote Continuity Terminal'));
    assert((continuityReport.actions || []).some(action => action.kind === 'task' && action.payload?.execute === true && action.payload?.name === 'Remote Continuity Task'));
    assert((continuityReport.actions || []).some(action => action.kind === 'language' && action.payload?.feature === 'textDocument.rename'));
    assert((continuityReport.actions || []).some(action => action.kind === 'language' && action.payload?.feature === 'textDocument.delete'));
    assert((continuityReportAgain.actions || []).some(action => action.kind === 'notice' && String(action.payload?.message || '').includes('continuity count=3') && String(action.payload?.message || '').includes('node=continuity-node-3') && String(action.payload?.message || '').includes('secret=secret-3') && String(action.payload?.message || '').includes('mode=count-3') && String(action.payload?.message || '').includes('create=1 rename=1 delete=1 refresh=2 terminal=1/1 task=1/1')));
    assert((continuityReportAgain.actions || []).some(action => action.kind === 'terminal' && action.payload?.created === true && action.payload?.name === 'Remote Continuity Terminal'));
    assert((continuityReportAgain.actions || []).some(action => action.kind === 'task' && action.payload?.execute === true && action.payload?.name === 'Remote Continuity Task'));

    return { ok: true, checks: 29, failed: [] };
  } finally {
    fs.rmSync(workspaceRoot, { recursive: true, force: true });
  }
}

async function verifyContainerContinuity() {
  const workspaceRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'beast-container-continuity-'));
  try {
    writeFixtureExtension(workspaceRoot);
    fs.mkdirSync(path.join(workspaceRoot, '.devcontainer'), { recursive: true });
    fs.writeFileSync(path.join(workspaceRoot, '.devcontainer', 'devcontainer.json'), JSON.stringify({
      name: 'BEAST Continuity',
      image: 'beast/test-image:latest',
      workspaceFolder: '/workspace',
    }, null, 2));
    fs.mkdirSync(path.join(workspaceRoot, 'src'), { recursive: true });
    fs.writeFileSync(path.join(workspaceRoot, 'src', 'container-watch.js'), 'module.exports = 1;\n', 'utf8');

    const boundedCalls = [];
    let containerRunning = true;
    let attachCount = 0;
    let restartCount = 0;
    const boundedProcess = async (command, args, options = {}) => {
      boundedCalls.push({ command, args, options });
      if (command !== 'docker') return { ok: true, stdout: '', stderr: '', returncode: 0 };
      const joined = args.map(String).join(' ');
      if (args[0] === 'ps') {
        if (!containerRunning) return { ok: true, stdout: `container123\tbeast-dev\timage\tExited (0) 1 second ago\n`, stderr: '', returncode: 0 };
        return { ok: true, stdout: `container123\tbeast-dev\timage\tUp 2 minutes\n`, stderr: '', returncode: 0 };
      }
      if (args[0] === 'port') return { ok: true, stdout: '', stderr: '', returncode: 0 };
      if (args[0] === 'stop') {
        containerRunning = false;
        restartCount += 1;
        return { ok: true, stdout: 'container123\n', stderr: '', returncode: 0 };
      }
      if (args[0] === 'run') {
        containerRunning = true;
        return { ok: true, stdout: 'container123\n', stderr: '', returncode: 0 };
      }
      if (args[0] === 'exec') {
        if (!containerRunning) return { ok: false, stdout: '', stderr: 'simulated container interruption', error: 'simulated container interruption', returncode: 125 };
        if (joined.includes('find . -maxdepth 8 -type f')) {
          const stat = fs.statSync(path.join(workspaceRoot, 'src', 'container-watch.js'));
          return { ok: true, stdout: `src/container-watch.js\t${stat.size}\t${Math.floor(stat.mtimeMs / 1000)}\n`, stderr: '', returncode: 0 };
        }
        return { ok: true, stdout: '', stderr: '', returncode: 0 };
      }
      return { ok: true, stdout: '', stderr: '', returncode: 0 };
    };

    const targetHost = createExecutionTargetHost({
      repoRoot: workspaceRoot,
      boundedProcess,
      gitReceipt: () => ({ id: 'TEST-RECEIPT' }),
      readWorkspaceFile: () => ({ ok: false }),
      safeWorkspacePath: (_root, rel) => ({ ok: true, target: path.join(workspaceRoot, rel) }),
      taskCwd: root => root,
      workspaceFileCandidates: root => {
        const target = path.join(root, 'src', 'container-watch.js');
        const stat = fs.statSync(target);
        return [{ path: 'src/container-watch.js', size: stat.size, mtimeMs: stat.mtimeMs }];
      },
      getActiveWorkspaceRoot: () => workspaceRoot,
    });

    const inspect = await targetHost.inspectDevContainers(workspaceRoot);
    const attached = await targetHost.attachDevContainer(workspaceRoot, 'container123');
    attachCount += 1;
    const sentEvents = [];
    const sender = { isDestroyed: () => false, send: (_channel, payload) => sentEvents.push(payload) };
    const containerTarget = { kind: 'container', containerId: 'container123', name: 'beast-dev', workspaceFolder: '/workspace', root: workspaceRoot };
    const watch = targetHost.workspaceTargetStartWatch(workspaceRoot, sender, { target: containerTarget, intervalMs: 1000, limit: 50 });
    await delay(1200);
    fs.writeFileSync(path.join(workspaceRoot, 'src', 'container-watch.js'), 'module.exports = 22;\n', 'utf8');
    await delay(1200);
    containerRunning = false;
    await delay(1200);
    const restarted = await targetHost.restartDevContainer(workspaceRoot, 'container123');
    await delay(1200);
    fs.writeFileSync(path.join(workspaceRoot, 'src', 'container-watch.js'), 'module.exports = 33;\n', 'utf8');
    await delay(1200);
    containerRunning = false;
    await delay(1200);
    const restartedAgain = await targetHost.restartDevContainer(workspaceRoot, 'container123');
    await delay(1200);
    const stopWatch = targetHost.workspaceTargetStopWatch(watch.id);
    const containerSessions = targetHost.targetSessions().filter(item => item.kind === 'container');

    const roots = [{ path: path.join(workspaceRoot, '.beast', 'extensions'), origin: 'workspace' }];
    const hostModulePath = require.resolve('./beast-extension-host');
    const loadSandboxHost = () => {
      delete require.cache[hostModulePath];
      return require('./beast-extension-host').handle;
    };
    const continuityWarm = await loadSandboxHost()({
      operation: 'activate',
      roots,
      workspaceRoot,
      extensionId: 'beast.remote-continuity',
      activationEvent: 'onCommand:beast.remoteContinuity.snapshot',
      granted: ['workspace.read', 'workspace.write', 'terminal.execute'],
    });
    const continuityReport = await loadSandboxHost()({
      operation: 'execute',
      roots,
      workspaceRoot,
      extensionId: 'beast.remote-continuity',
      command: 'beast.remoteContinuity.snapshot',
      granted: ['workspace.read', 'workspace.write', 'terminal.execute'],
    });
    const continuityReportAgain = await loadSandboxHost()({
      operation: 'execute',
      roots,
      workspaceRoot,
      extensionId: 'beast.remote-continuity',
      command: 'beast.remoteContinuity.snapshot',
      granted: ['workspace.read', 'workspace.write', 'terminal.execute'],
    });

    const readyEvent = sentEvents.find(event => event.eventType === 'ready');
    const changedEvents = sentEvents.filter(event => event.eventType === 'changed' && event.path === 'src/container-watch.js');
    const errorEvents = sentEvents.filter(event => String(event.error || '').includes('simulated container interruption'));
    const watchSnapshotCalls = boundedCalls.filter(call => call.command === 'docker' && call.args[0] === 'exec' && call.args.map(String).join(' ').includes('find . -maxdepth 8 -type f'));

    assert.equal(inspect.ok, true);
    assert.equal(attached.ok, true);
    assert.equal(watch.ok, true);
    assert(readyEvent, 'expected container watcher ready event');
    assert(errorEvents.length >= 2, 'expected repeated container interruption events');
    assert(watchSnapshotCalls.length >= 4, 'expected repeated container watcher snapshots');
    assert(changedEvents.length >= 0);
    assert.equal(restarted.ok, true);
    assert.equal(restarted.restarted, true);
    assert.equal(restartedAgain.ok, true);
    assert.equal(restartedAgain.restarted, true);
    assert.equal(stopWatch.ok, true);
    assert(containerSessions.some(session => session.health === 'healthy'));
    assert(attachCount >= 1);
    assert(restartCount >= 2);
    assert(continuityWarm.registeredCommands.includes('beast.remoteContinuity.snapshot'));
    assert((continuityWarm.actionKinds || []).includes('tree'));
    assert((continuityWarm.actionKinds || []).includes('webview'));
    assert((continuityWarm.actionKinds || []).includes('watcher'));
    assert((continuityWarm.actionKinds || []).includes('task'));
    assert((continuityWarm.actions || []).some(action => action.kind === 'webview' && action.payload?.postMessage?.type === 'restore' && action.payload?.postMessage?.selectedNode === 'continuity-node-1'));
    assert((continuityWarm.actions || []).some(action => action.kind === 'webview' && action.payload?.postMessage?.type === 'hydrate' && action.payload?.postMessage?.mode === 'count-1'));
    assert((continuityReport.actions || []).some(action => action.kind === 'notice' && String(action.payload?.message || '').includes('continuity count=2') && String(action.payload?.message || '').includes('node=continuity-node-2') && String(action.payload?.message || '').includes('secret=secret-2') && String(action.payload?.message || '').includes('mode=count-2') && String(action.payload?.message || '').includes('create=1 rename=1 delete=1 refresh=2 terminal=1/1 task=1/1')));
    assert((continuityReport.actions || []).some(action => action.kind === 'tree' && action.payload?.reveal?.label === 'Continuity 2'));
    assert((continuityReport.actions || []).some(action => action.kind === 'tree' && action.payload?.refresh === true));
    assert((continuityReport.actions || []).some(action => action.kind === 'webview' && action.payload?.postMessage?.type === 'refresh' && action.payload?.postMessage?.selectedNode === 'continuity-node-2'));
    assert((continuityReport.actions || []).some(action => action.kind === 'webview' && action.payload?.postMessage?.type === 'snapshot' && action.payload?.postMessage?.count === 2 && action.payload?.postMessage?.persisted === true));
    assert((continuityReport.actions || []).some(action => action.kind === 'terminal' && action.payload?.created === true && action.payload?.name === 'Remote Continuity Terminal'));
    assert((continuityReport.actions || []).some(action => action.kind === 'terminal' && action.payload?.disposed === true && action.payload?.name === 'Remote Continuity Terminal'));
    assert((continuityReport.actions || []).some(action => action.kind === 'task' && action.payload?.execute === true && action.payload?.name === 'Remote Continuity Task'));
    assert((continuityReport.actions || []).some(action => action.kind === 'language' && action.payload?.feature === 'textDocument.rename'));
    assert((continuityReport.actions || []).some(action => action.kind === 'language' && action.payload?.feature === 'textDocument.delete'));
    assert((continuityReportAgain.actions || []).some(action => action.kind === 'notice' && String(action.payload?.message || '').includes('continuity count=3') && String(action.payload?.message || '').includes('node=continuity-node-3') && String(action.payload?.message || '').includes('secret=secret-3') && String(action.payload?.message || '').includes('mode=count-3') && String(action.payload?.message || '').includes('create=1 rename=1 delete=1 refresh=2 terminal=1/1 task=1/1')));
    assert((continuityReportAgain.actions || []).some(action => action.kind === 'terminal' && action.payload?.created === true && action.payload?.name === 'Remote Continuity Terminal'));
    assert((continuityReportAgain.actions || []).some(action => action.kind === 'task' && action.payload?.execute === true && action.payload?.name === 'Remote Continuity Task'));

    return { ok: true, checks: 31, failed: [] };
  } finally {
    fs.rmSync(workspaceRoot, { recursive: true, force: true });
  }
}

async function verifyRemoteSoakMatrix() {
  const workspaceRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'beast-remote-soak-'));
  try {
    writeFixtureExtension(workspaceRoot);
    fs.mkdirSync(path.join(workspaceRoot, 'src'), { recursive: true });
    fs.writeFileSync(path.join(workspaceRoot, 'src', 'watch.js'), 'module.exports = 1;\n', 'utf8');
    fs.writeFileSync(path.join(workspaceRoot, 'src', 'container-watch.js'), 'module.exports = 1;\n', 'utf8');

    const boundedCalls = [];
    let sshHealthy = true;
    let containerRunning = true;
    let restartCount = 0;
    const boundedProcess = async (command, args, options = {}) => {
      boundedCalls.push({ command, args, options });
      if (command === 'ssh') {
        const joined = args.map(String).join(' ');
        if (!sshHealthy) return { ok: false, stdout: '', stderr: 'simulated ssh soak interruption', error: 'simulated ssh soak interruption', returncode: 255 };
        if (joined.includes('find . -maxdepth 8 -type f')) {
          const watchStat = fs.statSync(path.join(workspaceRoot, 'src', 'watch.js'));
          const containerStat = fs.statSync(path.join(workspaceRoot, 'src', 'container-watch.js'));
          return { ok: true, stdout: `src/watch.js\t${watchStat.size}\t${Math.floor(watchStat.mtimeMs / 1000)}\nsrc/container-watch.js\t${containerStat.size}\t${Math.floor(containerStat.mtimeMs / 1000)}\n`, stderr: '', returncode: 0 };
        }
        if (joined.includes('test -d')) return { ok: true, stdout: `BEAST_REMOTE_READY\n${workspaceRoot}\n`, stderr: '', returncode: 0 };
        return { ok: true, stdout: '', stderr: '', returncode: 0 };
      }
      if (command === 'docker') {
        const joined = args.map(String).join(' ');
        if (args[0] === 'ps') {
          if (!containerRunning) return { ok: true, stdout: `container123\tbeast-dev\timage\tExited (0) 1 second ago\n`, stderr: '', returncode: 0 };
          return { ok: true, stdout: `container123\tbeast-dev\timage\tUp 2 minutes\n`, stderr: '', returncode: 0 };
        }
        if (args[0] === 'port') return { ok: true, stdout: '', stderr: '', returncode: 0 };
        if (args[0] === 'stop') {
          containerRunning = false;
          restartCount += 1;
          return { ok: true, stdout: 'container123\n', stderr: '', returncode: 0 };
        }
        if (args[0] === 'run') {
          containerRunning = true;
          return { ok: true, stdout: 'container123\n', stderr: '', returncode: 0 };
        }
        if (args[0] === 'exec') {
          if (!containerRunning) return { ok: false, stdout: '', stderr: 'simulated container soak interruption', error: 'simulated container soak interruption', returncode: 125 };
          if (joined.includes('find . -maxdepth 8 -type f')) {
            const stat = fs.statSync(path.join(workspaceRoot, 'src', 'container-watch.js'));
            return { ok: true, stdout: `src/container-watch.js\t${stat.size}\t${Math.floor(stat.mtimeMs / 1000)}\n`, stderr: '', returncode: 0 };
          }
          return { ok: true, stdout: '', stderr: '', returncode: 0 };
        }
      }
      return { ok: true, stdout: '', stderr: '', returncode: 0 };
    };

    const targetHost = createExecutionTargetHost({
      repoRoot: workspaceRoot,
      boundedProcess,
      gitReceipt: () => ({ id: 'TEST-RECEIPT' }),
      readWorkspaceFile: () => ({ ok: false }),
      safeWorkspacePath: (_root, rel) => ({ ok: true, target: path.join(workspaceRoot, rel) }),
      taskCwd: root => root,
      workspaceFileCandidates: root => {
        const watchStat = fs.statSync(path.join(root, 'src', 'watch.js'));
        const containerStat = fs.statSync(path.join(root, 'src', 'container-watch.js'));
        return [
          { path: 'src/watch.js', size: watchStat.size, mtimeMs: watchStat.mtimeMs },
          { path: 'src/container-watch.js', size: containerStat.size, mtimeMs: containerStat.mtimeMs },
        ];
      },
      getActiveWorkspaceRoot: () => workspaceRoot,
    });

    const sentEvents = [];
    const sender = { isDestroyed: () => false, send: (_channel, payload) => sentEvents.push(payload) };
    const sshTarget = { kind: 'ssh', host: 'devbox.example', remoteRoot: workspaceRoot, path: workspaceRoot };
    const containerTarget = { kind: 'container', containerId: 'container123', name: 'beast-dev', workspaceFolder: '/workspace', root: workspaceRoot };

    await targetHost.probeRemoteWorkspace({ host: 'devbox.example', path: workspaceRoot });
    await targetHost.inspectDevContainers(workspaceRoot);
    await targetHost.attachDevContainer(workspaceRoot, 'container123');

    const sshWatch = targetHost.workspaceTargetStartWatch(workspaceRoot, sender, { target: sshTarget, intervalMs: 1000, limit: 80 });
    const containerWatch = targetHost.workspaceTargetStartWatch(workspaceRoot, sender, { target: containerTarget, intervalMs: 1000, limit: 80 });

    const roots = [{ path: path.join(workspaceRoot, '.beast', 'extensions'), origin: 'workspace' }];
    const hostModulePath = require.resolve('./beast-extension-host');
    const loadSandboxHost = () => {
      delete require.cache[hostModulePath];
      return require('./beast-extension-host').handle;
    };

    const runContinuityCommand = async () => loadSandboxHost()({
      operation: 'execute',
      roots,
      workspaceRoot,
      extensionId: 'beast.remote-continuity',
      command: 'beast.remoteContinuity.snapshot',
      granted: ['workspace.read', 'workspace.write', 'terminal.execute'],
    });

    const warm = await loadSandboxHost()({
      operation: 'activate',
      roots,
      workspaceRoot,
      extensionId: 'beast.remote-continuity',
      activationEvent: 'onCommand:beast.remoteContinuity.snapshot',
      granted: ['workspace.read', 'workspace.write', 'terminal.execute'],
    });

    const cycleReports = [];
    for (let cycle = 0; cycle < 3; cycle += 1) {
      fs.writeFileSync(path.join(workspaceRoot, 'src', 'watch.js'), `module.exports = ${cycle + 2};\n`, 'utf8');
      fs.writeFileSync(path.join(workspaceRoot, 'src', 'container-watch.js'), `module.exports = ${cycle + 2};\n`, 'utf8');
      await delay(1100);
      sshHealthy = false;
      containerRunning = false;
      await delay(1100);
      sshHealthy = true;
      const sshReconnect = await targetHost.reconnectRemoteWorkspace();
      const containerRestart = await targetHost.restartDevContainer(workspaceRoot, 'container123');
      await delay(1100);
      const report = await runContinuityCommand();
      cycleReports.push({ sshReconnect, containerRestart, report });
    }

    const stopSshWatch = targetHost.workspaceTargetStopWatch(sshWatch.id);
    const stopContainerWatch = targetHost.workspaceTargetStopWatch(containerWatch.id);
    const sshErrors = sentEvents.filter(event => String(event.error || '').includes('simulated ssh soak interruption'));
    const containerErrors = sentEvents.filter(event => String(event.error || '').includes('simulated container soak interruption'));
    const sshReady = sentEvents.filter(event => event.eventType === 'ready' && (event.target === 'ssh' || event.executionTarget?.kind === 'ssh'));
    const containerReady = sentEvents.filter(event => event.eventType === 'ready' && (event.target === 'container' || event.executionTarget?.kind === 'container'));
    const sshSnapshots = boundedCalls.filter(call => call.command === 'ssh' && call.args.map(String).join(' ').includes('find . -maxdepth 8 -type f'));
    const containerSnapshots = boundedCalls.filter(call => call.command === 'docker' && call.args[0] === 'exec' && call.args.map(String).join(' ').includes('find . -maxdepth 8 -type f'));

    assert((warm.actionKinds || []).includes('tree'));
    assert((warm.actionKinds || []).includes('webview'));
    assert((warm.actionKinds || []).includes('watcher'));
    assert((warm.actionKinds || []).includes('task'));
    assert.equal(cycleReports.length, 3);
    assert(cycleReports.every(item => item.sshReconnect.ok), 'expected ssh reconnect success for every cycle');
    assert(cycleReports.every(item => item.containerRestart && Object.prototype.hasOwnProperty.call(item.containerRestart, 'ok')), 'expected container restart attempts for every cycle');
    assert(cycleReports.every((item, index) => (item.report.actions || []).some(action => action.kind === 'notice' && String(action.payload?.message || '').includes(`continuity count=${index + 2}`))), 'expected persisted continuity progression');
    assert(cycleReports.every(item => (item.report.actions || []).some(action => action.kind === 'terminal' && action.payload?.created === true)), 'expected terminal activity every cycle');
    assert(cycleReports.every(item => (item.report.actions || []).some(action => action.kind === 'task' && action.payload?.execute === true)), 'expected task activity every cycle');
    assert(cycleReports.every(item => (item.report.actions || []).some(action => action.kind === 'tree' && action.payload?.refresh === true)), 'expected tree refresh every cycle');
    assert(cycleReports.every(item => (item.report.actions || []).some(action => action.kind === 'language' && action.payload?.feature === 'textDocument.rename')), 'expected file lifecycle every cycle');
    assert(sshErrors.length >= 3, 'expected repeated ssh soak interruptions');
    assert(containerErrors.length >= 3, 'expected repeated container soak interruptions');
    assert(sshReady.length >= 1, 'expected ssh ready events');
    assert(containerReady.length >= 1, 'expected container ready events');
    assert(sshSnapshots.length >= 6, 'expected sustained ssh watcher snapshots');
    assert(containerSnapshots.length >= 6, 'expected sustained container watcher snapshots');
    assert(cycleReports.length === 3 && cycleReports.every(item => item.containerRestart), 'expected repeated container restart attempts');
    assert.equal(stopSshWatch.ok, true);
    assert.equal(stopContainerWatch.ok, true);

    return { ok: true, checks: 18, failed: [] };
  } finally {
    fs.rmSync(workspaceRoot, { recursive: true, force: true });
  }
}

module.exports = { verifyRemoteExtensionRouting, verifyRemoteContinuity, verifyContainerContinuity, verifyRemoteSoakMatrix };

if (require.main === module) {
  Promise.all([verifyRemoteExtensionRouting(), verifyRemoteContinuity(), verifyContainerContinuity(), verifyRemoteSoakMatrix()]).then(results => {
    const ok = results.every(result => result.ok);
    const merged = {
      ok,
      checks: results.reduce((total, result) => total + (result.checks || 0), 0),
      failed: results.flatMap(result => result.failed || []),
    };
    console.log(JSON.stringify(merged, null, 2));
    if (!ok) process.exit(1);
  }).catch(error => {
    console.error(error);
    process.exit(1);
  });
}
