global.activeWorkspaceRoot = "/home/byron/EdgeK-BEAST";
const { app, BrowserWindow, Menu, dialog, ipcMain, shell, screen } = require('electron');
const { spawn, spawnSync } = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const http = require('http');
const net = require('net');
const os = require('os');
const path = require('path');
const { IdeCompatibilityHost } = require('./ide-compatibility-host');
const { loadBuildIdentity } = require('./main/build-identity');
const { resolveRepoRoot, runtimeResourcePath: resolveRuntimeResourcePath, pythonToolRoot: resolvePythonToolRoot } = require('./main/runtime-paths');
const { createBrowserWindowOptions } = require('./main/bootstrap');
const { DEFAULT_WINDOW_BOUNDS, createWindowStateStore } = require('./main/window-state');
const { serviceRegistryGateway, serviceRegistryPort } = require('./main/gateway-host');
const { createWorkspaceHost } = require('./main/workspace-host');
const { createIpcRegistry } = require('./main/ipc-registry');
const { createDesktopScriptRunner } = require('./main/diagnostics-host');
const { installApplicationMenu } = require('./main/menu-host');
const { createDesktopWindowHost } = require('./main/window-host');
const { registerApplicationLifecycle } = require('./main/application-lifecycle');
const { GatewayEventStreamHost } = require('./main/gateway-event-stream-host');
const { NotebookKernelHost } = require('./main/notebook-kernel-host');
const { createWorkspacePathTools } = require('./main/workspace-paths');
const { createBoundedProcess } = require('./main/process-host');
const { createWorkspaceFileHost } = require('./main/workspace-file-host');
const { createGitHost } = require('./main/git-host');
const { createTaskTestHost } = require('./main/task-test-host');
const { createNotebookExecutionHost } = require('./main/notebook-execution-host');
const { createExecutionTargetHost } = require('./main/execution-target-host');
const { createBeastExtensionHost } = require('./main/extension-host');

const BUILD_IDENTITY = loadBuildIdentity(__dirname);
const DESKTOP_IDE_VERSION = BUILD_IDENTITY.desktop_runtime_build;

const repoRoot = resolveRepoRoot({ baseDirectory: __dirname });
const ideCompatibilityHost = new IdeCompatibilityHost(repoRoot);
const runtimeResourcePath = (...parts) => resolveRuntimeResourcePath(__dirname, process.resourcesPath, ...parts);
const pythonToolRoot = () => resolvePythonToolRoot(__dirname, process.resourcesPath);

let windowStateStore = null;
function readWindowState() { return windowStateStore.read(); }
function persistWindowState(windowRef) { return windowStateStore.persist(windowRef); }
function scheduleWindowStatePersist(windowRef) { return windowStateStore.schedule(windowRef); }

const notebookKernelHost = new NotebookKernelHost({ repoRoot, runtimeResourcePath, pythonToolRoot });
const runDesktopScript = createDesktopScriptRunner({ desktopRoot: __dirname });

const configuredGatewayUrl = serviceRegistryGateway(repoRoot);
const gatewayOverrideAllowed = process.env.BEAST_ALLOW_GATEWAY_OVERRIDE === '1';
let gatewayUrl = gatewayOverrideAllowed && process.env.BEAST_DESKTOP_GATEWAY ? process.env.BEAST_DESKTOP_GATEWAY : configuredGatewayUrl;
let gatewayProcess = null;
let gatewayStartupPromise = null;
let mainWindow = null;
const appWindows = new Set();
let lastGatewayCommand = '';
let gatewayLog = [];
let gatewayStartedAt = 0;
let localIdeMode = false;
let localIdeReason = '';
let resolvedBeastPython = null;
const ipcRegistry = createIpcRegistry(ipcMain);

const {
  restoreWorkspaceFolders,
  setWorkspaceRoots,
  workspaceFolders,
  getActiveWorkspaceRoot,
  parseWorkspaceReference,
  multiRootFiles,
  registeredWorkspaceRoot,
} = createWorkspaceHost({
  app,
  dialog,
  repoRoot,
  appendLog,
  getMainWindow: () => mainWindow,
  getAppWindows: () => appWindows,
  ipcRegistry,
  BrowserWindow,
});

const { safeWorkspacePath, taskCwd } = createWorkspacePathTools({ repoRoot });
const boundedProcess = createBoundedProcess({ repoRoot });
const workspaceFileHost = createWorkspaceFileHost({ repoRoot, safeWorkspacePath });
const {
  workspaceFileCandidates,
  readWorkspaceFile,
  textWorkspaceSearch,
  workspaceReplacePreview,
  mutateWorkspaceFile,
} = workspaceFileHost;
const gitHost = createGitHost({ repoRoot, boundedProcess, safeWorkspacePath });
const {
  gitReceipt,
  workspaceGitStatus,
  workspaceGitDiff,
  workspaceGitHunks,
  workspaceGitHunkAction,
  workspaceGitConflict,
  workspaceGitResolve,
  workspaceGitAction,
  workspaceGitCommit,
  workspaceGitBranch,
  workspaceGitHistory,
  workspaceGitRemotes,
  workspaceGitOperation,
} = gitHost;
let executionTargetHost = null;
const taskTestHost = createTaskTestHost({
  repoRoot,
  workspaceFileCandidates,
  safeWorkspacePath,
  taskCwd,
  getTargetHost: () => executionTargetHost,
});
const {
  workspaceTasks,
  workspaceSettings,
  writeWorkspaceSettings,
  workspaceTestsForTarget,
  runWorkspaceTest,
  runWorkspaceTask,
  workspaceTaskHost,
} = taskTestHost;
executionTargetHost = createExecutionTargetHost({
  repoRoot,
  boundedProcess,
  gitReceipt,
  readWorkspaceFile,
  safeWorkspacePath,
  taskCwd,
  workspaceFileCandidates,
  getActiveWorkspaceRoot,
});
const {
  executionTargetSummary,
  setActiveExecutionTarget,
  listExecutionTargets,
  workspaceTargetListFiles,
  workspaceTargetReadFile,
  workspaceTargetWriteFile,
  probeRemoteWorkspace,
  listRemoteWorkspaceFiles,
  searchRemoteWorkspace,
  reconnectRemoteWorkspace,
  remoteWorkspaceHealth,
  readRemoteWorkspaceFile,
  writeRemoteWorkspaceFile,
  runRemoteTerminal,
  inspectDevContainers,
  startDevContainer,
  stopDevContainer,
  restartDevContainer,
  attachDevContainer,
  rebuildDevContainer,
  devContainerLogs,
  runDevContainerTerminal,
  sshForwardHost,
  remoteTerminalHost,
  localTerminalHost,
} = executionTargetHost;
const { executeNotebookCell } = createNotebookExecutionHost({
  repoRoot,
  boundedProcess,
  getActiveWorkspaceRoot,
});
const beastExtensionHost = createBeastExtensionHost({
  repoRoot,
  runtimeResourcePath,
  boundedProcess,
  getMainWindow: () => mainWindow,
  executionTargetHost,
  BrowserWindow,
  dialog,
});

function appendLog(line) {
  const record = `[${new Date().toISOString()}] ${String(line || '').trim()}`;
  gatewayLog.push(record);
  gatewayLog = gatewayLog.slice(-500);
  try {
    const logDir = path.join(repoRoot, '.beast', 'logs');
    fs.mkdirSync(logDir, { recursive: true });
    fs.appendFileSync(path.join(logDir, 'desktop-gateway.log'), `${record}\n`, { encoding: 'utf8', mode: 0o600 });
  } catch (_) {}
  for (const windowRef of appWindows) {
    if (!windowRef.isDestroyed()) windowRef.webContents.send('beast:gateway-log', gatewayLog);
  }
}

