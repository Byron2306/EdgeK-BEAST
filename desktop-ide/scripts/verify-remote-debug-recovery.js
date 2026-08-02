const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..');
const runtimeSource = fs.readFileSync(path.join(root, 'renderer/js/beast-ide-runtime.js'), 'utf8');

function createHarness(initialTarget) {
  const state = {
    workspace: { root: '/workspace/project', executionTarget: { ...initialTarget } },
    compatibility: {
      debug: [{ id: 'debugpy', available: true }],
      runtime: { debug: { status: 'idle', output: [], stack: [], threads: [], breakpoints: [] }, remote: {}, notebook: {} },
      sessions: [],
    },
    editor: { activePath: 'src/app.py' },
  };
  const localStorageStore = new Map();
  let protocolListener = null;
  let sessionCounter = 0;
  let setExecutionTargetCalls = 0;
  const starts = [];

  function emitProtocol(message) {
    if (typeof protocolListener === 'function') protocolListener(message);
  }

  const desktop = {
    startIdeProtocol: async options => {
      sessionCounter += 1;
      const id = `dap-${sessionCounter}`;
      starts.push({ id, options });
      setTimeout(() => emitProtocol({ sessionId: id, kind: 'dap', type: 'ready', capabilities: { supportsConfigurationDoneRequest: true, supportsLoadedSourcesRequest: true, supportsRestartRequest: true } }), 0);
      return { id, kind: 'dap', adapter: options.adapter, label: 'debugpy', status: 'running', target: options.target || initialTarget, transport: 'ssh-stdio' };
    },
    requestIdeProtocol: async payload => {
      if (payload.method === 'threads') return { threads: [{ id: 1, name: 'MainThread' }] };
      if (payload.method === 'stackTrace') return { stackFrames: [{ id: 11, name: 'main', line: 3, source: { path: '/workspace/project/src/app.py', name: 'app.py', sourceReference: 9 } }] };
      if (payload.method === 'scopes') return { scopes: [{ name: 'Locals', variablesReference: 21 }] };
      if (payload.method === 'variables') return { variables: [{ name: 'value', value: '42', type: 'int' }] };
      if (payload.method === 'evaluate') return { result: '42', type: 'int', variablesReference: 0 };
      if (payload.method === 'loadedSources') return { loadedSources: [{ name: 'app.py', path: '/workspace/project/src/app.py', sourceReference: 9 }] };
      if (payload.method === 'disconnect') return { ok: true };
      return {};
    },
    notifyIdeProtocol: async payload => {
      if (payload.method === 'launch' || payload.method === 'attach') {
        setTimeout(() => emitProtocol({ sessionId: payload.sessionId, kind: 'dap', message: { type: 'event', event: 'initialized' } }), 0);
      }
      return { ok: true };
    },
    stopIdeProtocol: async () => ({ ok: true }),
    reconnectRemote: async () => ({ ok: true, host: initialTarget.host, path: initialTarget.remoteRoot || initialTarget.path || '~', remote_root: initialTarget.remoteRoot || initialTarget.path || '~', target: { ...initialTarget } }),
    listRemoteFiles: async () => ({ ok: true, files: [] }),
    listRemoteTerminals: async () => ({ terminals: [] }),
    listRemoteForwards: async () => ({ forwards: [] }),
    attachDevContainer: async () => ({ ok: true, containers: [], attached: { id: initialTarget.containerId || 'container' }, target: { ...initialTarget } }),
    restartDevContainer: async () => ({ ok: true, containers: [], attached: { id: initialTarget.containerId || 'container' }, target: { ...initialTarget } }),
    startDevContainer: async () => ({ ok: true, containers: [], attached: { id: initialTarget.containerId || 'container' }, target: { ...initialTarget } }),
    inspectDevContainers: async () => ({ ok: true, containers: [], config: { workspaceFolder: initialTarget.workspaceFolder || '/workspace' } }),
    onIdeProtocolMessage: callback => { protocolListener = callback; },
    onNotebookKernelMessage: () => {},
    onRemoteForwardMessage: () => {},
    onRemoteTerminalMessage: () => {},
    onTerminalSessionMessage: () => {},
    onExtensionHostMessage: () => {},
  };

  const BeastStore = {
    get: () => state,
    patch: (key, value) => { state[key] = { ...(state[key] || {}), ...value }; },
    addLedger: () => {},
  };

  const context = {
    console,
    setTimeout,
    clearTimeout,
    queueMicrotask,
    structuredClone,
    localStorage: {
      getItem: key => localStorageStore.get(key) || null,
      setItem: (key, value) => localStorageStore.set(key, String(value)),
    },
    BeastStore,
    BeastEditorCortex: { getActive: () => ({ path: 'src/app.py' }) },
    BeastRouter: { navigate: async () => {} },
    BeastDesktopBridge: {
      setExecutionTarget: target => {
        setExecutionTargetCalls += 1;
        state.workspace.executionTarget = { ...target };
        return state.workspace.executionTarget;
      },
      listExecutionTargets: async () => ({ ok: true, active: state.workspace.executionTarget, targets: [state.workspace.executionTarget] }),
      remoteRef: (host, filePath) => `beast-remote://${host}/${filePath}`,
    },
    window: { beastDesktop: desktop },
  };
  context.window.BeastStore = BeastStore;
  context.window.BeastEditorCortex = context.BeastEditorCortex;
  context.window.BeastRouter = context.BeastRouter;
  context.window.BeastDesktopBridge = context.BeastDesktopBridge;
  vm.createContext(context);
  vm.runInContext(runtimeSource, context);
  return {
    context,
    state,
    starts,
    get setExecutionTargetCalls() { return setExecutionTargetCalls; },
    emitExit() {
      const latest = starts.at(-1);
      emitProtocol({ sessionId: latest.id, kind: 'dap', type: 'exit' });
    },
  };
}

