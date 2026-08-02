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
  'bootstrap',
  'window-state',
  'gateway-host',
  'workspace-host',
  'ipc-registry',
  'diagnostics-host',
  'menu-host',
  'window-host',
  'application-lifecycle',
  'gateway-event-stream-host',
  'notebook-kernel-host',
  'workspace-paths',
  'process-host',
  'workspace-file-host',
  'git-host',
  'task-test-host',
  'notebook-execution-host',
  'execution-target-host',
  'extension-host',
];

const rendererModules = [
  'beast-ai-transport',
  'beast-ai-intent',
  'beast-ai-narration',
  'beast-ai-profile',
];

for (const required of directModules) {
  assert(mainSource.includes(`./main/${required}`), `main.js does not compose ./main/${required}`);
}
assert(moduleSource('execution-target-host').includes("require('./session-hosts')"), 'execution-target-host does not own session-host composition');
assert(moduleSource('bootstrap').includes("require('./security-policy')"), 'bootstrap does not own renderer security-policy composition');
assert(mainSource.includes('ipcRegistry.handle('), 'main.js does not register channels through ipc-registry');
assert(!mainSource.includes('ipcMain.handle('), 'raw ipcMain.handle leaked back into main.js');

for (const forbidden of [
  'class NotebookKernelHost',
  'class SshForwardHost',
  'class RemoteTerminalHost',
  'class LocalTerminalHost',
  'class GatewayEventStreamHost',
  'class BeastExtensionHost',
  'class WorkspaceTaskHost',
  'function serviceRegistryGateway',
  'function serviceRegistryPort',
  'function normalizeWorkspaceRoots',
  'function runDesktopScript',
  'function installApplicationMenu',
  'function boundedProcess',
  'function workspaceGitStatus',
  'function workspaceFileCandidates',
  'function inspectDevContainers',
]) assert(!mainSource.includes(forbidden), `${forbidden} leaked back into main.js`);

for (const required of rendererModules) {
  assert(fs.existsSync(path.join(root, 'renderer/js/ai', `${required}.js`)), `renderer AI module ${required} missing`);
  assert(
    fs.readFileSync(path.join(root, 'renderer', 'index.html'), 'utf8').includes(`js/ai/${required}.js`),
    `renderer index.html does not load js/ai/${required}.js`
  );
}
assert(mainSource.split(/\r?\n/).length < 1500, 'main.js grew past the Phase 1 decomposition ceiling');

const { loadBuildIdentity } = require('../main/build-identity');
const { resolveRepoRoot } = require('../main/runtime-paths');
const { createBrowserWindowOptions } = require('../main/bootstrap');
const { assertRendererWebPreferences, rendererWebPreferences } = require('../main/security-policy');
const { createWindowStateStore } = require('../main/window-state');
const { serviceRegistryGateway, serviceRegistryPort } = require('../main/gateway-host');
const { normalizeWorkspaceRoots, workspaceFoldersStatePath } = require('../main/workspace-host');
const { createIpcRegistry } = require('../main/ipc-registry');
const { createDesktopScriptRunner } = require('../main/diagnostics-host');
const { installApplicationMenu } = require('../main/menu-host');
const { createDesktopWindowHost } = require('../main/window-host');
const { registerApplicationLifecycle } = require('../main/application-lifecycle');
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

const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'beast-phase1-'));

