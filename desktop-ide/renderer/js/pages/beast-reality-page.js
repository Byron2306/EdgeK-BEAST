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
    root.innerHTML = `<header class="beast-page-head"><div><h2>Reality Matrix</h2><div class="sub">DECLARED CAPABILITY VERSUS PHYSICALLY OBSERVED STATE</div></div><div class="beast-page-actions"><button class="beast-button secondary" data-nav="doctor">Open Doctor</button><button class="beast-button hot" data-reality-refresh>Refresh Reality</button></div></header><section class="beast-card wide reality-panel"><div class="reality-legend"><span>INSTALLED</span><span>READY</span><span>LIVE</span><span>VERIFIED</span></div><section class="reality-matrix" data-reality-matrix></section></section>`;
    const render = state => {
      const reality = state.reality || state.system?.reality || {};
      root.querySelector('[data-reality-matrix]').innerHTML = systems.map(([name, key]) => {
        const record = reality[key] || {};
        const levels = [['Installed', record.installed], ['Ready', record.ready], ['Live', record.live], ['Verified', record.verified]];
        return `<article class="reality-row"><header><b>${name}</b><small>${esc(record.receipt || record.note || 'No live receipt projected')}</small></header>${levels.map(([label, value]) => `<div class="reality-cell ${value === true ? 'yes' : value === false ? 'no' : 'unknown'}"><span>${label}</span><b>${value === true ? 'YES' : value === false ? 'NO' : '—'}</b></div>`).join('')}</article>`;
      }).join('');
    };
    const unsubscribe = BeastStore.subscribe(render);
    render(BeastStore.get());
    return { node: root, dispose() { unsubscribe?.(); } };
  }

  window.BeastRealityPage = { renderer };
})();