async function verifySshRecovery() {
  const target = { kind: 'ssh', host: 'dev@example', remoteRoot: '/srv/app', path: '/srv/app' };
  const harness = createHarness(target);
  await harness.context.window.BeastIDERuntime.startDebug({ adapter: 'debugpy', breakpoints: '3' });
  harness.emitExit();
  await harness.context.window.BeastIDERuntime.reconnectRemote();
  const debug = harness.state.compatibility.runtime.debug || {};
  return {
    ok: harness.starts.length >= 2 && debug.disconnected === false && String(debug.status || '') !== 'terminated',
    detail: { starts: harness.starts.length, status: debug.status, disconnected: debug.disconnected, canRestart: debug.canRestart },
  };
}

async function verifyContainerRecovery(method) {
  const target = { kind: 'container', containerId: 'beast-dev', name: 'beast-dev', workspaceFolder: '/workspace' };
  const harness = createHarness(target);
  await harness.context.window.BeastIDERuntime.startDebug({ adapter: 'debugpy', breakpoints: '3' });
  harness.emitExit();
  if (method === 'attach') await harness.context.window.BeastIDERuntime.attachDevContainer('beast-dev');
  else await harness.context.window.BeastIDERuntime.restartDevContainer('beast-dev');
  const debug = harness.state.compatibility.runtime.debug || {};
  return {
    ok: harness.starts.length >= 2 && debug.disconnected === false && String(debug.status || '') !== 'terminated',
    detail: { method, starts: harness.starts.length, status: debug.status, disconnected: debug.disconnected },
  };
}

async function runVerification() {
  const rows = [];
  const ssh = await verifySshRecovery();
  rows.push({ name: 'SSH debug auto-resume after reconnect', passed: ssh.ok, detail: JSON.stringify(ssh.detail) });
  const containerAttach = await verifyContainerRecovery('attach');
  rows.push({ name: 'Container debug auto-resume after attach', passed: containerAttach.ok, detail: JSON.stringify(containerAttach.detail) });
  const containerRestart = await verifyContainerRecovery('restart');
  rows.push({ name: 'Container debug auto-resume after restart', passed: containerRestart.ok, detail: JSON.stringify(containerRestart.detail) });
  const failed = rows.filter(row => !row.passed);
  return { ok: failed.length === 0, checks: rows.length, failed };
}

module.exports = { runVerification };

if (require.main === module) {
  runVerification().then(result => {
    console.log(JSON.stringify(result, null, 2));
    if (!result.ok) process.exit(1);
  }).catch(error => {
    console.error(error);
    process.exit(1);
  });
}
