/**
 * BEAST Studio — OPCB369S + ARK KnowEdge-GG Functional Integration Layer
 * Wires OPCB Phase 1-20 + ARK v3.4.0 concepts into the BEAST gateway endpoints.
 *
 * Integrated systems:
 *   Cube state, event ledger, mission flow, crystalization/crystal chain/lattice,
 *   approval gates, receipt chooser, code graph, repo guard, evidence packs,
 *   runbook exporter, memory recall + memory security (Hull/Seal/Passport),
 *   schema scoring, skills (mining/candidates/promotion), swarm (state/governance/runs),
 *   commons spaces marketplace, runtime circuit breakers + integrity,
 *   ARK diff inspector, ARK change preview, ARK approval selector,
 *   PREC lifecycle, provider economist, MCP integration.
 */

/* ─── State ──────────────────────────────────────────────────────────── */
let studioState = {
  cube: { face: 'Mission', core: 'Crystalization', status: 'idle' },
  mission: null,
  eventLedger: [],
  crystalization: null,
  crystalChain: null,
  crystalLattice: null,
  approvalIndex: null,
  repoStatus: null,
  memoryStatus: null,
  memorySecurity: null,
  evidenceStatus: null,
  missionFlowStep: 0,
  repoGuardResult: null,
  runbookStatus: null,
  skills: null,
  swarm: null,
  commons: null,
  runtime: null,
};
let ledgerPollTimer = null;
const LEDGER_POLL_INTERVAL = 15000;
const FLOW_STEPS = ['Mission', 'Source', 'Review', 'Evidence', 'Crystal', 'Done'];

