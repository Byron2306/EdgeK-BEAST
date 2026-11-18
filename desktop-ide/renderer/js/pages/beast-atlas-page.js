(() => {
  'use strict';

  const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const domains={coder:'Agent Coder',context:'Context Economy',memory:'Memory + Retrieval',crystals:'Crystals + Lattices',orchestration:'Orchestration',infrastructure:'Infrastructure',providers:'Providers + Routing',security:'Security + Kernel'};
  const status=(item,label)=>`<span class="atlas-status ${item?'yes':'no'}"><i></i>${label}</span>`;
  const metric=(label,value,detail)=>`<article class="beast-card compact terminal-metric"><div><h3>${esc(label)}</h3><strong>${esc(value)}</strong><span>${esc(detail)}</span></div></article>`;

  function template(){
    const root=document.createElement('div');
    root.className='beast-page beast-atlas-page';
    root.innerHTML=`
      <header class="beast-page-head"><div><h2>BEAST Systems Atlas</h2><div class="sub">CANONICAL INTEGRATION MAP // IMPLEMENTED ≠ ENABLED ≠ EVIDENCE ≠ LIVE</div></div><div class="beast-page-actions"><button class="beast-button secondary" data-atlas-integrations="definitions">Status Definitions</button><button class="beast-button hot" data-atlas-refresh>Refresh Integrations</button></div></header>
      <section class="beast-card atlas-definitions" data-atlas-definitions hidden><header class="beast-panel-head"><div><h3>Claim Boundary</h3><span>Each status is independent. Historical evidence never implies a currently live process.</span></div><span class="beast-pill warn">claim-boundary</span></header><div class="atlas-definition-grid"><div><b>IMPLEMENTED</b><span>Backend code is present.</span></div><div><b>ENABLED</b><span>Required runtime flag is active.</span></div><div><b>EVIDENCE</b><span>A bounded test or run artifact exists.</span></div><div><b>LIVE</b><span>A current runtime probe is positive.</span></div></div></section>
      <section class="p8-metric-grid" data-atlas-metrics></section>
      <section class="beast-card atlas-fault" data-atlas-fault hidden></section>
      <section class="beast-card wide atlas-controls"><header class="beast-panel-head"><div><h3>Integration Families</h3><span>Filter the audited backend inventory without changing its claims.</span></div><span class="beast-pill" data-atlas-state>UNLOADED</span></header><div class="atlas-filter-row">${['all','enabled','evidence','live','disabled'].map(name=>`<button class="beast-button secondary ${name==='all'?'active':''}" data-atlas-filter="${name}">${name}</button>`).join('')}</div></section>
      <div class="atlas-layout"><section class="beast-card atlas-section-list"><header class="beast-panel-head"><div><h3>Capability Map</h3><span>Server-owned catalog grouped by operational domain.</span></div></header><div data-atlas-capabilities></div></section><section class="beast-card atlas-inspector is-active"><header class="beast-panel-head"><div><h3 data-atlas-title>Integration Inspector</h3><span data-atlas-source>Select a capability family.</span></div><button class="beast-button secondary" data-atlas-open>Open Primary Surface</button></header><div class="atlas-status-strip" data-atlas-statuses></div><p class="atlas-claim" data-atlas-claim></p><div class="atlas-facts" data-atlas-facts></div><div class="atlas-component-list" data-atlas-components></div></section></div>`;
    const lifecycle = document.createElement('section');
    lifecycle.className = 'beast-card wide';
    lifecycle.setAttribute('data-atlas-lifecycle', '');
    lifecycle.innerHTML = '<header class="beast-panel-head"><div><h3>Agent Integration Lifecycle</h3><span>Observed receipts are not independent durability proof.</span></div></header><div data-atlas-lifecycle-events></div>';
    root.append(lifecycle);
    return root;
  }

  function include(item,filter){
    if(filter==='enabled')return item.enabled;
    if(filter==='evidence')return item.evidence.present;
    if(filter==='live')return item.live;
    if(filter==='disabled')return !item.enabled;
    return true;
  }

  function renderer(){
    const root=template();
    let disposed=false;
    let selectedId=BeastStore.get().integrations.selectedId||'';
    let filter='all';
    function patch(state){
      if(disposed)return;
      const integrations=state.integrations||{};
      const all=Array.isArray(integrations.capabilities)?integrations.capabilities:[];
      const rows=all.filter(item=>include(item,filter));
      const selected=all.find(item=>item.id===selectedId)||rows[0]||all[0]||null;
      if(selected)selectedId=selected.id;
      const receipts = Array.isArray(integrations.lifecycleEvents)
        ? integrations.lifecycleEvents.slice(-30).reverse() : [];

      root.querySelector('[data-atlas-lifecycle-events]').innerHTML =
        receipts.length
          ? receipts.map(item => `<article class="atlas-lifecycle-row">
              <b>${esc(item.capability)}</b>
              <span>${esc(item.stage)} / ${esc(item.operation)}</span>
              <em>${esc(item.status)}</em>
              <small>${esc(item.mode || item.reason)}</small>
              <strong>${item.effectCommitted
                ? 'COMMIT CLAIMED · NOT INDEPENDENTLY VERIFIED'
                : 'NO DURABLE EFFECT PROVEN'}</strong>
            </article>`).join('')
          : '<div class="cortex-empty-list">No integration lifecycle receipts observed.</div>';

      const summary=integrations.summary||{};
      const componentCount=all.reduce((total,item)=>total+(item.components?.length||0),0);
      root.querySelector('[data-atlas-metrics]').innerHTML=[metric('Implemented',`${summary.implemented||0}/${summary.total||all.length}`,'backend families present'),metric('Enabled',summary.enabled||0,'runtime flags active'),metric('Evidence',summary.withEvidence||0,'families with artifacts'),metric('Live',summary.live||0,`${componentCount} audited components`)].join('');
      const statePill=root.querySelector('[data-atlas-state]');
      statePill.textContent=integrations.loading?'LOADING':String(integrations.status||'unloaded').toUpperCase();
      statePill.className=`beast-pill ${integrations.error?'bad':integrations.loading?'warn':'live'}`;
      const fault=root.querySelector('[data-atlas-fault]');
      fault.hidden=!integrations.error;
      fault.innerHTML=integrations.error?`<header class="beast-panel-head"><div><h3>Integration Catalog Unavailable</h3><span>No demo or seeded replacement has been inserted.</span></div><span class="beast-pill bad">ACTION REQUIRED</span></header><p>${esc(integrations.error)}</p>`:'';
      const grouped=rows.reduce((result,item)=>{(result[item.domain]??=[]).push(item);return result;},{});
      root.querySelector('[data-atlas-capabilities]').innerHTML=rows.length?Object.entries(grouped).map(([domain,items])=>`<div class="atlas-domain"><h4>${esc(domains[domain]||domain)}</h4>${items.map(item=>`<button class="atlas-section-row ${item.id===selectedId?'selected':''}" data-atlas-id="${esc(item.id)}"><span><b>${esc(item.title)}</b><small>${esc(item.mode||item.claim)}</small></span><em>${item.live?'live':item.enabled?'enabled':item.implemented?'implemented':'declared'}</em></button>`).join('')}</div>`).join(''):'<div class="cortex-empty-list">No capability families match this filter.</div>';
      root.querySelectorAll('[data-atlas-filter]').forEach(button=>button.classList.toggle('active',button.dataset.atlasFilter===filter));
      const open=root.querySelector('[data-atlas-open]');
      if(!selected){root.querySelector('[data-atlas-title]').textContent='Integration Inspector';root.querySelector('[data-atlas-source]').textContent='No catalog entry selected.';root.querySelector('[data-atlas-statuses]').innerHTML='';root.querySelector('[data-atlas-claim]').textContent='';root.querySelector('[data-atlas-facts]').innerHTML='';root.querySelector('[data-atlas-components]').innerHTML='';open.disabled=true;return;}
      root.querySelector('[data-atlas-title]').textContent=selected.title;
      root.querySelector('[data-atlas-source]').textContent=selected.source||'canonical integration catalog';
      root.querySelector('[data-atlas-statuses]').innerHTML=[status(selected.implemented,'IMPLEMENTED'),status(selected.enabled,'ENABLED'),status(selected.evidence.present,'EVIDENCE'),status(selected.live,'LIVE')].join('');
      root.querySelector('[data-atlas-claim]').textContent=selected.claim||'No claim supplied.';
      root.querySelector('[data-atlas-facts]').innerHTML=`<div><span>Mode</span><b>${esc(selected.mode||'unspecified')}</b></div><div><span>Primary surface</span><b>${esc(selected.primarySurface||'not mapped')}</b></div><div><span>Evidence files</span><b>${selected.evidence.count||0}</b></div><div><span>Required flags</span><b>${esc(selected.flags?.join(', ')||'none')}</b></div>`;
      root.querySelector('[data-atlas-components]').innerHTML=`<header><b>Audited Components</b><span>${selected.components.length} entries</span></header>${selected.components.length?selected.components.map(component=>`<article><div><b>${esc(component.title)}</b><small>${esc(component.id)}</small></div><span>${esc(component.backendState||'unknown')}</span><span>${esc(component.ideWiring||'unmapped')}</span><em>${esc(component.baselineRunState||'unknown')}</em></article>`).join(''):'<div class="cortex-empty-list">No component rows supplied.</div>'}`;
      open.disabled=!selected.primarySurface;
      open.dataset.atlasOpen=selected.primarySurface||'';
    }
    const unsubscribe=BeastStore.subscribe(patch);
    root.addEventListener('click',async event=>{
      const row=event.target.closest('[data-atlas-id]');if(row){selectedId=row.dataset.atlasId;patch(BeastStore.get());return;}
      const filterButton=event.target.closest('[data-atlas-filter]');if(filterButton){filter=filterButton.dataset.atlasFilter;patch(BeastStore.get());return;}
      if(event.target.closest('[data-atlas-integrations]')){const panel=root.querySelector('[data-atlas-definitions]');panel.hidden=!panel.hidden;return;}
      if(event.target.closest('[data-atlas-refresh]')){await BeastIntegrationMap.refresh().catch(()=>{});return;}
      const open=event.target.closest('[data-atlas-open]');if(open?.dataset.atlasOpen)await BeastRouter.navigate(open.dataset.atlasOpen);
    });
    BeastIntegrationMap.refresh().catch(()=>{});
    return{node:root,dispose(){disposed=true;unsubscribe();}};
  }
  window.BeastAtlasPage={renderer};
})();
