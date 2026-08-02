(() => {
  const esc = value => String(value ?? '—').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const pick = (...values) => values.find(value => value !== undefined && value !== null);
  const truth = value => value === true ? 'LIVE' : value === false ? 'OFFLINE' : 'UNREPORTED';
  const tone = value => value === true ? 'good' : value === false ? 'bad' : 'unknown';
  const list = value => Array.isArray(value) ? value : [];
  const boolish = value => value === true ? true : value === false ? false : undefined;

  function kernelStatus({ bpfLive, bpfReady, x2Live, x2Ready }) {
    if (bpfLive === true && x2Live === true) return { label: 'LIVE', tone: 'good' };
    if (bpfLive === true) return { label: x2Ready === true ? 'BPF LIVE' : 'BPF VERIFIED', tone: 'good' };
    if (bpfReady === true) return { label: 'BPF READY', tone: 'good' };
    if (x2Live === true) return { label: 'SENSORIUM LIVE', tone: 'good' };
    if (x2Ready === true) return { label: 'SENSORIUM READY', tone: 'unknown' };
    return { label: 'UNREPORTED', tone: 'unknown' };
  }

  function snapshot(state) {
    const reality = state.reality || state.system?.reality || {};
    const fabric = state.liveFabric || state.system?.liveFabric || state.fabric || {};
    const bpf = fabric.bpf || state.sensorium?.bpf || reality.bpf || {};
    const x2 = fabric.x2 || state.sensorium?.x2 || reality.x2 || {};
    const xdp = fabric.xdp || fabric.x3 || state.network?.af_xdp || reality.x3 || {};
    const transport = fabric.transport || state.network?.evidenceFabric || {};
    const prism = state.computeFabric || state.control?.prism || {};
    const kv = state.providers?.kv || state.models?.kv || {};
    const economy = state.economy || state.computeEconomy || {};
    const pressure = state.system?.pressure || state.system?.psi || {};
    return { reality, fabric, bpf, x2, xdp, transport, prism, kv, economy, pressure };
  }

  function metric(label, value, note = '') {
    return `<div class="live-metric"><span>${esc(label)}</span><b>${esc(value)}</b><small>${esc(note)}</small></div>`;
  }

  function renderer() {
    const root = document.createElement('div');
    root.className = 'beast-page beast-live-fabric-page';
    root.innerHTML = `
      <header class="beast-page-head">
        <div><h2>Live Evidence Fabric</h2><div class="sub">KERNEL PULSE // AF_XDP PATH // KV RESIDENCY // PRISM DECISION // PSI ECONOMICS</div></div>
        <div class="beast-page-actions">
          <button class="beast-button secondary" data-nav="compute-fabric">Compute Fabric</button>
          <button class="beast-button secondary" data-nav="reality">Reality Matrix</button>
          <button class="beast-button hot" data-live-refresh>Refresh Pulse</button>
        </div>
      </header>
      <section class="live-proof-strip" data-proof-strip></section>
      <div class="live-fabric-layout">
        <section class="beast-card live-kernel-card">
          <header class="beast-panel-head"><div><h3>Kernel Observation</h3><span>X1 BPF and X2 Sensorium consumption</span></div><span class="beast-pill" data-kernel-state>UNREPORTED</span></header>
          <div class="live-kernel-viz" aria-hidden="true"><div class="kernel-ring"></div><div class="kernel-core">BPF</div><div class="kernel-pulse p1"></div><div class="kernel-pulse p2"></div><div class="kernel-pulse p3"></div></div>
          <div class="live-metric-grid" data-kernel-metrics></div>
          <div class="live-event-feed" data-event-feed></div>
        </section>
        <section class="beast-card live-network-card">
          <header class="beast-panel-head"><div><h3>AF_XDP Topology</h3><span>Fast path, fallback path and reconstruction</span></div><span class="beast-pill" data-xdp-state>UNREPORTED</span></header>
          <div class="xdp-topology" data-xdp-topology></div>
          <div class="live-metric-grid compact" data-xdp-metrics></div>
        </section>
        <section class="beast-card live-kv-card">
          <header class="beast-panel-head"><div><h3>KV Residency</h3><span>Engine-local and deployment cache backends</span></div><span class="beast-pill" data-kv-route>UNRESOLVED</span></header>
          <div class="kv-live-stack" data-kv-live></div>
        </section>
        <section class="beast-card live-prism-card">
          <header class="beast-panel-head"><div><h3>PRISM Decision Trace</h3><span>Eligibility before economics, authority before speed</span></div><span class="beast-pill" data-prism-state>UNRESOLVED</span></header>
          <div class="prism-waterfall" data-prism-waterfall></div>
        </section>
        <section class="beast-card live-economy-card">
          <header class="beast-panel-head"><div><h3>Economics + Pressure</h3><span>Preparation debt, reuse value, PSI and eviction</span></div><span class="beast-pill" data-pressure-state>UNKNOWN</span></header>
          <div class="economy-pressure-grid" data-economy-pressure></div>
        </section>
      </div>`;

    const render = state => {
      const s = snapshot(state);
      const bpfLive = pick(s.bpf.live_bpf_loaded, s.bpf.live, s.reality.bpf?.live);
      const bpfReady = boolish(pick(s.bpf.verified, s.bpf.ready, s.reality.bpf?.verified, s.reality.bpf?.ready));
      const x2Live = pick(s.x2.live, Number(s.x2.events_consumed) > 0 ? true : undefined, s.reality.x2?.live);
      const x2Ready = boolish(pick(s.x2.verified, s.x2.ready, Number(s.x2.events_consumed) > 0 ? true : undefined, s.reality.x2?.verified, s.reality.x2?.ready));
      const xdpLive = pick(s.xdp.live, Number(s.xdp.rx_packets) > 0 ? true : undefined, s.reality.x3?.live);
      const xdpVerified = pick(s.xdp.verified, s.reality.x3?.verified);
      const route = pick(s.prism.selectedRoute, s.prism.selected_route, state.models?.activeRoute, state.models?.route, 'UNRESOLVED');
      const pressureState = pick(s.pressure.status, s.pressure.state, 'UNKNOWN');
      const kernel = kernelStatus({ bpfLive, bpfReady, x2Live, x2Ready });
      root.dataset.kernelLive = bpfLive === true ? 'true' : 'false';
      root.dataset.xdpLive = xdpLive === true ? 'true' : 'false';
      root.querySelector('[data-kernel-state]').textContent = kernel.label;
      root.querySelector('[data-kernel-state]').className = `beast-pill ${kernel.tone}`;
      root.querySelector('[data-xdp-state]').textContent = xdpVerified === true ? 'VERIFIED' : truth(xdpLive);
      root.querySelector('[data-xdp-state]').className = `beast-pill ${tone(xdpVerified === true ? true : xdpLive)}`;
      root.querySelector('[data-kv-route]').textContent = String(route).toUpperCase();
      root.querySelector('[data-prism-state]').textContent = String(route).toUpperCase();
      root.querySelector('[data-pressure-state]').textContent = String(pressureState).toUpperCase();

      const proof = [
        ['BPF LOAD', pick(bpfLive, bpfReady)],
        ['RING', pick(x2Live, x2Ready)],
        ['LEASE CORRELATION', pick(s.x2.process_lease_correlation_performed, s.fabric.process_lease_correlation)],
        ['AF_XDP', xdpLive],
        ['X6 REMOTE', pick(s.reality.x6?.live, s.transport.cross_node_live)],
        ['X8 PRISM', pick(s.reality.x8?.live, s.transport.prism_remote_live)]
      ];
      root.querySelector('[data-proof-strip]').innerHTML = proof.map(([label,value]) => `<div class="live-proof ${tone(value)}"><span>${esc(label)}</span><b>${truth(value)}</b></div>`).join('');

      root.querySelector('[data-kernel-metrics]').innerHTML = [
        metric('BPF receipt', pick(s.bpf.receipt, s.reality.bpf?.receipt, '—'), bpfReady === true ? 'receipt-backed' : 'not projected'),
        metric('BPF load', truth(pick(bpfLive, bpfReady)), bpfLive === true ? 'loopback or load receipt observed' : 'awaiting live load receipt'),
        metric('Events consumed', pick(s.x2.events_consumed, s.bpf.events_consumed, '—')),
        metric('Loss total', pick(s.x2.loss_total, s.bpf.loss_total, '—'), pick(s.x2.loss_counters_reconciled, s.bpf.loss_counters_reconciled) === true ? 'reconciled' : 'unreported'),
        metric('Links detached', truth(pick(s.x2.links_detached_cleanly, s.bpf.links_detached_cleanly))),
        metric('ProcessLease', truth(pick(s.x2.process_lease_correlation_performed, s.fabric.process_lease_correlation)))
      ].join('');
      const events = list(pick(s.fabric.events, state.sensorium?.events, state.chronicle?.events)).slice(-8).reverse();
      root.querySelector('[data-event-feed]').innerHTML = events.length
        ? events.map(event => `<div class="live-event"><span>${esc(event.type || event.kind || 'EVENT')}</span><b>${esc(event.program || event.target || event.message || event.summary || 'Observed')}</b><em>${esc(event.timestamp || event.at || event.sequence || '')}</em></div>`).join('')
        : `<div class="live-empty">${bpfReady === true ? `BPF receipt ${esc(pick(s.bpf.receipt, s.reality.bpf?.receipt, 'observed'))} is present, but no live Sensorium event projection is currently attached.` : 'No live Sensorium event projection. Kernel truth remains unreported.'}</div>`;

      const nodes = [
        ['KERNEL', bpfLive], ['XDP RX', xdpLive], ['CHUNKER', pick(s.reality.x4?.live, s.transport.chunk_live)],
        ['MANIFEST', pick(s.transport.manifest_live, s.reality.x4?.ready)], ['REMOTE NODE', pick(s.reality.x6?.live, s.transport.cross_node_live)],
        ['PRISM', pick(s.reality.x8?.live, s.transport.prism_remote_live)]
      ];
      root.querySelector('[data-xdp-topology]').innerHTML = nodes.map(([label,value], index) => `${index ? '<i class="xdp-link"><span></span></i>' : ''}<div class="xdp-node ${tone(value)}"><span>${esc(label)}</span><b>${truth(value)}</b></div>`).join('');
      root.querySelector('[data-xdp-metrics]').innerHTML = [
        metric('RX packets', pick(s.xdp.rx_packets, s.xdp.received, '—')),
        metric('TX packets', pick(s.xdp.tx_packets, s.xdp.echoed, '—')),
        metric('Completions', pick(s.xdp.completions, '—')),
        metric('Drops', pick(s.xdp.drops, s.xdp.loss_total, '—')),
        metric('P50', pick(s.xdp.p50_us, s.xdp.p50, '—'), 'µs'),
        metric('P99', pick(s.xdp.p99_us, s.xdp.p99, '—'), 'µs')
      ].join('');

      const backends = [
        ['llama.cpp', s.kv.llamacpp || state.models?.llamacpp], ['Local Prefix', s.kv.local_prefix], ['LMCache', s.kv.lmcache],
        ['vLLM', s.kv.vllm], ['SGLang', s.kv.sglang], ['TensorRT-LLM', s.kv.tensorrt], ['TGI', s.kv.tgi]
      ];
      root.querySelector('[data-kv-live]').innerHTML = backends.map(([name,value]) => {
        const status = typeof value === 'string' ? value : pick(value?.status, value?.healthy === true ? 'HEALTHY' : undefined, 'UNREPORTED');
        const cache = pick(value?.cache_n, value?.reuse, value?.hit_rate, value?.prefix_reuse, '—');
        const scope = pick(value?.authority, value?.portability, value?.cache_mode, '—');
        return `<div class="kv-live-row"><span class="kv-led ${String(status).toLowerCase().includes('health') || String(status).toLowerCase().includes('live') ? 'good' : 'unknown'}"></span><b>${esc(name)}</b><em>${esc(status)}</em><small>${esc(cache)}</small><i>${esc(scope)}</i></div>`;
      }).join('');

      const trace = list(pick(s.prism.decisionTrace, s.prism.decision_trace, state.control?.prism?.decision_trace));
      const fallbackTrace = [
        {message:`Selected route: ${route}`, status:'selected'},
        {message:'Compatibility and authority gates evaluated before cost', status:'contract'},
        {message:'No permissive fallback is assumed', status:'fail-closed'}
      ];
      root.querySelector('[data-prism-waterfall]').innerHTML = (trace.length ? trace : fallbackTrace).slice(0,10).map((item,index) => {
        const message = typeof item === 'string' ? item : pick(item.message, item.reason, item.route, 'Observed decision');
        const status = typeof item === 'string' ? 'observed' : pick(item.status, item.result, 'observed');
        return `<div class="prism-step"><span>${String(index+1).padStart(2,'0')}</span><div><b>${esc(message)}</b><small>${esc(item.authority || item.cost || item.detail || '')}</small></div><em>${esc(status)}</em></div>`;
      }).join('');

      root.querySelector('[data-economy-pressure]').innerHTML = [
        metric('Avoided compute', pick(s.economy.netSavings, s.economy.savedTokens, s.economy.avoided_compute, '—')),
        metric('Preparation debt', pick(s.economy.preparationDebt, s.economy.preparation_debt, '—')),
        metric('Break-even', pick(s.economy.breakEven, s.economy.break_even, '—')),
        metric('Memory PSI', pick(s.pressure.memory, s.pressure.memory_some, '—')),
        metric('CPU PSI', pick(s.pressure.cpu, s.pressure.cpu_some, '—')),
        metric('IO PSI', pick(s.pressure.io, s.pressure.io_some, '—')),
        metric('Pins', pick(s.pressure.pins, s.economy.pins, '—')),
        metric('Evictions', pick(s.pressure.evictions, s.economy.evictions, '—'))
      ].join('');
    };

    const unsubscribe = BeastStore.subscribe(render);
    render(BeastStore.get());
    root.addEventListener('click', event => {
      if (event.target.closest('[data-live-refresh]')) {
        document.dispatchEvent(new CustomEvent('beast:operation', {detail:{message:'Live Evidence Fabric refresh requested', tone:'ok'}}));
        window.BeastRuntime?.refresh?.();
      }
    });
    return {node: root, dispose(){ unsubscribe?.(); }};
  }
  window.BeastLiveFabricPage = { renderer };
})();
