const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');
const { createExecutionTargetHost } = require('../main/execution-target-host');
const { createTaskTestHost } = require('../main/task-test-host');
const { IdeCompatibilityHost } = require('../ide-compatibility-host');
const { runVerification: runRemoteDebugRecoveryVerification } = require('./verify-remote-debug-recovery');
const { verifyRemoteExtensionRouting } = require('./verify-remote-extension-parity');

const root = path.resolve(__dirname, '..');
const repo = path.resolve(root, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const rows = [];
const record = (name, status, detail = '') => rows.push({ name, status, detail });
const has = command => spawnSync(process.platform === 'win32' ? 'where' : 'which', [command], { encoding: 'utf8', timeout: 3000 }).status === 0;

function check(name, condition, detail = '') {
  record(name, condition ? 'passed' : 'failed', detail);
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd || repo,
    encoding: 'utf8',
    timeout: options.timeout || 20000,
    maxBuffer: 1024 * 1024,
  });
  return {
    ok: result.status === 0,
    status: result.status,
    stdout: String(result.stdout || ''),
    stderr: String(result.stderr || ''),
    error: result.error ? String(result.error.message || result.error) : '',
  };
}

const mainEntry = read('main.js');
const mainModules = fs.readdirSync(path.join(root, 'main')).filter(name => name.endsWith('.js')).sort().map(name => read(`main/${name}`)).join('\n');
const main = `${mainEntry}\n${mainModules}`;
const preload = read('preload.js');
const runtime = read('renderer/js/beast-ide-runtime.js');
const compatibility = read('renderer/js/beast-ide-compatibility.js');
const compatibilityPage = read('renderer/js/pages/beast-compatibility-page.js');
const ideServices = read('main/ide-services-host.js');
const workspaceIndex = read('main/workspace-index-host.js');
const ideContext = fs.readFileSync(path.join(repo, 'app', 'routes', 'ide_context.py'), 'utf8');
const agentSessionsRoute = fs.readFileSync(path.join(repo, 'app', 'routes', 'ide_routes', 'agent_sessions.py'), 'utf8');
const agentRunStreamRoute = fs.readFileSync(path.join(repo, 'app', 'routes', 'ide_routes', 'agent_run_stream.py'), 'utf8');
const agentSessionStore = fs.readFileSync(path.join(repo, 'app', 'kernel', 'workspaces', 'agent_session_store.py'), 'utf8');
const plannerRuntime = fs.readFileSync(path.join(repo, 'app', 'kernel', 'agents', 'planner_runtime.py'), 'utf8');
const verificationPlanner = fs.readFileSync(path.join(repo, 'app', 'kernel', 'agents', 'verification_planner.py'), 'utf8');
const plannerProvider = fs.readFileSync(path.join(repo, 'app', 'kernel', 'agents', 'planner_provider.py'), 'utf8');
const aiModuleNames = ['agent-client.js', 'agent-store.js', 'agent-events.js', 'agent-view.js', 'context-picker.js', 'context-manifest.js', 'approval-cards.js', 'tool-cards.js', 'plan-view.js', 'verification-view.js', 'sourceplan-handoff.js', 'conversation-renderer.js', 'mode-controller.js', 'budget-view.js'];
const aiCoding = [read('renderer/js/beast-ai-coding.js'), ...aiModuleNames.map(name => read(`renderer/js/ai/${name}`))].join('\n');
const host = read('ide-compatibility-host.js');

check('shared execution target desktop IPC exists', [
  'beast:execution-target-list',
  'beast:execution-target-get',
  'beast:execution-target-set',
  'beast:execution-target-soak',
  'beast:execution-target-soak-summary',
  'activeExecutionTarget',
  'soakExecutionTarget',
  'targetSoakSummary',
  'runOnExecutionTarget',
  'targetSessions',
].every(value => main.includes(value)) && ['listExecutionTargets:', 'getExecutionTarget:', 'setExecutionTarget:'].every(value => preload.includes(value)));

check('Explorer/runtime store exposes selected execution target', [
  'executionTarget',
  'setExecutionTarget',
  'listExecutionTargets',
  'beast.v2.workspace.execution-target',
].every(value => read('renderer/js/beast-desktop-bridge.js').includes(value) || read('renderer/js/beast-store.js').includes(value)));

check('execution target layer tracks durable target sessions', [
  'createTargetSessionRegistry',
  'sessionId',
  'reconnectCount',
  'lastHealthyAt',
  'targetSessions',
  'targetSoakHistory',
  'targetSoakSummary',
  'sessions:targetSessionRegistry.list()',
].every(value => main.includes(value)));

check('execution target soak is exposed through preload/runtime surfaces', [
  'soakExecutionTarget:',
  'executionTargetSoakSummary:',
].every(value => preload.includes(value)) && [
  'async function soakExecutionTarget',
  'async function refreshExecutionTargetSoaks',
  'soakStatus',
  'lastSoak',
].every(value => runtime.includes(value)));

check('tasks and tests execute through the shared target layer', [
  'runWorkspaceTask(rootPath,payload)',
  'runWorkspaceTest(rootPath,payload)',
  'runOnExecutionTarget(selectedTarget',
  'executionTarget',
].every(value => main.includes(value)));

check('remote workspace watchers invalidate through execution targets', [
  'workspaceTargetStartWatch',
  'workspaceTargetStopWatch',
  'target_polling_watch',
  'targetWatchDiff',
  'beast:workspace-watch-event',
  'sessionId:watcher.sessionId',
].every(value => main.includes(value)));