function enterLocalIdeMode(reason) {
  localIdeMode = true;
  localIdeReason = reason || 'gateway unavailable; using local desktop IDE mode';
  appendLog(`Local IDE Mode: ${localIdeReason}`);
  return {
    ok: false,
    url: gatewayUrl,
    local_mode: true,
    error: localIdeReason,
    capabilities: {
      ok: true,
      mode: 'desktop_local_fallback',
      checks: {
        local_files: { ok: true, mode: 'desktop_ipc' },
        local_editor: { ok: true, mode: 'monaco' },
        sourceplan_gateway: { ok: false, mode: 'deferred_until_gateway_ready' },
      },
    },
  };
}


function localReleaseReadiness(rootPath = repoRoot) {
  const root = path.resolve(rootPath || repoRoot);
  const files = {
    desktop_package: path.join(__dirname, 'package.json'),
    desktop_main: path.join(__dirname, 'main.js'),
    desktop_preload: path.join(__dirname, 'preload.js'),
    desktop_renderer: path.join(__dirname, 'renderer', 'app.js'),
    desktop_html: path.join(__dirname, 'renderer', 'index.html'),
    desktop_styles: path.join(__dirname, 'renderer', 'styles.css'),
    desktop_smoke: path.join(__dirname, 'scripts', 'smoke-desktop-ide.js'),
    desktop_launch_smoke: path.join(__dirname, 'scripts', 'launch-smoke-desktop-ide.js'),
    ide_routes: path.join(root, 'app', 'routes', 'ide.py'),
    desktop_tests: path.join(root, 'tests', 'test_desktop_ide_manifest.py'),
  };
  const read = filePath => {
    try {
      return fs.readFileSync(filePath, 'utf8');
    } catch (_error) {
      return '';
    }
  };
  const packageText = read(files.desktop_package);
  const rendererText = read(files.desktop_renderer);
  const htmlText = read(files.desktop_html);
  const mainText = read(files.desktop_main);
  const preloadText = read(files.desktop_preload);
  const routeText = read(files.ide_routes);
  const smoke = runDesktopScript('smoke-desktop-ide.js');
  const launchSmoke = runDesktopScript('launch-smoke-desktop-ide.js');
  const checks = [
    ...Object.entries(files).map(([name, filePath]) => ({ check: `${name}_exists`, passed: fs.existsSync(filePath), path: filePath })),
    { check: 'monaco_packaged', passed: packageText.includes('monaco-editor') },
    { check: 'command_palette_modal_present', passed: htmlText.includes('commandPaletteOverlay') && rendererText.includes('openCommandPaletteModal') },
    { check: 'status_chips_present', passed: htmlText.includes('statusChipBar') && rendererText.includes('updateStatusChips') },
    { check: 'local_readiness_ipc_present', passed: mainText.includes('localReleaseReadiness') && preloadText.includes('releaseReadiness') },
    { check: 'release_route_present', passed: routeText.includes('release-readiness/check') },
    { check: 'desktop_smoke_passed', passed: Boolean(smoke.ok), detail: smoke },
    { check: 'desktop_launch_smoke_passed', passed: Boolean(launchSmoke.ok), detail: launchSmoke },
  ];
  const passed = checks.filter(item => item.passed).length;
  return {
    ok: passed === checks.length,
    beast_object_type: 'beast_desktop_local_release_readiness',
    version: DESKTOP_IDE_VERSION,
    build_identity: BUILD_IDENTITY,
    source: 'electron_main_local',
    created_at: Date.now(),
    repoRoot: root,
    desktopRoot: __dirname,
    status: passed === checks.length ? 'pass' : 'warn',
    summary: { checks: checks.length, passed, failed: checks.length - passed },
    checks,
    smoke,
    launch_smoke: launchSmoke,
    gateway: {
      url: gatewayUrl,
      local_mode: localIdeMode,
      processPid: gatewayProcess?.pid || null,
    },
    read_only: true,
  };
}

function commandVersion(command, args = ['--version']) {
  try {
    const completed = spawnSync(command, args, {
      cwd: repoRoot,
      encoding: 'utf8',
      timeout: 5000,
    });
    const output = String(completed.stdout || completed.stderr || '').trim().split('\n')[0] || 'available';
    return { ok: completed.status === 0, command, version: output, returncode: completed.status };
  } catch (error) {
    return { ok: false, command, error: String(error.message || error) };
  }
}

function syntaxCheckFile(rootPath = repoRoot, relPath = '') {
  if (!relPath) return { ok: true, status: 'idle', detail: 'No active file selected.' };
  const pathCheck = safeWorkspacePath(rootPath || repoRoot, relPath);
  if (!pathCheck.ok) return { ok: false, status: 'blocked', detail: pathCheck.error, path: relPath };
  const suffix = path.extname(pathCheck.target).toLowerCase();
  try {
    if (suffix === '.json') {
      JSON.parse(fs.readFileSync(pathCheck.target, 'utf8'));
      return { ok: true, status: 'pass', kind: 'json', path: relPath };
    }
    if (suffix === '.js' || suffix === '.mjs' || suffix === '.cjs') {
      const completed = spawnSync('node', ['--check', pathCheck.target], { encoding: 'utf8', timeout: 10000 });
      return {
        ok: completed.status === 0,
        status: completed.status === 0 ? 'pass' : 'warn',
        kind: 'node',
        path: relPath,
        stdout: String(completed.stdout || '').slice(-2000),
        stderr: String(completed.stderr || '').slice(-2000),
      };
    }
    if (suffix === '.py') {
      const completed = spawnSync('python3', ['-m', 'py_compile', pathCheck.target], { encoding: 'utf8', timeout: 10000 });
      return {
        ok: completed.status === 0,
        status: completed.status === 0 ? 'pass' : 'warn',
        kind: 'python',
        path: relPath,
        stdout: String(completed.stdout || '').slice(-2000),
        stderr: String(completed.stderr || '').slice(-2000),
      };
    }
    return { ok: true, status: 'skipped', kind: suffix || 'text', path: relPath, detail: 'No syntax checker registered for this file type.' };
  } catch (error) {
    return { ok: false, status: 'warn', path: relPath, error: String(error.message || error) };
  }
}

function localToolingSnapshot(rootPath = repoRoot, activeFile = '') {
  const root = path.resolve(rootPath || repoRoot);
  const packagePath = path.join(root, 'package.json');
  const desktopPackagePath = path.join(root, 'desktop-ide', 'package.json');
  const cursorMcp = path.join(root, '.cursor', 'mcp.json');
  const vscodeDir = path.join(root, 'vscode-extension');
  const desktopDir = path.join(root, 'desktop-ide');
  const readJson = filePath => {
    try {
      return JSON.parse(fs.readFileSync(filePath, 'utf8'));
    } catch (_error) {
      return {};
    }
  };
  const rootPackage = readJson(packagePath);
  const desktopPackage = readJson(desktopPackagePath);
  const scripts = {
    root: Object.keys(rootPackage.scripts || {}),
    desktop: Object.keys(desktopPackage.scripts || {}),
  };
  const env = [
    commandVersion('python3', ['--version']),
    commandVersion('node', ['--version']),
    commandVersion('npm', ['--version']),
    commandVersion('git', ['--version']),
  ];
  const mcpConfigured = fs.existsSync(cursorMcp);
  return {
    ok: true,
    beast_object_type: 'beast_desktop_local_tooling_snapshot',
    version: DESKTOP_IDE_VERSION,
    source: 'electron_main_local',
    repoRoot: root,
    activeFile,
    syntax: syntaxCheckFile(root, activeFile),
    linting: {
      scripts,
      has_root_lint: scripts.root.some(item => item.includes('lint')),
      has_desktop_smoke: scripts.desktop.includes('smoke'),
      has_launch_smoke: scripts.desktop.includes('smoke:launch'),
      recommendation: scripts.root.some(item => item.includes('lint'))
        ? 'Use the project lint script through the governed terminal.'
        : 'No root lint script detected; use syntax checks and focused tests until a lint contract is added.',
    },
    mcp: {
      configured: mcpConfigured,
      cursor_config: cursorMcp,
      expected_routes: ['/edgek/mcp/state', '/edgek/mcp/servers', '/edgek/mcp/audit', '/edgek/mcp/executions', '/edgek/mcp/approvals'],
      status: mcpConfigured ? 'configured' : 'no local .cursor/mcp.json',
    },
    plugins: {
      vscode_extension_present: fs.existsSync(vscodeDir),
      desktop_ide_present: fs.existsSync(desktopDir),
      expected_routes: ['/edgek/plugins', '/edgek/plugins/manifest/prepare', '/edgek/plugins/manifest/validate', '/edgek/plugins/install'],
      status: fs.existsSync(vscodeDir) || fs.existsSync(desktopDir) ? 'local surfaces present' : 'no local plugin surfaces detected',
    },
    environments: env,
    read_only: true,
  };
}

