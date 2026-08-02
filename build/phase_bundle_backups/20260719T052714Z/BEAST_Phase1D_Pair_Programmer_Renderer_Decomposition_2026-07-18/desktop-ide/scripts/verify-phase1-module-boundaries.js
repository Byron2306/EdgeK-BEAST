'use strict';

const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..');
const mainSource = fs.readFileSync(path.join(root, 'main.js'), 'utf8');
const moduleSource = name => fs.readFileSync(path.join(root, 'main', `${name}.js`), 'utf8');

const directModules = [
  'build-identity',
  'runtime-paths',
  'window-state',
  'notebook-kernel-host',
  'workspace-paths',
  'process-host',
  'workspace-file-host',
  'git-host',
  'task-test-host',
  'notebook-execution-host',
  'execution-target-host',
  'extension-host',
  'workspace-state-host',
  'desktop-diagnostics-host',
  'gateway-host',
  'window-host',
  'ipc-registry',
  'application-lifecycle',
];
for (const required of directModules) {
  assert(mainSource.includes(`./main/${required}`), `main.js does not compose ./main/${required}`);
}
const transitiveModules = ['gateway-event-stream-host', 'session-hosts'];
assert(moduleSource('gateway-host').includes("require('./gateway-event-stream-host')"), 'gateway-host does not own event-stream composition');
assert(moduleSource('execution-target-host').includes("require('./session-hosts')"), 'execution-target-host does not own session-host composition');

for (const forbidden of [
  'class NotebookKernelHost',
  'class SshForwardHost',
  'class RemoteTerminalHost',
  'class LocalTerminalHost',
  'class GatewayEventStreamHost',
  'class BeastExtensionHost',
  'class WorkspaceTaskHost',
  'function boundedProcess',
  'function workspaceGitStatus',
  'function workspaceFileCandidates',
  'function inspectDevContainers',
  'function ensureGatewayInner',
  'function localReleaseReadiness',
  "ipcMain.handle('",
]) assert(!mainSource.includes(forbidden), `${forbidden} leaked back into main.js`);

assert(mainSource.split(/\r?\n/).length < 240, 'main.js grew past the Phase 1C composition-root ceiling');

const { loadBuildIdentity } = require('../main/build-identity');
const { resolveRepoRoot } = require('../main/runtime-paths');
const { createWindowStateStore } = require('../main/window-state');
const { GatewayEventStreamHost } = require('../main/gateway-event-stream-host');
const { NotebookKernelHost } = require('../main/notebook-kernel-host');
const { SshForwardHost, RemoteTerminalHost, LocalTerminalHost } = require('../main/session-hosts');
const { createWorkspacePathTools } = require('../main/workspace-paths');
const { createBoundedProcess } = require('../main/process-host');
const { createWorkspaceFileHost } = require('../main/workspace-file-host');
const { createGitHost } = require('../main/git-host');
const { createTaskTestHost } = require('../main/task-test-host');
const { createNotebookExecutionHost } = require('../main/notebook-execution-host');
const { createExecutionTargetHost } = require('../main/execution-target-host');
const { createBeastExtensionHost } = require('../main/extension-host');
const { createWorkspaceStateHost } = require('../main/workspace-state-host');
const { createDesktopDiagnosticsHost } = require('../main/desktop-diagnostics-host');
const { createGatewayHost } = require('../main/gateway-host');
const { createWindowHost } = require('../main/window-host');
const { registerIpcHandlers } = require('../main/ipc-registry');
const { registerApplicationLifecycle } = require('../main/application-lifecycle');