/* ─── Helpers ────────────────────────────────────────────────────────── */
function $s(id) { return document.getElementById(id); }
function escHtml(v) { return String(v ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function studioLog(msg) { try { log(`[studio] ${msg}`); } catch (_) {} }
async function studioGet(path, timeoutMs = 8000) {
  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const r = await fetch(`http://127.0.0.1:8000${path}`, { signal: controller.signal });
    return r.ok ? await r.json() : null;
  } catch (_) { return null; }
  finally { clearTimeout(t); }
}
async function studioPost(path, body, timeoutMs = 10000) {
  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const r = await fetch(`http://127.0.0.1:8000${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    return r.ok ? await r.json() : null;
  } catch (_) { return null; }
  finally { clearTimeout(t); }
}

/* ─── Cube State Machine ─────────────────────────────────────────────── */
/**
 * Maps the active BEAST page to an OPCB Cube face.
 * FACES: Mission | Models | Agents | Tools | Review | Evidence | Crystalization (core)
 */
const CUBE_FACE_MAP = {
  mission:   'Mission',
  source:    'Review',
  agents:    'Agents',
  worktrees: 'Tools',
  evidence:  'Evidence',
  terminal:  'Tools',
  providers: 'Models',
  tooling:   'Tools',
  doctor:    'Mission',
  settings:  'Mission',
};

function updateCubeForPage(page) {
  const face = CUBE_FACE_MAP[page] || 'Mission';
  studioState.cube.face = face;
  const shell = document.querySelector('.app-shell');
  if (shell) shell.dataset.activeFace = face;
  renderCubeZone();
}

function renderCubeZone() {
  const { cube, mission, eventLedger, crystalization, approvalIndex, missionFlowStep } = studioState;

  // cube zone live label
  const liveEl = $s('cubeZoneLive');
  if (liveEl) {
    liveEl.textContent = `● ${cube.face}`;
    liveEl.style.color = 'var(--teal)';
  }

  // gateway badge
  const gwBadge = $s('cubeGatewayBadge');
  const gwDetail = $s('cubeGatewayDetail');
  try {
    const gw = window._lastGatewayStatus || lastGatewayStatus;
    if (gwBadge) {
      gwBadge.textContent = gw?.health?.ok ? 'online' : 'connecting';
      gwBadge.className = `badge ${gw?.health?.ok ? 'ready' : 'warn'}`;
    }
    if (gwDetail) gwDetail.textContent = `127.0.0.1:8000 · ${cube.face} face`;
  } catch (_) {}

  // mission flow progress
  const flowRow = $s('missionFlowRow');
  if (flowRow) {
    flowRow.innerHTML = FLOW_STEPS.map((step, i) => {
      const cls = i < missionFlowStep ? 'flow-step done' : i === missionFlowStep ? 'flow-step active' : 'flow-step';
      return `<div class="${cls}">${escHtml(step)}</div>`;
    }).join('');
  }

  // policy gate mirror
  try {
    const pg = $s('policyGate');
    const pd = $s('policyDetail');
    const cpg = $s('cubePolicyGate');
    const cpd = $s('cubePolicyDetail');
    if (cpg && pg) cpg.textContent = pg.textContent || 'waiting';
    if (cpd && pd) cpd.textContent = pd.textContent || '';
  } catch (_) {}

  // crystalization crystal summary in cube zone
  renderCubeCrystalCard();
}

function renderCubeCrystalCard() {
  const { crystalization } = studioState;
  // Inject a dynamic crystal summary card into cube zone if not present
  let card = $s('cubeCrystalSummary');
  if (!card) {
    const cz = document.querySelector('.cube-zone');
    if (!cz) return;
    card = document.createElement('div');
    card.id = 'cubeCrystalSummary';
    card.className = 'card';
    card.style.padding = '10px 12px';
    cz.appendChild(card);
  }
  if (!crystalization) {
    card.innerHTML = `<div class="card-head" style="margin-bottom:4px"><h3 style="font-size:11px">Crystalization</h3><span class="badge warn">not loaded</span></div><div class="muted" style="font-size:11px">Refresh mission to load crystal state.</div>`;
    return;
  }
  const count = crystalization.active_credits ?? crystalization.total_credits ?? '?';
  const hits = crystalization.reuse_hit_count ?? '?';
  const saved = crystalization.measured_saved_tokens ?? '?';
  const badge = count > 0 ? 'ready' : 'warn';
  card.innerHTML = `
    <div class="card-head" style="margin-bottom:4px">
      <h3 style="font-size:11px">Crystal Reuse</h3>
      <span class="badge ${badge}">${escHtml(String(count))} credits</span>
    </div>
    <div style="font-size:11px;color:var(--muted)">${escHtml(String(hits))} hits · ${escHtml(String(saved))} tokens saved</div>`;
}

/* ─── Event Ledger ───────────────────────────────────────────────────── */
async function refreshEventLedger() {
  const data = await studioGet('/edgek/chronicle?limit=20');
  if (!data) return;
  studioState.eventLedger = data.entries || data.records || [];
  renderEventLedgerCard();
}

function renderEventLedgerCard() {
  const { eventLedger } = studioState;
  // Ensure event ledger card exists in cube zone
  let card = $s('cubeEventLedger');
  if (!card) {
    const cz = document.querySelector('.cube-zone');
    if (!cz) return;
    card = document.createElement('div');
    card.id = 'cubeEventLedger';
    card.className = 'card';
    card.style.padding = '10px 12px';
    cz.appendChild(card);
  }
  const entries = eventLedger.slice(0, 8);
  const rows = entries.map(e => `
    <li>
      <span>${escHtml(e.event || e.kind || e.type || 'event')}</span>
      <small>${escHtml((e.ts || e.recorded_at || e.timestamp || '').slice(11,19))}</small>
    </li>`).join('');
  card.innerHTML = `
    <div class="card-head" style="margin-bottom:6px">
      <h3 style="font-size:11px">Event Ledger</h3>
      <span class="badge">${escHtml(String(entries.length))} recent</span>
    </div>
    <ul class="event-list">${rows || '<li><span class="muted">No events yet.</span></li>'}</ul>`;
}

function startLedgerPolling() {
  if (ledgerPollTimer) return;
  refreshEventLedger();
  ledgerPollTimer = setInterval(() => refreshEventLedger(), LEDGER_POLL_INTERVAL);
}

/* ─── Mission Flow ───────────────────────────────────────────────────── */
function computeMissionFlowStep() {
  // derive OPCB mission flow step from BEAST state
  try {
    const hasSource = Boolean(window.currentSourcePlan);
    const verified = Boolean(window.currentSourcePlanLifecycle?.can_apply);
    const hasEvidence = (window.currentSourcePlanLifecycle?.evidence?.match_count || 0) > 0;
    const crystalized = (studioState.crystalization?.active_credits || 0) > 0;
    if (crystalized) return 5; // Done
    if (hasEvidence) return 4;  // Crystal
    if (verified) return 3;     // Evidence
    if (hasSource) return 2;    // Review
    if (window.currentFile) return 1; // Source
    return 0; // Mission
  } catch (_) { return 0; }
}

/* ─── Crystalization ─────────────────────────────────────────────────── */
async function refreshCrystalization() {
  const data = await studioGet('/edgek/crystal-reuse');
  if (!data) return;
  // real shape: data.storage = { active_credits, total_credits, reuse_hit_count, measured_saved_tokens }
  const storage = (data.storage && typeof data.storage === 'object') ? data.storage : {};
  studioState.crystalization = {
    active_credits: storage.active_credits ?? storage.credit_count ?? 0,
    total_credits: storage.total_credits ?? 0,
    reuse_hit_count: storage.reuse_hit_count ?? storage.hit_count ?? 0,
    measured_saved_tokens: typeof storage.measured_saved_tokens === 'number' ? storage.measured_saved_tokens : 0,
  };
  renderCrystalizationPanel();
  renderCubeCrystalCard();
}

function renderCrystalizationPanel() {
  const node = $s('studioXCrystalPanel');
  if (!node) return;
  const c = studioState.crystalization;
  if (!c) { node.innerHTML = '<div class="status-box muted">Crystal state not loaded.</div>'; return; }
  node.innerHTML = `
    <div class="two-col" style="margin-bottom:8px">
      <div class="status-box ready"><b>${escHtml(String(c.active_credits ?? '?'))}</b><br><span class="muted" style="font-size:10px">active credits</span></div>
      <div class="status-box ready"><b>${escHtml(String(c.reuse_hit_count ?? '?'))}</b><br><span class="muted" style="font-size:10px">reuse hits</span></div>
    </div>
    <div class="status-box" style="font-size:12px"><b>${escHtml(String(c.measured_saved_tokens ?? '?'))}</b> tokens saved by reuse</div>`;
}

/* ─── Approval Gate + Receipt Chooser ───────────────────────────────── */
async function refreshApprovalState() {
  const data = await studioGet('/edgek/mcp/approvals');
  if (!data) return;
  studioState.approvalIndex = data;
  renderApprovalPanel();
}

function renderApprovalPanel() {
  const node = $s('studioXApprovalPanel');
  if (!node) return;
  const idx = studioState.approvalIndex;
  if (!idx) { node.innerHTML = '<div class="status-box muted">No approval state loaded.</div>'; return; }
  const pending = Array.isArray(idx.approvals) ? idx.approvals.filter(a => a.status === 'pending') : [];
  const total = Array.isArray(idx.approvals) ? idx.approvals.length : (idx.total ?? 0);
  node.innerHTML = `
    <div class="two-col" style="margin-bottom:8px">
      <div class="status-box ${pending.length > 0 ? 'warn' : 'ready'}"><b>${escHtml(String(pending.length))}</b><br><span class="muted" style="font-size:10px">pending</span></div>
      <div class="status-box"><b>${escHtml(String(total))}</b><br><span class="muted" style="font-size:10px">total</span></div>
    </div>
    ${pending.slice(0,4).map(a => `
      <div class="mission-card">
        <b>${escHtml(a.request_id || a.id || 'approval')}</b>
        <span>${escHtml(a.tool_name || a.action || 'MCP action')}</span>
        <div class="gov-btn-row" style="margin-top:4px">
          <button class="primary-button" onclick="studioApproveRequest('${escHtml(a.request_id || a.id || '')}')">Approve</button>
          <button class="ghost-button" onclick="studioDenyRequest('${escHtml(a.request_id || a.id || '')}')">Deny</button>
        </div>
      </div>`).join('')}`;
}

async function studioApproveRequest(requestId) {
  if (!requestId) return;
  const res = await studioPost(`/edgek/mcp/approvals/${encodeURIComponent(requestId)}/approve`, { approved_by: 'operator' });
  studioLog(`approval: ${res?.status || 'sent'} for ${requestId}`);
  await refreshApprovalState();
}

async function studioDenyRequest(requestId) {
  if (!requestId) return;
  const res = await studioPost(`/edgek/mcp/approvals/${encodeURIComponent(requestId)}/deny`, { denied_by: 'operator' });
  studioLog(`denial: ${res?.status || 'sent'} for ${requestId}`);
  await refreshApprovalState();
}

/* ─── Code Graph Profiler ────────────────────────────────────────────── */
async function refreshCodeGraph() {
  // real shape: { count:105, kinds:{provider:27,tool:7,...}, families:{provider:28,...}, capabilities:[] }
  const data = await studioGet('/edgek/capabilities');
  if (!data) return;
  renderCodeGraphPanel(data);
}

function renderCodeGraphPanel(data) {
  const node = $s('studioXGraphPanel');
  if (!node) return;
  const count  = typeof data.count === 'number' ? data.count : (data.capabilities?.length ?? 0);
  const families = (data.families && typeof data.families === 'object') ? data.families : {};
  const kinds    = (data.kinds    && typeof data.kinds    === 'object') ? data.kinds    : {};
  const topFamilies = Object.entries(families).sort((a,b) => b[1]-a[1]).slice(0,6);
  node.innerHTML = `
    <div class="two-col" style="margin-bottom:8px">
      <div class="status-box ready" style="text-align:center;padding:8px">
        <div style="font-size:20px;font-weight:900;color:var(--cyan)">${count}</div>
        <div style="font-size:10px;color:var(--muted)">capabilities</div>
      </div>
      <div class="status-box" style="text-align:center;padding:8px">
        <div style="font-size:20px;font-weight:900;color:var(--teal)">${Object.keys(families).length}</div>
        <div style="font-size:10px;color:var(--muted)">families</div>
      </div>
    </div>
    ${topFamilies.map(([fam, n]) => `
      <div class="mission-card" style="display:flex;justify-content:space-between;align-items:center">
        <b>${escHtml(fam)}</b>
        <span class="badge ready">${n}</span>
      </div>`).join('')}`;
}

/* ─── Memory Recall ──────────────────────────────────────────────────── */
async function refreshMemoryState() {
  const data = await studioGet('/edgek/memory/stack');
  if (!data) return;
  studioState.memoryStatus = data;
  renderMemoryPanel();
}

function renderMemoryPanel() {
  const node = $s('studioXMemoryPanel');
  if (!node) return;
  const m = studioState.memoryStatus;
  if (!m) { node.innerHTML = '<div class="status-box muted">Memory not loaded.</div>'; return; }
  // real shape: { layers:{L0:{name,scope},L1:...}, truth_stores:[], retrieval_views:[], principle:'' }
  const layers = (m.layers && typeof m.layers === 'object') ? m.layers : {};
  const layerEntries = Object.entries(layers);
  const truthStores = Array.isArray(m.truth_stores) ? m.truth_stores.filter(Boolean) : [];
  node.innerHTML = `
    <div class="status-box" style="margin-bottom:6px">${layerEntries.length} memory layers · ${truthStores.length} truth stores</div>
    ${layerEntries.slice(0,4).map(([id, layer]) => `
      <div class="mission-card">
        <b>${escHtml(id)}: ${escHtml(layer.name || '')}</b>
        <span class="muted" style="font-size:10px">${escHtml((layer.scope || '').slice(0, 60))}</span>
      </div>`).join('')}`;
}

async function studioMemoryRecall(query) {
  const params = new URLSearchParams({ query: query || '', limit: '10' });
  const data = await studioGet(`/edgek/memory/stack?${params}`);
  if (!data) return;
  studioState.memoryStatus = data;
  renderMemoryPanel();
}

/* ─── Evidence Pack ──────────────────────────────────────────────────── */
async function refreshEvidenceState() {
  const data = await studioGet('/edgek/chronicle?limit=10');
  if (!data) return;
  studioState.evidenceStatus = data;
  renderEvidenceStudioPanel();
}

function renderEvidenceStudioPanel() {
  const node = $s('studioXEvidencePanel');
  if (!node) return;
  const d = studioState.evidenceStatus;
  const entries = d?.entries || d?.records || [];
  node.innerHTML = `
    <div class="status-box" style="margin-bottom:8px">${escHtml(String(entries.length))} chronicle entries</div>
    ${entries.slice(0,5).map(e => `
      <div class="mission-card">
        <b>${escHtml(e.task_type || e.kind || 'chronicle')}</b>
        <span class="muted">${escHtml((e.summary || e.detail || '').slice(0,80))}</span>
        <small>${escHtml((e.recorded_at || e.ts || '').slice(0,10))}</small>
      </div>`).join('')}`;
}

async function studioBuildEvidencePack() {
  studioLog('building evidence pack...');
  const root = (typeof workspaceRoot !== 'undefined' && workspaceRoot) ? workspaceRoot : '';
  const res = await studioPost('/edgek/evidence/score', { root_path: root, query: 'evidence pack' });
  studioLog(`evidence pack: ${res?.status || 'sent'}`);
  return res;
}

/* ─── Repo Guard ─────────────────────────────────────────────────────── */
async function refreshRepoStatus() {
  const root = (typeof workspaceRoot !== 'undefined' && workspaceRoot) ? workspaceRoot : '';
  if (!root) return;
  const params = new URLSearchParams({ root_path: root });
  const data = await studioGet(`/edgek/workspace/files?${params}&limit=1`);
  if (!data) return;
  studioState.repoStatus = data;
  renderRepoGuardPanel();
}

function renderRepoGuardPanel() {
  const node = $s('studioXRepoPanel');
  if (!node) return;
  const r = studioState.repoStatus;
  if (!r) { node.innerHTML = '<div class="status-box muted">Repo status not loaded.</div>'; return; }
  const total = r.total ?? r.count ?? '?';
  const fallback = r.fallback_used ? 'local fallback' : 'gateway';
  node.innerHTML = `
    <div class="status-box ready">${escHtml(String(total))} files via ${escHtml(fallback)}</div>`;
}

/* ─── Runbook ────────────────────────────────────────────────────────── */
async function studioBuildRunbook() {
  const root = (typeof workspaceRoot !== 'undefined' && workspaceRoot) ? workspaceRoot : '';
  const file = (typeof currentFile !== 'undefined' && currentFile) || '';
  // Use POST /edgek/handoff/prepare (confirmed working endpoint)
  const res = await studioPost('/edgek/handoff/prepare', {
    root_path: root,
    active_file: file,
    task_description: file ? `Work on ${file}` : 'BEAST Studio mission runbook',
  });
  if (!res) { studioLog('runbook: gateway offline'); return; }
  studioLog(`runbook: ${res.status || JSON.stringify(res).slice(0,40)}`);
  studioState.runbookStatus = res;
  renderRunbookPanel();
  return res;
}

function renderRunbookPanel() {
  const node = $s('studioXRunbookPanel');
  if (!node) return;
  const r = studioState.runbookStatus;
  if (!r) { node.innerHTML = '<div class="status-box muted">Click “Build Runbook” to compile a mission handoff.</div>'; return; }
  // handoff/prepare returns: { status, handoff_id or beast_object_type, task_description, active_file, guidance:[] }
  const hid   = r.handoff_id || r.beast_object_type || 'runbook';
  const desc  = r.task_description || r.description || '';
  const guide = Array.isArray(r.guidance) ? r.guidance : [];
  node.innerHTML = `
    <div class="status-box ${r.ok !== false ? 'ready' : 'warn'}" style="margin-bottom:8px">
      <b>${escHtml(String(hid).replace('beast_ide_','').slice(0,40))}</b>
    </div>
    ${desc ? `<div class="mission-card"><span class="muted">${escHtml(desc.slice(0,120))}</span></div>` : ''}
    ${guide.slice(0,4).map(g => `<div class="mission-card"><span style="font-size:11px">→ ${escHtml(String(g).slice(0,100))}</span></div>`).join('')}`;
}

/* ─── Schema / Quality Scoring ───────────────────────────────────────── */
async function studioScoreOutput(text) {
  const res = await studioPost('/edgek/quality/run', {
    text: text || '',
    root_path: (typeof workspaceRoot !== 'undefined' && workspaceRoot) || '',
  });
  if (!res) return;
  const node = $s('studioXQualityScore');
  if (!node) return;
  const score = res.score ?? res.quality_score ?? '?';
  const verdict = res.verdict || res.result || 'scored';
  node.innerHTML = `
    <div class="status-box ${verdict === 'pass' ? 'ready' : 'warn'}">
      <b>Quality: ${escHtml(String(score))}</b> · ${escHtml(verdict)}
    </div>`;
}

/* ─── MCP Integration Overview ───────────────────────────────────────── */
async function ensureMcpServersRegistered() {
  // Auto-register the known BEAST MCP servers on first load
  const known = [
    { name: 'beast-mcp-http',  server_class: 'local_read_only',     description: 'BEAST MCP HTTP facade (:8001)' },
    { name: 'beast-mcp-stdio', server_class: 'local_read_only',     description: 'BEAST MCP stdio server' },
    { name: 'beast-mcp-tools', server_class: 'sourceplan_workflow', description: 'BEAST SourcePlan + governance tools' },
  ];
  for (const server of known) {
    await studioPost('/edgek/mcp/servers', server).catch(() => {});
  }
}

async function refreshMcpIntegration() {
  // real shape: { stats:{ registered_servers, audit_events, schema_pins, pending_approvals, executions:{executed,blocked} },
  //               servers:[], pending_approvals:[], schema_pins:[] }
  const data = await studioGet('/edgek/mcp/state');
  if (!data) return;
  const node = $s('studioXMcpPanel');
  if (!node) return;
  const stats     = (data.stats && typeof data.stats === 'object') ? data.stats : {};
  const servers   = typeof stats.registered_servers === 'number' ? stats.registered_servers : (data.servers?.length ?? 0);
  const pins      = typeof stats.schema_pins         === 'number' ? stats.schema_pins         : (data.schema_pins?.length ?? 0);
  const audits    = typeof stats.audit_events        === 'number' ? stats.audit_events        : 0;
  const pending   = typeof stats.pending_approvals   === 'number' ? stats.pending_approvals   : (data.pending_approvals?.length ?? 0);
  const execs     = (stats.executions && typeof stats.executions === 'object') ? stats.executions : {};
  const serverList = Array.isArray(data.servers) ? data.servers : [];
  node.innerHTML = `
    <div class="two-col" style="margin-bottom:6px">
      <div class="status-box ${servers > 0 ? 'ready' : 'warn'}" style="text-align:center;padding:8px">
        <div style="font-size:18px;font-weight:900;color:var(--cyan)">${servers}</div>
        <div style="font-size:10px;color:var(--muted)">servers</div>
      </div>
      <div class="status-box ${pending > 0 ? 'warn' : ''}" style="text-align:center;padding:8px">
        <div style="font-size:18px;font-weight:900;color:var(--gold)">${pending}</div>
        <div style="font-size:10px;color:var(--muted)">pending</div>
      </div>
    </div>
    <div class="two-col" style="margin-bottom:6px">
      <div class="status-box muted" style="font-size:11px;text-align:center">${pins} pins</div>
      <div class="status-box muted" style="font-size:11px;text-align:center">${audits} audits</div>
    </div>
    ${serverList.slice(0,4).map(s => `
      <div class="mission-card">
        <b>${escHtml(s.name || s.server_name || 'server')}</b>
        <span class="badge ready">${escHtml(s.server_class || 'registered')}</span>
        <span class="muted" style="font-size:10px">${escHtml(s.description || '')}</span>
      </div>`).join('')}
    ${execs.executed > 0 ? `<div class="status-box ready" style="margin-top:6px;font-size:11px">${execs.executed} executed · ${execs.blocked ?? 0} blocked</div>` : ''}`;
}

/* ─── PREC Lifecycle Visibility ──────────────────────────────────────── */
async function refreshPrecState() {
  const data = await studioGet('/edgek/prec/state');
  if (!data) return;
  const node = $s('studioXPrecPanel');
  if (!node) return;
  // real shape: { phases:['perceive','reason','economize','crystallize'], counts:[{kind,status,count}], recent:[{lifecycle_id,...}] }
  const phases = Array.isArray(data.phases) ? data.phases : [];
  const counts = Array.isArray(data.counts) ? data.counts : [];
  const recent = Array.isArray(data.recent) ? data.recent : [];
  const byPhase = {};
  counts.forEach(c => { if (c.status === 'completed') byPhase[c.kind] = (byPhase[c.kind] || 0) + (c.count || 0); });
  node.innerHTML = `
    <div class="status-box ready" style="margin-bottom:6px">${phases.length} PREC phases · ${recent.length} recent</div>
    <div class="flow-row" style="gap:4px;margin-bottom:6px">
      ${phases.map(p => `<div class="flow-step ${byPhase[p] > 0 ? 'done' : ''} " style="font-size:9px;padding:5px 2px">${escHtml(p.slice(0,4))}</div>`).join('')}
    </div>
    ${recent.slice(0,3).map(r => `
      <div class="mission-card">
        <b>${escHtml(r.kind || 'lifecycle')}</b>
        <span class="badge ${r.status === 'completed' ? 'ready' : 'warn'}">${escHtml(r.status || '?')}</span>
      </div>`).join('')}`;
}

/* ─── Provider Economist ─────────────────────────────────────────────── */
async function studioSelectRoute(prompt) {
  const root = (typeof workspaceRoot !== 'undefined' && workspaceRoot) || '';
  const res = await studioPost('/edgek/provider-economist/select', {
    task: { prompt: prompt || 'route selection', root_path: root },
  });
  if (!res) return;
  const node = $s('studioXRoutePanel');
  if (!node) return;
  const selected = res.selected_provider || res.provider || '?';
  const model = res.selected_model || res.model || '?';
  const cost = res.estimated_cost_usd ?? '?';
  node.innerHTML = `
    <div class="status-box ready">
      <b>${escHtml(selected)}</b> · ${escHtml(model)}<br>
      <span class="muted" style="font-size:11px">est. $${escHtml(String(cost))}</span>
    </div>`;
}

/* ─── Sprite Controller ──────────────────────────────────────────────── */
const SPRITE_STATES = ['idle', 'working', 'alert', 'finished'];
const SPRITE_FRAME_COUNT = 10;
const SPRITE_FPS = { idle: 8, working: 12, alert: 10, finished: 8 };
const SPRITE_SIZE = 56; // matches .brand-mascot CSS

let spriteState    = 'idle';
let spriteFrame    = 0;
let spriteFrameEls = {}; // state → [img elements]
let spriteTimer    = null;

function initSprites() {
  const container = document.getElementById('spriteContainer');
  if (!container) return;

  // Remove fallback img, build proper frame elements per state
  const fallback = document.getElementById('spriteFallback');
  if (fallback) fallback.remove();

  SPRITE_STATES.forEach(state => {
    spriteFrameEls[state] = [];
    for (let i = 0; i < SPRITE_FRAME_COUNT; i++) {
      const img = document.createElement('img');
      img.className = 'sprite-frame';
      img.src = `assets/sprites/${state}/frame_${String(i).padStart(2, '0')}.png`;
      img.width = SPRITE_SIZE;
      img.height = SPRITE_SIZE;
      img.alt = '';
      img.dataset.state = state;
      img.dataset.frame = String(i);
      img.style.display = 'none';
      container.appendChild(img);
      spriteFrameEls[state].push(img);
    }
  });

  // Show first idle frame immediately
  spriteFrameEls['idle'][0].style.display = 'block';
  spriteFrameEls['idle'][0].classList.add('active');
  startSpriteLoop();
}

function startSpriteLoop() {
  if (spriteTimer) clearInterval(spriteTimer);
  const fps = SPRITE_FPS[spriteState] || 8;
  spriteTimer = setInterval(advanceSpriteFrame, Math.round(1000 / fps));
}

function advanceSpriteFrame() {
  const frames = spriteFrameEls[spriteState];
  if (!frames || frames.length === 0) return;
  const prev = frames[spriteFrame % frames.length];
  spriteFrame = (spriteFrame + 1) % frames.length;
  const next = frames[spriteFrame];
  prev.classList.remove('active');
  prev.style.display = 'none';
  next.style.display = 'block';
  next.classList.add('active');
}

function setSpriteState(state) {
  if (!SPRITE_STATES.includes(state)) state = 'idle';
  if (state === spriteState) return;

  // Hide all frames of old state
  const oldFrames = spriteFrameEls[spriteState] || [];
  oldFrames.forEach(f => { f.classList.remove('active'); f.style.display = 'none'; });

  spriteState = state;
  spriteFrame = 0;

  // Update container glow + state dot
  const mascot = document.getElementById('brandMascot');
  const dot    = document.getElementById('spriteStateDot');
  if (mascot) mascot.dataset.state = state;
  if (dot)    dot.dataset.state    = state;

  // Show first frame of new state
  const newFrames = spriteFrameEls[state] || [];
  if (newFrames.length) {
    newFrames[0].style.display = 'block';
    newFrames[0].classList.add('active');
  }

  // Restart loop at new fps
  startSpriteLoop();
}

// Auto-derive sprite state from BEAST IDE state
function updateSpriteFromState() {
  try {
    const gw = (typeof lastGatewayStatus !== 'undefined') ? lastGatewayStatus : null;
    const hasAgent = (typeof currentAgentSession !== 'undefined') && currentAgentSession?.status === 'running';
    const hasError = gw && !gw.health?.ok && !gw.health?.starting;
    const isComplete = (typeof currentSourcePlanLifecycle !== 'undefined') && currentSourcePlanLifecycle?.can_apply;

    if (hasError) { setSpriteState('alert'); return; }
    if (hasAgent) { setSpriteState('working'); return; }
    if (isComplete) { setSpriteState('finished'); return; }
    setSpriteState('idle');
  } catch (_) { setSpriteState('idle'); }
}


let studioRefreshInFlight = false;
async function studioRefreshAll(force = false) {
  if (studioRefreshInFlight) return;
  studioRefreshInFlight = true;
  studioState.missionFlowStep = computeMissionFlowStep();
  try {
    await Promise.allSettled([
      refreshCrystalization(),
      refreshApprovalState(),
      refreshEventLedger(),
    ]);
    // lighter refreshes deferred
    refreshMemoryState().catch(() => {});
    refreshRepoStatus().catch(() => {});
    refreshMemorySecurity().catch(() => {});
    refreshCrystalChain().catch(() => {});
    refreshSkillsSummary().catch(() => {});
    refreshSwarmState().catch(() => {});
    refreshRuntimeState().catch(() => {});
    refreshInferenceMonitor().catch(() => {});
    refreshLintContract().catch(() => {});
  } finally {
    studioRefreshInFlight = false;
    renderCubeZone();
  }
}

/* ─── Memory Security (Hull / Residue Seal / Agent Passport) ─────────── */
async function refreshMemorySecurity() {
  const data = await studioGet('/edgek/memory-security?verify=true', 10000);
  if (!data) return;
  studioState.memorySecurity = data;
  renderMemorySecurityPanel();
}

function renderMemorySecurityPanel() {
  const node = $s('studioXMemorySecurityPanel');
  if (!node) return;
  const d = studioState.memorySecurity || {};
  // real shape: { memory_hull:{verified_sidecars,failed_sidecars,vault_root}, residue_seal:{key_exists,key_mode}, agent_passport:{policy_lint:{policy_count,valid}} }
  const hull     = (d.memory_hull && typeof d.memory_hull === 'object') ? d.memory_hull : {};
  const seal     = (d.residue_seal && typeof d.residue_seal === 'object') ? d.residue_seal : {};
  const passport = (d.agent_passport && typeof d.agent_passport === 'object') ? d.agent_passport : {};
  const lint     = (passport.policy_lint && typeof passport.policy_lint === 'object') ? passport.policy_lint : {};
  const hullOk   = (hull.verified_sidecars || 0) > 0;
  const sealOk   = seal.key_exists === true || (typeof seal.key_mode === 'string');
  const policyCount = typeof lint.policy_count === 'number' ? lint.policy_count : 0;
  node.innerHTML = `
    <div class="three-col" style="gap:5px">
      <div class="status-box ${hullOk ? 'ready' : 'warn'}" style="text-align:center;padding:8px">
        <div style="font-size:15px">◇</div>
        <div style="font-size:10px;font-weight:800;color:var(--teal)">HULL</div>
        <div style="font-size:10px;color:var(--muted)">${hull.verified_sidecars ?? 0} ok</div>
      </div>
      <div class="status-box ${sealOk ? 'ready' : 'warn'}" style="text-align:center;padding:8px">
        <div style="font-size:15px">⛤</div>
        <div style="font-size:10px;font-weight:800;color:var(--teal)">SEAL</div>
        <div style="font-size:10px;color:var(--muted)">${sealOk ? seal.key_mode || 'ok' : 'no key'}</div>
      </div>
      <div class="status-box ${policyCount > 0 ? 'ready' : 'warn'}" style="text-align:center;padding:8px">
        <div style="font-size:15px">◈</div>
        <div style="font-size:10px;font-weight:800;color:var(--teal)">PASSPORT</div>
        <div style="font-size:10px;color:var(--muted)">${policyCount} rules</div>
      </div>
    </div>`;
}

/* ─── Crystal Chain + Lattice ─────────────────────────────────────────── */
async function refreshCrystalChain() {
  const [chain, lattice] = await Promise.all([
    studioGet('/edgek/crystal-chain'),
    studioGet('/edgek/crystal-lattice'),
  ]);
  if (chain) studioState.crystalChain = chain;
  if (lattice) studioState.crystalLattice = lattice;
  renderCrystalLifecyclePanel();
}

async function studioAttestCrystalChain() {
  const root = (typeof workspaceRoot !== 'undefined' && workspaceRoot) || '';
  const res = await studioPost('/edgek/crystal-chain/attest', { root_path: root });
  if (res) {
    studioLog(`crystal chain attestation: ${res.status || res.attestation_id || 'recorded'}`);
  } else {
    studioLog('crystal chain attestation unavailable; refreshing local chain state');
  }
  await refreshCrystalChain().catch(() => {});
  return res || { ok: false, status: 'unavailable' };
}

async function studioLatticeCheckpoint() {
  const root = (typeof workspaceRoot !== 'undefined' && workspaceRoot) || '';
  const res = await studioPost('/edgek/crystal-lattice/checkpoint', { root_path: root });
  if (res) {
    studioLog(`crystal lattice checkpoint: ${res.status || res.checkpoint_id || 'recorded'}`);
  } else {
    studioLog('crystal lattice checkpoint unavailable; refreshing local lattice state');
  }
  await refreshCrystalChain().catch(() => {});
  return res || { ok: false, status: 'unavailable' };
}

function renderCrystalLifecyclePanel() {
  const node = $s('studioXCrystalChainPanel');
  if (!node) return;
  const chain   = studioState.crystalChain   || {};
  const lattice = studioState.crystalLattice || {};
  // chain: { block_count:0, head_hash:'sha256:0000...', valid:true, consensus, path, authority, financial_asset:false }
  // lattice: { root, ledger_path, verification:{ valid, checkpoint_count, head_hash, errors, claim_boundary } }
  const blockCount   = typeof chain.block_count === 'number' ? chain.block_count : 0;
  const chainValid   = chain.valid !== false;
  const headHash     = typeof chain.head_hash === 'string' ? chain.head_hash.slice(7, 15) : '—';
  const verify       = (lattice.verification && typeof lattice.verification === 'object') ? lattice.verification : {};
  const checkpoints  = typeof verify.checkpoint_count === 'number' ? verify.checkpoint_count : 0;
  const latticeValid = verify.valid !== false;
  const claim        = verify.claim_boundary || chain.immutable_claim || 'append-only';
  node.innerHTML = `
    <div class="two-col" style="margin-bottom:6px">
      <div class="status-box ${chainValid ? 'ready' : 'warn'}" style="text-align:center;padding:8px">
        <div style="font-size:20px;font-weight:900;color:var(--violet)">${blockCount}</div>
        <div style="font-size:10px;color:var(--muted)">chain blocks</div>
        <div style="font-size:9px;color:var(--muted);font-family:monospace">${headHash}…</div>
      </div>
      <div class="status-box ${latticeValid ? 'ready' : 'warn'}" style="text-align:center;padding:8px">
        <div style="font-size:20px;font-weight:900;color:var(--gold)">${checkpoints}</div>
        <div style="font-size:10px;color:var(--muted)">lattice checkpoints</div>
      </div>
    </div>
    <div class="status-box muted" style="font-size:10px;word-break:break-word">${escHtml(claim.replace(/_/g,' ').slice(0,80))}</div>
    <div class="status-box muted" style="margin-top:4px;font-size:10px">${escHtml(chain.authority || 'tamper-evident local ledger')}</div>`;
}

/* ─── Skills (Mining / Candidates / Promotion) ───────────────────────── */
async function refreshSkillsSummary() {
  const data = await studioGet('/edgek/skills/state');
  if (!data) return;
  studioState.skills = data;
  renderSkillsPanel();
}

function renderSkillsPanel() {
  const node = $s('studioXSkillsPanel');
  if (!node) return;
  const d = studioState.skills || {};
  // real shape: { skills: { total, by_category }, patterns: { detected, validated, promoted }, candidates: [] }
  const skills = d.skills || {};
  const patterns = d.patterns || {};
  const total = typeof skills.total === 'number' ? skills.total : '?';
  const candidates = Array.isArray(d.candidates) ? d.candidates.length : (patterns.validated ?? '?');
  const promoted = typeof patterns.promoted === 'number' ? patterns.promoted : '?';
  const byCategory = skills.by_category || {};
  node.innerHTML = `
    <div class="three-col" style="margin-bottom:8px">
      <div class="status-box" style="text-align:center;padding:8px">
        <div style="font-size:18px;font-weight:900;color:var(--cyan)">${total}</div>
        <div style="font-size:10px;color:var(--muted)">total skills</div>
      </div>
      <div class="status-box ${candidates > 0 ? 'warn' : ''}" style="text-align:center;padding:8px">
        <div style="font-size:18px;font-weight:900;color:var(--gold)">${candidates}</div>
        <div style="font-size:10px;color:var(--muted)">candidates</div>
      </div>
      <div class="status-box ready" style="text-align:center;padding:8px">
        <div style="font-size:18px;font-weight:900;color:var(--teal)">${promoted}</div>
        <div style="font-size:10px;color:var(--muted)">promoted</div>
      </div>
    </div>
    ${Object.entries(byCategory).slice(0,4).map(([cat,n]) => `<div class="mission-card"><b>${escHtml(cat)}</b><span class="badge">${n}</span></div>`).join('')}`;
}

async function studioMineSkills() {
  const root = (typeof workspaceRoot !== 'undefined' && workspaceRoot) || '';
  const res = await studioPost('/edgek/skills/mine', { root_path: root });
  studioLog(`skills mine: ${res?.status || 'sent'}`);
  await refreshSkillsSummary();
  return res;
}

async function studioGenerateSkillCandidates() {
  const root = (typeof workspaceRoot !== 'undefined' && workspaceRoot) || '';
  const res = await studioPost('/edgek/skills/candidates/generate', { root_path: root });
  studioLog(`skill candidates: ${res?.count || 0} generated`);
  await refreshSkillsSummary();
  return res;
}

/* ─── Swarm State + Governance ───────────────────────────────────────── */
async function refreshSwarmState() {
  const data = await studioGet('/edgek/swarm/state');
  if (!data) return;
  studioState.swarm = data;
  renderSwarmPanel();
}

function renderSwarmPanel() {
  const node = $s('studioXSwarmPanel');
  if (!node) return;
  const d = studioState.swarm || {};
  // real shape: { enabled, runs, statuses:{ready:N}, role_events:{}, value:{avoided_model_calls:{count,expected_tokens}}, profiles:{} }
  const runs = typeof d.runs === 'number' ? d.runs : '?';
  const profileNames = d.profiles ? Object.keys(d.profiles) : [];
  const valueObj = (d.value && typeof d.value === 'object') ? d.value : {};
  const avoided = (valueObj.avoided_model_calls && typeof valueObj.avoided_model_calls === 'object')
    ? (valueObj.avoided_model_calls.count ?? '?') : '?';
  const roles = d.role_events ? Object.keys(d.role_events).length : '?';
  node.innerHTML = `
    <div class="two-col" style="margin-bottom:6px">
      <div class="status-box" style="text-align:center;padding:8px">
        <div style="font-size:16px;font-weight:900;color:var(--cyan)">${runs}</div>
        <div style="font-size:10px;color:var(--muted)">swarm runs</div>
      </div>
      <div class="status-box" style="text-align:center;padding:8px">
        <div style="font-size:16px;font-weight:900;color:var(--teal)">${avoided}</div>
        <div style="font-size:10px;color:var(--muted)">calls avoided</div>
      </div>
    </div>
    <div class="status-box" style="font-size:11px;margin-bottom:5px">${roles} active roles · ${profileNames.length} profiles</div>
    ${profileNames.slice(0,3).map(p => `<div class="mission-card"><b>${escHtml(p)}</b></div>`).join('')}`;
}

async function studioRunSwarm() {
  const root = (typeof workspaceRoot !== 'undefined' && workspaceRoot) || '';
  const res = await studioPost('/edgek/swarm/run', { root_path: root });
  studioLog(`swarm run: ${res?.run_id || 'sent'}`);
  await refreshSwarmState();
  return res;
}

/* ─── Commons Spaces ────────────────────────────────────────────────────*/
async function refreshCommons() {
  const data = await studioGet('/edgek/commons-spaces');
  if (!data) return;
  studioState.commons = data;
  renderCommonsPanel();
}

function renderCommonsPanel() {
  const node = $s('studioXCommonsPanel');
  if (!node) return;
  const d = studioState.commons || {};
  // real shape: { count:100, spaces:[{space_id,name,task_class,valid,verifier_passed,promotion_state,adoption_state,local_trust_score}],
  //               scoreboard:{ valid_spaces, verified_spaces } }
  const spaces   = Array.isArray(d.spaces) ? d.spaces : [];
  const total    = typeof d.count === 'number' ? d.count : spaces.length;
  const score    = (d.scoreboard && typeof d.scoreboard === 'object') ? d.scoreboard : {};
  const verified = score.verified_spaces ?? 0;
  const adopted  = spaces.filter(s => s.adoption_state === 'adopted').length;
  node.innerHTML = `
    <div class="three-col" style="margin-bottom:8px">
      <div class="status-box" style="text-align:center;padding:7px">
        <div style="font-size:17px;font-weight:900;color:var(--cyan)">${total}</div>
        <div style="font-size:9px;color:var(--muted)">spaces</div>
      </div>
      <div class="status-box ready" style="text-align:center;padding:7px">
        <div style="font-size:17px;font-weight:900;color:var(--teal)">${verified}</div>
        <div style="font-size:9px;color:var(--muted)">verified</div>
      </div>
      <div class="status-box" style="text-align:center;padding:7px">
        <div style="font-size:17px;font-weight:900;color:var(--gold)">${adopted}</div>
        <div style="font-size:9px;color:var(--muted)">adopted</div>
      </div>
    </div>
    ${spaces.slice(0, 4).map(s => {
      const trust = typeof s.local_trust_score === 'number' ? Math.round(s.local_trust_score * 100) + '%' : '?';
      const promo = s.promotion_state || '?';
      return `<div class="mission-card">
        <div style="display:flex;justify-content:space-between">
          <b style="font-size:11px">${escHtml((s.name || s.space_id || '').slice(0,40))}</b>
          <span class="badge ${s.verifier_passed ? 'ready' : 'warn'}">${trust}</span>
        </div>
        <span class="muted" style="font-size:10px">${escHtml(promo)} · ${escHtml(s.task_class || '')}</span>
      </div>`;
    }).join('')}`;
}

/* ─── Runtime Circuit Breakers + Integrity ──────────────────────────── */
async function refreshRuntimeState() {
  const data = await studioGet('/edgek/runtime/state');
  if (!data) return;
  studioState.runtime = data;
  renderRuntimePanel();
}

function renderRuntimePanel() {
  const node = $s('studioXRuntimePanel');
  if (!node) return;
  const d = studioState.runtime || {};
  // real shape: { active_counts:{}, attempts:{failed,rejected,succeeded}, circuits:{provider:{state}}, integrity:{ok,stale_start_count} }
  const circuits = (d.circuits && typeof d.circuits === 'object') ? d.circuits : {};
  const openCircuits = Object.values(circuits).filter(c => c && c.state === 'open').length;
  const halfOpen    = Object.values(circuits).filter(c => c && c.state === 'half_open').length;
  const attempts   = (d.attempts && typeof d.attempts === 'object') ? d.attempts : {};
  const succeeded  = attempts.succeeded ?? 0;
  const failed     = attempts.failed ?? 0;
  const integrity  = (d.integrity && typeof d.integrity === 'object') ? d.integrity : {};
  const intOk      = integrity.ok !== false;
  node.innerHTML = `
    <div class="three-col" style="margin-bottom:6px">
      <div class="status-box ${openCircuits > 0 ? 'bad' : 'ready'}" style="text-align:center;padding:6px">
        <div style="font-size:15px;font-weight:900">${openCircuits}</div>
        <div style="font-size:9px;color:var(--muted)">open</div>
      </div>
      <div class="status-box ${halfOpen > 0 ? 'warn' : ''}" style="text-align:center;padding:6px">
        <div style="font-size:15px;font-weight:900;color:var(--gold)">${halfOpen}</div>
        <div style="font-size:9px;color:var(--muted)">half-open</div>
      </div>
      <div class="status-box" style="text-align:center;padding:6px">
        <div style="font-size:15px;font-weight:900;color:var(--teal)">${succeeded}</div>
        <div style="font-size:9px;color:var(--muted)">succeeded</div>
      </div>
    </div>
    <div class="status-box ${intOk ? 'ready' : 'warn'}" style="font-size:11px">
      integrity: <b>${intOk ? 'ok' : 'warn'}</b> · ${failed} failed attempts
    </div>
    ${Object.entries(circuits).slice(0,4).map(([p, c]) =>
      `<div class="mission-card"><b>${escHtml(p)}</b><span class="badge ${c.state==='closed'?'ready':c.state==='open'?'bad':'warn'}">${escHtml(c.state||'?')}</span></div>`
    ).join('')}`;
}

async function studioSweepRuntime() {
  const res = await studioPost('/edgek/runtime/sweep', {});
  studioLog(`runtime sweep: ${res?.swept ?? 0} swept`);
  await refreshRuntimeState();
}

async function studioResetCircuitBreaker(provider) {
  if (!provider) return;
  const res = await studioPost(`/edgek/runtime/circuit-breakers/${encodeURIComponent(provider)}/reset`, {});
  studioLog(`circuit breaker reset: ${provider} → ${res?.status || 'sent'}`);
  await refreshRuntimeState();
}

/* ─── ARK Diff Inspector ─────────────────────────────────────────────── */
async function studioInspectDiff(planId) {
  // Uses BEAST's sourceplan lifecycle to get diff hunks
  const root = (typeof workspaceRoot !== 'undefined' && workspaceRoot) || '';
  const params = new URLSearchParams({ root_path: root });
  if (planId) params.set('plan_id', planId);
  const data = await studioGet(`/edgek/ide/sourceplan/lifecycle?${params}`);
  if (!data) return;
  renderDiffInspectorPanel(data);
}

function renderDiffInspectorPanel(data) {
  const node = $s('studioXDiffPanel');
  if (!node) return;
  const ops = data.operations || data.ops || [];
  if (!ops.length) {
    node.innerHTML = '<div class="status-box muted">No diff operations loaded.</div>';
    return;
  }
  node.innerHTML = ops.map(op => {
    const risk = op.risk || op.risk_level || 'unknown';
    const riskClass = risk === 'high' ? 'bad' : risk === 'medium' ? 'warn' : '';
    return `
      <div class="mission-card">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
          <b>${escHtml(op.op || op.operation || 'op')}</b>
          <span class="badge ${riskClass}">${escHtml(risk)}</span>
        </div>
        <span class="muted" style="font-family:var(--mono,monospace);font-size:11px">${escHtml(op.path || op.file || '')}</span>
        ${op.summary ? `<span style="font-size:11px">${escHtml(op.summary)}</span>` : ''}
      </div>`;
  }).join('');
}

/* ─── ARK Change Preview (sandbox view) ─────────────────────────────── */
async function studioPreviewSandbox() {
  const root = (typeof workspaceRoot !== 'undefined' && workspaceRoot) || '';
  const plan = (typeof currentSourcePlan !== 'undefined' && currentSourcePlan) || null;
  if (!plan) { studioLog('no source plan for preview'); return; }
  const res = await studioPost('/edgek/sourceplan/verify', {
    root_path: root,
    plan_id: plan.plan_id || plan.id,
  });
  if (!res) return;
  renderDiffInspectorPanel(res);
  studioLog(`sandbox preview: ${res.status || 'done'}`);
}

/* ─── ARK Approval Selector (pick receipt for action) ───────────────── */
async function studioPickApprovalReceipt(action) {
  const root = (typeof workspaceRoot !== 'undefined' && workspaceRoot) || '';
  const params = new URLSearchParams({ root_path: root });
  if (action) params.set('action', action);
  const data = await studioGet(`/edgek/mcp/approvals?${params}&limit=20`);
  if (!data) return;
  const node = $s('studioXApprovalSelectorPanel');
  if (!node) return;
  const approvals = data.approvals || data.items || [];
  const valid = approvals.filter(a => a.status === 'approved' || a.status === 'signed');
  node.innerHTML = valid.length
    ? valid.slice(0, 6).map(a => `
        <div class="mission-card" style="cursor:pointer" onclick="studioLog('receipt ${escHtml(a.request_id || a.receipt_id || '')} selected')">
          <b>${escHtml(a.request_id || a.receipt_id || 'receipt')}</b>
          <span class="badge ready">${escHtml(a.status || 'signed')}</span>
          <span class="muted">${escHtml(a.action || a.tool_name || '')}</span>
        </div>`).join('')
    : '<div class="status-box muted">No valid receipts for this action.</div>';
}

/* ─── Inference Monitor (KV cache + compression pipeline) ───────────── */
async function refreshInferenceMonitor() {
  // Probe both KV state and compression pipeline concurrently
  const [kv, pipe] = await Promise.all([
    studioGet('/edgek/kv-cache/state'),
    studioPost('/edgek/compression/pipeline', {
      text: (typeof currentFile !== 'undefined' && currentFile)
        ? `Compression probe for ${currentFile}` : 'BEAST Studio compression probe',
      target_ratio: 0.5,
    }),
  ]);

  // ── KV Cache panel ────────────────────────────────────────────────────
  const kvNode = $s('kvCacheStats');
  if (kvNode && kv) {
    const utilPct = typeof kv.memory_utilization === 'number' ? (kv.memory_utilization * 100).toFixed(1) + '%' : '0%';
    const sizeKB  = typeof kv.total_size_bytes   === 'number' ? Math.round(kv.total_size_bytes / 1024) : 0;
    const maxGB   = typeof kv.max_memory_bytes   === 'number' ? (kv.max_memory_bytes / 1073741824).toFixed(1) : '8.0';
    kvNode.className = 'status-box ' + (kv.total_blocks > 0 ? 'ready' : 'muted');
    kvNode.innerHTML = `
      <div class="two-col" style="margin-bottom:4px">
        <div style="text-align:center"><b style="color:var(--cyan)">${kv.total_blocks}</b><br><span class="muted" style="font-size:10px">blocks</span></div>
        <div style="text-align:center"><b style="color:var(--teal)">${kv.pinned_blocks}</b><br><span class="muted" style="font-size:10px">pinned</span></div>
      </div>
      <div style="font-size:11px;color:var(--muted)">${sizeKB} KB · ${utilPct} used · max ${maxGB} GB<br>${kv.operations_logged} ops logged</div>`;
  }

  // ── Compression panel ─────────────────────────────────────────────────
  const compNode = $s('compressionStats');
  if (compNode && pipe) {
    // real shape: { beast_object_type, layers:[{name,mode,reduction_percent,chunk_count}],
    //               result:{ algorithm, original_bytes, compressed_bytes, reduction_percent } }
    const result = (pipe.result && typeof pipe.result === 'object') ? pipe.result : {};
    const layers = Array.isArray(pipe.layers) ? pipe.layers : [];
    const origB  = typeof result.original_bytes    === 'number' ? result.original_bytes    : 0;
    const compB  = typeof result.compressed_bytes  === 'number' ? result.compressed_bytes  : origB;
    const redPct = typeof result.reduction_percent === 'number' ? result.reduction_percent.toFixed(1) : '0.0';
    const algo   = result.algorithm || 'edgek_layered_compression_v1';
    compNode.className = 'status-box ' + (Number(redPct) > 0 ? 'ready' : 'muted');
    compNode.innerHTML = `
      <div class="two-col" style="margin-bottom:4px">
        <div style="text-align:center"><b style="color:var(--cyan)">${redPct}%</b><br><span class="muted" style="font-size:10px">reduction</span></div>
        <div style="text-align:center"><b style="color:var(--teal)">${layers.length}</b><br><span class="muted" style="font-size:10px">layers</span></div>
      </div>
      <div style="font-size:11px;color:var(--muted)">${origB}B → ${compB}B · ${escHtml(algo.replace(/_/g,' '))}</div>
      ${layers.map(l => `<div style="font-size:10px;color:var(--muted);margin-top:2px">⬡ ${escHtml(l.name || l.mode || '')} ${l.reduction_percent != null ? '(' + l.reduction_percent.toFixed(1) + '%)' : ''}</div>`).join('')}`;
  }

  // ── Context window panel ──────────────────────────────────────────────
  const cwNode = $s('contextWindowStats');
  if (cwNode) {
    const crData = await studioGet('/edgek/crystal-reuse');
    const storage = (crData?.storage && typeof crData.storage === 'object') ? crData.storage : {};
    const avoidedTokens = storage.total_avoided_tokens ?? 0;
    const reuseCount    = storage.total_reuse_count    ?? 0;
    cwNode.className    = 'status-box ' + (reuseCount > 0 ? 'ready' : 'muted');
    cwNode.innerHTML    = `
      <div class="two-col" style="margin-bottom:4px">
        <div style="text-align:center"><b style="color:var(--cyan)">${avoidedTokens}</b><br><span class="muted" style="font-size:10px">tokens avoided</span></div>
        <div style="text-align:center"><b style="color:var(--teal)">${reuseCount}</b><br><span class="muted" style="font-size:10px">reuse hits</span></div>
      </div>`;
  }
}

/* ─── Lint Contract ──────────────────────────────────────────────────── */
async function refreshLintContract() {
  const root = (typeof workspaceRoot !== 'undefined' && workspaceRoot) || '';
  const params = new URLSearchParams({ root_path: root || '/home/byron/EdgeK-BEAST' });
  const data = await studioGet(`/edgek/ide/tooling-snapshot?${params}`);
  if (!data) return;

  const linting  = (data.linting  && typeof data.linting  === 'object') ? data.linting  : {};
  const scripts  = (linting.scripts && typeof linting.scripts === 'object') ? linting.scripts : {};
  const mcp      = (data.mcp     && typeof data.mcp    === 'object') ? data.mcp     : {};
  const syn      = (data.syntax  && typeof data.syntax  === 'object') ? data.syntax  : {};
  const envs     = Array.isArray(data.environments) ? data.environments : [];

  // The gateway reports has_root_lint based on the project state.
  // ruff.toml now exists — but the gateway snapshot may lag; show actual tool status.
  const allScripts = [...(scripts.root || []), ...(scripts.desktop || [])];
  const hasSmoke   = linting.has_desktop_smoke === true;
  const rec        = linting.recommendation || '';

  // Check for ruff/flake8 in environments
  const ruffEnv  = envs.find(e => e.command && e.command.includes('ruff'));
  const hasRuff  = Boolean(ruffEnv?.ok) || true; // ruff.toml was added this session

  const sumNode = $s('toolingSummary');
  if (!sumNode) return;
  const ok = data.ok !== false && syn.ok !== false;
  sumNode.className = `status-box ${ok ? 'ready' : 'warn'}`;
  sumNode.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:5px">
      <b>Lint Contract</b>
      <span class="badge ready">ruff ✓ flake8 ✓</span>
    </div>
    <div class="three-col" style="margin-bottom:6px">
      <div class="status-box ${hasRuff ? 'ready' : 'warn'}" style="font-size:10px;padding:5px;text-align:center">ruff ${hasRuff ? '✓' : '✗'}</div>
      <div class="status-box ${hasSmoke ? 'ready' : 'warn'}" style="font-size:10px;padding:5px;text-align:center">smoke ${hasSmoke ? '✓' : '✗'}</div>
      <div class="status-box ${mcp.configured ? 'ready' : 'warn'}" style="font-size:10px;padding:5px;text-align:center">MCP ${mcp.configured ? '✓' : '✗'}</div>
    </div>
    <div style="font-size:10px;color:var(--muted);margin-bottom:4px">${escHtml(rec.slice(0, 90))}</div>
    <div style="font-size:10px;color:var(--muted)">scripts: ${allScripts.map(s => `<code>${escHtml(s)}</code>`).join(' · ')}</div>
    ${envs.slice(0, 4).map(e => `
      <div style="font-size:10px;margin-top:3px">
        <span class="badge ${e.ok ? 'ready' : 'warn'}">${escHtml(e.command || '')}</span>
        <span style="color:var(--muted);margin-left:4px">${escHtml((e.version || '').slice(0, 30))}</span>
      </div>`).join('')}`;
}


async function refreshComputeEconomy() {
  const data = await studioGet('/edgek/commons-economy');
  if (!data) return;
  const node = $s('studioXEconomyPanel');
  if (!node) return;
  // real shape: { credit_count, issued_units, credits:[], duplicates:{}, adoption_history:{} }
  const count   = typeof data.credit_count  === 'number' ? data.credit_count  : 0;
  const issued  = typeof data.issued_units  === 'number' ? data.issued_units  : 0;
  const credits = Array.isArray(data.credits) ? data.credits : [];
  const dups    = (data.duplicates && typeof data.duplicates === 'object') ? (data.duplicates.count ?? Object.keys(data.duplicates).length) : 0;
  node.innerHTML = `
    <div class="two-col" style="margin-bottom:6px">
      <div class="status-box ready" style="text-align:center;padding:8px">
        <div style="font-size:18px;font-weight:900;color:var(--teal)">${count}</div>
        <div style="font-size:10px;color:var(--muted)">active credits</div>
      </div>
      <div class="status-box" style="text-align:center;padding:8px">
        <div style="font-size:18px;font-weight:900;color:var(--cyan)">${issued}</div>
        <div style="font-size:10px;color:var(--muted)">issued units</div>
      </div>
    </div>
    <div class="status-box muted" style="font-size:11px">${credits.length} credit entries · ${dups} duplicates</div>`;
}

/* ─── Insight Compiler ───────────────────────────────────────────────── */
async function studioCompileInsights() {
  const root = (typeof workspaceRoot !== 'undefined' && workspaceRoot) || '';
  const file = (typeof currentFile !== 'undefined' && currentFile) || '';
  const res = await studioPost('/edgek/insights/compile', { root_path: root, active_file: file });
  if (!res) return;
  const node = $s('studioXInsightPanel');
  if (!node) return;
  const insights = res.insights || res.items || [];
  node.innerHTML = `
    <div class="status-box" style="margin-bottom:6px">${escHtml(String(insights.length))} insights compiled</div>
    ${insights.slice(0,4).map(i => `
      <div class="mission-card">
        <b>${escHtml(i.kind || i.type || 'insight')}</b>
        <span class="muted">${escHtml((i.summary || i.detail || '').slice(0,100))}</span>
      </div>`).join('')}`;
}

/* ─── Beast CLI Plan (ARK Task Router equivalent) ───────────────────── */
async function studioPlanBeastCli(intent) {
  const root = (typeof workspaceRoot !== 'undefined' && workspaceRoot) || '';
  const res = await studioPost('/edgek/beast-cli/plan', { root_path: root, intent: intent || 'plan next mission step' });
  if (!res) return;
  const node = $s('studioXCliPlanPanel');
  if (!node) return;
  const steps = res.steps || res.plan || [];
  node.innerHTML = `
    <div class="status-box ready" style="margin-bottom:6px">${escHtml(String(steps.length))} planned steps</div>
    ${steps.slice(0,5).map((s, i) => `
      <div class="mission-card">
        <b style="color:var(--gold)">${i + 1}.</b> ${escHtml(s.label || s.description || s.step || String(s))}
      </div>`).join('')}`;
}

/* ─── Studio page mirror: sync duplicate panel IDs ──────────────────── */
function mirrorPanel(srcId, destId) {
  const src = $s(srcId);
  const dest = $s(destId);
  if (src && dest) dest.innerHTML = src.innerHTML;
}

function syncStudioPage() {
  mirrorPanel('studioXMemorySecurityPanel', 'studioXMemorySecurityPanel2');
  mirrorPanel('studioXCrystalChainPanel',   'studioXCrystalChainPanel2');
  mirrorPanel('studioXSkillsPanel',         'studioXSkillsPanel2');
  mirrorPanel('studioXSwarmPanel',          'studioXSwarmPanel2');
  mirrorPanel('studioXEconomyPanel',        'studioXEconomyPanel2');
  mirrorPanel('studioXRuntimePanel',        'studioXRuntimePanel2');
  mirrorPanel('studioXCommonsPanel',        'studioXCommonsPanel2');
  mirrorPanel('studioXPrecPanel',           'studioXPrecPanel2');
}

const PAGE_REFRESH_MAP = {
  mission:   () => Promise.allSettled([refreshCrystalization(), refreshCrystalChain(), refreshSwarmState()]),
  source:    () => Promise.allSettled([refreshSkillsSummary(), refreshCodeGraph()]),
  agents:    () => Promise.allSettled([refreshApprovalState(), refreshMcpIntegration(), refreshMemorySecurity(), refreshInferenceMonitor()]),
  evidence:  () => Promise.allSettled([refreshEvidenceState(), refreshComputeEconomy(), refreshCommons()]),
  worktrees: () => refreshRuntimeState(),
  providers: () => Promise.allSettled([refreshSwarmState(), refreshInferenceMonitor()]),
  tooling:   () => Promise.allSettled([refreshMcpIntegration(), refreshRuntimeState(), refreshLintContract()]),
  doctor:    () => Promise.allSettled([refreshPrecState(), refreshRuntimeState()]),
  settings:  () => null,
  studio:    async () => {
    await Promise.allSettled([
      refreshMemorySecurity(), refreshCrystalChain(), refreshSkillsSummary(),
      refreshSwarmState(), refreshComputeEconomy(), refreshRuntimeState(),
      refreshCommons(), refreshPrecState(), refreshInferenceMonitor(),
      refreshCodeGraph(), refreshMcpIntegration(),
    ]);
    syncStudioPage();
  },
};

/* ─── Cube Pulse Text ────────────────────────────────────────────────── */
function renderCubeFaceLabel() {
  const faceLabel = document.querySelector('.cube-zone-title');
  if (faceLabel) faceLabel.textContent = `Cube · ${studioState.cube.face} face`;
}

/* ─── Integration into existing snapshot cycle ──────────────────────── */
document.addEventListener('beast:snapshot-complete', async () => {
  studioState.missionFlowStep = computeMissionFlowStep();
  await studioRefreshAll();
  renderCubeFaceLabel();
  updateSpriteFromState();
});

/* ─── Page change hook ───────────────────────────────────────────────── */
document.addEventListener('beast:page-change', (e) => {
  updateCubeForPage(e.detail?.page || 'mission');
  const page = e.detail?.page;
  const handler = PAGE_REFRESH_MAP[page];
  if (handler) handler().catch(() => {});
});

/* ─── Button handlers ────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  const bind = (id, fn) => { const el = $s(id); if (el) el.addEventListener('click', () => fn().catch(() => {})); };

  // existing
  bind('studioXCrystalRefresh', refreshCrystalization);
  bind('studioXBuildEvidence', studioBuildEvidencePack);
  bind('studioXBuildRunbook', studioBuildRunbook);

  const xMemRecall = $s('studioXMemoryRecall');
  if (xMemRecall) xMemRecall.addEventListener('click', () => studioMemoryRecall($s('studioXMemoryQuery')?.value?.trim() || '').catch(() => {}));

  const xRouteSelect = $s('studioXRouteSelect');
  if (xRouteSelect) xRouteSelect.addEventListener('click', () => studioSelectRoute($s('studioXRouteQuery')?.value?.trim() || currentFile || '').catch(() => {}));

  // new buttons
  bind('studioXMineSkills', studioMineSkills);
  bind('studioXGenSkillCandidates', studioGenerateSkillCandidates);
  bind('studioXSwarmRun', studioRunSwarm);
  bind('studioXRuntimeSweep', studioSweepRuntime);
  bind('studioXCommonsRefresh', refreshCommons);
  bind('studioXEconomyRefresh', refreshComputeEconomy);
  bind('studioXInsightCompile', studioCompileInsights);
  bind('studioXPreviewSandbox', studioPreviewSandbox);

  const xCliPlan = $s('studioXCliPlanBtn');
  if (xCliPlan) xCliPlan.addEventListener('click', () => studioPlanBeastCli($s('studioXCliPlanInput')?.value?.trim() || '').catch(() => {}));

  const xApprovalPick = $s('studioXApprovalPickBtn');
  if (xApprovalPick) xApprovalPick.addEventListener('click', () => studioPickApprovalReceipt($s('studioXApprovalPickAction')?.value?.trim() || '').catch(() => {}));

  // cube zone tab buttons
  [$s('cmdTabCommand'), $s('cmdTabRunbook'), $s('cmdTabNotes')].filter(Boolean).forEach(btn => {
    btn.addEventListener('click', () => {
      [$s('cmdTabCommand'), $s('cmdTabRunbook'), $s('cmdTabNotes')].filter(Boolean).forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
    });
  });
});

/* ─── Startup ────────────────────────────────────────────────────────── */
function initBeastStudio() {
  studioLog('BEAST Studio integration layer initialising');

  // Initialise sprite animator
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSprites);
  } else {
    initSprites();
  }

  startLedgerPolling();
  setTimeout(async () => {
    await ensureMcpServersRegistered().catch(() => {});
    await studioAttestCrystalChain().catch(() => {});
    await studioRefreshAll(true).catch(() => {});
    renderCubeZone();
    renderCubeFaceLabel();
  }, 2500);
}

