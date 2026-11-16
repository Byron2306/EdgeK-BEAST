(() => {
  const systems = [
    ['Grand Closure', 'grandClosure'], ['BPF Observation', 'bpf'],
    ['Ring Consumer', 'x2'], ['AF_XDP Lab', 'x3'], ['Chunk Transport', 'x4'],
    ['Transport Economics', 'x5'], ['Cross-node Reconstruction', 'x6'],
    ['Production NIC Canary', 'x7'], ['PRISM Remote Residual', 'x8'],
    ['llama.cpp Prompt Cache', 'llamacpp'],
  ];
  const esc = value => String(value ?? '—').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));

  function renderer() {
    const root = document.createElement('div');
    root.className = 'beast-page beast-reality-page';
    root.innerHTML = `<header class="beast-page-head"><div><h2>Reality Matrix</h2><div class="sub">DECLARED CAPABILITY VERSUS PHYSICALLY OBSERVED STATE</div></div><div class="beast-page-actions"><button class="beast-button secondary" data-nav="doctor">Open Doctor</button><button class="beast-button hot" data-reality-refresh>Refresh Reality</button></div></header><div class="cortex-empty-list" data-reality-status role="status" aria-live="polite"></div><section class="beast-card wide reality-panel"><div class="reality-legend"><span>INSTALLED</span><span>READY</span><span>LIVE</span><span>VERIFIED</span></div><section class="reality-matrix" data-reality-matrix></section></section>`;
    const status = root.querySelector('[data-reality-status]');
    let disposed = false;
    let refreshPromise = null;

    const render = state => {
      const reality = state.reality || state.system?.reality || {};
      root.querySelector('[data-reality-matrix]').innerHTML = systems.map(([name, key]) => {
        const record = reality[key] || {};
        const levels = [['Installed', record.installed], ['Ready', record.ready], ['Live', record.live], ['Verified', record.verified]];
        return `<article class="reality-row"><header><b>${name}</b><small>${esc(record.receipt || record.note || 'No live receipt projected')}</small></header>${levels.map(([label, value]) => `<div class="reality-cell ${value === true ? 'yes' : value === false ? 'no' : 'unknown'}"><span>${label}</span><b>${value === true ? 'YES' : value === false ? 'NO' : '—'}</b></div>`).join('')}</article>`;
      }).join('');
      if (state.platform?.loading) status.textContent = 'Refreshing platform evidence…';
      else if (state.platform?.error) status.textContent = `Refresh failed: ${state.platform.error}`;
      else if (state.platform?.updatedAt) status.textContent = 'Repository evidence snapshot loaded. Historical proof is not a live host attestation.';
      else status.textContent = 'No platform evidence snapshot loaded yet.';
    };

    const refresh = () => {
      if (refreshPromise) return refreshPromise;
      status.textContent = 'Refreshing platform evidence…';
      refreshPromise = window.BeastUtilityOrchestrationBridge.refreshPlatform()
        .catch(error => {
          status.textContent = `Refresh failed: ${String(error.message || error)}`;
        })
        .finally(() => { refreshPromise = null; });
      return refreshPromise;
    };
    const unsubscribe = BeastStore.subscribe(render);
    root.addEventListener('click', event => {
      if (event.target.closest('[data-reality-refresh]')) void refresh();
    });
    queueMicrotask(() => { if (!disposed) void refresh(); });
    return {
      node: root,
      dispose() { disposed = true; unsubscribe?.(); },
    };
  }

  window.BeastRealityPage = { renderer };
})();
