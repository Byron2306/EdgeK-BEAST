const { app, BrowserWindow, Menu, dialog, ipcMain, shell } = require('electron');
const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const http = require('http');
const net = require('net');
const path = require('path');

const DESKTOP_IDE_VERSION = '0.1.1-ux-modal-chips';

function resolveRepoRoot() {
  const candidates = [
    process.env.BEAST_REPO_ROOT,
    process.env.BEAST_WORKSPACE,
    process.cwd(),
    path.resolve(__dirname, '..'),
    path.resolve(__dirname, '..', '..', '..', '..'),
    path.resolve(__dirname, '..', '..', '..', '..', '..'),
  ].filter(Boolean);
  for (const candidate of candidates) {
    const root = path.resolve(candidate);
    if (fs.existsSync(path.join(root, 'bin', 'beast')) && fs.existsSync(path.join(root, 'app', 'main.py'))) {
      return root;
    }
  }
  return path.resolve(__dirname, '..');
}

const repoRoot = resolveRepoRoot();
let gatewayUrl = process.env.BEAST_DESKTOP_GATEWAY || 'http://127.0.0.1:8000';
let gatewayProcess = null;
let gatewayStartupPromise = null;
let mainWindow = null;
const appWindows = new Set();
let lastGatewayCommand = '';
let gatewayLog = [];
let gatewayStartedAt = 0;
let localIdeMode = false;
let localIdeReason = '';