(async () => {
  try {
    const identityDirectory = path.join(temporary, 'desktop');
    fs.mkdirSync(identityDirectory, { recursive: true });
    fs.writeFileSync(path.join(identityDirectory, 'BUILD_IDENTITY.json'), JSON.stringify({ schema:'beast.build-identity.v1', desktop_runtime_build:'test' }));
    assert.equal(loadBuildIdentity(identityDirectory).desktop_runtime_build, 'test');

    const repository = path.join(temporary, 'repo');
    const fakeDesktop = path.join(temporary, 'desktop-root');
    fs.mkdirSync(path.join(fakeDesktop, 'scripts'), { recursive:true });
    fs.writeFileSync(path.join(fakeDesktop, 'scripts', 'ok.js'), "process.stdout.write('diagnostics-ok')");
    const runDesktopScript = createDesktopScriptRunner({ desktopRoot:fakeDesktop });
    assert.equal(runDesktopScript('ok.js').ok, true);
    assert.equal(runDesktopScript('missing.js').ran, false);

    fs.mkdirSync(path.join(repository, 'bin'), { recursive: true });
    fs.mkdirSync(path.join(repository, 'app'), { recursive: true });
    fs.mkdirSync(path.join(repository, 'src'), { recursive: true });
    fs.mkdirSync(path.join(repository, '.byron'), { recursive:true });
    fs.writeFileSync(path.join(repository, 'bin', 'beast'), '');
    fs.writeFileSync(path.join(repository, 'app', 'main.py'), '');
    fs.writeFileSync(path.join(repository, 'src', 'alpha.txt'), 'alpha\nbeta\n');
    fs.writeFileSync(path.join(repository, '.byron', 'services.yaml'), 'services:\n  beast:\n    upstream: "127.0.0.1:8123"\n  command:\n    port: 7070\n');
    fs.mkdirSync(path.join(repository, '.beast-phase1b-backup-old'), { recursive:true });
    fs.writeFileSync(path.join(repository, '.beast-phase1b-backup-old', 'hidden.txt'), 'do not index');
    fs.mkdirSync(path.join(repository, '.phase1-backup'), { recursive:true });
    fs.writeFileSync(path.join(repository, '.phase1-backup', 'hidden.txt'), 'do not index');
    fs.writeFileSync(path.join(repository, 'package.json'), JSON.stringify({ scripts:{ test:'node -e "process.exit(0)"' } }));
    assert.equal(resolveRepoRoot({ baseDirectory:identityDirectory, env:{ BEAST_REPO_ROOT:repository }, cwd:temporary }), repository);

    const webPreferences = rendererWebPreferences(path.join(identityDirectory, 'preload.js'));
    assert.equal(assertRendererWebPreferences(webPreferences), true);
    const windowOptions = createBrowserWindowOptions({ bounds:{ width:900, height:700 }, preloadPath:webPreferences.preload });
    assert.equal(windowOptions.webPreferences.contextIsolation, true);
    assert.equal(windowOptions.webPreferences.nodeIntegration, false);
    assert.equal(windowOptions.width, 900);

    const handledChannels = [];
    const registry = createIpcRegistry({ handle:(channel, handler) => handledChannels.push({ channel, handler }) });
    registry.handle('beast:test-channel', async () => ({ ok:true }));
    assert.deepEqual(registry.registeredChannels(), ['beast:test-channel']);
    assert.throws(() => registry.handle('beast:test-channel', async () => ({})), /Duplicate IPC channel/);

    let applicationMenu = null;
    installApplicationMenu({
      BrowserWindow:{ getFocusedWindow:() => null },
      Menu:{ buildFromTemplate:template => template, setApplicationMenu:menu => { applicationMenu = menu; } },
      dialog:{ showOpenDialog:async () => ({ canceled:true, filePaths:[] }) },
      shell:{ openExternal:() => {} },
      ensureGateway:() => {},
      getGatewayUrl:() => 'http://127.0.0.1:8101',
      getMainWindow:() => null,
      chooseWorkspace:() => ({ root:repository, folders:[] }),
    });
    assert(applicationMenu.some(item => item.label === 'BEAST'));

    assert.equal(typeof createDesktopWindowHost({}), 'object');
    const lifecycleEvents = [];
    registerApplicationLifecycle({
      app:{ whenReady:() => ({ then:handler => lifecycleEvents.push(['ready', handler]) }), on:(event, handler) => lifecycleEvents.push([event, handler]) },
      BrowserWindow:{ getAllWindows:() => [] },
      onReady:() => {},
      onWindowAllClosed:() => {},
      createWindow:() => {},
    });
    assert.deepEqual(lifecycleEvents.map(item => item[0]), ['ready', 'window-all-closed', 'activate']);

    assert.equal(serviceRegistryGateway(repository), 'http://127.0.0.1:8123');
    assert.equal(serviceRegistryPort(repository, 'command', 7000), 7070);
    assert.equal(serviceRegistryPort(repository, 'missing', 7001), 7001);

    const stateDirectory = path.join(temporary, 'state');
    const fakeApp = { getPath:() => stateDirectory };
    assert.equal(workspaceFoldersStatePath(fakeApp), path.join(stateDirectory, 'beast-desktop-workspace-folders.json'));
    const folders = normalizeWorkspaceRoots([path.join(repository, 'src')], repository, repository);
    assert.equal(folders.length, 2);
    assert.equal(folders[0].primary, true);

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
    if (/EPERM|EACCES/i.test(String(processResult.error || ''))) {
      assert.equal(processResult.ok, false);
    } else {
      assert.equal(processResult.ok, true);
      if (processResult.stdout !== 'phase1b') {
        assert.equal(processResult.returncode, 0);
        assert.equal(processResult.timed_out, false);
        assert.equal(processResult.stdout, '');
      }
    }

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

    executionTargetHost.shutdown();

    const context = { window:{}, URL };
    vm.createContext(context);
    for (const moduleName of rendererModules) {
      vm.runInContext(fs.readFileSync(path.join(root, 'renderer/js/ai', `${moduleName}.js`), 'utf8'), context);
    }
    assert.equal(context.window.BeastAIIntent.parseActionIntent('{"kind":"beast.action_intent.v1","actions":[]}').kind, 'beast.action_intent.v1');
    assert.equal(context.window.BeastAIIntent.looksLikeActionIntent('{"actions":[]}'), true);
    assert.equal(context.window.BeastAINarration.runDoneSentence('advisory_response'), 'Run complete: no SourcePlan was created and no files changed.');
    assert.equal(context.window.BeastAINarration.narrationFromTurn({ type:'tool_call', tool:'Workspace Search' }), 'I’m searching the workspace for the symbols and references that matter.');
    assert.equal(context.window.BeastAIProfile.isAgentAnalysisPrompt('look over this file deeply'), true);
    assert.equal(context.window.BeastAIProfile.agentTurnProfile('run tests after fixing it', 'agent', false, ['a.js']).wantsTests, true);

    console.log(JSON.stringify({
      status:'PASS',
      direct_modules:directModules.length,
      transitive_modules:1,
      renderer_modules:rendererModules.length,
      main_lines:mainSource.split(/\r?\n/).length,
    }, null, 2));
  } finally {
    fs.rmSync(temporary, { recursive:true, force:true });
  }
})().catch(error => {
  console.error(error);
  process.exit(1);
});