function localSystemSnapshot(rootPath = repoRoot) {
  const root = path.resolve(rootPath || activeWorkspaceRoot || repoRoot);
  const python = resolveBeastPython();
  const code = [
    'import json, sys',
    'from pathlib import Path',
    'from app.kernel.workspaces import system_inspector',
    'root = Path(sys.argv[1]).resolve()',
    'snap = system_inspector.system_snapshot(root, port_limit=120, process_limit=80)',
    'snap["catalog"] = system_inspector.catalog_report(root)',
    'print(json.dumps(snap, default=str))',
  ].join('; ');
  const completed = spawnSync(python, ['-c', code, repoRoot], {
    cwd: repoRoot,
    env: { ...process.env, BEAST_ACTIVE_WORKSPACE: root, BEAST_WORKSPACE: root },
    encoding: 'utf8',
    timeout: 12000,
  });
  if (completed.error) {
    return { ok: false, source: 'electron_main_local', error: String(completed.error.message || completed.error) };
  }
  if (completed.status !== 0) {
    return {
      ok: false,
      source: 'electron_main_local',
      error: (completed.stderr || completed.stdout || `python exited ${completed.status}`).trim(),
    };
  }
  try {
    return { ...JSON.parse(completed.stdout || '{}'), source: 'electron_main_local' };
  } catch (error) {
    return { ok: false, source: 'electron_main_local', error: String(error.message || error), raw: completed.stdout };
  }
}

function resolveBeastPython() {
  if (resolvedBeastPython) return resolvedBeastPython;
  const candidates = [
    process.env.BEAST_PYTHON,
    path.join(repoRoot, 'venv', 'bin', 'python'),
    path.join(repoRoot, '.venv', 'bin', 'python'),
    'python3',
    'python',
  ].filter(Boolean);
  for (const candidate of candidates) {
    const completed = spawnSync(candidate, ['-c', 'import fastapi, uvicorn, cryptography, yaml'], {
      cwd: repoRoot,
      encoding: 'utf8',
      timeout: 5000,
    });
    if (!completed.error && completed.status === 0) {
      resolvedBeastPython = candidate;
      return resolvedBeastPython;
    }
  }
  resolvedBeastPython = process.env.BEAST_PYTHON || 'python3';
  return resolvedBeastPython;
}

function getJson(url, timeoutMs = 2500) {
  return new Promise((resolve, reject) => {
    const request = http.get(url, { timeout: timeoutMs }, response => {
      let body = '';
      response.setEncoding('utf8');
      response.on('data', chunk => { body += chunk; });
      response.on('end', () => {
        if (response.statusCode >= 400) {
          reject(new Error(`${url} -> ${response.statusCode}`));
          return;
        }
        try {
          resolve(JSON.parse(body || '{}'));
        } catch (error) {
          reject(error);
        }
      });
    });
    request.on('timeout', () => {
      request.destroy(new Error(`timeout: ${url}`));
    });
    request.on('error', reject);
  });
}

function httpProbe(url, timeoutMs = 1600) {
  return new Promise(resolve => {
    const started = Date.now();
    const request = http.get(url, { timeout: timeoutMs }, response => {
      response.resume();
      response.on('end', () => resolve({ ok: response.statusCode >= 200 && response.statusCode < 400, statusCode: response.statusCode, url, latencyMs: Date.now() - started }));
    });
    request.on('timeout', () => {
      request.destroy(new Error(`timeout: ${url}`));
    });
    request.on('error', error => resolve({ ok:false, url, error:String(error.message || error), latencyMs:Date.now() - started }));
  });
}

async function jsonHealthProbe(name, url, timeoutMs = 2000) {
  const started = Date.now();
  try {
    const payload = await getJson(url, timeoutMs);
    return { name, ok:true, url, latencyMs:Date.now() - started, payload };
  } catch (error) {
    return { name, ok:false, url, latencyMs:Date.now() - started, error:String(error.message || error) };
  }
}

function gatewayRequest(payload = {}) {
  return new Promise(resolve => {
    let target;
    try {
      const base = new URL(gatewayUrl);
      target = new URL(payload.path || payload.url || '/', base);
      if (target.origin !== base.origin || !['127.0.0.1', '::1', 'localhost'].includes(target.hostname)) {
        resolve({ ok: false, status: 0, error: 'gateway request escaped the active loopback origin' });
        return;
      }
    } catch (error) {
      resolve({ ok: false, status: 0, error: String(error.message || error) });
      return;
    }
    const method = String(payload.method || 'GET').toUpperCase();
    const encoded = payload.body == null ? null : Buffer.from(JSON.stringify(payload.body));
    if (encoded && encoded.length > 4 * 1024 * 1024) {
      resolve({ ok: false, status: 413, error: 'gateway IPC request body exceeds 4 MiB' });
      return;
    }
    const forbidden = new Set(['host', 'connection', 'content-length', 'transfer-encoding']);
    const headers = Object.fromEntries(Object.entries(payload.headers || {}).filter(([name]) => !forbidden.has(String(name).toLowerCase())).map(([name, value]) => [String(name), String(value)]));
    if (encoded) {
      headers['Content-Type'] = headers['Content-Type'] || 'application/json';
      headers['Content-Length'] = String(encoded.length);
    }
    // SourcePlan lifecycle and verification can legitimately need more than a
    // UI probe. Keep the cap bounded, but do not turn a normal review into a
    // guaranteed five-second failure under a busy local gateway.
    const timeoutMs = Math.max(250, Math.min(Number(payload.timeoutMs || 6000), 120000));
    const request = http.request(target, { method, headers, timeout: timeoutMs }, response => {
      const chunks = []; let total = 0;
      response.on('data', chunk => {
        total += chunk.length;
        if (total > 8 * 1024 * 1024) request.destroy(new Error('gateway response exceeds 8 MiB'));
        else chunks.push(chunk);
      });
      response.on('end', () => {
        const text = Buffer.concat(chunks).toString('utf8');
        let data = text;
        try { if ((response.headers['content-type'] || '').includes('application/json')) data = JSON.parse(text || 'null'); } catch (_) {}
        const ok = response.statusCode >= 200 && response.statusCode < 300;
        resolve({ ok, status: response.statusCode || 0, data, error: ok ? '' : (data?.detail || `${response.statusCode} gateway request failed`) });
      });
    });
    request.on('timeout', () => request.destroy(new Error(`gateway request timeout after ${timeoutMs} ms`)));
    request.on('error', error => resolve({ ok: false, status: 0, error: String(error.message || error) }));
    if (encoded) request.write(encoded);
    request.end();
  });
}

// Renderer pages are loaded from file://, so browser EventSource requests are
// carried through the trusted Electron gateway stream host.
const gatewayEventStreamHost = new GatewayEventStreamHost({ gatewayUrl: () => gatewayUrl });

