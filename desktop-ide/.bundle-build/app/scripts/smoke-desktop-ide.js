const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..');
const buildIdentity = JSON.parse(fs.readFileSync(path.join(root, 'BUILD_IDENTITY.json'), 'utf8'));
const files = {
  package: path.join(root, 'package.json'),
  main: path.join(root, 'main.js'),
  preload: path.join(root, 'preload.js'),
  html: path.join(root, 'renderer', 'index.html'),
  opcbComponents: path.join(root, 'renderer', 'opcb-components.js'),
  opcbLiveStore: path.join(root, 'renderer', 'opcb-live-store.js'),
  opcbState: path.join(root, 'renderer', 'opcb-state.js'),
  opcbRenderers: path.join(root, 'renderer', 'opcb-renderers.js'),
  styles: path.join(root, 'renderer', 'css', 'beast-production.css'),
};

function read(name) {
  if (name === 'renderer') {
    const jsRoot = path.join(root, 'renderer', 'js');
    return fs.readdirSync(jsRoot, { recursive: true }).filter(file => file.endsWith('.js')).sort()
      .map(file => fs.readFileSync(path.join(jsRoot, file), 'utf8')).join('\n');
  }
  if (!fs.existsSync(files[name])) return '';
  return fs.readFileSync(files[name], 'utf8');
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function parseJavaScript(name) {
  const source = read(name);
  if (source) new vm.Script(source, { filename: files[name] });
}

const manifest = JSON.parse(read('package'));
const html = read('html');
const renderer = read('renderer');
const styles = read('styles');
const main = read('main');
const mainModules = fs.readdirSync(path.join(root, 'main')).filter(name => name.endsWith('.js')).sort().map(name => fs.readFileSync(path.join(root, 'main', name), 'utf8')).join('\n');
const mainContract = `${main}\n${mainModules}`;
const preload = read('preload');

parseJavaScript('main');
parseJavaScript('preload');
parseJavaScript('renderer');
parseJavaScript('opcbComponents');
parseJavaScript('opcbLiveStore');
parseJavaScript('opcbState');
parseJavaScript('opcbRenderers');

const legacyChecks = [
  ['package name', manifest.name === 'beast-desktop-ide'],
  ['electron main', manifest.main === 'main.js'],
  ['linux packaging', manifest.scripts && manifest.scripts['package:linux']],
  ['smoke script registered', manifest.scripts && manifest.scripts.smoke],
  ['monaco dependency', manifest.dependencies && manifest.dependencies['monaco-editor']],
  ['renderer html loads monaco', html.includes('../node_modules/monaco-editor/min/vs/loader.js')],
  ['opcb live store', !files.opcbLiveStore || !fs.existsSync(files.opcbLiveStore) || (html.includes('opcb-live-store.js') && read('opcbLiveStore').includes('requiredGatewayRoutes') && read('opcbState').includes('enforceOpcbControlContract'))],
  ['command palette modal', html.includes('commandPaletteOverlay') && renderer.includes('openCommandPaletteModal')],
  ['status chips', html.includes('statusChipBar') && renderer.includes('updateStatusChips')],
  ['next action inspector', html.includes('nextActionInspector') && renderer.includes('renderNextActionInspector')],
  ['workspace persistence', renderer.includes('saveWorkspaceState') && renderer.includes('restoreWorkspaceTabs')],
  ['local mascot asset', html.includes('assets/beast-dragon-mascot.png') && !html.includes('127.0.0.1:8000/beast-assets')],
  ['file explorer controls', html.includes('expandExplorer') && html.includes('toggleExplorerMode') && html.includes('fileExplorerStatus') && renderer.includes('explorerFlatMode') && renderer.includes('setExplorerStatus')],
  ['file operations', html.includes('newWorkspaceFile') && renderer.includes('runGovernedFileOperation') && preload.includes('fileOperation')],
  ['local release readiness', mainContract.includes('localReleaseReadiness') && mainContract.includes("ipcMain.handle('beast:release-readiness'") && preload.includes('releaseReadiness') && renderer.includes('Gateway readiness route unavailable')],
  ['split editor', html.includes('monacoSplitEditor') && renderer.includes('toggleSplitEditor')],
  ['sourceplan operation editor', html.includes('editSourcePlanOp') && renderer.includes('editSelectedSourcePlanOperation')],
  ['sourceplan rebase', html.includes('rebaseSourcePlan') && renderer.includes('rebaseSourcePlanAgainstDisk')],
  ['diff hunk selector', html.includes('diffHunkSelector') && renderer.includes('renderDiffHunkSelector') && renderer.includes('selected_hunks')],
  ['governed terminal cwd', html.includes('terminalCwd') && renderer.includes("params.set('cwd'")],
  ['terminal streaming', html.includes('terminalStreamState') && html.includes('cancelCommand') && renderer.includes('/edgek/ide/terminal/stream') && renderer.includes('cancelTerminalCommand')],
  ['terminal evidence drawer', html.includes('terminalEvidenceDetail') && renderer.includes('recordTerminalExecution')],
  ['terminal history', html.includes('terminalHistoryList') && renderer.includes('rememberTerminalCommand')],
  ['provider setup', html.includes('providerSelect') && renderer.includes('smokeNvidiaProvider')],
  ['tooling plane', html.includes('data-view="tooling"') && html.includes('toolingSummary') && renderer.includes('refreshToolingSnapshot') && preload.includes('toolingSnapshot')],
  ['tooling operations', html.includes('mcpOpsPanel') && html.includes('pluginOpsPanel') && renderer.includes('refreshMcpOps') && renderer.includes('validatePluginManifest')],
  ['agent sourceplan path', renderer.includes('/edgek/ide/agent-sessions/action-ir-sourceplan')],
  ['agent retry options', renderer.includes('providerRetryOptions') && renderer.includes('symbol-scoped patches')],
  ['agent action ir retry guidance', renderer.includes('renderAgentActionIrRetry') && renderer.includes('missing_context_questions')],
  ['code references', html.includes('findReferences') && renderer.includes('/edgek/ide/text-search')],
  ['code intelligence route', renderer.includes('/edgek/ide/code-intel') && renderer.includes('refreshCodeIntelligence')],
  ['worktree window wizard', html.includes('openWorktreeWindow') && renderer.includes('runWorktreePromotionWizard') && preload.includes('openWorkspaceWindow')],
  ['worktree wizard polish', html.includes('worktreeWizardSteps') && renderer.includes('renderWorktreeDiffSummary')],
  ['sourceplan checklist', html.includes('sourcePlanChecklist') && renderer.includes('renderSourcePlanChecklist')],
  ['gateway doctor', html.includes('gatewayDoctorRaw') && mainContract.includes('gatewayCapabilityHealth')],
  ['compatible gateway attach scan', mainContract.includes('findCompatibleGateway') && mainContract.includes('attached to compatible BEAST gateway')],
  ['multi-window log routing', mainContract.includes('appWindows') && mainContract.includes('windowId')],
  ['workspace selection persistence', renderer.includes('selectedAgentSessionId') && renderer.includes('selectedWorktreeTaskId') && renderer.includes('commandPaletteRecents')],
  ['local IDE mode', mainContract.includes('enterLocalIdeMode') && renderer.includes('desktopLocalMode')],
  ['preload file IPC', preload.includes('listFiles') && preload.includes('readFile')],
  ['terminal styling', styles.includes('terminal-control-plane') && styles.includes('terminal-decision-card')],
];

const checks = [
  ['package name', manifest.name === 'beast-desktop-ide'],
  ['electron main', manifest.main === 'main.js'],
  ['linux packaging script', Boolean(manifest.scripts?.['package:linux'])],
  ['smoke script registered', Boolean(manifest.scripts?.smoke)],
  ['monaco dependency', Boolean(manifest.dependencies?.['monaco-editor'])],
  ['release page shell', html.includes('beastPageOutlet') && renderer.includes('BeastRouter.register')],
  ['all navigation surfaces', ['tooling','atlas','worktrees','deploy','terminal','trust','map'].every(route=>html.includes(`data-beast-route="${route}"`))],
  ['streamed model chat', renderer.includes('startChat') && renderer.includes('terminal-chat-trace')],
  ['visible chat run details', renderer.includes('Show chat run details')],
  ['AI editor handoff', renderer.includes('data-editor-action="assist"') && renderer.includes('Act as my coding partner')],
  ['worktree mission registry', renderer.includes('/edgek/ide/worktree-mission/list') && renderer.includes('worktree-sourceplan')],
  ['provider diagnostics route', renderer.includes('/edgek/route/provider-diagnostic/')],
  ['system operation feedback', renderer.includes('Runtime sweep complete')],
  ['readiness operation feedback', renderer.includes('IDE readiness checked')],
  ['trust-first mission flow', renderer.includes('data-mission-action="verify-trust"')],
  ['operational semantic map', renderer.includes('addOperationalTopology') && renderer.includes('Trust And Risk Gates')],
  ['tooling forge surface', renderer.includes('BeastToolingPage') && renderer.includes('/edgek/ide/tooling-snapshot')],
  ['tooling initial-state guard', renderer.includes('capabilities: []') && renderer.includes('Array.isArray(tooling.capabilities)')],
  ['model route diagnostic action', renderer.includes("data-model-action=\"test\"") && renderer.includes("providerAction('smoke')")],
  ['swarm action feedback', renderer.includes('Swarm run started') && renderer.includes('Swarm synchronized')],
  ['studio availability status', renderer.includes("status==='available'") && renderer.includes('Operational Surfaces')],
  ['local mascot asset', html.includes('assets/mascot/idle/frame_00.png') && !html.includes('127.0.0.1:8000/beast-assets')],
  ['preload file IPC', preload.includes('listFiles') && preload.includes('readFile')],
  ['terminal styling', styles.includes('terminal-chat-trace') && styles.includes('terminal-screen')],
];

const failed = checks.filter(([, passed]) => !passed);
if (failed.length) {
  for (const [name] of failed) {
    console.error(`FAIL ${name}`);
  }
  process.exit(1);
}

console.log(JSON.stringify({
  ok: true,
  checks: checks.length,
  desktopVersion: buildIdentity.desktop_runtime_build || buildIdentity.desktop_runtime_version || 'unknown',
  renderer: path.relative(process.cwd(), path.join(root, 'renderer', 'js')),
}, null, 2));
