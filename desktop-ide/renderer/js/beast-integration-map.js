(() => {
  const emptySummary=()=>({total:0,implemented:0,enabled:0,withEvidence:0,live:0});
  const text=(value,limit=400)=>String(value ?? '').slice(0,limit);
  const html=(value,limit=400)=>text(value,limit).replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const strings=value=>Array.isArray(value)?value.map(item=>text(item,120)).filter(Boolean):[];

  function normalizeComponent(raw={}) {
    return {
      id:text(raw.id,120),title:text(raw.title,240),backendState:text(raw.backend_state,80),
      ideWiring:text(raw.ide_wiring,80),baselineRunState:text(raw.baseline_run_state,80)
    };
  }

  function normalizeCapability(raw={}) {
    const surfaces=strings(raw.surfaces);
    const primary=text(raw.primary_surface,80);
    const evidence=raw.evidence && typeof raw.evidence==='object'?raw.evidence:{};
    return {
      id:text(raw.id,120),title:text(raw.title,240),domain:text(raw.domain,80),
      implemented:raw.implemented===true,enabled:raw.enabled===true,live:raw.live===true,
      mode:text(raw.mode,100),claim:text(raw.claim,800),source:text(raw.source,300),
      flags:strings(raw.flags),surfaces,primarySurface:surfaces.includes(primary)?primary:(surfaces[0]||''),
      evidence:{present:evidence.present===true,count:Number(evidence.count)||0,updatedAt:Number(evidence.updated_at)||0},
      components:(Array.isArray(raw.components)?raw.components:[]).map(normalizeComponent).filter(item=>item.id)
    };
  }

  function normalize(payload={}) {
    const capabilities=(Array.isArray(payload.capabilities)?payload.capabilities:[])
      .map(normalizeCapability).filter(item=>item.id);
    const summary=payload.summary && typeof payload.summary==='object'?payload.summary:{};
    const baseline=payload.baseline && typeof payload.baseline==='object'?payload.baseline:{};
    return {
      status:text(payload.status||'available',80),
      summary:{
        total:Number(summary.total)||capabilities.length,
        implemented:Number(summary.implemented)||capabilities.filter(item=>item.implemented).length,
        enabled:Number(summary.enabled)||capabilities.filter(item=>item.enabled).length,
        withEvidence:Number(summary.with_evidence)||capabilities.filter(item=>item.evidence.present).length,
        live:Number(summary.live)||capabilities.filter(item=>item.live).length
      },
      baseline:{
        audit:text(baseline.audit,300),inventory:text(baseline.inventory,300),runId:text(baseline.run_id,160),
        gateway:text(baseline.gateway,80),capturedAt:text(baseline.captured_at,80)
      },
      capabilities
    };
  }

  async function refresh(options={}) {
    BeastStore.patch('integrations',{loading:true,error:''});
    try {
      if (BeastDesktopBridge.demoMode) throw new Error('Live integration evidence is unavailable in demo mode.');
      const root=BeastDesktopBridge.workspaceRoot;
      const query=root?`?${new URLSearchParams({root_path:root})}`:'';
      const payload=await BeastDesktopBridge.fetchJson(`/edgek/ide/integrations${query}`,{...options,cacheTtl:0});
      const normalized=normalize(payload);
      BeastStore.transaction(next=>{
        next.integrations={...next.integrations,...normalized,loading:false,error:'',updatedAt:Date.now()};
      });
      return normalized;
    } catch(error) {
      BeastStore.patch('integrations',{loading:false,error:String(error?.message||error),status:'error',updatedAt:Date.now()});
      throw error;
    }
  }

  function bySurface(route='') {
    const surface=text(route,80).replace(/^\//,'');
    return BeastStore.get().integrations.capabilities.filter(item=>item.surfaces.includes(surface));
  }

  function byId(id='') {
    return BeastStore.get().integrations.capabilities.find(item=>item.id===id)||null;
  }

  function mountSurface(root,route) {
    if (!root || !route) return ()=>{};
    const rail=document.createElement('section');
    rail.className='beast-card wide integration-surface-rail';
    rail.setAttribute('data-integration-rail',route);
    const header=root.querySelector('.beast-page-head');
    if (header) header.insertAdjacentElement('afterend',rail); else root.prepend(rail);
    let disposed=false;
    const render=state=>{
      if (disposed) return;
      const integrations=state.integrations||{};
      const rows=(integrations.capabilities||[]).filter(item=>item.surfaces.includes(route));
      const content=rows.map(item=>`<button data-integration-id="${html(item.id,120)}"><span><b>${html(item.title,240)}</b><small>${html(item.mode||item.claim,180)}</small></span><em class="${item.live?'live':item.enabled?'enabled':'disabled'}">${item.live?'LIVE':item.enabled?'ENABLED':'DISABLED'}</em><i class="${item.evidence.present?'has-evidence':''}">${item.evidence.present?'EVIDENCE':'NO EVIDENCE'}</i></button>`).join('');
      rail.innerHTML=`<header><div><b>Mapped Integrations</b><span>implemented · enabled · evidence · live</span></div><button class="integration-rail-atlas" data-integration-atlas>Open Atlas</button></header><div>${content||`<span class="integration-rail-empty">${integrations.loading?'Loading integration map…':integrations.error?'Integration catalog unavailable.':'No mapped integrations reported.'}</span>`}</div>`;
    };
    const unsubscribe=BeastStore.subscribe(render);
    const onClick=event=>{
      const item=event.target.closest('[data-integration-id]');
      if (item) BeastStore.patch('integrations',{selectedId:item.dataset.integrationId});
      if (item || event.target.closest('[data-integration-atlas]')) BeastRouter.navigate('atlas');
    };
    rail.addEventListener('click',onClick);
    if (!BeastStore.get().integrations.updatedAt && !BeastStore.get().integrations.loading) refresh().catch(()=>{});
    return ()=>{disposed=true;unsubscribe();rail.removeEventListener('click',onClick);};
  }

  function clear() {
    BeastStore.set('integrations',{loading:false,error:'',status:'unloaded',updatedAt:0,selectedId:'',summary:emptySummary(),baseline:{},capabilities:[]});
  }

  window.BeastIntegrationMap={refresh,normalize,bySurface,byId,mountSurface,clear};
})();