const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'beast-phase1-'));
(async () => {
  try {
    const identityDirectory = path.join(temporary, 'desktop');
    fs.mkdirSync(identityDirectory, { recursive: true });
    fs.writeFileSync(path.join(identityDirectory, 'BUILD_IDENTITY.json'), JSON.stringify({ schema:'beast.build-identity.v1', desktop_runtime_build:'test' }));
    assert.equal(loadBuildIdentity(identityDirectory).desktop_runtime_build, 'test');

    const repository = path.join(temporary, 'repo');
    fs.mkdirSync(path.join(repository, 'bin'), { recursive: true });
    fs.mkdirSync(path.join(repository, 'app'), { recursive: true });
    fs.mkdirSync(path.join(repository, 'src'), { recursive: true });
    fs.writeFileSync(path.join(repository, 'bin', 'beast'), '');
    fs.writeFileSync(path.join(repository, 'app', 'main.py'), '');
    fs.writeFileSync(path.join(repository, 'src', 'alpha.txt'), 'alpha\nbeta\n');
    fs.mkdirSync(path.join(repository, '.beast-phase1b-backup-old'), { recursive:true });
    fs.writeFileSync(path.join(repository, '.beast-phase1b-backup-old', 'hidden.txt'), 'do not index');
    fs.mkdirSync(path.join(repository, '.phase1-backup'), { recursive:true });
    fs.writeFileSync(path.join(repository, '.phase1-backup', 'hidden.txt'), 'do not index');
    fs.writeFileSync(path.join(repository, 'package.json'), JSON.stringify({ scripts:{ test:'node -e "process.exit(0)"' } }));
    assert.equal(resolveRepoRoot({ baseDirectory:identityDirectory, env:{ BEAST_REPO_ROOT:repository }, cwd:temporary }), repository);

    const stateDirectory = path.join(temporary, 'state');
    const fakeApp = { getPath:() => stateDirectory };
    const fakeScreen = { getAllDisplays:() => [{ workArea:{ x:0, y:0, width:1920, height:1080 } }] };
    const store = createWindowStateStore({ app:fakeApp, screen:fakeScreen });
    const windowRef = { isDestroyed:() => false, isMaximized:() => false, getBounds:() => ({ x:10, y:20, width:1300, height:800 }) };
    store.persist(windowRef);
    assert.equal(store.read().width, 1300);
    store.dispose();

    assert.equal(new GatewayEventStreamHost({ gatewayUrl:() => 'http://127.0.0.1:8101' }).stop('missing').stopped, false);
    assert.equal(new NotebookKernelHost({ repoRoot:repository, runtimeResourcePath:() => '', pythonToolRoot:() => '' }).summary().status, 'stopped');
    assert.deepEqual(new SshForwardHost({ repoRoot:repository, remoteTarget:value => value }).list(), []);
    assert.deepEqual(new RemoteTerminalHost({ repoRoot:repository, remoteTarget:value => value, remotePath:value => value, getLastRemoteWorkspace:() => null }).list(), []);
    assert.deepEqual(new LocalTerminalHost({ repoRoot:repository, taskCwd:(_root,cwd) => cwd, getActiveWorkspaceRoot:() => repository }).list(), []);

    const { safeWorkspacePath, taskCwd } = createWorkspacePathTools({ repoRoot:repository });
    assert.equal(safeWorkspacePath(repository, 'src/alpha.txt').ok, true);
    assert.equal(safeWorkspacePath(repository, '../escape').ok, false);
    assert.equal(taskCwd(repository, 'src'), path.join(repository, 'src'));

    const boundedProcess = createBoundedProcess({ repoRoot:repository });
    const processResult = await boundedProcess(process.execPath, ['-e', "process.stdout.write('phase1b')"], { timeoutMs:3000 });
    assert.equal(processResult.ok, true);
    assert.equal(processResult.stdout, 'phase1b');

    const workspaceFileHost = createWorkspaceFileHost({ repoRoot:repository, safeWorkspacePath });
    const candidates = workspaceFileHost.workspaceFileCandidates(repository, 20);
    assert(candidates.some(item => item.path === path.join('src', 'alpha.txt')));
    assert(!candidates.some(item => item.path.includes('.beast-phase1b-backup-old')));
    assert(!candidates.some(item => item.path.includes('.phase1-backup')));
    assert.equal(workspaceFileHost.readWorkspaceFile(repository, 'src/alpha.txt').content, 'alpha\nbeta\n');
    assert.equal(workspaceFileHost.textWorkspaceSearch(repository, { query:'beta' }).results.length, 1);

    const gitHost = createGitHost({ repoRoot:repository, boundedProcess, safeWorkspacePath });
    const parsedGit = gitHost.parseGitPorcelain('?? src/new.js\n');
    assert.equal(parsedGit.changes.length, 1);
    assert.equal(parsedGit.changes[0].untracked, true);

    let executionTargetHost = null;
    const taskTestHost = createTaskTestHost({
      repoRoot:repository,
      workspaceFileCandidates:workspaceFileHost.workspaceFileCandidates,
      safeWorkspacePath,
      taskCwd,
      getTargetHost:() => executionTargetHost,
    });
    executionTargetHost = createExecutionTargetHost({
      repoRoot:repository,
      boundedProcess,
      gitReceipt:gitHost.gitReceipt,
      readWorkspaceFile:workspaceFileHost.readWorkspaceFile,
      safeWorkspacePath,
      taskCwd,
      workspaceFileCandidates:workspaceFileHost.workspaceFileCandidates,
      getActiveWorkspaceRoot:() => repository,
    });
    assert.equal(executionTargetHost.executionTargetSummary().kind, 'local');
    assert.equal(executionTargetHost.setActiveExecutionTarget({ kind:'local' }).ok, true);
    assert.equal(taskTestHost.workspaceTasks(repository).tasks.some(item => item.id === 'npm:test'), true);
    assert.deepEqual(taskTestHost.workspaceTaskHost.list(), []);

    const notebook = createNotebookExecutionHost({ repoRoot:repository, boundedProcess, getActiveWorkspaceRoot:() => repository });
    assert.equal(typeof notebook.executeNotebookCell, 'function');

    const fakeDialog = {
      showOpenDialog:async () => ({ canceled:true, filePaths:[] }),
      showMessageBox:async () => ({ response:1 }),
    };
    const fakeBrowserWindow = { fromWebContents:() => null };
    const extensionHost = createBeastExtensionHost({
      repoRoot:repository,
      runtimeResourcePath:(...parts) => path.join(repository, ...parts),
      boundedProcess,
      getMainWindow:() => null,
      executionTargetHost,
      BrowserWindow:fakeBrowserWindow,
      dialog:fakeDialog,
    });
    assert.equal(extensionHost.summary().status, 'stopped');

    const fakeAppForWorkspace = { getPath:() => stateDirectory };
    let gatewayHost = null;
    const workspaceStateHost = createWorkspaceStateHost({
      app:fakeAppForWorkspace,
      repoRoot:repository,
      workspaceFileCandidates:workspaceFileHost.workspaceFileCandidates,
      appendLog:() => {},
    });
    assert.equal(workspaceStateHost.workspaceFolders().length, 1);
    workspaceStateHost.setWorkspaceRoots([repository], repository);
    assert.equal(workspaceStateHost.registeredWorkspaceRoot({}), repository);

    let windowHost = null;
    gatewayHost = createGatewayHost({
      repoRoot:repository,
      initialGatewayUrl:'http://127.0.0.1:18101',
      resolveBeastPython:() => process.execPath,
      getActiveWorkspaceRoot:workspaceStateHost.getActiveWorkspaceRoot,
      getAppWindows:() => windowHost?.getAppWindows() || [],
    });
    assert.equal(gatewayHost.getSnapshot().url, 'http://127.0.0.1:18101');
    assert.equal(gatewayHost.gatewayEventStreamHost.stop('missing').stopped, false);

    const fakeMenu = { buildFromTemplate:value => value, setApplicationMenu:() => {} };
    const fakeWindowClass = { getFocusedWindow:() => null };
    windowHost = createWindowHost({
      BrowserWindow:fakeWindowClass,
      Menu:fakeMenu,
      dialog:fakeDialog,
      shell:{ openExternal:async () => {} },
      desktopRoot:root,
      buildIdentity:{ desktop_runtime_build:'test' },
      desktopVersion:'test',
      workspaceStateHost,
      gatewayHost,
      beastRepoRoot:repository,
    });
    assert.equal(windowHost.getWindowCount(), 0);
    windowHost.createMenu();

    const diagnosticsHost = createDesktopDiagnosticsHost({
      repoRoot:repository,
      desktopRoot:root,
      buildIdentity:{ desktop_runtime_build:'test' },
      desktopVersion:'test',
      safeWorkspacePath,
      getActiveWorkspaceRoot:workspaceStateHost.getActiveWorkspaceRoot,
      getGatewaySnapshot:gatewayHost.getSnapshot,
    });
    assert.equal(typeof diagnosticsHost.localReleaseReadiness, 'function');
    assert.equal(typeof diagnosticsHost.resolveBeastPython, 'function');

    const registeredChannels = new Map();
    const fakeIpcMain = { handle:(name, handler) => registeredChannels.set(name, handler) };
    const functionProxy = new Proxy({}, { get:() => (() => ({ ok:true })) });
    registerIpcHandlers({
      ipcMain:fakeIpcMain,
      BrowserWindow:{ fromWebContents:() => null },
      dialog:fakeDialog,
      shell:{ openExternal:async () => {} },
      repoRoot:repository,
      desktopRoot:root,
      desktopVersion:'test',
      workspaceStateHost,
      windowHost,
      gatewayHost,
      diagnosticsHost,
      workspaceFileHost,
      gitHost,
      taskTestHost,
      executionTargetHost,
      notebookExecutionHost:notebook,
      notebookKernelHost:{ start:async () => ({}), request:async () => ({}), stop:() => ({}) },
      ideCompatibilityHost:functionProxy,
      beastExtensionHost:extensionHost,
    });
    assert(registeredChannels.size >= 60, `expected at least 60 IPC channels, got ${registeredChannels.size}`);
    assert(registeredChannels.has('beast:status'));
    assert(registeredChannels.has('beast:workspace-git-status'));
    assert(registeredChannels.has('beast:extension-host-execute'));

    const lifecycleEvents = new Map();
    const fakeLifecycleApp = {
      whenReady:() => ({ then:callback => { fakeLifecycleApp.readyCallback=callback; return { catch:() => {} }; } }),
      on:(name, callback) => lifecycleEvents.set(name, callback),
      quit:() => {},
    };
    registerApplicationLifecycle({
      app:fakeLifecycleApp,
      BrowserWindow:{ getAllWindows:() => [1] },
      screen:fakeScreen,
      createWindowStateStore:() => store,
      windowHost,
      workspaceStateHost,
      gatewayHost,
      ideCompatibilityHost:{ stopAll:() => {} },
      notebookKernelHost:{ stop:() => {} },
      executionTargetHost,
      taskTestHost,
      beastExtensionHost:extensionHost,
    });
    assert(lifecycleEvents.has('window-all-closed'));
    assert(lifecycleEvents.has('activate'));

    gatewayHost.shutdown();
    executionTargetHost.shutdown();

    const intentSource = fs.readFileSync(path.join(root, 'renderer/js/ai/beast-ai-intent.js'), 'utf8');
    const context = { window:{} };
    vm.createContext(context);
    vm.runInContext(intentSource, context);
    assert.equal(context.window.BeastAIIntent.parseActionIntent('{"kind":"beast.action_intent.v1","actions":[]}').kind, 'beast.action_intent.v1');
    assert.equal(context.window.BeastAIIntent.looksLikeActionIntent('{"actions":[]}'), true);

    console.log(JSON.stringify({
      status:'PASS',
      direct_modules:directModules.length,
      transitive_modules:transitiveModules.length,
      renderer_modules:2,
      main_lines:mainSource.split(/\r?\n/).length,
    }, null, 2));
  } finally {
    fs.rmSync(temporary, { recursive:true, force:true });
  }
})().catch(error => {
  console.error(error);
  process.exit(1);
});
