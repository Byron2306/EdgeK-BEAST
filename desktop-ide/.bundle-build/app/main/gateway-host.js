'use strict';

const fs = require('fs');
const http = require('http');
const net = require('net');
const path = require('path');
const { spawn } = require('child_process');
let yaml = null;
try { yaml = require('js-yaml'); } catch (_) {}
const { GatewayEventStreamHost } = require('./gateway-event-stream-host');

function readServiceRegistry(root) {
  const text = fs.readFileSync(path.join(root, '.byron', 'services.yaml'), 'utf8');
  if (yaml) return yaml.load(text) || {};
  const services = {};
  let current = '';
  for (const rawLine of text.split(/\r?\n/)) {
    const service = rawLine.match(/^  ([A-Za-z0-9_-]+):\s*$/);
    if (service) { current = service[1]; services[current] = services[current] || {}; continue; }
    const field = rawLine.match(/^    ([A-Za-z0-9_-]+):\s*["']?([^"'#]+)["']?\s*$/);
    if (current && field) services[current][field[1]] = field[2].trim();
  }
  return { services };
}

function serviceRegistryGateway(root) {
  try {
    const config = readServiceRegistry(root);
    const upstream = config?.services?.beast?.upstream;
    if (!/^(?:127\.0\.0\.1|\[::1\]):\d+$/.test(String(upstream || ''))) throw new Error('invalid BEAST upstream');
    return `http://${upstream}`;
  } catch (_) {
    return 'http://127.0.0.1:8101';
  }
}

function serviceRegistryPort(root, serviceName, fallback) {
  try {
    const config = readServiceRegistry(root);
    const value = Number(config?.services?.[serviceName]?.port);
    return Number.isInteger(value) && value > 0 && value <= 65535 ? value : fallback;
  } catch (_) {
    return fallback;
  }
}

