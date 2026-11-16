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
const activeApp = fs.readFileSync(path.join(root, 'renderer', 'js', 'beast-phase9-app.js'), 'utf8');
const localRendererResources = [...html.matchAll(/<(?:script|link)\b[^>]*\b(?:src|href)="([^"]+)"/g)]
  .map(([, resource]) => resource)
  .filter(resource => !/^(?:https?:|data:|#)/.test(resource));
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
  ['local renderer resources', localRendererResources.every(resource => fs.existsSync(path.resolve(root, 'renderer', resource)))],
  ['restored route visual theme', html.includes('beast-restored-pages-polish.css') && fs.readFileSync(path.join(root, 'renderer', 'css', 'beast-restored-pages-polish.css'), 'utf8').includes('assets/headers/header-page.png') && ['fabric-route-map','live-proof-strip','closure-gate','reality-row','atlas-feature-card','compat-hero-mark img','compat-summary-grid img','compat-capability img'].every(selector => fs.readFileSync(path.join(root, 'renderer', 'css', 'beast-restored-pages-polish.css'), 'utf8').includes(`.${selector}`))],
  ['workspace Agent Coder wiring', html.includes('js/beast-workspace-agent-panel.js') && html.includes('js/beast-ai-coding.js') && html.indexOf('js/ai/agent-store.js') < html.indexOf('js/beast-ai-coding.js') && renderer.includes('data-ai-action="worktree-agent"') && renderer.includes('BeastWorkspaceTrust') && fs.readFileSync(path.join(root, 'renderer', 'js', 'beast-store.js'), 'utf8').includes('aiCoding: {')],
  ['Studio live readiness probes', renderer.includes('refreshStudio({force=false}={})') && renderer.includes('No successful live check recorded') && renderer.includes('Demo telemetry; live readiness is not verified') && html.includes('js/beast-studio-readiness-ui.js')],
  ['MCP approval counts follow loaded requests', renderer.includes('approvalQueueChecked:Boolean(extras.approvals?.ok)') && renderer.includes("approvalQueue:'/edgek/mcp/approvals?limit=20'") && renderer.includes('tooling.approvalQueueChecked ? pendingApprovals.length : reportedPending') && !renderer.includes('One governed tool request is waiting')],
  ['Studio readiness details match local capability state', renderer.includes('Workspace editor runtime is available') && renderer.includes('SourcePlan runtime is available')],
  ['compute fabric leaves unreported routes unverified', renderer.includes("route.eligible === true ? 'ELIGIBLE'") && renderer.includes("'UNVERIFIED'") && fs.readFileSync(path.join(root, 'renderer', 'css', 'beast-restored-pages-polish.css'), 'utf8').includes('.fabric-route.unverified')],
  ['closure and reality refresh their evidence snapshot', renderer.includes("['grandClosure', 'grandClosure', 'grand_closure']") && renderer.includes('data-closure-refresh') && renderer.includes('data-reality-refresh') && renderer.includes('Historical proof is not a live host attestation')],
  ['agent page does not claim empty sessions are ready', fs.readFileSync(path.join(root, 'renderer', 'js', 'pages', 'beast-agents-page.js'), 'utf8').includes('IDLE · NO SESSIONS') && fs.readFileSync(path.join(root, 'renderer', 'js', 'beast-model-agent-bridge.js'), 'utf8').includes('if (failures.length) throw new Error')],
  ['Agents page exposes governed swarm role lanes and explicit runs', fs.readFileSync(path.join(root, 'renderer', 'js', 'pages', 'beast-agents-page.js'), 'utf8').includes('Governed Swarm Kernel') && fs.readFileSync(path.join(root, 'renderer', 'js', 'beast-model-agent-bridge.js'), 'utf8').includes("fetchJson('/edgek/swarm/run'") && fs.readFileSync(path.join(root, 'renderer', 'js', 'beast-store.js'), 'utf8').includes('roleLanes: []')],
  ['commons inventory allows normal gateway startup latency', fs.readFileSync(path.join(root, 'renderer', 'js', 'pages', 'beast-commons-page.js'), 'utf8').includes('timeoutMs:6000')],
  ['compatibility route prerequisites', html.includes('js/beast-ide-compatibility.js') && fs.readFileSync(path.join(root, 'renderer', 'js', 'beast-store.js'), 'utf8').includes('compatibility: {')],
  ['restored navigation routes', ['compatibility','compute-fabric','live-fabric','compute-control','grand-closure','commons','testing','reality','atlas'].every(route=>html.includes(`data-beast-route="${route}"`) && html.includes(`value="${route}"`))],
  ['restored route renderers', ['BeastCompatibilityPage','BeastComputeFabricPage','BeastLiveFabricPage','BeastComputeControlPage','BeastGrandClosurePage','BeastCommonsPage','BeastTestingPage','BeastRealityPage','BeastAtlasPage'].every(page=>renderer.includes(`window.${page}`))],
  ['IDE compatibility runtime', html.includes('beast-ide-runtime.js') && renderer.includes('BeastIDERuntime.startDebug')],
  ['compute control refresh', renderer.includes('refreshPlatform = refreshPlatform') && renderer.includes('refreshControl = refreshControl')],
  ['workspace testing IPC', renderer.includes('runWorkspaceTest') && preload.includes('runWorkspaceTest')],
  ['commons control-plane route', renderer.includes('/edgek/control-plane/commons/remote')],
  ['commons fabric health and endpoint transitions without pins', (() => { const page = fs.readFileSync(path.join(root, 'renderer', 'js', 'pages', 'beast-commons-page.js'), 'utf8'); return page.includes('/edgek/control-plane/commons/remote/health') && page.includes('data-remote-health') && page.includes('admission_valid_until') && page.includes('endpoint_history') && page.includes('superseded_candidate') && !page.includes('node_public_key}') && !/esc\([^)]*node_public_key/.test(page); })()],
  ['commons docker custody records rendered without signatures', (() => { const page = fs.readFileSync(path.join(root, 'renderer', 'js', 'pages', 'beast-commons-page.js'), 'utf8'); return page.includes('custodyLine(row.custody)') && page.includes('custody refused') && page.includes('socket_owner') && !/esc\([^)]*custody\.signature/.test(page); })()],
  ['new routes have working commands', ['compatibility','compute-fabric','live-fabric','compute-control','grand-closure','commons','testing','reality','atlas'].every(route=>renderer.includes(`BeastRouter.navigate('${route}')`))],
  ['system operation feedback', renderer.includes('Runtime sweep complete')],
  ['local typography assets', html.includes('beast-9-1-5-local-fonts.css') && !html.includes('fonts.googleapis.com')],
  ['Phase 9.1.5 renderer shell', html.includes('Unique Hacker Type') && html.includes('beastPageOutlet')],
  ['tooling forge surface', renderer.includes('BeastToolingPage') && renderer.includes('/edgek/ide/tooling-snapshot')],
  ['tooling exposes BEAST MCP built-ins and meta skills', renderer.includes("builtinTools:'/mcp/tools/list'") && renderer.includes("skillState:'/edgek/skills/state'") && renderer.includes('data-tooling-module="skills"') && renderer.includes('BEAST Built-ins')],
  ['on-demand initial page loading', !activeApp.slice(activeApp.indexOf('async function boot()')).includes('BeastModelAgentBridge.refreshModels()')],
  ['model route diagnostic action', renderer.includes("data-model-action=\"test\"") && renderer.includes("providerAction('smoke')")],
  ['throttled visual effects', renderer.includes('frameDelay=()=>document.hidden') && renderer.includes('setTimeout(draw, document.hidden ? 500 : 80)')],
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
