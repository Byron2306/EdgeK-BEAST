(() => {
  'use strict';

  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[char]);
  const icon = name => BeastAssets.icon(name);
  const routeFor = {
    pipeline: 'source', system: 'system', memory: 'memory', capabilities: 'tooling',
    vectors: 'providers', swarm: 'agents', sensorium: 'chronicle', tools: 'chronicle'
  };
  const features = [
    ['Semantic Mapping', 'pipeline', 'Map SourcePlan context, graph relationships, and schema-bearing evidence.', 'map'],
    ['KV Cache + Compression', 'vectors', 'Inspect cache transport, reuse, and context-economy route data.', 'economy'],
    ['Interception Mesh', 'sensorium', 'Read L1–L4 interception topology and payload-free runtime evidence.', 'chronicle'],
    ['Schema Trees + Tool Contracts', 'capabilities', 'Inspect governed capabilities, skills, schema exposure, and meta-tool evidence.', 'tooling'],
    ['Vector RAG', 'vectors', 'Inspect retrieval adapters, dense-vector readiness, and lexical fallback.', 'providers'],
    ['Insight Compiler', 'pipeline', 'Inspect ranked evidence and the task-to-insight pipeline.', 'chronicle'],
    ['Quality Cascade + Forge', 'pipeline', 'Inspect quality gates, context packet, scorecard, and rollout decision.', 'source'],
    ['PREC Lifecycle', 'system', 'Inspect Prevent → Review → Evidence → Crystallize lifecycle records.', 'system'],
    ['Economizer', 'vectors', 'Inspect local-first routing, compression, reuse, and cache counters.', 'economy'],
    ['L0–L4 Memory', 'memory', 'Inspect governance, hot cache, workspace graph, skill, and forensic layers.', 'memory'],
    ['Chronicles', 'tools', 'Inspect durable task, provider, and governance history.', 'chronicle'],
    ['Sensorium', 'sensorium', 'Inspect observatory projection, telemetry, and event mesh.', 'chronicle'],
    ['Task Envelopes + Output IR', 'pipeline', 'Inspect the canonical task contract and governed output path.', 'source'],
    ['Anti-gaming + OS Bypass', 'system', 'Inspect runtime controls, evidence boundaries, ports, and privileged capability readiness.', 'system'],
    ['Swarm', 'swarm', 'Inspect governed roles, runs, value logs, and task handoffs.', 'agents']
  ];

  function metric(label, value, detail) {
    return `<article class="beast-card compact terminal-metric"><div><h3>${esc(label)}</h3><strong>${esc(value)}</strong><span>${esc(detail)}</span></div></article>`;
  }
  function compact(value) {
    try { return JSON.stringify(value ?? {}, null, 2); } catch (_) { return String(value ?? ''); }
  }
  function statusClass(value) {
    return /fail|error|offline|attention|block/i.test(String(value || '')) ? 'bad' : /watch|warn|pending/i.test(String(value || '')) ? 'warn' : 'live';
  }

  function template() {
    const root = document.createElement('div');
    root.className = 'beast-page beast-atlas-page';
    root.innerHTML = `
      <header class="beast-page-head"><div><h2>BEAST Systems Atlas</h2><div class="sub">LIVE SUBSYSTEM CONTRACTS // NO SEEDED RUNTIME DATA // DRILL INTO THE MACHINE</div></div><div class="beast-page-actions"><button class="beast-button secondary" data-atlas-runtime>Gateway Diagnostics</button><button class="beast-button hot" data-atlas-refresh>Refresh Live Atlas</button></div></header>
      <section class="beast-card wide"><header class="beast-panel-head"><div><h3>Operational Systems</h3><span>Named entry points for the live systems that drive BEAST—not a demo dashboard.</span></div><span class="beast-pill live">LIVE ROUTES</span></header><div class="atlas-feature-grid" data-atlas-features></div></section>
      <section class="p8-metric-grid" data-atlas-metrics></section>
      <section class="beast-card wide atlas-fault" data-atlas-fault hidden></section>
      <div class="atlas-layout"><section class="beast-card atlas-section-list"><header class="beast-panel-head"><div><h3>Live Subsystems</h3><span>Every card is sourced from <code>/edgek/platform/snapshot</code>.</span></div><span class="beast-pill" data-atlas-state>CHECKING</span></header><div data-atlas-sections></div></section><section class="beast-card atlas-inspector is-active"><header class="beast-panel-head"><div><h3 data-atlas-title>Subsystem Inspector</h3><span data-atlas-source>Select a live subsystem.</span></div><button class="beast-button secondary" data-atlas-open>Open Surface</button></header><div class="atlas-facts" data-atlas-facts></div><pre class="atlas-json" data-atlas-json>Awaiting a live snapshot.</pre></section></div>
      `;
    return root;
  }

  function renderer() {
    const root = template();
    let disposed = false;
    let selectedId = '';

    function patch(state) {
      if (disposed) return;
      const platform = state.platform || {};
      const sections = Array.isArray(platform.sections) ? platform.sections : [];
      const selected = sections.find(section => section.id === selectedId) || sections[0] || null;
      if (selected) selectedId = selected.id;
      root.querySelector('[data-atlas-state]').textContent = String(platform.status || 'checking').toUpperCase();
      root.querySelector('[data-atlas-state]').className = `beast-pill ${statusClass(platform.status)}`;
      root.querySelector('[data-atlas-metrics]').innerHTML = [
        metric('Atlas Health', `${Math.round(Number(platform.health || 0))}%`, platform.status || 'checking'),
        metric('Live Sections', sections.length, platform.updatedAt ? `updated ${new Date(platform.updatedAt).toLocaleTimeString()}` : 'not yet refreshed'),
        metric('Gateway', state.connection?.status || BeastRuntime.mode, BeastRuntime.gatewayUrl || 'unresolved'),
        metric('Runtime Faults', BeastRuntime.diagnostics().errors.length, platform.error ? 'atlas request failed' : 'none reported')
      ].join('');
      const fault = root.querySelector('[data-atlas-fault]');
      const faultText = platform.error || state.connection?.message || '';
      fault.hidden = !faultText;
      fault.innerHTML = faultText ? `<header class="beast-panel-head"><div><h3>Live Data Unavailable</h3><span>The UI is intentionally showing no replacement demo data.</span></div><span class="beast-pill bad">ACTION REQUIRED</span></header><p>${esc(faultText)}</p><p>Check the gateway target, its owner process, LiteLLM/proxy configuration, and Socket Guardian/port ownership in System Plane.</p>` : '';
      root.querySelector('[data-atlas-sections]').innerHTML = sections.length ? sections.map(section => `<button class="atlas-section-row ${section.id === selectedId ? 'selected' : ''}" data-atlas-section="${esc(section.id)}"><span><b>${esc(section.title)}</b><small>${esc(section.summary || '')}</small></span><em class="${statusClass(section.status)}">${esc(section.status || 'unknown')}</em></button>`).join('') : '<div class="cortex-empty-list">No live platform snapshot. Refresh after the gateway is reachable.</div>';
      root.querySelector('[data-atlas-features]').innerHTML = features.map(([name, sectionId, detail, route]) => {
        const section = sections.find(item => item.id === sectionId);
        return `<button class="atlas-feature-card" data-atlas-route="${esc(route)}" data-atlas-section="${esc(sectionId)}"><img src="${icon(route === 'agents' ? 'agents' : route === 'memory' ? 'memory' : route === 'chronicle' ? 'chronicle' : route === 'economy' ? 'economy' : route === 'providers' ? 'providers' : route === 'map' ? 'map' : 'system')}" alt=""><span><b>${esc(name)}</b><small>${esc(detail)}</small></span><em class="${statusClass(section?.status)}">${esc(section?.status || 'unavailable')}</em></button>`;
      }).join('');
      const title = root.querySelector('[data-atlas-title]');
      const source = root.querySelector('[data-atlas-source]');
      const facts = root.querySelector('[data-atlas-facts]');
      const json = root.querySelector('[data-atlas-json]');
      const open = root.querySelector('[data-atlas-open]');
      if (!selected) {
        title.textContent = 'Subsystem Inspector'; source.textContent = 'Select a live subsystem.'; facts.innerHTML = ''; json.textContent = 'Awaiting a live snapshot.'; open.disabled = true; return;
      }
      title.textContent = selected.title;
      source.textContent = selected.source || 'live BEAST platform snapshot';
      facts.innerHTML = (selected.metrics || []).map(item => `<div><span>${esc(item.label)}</span><b>${esc(item.value)}</b><small>${esc(item.detail || '')}</small></div>`).join('');
      json.textContent = compact(selected.payload || platform.snapshots?.[selected.id] || {});
      open.disabled = false;
      open.dataset.atlasOpen = routeFor[selected.id] || 'system';
    }

    const unsubscribe = BeastStore.subscribe(patch);
    root.addEventListener('click', async event => {
      const section = event.target.closest('[data-atlas-section]');
      if (section && !event.target.closest('[data-atlas-route]')) { selectedId = section.dataset.atlasSection; patch(BeastStore.get()); return; }
      const feature = event.target.closest('[data-atlas-route]');
      if (feature) { selectedId = feature.dataset.atlasSection || selectedId; await BeastRouter.navigate(feature.dataset.atlasRoute); return; }
      if (event.target.closest('[data-atlas-refresh]')) { await BeastUtilityOrchestrationBridge.refreshPlatform().catch(() => {}); return; }
      if (event.target.closest('[data-atlas-runtime]')) { await BeastRuntime.probe(); await BeastUtilityOrchestrationBridge.refreshPlatform().catch(() => {}); return; }
      const open = event.target.closest('[data-atlas-open]');
      if (open?.dataset.atlasOpen) await BeastRouter.navigate(open.dataset.atlasOpen);
    });
    BeastUtilityOrchestrationBridge.refreshPlatform().catch(() => {});
    return {node: root, dispose() { disposed = true; unsubscribe(); }};
  }

  window.BeastAtlasPage = {renderer};
})();