check('LSP and DAP pass active execution target into protocol host', [
  "startIdeProtocol({kind:'lsp'",
  "startIdeProtocol({kind:'dap'",
  'target:executionTarget()',
].every(value => runtime.includes(value) || compatibility.includes(value)));

check('SSH and container protocol transports are real stdio relays', [
  'ssh-stdio',
  'docker-exec-stdio',
  "args:['exec','-i'",
  "StrictHostKeyChecking=yes",
  'debugpy.adapter',
].every(value => host.includes(value)));

check('Dev Containers are first-class workbench actions', [
  'attachDevContainer',
  'restartDevContainer',
  'rebuildDevContainer',
  'devContainerLogs',
  'runDevContainerTerminal',
  'devContainerPorts',
  'beast:dev-container-open-port',
  'data-runtime-action="container-start"',
  'data-runtime-action="container-rebuild"',
  'data-runtime-action="container-restart"',
  'data-runtime-action="container-terminal-run"',
  'data-runtime-container-port',
].every(value => main.includes(value) || preload.includes(value) || runtime.includes(value) || compatibilityPage.includes(value)));

check('Dev Container Compose configurations are managed through the target layer', [
  'dockerComposeFile',
  'composeFiles',
  'function composeArgs',
  "composeArgs(state,'up'",
  "composeArgs(state,'stop'",
  "composeArgs(state,'logs'",
].every(value => main.includes(value)));

check('extensions activate through the selected execution target', [
  'launch(root,target',
  'workspaceRoot(root,target',
  "target.kind==='ssh'",
  "target.kind==='container'",
  'remote-declarative-manifests',
  'this.session.target',
  'payload?.target || executionTargetHost.getActiveExecutionTarget()',
  'deployWorkspaceExtensions',
  'runtimePreflight',
  'SSH extension runtime requires Node.js',
  'Container extension runtime requires Node.js',
  'grantForTarget',
  "'.beast','extensions'",
  'beast:extension-host-deploy',
].every(value => main.includes(value)) && ['beast-code-health', 'beast-crystal-lab', 'beast-remote-toolkit'].every(name => fs.existsSync(path.join(root, 'extensions', name))));

check('extension host exposes per-target lifecycle state', [
  'lifecycleStatus(target',
  'lifecycleFor(target',
  'extension-host-status',
  'refreshExtensionHostStatus',
  'lifecycleTargets',
  'deploy_complete',
  'discover_complete',
].every(value => main.includes(value) || preload.includes(value) || runtime.includes(value)));

check('target-aware IDE services snapshot unifies LSP/DAP/tests/SCM/extensions', [
  'beast_ide_services_snapshot',
  'remote-git-status',
  'sections.index.ok',
  'workspaceTestsForTarget',
  'lifecycleStatus(target',
  'services: sections',
  'score(sections)',
].every(value => ideServices.includes(value)) && [
  'beast:ide-services-snapshot',
  'createIdeServicesHost',
].every(value => main.includes(value)) && [
  'ideServicesSnapshot:',
].every(value => preload.includes(value)) && [
  'refreshIdeServicesSnapshot',
].every(value => runtime.includes(value)));

check('workspace index snapshots include target files, symbols, imports, tests, and Nim', [
  'beast_workspace_index_snapshot',
  'extractSymbols',
  "language === 'nim'",
  "['.nim', 'nim']",
  'target-remote-semantic-index',
  'workspaceTestsForTarget',
].every(value => workspaceIndex.includes(value)) && [
  'beast:workspace-index-snapshot',
  'createWorkspaceIndexHost',
].every(value => main.includes(value)) && [
  'workspaceIndexSnapshot:',
].every(value => preload.includes(value)) && [
  'refreshWorkspaceIndexSnapshot',
].every(value => runtime.includes(value)));

check('AI streaming keeps explicit context visible and bounded', [
  'MAX_CONTEXT_FILES',
  'normalizeContextFiles',
  'not locked by backend',
  'Context mismatch or read failure',
  "mode === 'ask' ? 6000 : 16000",
].every(value => aiCoding.includes(value)));

check('agentic validation preserves execution-target intent through session, compile, and verifier stages', [
  'execution_target',
  'execution_target_payload',
  '_normalize_execution_target',
  '_execution_target_validation_strategy',
  'isolated_remote_shadow',
  'isolated_container_shadow',
].every(value => ideContext.includes(value)) && [
  'execution_target=str(payload.get("execution_target") or "local")',
  'execution_target_payload=payload.get("execution_target_payload")',
].every(value => agentSessionsRoute.includes(value)) && [
  'execution_target = str(session.get("execution_target") or "local")',
  '"execution_target": execution_target',
  'execution_target_payload=execution_target_payload',
].every(value => agentRunStreamRoute.includes(value)) && [
  '"execution_target": str(execution_target or "local")',
  '"execution_target_payload": dict(execution_target_payload or {})',
].every(value => agentSessionStore.includes(value)));

check('planner verification selection is target-native and strategy-rich for remote targets', [
  '_target_runner_for',
  '_verification_strategy',
  '"target_execution": target.get("target_execution")',
  'target_native_remote',
  'python3',
].every(value => verificationPlanner.includes(value)) && [
  '"strategy": verifier_plan.get("strategy")',
  '"target_execution": verifier_plan.get("target_execution")',
].every(value => plannerRuntime.includes(value)));

check('provider scoring escalates hard remote repair failures toward stronger routes', [
  '_failure_pressure',
  'strong_route_recommended',
  'failure_pressure_escalation',
  'remote_failure',
].every(value => plannerProvider.includes(value)));

