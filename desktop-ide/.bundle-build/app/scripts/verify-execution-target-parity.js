const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');
const { IdeCompatibilityHost } = require('../ide-compatibility-host');

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
const aiModuleNames = ['agent-client.js', 'agent-store.js', 'agent-events.js', 'agent-view.js', 'context-picker.js', 'context-manifest.js', 'approval-cards.js', 'tool-cards.js', 'plan-view.js', 'verification-view.js', 'sourceplan-handoff.js', 'conversation-renderer.js', 'mode-controller.js', 'budget-view.js'];
const aiCoding = [read('renderer/js/beast-ai-coding.js'), ...aiModuleNames.map(name => read(`renderer/js/ai/${name}`))].join('\n');
const host = read('ide-compatibility-host.js');

check('shared execution target desktop IPC exists', [
  'beast:execution-target-list',
  'beast:execution-target-get',
  'beast:execution-target-set',
  'activeExecutionTarget',
  'runOnExecutionTarget',
].every(value => main.includes(value)) && ['listExecutionTargets:', 'getExecutionTarget:', 'setExecutionTarget:'].every(value => preload.includes(value)));

check('Explorer/runtime store exposes selected execution target', [
  'executionTarget',
  'setExecutionTarget',
  'listExecutionTargets',
  'beast.v2.workspace.execution-target',
].every(value => read('renderer/js/beast-desktop-bridge.js').includes(value) || read('renderer/js/beast-store.js').includes(value)));

check('tasks and tests execute through the shared target layer', [
  'runWorkspaceTask(rootPath,payload)',
  'runWorkspaceTest(rootPath,payload)',
  'runOnExecutionTarget(selectedTarget',
  'executionTarget',
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

check('AI streaming keeps explicit context visible and bounded', [
  'MAX_CONTEXT_FILES',
  'normalizeContextFiles',
  'not locked by backend',
  'Context mismatch or read failure',
  "mode === 'ask' ? 6000 : 16000",
].every(value => aiCoding.includes(value)));

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

const failed = rows.filter(row => row.status === 'failed');
const result={ ok: failed.length === 0, checks: rows.length, passed: rows.filter(row => row.status === 'passed').length, skipped: rows.filter(row => row.status === 'skipped').length, failed };
const reportPath=path.resolve(String(process.env.BEAST_TARGET_REPORT_PATH||path.join(root,'..','build','EXECUTION_TARGET_PARITY.json')));
fs.mkdirSync(path.dirname(reportPath),{recursive:true});
fs.writeFileSync(reportPath,`${JSON.stringify(result,null,2)}\n`,'utf8');
console.log(JSON.stringify(result, null, 2));
process.exit(failed.length ? 1 : 0);
