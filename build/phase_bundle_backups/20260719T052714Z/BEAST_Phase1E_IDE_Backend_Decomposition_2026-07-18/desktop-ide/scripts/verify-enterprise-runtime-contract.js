const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const mainEntry = read('main.js');
const mainModules = fs.readdirSync(path.join(root, 'main')).filter(name => name.endsWith('.js')).sort().map(name => read(`main/${name}`)).join('\n');
const main = `${mainEntry}\n${mainModules}`;
const preload = read('preload.js');
const runtime = read('renderer/js/beast-runtime-contract.js');
const commons = read('renderer/js/pages/beast-commons-page.js');
const bridge = read('renderer/js/beast-utility-orchestration-bridge.js');
const agents = read('renderer/js/beast-model-agent-bridge.js');
const atlas = read('renderer/js/pages/beast-atlas-page.js');
const release = read('renderer/js/beast-release-app.js');
const index = read('renderer/index.html');
const desktopBridge = read('renderer/js/beast-desktop-bridge.js');
const editorCortex = read('renderer/js/beast-editor-cortex.js');
const crystalBridge = read('renderer/js/beast-map-crystal-bridge.js');
const store = read('renderer/js/beast-store.js');
const styles = read('renderer/css/beast-production.css');
const ideRoot = path.join(root, '..', 'app', 'routes');
const ideRoutes = [
  fs.readFileSync(path.join(ideRoot, 'ide.py'), 'utf8'),
  ...fs.readdirSync(path.join(ideRoot, 'ide_support')).filter(name => name.endsWith('.py')).sort().map(name => fs.readFileSync(path.join(ideRoot, 'ide_support', name), 'utf8')),
].join('\n');
const gatewayTimeoutMatch = main.match(/gatewayHealth\(baseUrl\s*=\s*gatewayUrl,\s*rootTimeoutMs\s*=\s*(\d+)\)/);
const gatewayRootTimeoutMs = Number(gatewayTimeoutMatch?.[1] || 0);