check('Pair Programmer has a focused local-Qwen recovery profile', [
  'options.focused',
  'focused one-file recovery profile',
  'Recovery mode: make one exact, reviewable edit',
  'maxTokens:options.maxTokens||(focused?768:undefined)',
].every(value => aiCoding.includes(value)));

const localRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'beast-target-local-'));
fs.writeFileSync(path.join(localRoot, 'sample.js'), 'const answer = 42;\n', 'utf8');
const discovery = new IdeCompatibilityHost(repo).discover(localRoot);
check('local target discovery returns LSP/DAP/notebook/remote groups', discovery.ok && ['languages', 'debug', 'notebooks', 'remote'].every(key => Array.isArray(discovery[key])), JSON.stringify(discovery.summary));
const rendererSyntaxFiles = ['renderer/js/beast-ai-coding.js', ...aiModuleNames.map(name => `renderer/js/ai/${name}`)];
const rendererSyntax = rendererSyntaxFiles.map(file => ({ file, result:run('node', ['--check', path.join(root, file)], { cwd:localRoot }) }));
const rendererSyntaxFailures = rendererSyntax.filter(item => !item.result.ok);
check('local target renderer syntax acceptance', rendererSyntaxFailures.length === 0, rendererSyntaxFailures.map(item => `${item.file}: ${item.result.stderr || item.result.error}`).join('\n'));

const sshHost = process.env.BEAST_PARITY_SSH_HOST || '';
if (sshHost) {
  const ssh = run('ssh', ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=7', '-o', 'StrictHostKeyChecking=yes', sshHost, 'printf BEAST_SSH_PARITY'], { timeout: 15000 });
  check('SSH target live handshake', ssh.ok && ssh.stdout.includes('BEAST_SSH_PARITY'), ssh.stderr || ssh.error);
} else {
  record('SSH target live handshake', 'skipped', 'Set BEAST_PARITY_SSH_HOST to run a strict-host-key SSH acceptance handshake.');
}

const containerImage = process.env.BEAST_PARITY_CONTAINER_IMAGE || '';
if (containerImage) {
  const docker = run('docker', ['run', '--rm', containerImage, 'sh', '-lc', 'printf BEAST_CONTAINER_PARITY'], { timeout: 120000 });
  check('container target live handshake', docker.ok && docker.stdout.includes('BEAST_CONTAINER_PARITY'), docker.stderr || docker.error);
} else if (has('docker')) {
  record('container target live handshake', 'skipped', 'Set BEAST_PARITY_CONTAINER_IMAGE to run a Docker acceptance container without implicit image pulls.');
} else {
  record('container target live handshake', 'skipped', 'Docker CLI is not installed or not on PATH.');
}

if (containerImage && has('docker')) {
  const composeRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'beast-compose-target-'));
  const composeFile = path.join(composeRoot, 'docker-compose.yml');
  const project = `beast-parity-${process.pid}-${Date.now()}`.replace(/[^a-z0-9_-]/gi, '').toLowerCase();
  fs.writeFileSync(composeFile, `services:\n  workspace:\n    image: ${JSON.stringify(containerImage)}\n    working_dir: /workspace\n    ports:\n      - \"127.0.0.1::8080\"\n    command: [\"sh\", \"-lc\", \"printf BEAST_COMPOSE_PARITY; exec sleep infinity\"]\n`, 'utf8');
  const compose = args => run('docker', ['compose', '-p', project, '-f', composeFile, ...args], { cwd: composeRoot, timeout: 120000 });
  let up;
  let services;
  let execute;
  let logs;
  let port;
  try {
    up = compose(['up', '-d']);
    services = up.ok ? compose(['ps', '--status', 'running', '--services']) : { ok:false, stderr:'Compose did not start.' };
    execute = services.ok ? compose(['exec', '-T', 'workspace', 'sh', '-lc', 'printf BEAST_COMPOSE_EXEC']) : { ok:false, stderr:'Compose service is not running.' };
    logs = services.ok ? compose(['logs', '--tail', '20', 'workspace']) : { ok:false, stderr:'Compose service is not running.' };
    port = services.ok ? compose(['port', 'workspace', '8080']) : { ok:false, stderr:'Compose service is not running.' };
    const composeOk=Boolean(up?.ok) && services.stdout.split(/\r?\n/).includes('workspace') && `${execute.stdout}${execute.stderr}`.includes('BEAST_COMPOSE_EXEC') && logs.ok && port.ok && /127\.0\.0\.1:\d+/.test(`${port.stdout}${port.stderr}`);
    check('Dev Container Compose lifecycle live acceptance', composeOk, composeOk?'':JSON.stringify({up,services,execute,logs,port}));
  } finally {
    compose(['down', '--volumes', '--remove-orphans']);
    fs.rmSync(composeRoot, { recursive:true, force:true });
  }
} else {
  record('Dev Container Compose lifecycle live acceptance', 'skipped', 'Set BEAST_PARITY_CONTAINER_IMAGE to run Compose without implicit image pulls.');
}