async function runtimeStackHealth(baseUrl = gatewayUrl) {
  const litellmPort = serviceRegistryPort(repoRoot, 'litellm', 4000);
  const mcpHttpPort = serviceRegistryPort(repoRoot, 'mcp_http', 8765);
  const nginxPort = serviceRegistryPort(repoRoot, 'reverse_proxy', 80);
  const checks = await Promise.all([
    jsonHealthProbe('gateway', `${baseUrl}/health`, 2200),
    jsonHealthProbe('proxy', `${baseUrl}/proxy/health`, 2200),
    jsonHealthProbe('mcp_gateway', `${baseUrl}/mcp/health`, 1800),
    jsonHealthProbe('providers', `${baseUrl}/edgek/providers/state`, 3500),
    jsonHealthProbe('integrations', `${baseUrl}/edgek/tools/integrations`, 2200),
    httpProbe(`http://127.0.0.1:${mcpHttpPort}/mcp/health`, 1800).then(row => ({ name:'mcp_http', ...row })),
    httpProbe(`http://127.0.0.1:${litellmPort}/health`, 1800).then(row => ({ name:'litellm', ...row })),
    httpProbe(`http://127.0.0.1:${nginxPort}/health`, 1800).then(row => ({ name:'nginx', ...row })),
  ]);
  const byName = Object.fromEntries(checks.map(row => [row.name, row]));
  return {
    ok: Boolean(byName.gateway?.ok && byName.proxy?.ok && byName.providers?.ok),
    required_ok: Boolean(byName.gateway?.ok && byName.proxy?.ok && byName.providers?.ok),
    optional_ok: Boolean(byName.mcp_gateway?.ok && byName.mcp_http?.ok && byName.litellm?.ok && byName.nginx?.ok),
    checks: byName,
    summary: checks.map(row => `${row.name}:${row.ok ? 'ok' : (row.statusCode || row.error || 'attention')}`).join(' · '),
  };
}

async function gatewayHealth(baseUrl = gatewayUrl, rootTimeoutMs = 3500) {
  if (localIdeMode) {
    return {
      ok: false,
      url: gatewayUrl,
      local_mode: true,
      error: localIdeReason,
      capabilities: {
        ok: true,
        mode: 'desktop_local_fallback',
        checks: {
          local_files: { ok: true, mode: 'desktop_ipc' },
          local_editor: { ok: true, mode: 'monaco' },
          sourceplan_gateway: { ok: false, mode: 'deferred_until_gateway_ready' },
        },
      },
    };
  }
  try {
    const payload = await getJson(`${baseUrl}/edgek/root-info`, rootTimeoutMs);
    const capabilities = await gatewayCapabilityHealth(baseUrl, payload);
    return { ok: true, url: baseUrl, payload, capabilities };
  } catch (error) {
    const tcp = await gatewayTcpListening(baseUrl);
    return {
      ok: false,
      url: baseUrl,
      error: String(error.message || error),
      starting: Boolean(gatewayProcess && !gatewayProcess.killed),
      tcp_listening: tcp,
      started_at: gatewayStartedAt,
    };
  }
}

function gatewayTcpListening(urlValue, timeoutMs = 700) {
  return new Promise(resolve => {
    let parsed;
    try {
      parsed = new URL(urlValue);
    } catch (_error) {
      resolve(false);
      return;
    }
    const socket = net.createConnection({
      host: parsed.hostname,
      port: Number(parsed.port || 80),
      timeout: timeoutMs,
    });
    socket.once('connect', () => {
      socket.destroy();
      resolve(true);
    });
    socket.once('timeout', () => {
      socket.destroy();
      resolve(false);
    });
    socket.once('error', () => resolve(false));
  });
}

async function gatewayCapabilityHealth(baseUrl = gatewayUrl, rootPayload = null) {
  try {
    const contract = await getJson(`${baseUrl}/edgek/control-plane/desktop-compatibility`, 4500);
    const valid = contract?.contract === 'beast-desktop-enterprise-v1' && contract?.status === 'ready' && Object.values(contract?.checks || {}).every(Boolean);
    return { ok: valid, mode: 'side_effect_free_route_attestation', contract, checks: contract?.checks || {}, root_declared: Boolean(rootPayload?.endpoints) };
  } catch (error) {
    return { ok: false, mode: 'missing_enterprise_desktop_contract', error: String(error.message || error), checks: {}, root_declared: Boolean(rootPayload?.endpoints) };
  }
}

function portIsFree(port) {
  return new Promise(resolve => {
    const server = net.createServer();
    server.once('error', () => resolve(false));
    server.once('listening', () => {
      server.close(() => resolve(true));
    });
    server.listen(port, '127.0.0.1');
  });
}

async function chooseGatewayPort(preferred = 8101) {
  for (let port = preferred; port <= preferred + 20; port += 1) {
    if (await portIsFree(port)) return port;
  }
  return preferred;
}

async function findCompatibleGateway(preferred = 8101) {
  // A listener alone is not a gateway. Keep this probe bounded so an abandoned
  // Guardian-owned socket cannot hold desktop startup hostage, while still
  // allowing a cold BEAST gateway enough time to answer its desktop contract.
  // Always include the registry port.  A stale persisted/overridden URL such
  // as 8102 must not hide the healthy Guardian gateway on 8101.
  const ports = [...new Set([preferred, 8101, ...Array.from({ length: 6 }, (_item, index) => preferred + index)])];
  for (const port of ports) {
    const candidateUrl = `http://127.0.0.1:${port}`;
    if (!(await gatewayTcpListening(candidateUrl, 400))) continue;
    const ready = await gatewayHealth(candidateUrl, 2500);
    if (ready.ok && ready.capabilities?.ok) {
      return { url: candidateUrl, health: ready };
    }
  }
  return null;
}

function waitForGatewayExit(processRef) {
  return new Promise(resolve => {
    processRef.once('exit', code => resolve(code));
  });
}

async function stopManagedGateway(processRef, timeoutMs = 4000) {
  if (!processRef || processRef.exitCode !== null) return true;
  const exited = waitForGatewayExit(processRef);
  processRef.kill('SIGTERM');
  const stopped = await Promise.race([
    exited.then(() => true),
    new Promise(resolve => setTimeout(() => resolve(false), timeoutMs)),
  ]);
  if (stopped) return true;
  appendLog('managed gateway did not stop after SIGTERM; escalating shutdown');
  processRef.kill('SIGKILL');
  return Promise.race([
    exited.then(() => true),
    new Promise(resolve => setTimeout(() => resolve(false), 1500)),
  ]);
}

function runBoundedProcess(command, args, { cwd = repoRoot, env = process.env, timeoutMs = 45000 } = {}) {
  return new Promise(resolve => {
    let processRef;
    let finished = false;
    let timer = null;
    let stdout = '';
    let stderr = '';
    const finish = (extra = {}) => {
      if (finished) return;
      finished = true;
      if (timer) clearTimeout(timer);
      resolve({ command, args, ok: extra.code === 0 && !extra.timedOut, code: extra.code ?? null, timedOut: Boolean(extra.timedOut), stdout: stdout.slice(-6000), stderr: stderr.slice(-6000), ...extra });
    };
    try {
      processRef = spawn(command, args, { cwd, env, stdio: ['ignore', 'pipe', 'pipe'] });
      processRef.stdout.on('data', chunk => { stdout += chunk.toString(); });
      processRef.stderr.on('data', chunk => { stderr += chunk.toString(); });
      processRef.on('error', error => finish({ error: String(error.message || error) }));
      processRef.on('exit', code => finish({ code }));
    } catch (error) {
      finish({ error: String(error.message || error) });
    }
    timer = setTimeout(() => {
      try { processRef?.kill('SIGTERM'); } catch (_) {}
      finish({ timedOut: true, error: `${command} timed out after ${timeoutMs}ms` });
    }, timeoutMs);
  });
}