function createGatewayHost({ repoRoot, initialGatewayUrl = '', resolveBeastPython, getActiveWorkspaceRoot, getAppWindows = () => [] }) {
  const configuredGatewayUrl = serviceRegistryGateway(repoRoot);
  let gatewayUrl = initialGatewayUrl || configuredGatewayUrl;
  let gatewayProcess = null;
  let gatewayStartupPromise = null;
  let lastGatewayCommand = '';
  let gatewayLog = [];
  let gatewayStartedAt = 0;
  let localIdeMode = false;
  let localIdeReason = '';
  let lastGatewayRequestRecoveryAt = 0;

  function appendLog(line) {
    const record = `[${new Date().toISOString()}] ${String(line || '').trim()}`;
    gatewayLog.push(record);
    gatewayLog = gatewayLog.slice(-500);
    try {
      const logDir = path.join(repoRoot, '.beast', 'logs');
      fs.mkdirSync(logDir, { recursive: true });
      fs.appendFileSync(path.join(logDir, 'desktop-gateway.log'), `${record}\n`, { encoding: 'utf8', mode: 0o600 });
    } catch (_) {}
    for (const windowRef of getAppWindows()) {
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

async function ensureGatewayRequestTarget(payload = {}) {
  const method = String(payload.method || 'GET').toUpperCase();
  const route = String(payload.path || payload.url || '/');
  const forceProbe = method !== 'GET' || /\/edgek\/ide\/worktree-mission\//.test(route);
  const now = Date.now();
  if (!forceProbe && now - lastGatewayRequestRecoveryAt < 5000) return;
  lastGatewayRequestRecoveryAt = now;
  const health = await gatewayHealth(gatewayUrl, forceProbe ? 1600 : 1000);
  if (health.ok && health.capabilities?.ok) return;
  appendLog(`active gateway ${gatewayUrl} failed preflight before ${method} ${route}; searching for a compatible desktop gateway`);
  const requestedPort = Number(new URL(gatewayUrl).port || 8101);
  const compatibleGateway = await findCompatibleGateway(requestedPort);
  if (compatibleGateway) {
    gatewayUrl = compatibleGateway.url;
    appendLog(`gateway request recovered compatible BEAST gateway at ${gatewayUrl}`);
    for (const windowRef of getAppWindows()) if (!windowRef.isDestroyed()) windowRef.webContents.send('beast:refresh');
    return;
  }
  if (method !== 'GET') {
    await ensureGateway();
  }
}

async function gatewayRequest(payload = {}) {
  await ensureGatewayRequestTarget(payload);
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
  const knownPorts = [];
  const rememberPort = value => {
    const port = Number(value);
    if (Number.isInteger(port) && port > 0 && port <= 65535) knownPorts.push(port);
  };
  rememberPort(preferred);
  rememberPort(8101);
  try { rememberPort(new URL(configuredGatewayUrl).port || 8101); } catch (_) {}
  try { rememberPort(new URL(serviceRegistryGateway(repoRoot)).port || 8101); } catch (_) {}
  const ports = [...new Set([...knownPorts, ...Array.from({ length: 6 }, (_item, index) => preferred + index)])];
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
  const childEnv = { ...process.env, BEAST_DESKTOP_MANAGED: '1', BEAST_ACTIVE_WORKSPACE: getActiveWorkspaceRoot() || repoRoot, BEAST_WORKSPACE: getActiveWorkspaceRoot() || repoRoot };
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
    for (const windowRef of getAppWindows()) if (!windowRef.isDestroyed()) windowRef.webContents.send('beast:refresh');
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
  appendLog(`active workspace: ${getActiveWorkspaceRoot() || repoRoot}`);
  // The command parser reads BEAST_SOCKET_MODE from its environment.  Strip a
  // Guardian setting inherited from the shell: it belongs to the externally
  // managed listener, while this child is deliberately the direct HTTP API
  // sibling selected above.
  const childEnv = {
    ...process.env,
    PYTHONUNBUFFERED: '1',
    BEAST_DESKTOP_MANAGED: '1',
    BEAST_ACTIVE_WORKSPACE: getActiveWorkspaceRoot() || repoRoot,
    BEAST_WORKSPACE: getActiveWorkspaceRoot() || repoRoot,
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
    for (const windowRef of getAppWindows()) if (!windowRef.isDestroyed()) windowRef.webContents.send('beast:refresh');
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
      for (const windowRef of getAppWindows()) if (!windowRef.isDestroyed()) windowRef.webContents.send('beast:refresh');
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
        for (const windowRef of getAppWindows()) if (!windowRef.isDestroyed()) windowRef.webContents.send('beast:refresh');
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


  async function restartGateway() {
    localIdeMode = false;
    localIdeReason = '';
    gatewayStartupPromise = null;
    if (gatewayProcess) {
      const previousGateway = gatewayProcess;
      gatewayProcess = null;
      const stopped = await stopManagedGateway(previousGateway);
      if (!stopped) throw new Error('Managed BEAST gateway did not stop; restart was not attempted to avoid attaching to a stale process.');
    }
    return ensureGateway();
  }

  async function recoverStatusHealth() {
    // Keep a managed compatible port instead of resetting every status probe to the Guardian registry listener.
    let health = await gatewayHealth();
    if (!health.ok || !health.capabilities?.ok) {
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
    return health;
  }

  function getSnapshot() {
    return {
      url: gatewayUrl,
      configuredUrl: configuredGatewayUrl,
      processPid: gatewayProcess?.pid || null,
      process: gatewayProcess,
      lastGatewayCommand,
      log: [...gatewayLog],
      startedAt: gatewayStartedAt,
      localMode: localIdeMode,
      localReason: localIdeReason,
    };
  }

  function shutdown() {
    if (gatewayProcess) gatewayProcess.kill('SIGTERM');
    gatewayEventStreamHost.stopAll();
  }

  return {
    appendLog,
    gatewayRequest,
    gatewayEventStreamHost,
    runtimeStackHealth,
    gatewayHealth,
    gatewayCapabilityHealth,
    gatewayTcpListening,
    findCompatibleGateway,
    ensureGateway,
    resetRuntimeStack,
    restartGateway,
    recoverStatusHealth,
    getGatewayUrl: () => gatewayUrl,
    getSnapshot,
    shutdown,
    stopManagedGateway,
  };
}

module.exports = { createGatewayHost, serviceRegistryGateway, serviceRegistryPort };