function verifyLocalTargetSoakContract() {
  const soakRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'beast-target-soak-'));
  try {
    fs.writeFileSync(path.join(soakRoot, 'package.json'), JSON.stringify({ name: 'beast-target-soak', version: '1.0.0' }), 'utf8');
    const boundedCalls = [];
    const targetHost = createExecutionTargetHost({
      repoRoot: soakRoot,
      boundedProcess: async (command, args, options = {}) => {
        boundedCalls.push({ command, args, options });
        if (command === 'sh' && Array.isArray(args) && args[0] === '-lc') {
          return { ok: true, returncode: 0, stdout: `${soakRoot}\n${soakRoot}\nBEAST_TARGET_SOAK_OK`, stderr: '', error: '' };
        }
        const result = run(command, args, { cwd: options.cwd || soakRoot, timeout: options.timeoutMs || 30000 });
        return { ok: result.ok, returncode: result.status, stdout: result.stdout, stderr: result.stderr, error: result.error };
      },
      gitReceipt: () => ({ id: 'TEST-RECEIPT' }),
      readWorkspaceFile: () => ({ ok: false }),
      safeWorkspacePath: (_rootPath, rel) => ({ ok: true, target: path.join(soakRoot, rel) }),
      taskCwd: rootPath => rootPath,
      workspaceFileCandidates: rootPath => {
        const file = path.join(rootPath, 'package.json');
        const stat = fs.statSync(file);
        return [{ path: 'package.json', size: stat.size, mtimeMs: stat.mtimeMs }];
      },
      getActiveWorkspaceRoot: () => soakRoot,
    });
    return targetHost.soakExecutionTarget(soakRoot, { target: { kind: 'local', root: soakRoot }, iterations: 3, interruptEvery: 2 }).then(result => {
      const summary = targetHost.targetSoakSummary();
      check('local execution target soak produces receipt/history rows', result.ok && result.iterations === 3 && result.rows.length === 3 && result.rows.some(row => row.interrupted === true) && /^SOAK-/.test(result.receipt?.id || '') && summary.counts.soaks >= 1 && summary.soaks[0]?.receipt?.id === result.receipt?.id, JSON.stringify({ result, summary, boundedCalls: boundedCalls.length }));
    });
  } finally {
    fs.rmSync(soakRoot, { recursive: true, force: true });
  }
}