const checks = {
  registry_gateway_8101: main.includes("serviceRegistryGateway(repoRoot)") && runtime.includes("http://127.0.0.1:8101"),
  legacy_scan_removed: !main.includes("8000 + index"),
  enterprise_routes_attested: main.includes('/edgek/control-plane/desktop-compatibility') && main.includes('side_effect_free_route_attestation') && [
    '/edgek/control-plane/workspace-identity','/edgek/control-plane/services','/edgek/control-plane/tool-buckets?phase=Observe','/edgek/control-plane/enterprise','/edgek/control-plane/commons',
  ].every(route => commons.includes(route)),
  remote_commons_control_plane: [
    '/edgek/control-plane/commons/remote','/edgek/control-plane/commons/remote/discovery','data-discovery-form','data-remote-discovery','data-node-form','data-bucket-form','data-probe-node','data-browse-node',
  ].every(contract => commons.includes(contract)),
  remote_commons_no_direct_egress: !commons.includes('fetch(') && commons.includes('BeastRuntime.request'),
  ipc_gateway_transport: preload.includes('gatewayRequest') && main.includes('createIpcRegistry') && main.includes("beast:gateway-request") && runtime.includes("hasDesktop('gatewayRequest')"),
  workspace_identity_header: runtime.includes('X-BEAST-Workspace-Identity'),
  dependency_complete_python_probe: main.includes('fastapi, uvicorn, cryptography, yaml'),
  systems_atlas_registered: index.includes('data-beast-route="atlas"') && index.includes('beast-atlas-page.js') && release.includes('BeastAtlasPage.renderer'),
  named_systems_are_visible_in_primary_ui: ['Swarm','Semantic Map','RAG + KV Cache','Runtime + PREC','Chronicle + Sensorium','Economizer'].every(label => index.includes(`>${label}<`)) && atlas.includes('<h3>Operational Systems</h3>'),
  legacy_studio_topology_routes_are_canonicalized: read('renderer/js/beast-router.js').includes("'platform atlas':'atlas'") && read('renderer/js/beast-router.js').includes("'swarm lanes':'agents'"),
  atlas_uses_live_platform_snapshot: bridge.includes('/edgek/platform/snapshot') && atlas.includes('NO SEEDED RUNTIME DATA'),
  swarm_uses_live_routes: agents.includes("'/edgek/swarm/state'") && agents.includes("'/edgek/swarm/runs?limit=20'"),
  no_live_agent_demo_fallback: !agents.includes('Agent Constellation refreshed from fallback telemetry') && !agents.includes('Agent session fell back locally'),
  demo_fixtures_require_explicit_build_opt_in: ['renderer/js/beast-store.js','renderer/js/beast-desktop-bridge.js','renderer/js/beast-terminal-tooling-doctor-bridge.js','renderer/js/beast-utility-orchestration-bridge.js'].every(file => read(file).includes('window.BEAST_ENABLE_DEMO === true')),
  demo_query_cannot_force_runtime_offline: runtime.includes("window.BEAST_ENABLE_DEMO===true&&(params.get('capture')==='1'||params.get('demo')==='1')"),
  platform_snapshot_not_boot_fanout: !bridge.includes('Promise.allSettled([refreshProviders(),refreshPlatform(),refreshWorktrees()'),
  guardian_listener_fallback_is_bounded: gatewayRootTimeoutMs >= 500 && gatewayRootTimeoutMs <= 5000 && main.includes('listener at ${gatewayUrl} did not answer the BEAST HTTP contract') && main.includes('health.ok || health.tcp_listening ? requestedPort + 1 : requestedPort'),
  managed_gateway_not_reset_to_guardian: main.includes('Keep a managed compatible port') && !main.includes('gatewayUrl = configuredGatewayUrl;\n    ensureGateway();'),
  desktop_child_forces_direct_gateway_mode: main.includes('delete childEnv.BEAST_SOCKET_MODE') && main.includes('starting direct desktop gateway'),
  gateway_restart_waits_for_managed_exit: main.includes('async function stopManagedGateway') && main.includes('await stopManagedGateway(previousGateway)'),
  system_mutations_use_preview_and_explicit_approval: bridge.includes('async function previewSystemAction') && bridge.includes('if (payload.dryRun) return response') && bridge.includes('approved:mutation?Boolean(payload.approved)') && read('renderer/js/pages/beast-phase8-pages.js').includes("previewSystemAction('free-port'") && read('renderer/js/pages/beast-phase8-pages.js').includes('PREVIEW STOP'),
  guardian_processes_are_protected_from_system_controls: fs.readFileSync(path.join(root, '..', 'app', 'kernel', 'workspaces', 'system_inspector.py'), 'utf8').includes('guardian_owned_process'),
  sourceplan_has_no_silent_local_success: !desktopBridge.includes('verified-local') && !desktopBridge.includes('applied-local') && !editorCortex.includes('Verified locally:') && !editorCortex.includes('Applied locally:'),
  snapshot_boot_is_bounded: desktopBridge.includes('const fullSnapshot = options.full === true') && desktopBridge.includes("'desktop-health'") && ideRoutes.includes('detail: bool = False') && ideRoutes.includes('if not detail or'),
  mutations_do_not_swallow_gateway_failures: !bridge.includes('await quiet(') && bridge.includes("await request('/edgek/providers/kv-cache/clear'") && bridge.includes("await request('/edgek/insights/compile'"),
  operation_failure_is_visible: index.includes('beastOperationNotice') && release.includes("window.addEventListener('unhandledrejection'") && release.includes('operationNotice('),
  gateway_startup_recovery_is_bounded: release.includes('gatewayRecoveryAttempts < 4') && release.includes("refreshProductionState('gateway-retry')") && release.includes("reason === 'boot' || reason === 'gateway-retry'"),
  crystal_actions_require_receipts: crystalBridge.includes("'/edgek/crystal-reuse/acceptance?probe=false'") && crystalBridge.includes('Crystal Chain attestation returned no witness receipt') && crystalBridge.includes('Crystal lattice checkpoint returned no ledger receipt') && (crystalBridge.includes('Candidate promotion requires a verified execution receipt') || crystalBridge.includes('Live Chamber promotion is intentionally unavailable')),
  crystal_verification_does_not_promote_pending_gates: !crystalBridge.includes("g.status==='Pending'&&state.connection.status==='online'?'Passed':g.status"),
  honest_boot_state: index.includes('Awaiting live mission assignment') && !index.includes('Transplant Terminal Nexus') && store.includes("build: 'unverified'") && store.includes('ledger: []'),
  no_unverified_default_model_route: store.includes("active: localStorage.getItem('beast.model') || ''") && store.includes("provider: localStorage.getItem('beast.provider') || ''") && store.includes("selectedModel: localStorage.getItem('beast.model') || ''") && store.includes("selectedProvider: localStorage.getItem('beast.provider') || ''"),
  provider_plane_uses_litellm_models_readiness: bridge.includes("request('/edgek/deploy/litellm-sidecar/state')") && bridge.includes("LiteLLM ready via /v1/models"),
  normalizers_tolerate_incomplete_live_telemetry: agents.includes("stats = stats && typeof stats === 'object' ? stats : {}") && agents.includes("return value.filter(item => item != null)") && read('renderer/js/beast-trust-memory-bridge.js').includes("(values.find(Array.isArray) || []).filter(item => item != null)"),
  agent_creation_requires_live_route: agents.includes("Select a live model and provider before creating an agent session.") && !agents.includes("|| 'nvidia_nim'"),
  responsive_header_wrap: styles.includes('--beast-header-h:190px') && styles.includes('-webkit-line-clamp:2') && release.includes('missionTitle.title = state.mission.title'),
  named_navigation_labels_wrap_in_sidebar: styles.includes('.beast-nav .label{font:700 14px/1.15') && styles.includes('overflow-wrap:anywhere'),
  canvas_resize_is_deferred_out_of_observer_delivery: read('renderer/js/beast-visual-canvas.js').includes('resizeRaf=requestAnimationFrame') && read('renderer/js/beast-visual-canvas.js').includes('cancelAnimationFrame(resizeRaf)'),
  runtime_canvas_resize_is_deferred_out_of_observer_delivery: read('renderer/js/beast-visual-runtime.js').includes('resizeRaf=requestAnimationFrame') && read('renderer/js/beast-visual-runtime.js').includes('cancelAnimationFrame(resizeRaf)'),
};

const failed = Object.entries(checks).filter(([, ok]) => !ok).map(([name]) => name);
console.log(JSON.stringify({ checks, failed, status: failed.length ? 'FAIL' : 'PASS' }, null, 2));
if (failed.length) process.exit(1);
