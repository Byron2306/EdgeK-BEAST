const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const dist = path.join(root, 'dist');
const unpacked = path.join(dist, 'linux-unpacked');
const appImage = path.join(dist, 'BEAST Desktop IDE-0.1.1.AppImage');
const deb = path.join(dist, 'beast-desktop-ide_0.1.1_amd64.deb');
const executable = path.join(unpacked, 'beast-desktop-ide');
const appAsar = path.join(unpacked, 'resources', 'app.asar');
const renderer = fs.readFileSync(path.join(root, 'renderer', 'app.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'renderer', 'index.html'), 'utf8');
const main = fs.readFileSync(path.join(root, 'main.js'), 'utf8');

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const checks = [
  ['dist exists', fs.existsSync(dist)],
  ['linux unpacked exists', fs.existsSync(unpacked)],
  ['unpacked executable exists', fs.existsSync(executable)],
  ['unpacked executable is executable', fs.existsSync(executable) && Boolean(fs.statSync(executable).mode & 0o111)],
  ['asar exists', fs.existsSync(appAsar)],
  ['AppImage exists', fs.existsSync(appImage)],
  ['deb exists', fs.existsSync(deb)],
  ['AppImage non-empty', fs.existsSync(appImage) && fs.statSync(appImage).size > 50 * 1024 * 1024],
  ['deb non-empty', fs.existsSync(deb) && fs.statSync(deb).size > 20 * 1024 * 1024],
  ['multi-window state contract', main.includes('appWindows') && main.includes('windowId')],
  ['terminal stream contract', renderer.includes('/edgek/ide/terminal/stream') && html.includes('terminalStreamState')],
  ['tooling ops contract', renderer.includes('refreshMcpOps') && renderer.includes('validatePluginManifest') && html.includes('mcpOpsPanel')],
  ['code intel contract', renderer.includes('/edgek/ide/code-intel') && renderer.includes('refreshCodeIntelligence')],
  ['worktree wizard contract', renderer.includes('renderWorktreeWizardSteps') && html.includes('worktreeWizardSteps')],
];

const failed = checks.filter(([, ok]) => !ok);
if (failed.length) {
  for (const [name] of failed) console.error(`FAIL ${name}`);
  process.exit(1);
}

for (const [name, ok] of checks) assert(ok, name);
console.log(JSON.stringify({
  ok: true,
  checks: checks.length,
  appImage: path.relative(root, appImage),
  deb: path.relative(root, deb),
  unpacked: path.relative(root, executable),
}, null, 2));