async function verifyRemoteAgenticApplyContract() {
  const contractRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'beast-agentic-target-'));
  const remoteRoot = path.posix.join('/tmp', path.basename(contractRoot));
  const containerId = 'beast-agentic-container';
  const sshHostName = 'beast-parity-host';
  const execLocal = (command, args, options = {}) => {
    const result = run(command, args, { cwd: options.cwd || contractRoot, timeout: options.timeoutMs || 30000 });
    return { ok: result.ok, returncode: result.status, stdout: result.stdout, stderr: result.stderr, error: result.error };
  };
  const readWorkspaceFile = (rootPath, relative, maxChars = 1000000) => {
    const target = path.resolve(rootPath, relative);
    const workspace = path.resolve(rootPath);
    if (!(target === workspace || target.startsWith(`${workspace}${path.sep}`))) return { ok: false, error: 'unsafe path', path: relative };
    const content = fs.readFileSync(target, 'utf8').slice(0, maxChars);
    const digest = require('crypto').createHash('sha256').update(content).digest('hex');
    return { ok: true, path: relative, content, digest: `sha256:${digest}`, truncated: content.length >= maxChars };
  };
  const safeWorkspacePath = (rootPath, relative) => {
    const workspace = path.resolve(rootPath);
    const target = path.resolve(workspace, relative);
    return target === workspace || target.startsWith(`${workspace}${path.sep}`)
      ? { ok: true, target }
      : { ok: false, error: 'unsafe path' };
  };
  const workspaceFileCandidates = (rootPath, limit = 5000) => {
    const files = [];
    const queue = ['.'];
    while (queue.length && files.length < limit) {
      const next = queue.shift();
      const base = path.resolve(rootPath, next);
      for (const entry of fs.readdirSync(base, { withFileTypes: true })) {
        if (entry.name === '.git' || entry.name === 'node_modules' || entry.name === '.beast') continue;
        const rel = next === '.' ? entry.name : path.join(next, entry.name);
        const target = path.resolve(rootPath, rel);
        if (entry.isDirectory()) queue.push(rel);
        else if (entry.isFile()) {
          const stat = fs.statSync(target);
          files.push({ path: rel.replace(/\\/g, '/'), name: entry.name, size: stat.size, mtimeMs: stat.mtimeMs });
          if (files.length >= limit) break;
        }
      }
    }
    return files;
  };
  const taskCwd = (rootPath, value) => {
    const base = path.resolve(rootPath);
    const target = path.resolve(base, value || '.');
    return target === base || target.startsWith(`${base}${path.sep}`) ? target : '';
  };
  const gitReceipt = (_rootPath, action, relative) => ({ id: `RECEIPT-${action}-${String(relative).replace(/[^A-Za-z0-9]/g, '').slice(0, 12)}` });
  const remapRemoteCommand = command => command.split(remoteRoot).join(contractRoot);
  const boundedProcess = async (command, args, options = {}) => {
    if (command === 'ssh') {
      const remoteCommand = Array.isArray(args) ? args[args.length - 1] : '';
      return execLocal('sh', ['-lc', remapRemoteCommand(remoteCommand)], { cwd: contractRoot, timeoutMs: options.timeoutMs });
    }
    if (command === 'docker' && Array.isArray(args) && args[0] === 'ps') {
      return { ok: true, returncode: 0, stdout: `${containerId}\tbeast-agentic\tbeast:latest\tUp 5 minutes\n`, stderr: '', error: '' };
    }
    if (command === 'docker' && Array.isArray(args) && args[0] === 'port') {
      return { ok: true, returncode: 0, stdout: '8080/tcp -> 127.0.0.1:38080\n', stderr: '', error: '' };
    }
    if (command === 'docker' && Array.isArray(args) && args[0] === 'exec') {
      const workdirFlag = args.indexOf('-w');
      const cwd = workdirFlag >= 0 ? remapRemoteCommand(String(args[workdirFlag + 1] || contractRoot)) : contractRoot;
      const start = workdirFlag >= 0 ? workdirFlag + 3 : 2;
      const innerCommand = args[start];
      const innerArgs = args.slice(start + 1).map(value => remapRemoteCommand(String(value)));
      return execLocal(innerCommand, innerArgs, { cwd, timeoutMs: options.timeoutMs });
    }
    return execLocal(command, args, options);
  };

  try {
    fs.mkdirSync(path.join(contractRoot, 'src'), { recursive: true });
    fs.mkdirSync(path.join(contractRoot, '.vscode'), { recursive: true });
    fs.mkdirSync(path.join(contractRoot, '.devcontainer'), { recursive: true });
    fs.writeFileSync(path.join(contractRoot, 'src', 'remote-agent.js'), 'function remoteValue() {\n  return 1;\n}\nmodule.exports = { remoteValue };\n', 'utf8');
    fs.writeFileSync(path.join(contractRoot, 'src', 'container-agent.js'), 'function containerValue() {\n  return 10;\n}\nmodule.exports = { containerValue };\n', 'utf8');
    fs.writeFileSync(path.join(contractRoot, 'src', 'final-apply.js'), 'function finalValue() {\n  return 100;\n}\nmodule.exports = { finalValue };\n', 'utf8');
    fs.writeFileSync(path.join(contractRoot, 'verify.js'), `const fs=require('fs');\nconst path=process.argv[2];\nconst expected=process.argv[3];\nconst text=fs.readFileSync(path,'utf8');\nif(!text.includes(expected)){console.error(\`missing \${expected} in \${path}\`);process.exit(1);}\nconsole.log(\`verified \${path} -> \${expected}\`);\n`, 'utf8');
    fs.writeFileSync(path.join(contractRoot, '.vscode', 'tasks.json'), JSON.stringify({
      version: '2.0.0',
      tasks: [
        { label: 'verify-remote-agent', type: 'process', command: 'node', args: ['verify.js', 'src/remote-agent.js', 'return 2'] },
        { label: 'verify-container-agent', type: 'process', command: 'node', args: ['verify.js', 'src/container-agent.js', 'return 11'] },
      ],
    }, null, 2), 'utf8');
    fs.writeFileSync(path.join(contractRoot, '.devcontainer', 'devcontainer.json'), JSON.stringify({
      name: 'BEAST Agentic Contract',
      image: 'beast:latest',
      workspaceFolder: remoteRoot,
    }, null, 2), 'utf8');

    const executionTargetHost = createExecutionTargetHost({
      repoRoot: contractRoot,
      boundedProcess,
      gitReceipt,
      readWorkspaceFile,
      safeWorkspacePath,
      taskCwd,
      workspaceFileCandidates,
      getActiveWorkspaceRoot: () => contractRoot,
    });
    const taskTestHost = createTaskTestHost({
      repoRoot: contractRoot,
      workspaceFileCandidates,
      safeWorkspacePath,
      taskCwd,
      getTargetHost: () => executionTargetHost,
    });

    const sshProbe = await executionTargetHost.probeRemoteWorkspace({ host: sshHostName, path: remoteRoot });
    const sshTarget = { kind: 'ssh', host: sshHostName, remoteRoot };
    const sshBefore = await executionTargetHost.workspaceTargetReadFile(contractRoot, { target: sshTarget, path: 'src/remote-agent.js' });
    const sshWrite = await executionTargetHost.workspaceTargetWriteFile(contractRoot, {
      target: sshTarget,
      path: 'src/remote-agent.js',
      expectedDigest: sshBefore.digest,
      content: sshBefore.content.replace('return 1', 'return 2'),
    });
    const sshVerify = await taskTestHost.runWorkspaceTask(contractRoot, { id: 'verify-remote-agent', target: sshTarget });
    fs.writeFileSync(path.join(contractRoot, 'src', 'remote-agent.js'), 'function remoteValue() {\n  return 3;\n}\nmodule.exports = { remoteValue };\n', 'utf8');
    const sshConflict = await executionTargetHost.workspaceTargetWriteFile(contractRoot, {
      target: sshTarget,
      path: 'src/remote-agent.js',
      expectedDigest: sshBefore.digest,
      content: sshBefore.content.replace('return 1', 'return 4'),
    });
    const sshReconnect = await executionTargetHost.reconnectRemoteWorkspace();

    const attached = await executionTargetHost.attachDevContainer(contractRoot, containerId);
    const containerTarget = { kind: 'container', containerId, name: 'beast-agentic', workspaceFolder: remoteRoot, root: contractRoot };
    const containerBefore = await executionTargetHost.workspaceTargetReadFile(contractRoot, { target: containerTarget, path: 'src/container-agent.js' });
    const containerWrite = await executionTargetHost.workspaceTargetWriteFile(contractRoot, {
      target: containerTarget,
      path: 'src/container-agent.js',
      expectedDigest: containerBefore.digest,
      content: containerBefore.content.replace('return 10', 'return 11'),
    });
    const containerVerify = await taskTestHost.runWorkspaceTask(contractRoot, { id: 'verify-container-agent', target: containerTarget });

    const apply = run('python3', ['-c', `
import json
from app.cli.api import BeastApiClient
client = BeastApiClient("http://offline", workspace=${JSON.stringify(contractRoot)})
plan = {
  "plan_id": "agentic_target_apply_contract",
  "objective": "Governed final apply",
  "risk_level": "low",
  "files_allowed": ["src/final-apply.js"],
  "verification_commands": ["node verify.js src/final-apply.js return 101"],
  "operations": [{
    "op_id": "op-1",
    "op": "replace_exact",
    "path": "src/final-apply.js",
    "old": "return 100",
    "new": "return 101",
    "description": "Finalize governed merge"
  }]
}
preview = client.preview_patch_plan(plan)
verify = client.verify_patch_plan(plan)
saved = client.save_patch_plan(plan)
applied = client.apply_patch_plan(plan, approved=True)
print(json.dumps({
  "preview_ok": preview.ok,
  "verify_ok": verify.ok,
  "saved_ok": saved.ok,
  "apply_ok": applied.ok,
  "status": ((applied.data or {}).get("plan") or {}).get("status"),
  "verification_ok": ((applied.data or {}).get("verification") or {}).get("ok"),
  "evidence_path": bool(((applied.data or {}).get("evidence_packet") or {}).get("path")),
  "rollback_path": bool((applied.data or {}).get("rollback_path")),
  "applied": (applied.data or {}).get("applied") or []
}))
`], { cwd: repo, timeout: 120000 });
    let applyPayload = {};
    try { applyPayload = JSON.parse(apply.stdout || '{}'); } catch (_) {}
    const finalContent = fs.readFileSync(path.join(contractRoot, 'src', 'final-apply.js'), 'utf8');
    const taskHistory = taskTestHost.historySummary();
    const targetSessions = executionTargetHost.targetSessions();

    check(
      'remote target mutation and verify loop runs through SSH/container targets with governed final apply',
      sshProbe.ok &&
      sshWrite.ok &&
      sshVerify.ok &&
      sshConflict.conflict === true &&
      sshReconnect.ok &&
      attached.ok &&
      containerWrite.ok &&
      containerVerify.ok &&
      apply.ok &&
      applyPayload.preview_ok === true &&
      applyPayload.verify_ok === true &&
      applyPayload.saved_ok === true &&
      applyPayload.apply_ok === true &&
      applyPayload.status === 'applied_verified_crystallized' &&
      applyPayload.verification_ok === true &&
      applyPayload.evidence_path === true &&
      applyPayload.rollback_path === true &&
      Array.isArray(applyPayload.applied) &&
      applyPayload.applied.includes('src/final-apply.js') &&
      finalContent.includes('return 101') &&
      taskHistory.counts.tasks >= 2 &&
      targetSessions.some(item => item.kind === 'ssh') &&
      targetSessions.some(item => item.kind === 'container'),
      JSON.stringify({
        sshProbe: sshProbe.ok,
        sshWrite: sshWrite.ok,
        sshVerify: sshVerify.ok,
        sshConflict: sshConflict.conflict,
        sshReconnect: sshReconnect.ok,
        attached: attached.ok,
        containerWrite: containerWrite.ok,
        containerVerify: containerVerify.ok,
        applyOk: apply.ok,
        applyPayload,
        taskCounts: taskHistory.counts,
        targetSessions: targetSessions.map(item => ({ kind: item.kind, status: item.status, health: item.health })),
      }),
    );
  } finally {
    fs.rmSync(contractRoot, { recursive: true, force: true });
  }
}