function appendLog(line) {
  gatewayLog.push(`[${new Date().toISOString()}] ${String(line || '').trim()}`);
  gatewayLog = gatewayLog.slice(-500);
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

function workspaceFileCandidates(rootPath, limit = 400) {
  const root = path.resolve(rootPath || repoRoot);
  const ignore = new Set(['.git', '.beast', 'node_modules', '__pycache__', '.pytest_cache', 'dist', 'build', '.venv', 'venv']);
  const rows = [];
  function walk(dir) {
    if (rows.length >= limit) return;
    let entries = [];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch (_error) {
      return;
    }
    entries.sort((a, b) => a.name.localeCompare(b.name));
    for (const entry of entries) {
      if (rows.length >= limit) return;
      if (ignore.has(entry.name)) continue;
      const full = path.join(dir, entry.name);
      const rel = path.relative(root, full);
      if (entry.isDirectory()) {
        walk(full);
      } else if (entry.isFile()) {
        rows.push({ path: rel, source: 'desktop_local_files' });
      }
    }
  }
  walk(root);
  return rows;
}

function readWorkspaceFile(rootPath, relPath, maxChars = 200000) {
  const root = path.resolve(rootPath || repoRoot);
  const target = path.resolve(root, relPath || '');
  if (target !== root && !target.startsWith(`${root}${path.sep}`)) {
    return { ok: false, error: 'path escaped workspace', path: relPath };
  }
  try {
    const content = fs.readFileSync(target, 'utf8').slice(0, maxChars);
    return { ok: true, path: relPath, content, source: 'desktop_local_files' };
  } catch (error) {
    return { ok: false, error: String(error.message || error), path: relPath };
  }
}

function safeWorkspacePath(rootPath, relPath) {
  const root = path.resolve(rootPath || repoRoot);
  const target = path.resolve(root, relPath || '');
  if (target === root || !target.startsWith(`${root}${path.sep}`)) {
    return { ok: false, error: 'path escaped workspace', root, target };
  }
  return { ok: true, root, target };
}

function mutateWorkspaceFile(rootPath, operation = {}) {
  const op = String(operation.op || '').trim();
  const pathCheck = safeWorkspacePath(rootPath || repoRoot, operation.path || '');
  if (!pathCheck.ok) return { ok: false, error: pathCheck.error, op };
  try {
    if (op === 'create_file') {
      fs.mkdirSync(path.dirname(pathCheck.target), { recursive: true });
      if (!fs.existsSync(pathCheck.target)) fs.writeFileSync(pathCheck.target, String(operation.content || ''), 'utf8');
      return { ok: true, op, path: path.relative(pathCheck.root, pathCheck.target) };
    }
    if (op === 'create_folder') {
      fs.mkdirSync(pathCheck.target, { recursive: true });
      return { ok: true, op, path: path.relative(pathCheck.root, pathCheck.target) };
    }
    if (op === 'rename') {
      const targetCheck = safeWorkspacePath(rootPath || repoRoot, operation.target || '');
      if (!targetCheck.ok) return { ok: false, error: targetCheck.error, op };
      fs.mkdirSync(path.dirname(targetCheck.target), { recursive: true });
      fs.renameSync(pathCheck.target, targetCheck.target);
      return {
        ok: true,
        op,
        path: path.relative(pathCheck.root, pathCheck.target),
        target: path.relative(targetCheck.root, targetCheck.target),
      };
    }
    if (op === 'delete_file') {
      const stat = fs.statSync(pathCheck.target);
      if (!stat.isFile()) return { ok: false, error: 'delete_file only removes files', op };
      fs.unlinkSync(pathCheck.target);
      return { ok: true, op, path: path.relative(pathCheck.root, pathCheck.target) };
    }
    return { ok: false, error: `unsupported operation: ${op}`, op };
  } catch (error) {
    return { ok: false, error: String(error.message || error), op };
  }
}

function runDesktopScript(scriptName) {
  const scriptPath = path.join(__dirname, 'scripts', scriptName);
  if (!fs.existsSync(scriptPath)) {
    return { ran: false, ok: false, error: `${scriptName} missing`, script: scriptPath };
  }
  try {
    const completed = spawnSync('node', [scriptPath], {
      cwd: __dirname,
      encoding: 'utf8',
      timeout: 30000,
    });
    return {
      ran: true,
      ok: completed.status === 0,
      returncode: completed.status,
      stdout: String(completed.stdout || '').slice(-4000),
      stderr: String(completed.stderr || '').slice(-4000),
      script: scriptPath,
    };
  } catch (error) {
    return { ran: true, ok: false, error: String(error.message || error), script: scriptPath };
  }
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

async function gatewayHealth(baseUrl = gatewayUrl, rootTimeoutMs = 8000) {
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
  const endpoints = rootPayload?.endpoints && typeof rootPayload.endpoints === 'object'
    ? rootPayload.endpoints
    : {};
  const declaredChecks = {
    ide_snapshot: endpoints.edgek_ide_snapshot === '/edgek/ide/snapshot',
    ide_events: endpoints.edgek_ide_events === '/edgek/ide/events',
    mission_timeline: endpoints.edgek_ide_mission_timeline === '/edgek/ide/mission-timeline',
    workspace_files: endpoints.edgek_workspace_files === '/edgek/workspace/files',
  };
  if (Object.keys(endpoints).length) {
    const checks = Object.fromEntries(Object.entries(declaredChecks).map(([name, ok]) => [
      name,
      ok
        ? { ok: true, mode: 'declared_by_root_info' }
        : { ok: false, mode: 'declared_by_root_info', error: 'route not listed in /edgek/root-info' },
    ]));
    return {
      ok: Object.values(checks).every(item => item.ok),
      mode: 'route_manifest',
      checks,
    };
  }
  const checksToProbe = [
    ['ide_snapshot', `/edgek/ide/snapshot?root_path=${encodeURIComponent(repoRoot)}&objective=desktop-health`],
    ['workspace_files', `/edgek/workspace/files?root_path=${encodeURIComponent(repoRoot)}&limit=1`],
  ];
  const results = {};
  for (const [name, route] of checksToProbe) {
    try {
      await getJson(`${baseUrl}${route}`, 2500);
      results[name] = { ok: true };
    } catch (error) {
      results[name] = { ok: false, error: String(error.message || error) };
    }
  }
  return {
    ok: Object.values(results).every(item => item.ok),
    mode: 'active_probe',
    checks: results,
  };
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

async function chooseGatewayPort(preferred = 8000) {
  for (let port = preferred; port <= preferred + 20; port += 1) {
    if (await portIsFree(port)) return port;
  }
  return preferred;
}

async function findCompatibleGateway(preferred = 8000) {
  const ports = [
    preferred,
    ...Array.from({ length: 21 }, (_item, index) => 8000 + index).filter(port => port !== preferred),
  ];
  for (const port of ports) {
    const candidateUrl = `http://127.0.0.1:${port}`;
    if (!(await gatewayTcpListening(candidateUrl, 250))) continue;
    const ready = await gatewayHealth(candidateUrl, 1200);
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

function spawnGatewayProcess(port) {
  const python = process.env.BEAST_PYTHON || 'python3';
  const beast = path.join(repoRoot, 'bin', 'beast');
  const args = [beast, 'gateway', '--host', '127.0.0.1', '--port', String(port)];
  lastGatewayCommand = `${python} ${args.map(item => `"${item}"`).join(' ')}`;
  gatewayStartedAt = Date.now();
  appendLog(`desktop repo root: ${repoRoot}`);
  appendLog(`starting gateway: ${lastGatewayCommand}`);
  const processRef = spawn(python, args, {
    cwd: repoRoot,
    env: {
      ...process.env,
      BEAST_ACTIVE_WORKSPACE: process.env.BEAST_ACTIVE_WORKSPACE || repoRoot,
      BEAST_WORKSPACE: process.env.BEAST_WORKSPACE || repoRoot,
    },
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
  if (health.ok && !health.capabilities?.ok) {
    appendLog(`existing gateway at ${gatewayUrl} is missing desktop IDE routes; starting current BEAST on a free port`);
  }
  const url = new URL(gatewayUrl);
  const requestedPort = Number(url.port || 8000);
  const compatibleGateway = await findCompatibleGateway(requestedPort);
  if (compatibleGateway) {
    gatewayUrl = compatibleGateway.url;
    appendLog(`attached to compatible BEAST gateway at ${gatewayUrl}`);
    return compatibleGateway.health;
  }
  const firstPort = health.ok ? requestedPort + 1 : requestedPort;
  const maxAutomaticAttempts = 3;
  let attempts = 0;
  for (let port = firstPort; port <= firstPort + 20 && attempts < maxAutomaticAttempts; port += 1) {
    const candidateUrl = `http://127.0.0.1:${port}`;
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
    for (let attempt = 0; attempt < 180; attempt += 1) {
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
        return ready;
      }
      sawTcpListening = sawTcpListening || Boolean(ready.tcp_listening);
      if (attempt > 0 && attempt % 15 === 0) {
        appendLog(`gateway warmup on port ${port}: tcp=${ready.tcp_listening ? 'listening' : 'waiting'} http=${ready.ok ? 'ok' : 'waiting'} ${ready.error || ''}`);
      }
    }
    if (gatewayProcess) {
      if (sawTcpListening) {
        appendLog(`gateway is still listening on port ${port} but HTTP routes are not ready; leaving process alive for diagnosis`);
        return await gatewayHealth(candidateUrl);
      }
      appendLog(`gateway did not listen on port ${port}; trying next port`);
      gatewayProcess.kill('SIGTERM');
      gatewayProcess = null;
    }
  }
  return enterLocalIdeMode('managed BEAST gateway did not become ready quickly; local file/editor mode is active');
}

function createMenu() {
  const template = [
    {
      label: 'BEAST',
      submenu: [
        { label: 'Start or Attach Gateway', click: () => ensureGateway() },
        { label: 'Open Gateway in Browser', click: () => shell.openExternal(gatewayUrl) },
        { type: 'separator' },
        { role: 'quit' },
      ],
    },
    {
      label: 'Workspace',
      submenu: [
        {
          label: 'Choose Workspace',
          accelerator: 'CmdOrCtrl+O',
          click: async () => {
            const targetWindow = BrowserWindow.getFocusedWindow() || mainWindow;
            const result = await dialog.showOpenDialog(targetWindow, { properties: ['openDirectory'] });
            if (!result.canceled && result.filePaths[0]) {
              targetWindow.webContents.send('beast:workspace-selected', result.filePaths[0]);
            }
          },
        },
        { label: 'Refresh IDE Snapshot', accelerator: 'CmdOrCtrl+R', click: () => (BrowserWindow.getFocusedWindow() || mainWindow)?.webContents.send('beast:refresh') },
      ],
    },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'toggleDevTools' },
        { role: 'togglefullscreen' },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

async function createWindow(options = {}) {
  const initialWorkspace = options.initialWorkspace || '';
  const windowRef = new BrowserWindow({
    width: 1560,
    height: 980,
    minWidth: 1180,
    minHeight: 760,
    title: 'BEAST Desktop IDE',
    backgroundColor: '#050607',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  mainWindow = windowRef;
  appWindows.add(windowRef);
  windowRef.on('focus', () => { mainWindow = windowRef; });
  windowRef.on('closed', () => {
    appWindows.delete(windowRef);
    if (mainWindow === windowRef) mainWindow = [...appWindows].find(item => !item.isDestroyed()) || null;
  });
  try {
    await windowRef.webContents.session.clearCache();
  } catch (error) {
    appendLog(`renderer cache clear failed: ${error.message || error}`);
  }
  windowRef.webContents.once('did-finish-load', () => {
    appendLog(`renderer loaded: ${path.join(__dirname, 'renderer', 'index.html')} · ${DESKTOP_IDE_VERSION}`);
    windowRef.webContents.send('beast:desktop-version', {
      version: DESKTOP_IDE_VERSION,
      rendererPath: path.join(__dirname, 'renderer', 'index.html'),
      repoRoot,
      windowId: windowRef.id,
    });
    if (initialWorkspace) {
      windowRef.webContents.send('beast:workspace-selected', initialWorkspace);
    }
  });
  await windowRef.loadFile(path.join(__dirname, 'renderer', 'index.html'));
  createMenu();
  ensureGateway();
}

ipcMain.handle('beast:status', async event => {
  const health = await gatewayHealth();
  const windowRef = BrowserWindow.fromWebContents(event.sender);
  return {
    gatewayUrl: health.url || gatewayUrl,
    repoRoot,
    health,
    processPid: gatewayProcess?.pid || null,
    lastGatewayCommand,
    gatewayLog,
    desktopVersion: DESKTOP_IDE_VERSION,
    rendererPath: path.join(__dirname, 'renderer', 'index.html'),
    windowId: windowRef?.id || null,
    windowCount: appWindows.size,
  };
});

ipcMain.handle('beast:choose-workspace', async event => {
  const windowRef = BrowserWindow.fromWebContents(event.sender) || mainWindow;
  const result = await dialog.showOpenDialog(windowRef, { properties: ['openDirectory'] });
  return result.canceled ? '' : result.filePaths[0];
});

ipcMain.handle('beast:restart-gateway', async () => {
  localIdeMode = false;
  localIdeReason = '';
  gatewayStartupPromise = null;
  if (gatewayProcess) {
    gatewayProcess.kill('SIGTERM');
    gatewayProcess = null;
  }
  return ensureGateway();
});

ipcMain.handle('beast:open-gateway', async () => {
  await shell.openExternal(gatewayUrl);
  return { ok: true, gatewayUrl };
});

ipcMain.handle('beast:list-files', async (_event, rootPath, limit) => {
  return workspaceFileCandidates(rootPath || repoRoot, Math.max(1, Math.min(Number(limit || 400), 2000)));
});

ipcMain.handle('beast:read-file', async (_event, rootPath, relPath, maxChars) => {
  return readWorkspaceFile(rootPath || repoRoot, relPath, Math.max(1, Math.min(Number(maxChars || 200000), 1000000)));
});

ipcMain.handle('beast:file-operation', async (_event, rootPath, operation) => {
  return mutateWorkspaceFile(rootPath || repoRoot, operation || {});
});

ipcMain.handle('beast:open-workspace-window', async (_event, workspace) => {
  const target = path.resolve(workspace || repoRoot);
  if (!fs.existsSync(target)) return { ok: false, error: 'workspace path does not exist', workspace: target };
  await createWindow({ initialWorkspace: target });
  return { ok: true, workspace: target };
});

ipcMain.handle('beast:release-readiness', async (_event, rootPath) => {
  return localReleaseReadiness(rootPath || repoRoot);
});

ipcMain.handle('beast:tooling-snapshot', async (_event, rootPath, activeFile) => {
  return localToolingSnapshot(rootPath || repoRoot, activeFile || '');
});

app.whenReady().then(createWindow);
app.on('window-all-closed', () => {
  if (gatewayProcess) gatewayProcess.kill('SIGTERM');
  if (process.platform !== 'darwin') app.quit();
});
app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