async function resetRuntimeStack() {
  // This intentionally controls only known BEAST user services. It never
  // guesses at arbitrary PIDs, and reports unavailable optional components.
  const startedAt = Date.now();
  const report = { ok: false, action: 'reset_runtime_stack', startedAt, components: [], gatewayUrl: '', durationMs: 0 };
  const add = (component, result) => {
    const entry = { component, ok: Boolean(result?.ok), status: result?.status || (result?.ok ? 'ready' : 'attention'), detail: result?.detail || result?.error || result?.stderr || '', ...result };
    report.components.push(entry);
    appendLog(`runtime reset · ${component}: ${entry.ok ? 'ok' : entry.status}${entry.detail ? ` · ${entry.detail}` : ''}`);
    return entry;
  };
  localIdeMode = false;
  localIdeReason = '';
  gatewayStartupPromise = null;
  if (gatewayProcess) {
    const managed = gatewayProcess;
    gatewayProcess = null;
    add('desktop_gateway', { ok: await stopManagedGateway(managed), status: 'stopped', detail: 'Stopped the desktop-managed direct gateway.' });
  } else {
    add('desktop_gateway', { ok: true, status: 'not_managed', detail: 'No desktop-managed gateway process was running.' });
  }

  // These are generated optional user units. `try-restart` is safe when they
  // are not installed or inactive; each result remains visible to the user.
  const guardianUnits = [
    'beast-socket-guardian.service',
    'beast-socket-guardian-beast.socket',
    'beast-socket-guardian-commons.socket',
    'beast-beast-guardian-consumer.service',
    'beast-commons-guardian-consumer.service',
  ];
  for (const unit of guardianUnits) {
    const result = await runBoundedProcess('systemctl', ['--user', 'restart', unit], { timeoutMs: 10000 });
    const unavailable = !result.ok && /not found|not loaded|could not be found/i.test(`${result.stderr} ${result.stdout}`);
    add(unit, { ...result, ok: result.ok || unavailable, status: unavailable ? 'not_installed' : result.ok ? 'restarted' : 'attention', detail: unavailable ? 'Optional user unit is not installed.' : (result.stderr || result.stdout || 'Restart request completed.') });
  }

  // The CLI healer owns daemon PID cleanup and restart ordering for LiteLLM,
  // Ollama, MCP HTTP, Nginx, the gateway, and its proxy lane. Do not kill
  // listener PIDs here: Guardian owns protected sockets and is handled above.
  const childEnv = { ...process.env, BEAST_DESKTOP_MANAGED: '1', BEAST_ACTIVE_WORKSPACE: activeWorkspaceRoot || repoRoot, BEAST_WORKSPACE: activeWorkspaceRoot || repoRoot };
  delete childEnv.BEAST_SOCKET_MODE;
  const registryGatewayPort = Number(new URL(configuredGatewayUrl).port || 8101);
  const registryMcpPort = serviceRegistryPort(repoRoot, 'mcp_http', 8765);
  const registryNginxPort = serviceRegistryPort(repoRoot, 'reverse_proxy', 80);
  const heal = await runBoundedProcess(resolveBeastPython(), [
    path.join(repoRoot, 'bin', 'beast'), 'heal',
    '--gateway-port', String(registryGatewayPort),
    '--mcp-port', String(registryMcpPort),
    '--nginx-port', String(registryNginxPort),
    '--restart-all', 'true',
    '--kill-address-pids', 'false',
  ], { env: childEnv, timeoutMs: 75000 });
  let healPayload = null;
  // The Python runtime may print early boot diagnostics before its JSON receipt.
  // Keep the command resilient by parsing the final structured object.
  try { healPayload = JSON.parse(heal.stdout.slice(heal.stdout.indexOf('{'))); } catch (_) {}
  add('beast_runtime_daemon', { ...heal, ok: heal.ok && Boolean(healPayload), status: healPayload?.status || (heal.ok ? 'completed' : 'attention'), detail: healPayload ? `Reset ${Array.isArray(healPayload.actions) ? healPayload.actions.length : 0} managed runtime actions.` : (heal.stderr || heal.error || 'The healer did not return a JSON receipt.'), receipt: healPayload });
  for (const [name, check] of Object.entries(healPayload?.after || {})) {
    add(name === 'mcp_http' ? 'mcp_http' : name, { ok: Boolean(check?.ok), status: check?.ok ? 'healthy' : 'attention', detail: check?.error || check?.path || '' });
  }

  const compatible = await findCompatibleGateway(8101);
  if (compatible) {
    gatewayUrl = compatible.url;
    report.gatewayUrl = gatewayUrl;
    add('desktop_contract', { ok: true, status: 'ready', detail: `Connected to ${gatewayUrl}.` });
    for (const windowRef of appWindows) if (!windowRef.isDestroyed()) windowRef.webContents.send('beast:refresh');
  } else {
    const ready = await ensureGateway();
    report.gatewayUrl = gatewayUrl;
    add('desktop_contract', { ok: Boolean(ready?.ok && ready?.capabilities?.ok), status: ready?.ok ? 'ready' : 'attention', detail: ready?.error || `Gateway recovery result: ${gatewayUrl}` });
  }
  report.durationMs = Date.now() - startedAt;
  report.ok = report.components.filter(item => ['gateway', 'proxy', 'litellm', 'ollama', 'nginx', 'desktop_contract'].includes(item.component)).every(item => item.ok);
  return report;
}