function verifyPlannerRemoteRepairContract() {
  const code = `
import asyncio
import json
import tempfile
from pathlib import Path

import app.kernel.agents.worktree_tools as worktree_tools
from app.kernel.agents.tool_models import ToolExecutionContext

class FakeStore:
    def __init__(self, run):
        self.run = run
    def get_run(self, run_id):
        return self.run if run_id == self.run.get("run_id") else None

class FakeEngine:
    def __init__(self, run):
        self.store = FakeStore(run)
        self.events = []
        self.merges = []
    def merge_checkpoint(self, run_id, payload):
        checkpoint = dict(self.store.run.get("checkpoint") or {})
        checkpoint.update(payload or {})
        self.store.run["checkpoint"] = checkpoint
        self.merges.append({"run_id": run_id, "payload": payload})
    def emit(self, run_id, event_type, payload):
        self.events.append({"run_id": run_id, "event_type": event_type, "payload": payload})

async def main():
    temp_root = Path(tempfile.mkdtemp(prefix="beast-planner-remote-repair-"))
    run = {"run_id": "planner-remote-repair", "checkpoint": {"worktree_mutation_epoch": 3}}
    engine = FakeEngine(run)
    context = ToolExecutionContext(
        run_id="planner-remote-repair",
        workspace_root=str(temp_root),
        execution_target="ssh",
        execution_target_payload={"kind": "ssh", "host": "beast-host", "remoteRoot": "/workspace/project"},
        worktree_root="/workspace/project/.beast/agent-worktrees/planner-remote-repair",
        engine=engine,
    )

    async def fake_run_target_shell(_context, _script, *, timeout=20.0, output_limit=512000):
        return {"ok": False, "returncode": 2, "stdout": "pytest collected 1 item\\n", "stderr": "AssertionError: expected 2 actual 1\\n", "truncated": False}

    original = worktree_tools._run_target_shell
    worktree_tools._run_target_shell = fake_run_target_shell
    try:
        result = await worktree_tools._worktree_run_verification({"command": ["python", "-m", "pytest", "-q", "tests/test_demo.py"]}, context)
    finally:
        worktree_tools._run_target_shell = original

    checkpoint = run.get("checkpoint") or {}
    verification = checkpoint.get("verification") if isinstance(checkpoint.get("verification"), dict) else {}
    fail_event = next((event for event in engine.events if event.get("event_type") == "agent.verification.failed"), {})
    print(json.dumps({
        "ok": result.get("ok") is False,
        "target_execution": result.get("target_execution"),
        "execution_target": result.get("execution_target"),
        "transport": result.get("transport"),
        "verification_target_execution": verification.get("target_execution"),
        "verification_execution_target": verification.get("execution_target"),
        "event_target_execution": (fail_event.get("payload") or {}).get("target_execution"),
        "event_execution_target": (fail_event.get("payload") or {}).get("execution_target"),
        "event_command": (fail_event.get("payload") or {}).get("command"),
    }))

asyncio.run(main())
`;
  const result = run('python3', ['-c', code], { cwd: repo, timeout: 120000 });
  let payload = {};
  try { payload = JSON.parse((result.stdout || '').trim().split(/\r?\n/).at(-1) || '{}'); } catch (_) {}
  check(
    'planner repair loop preserves target execution evidence for failed remote verification',
    result.ok &&
    payload.ok === true &&
    payload.target_execution === 'remote_ssh' &&
    payload.execution_target === 'ssh' &&
    payload.transport === 'ssh' &&
    payload.verification_target_execution === 'remote_ssh' &&
    payload.verification_execution_target === 'ssh' &&
    payload.event_target_execution === 'remote_ssh' &&
    payload.event_execution_target === 'ssh' &&
    Array.isArray(payload.event_command) &&
    payload.event_command[0] === 'python',
    JSON.stringify({ result, payload }),
  );
}

