(() => {
  const gates = [
    ['G1', 'Reconciliation'], ['G2', 'Composition'], ['G3', 'Reachability'],
    ['G4', 'Read-only Capsule'], ['G5', 'Write + Rollback'],
    ['G6', 'Refusal Gauntlet'], ['G7', 'Economics + Pressure'],
    ['G8', 'Capsule Required'], ['G9', 'Signed Bundle'],
  ];
  const esc = value => String(value ?? '—').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));
  const gateStatus = receipt => {
    if (String(receipt?.status || '').trim()) return String(receipt.status).trim().toUpperCase();
    if (receipt?.validated === true) return 'PASS';
    if (receipt?.validated === false) return 'FAIL';
    return 'UNVERIFIED';
  };

  function renderer() {
    const root = document.createElement('div');
    root.className = 'beast-page beast-grand-closure-page';
    root.innerHTML = `<header class="beast-page-head"><div><h2>Grand Closure</h2><div class="sub">INSTALLATION → EXECUTION → REFUSAL → ECONOMICS → ENFORCEMENT → SIGNED ROOT</div></div><div class="beast-page-actions"><button class="beast-button secondary" data-nav="evidence">Open Evidence</button><button class="beast-button hot" data-closure-refresh>Refresh Receipts</button></div></header><div class="cortex-empty-list" data-closure-refresh-status role="status" aria-live="polite"></div><section class="closure-hero"><div><span>END-TO-END STATUS</span><strong data-closure-status>UNVERIFIED</strong><small data-closure-root>No verified root loaded</small></div><div class="closure-seal" data-closure-seal>G9</div></section><section class="closure-timeline" data-closure-timeline></section><section class="beast-card wide closure-detail" data-closure-detail></section>`;
    let selected = 'G9';
    let refreshPromise = null;
    let disposed = false;

    const render = state => {
      const receipts = state.grandClosure?.gates || state.evidence?.grandClosure || {};
      root.querySelector('[data-closure-timeline]').innerHTML = gates.map(([id, name]) => {
        const receipt = receipts[id] || receipts[id.toLowerCase()] || {};
        const status = gateStatus(receipt);
        return `<button class="closure-gate ${selected === id ? 'active' : ''} ${status.toLowerCase()}" data-gate="${id}"><span>${id}</span><div><b>${name}</b><small>${esc(receipt.receipt || receipt.path || 'receipt not loaded')}</small></div><em>${status}</em></button>`;
      }).join('');

      const g9 = receipts.G9 || receipts.g9 || {};
      const valid = g9.validated === true || String(g9.status).toLowerCase() === 'pass';
      const platform = state.platform || {};
      root.querySelector('[data-closure-status]').textContent = platform.error
        ? 'SNAPSHOT UNAVAILABLE'
        : platform.loading ? 'REFRESHING EVIDENCE'
          : valid ? 'SIGNED CLOSURE VERIFIED' : 'EVIDENCE INCOMPLETE';
      root.querySelector('[data-closure-root]').textContent = g9.merkle_root || g9.root_digest || 'No verified Merkle root loaded';
      root.querySelector('[data-closure-seal]').classList.toggle('verified', valid);
      const receipt = receipts[selected] || receipts[selected.toLowerCase()] || {};
      root.querySelector('[data-closure-detail]').innerHTML = `<header class="beast-panel-head"><div><h3>${selected} · ${gates.find(item => item[0] === selected)?.[1]}</h3><span>${esc(receipt.note || 'Repository evidence receipt')}</span></div><span class="beast-pill ${receipt.validated ? 'live' : 'amber'}">${receipt.validated ? 'VERIFIED' : 'INSPECT'}</span></header><div class="closure-proof-grid"><div><span>Receipt</span><b>${esc(receipt.receipt || receipt.path)}</b></div><div><span>Digest</span><b>${esc(receipt.receipt_digest || receipt.digest)}</b></div><div><span>Authority</span><b>${esc(receipt.authority)}</b></div><div><span>Host</span><b>${esc(receipt.host || state.system?.hostname)}</b></div></div>`;
      const status = root.querySelector('[data-closure-refresh-status]');
      status.textContent = platform.error
        ? `Refresh failed: ${platform.error}`
        : platform.loading ? 'Loading repository evidence and signed closure receipts…'
          : platform.updatedAt ? 'Repository evidence snapshot loaded. Historical receipts do not attest current host state.'
            : 'No platform evidence snapshot loaded yet.';
    };

    const refresh = () => {
      if (refreshPromise) return refreshPromise;
      root.querySelector('[data-closure-refresh-status]').textContent = 'Loading repository evidence and signed closure receipts…';
      refreshPromise = window.BeastUtilityOrchestrationBridge.refreshPlatform()
        .catch(error => {
          root.querySelector('[data-closure-refresh-status]').textContent = `Refresh failed: ${String(error.message || error)}`;
        })
        .finally(() => { refreshPromise = null; });
      return refreshPromise;
    };

    const unsubscribe = BeastStore.subscribe(render);
    root.addEventListener('click', event => {
      const gate = event.target.closest('[data-gate]')?.dataset.gate;
      if (gate) {
        selected = gate;
        render(BeastStore.get());
      }
      if (event.target.closest('[data-closure-refresh]')) void refresh();
    });
    queueMicrotask(() => { if (!disposed) void refresh(); });
    return {
      node: root,
      dispose() { disposed = true; unsubscribe?.(); },
    };
  }

  window.BeastGrandClosurePage = { renderer };
})();