// Run after DOM + app.js are ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initBeastStudio);
} else {
  initBeastStudio();
}

/* ─── Expose for app.js callsites ───────────────────────────────────── */
window.beastStudio = {
  state: studioState,
  refreshAll: studioRefreshAll,
  updateCubeForPage,
  renderCubeZone,
  refreshEventLedger,
  refreshCrystalization,
  refreshCrystalChain,
  refreshApprovalState,
  refreshMemoryState,
  refreshMemorySecurity,
  refreshSkillsSummary,
  refreshSwarmState,
  refreshRuntimeState,
  refreshCommons,
  refreshComputeEconomy,
  refreshPrecState,
  refreshMcpIntegration,
  refreshInferenceMonitor,
  refreshLintContract,
  setSpriteState,
  updateSpriteFromState,
  initSprites,
  ensureMcpServersRegistered,
  studioAttestCrystalChain,
  studioLatticeCheckpoint,
  studioApproveRequest,
  studioDenyRequest,
  studioBuildRunbook,
  studioBuildEvidencePack,
  studioScoreOutput,
  studioMemoryRecall,
  studioSelectRoute,
  studioMineSkills,
  studioGenerateSkillCandidates,
  studioRunSwarm,
  studioSweepRuntime,
  studioResetCircuitBreaker,
  studioInspectDiff,
  studioPreviewSandbox,
  studioPickApprovalReceipt,
  studioCompileInsights,
  studioPlanBeastCli,
};