function verifyPlannerTargetVerificationStrategy() {
  const code = `
import json
from app.kernel.agents.verification_planner import plan_verification

run = {
  "request": {
    "execution_target": "ssh",
    "execution_target_payload": {"kind": "ssh", "host": "beast-host", "remoteRoot": "/workspace/project"},
    "test_catalog": [{"id": "python:pytest", "framework": "pytest", "command": "python3 -m pytest", "label": "pytest"}],
  },
  "checkpoint": {
    "planner": {
      "observations": [
        {
          "tool_id": "worktree.replace_exact",
          "status": "completed",
          "result": {"path": "pkg/demo.py"},
        },
        {
          "tool_id": "workspace.index",
          "status": "completed",
          "result": {
            "beast_object_type": "beast_workspace_index_snapshot",
            "tests": ["tests/test_demo.py"],
            "files": [
              {"path": "pkg/demo.py"},
              {"path": "tests/test_demo.py"},
            ],
            "imports": [
              {"path": "tests/test_demo.py", "target": "pkg.demo", "kind": "import"},
            ],
          },
        },
      ]
    }
  }
}
plan = plan_verification(run)
print(json.dumps(plan))
`;
  const result = run('python3', ['-c', code], { cwd: repo, timeout: 120000 });
  let payload = {};
  try { payload = JSON.parse((result.stdout || '').trim().split(/\r?\n/).at(-1) || '{}'); } catch (_) {}
  check(
    'remote verification planner chooses target-native command and strategy',
    result.ok &&
    Array.isArray(payload.command) &&
    payload.command[0] === 'python3' &&
    payload.command[1] === '-m' &&
    payload.reason === 'related_pytest_from_workspace_index' &&
    payload.target_execution === 'remote_ssh' &&
    payload.execution_target?.kind === 'ssh' &&
    payload.strategy?.mode === 'target_native_remote' &&
    payload.strategy?.family === 'python_pytest',
    JSON.stringify({ result, payload }),
  );
}

function verifyPlannerTargetVerificationFallbacks() {
  const retryCode = `
import json
from app.kernel.agents.verification_planner import plan_verification
run = {
  "request": {
    "execution_target": "ssh",
    "execution_target_payload": {"kind": "ssh", "host": "beast-host", "remoteRoot": "/workspace/project"},
  },
  "checkpoint": {
    "planner": {
      "observations": [
        {"tool_id": "worktree.replace_exact", "status": "completed", "result": {"path": "pkg/demo.py"}}
      ],
      "verification_failures": [
        {
          "repair_cycle": 1,
          "command": ["python3", "-m", "pytest", "-q", "tests/test_demo.py"],
          "target_execution": "remote_ssh",
          "analysis": {"failure_class": "environment_issue", "retryable_without_code_change": True}
        }
      ]
    }
  }
}
print(json.dumps(plan_verification(run)))
`;
  const degradeCode = `
import json
from app.kernel.agents.verification_planner import plan_verification
run = {
  "request": {
    "execution_target": "ssh",
    "execution_target_payload": {"kind": "ssh", "host": "beast-host", "remoteRoot": "/workspace/project"},
  },
  "checkpoint": {
    "planner": {
      "observations": [
        {"tool_id": "worktree.replace_exact", "status": "completed", "result": {"path": "pkg/demo.py"}}
      ],
      "verification_failures": [
        {
          "repair_cycle": 2,
          "command": ["python3", "-m", "pytest", "-q", "tests/test_demo.py"],
          "target_execution": "remote_ssh",
          "analysis": {"failure_class": "environment_issue", "retryable_without_code_change": True}
        }
      ]
    }
  }
}
print(json.dumps(plan_verification(run)))
`;
  const retryResult = run('python3', ['-c', retryCode], { cwd: repo, timeout: 120000 });
  const degradeResult = run('python3', ['-c', degradeCode], { cwd: repo, timeout: 120000 });
  let retryPayload = {};
  let degradePayload = {};
  try { retryPayload = JSON.parse((retryResult.stdout || '').trim().split(/\r?\n/).at(-1) || '{}'); } catch (_) {}
  try { degradePayload = JSON.parse((degradeResult.stdout || '').trim().split(/\r?\n/).at(-1) || '{}'); } catch (_) {}
  check(
    'remote verification planner retries same target verifier once for retryable failures',
    retryResult.ok &&
    retryPayload.reason === 'retry_same_target_verifier_once' &&
    Array.isArray(retryPayload.command) &&
    retryPayload.command[0] === 'python3' &&
    retryPayload.strategy?.mode === 'target_native_remote' &&
    retryPayload.strategy?.family === 'retry_same_command' &&
    retryPayload.prior_failure?.failure_class === 'environment_issue',
    JSON.stringify({ retryResult, retryPayload }),
  );
  check(
    'remote verification planner degrades to target-native syntax fallback after repeated retryable failures',
    degradeResult.ok &&
    degradePayload.reason === 'degraded_target_fallback_after_retryable_verifier_failure' &&
    Array.isArray(degradePayload.command) &&
    degradePayload.command[0] === 'python3' &&
    degradePayload.command[1] === '-m' &&
    degradePayload.command[2] === 'py_compile' &&
    degradePayload.strategy?.mode === 'target_native_remote' &&
    degradePayload.strategy?.family === 'python_compile' &&
    degradePayload.prior_failure?.failure_class === 'environment_issue',
    JSON.stringify({ degradeResult, degradePayload }),
  );
}

