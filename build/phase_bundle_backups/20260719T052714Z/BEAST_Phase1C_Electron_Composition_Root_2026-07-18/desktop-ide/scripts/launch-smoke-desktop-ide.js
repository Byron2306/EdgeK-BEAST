const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const rendererRoot = path.join(root, 'renderer', 'js');
const renderer = fs.readdirSync(rendererRoot, { recursive: true }).filter(file => file.endsWith('.js')).sort()
  .map(file => fs.readFileSync(path.join(rendererRoot, file), 'utf8')).join('\n');
const html = fs.readFileSync(path.join(root, 'renderer', 'index.html'), 'utf8');
const main = fs.readFileSync(path.join(root, 'main.js'), 'utf8');
const preload = fs.readFileSync(path.join(root, 'preload.js'), 'utf8');

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const checks = [
  ['renderer entry modules exist', renderer.includes('window.BeastRouter') && renderer.includes("BeastRouter.navigate('studio')")],
  ['multi-window state contract', main.includes('appWindows') && main.includes('windowId')],
  ['terminal stream contract', renderer.includes('startChat') && renderer.includes('terminal-chat-output')],
  ['tooling operations contract', renderer.includes('refreshTooling') && renderer.includes('validatePluginManifest')],
  ['worktree mission contract', renderer.includes('worktreeAction') && renderer.includes('worktree-mission/sourceplan-draft')],
  ['release readiness contract', renderer.includes('/edgek/ide/release-readiness/check') && html.includes('data-beast-route="deploy"')],
  ['IDE compatibility contract', main.includes('IdeCompatibilityHost') && preload.includes('startIdeProtocol') && renderer.includes('registerCompletionItemProvider')],
  ['debug notebook remote contract', main.includes('beast:notebook-execute') && main.includes('beast:remote-probe') && preload.includes('executeNotebookCell') && renderer.includes('startPythonDebug')],
  ['first mission journey', renderer.includes('window.BeastOnboarding') && renderer.includes('Prove + Reuse')],
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
  renderer: path.relative(root, rendererRoot),
}, null, 2));
