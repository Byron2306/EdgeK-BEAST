// PHASE5_UI_ALIGNMENT: shared durable operations console client.
(() => {
  const cache = new Map();
  const cursors = new Map();
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
  const rootPath = () => BeastStore.get().workspace.root || '';
  const activeRunId = () => String(BeastStore.get().aiCoding.activeRunId || BeastStore.get().aiCoding.sessionId || '').trim();
  const request = (path, options = {}) => BeastRuntime.request(path, { timeoutMs:12000, ...options });
  const runPath = (runId, suffix) => `/edgek/agent-runs/${encodeURIComponent(runId)}/${suffix}`;

  async function load(runId = activeRunId(), { force = false } = {}) {
    if (!runId) return { run_id:'', unavailable:true, reason:'No durable AgentRun selected.' };
    const key = `${rootPath()}::${runId}`;
    if (!force && cache.has(key)) return cache.get(key);
    const payload = await request(runPath(runId, 'console') + `?root_path=${encodeURIComponent(rootPath())}`);
    cache.set(key, payload);
    return payload;
  }

  async function loadSurface(surface, runId = activeRunId(), params = {}) {
    if (!runId) return { run_id:'', unavailable:true, reason:'No durable AgentRun selected.' };
    const query = new URLSearchParams({ root_path:rootPath(), ...Object.fromEntries(Object.entries(params).filter(([,v]) => v !== '' && v != null)) });
    return request(runPath(runId, `console/${surface}`) + `?${query}`);
  }

  async function loadMission(runId = activeRunId()) {
    if (!runId) return null;
    return request(runPath(runId, 'objective-plan') + `?root_path=${encodeURIComponent(rootPath())}`);
  }

  async function getMode(runId = activeRunId()) {
    if (!runId) return null;
    return request(runPath(runId, 'mode') + `?root_path=${encodeURIComponent(rootPath())}`);
  }

  async function transitionMode(toMode, { runId = activeRunId(), reason = 'Operator changed Pair Programmer mode', conversionConfirmed = false } = {}) {
    if (!runId) throw new Error('Start or select a durable AgentRun before changing governed mode.');
    return request(runPath(runId, 'mode') + `?root_path=${encodeURIComponent(rootPath())}`, {
      method:'POST',
      body:{ to_mode:String(toMode || '').toUpperCase(), operator_id:'operator:desktop', reason, conversion_confirmed:Boolean(conversionConfirmed) }
    });
  }

  async function decideContext(itemId, decision, { runId = activeRunId(), provider = '', reason = 'Operator context decision' } = {}) {
    if (!runId) throw new Error('No durable AgentRun selected.');
    return request(runPath(runId, `context-manifest/items/${encodeURIComponent(itemId)}/decision`) + `?root_path=${encodeURIComponent(rootPath())}`, {
      method:'POST', body:{ decision, operator_id:'operator:desktop', reason, provider }
    });
  }

  async function timeline(runId = activeRunId(), { reset = false, ...params } = {}) {
    if (!runId) return { events:[], unavailable:true };
    const key = `${rootPath()}::${runId}`;
    if (reset) cursors.delete(key);
    const cursor = params.cursor ?? cursors.get(key) ?? '';
    const payload = await loadSurface('timeline', runId, { view:'expanded', limit:100, ...params, cursor });
    if (payload?.next_cursor) cursors.set(key, payload.next_cursor);
    return payload;
  }

  function invalidate(runId = activeRunId()) {
    if (!runId) return;
    cache.delete(`${rootPath()}::${runId}`);
  }

  window.BeastOperationsConsole = Object.freeze({
    activeRunId, rootPath, load, loadSurface, loadMission, getMode, transitionMode,
    decideContext, timeline, invalidate, esc
  });
})();