function verifyProviderFailurePressureEscalation() {
  const code = `
import json
from app.kernel.agents.planner_provider import CapabilityRoute, CapabilityScoredPlannerProvider, ScriptedPlannerProvider

provider = CapabilityScoredPlannerProvider(
    [
        CapabilityRoute(name="weak_local", provider=ScriptedPlannerProvider([{"decision_type":"blocked","arguments":{},"blocker":"x"}]), capability_score=0.35, cost_score=0.95),
        CapabilityRoute(name="strong_remote", provider=ScriptedPlannerProvider([{"decision_type":"blocked","arguments":{},"blocker":"x"}]), capability_score=0.92, cost_score=0.35),
    ],
    hard_edit_threshold=0.68,
)
run = {
    "mode": "agent",
    "objective": "repair a hard patch in a remote monorepo",
    "request": {"context_files": ["a.py", "b.py", "c.py", "d.py"]},
    "checkpoint": {
        "planner": {
            "repair_cycles": 2,
            "verification_failures": [{
                "repair_cycle": 2,
                "execution_target": "ssh",
                "target_execution": "remote_ssh",
                "analysis": {
                    "failure_class": "logic_regression",
                    "retryable_without_code_change": False,
                    "escalation_hint": "stronger_model_recommended",
                },
            }],
        }
    }
}
ranked = provider._ranked_routes(run)
print(json.dumps({
    "first": ranked[0][1].name,
    "second": ranked[1][1].name,
    "failure_pressure": provider._failure_pressure(run),
}))
`;
  const result = run('python3', ['-c', code], { cwd: repo, timeout: 120000 });
  let payload = {};
  try { payload = JSON.parse((result.stdout || '').trim().split(/\r?\n/).at(-1) || '{}'); } catch (_) {}
  check(
    'capability scorer prefers stronger route after hard remote repair failure',
    result.ok &&
    payload.first === 'strong_remote' &&
    payload.second === 'weak_local' &&
    payload.failure_pressure?.strong_route_recommended === true &&
    payload.failure_pressure?.remote_failure === true &&
    payload.failure_pressure?.failure_class === 'logic_regression',
    JSON.stringify({ result, payload }),
  );
}

async function runParitySuite() {
  await verifyLocalTargetSoakContract();
  await verifyRemoteAgenticApplyContract();
  verifyPlannerRemoteRepairContract();
  verifyPlannerTargetVerificationStrategy();
  verifyPlannerTargetVerificationFallbacks();
  verifyProviderFailurePressureEscalation();
  const remoteDebugRecovery = await runRemoteDebugRecoveryVerification();
  check('remote debug interruption recovery auto-resumes governed sessions', remoteDebugRecovery.ok, JSON.stringify(remoteDebugRecovery.failed || []));
  const remoteExtensionParity = await verifyRemoteExtensionRouting();
  check('remote extension deploy and activation route inside SSH/container targets', remoteExtensionParity.ok, JSON.stringify(remoteExtensionParity.failed || []));
  const failed = rows.filter(row => row.status === 'failed');
  const result={
    ok: failed.length === 0,
    checks: rows.length,
    passed: rows.filter(row => row.status === 'passed').length,
    skipped: rows.filter(row => row.status === 'skipped').length,
    failed,
    rows,
  };
  const reportPath=path.resolve(String(process.env.BEAST_TARGET_REPORT_PATH||path.join(root,'..','build','EXECUTION_TARGET_PARITY.json')));
  fs.mkdirSync(path.dirname(reportPath),{recursive:true});
  fs.writeFileSync(reportPath,`${JSON.stringify(result,null,2)}\n`,'utf8');
  console.log(JSON.stringify({ ok: result.ok, checks: result.checks, passed: result.passed, skipped: result.skipped, failed: result.failed }, null, 2));
  process.exit(failed.length ? 1 : 0);
}

runParitySuite().catch(error => {
  console.error(error);
  process.exit(1);
});
