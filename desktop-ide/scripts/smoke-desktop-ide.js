const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..');
const files = {
  package: path.join(root, 'package.json'),
  main: path.join(root, 'main.js'),
  preload: path.join(root, 'preload.js'),
  html: path.join(root, 'renderer', 'index.html'),
  renderer: path.join(root, 'renderer', 'app.js'),
  styles: path.join(root, 'renderer', 'styles.css'),
};

function read(name) {
  return fs.readFileSync(files[name], 'utf8');
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function parseJavaScript(name) {
  new vm.Script(read(name), { filename: files[name] });
}

const manifest = JSON.parse(read('package'));
const html = read('html');
const renderer = read('renderer');
const styles = read('styles');
const main = read('main');
const preload = read('preload');

parseJavaScript('main');
parseJavaScript('preload');
parseJavaScript('renderer');

const checks = [
  ['package name', manifest.name === 'beast-desktop-ide'],
  ['electron main', manifest.main === 'main.js'],
  ['linux packaging', manifest.scripts && manifest.scripts['package:linux']],
  ['smoke script registered', manifest.scripts && manifest.scripts.smoke],
  ['monaco dependency', manifest.dependencies && manifest.dependencies['monaco-editor']],
  ['renderer html loads monaco', html.includes('../node_modules/monaco-editor/min/vs/loader.js')],
  ['command palette modal', html.includes('commandPaletteOverlay') && renderer.includes('openCommandPaletteModal')],
  ['status chips', html.includes('statusChipBar') && renderer.includes('updateStatusChips')],
  ['next action inspector', html.includes('nextActionInspector') && renderer.includes('renderNextActionInspector')],
  ['workspace persistence', renderer.includes('saveWorkspaceState') && renderer.includes('restoreWorkspaceTabs')],
  ['local mascot asset', html.includes('assets/beast-dragon-mascot.png') && !html.includes('127.0.0.1:8000/beast-assets')],
  ['file explorer controls', html.includes('expandExplorer') && html.includes('toggleExplorerMode') && html.includes('fileExplorerStatus') && renderer.includes('explorerFlatMode') && renderer.includes('setExplorerStatus')],
  ['file operations', html.includes('newWorkspaceFile') && renderer.includes('runGovernedFileOperation') && preload.includes('fileOperation')],
  ['local release readiness', main.includes('localReleaseReadiness') && main.includes("ipcMain.handle('beast:release-readiness'") && preload.includes('releaseReadiness') && renderer.includes('Gateway readiness route unavailable')],
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
  ['gateway doctor', html.includes('gatewayDoctorRaw') && main.includes('gatewayCapabilityHealth')],
  ['compatible gateway attach scan', main.includes('findCompatibleGateway') && main.includes('attached to compatible BEAST gateway')],
  ['multi-window log routing', main.includes('appWindows') && main.includes('windowId')],
  ['workspace selection persistence', renderer.includes('selectedAgentSessionId') && renderer.includes('selectedWorktreeTaskId') && renderer.includes('commandPaletteRecents')],
  ['local IDE mode', main.includes('enterLocalIdeMode') && renderer.includes('desktopLocalMode')],
  ['preload file IPC', preload.includes('listFiles') && preload.includes('readFile')],
  ['terminal styling', styles.includes('terminal-control-plane') && styles.includes('terminal-decision-card')],
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
  desktopVersion: main.match(/DESKTOP_IDE_VERSION\s*=\s*'([^']+)'/)?.[1] || 'unknown',
  renderer: path.relative(process.cwd(), files.renderer),
}, null, 2));