function spawnGatewayProcess(port) {
  const python = resolveBeastPython();
  const beast = path.join(repoRoot, 'bin', 'beast');
  const args = [beast, 'gateway', '--host', '127.0.0.1', '--port', String(port)];
  // Socket Guardian owns its listener and, on this installation, does not
  // expose the BEAST HTTP desktop contract.  The desktop must therefore run
  // its managed API as a direct sibling on a free port; inheriting guardian
  // socket mode here would make restart re-create the original conflict.
  lastGatewayCommand = `${python} ${args.map(item => `"${item}"`).join(' ')}`;
  gatewayStartedAt = Date.now();
  appendLog(`desktop repo root: ${repoRoot}`);
  appendLog(`active workspace: ${activeWorkspaceRoot || repoRoot}`);
  // The command parser reads BEAST_SOCKET_MODE from its environment.  Strip a
  // Guardian setting inherited from the shell: it belongs to the externally
  // managed listener, while this child is deliberately the direct HTTP API
  // sibling selected above.
  const childEnv = {
    ...process.env,
    PYTHONUNBUFFERED: '1',
    BEAST_DESKTOP_MANAGED: '1',
    BEAST_ACTIVE_WORKSPACE: activeWorkspaceRoot || repoRoot,
    BEAST_WORKSPACE: activeWorkspaceRoot || repoRoot,
  };
  delete childEnv.BEAST_SOCKET_MODE;
  appendLog(`starting direct desktop gateway: ${lastGatewayCommand}`);
  const processRef = spawn(python, args, {
    cwd: repoRoot,
    env: childEnv,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  processRef.stdout.on('data', chunk => appendLog(chunk.toString()));
  processRef.stderr.on('data', chunk => appendLog(chunk.toString()));
  processRef.on('exit', code => {
    appendLog(`gateway exited with code ${code}`);
    if (gatewayProcess === processRef) {
      gatewayProcess = null;
    }
  });
  return processRef;
}

async function ensureGateway() {
  if (gatewayStartupPromise) {
    appendLog('gateway startup already in progress; joining existing attempt');
    return gatewayStartupPromise;
  }
  gatewayStartupPromise = ensureGatewayInner().finally(() => {
    gatewayStartupPromise = null;
  });
  return gatewayStartupPromise;
}

async function ensureGatewayInner() {
  if (localIdeMode) {
    return enterLocalIdeMode(localIdeReason);
  }
  const health = await gatewayHealth();
  if (health.ok && health.capabilities?.ok) {
    appendLog(`attached to existing BEAST gateway at ${gatewayUrl}`);
    return health;
  }
  if (gatewayProcess && !gatewayProcess.killed && health.tcp_listening) {
    appendLog(`gateway process is listening at ${gatewayUrl}; waiting for HTTP routes instead of spawning another gateway`);
  }
  if (!health.ok && health.tcp_listening) {
    appendLog(`listener at ${gatewayUrl} did not answer the BEAST HTTP contract; preserving it and selecting a separate desktop gateway port`);
  }
  if (health.ok && !health.capabilities?.ok) {
    appendLog(`existing gateway at ${gatewayUrl} is missing desktop IDE routes; starting current BEAST on a free port`);
  }
  const url = new URL(gatewayUrl);
  const requestedPort = Number(url.port || 8101);
  const compatibleGateway = await findCompatibleGateway(requestedPort);
  if (compatibleGateway) {
    gatewayUrl = compatibleGateway.url;
    appendLog(`attached to compatible BEAST gateway at ${gatewayUrl}`);
    for (const windowRef of appWindows) if (!windowRef.isDestroyed()) windowRef.webContents.send('beast:refresh');
    return compatibleGateway.health;
  }
  const firstPort = health.ok || health.tcp_listening ? requestedPort + 1 : requestedPort;
  const maxAutomaticAttempts = 3;
  let attempts = 0;
  for (let port = firstPort; port <= firstPort + 20 && attempts < maxAutomaticAttempts; port += 1) {
    const candidateUrl = `http://127.0.0.1:${port}`;
    const incumbent = await gatewayHealth(candidateUrl, 2500);
    if (incumbent.ok && incumbent.capabilities?.ok) {
      gatewayUrl = candidateUrl;
      appendLog(`attached to incumbent BEAST gateway at ${gatewayUrl}`);
      for (const windowRef of appWindows) if (!windowRef.isDestroyed()) windowRef.webContents.send('beast:refresh');
      return incumbent;
    }
    if (!gatewayProcess || gatewayProcess.killed || gatewayUrl !== candidateUrl) {
      const free = await portIsFree(port);
      if (!free) {
        appendLog(`port ${port} is already in use; trying next port`);
        continue;
      }
      attempts += 1;
      gatewayUrl = candidateUrl;
      gatewayProcess = spawnGatewayProcess(port);
    }
    const exited = waitForGatewayExit(gatewayProcess);
    let sawTcpListening = false;
    for (let attempt = 0; attempt < 60; attempt += 1) {
      const race = await Promise.race([
        new Promise(resolve => setTimeout(() => resolve({ type: 'tick' }), 1000)),
        exited.then(code => ({ type: 'exit', code })),
      ]);
      if (race.type === 'exit') {
        appendLog(`gateway start failed on port ${port}; trying next port`);
        gatewayProcess = null;
        break;
      }
      const ready = await gatewayHealth(candidateUrl);
      if (ready.ok && ready.capabilities?.ok) {
        appendLog(`BEAST desktop gateway ready at ${gatewayUrl}`);
        for (const windowRef of appWindows) if (!windowRef.isDestroyed()) windowRef.webContents.send('beast:refresh');
        return ready;
      }
      sawTcpListening = sawTcpListening || Boolean(ready.tcp_listening);
      if (attempt > 0 && attempt % 15 === 0) {
        appendLog(`gateway warmup on port ${port}: tcp=${ready.tcp_listening ? 'listening' : 'waiting'} http=${ready.ok ? 'ok' : 'waiting'} ${ready.error || ''}`);
      }
    }
    if (gatewayProcess) {
      if (sawTcpListening) {
        appendLog(`gateway is listening on port ${port} but failed the desktop route contract; replacing it`);
        gatewayProcess.kill('SIGTERM');
        gatewayProcess = null;
        continue;
      }
      appendLog(`gateway did not listen on port ${port}; trying next port`);
      gatewayProcess.kill('SIGTERM');
      gatewayProcess = null;
    }
  }
  return enterLocalIdeMode('managed BEAST gateway did not become ready quickly; local file/editor mode is active');
}

function createMenu() {
  return installApplicationMenu({
    BrowserWindow,
    Menu,
    dialog,
    shell,
    ensureGateway,
    getGatewayUrl: () => gatewayUrl,
    getMainWindow: () => mainWindow,
    chooseWorkspace: workspace => ({ root:activeWorkspaceRoot, folders:setWorkspaceRoots([workspace],workspace) }),
  });
}

const desktopWindowHost = createDesktopWindowHost({
  BrowserWindow,
  desktopRoot: __dirname,
  createBrowserWindowOptions,
  defaultWindowBounds: DEFAULT_WINDOW_BOUNDS,
  readWindowState,
  persistWindowState,
  scheduleWindowStatePersist,
  setWorkspaceRoots,
  workspaceFolders,
  appendLog,
  buildIdentity: BUILD_IDENTITY,
  desktopVersion: DESKTOP_IDE_VERSION,
  repoRoot,
  getActiveWorkspaceRoot: () => activeWorkspaceRoot,
  setMainWindow: windowRef => { mainWindow = windowRef; },
  getMainWindow: () => mainWindow,
  appWindows,
  installMenu: createMenu,
  ensureGateway,
});
const createWindow = desktopWindowHost.createWindow;

ipcRegistry.handle('beast:status', async event => {
  let health = await gatewayHealth();
  if (!health.ok || !health.capabilities?.ok) {
    // Keep a managed compatible port (for example 8102 when Socket Guardian
    // owns 8101). Resetting to the registry port here made every transient
    // probe re-enter the Guardian conflict even after desktop had found a
    // healthy BEAST gateway.
    const requestedPort = Number(new URL(gatewayUrl).port || 8101);
    const compatibleGateway = await findCompatibleGateway(requestedPort);
    if (compatibleGateway) {
      gatewayUrl = compatibleGateway.url;
      health = compatibleGateway.health;
      appendLog(`status probe recovered compatible BEAST gateway at ${gatewayUrl}`);
    } else {
      ensureGateway();
    }
    if (!health.ok || !health.capabilities?.ok) health = { ...health, ok: false, starting: true, url: gatewayUrl };
  }
  const windowRef = BrowserWindow.fromWebContents(event.sender);
  const runtimeStack = await runtimeStackHealth(health.url || gatewayUrl);
  return {
    gatewayUrl: health.url || gatewayUrl,
    repoRoot: activeWorkspaceRoot || repoRoot,
    workspaceFolders: workspaceFolders(),
    beastRepoRoot: repoRoot,
    health,
    runtimeStack,
    processPid: gatewayProcess?.pid || null,
    lastGatewayCommand,
    gatewayLog,
    desktopVersion: DESKTOP_IDE_VERSION,
    rendererPath: path.join(__dirname, 'renderer', 'index.html'),
    windowId: windowRef?.id || null,
    windowCount: appWindows.size,
  };
});

ipcRegistry.handle('beast:gateway-request', async (_event, payload) => gatewayRequest(payload || {}));
ipcRegistry.handle('beast:gateway-stream-start', async (event, payload) => gatewayEventStreamHost.start(payload || {}, event.sender));
ipcRegistry.handle('beast:gateway-stream-stop', async (_event, id) => gatewayEventStreamHost.stop(id));

function normalizedZoomLevel(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? Math.max(-3, Math.min(5, Math.round(numeric))) : 0;
}

ipcRegistry.handle('beast:zoom-get', async event => {
  const windowRef = BrowserWindow.fromWebContents(event.sender) || mainWindow;
  return { level: windowRef?.webContents.getZoomLevel?.() ?? 0, factor: windowRef?.webContents.getZoomFactor?.() ?? 1 };
});
ipcRegistry.handle('beast:zoom-set', async (event, requestedLevel) => {
  const windowRef = BrowserWindow.fromWebContents(event.sender) || mainWindow;
  if (!windowRef || windowRef.isDestroyed()) throw new Error('No BEAST desktop window is available for zoom.');
  const level = normalizedZoomLevel(requestedLevel); windowRef.webContents.setZoomLevel(level);
  return { level, factor: windowRef.webContents.getZoomFactor() };
});
ipcRegistry.handle('beast:zoom-reset', async event => {
  const windowRef = BrowserWindow.fromWebContents(event.sender) || mainWindow;
  if (!windowRef || windowRef.isDestroyed()) throw new Error('No BEAST desktop window is available for zoom.');
  windowRef.webContents.setZoomLevel(0); return { level: 0, factor: windowRef.webContents.getZoomFactor() };
});

ipcRegistry.handle('beast:execution-target-get', async () => ({ok:true,target:executionTargetSummary()}));
ipcRegistry.handle('beast:execution-target-set', async (_event,payload) => setActiveExecutionTarget(payload || {}));
ipcRegistry.handle('beast:execution-target-list', async (_event,payload) => listExecutionTargets(registeredWorkspaceRoot(payload || {})));

ipcRegistry.handle('beast:restart-gateway', async () => {
  localIdeMode = false;
  localIdeReason = '';
  gatewayStartupPromise = null;
  if (gatewayProcess) {
    const previousGateway = gatewayProcess;
    gatewayProcess = null;
    const stopped = await stopManagedGateway(previousGateway);
    if (!stopped) {
      throw new Error('Managed BEAST gateway did not stop; restart was not attempted to avoid attaching to a stale process.');
    }
  }
  return ensureGateway();
});

ipcRegistry.handle('beast:reset-runtime-stack', async () => resetRuntimeStack());

ipcRegistry.handle('beast:open-gateway', async () => {
  await shell.openExternal(gatewayUrl);
  return { ok: true, gatewayUrl };
});

ipcRegistry.handle('beast:list-files', async (_event, rootPath, limit) => {
  if(!rootPath||path.resolve(rootPath)===activeWorkspaceRoot)return multiRootFiles(Math.max(1, Math.min(Number(limit || 400), 2000)));
  return workspaceFileCandidates(rootPath, Math.max(1, Math.min(Number(limit || 400), 2000)));
});

ipcRegistry.handle('beast:read-file', async (_event, rootPath, relPath, maxChars) => {
  const ref=parseWorkspaceReference(relPath);if(!ref.folder)return {ok:false,error:'Unknown workspace folder reference.',path:relPath};return readWorkspaceFile(ref.folder.path,ref.relative, Math.max(1, Math.min(Number(maxChars || 200000), 1000000)));
});
ipcRegistry.handle('beast:workspace-target-list-files', async (_event, payload) => workspaceTargetListFiles(registeredWorkspaceRoot(payload || {}), payload || {}));
ipcRegistry.handle('beast:workspace-target-read-file', async (_event, payload) => workspaceTargetReadFile(registeredWorkspaceRoot(payload || {}), payload || {}));
ipcRegistry.handle('beast:workspace-target-write-file', async (_event, payload) => workspaceTargetWriteFile(registeredWorkspaceRoot(payload || {}), payload || {}));


ipcRegistry.handle('beast:workspace-search', async (_event, payload) => textWorkspaceSearch(registeredWorkspaceRoot(payload),payload || {}));
ipcRegistry.handle('beast:workspace-replace', async (_event, payload) => workspaceReplacePreview(registeredWorkspaceRoot(payload),payload || {}));
ipcRegistry.handle('beast:workspace-git-status', async (_event,payload) => workspaceGitStatus(registeredWorkspaceRoot(payload)));
ipcRegistry.handle('beast:workspace-git-repositories', async () => ({ok:true,repositories:await Promise.all(workspaceFolders().map(async folder=>{const status=await workspaceGitStatus(folder.path);return {folder,status:{ok:status.ok,branch:status.branch||'',branchName:status.branchName||'',counts:status.counts||{staged:0,unstaged:0,conflicts:0},changes:status.changes||[],error:status.error||''}};}))}));
ipcRegistry.handle('beast:workspace-git-action', async (_event, payload) => workspaceGitAction(registeredWorkspaceRoot(payload),payload?.action,payload?.path));
ipcRegistry.handle('beast:workspace-git-diff', async (_event, payload) => workspaceGitDiff(registeredWorkspaceRoot(payload),payload || {}));
ipcRegistry.handle('beast:workspace-git-commit', async (_event, payload) => workspaceGitCommit(registeredWorkspaceRoot(payload),payload || {}));
ipcRegistry.handle('beast:workspace-git-branch', async (_event, payload) => workspaceGitBranch(registeredWorkspaceRoot(payload),payload || {}));
ipcRegistry.handle('beast:workspace-git-hunks', async (_event, payload) => workspaceGitHunks(registeredWorkspaceRoot(payload),payload || {}));
ipcRegistry.handle('beast:workspace-git-hunk-action', async (_event, payload) => workspaceGitHunkAction(registeredWorkspaceRoot(payload),payload || {}));
ipcRegistry.handle('beast:workspace-git-conflict', async (_event, payload) => workspaceGitConflict(registeredWorkspaceRoot(payload),payload || {}));
ipcRegistry.handle('beast:workspace-git-resolve', async (_event, payload) => workspaceGitResolve(registeredWorkspaceRoot(payload),payload || {}));
ipcRegistry.handle('beast:workspace-git-history', async (_event, payload) => workspaceGitHistory(registeredWorkspaceRoot(payload),payload || {}));
ipcRegistry.handle('beast:workspace-git-remotes', async (_event,payload) => workspaceGitRemotes(registeredWorkspaceRoot(payload)));
ipcRegistry.handle('beast:workspace-git-operation', async (_event, payload) => workspaceGitOperation(registeredWorkspaceRoot(payload),payload || {}));
ipcRegistry.handle('beast:workspace-tasks', async (_event,payload) => workspaceTasks(registeredWorkspaceRoot(payload)));
ipcRegistry.handle('beast:workspace-task-run', async (_event, payload) => runWorkspaceTask(registeredWorkspaceRoot(payload),payload));
ipcRegistry.handle('beast:workspace-settings', async (_event,payload) => workspaceSettings(registeredWorkspaceRoot(payload)));
ipcRegistry.handle('beast:workspace-settings-save', async (_event,payload) => writeWorkspaceSettings(registeredWorkspaceRoot(payload),payload?.settings));
ipcRegistry.handle('beast:workspace-tests', async (_event,payload) => workspaceTestsForTarget(registeredWorkspaceRoot(payload),payload||{}));
ipcRegistry.handle('beast:workspace-test-run', async (_event,payload) => runWorkspaceTest(registeredWorkspaceRoot(payload),payload));
ipcRegistry.handle('beast:workspace-task-list', async () => ({ok:true,sessions:workspaceTaskHost.list()}));
ipcRegistry.handle('beast:workspace-task-start', async (event,payload) => ({ok:true,session:workspaceTaskHost.start(registeredWorkspaceRoot(payload),typeof payload==='string'?payload:payload?.id,event.sender)}));
ipcRegistry.handle('beast:workspace-task-stop', async (_event,id) => workspaceTaskHost.stop(id));

ipcRegistry.handle('beast:file-operation', async (_event, rootPath, operation) => {
  return mutateWorkspaceFile(rootPath || activeWorkspaceRoot || repoRoot, operation || {});
});

ipcRegistry.handle('beast:open-workspace-window', async (_event, workspace) => {
  const target = path.resolve(workspace || activeWorkspaceRoot || repoRoot);
  if (!fs.existsSync(target)) return { ok: false, error: 'workspace path does not exist', workspace: target };
  await createWindow({ initialWorkspace: target });
  return { ok: true, workspace: target };
});

ipcRegistry.handle('beast:release-readiness', async (_event, rootPath) => {
  return localReleaseReadiness(rootPath || activeWorkspaceRoot || repoRoot);
});

ipcRegistry.handle('beast:tooling-snapshot', async (_event, rootPath, activeFile) => {
  return localToolingSnapshot(rootPath || activeWorkspaceRoot || repoRoot, activeFile || '');
});

ipcRegistry.handle('beast:system-snapshot', async (_event, rootPath) => {
  return localSystemSnapshot(rootPath || activeWorkspaceRoot || repoRoot);
});

ipcRegistry.handle('beast:ide-compatibility', async (_event, rootPath) => {
  return ideCompatibilityHost.discover(rootPath || activeWorkspaceRoot || repoRoot);
});

ipcRegistry.handle('beast:ide-capability-install', async (_event, options) => {
  return ideCompatibilityHost.install(options || {});
});

ipcRegistry.handle('beast:ide-protocol-start', async (event, options) => {
  return ideCompatibilityHost.start({ ...(options || {}), root:options?.root || activeWorkspaceRoot || repoRoot, target:options?.target || executionTargetHost.getActiveExecutionTarget() }, event.sender);
});

ipcRegistry.handle('beast:ide-protocol-request', async (_event, payload) => {
  return ideCompatibilityHost.request(payload || {});
});

ipcRegistry.handle('beast:ide-protocol-notify', async (_event, payload) => {
  return ideCompatibilityHost.notify(payload || {});
});

ipcRegistry.handle('beast:ide-protocol-stop', async (_event, sessionId) => {
  return ideCompatibilityHost.stop(String(sessionId || ''));
});

ipcRegistry.handle('beast:notebook-execute', async (_event, payload) => {
  return executeNotebookCell(activeWorkspaceRoot || repoRoot, payload || {});
});

ipcRegistry.handle('beast:notebook-kernel-start', async (event, rootPath) => {
  return notebookKernelHost.start(rootPath || activeWorkspaceRoot || repoRoot,event.sender);
});

ipcRegistry.handle('beast:notebook-kernel-request', async (_event, payload) => {
  return notebookKernelHost.request(payload || {});
});

ipcRegistry.handle('beast:notebook-kernel-stop', async () => notebookKernelHost.stop());

ipcRegistry.handle('beast:remote-probe', async (_event, payload) => {
  return probeRemoteWorkspace(payload || {});
});

ipcRegistry.handle('beast:remote-list-files', async (_event, payload) => {
  return listRemoteWorkspaceFiles(payload || {});
});
ipcRegistry.handle('beast:remote-search', async (_event, payload) => searchRemoteWorkspace(payload || {}));
ipcRegistry.handle('beast:remote-reconnect', async () => reconnectRemoteWorkspace());
ipcRegistry.handle('beast:remote-health', async (_event,payload) => remoteWorkspaceHealth(payload || {}));
ipcRegistry.handle('beast:remote-read-file', async (_event, payload) => readRemoteWorkspaceFile(payload || {}));
ipcRegistry.handle('beast:remote-write-file', async (_event, payload) => writeRemoteWorkspaceFile(payload || {}));
ipcRegistry.handle('beast:remote-terminal-run', async (_event, payload) => runRemoteTerminal(payload || {}));
ipcRegistry.handle('beast:dev-container-inspect', async (_event,payload) => inspectDevContainers(registeredWorkspaceRoot(payload)));
ipcRegistry.handle('beast:dev-container-start', async (_event,payload) => startDevContainer(registeredWorkspaceRoot(payload)));
ipcRegistry.handle('beast:dev-container-stop', async (_event,payload) => stopDevContainer(registeredWorkspaceRoot(payload),payload?.id));
ipcRegistry.handle('beast:dev-container-restart', async (_event,payload) => restartDevContainer(registeredWorkspaceRoot(payload),payload?.id));
ipcRegistry.handle('beast:dev-container-attach', async (_event,payload) => attachDevContainer(registeredWorkspaceRoot(payload),payload?.id));
ipcRegistry.handle('beast:dev-container-rebuild', async (_event,payload) => rebuildDevContainer(registeredWorkspaceRoot(payload)));
ipcRegistry.handle('beast:dev-container-logs', async (_event,payload) => devContainerLogs(registeredWorkspaceRoot(payload),payload?.id));
ipcRegistry.handle('beast:dev-container-terminal-run', async (_event,payload) => runDevContainerTerminal(registeredWorkspaceRoot(payload),payload || {}));
ipcRegistry.handle('beast:dev-container-open-port', async (_event,payload) => { const port=Number(payload?.port);if(!Number.isInteger(port)||port<1||port>65535)return {ok:false,error:'Container port must be between 1 and 65535.'};const url=`http://127.0.0.1:${port}`;await shell.openExternal(url);return {ok:true,url,port}; });
ipcRegistry.handle('beast:remote-terminal-list', async () => ({ok:true,terminals:remoteTerminalHost.list()}));
ipcRegistry.handle('beast:remote-terminal-start', async (event,payload) => ({ok:true,terminal:remoteTerminalHost.start(payload || {},event.sender)}));
ipcRegistry.handle('beast:remote-terminal-send', async (_event,payload) => remoteTerminalHost.send(payload?.id,payload?.input));
ipcRegistry.handle('beast:remote-terminal-stop', async (_event,id) => remoteTerminalHost.stop(id));
ipcRegistry.handle('beast:terminal-session-list', async () => ({ok:true,terminals:localTerminalHost.list()}));
ipcRegistry.handle('beast:terminal-session-start', async (event,payload) => ({ok:true,terminal:localTerminalHost.start(registeredWorkspaceRoot(payload),payload||{},event.sender)}));
ipcRegistry.handle('beast:terminal-session-send', async (_event,payload) => localTerminalHost.send(payload?.id,payload?.input));
ipcRegistry.handle('beast:terminal-session-stop', async (_event,id) => localTerminalHost.stop(id));

ipcRegistry.handle('beast:remote-forward-list', async () => ({ ok:true, forwards:sshForwardHost.list() }));

ipcRegistry.handle('beast:remote-forward-start', async (event, payload) => {
  return { ok:true, forward:sshForwardHost.start(payload || {},event.sender) };
});

ipcRegistry.handle('beast:remote-forward-stop', async (_event, id) => sshForwardHost.stop(id));

ipcRegistry.handle('beast:extension-host-discover', async (event, rootPath) => {
  return beastExtensionHost.discover(rootPath || activeWorkspaceRoot || repoRoot,event.sender,executionTargetHost.getActiveExecutionTarget());
});

ipcRegistry.handle('beast:extension-host-grant', async (event, payload) => {
  return beastExtensionHost.grantForTarget(activeWorkspaceRoot || repoRoot,payload?.id,payload?.capabilities,event.sender,payload?.target || executionTargetHost.getActiveExecutionTarget());
});
ipcRegistry.handle('beast:extension-host-enable', async (event,payload) => beastExtensionHost.setEnabled(activeWorkspaceRoot||repoRoot,payload?.id,Boolean(payload?.enabled),event.sender));
ipcRegistry.handle('beast:extension-host-install', async event => beastExtensionHost.installWorkspaceExtension(activeWorkspaceRoot||repoRoot,event.sender));
ipcRegistry.handle('beast:extension-host-deploy', async (event,payload) => beastExtensionHost.deployWorkspaceExtensions(activeWorkspaceRoot||repoRoot,event.sender,payload?.target || executionTargetHost.getActiveExecutionTarget()));
ipcRegistry.handle('beast:extension-host-uninstall', async (event,payload) => beastExtensionHost.uninstallWorkspaceExtension(activeWorkspaceRoot||repoRoot,payload?.id,event.sender));
ipcRegistry.handle('beast:extension-host-execute', async (event, payload) => beastExtensionHost.execute(activeWorkspaceRoot || repoRoot,payload?.id,payload?.command,event.sender,payload?.target || executionTargetHost.getActiveExecutionTarget()));

ipcRegistry.handle('beast:extension-host-stop', async () => beastExtensionHost.stop());

registerApplicationLifecycle({
  app,
  BrowserWindow,
  createWindow,
  onReady: () => {
    windowStateStore = createWindowStateStore({ app, screen, appendLog });
    restoreWorkspaceFolders();
    return createWindow();
  },
  onWindowAllClosed: () => {
    if (gatewayProcess) gatewayProcess.kill('SIGTERM');
    ideCompatibilityHost.stopAll();
    notebookKernelHost.stop();
    gatewayEventStreamHost.stopAll();
    windowStateStore?.dispose();
    sshForwardHost.stopAll();
    remoteTerminalHost.stopAll();
    workspaceTaskHost.stopAll();
    localTerminalHost.stopAll();
    beastExtensionHost.stop();
    if (process.platform !== 'darwin') app.quit();
  },
});
