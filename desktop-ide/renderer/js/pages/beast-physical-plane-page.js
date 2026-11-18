/* Physical Plane: one byte budget, the crystal KV tier, and the reclaim ladder.
 *
 * Every number on this surface comes from a live gateway receipt.  Where the
 * backend cannot probe a value it reports null and the UI prints UNPROBED,
 * never a zero dressed up as a measurement.
 */
(() => {
  const esc = value => String(value ?? '—').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));

  const POOLS = [
    ['gpu_vram', 'GPU VRAM', 'RTX 3050 · nvidia-smi'],
    ['host_ram', 'Host RAM', '/proc/meminfo MemAvailable'],
    ['swap', 'Swap', '/proc/swaps SwapFree'],
    ['nvme_kv', 'NVMe KV', 'statvfs on the crystal root'],
    ['memfd', 'memfd', 'anonymous crystals'],
  ];

  function mib(bytes) {
    if (bytes === null || bytes === undefined) return 'UNPROBED';
    const value = Number(bytes);
    if (!Number.isFinite(value)) return 'UNPROBED';
    if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(2)} GiB`;
    return `${(value / 1024 ** 2).toFixed(1)} MiB`;
  }

  function bytesParam(input) {
    const raw = String(input || '').trim();
    if (!raw) return null;
    const match = raw.match(/^(\d+(?:\.\d+)?)\s*(b|kib|mib|gib)?$/i);
    if (!match) return null;
    const scale = { b: 1, kib: 1024, mib: 1024 ** 2, gib: 1024 ** 3 }[(match[2] || 'mib').toLowerCase()];
    return Math.round(Number(match[1]) * scale);
  }

  async function call(path, options = {}) {
    if (!window.BeastRuntime?.request) throw new Error('BeastRuntime is unavailable');
    return BeastRuntime.request(path, { timeoutMs: 20000, attempts: 1, ...options });
  }

  function renderer() {
    const root = document.createElement('div');
    root.className = 'beast-page beast-physical-plane-page';
    root.innerHTML = `
      <header class="beast-page-head"><div>
        <h2>Physical Plane</h2>
        <div class="sub">BYTE BUDGET // CRYSTAL KV STORAGE // ORDERED RECLAIM LADDER</div>
      </div><div class="beast-page-actions">
        <button class="beast-button secondary" data-nav="compute-fabric">Compute Fabric</button>
        <button class="beast-button secondary" data-nav="live-fabric">Live Fabric</button>
        <button class="beast-button hot" data-refresh>Refresh</button>
      </div></header>
      <div class="cortex-empty-list" data-status role="status" aria-live="polite">No snapshot loaded.</div>

      <section class="beast-card wide">
        <header class="beast-panel-head"><div><h3>Byte Budget</h3><span>One admission ledger across every tier</span></div>
          <span class="beast-pill" data-lease-count>0 LEASES</span></header>
        <div class="physical-pool-grid" data-pools></div>
        <div class="beast-page-actions">
          <button class="beast-button secondary" data-reprobe>Reprobe Capacities</button>
          <button class="beast-button secondary" data-sweep>Sweep Expired Leases</button>
        </div>
      </section>

      <div class="fabric-grid">
        <section class="beast-card">
          <header class="beast-panel-head"><div><h3>Crystal KV Storage</h3><span>Content-addressed, digest-verified</span></div>
            <span class="beast-pill" data-kv-backend>UNREPORTED</span></header>
          <div data-kv></div>
        </section>
        <section class="beast-card">
          <header class="beast-panel-head"><div><h3>Reclaim Ladder</h3><span>KV evict → memory.reclaim → freeze/kill</span></div>
            <span class="beast-pill" data-pressure>UNREPORTED</span></header>
          <div class="beast-page-actions">
            <button class="beast-button secondary" data-reclaim="">Observed Level</button>
            <button class="beast-button secondary" data-reclaim="high">Force High</button>
            <button class="beast-button secondary" data-reclaim="critical">Force Critical</button>
          </div>
          <div data-reclaim-out></div>
        </section>
        <section class="beast-card">
          <header class="beast-panel-head"><div><h3>Admit Bytes</h3><span>All-or-nothing reservation</span></div></header>
          <div class="beast-form-grid">
            <label>Owner <input data-in-owner value="ide-physical-plane" /></label>
            <label>Pool <select data-in-pool>${POOLS.map(([id, label]) => `<option value="${id}">${label}</option>`).join('')}</select></label>
            <label>Size <input data-in-bytes value="64MiB" /></label>
            <label>TTL (s) <input data-in-ttl value="3600" /></label>
            <label>Privacy <input data-in-privacy value="local_physical" /></label>
            <label class="beast-checkbox"><input type="checkbox" data-in-pinned /> Pinned (unbounded allowed)</label>
          </div>
          <div class="beast-page-actions"><button class="beast-button hot" data-admit>Admit</button></div>
          <div data-admit-out></div>
        </section>
        <section class="beast-card wide">
          <header class="beast-panel-head"><div><h3>Leases</h3><span>Committed bytes, replayed from the journal</span></div></header>
          <div data-leases></div>
        </section>
      </div>`;

    let disposed = false;
    let busy = false;
    const state = { ledger: null, kv: null, reclaim: null, admission: null, error: '' };
    const q = sel => root.querySelector(sel);

    function statusText() {
      if (busy) return 'Reading live physical-plane receipts…';
      if (state.error) return `Refresh failed: ${state.error}`;
      if (!state.ledger) return 'No snapshot loaded.';
      return `Snapshot loaded · ${state.ledger.lease_count ?? 0} leases · authority ${state.ledger.authority || 'unreported'}`;
    }

    function renderPools() {
      const pools = state.ledger?.pools || {};
      q('[data-pools]').innerHTML = POOLS.map(([id, label, source]) => {
        const pool = pools[id];
        if (!pool) return `<div class="physical-pool-card"><b>${label}</b><span class="pool-free">NO REPORT</span><small>${source}</small></div>`;
        const util = pool.utilization === null || pool.utilization === undefined ? null : Math.min(1, pool.utilization);
        const bar = util === null ? '' : `<div class="beast-meter"><i style="width:${(util * 100).toFixed(1)}%"></i></div>`;
        return `<div class="physical-pool-card"><b>${label}</b>
          <span class="pool-free">${mib(pool.available_bytes)}</span>
          <em>${mib(pool.committed_bytes)} committed / ${mib(pool.capacity_bytes)}</em>${bar}
          <small>${source}</small></div>`;
      }).join('');
      q('[data-lease-count]').textContent = `${state.ledger?.active_lease_count ?? 0} ACTIVE LEASES`;
    }

    function renderKv() {
      const kv = state.kv || {};
      const tier = kv.crystal_storage_tier;
      q('[data-kv-backend]').textContent = String(kv.storage_backend || 'UNREPORTED').toUpperCase();
      if (!tier) {
        q('[data-kv]').innerHTML = '<p>Crystal tier not bound; the transport is using raw files.</p>';
        return;
      }
      q('[data-kv]').innerHTML = [
        ['Manifests', tier.manifests],
        ['Logical KV bytes', mib(tier.kv_bytes)],
        ['Unique chunks', tier.unique_chunks],
        ['Physical chunk bytes', mib(tier.unique_chunk_bytes)],
        ['Hits / misses', `${tier.hits ?? '—'} / ${tier.misses ?? '—'}`],
        ['Rejections', tier.rejections],
        ['Authority', tier.authority],
        ['Cross-engine portable', tier.cross_engine_portable === false ? 'NO (cache only)' : 'unreported'],
      ].map(([label, value]) => `<div class="fabric-status-row"><b>${label}</b><span>${esc(value)}</span></div>`).join('');
    }

    function renderReclaim() {
      const receipt = state.reclaim;
      if (!receipt) { q('[data-reclaim-out]').innerHTML = ''; return; }
      q('[data-pressure]').textContent = `${String(receipt.pressure_level || '?').toUpperCase()}${receipt.level_forced ? ' (FORCED)' : ''}`;
      const steps = (receipt.steps || []).map(step => `<div class="fabric-trace-row">
        <span>${esc(step.status)}</span><b>${esc(step.step)}${step.target ? ` · ${esc(step.target)}` : ''}</b>
        <em>${step.freed_bytes ? `freed ${mib(step.freed_bytes)}` : esc(step.reason || '')}</em></div>`).join('');
      q('[data-reclaim-out]').innerHTML = `<div class="fabric-big-number">${mib(receipt.freed_bytes)}</div>
        <p>Reclaimed · target ${mib(receipt.requested_bytes)} · ${esc(receipt.stopped_because)}</p>
        <p>Observed host level: <b>${esc(receipt.observed_level || 'unreported')}</b>${receipt.level_forced ? ' · ladder forced by operator' : ''}</p>${steps}`;
    }

    function renderAdmission() {
      const receipt = state.admission;
      if (!receipt) { q('[data-admit-out]').innerHTML = ''; return; }
      q('[data-admit-out]').innerHTML = receipt.ok
        ? `<p class="beast-ok">Admitted <b>${mib(receipt.requested_bytes)}</b> into ${esc(receipt.pool)} · lease <code>${esc(receipt.lease_id)}</code></p>`
        : `<p class="beast-error">Denied: ${esc(receipt.denied_reason)} · shortfall ${mib(receipt.shortfall_bytes)}</p>`;
    }

    function renderLeases() {
      const leases = state.leases || [];
      q('[data-leases]').innerHTML = leases.length ? leases.map(lease => `<div class="fabric-trace-row">
        <span>${esc(lease.pool)}</span><b>${esc(lease.owner)} · ${mib(lease.bytes)}${lease.pinned ? ' · pinned' : ''}</b>
        <em><button class="beast-button secondary" data-release="${esc(lease.lease_id)}">Release</button></em></div>`).join('')
        : '<p>No committed leases.</p>';
    }

    function render() {
      if (disposed) return;
      q('[data-status]').textContent = statusText();
      renderPools(); renderKv(); renderReclaim(); renderAdmission(); renderLeases();
    }

    async function refresh() {
      if (busy) return;
      busy = true; render();
      try {
        const [ledger, kv] = await Promise.all([
          call('/edgek/physical/ledger'),
          call('/edgek/kv-cache/state'),
        ]);
        state.ledger = ledger;
        state.leases = Array.isArray(ledger?.leases) ? ledger.leases : [];
        state.kv = kv;
        state.error = '';
      } catch (error) {
        state.error = String(error?.message || error);
      } finally {
        busy = false; render();
      }
    }

    async function reclaim(level) {
      try {
        const body = level ? { force_level: level } : {};
        state.reclaim = await call('/edgek/physical/reclaim', { method: 'POST', body });
        state.error = '';
      } catch (error) {
        state.error = String(error?.message || error);
      }
      await refresh();
      renderReclaim();
    }

    async function admit() {
      const size = bytesParam(q('[data-in-bytes]').value);
      if (!size) { state.admission = { ok: false, denied_reason: 'invalid size', shortfall_bytes: 0 }; renderAdmission(); return; }
      const ttlRaw = q('[data-in-ttl]').value.trim();
      try {
        state.admission = await call('/edgek/physical/admit', {
          method: 'POST',
          body: {
            owner: q('[data-in-owner]').value,
            pool: q('[data-in-pool]').value,
            bytes: size,
            ttl_seconds: ttlRaw === '' ? null : Number(ttlRaw),
            pinned: q('[data-in-pinned]').checked,
            privacy_domain: q('[data-in-privacy]').value,
          },
        });
        state.error = '';
      } catch (error) {
        state.admission = { ok: false, denied_reason: String(error?.message || error), shortfall_bytes: 0 };
      }
      await refresh();
      renderAdmission();
    }

    root.addEventListener('click', async event => {
      const release = event.target.closest('[data-release]')?.dataset.release;
      if (release) {
        await call('/edgek/physical/release', { method: 'POST', body: { lease_id: release, reason: 'ide' } }).catch(() => {});
        await refresh();
      }
      if (event.target.closest('[data-refresh]')) await refresh();
      if (event.target.closest('[data-reprobe]')) {
        await call('/edgek/physical/reprobe', { method: 'POST', body: {} }).catch(error => { state.error = String(error?.message || error); });
        await refresh();
      }
      if (event.target.closest('[data-sweep]')) {
        await call('/edgek/physical/sweep', { method: 'POST', body: {} }).catch(() => {});
        await refresh();
      }
      if (event.target.closest('[data-admit]')) await admit();
      const level = event.target.closest('[data-reclaim]')?.dataset.reclaim;
      if (level !== undefined) await reclaim(level);
    });

    render();
    queueMicrotask(refresh);
    return {
      node: root,
      dispose() { disposed = true; },
    };
  }

  window.BeastPhysicalPlanePage = { renderer };
})();
