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

  function normalizeLifecycleEvent(raw={}) {
    const source=raw && typeof raw==='object'?raw:{};
    const status=text(source.status,24);
    const stage=text(source.stage,40);
    const effect=source.effect_committed===true;
    return {
      capability:text(source.capability,120),
      status:['fired','skipped','failed'].includes(status)?status:'failed',
      stage:['eligibility','execution','postflight'].includes(stage)?stage:'unclassified',
      operation:text(source.operation,120),
      mode:text(source.mode,120),
      reason:text(source.reason,160),
      effectCommitted:effect,
      metrics:source.metrics && typeof source.metrics==='object'?{...source.metrics}:{},
      artifacts:source.artifacts && typeof source.artifacts==='object'?{...source.artifacts}:{},
      // Interception receipts carry their own producer-sourced savings claim.
      savings:source.savings && typeof source.savings==='object'?{...source.savings}:undefined,
      savedTokens:Number.isSafeInteger(Number(source.saved_tokens))
        ? Number(source.saved_tokens) : undefined,
      tokensEmitted:Number.isSafeInteger(Number(source.tokens_emitted))
        ? Number(source.tokens_emitted) : undefined,
      // A producer assertion is not independent durability verification.
      durabilityVerified:false,
      runId:text(source.run_id,160),
      sessionId:text(source.session_id,160),
      sequence:Number.isSafeInteger(Number(source.sequence))
        && Number(source.sequence)>0
        ? Number(source.sequence) : 0
    };
  }

  // BEAST_INTEGRATION_003_REPLAY
  // Separate replay custody from the bounded Atlas display buffer.
  const REPLAY_WINDOW = 4096;
  const replayByRun = new Map();

  function acceptReplayIdentity(receipt) {
    const run = receipt.runId;
    const sequence = receipt.sequence;

    if (!run || !Number.isSafeInteger(sequence) || sequence <= 0) {
      return true;
    }

    let ledger = replayByRun.get(run);

    if (!ledger) {
      ledger = {
        maximum: 0,
        seen: new Set()
      };
      replayByRun.set(run, ledger);
    }

    // Reject events outside the retained replay horizon.
    if (
      ledger.maximum > REPLAY_WINDOW &&
      sequence <= ledger.maximum - REPLAY_WINDOW
    ) {
      return false;
    }

    if (ledger.seen.has(sequence)) {
      return false;
    }

    ledger.maximum = Math.max(ledger.maximum, sequence);
    ledger.seen.add(sequence);

    const floor = ledger.maximum - REPLAY_WINDOW;

    for (const value of ledger.seen) {
      if (value <= floor) ledger.seen.delete(value);
    }

    return true;
  }

  function recordLifecycleEvent(raw={}) {
    const receipt=normalizeLifecycleEvent(raw);
    if (!receipt.capability) return null;
    if (!acceptReplayIdentity(receipt)) return null;
    let inserted=false;
    BeastStore.transaction(next=>{
      const prior=next.integrations.lifecycleEvents||[];
      const identity=receipt.runId && receipt.sequence>0
        ? `${receipt.runId}:${receipt.sequence}` : '';
      if (identity && prior.some(item=>
        item.runId===receipt.runId && item.sequence===receipt.sequence
      )) return;
      next.integrations.lifecycleEvents=[...prior,receipt].slice(-100);
      inserted=true;
    });
    return inserted ? receipt : null;
  }

  function clear() {
    replayByRun.clear();
    BeastStore.set('integrations',{loading:false,error:'',status:'unloaded',updatedAt:0,selectedId:'',summary:emptySummary(),baseline:{},capabilities:[],lifecycleEvents:[]});
  }

  window.BeastIntegrationMap={
    refresh,normalize,bySurface,byId,mountSurface,
    normalizeLifecycleEvent,recordLifecycleEvent,clear
  };
})();
