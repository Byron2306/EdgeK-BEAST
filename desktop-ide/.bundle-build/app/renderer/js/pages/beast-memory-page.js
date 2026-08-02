(() => {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[char]);
  const pct = value => Math.max(0,Math.min(100,Number(value)||0));
  const tone = value => /fail|invalid|missing|degrad|cold/i.test(value) ? 'danger' : /warn|review|watch|queue|candidate/i.test(value) ? 'amber' : /secure|verified|valid|healthy|stable|hot|warm/i.test(value) ? 'live' : '';

  function constellation(memory) {
    const layers=memory.layers||[];
    const nodes=[
      {x:50,y:48,label:'Residue',icon:'memory'}, {x:22,y:26,label:layers[0]?.id||'L0',icon:'workspace'}, {x:72,y:22,label:layers[1]?.id||'L1',icon:'evidence'},
      {x:82,y:66,label:layers[2]?.id||'L2',icon:'crystallization'}, {x:28,y:76,label:layers[3]?.id||'L3',icon:'models'}, {x:52,y:84,label:'Skills',icon:'agents'}
    ];
    const lines=[[0,1],[0,2],[0,3],[0,4],[0,5],[1,2],[2,3],[3,5],[4,5]];
    return `<div class="memory-constellation"><canvas class="premium-memory-canvas" data-premium-canvas="memory" aria-hidden="true"></canvas>${nodes.map((node,index)=>`<button class="memory-star ${index===0?'core':''}" style="--x:${node.x}%;--y:${node.y}%;--delay:${index*.18}s" data-memory-layer="${esc(index===0?(layers[1]?.id||layers[0]?.id||''):node.label)}"><img src="${BeastAssets.icon(node.icon)}" alt=""><span>${esc(node.label)}</span></button>`).join('')}</div>`;
  }

  function template(){
    const root=document.createElement('div'); root.className='beast-page beast-memory-page';
    root.innerHTML=`
      <header class="beast-page-head sticky-phase-head">
        <div><h2>Memory Observatory</h2><div class="sub">RECALL GRAPH // VERIFIED RESIDUE // FRESHNESS // SKILL CRYSTALLIZATION</div></div>
        <div class="beast-page-actions"><button class="beast-button secondary" data-memory-action="export"><img src="${BeastAssets.icon('files')}" alt="">Export Index</button><button class="beast-button amber" data-memory-action="compact"><img src="${BeastAssets.icon('memory')}" alt="">Compact Queue</button><button class="beast-button hot" data-memory-action="refresh"><img src="${BeastAssets.icon('diagnostics')}" alt="">Refresh Memory</button></div>
      </header>

      <section class="memory-summary-grid">
        <article class="beast-card memory-summary-card"><img src="${BeastAssets.icon('memory')}" alt=""><div><h3>Mission Memory</h3><strong data-memory-records>0</strong><span>trace-linked records</span></div></article>
        <article class="beast-card memory-summary-card"><img src="${BeastAssets.icon('evidence')}" alt=""><div><h3>Evidence Residue</h3><strong data-memory-evidence>0</strong><span>verified proof objects</span></div></article>
        <article class="beast-card memory-summary-card"><img src="${BeastAssets.icon('context')}" alt=""><div><h3>Freshness</h3><strong data-memory-freshness>0%</strong><span>decay under threshold</span></div></article>
        <article class="beast-card memory-summary-card"><img src="${BeastAssets.icon('crystallization')}" alt=""><div><h3>Residue Quality</h3><strong data-memory-residue>0%</strong><span>fingerprint-bound capability</span></div></article>
        <article class="beast-card memory-summary-card"><img src="${BeastAssets.icon('agents')}" alt=""><div><h3>Skill Candidates</h3><strong data-memory-skills>0</strong><span>awaiting promotion</span></div></article>
      </section>

      <div class="memory-main-grid">
        <section class="beast-card wide memory-core-panel">
          <header class="beast-panel-head"><div><h3>Recall Constellation</h3><span>Semantic relationships across governed memory layers</span></div><span class="beast-pill live" data-memory-health-pill>0% HEALTH</span></header>
          <div class="memory-core-layout"><div class="memory-core-emblem" data-memory-core style="--value:0"><img src="${BeastAssets.icon('memory-core')}" alt="Memory recall core"><strong data-memory-health>0%</strong><small>recall health</small></div><div data-memory-constellation></div></div>
        </section>
        <section class="beast-card memory-recall-panel">
          <header class="beast-panel-head"><div><h3>Active Recall</h3><span>Query verified local memory</span></div><span class="beast-pill" data-recall-count>0 MATCHES</span></header>
          <form class="memory-recall-form" data-memory-recall-form><input data-memory-query placeholder="Recall mission, file, decision, or residue…"><button class="beast-button" type="submit"><img src="${BeastAssets.icon('memory')}" alt="">Recall</button></form>
          <div class="memory-recall-results" data-memory-recall-results></div>
          <article class="memory-record-detail" data-memory-record-detail></article>
        </section>
      </div>

      <div class="memory-layer-grid">
        <section class="beast-card memory-layer-panel">
          <header class="beast-panel-head"><div><h3>Memory Stack</h3><span>Hot working context through durable archive</span></div><span class="beast-pill" data-layer-count>0 LAYERS</span></header>
          <div class="memory-layer-list" data-memory-layers></div>
        </section>
        <section class="beast-card memory-layer-detail-panel">
          <header class="beast-panel-head"><div><h3>Selected Layer</h3><span>Scope, health, and retrieval surfaces</span></div><img src="${BeastAssets.icon('memory')}" alt=""></header>
          <article data-memory-layer-detail></article>
          <div class="memory-view-cloud" data-memory-views></div>
        </section>
        <section class="beast-card memory-security-panel">
          <header class="beast-panel-head"><div><h3>Memory Security</h3><span>Hull // Seal // Passport</span></div><button class="beast-button secondary" data-nav="trust"><img src="${BeastAssets.icon('trust')}" alt="">Open Trust</button></header>
          <div class="memory-security-stack" data-memory-security></div>
        </section>
      </div>

      <div class="memory-lower-grid">
        <section class="beast-card memory-truth-panel">
          <header class="beast-panel-head"><div><h3>Truth Stores</h3><span>Authoritative local stores</span></div><span class="beast-pill live">LOCAL</span></header><div class="memory-truth-list" data-memory-truth></div>
        </section>
        <section class="beast-card memory-skills-panel">
          <header class="beast-panel-head"><div><h3>Skill Crystallization</h3><span>Reusable capability candidates</span></div><button class="beast-button secondary" data-memory-action="promote"><img src="${BeastAssets.icon('crystallization')}" alt="">Promote Top</button></header>
          <div class="memory-skill-radar"><i></i><i></i><i></i><span data-skill-radar>${0}</span></div><p>Verified residue can compound into local capability after promotion, policy lint, and reproducibility checks.</p>
        </section>
        <section class="beast-card wide memory-event-panel">
          <header class="beast-panel-head"><div><h3>Recent Memory Events</h3><span>Compaction, recall, residue, and promotion ledger</span></div><i class="trust-live-dot"></i></header><div class="memory-event-list" data-memory-events></div>
        </section>
      </div>`;
    return root;
  }

  function renderer({signal}={}){
    const root=template();let disposed=false,lastKey='',memoryCanvasDispose=()=>{};
    function patch(state){
      if(disposed)return;const memory=state.memory||{};const key=JSON.stringify(memory);if(key===lastKey)return;lastKey=key;
      root.querySelector('[data-memory-records]').textContent=Number(memory.records||0).toLocaleString();
      root.querySelector('[data-memory-evidence]').textContent=Number(memory.evidenceItems||0).toLocaleString();
      root.querySelector('[data-memory-freshness]').textContent=`${pct(memory.freshness)}%`;
      root.querySelector('[data-memory-residue]').textContent=`${pct(memory.residueQuality)}%`;
      root.querySelector('[data-memory-skills]').textContent=memory.skillCandidates||0;
      root.querySelector('[data-memory-health]').textContent=`${pct(memory.recallHealth)}%`;
      root.querySelector('[data-memory-core]').style.setProperty('--value',pct(memory.recallHealth));
      root.querySelector('[data-memory-health-pill]').textContent=`${pct(memory.recallHealth)}% HEALTH`;
      root.querySelector('[data-memory-constellation]').innerHTML=constellation(memory); memoryCanvasDispose(); memoryCanvasDispose=BeastVisualCanvas.auto(root.querySelector('[data-memory-constellation]'));
      const results=memory.recallResults||[];const selectedRecord=results.find(item=>item.id===memory.selectedRecordId)||results[0];
      root.querySelector('[data-recall-count]').textContent=`${results.length} MATCHES`;
      const queryInput=root.querySelector('[data-memory-query]');if(document.activeElement!==queryInput)queryInput.value=memory.query||'';
      root.querySelector('[data-memory-recall-results]').innerHTML=results.length?results.map(item=>`<button class="memory-recall-row ${item.id===selectedRecord?.id?'selected':''}" data-memory-record="${esc(item.id)}"><span>${pct(item.score)}%</span><div><b>${esc(item.label)}</b><small>${esc(item.layer)} · ${esc(item.source)} · ${esc(item.age)}</small></div><em>›</em></button>`).join(''):'<div class="cortex-empty-list">No recall matches.</div>';
      root.querySelector('[data-memory-record-detail]').innerHTML=selectedRecord?`<span>SELECTED MEMORY</span><h4>${esc(selectedRecord.label)}</h4><p>Retrieved from ${esc(selectedRecord.layer)} with ${pct(selectedRecord.score)}% confidence.</p><small>${esc(selectedRecord.source)} · ${esc(selectedRecord.age)}</small>`:'<p>Run a recall query.</p>';
      const layers=memory.layers||[];const selectedLayer=layers.find(item=>item.id===memory.selectedLayerId)||layers[0];
      root.querySelector('[data-layer-count]').textContent=`${layers.length} LAYERS`;
      root.querySelector('[data-memory-layers]').innerHTML=layers.length?layers.map((item,index)=>`<button class="memory-layer-row ${item.id===selectedLayer?.id?'selected':''} ${tone(item.status)}" data-memory-layer="${esc(item.id)}"><span>${esc(item.id)}</span><div><b>${esc(item.name)}</b><small>${Number(item.records||0).toLocaleString()} records · ${pct(item.freshness)}% fresh</small></div><em>${esc(item.status)}</em><i style="--fresh:${pct(item.freshness)}%"></i></button>`).join(''):'<div class="cortex-empty-list">No memory layers reported.</div>';
      root.querySelector('[data-memory-layer-detail]').innerHTML=selectedLayer?`<span class="layer-id">${esc(selectedLayer.id)}</span><h4>${esc(selectedLayer.name)}</h4><p>${esc(selectedLayer.scope)}</p><div class="layer-metrics"><b>${Number(selectedLayer.records||0).toLocaleString()} records</b><b>${pct(selectedLayer.freshness)}% freshness</b><b>${esc(selectedLayer.status)}</b></div>`:'<p>Select a layer.</p>';
      root.querySelector('[data-memory-views]').innerHTML=(memory.retrievalViews||[]).map(item=>`<span>${esc(item)}</span>`).join('');
      const security=memory.security||{};
      const sec=[{label:'Hull',value:`${security.hull?.verified||0} verified`,status:security.hull?.status||'Checking'},{label:'Seal',value:security.seal?.mode||'unavailable',status:security.seal?.status||'Checking'},{label:'Passport',value:`${security.passport?.policies||0} policies`,status:security.passport?.status||'Checking'}];
      root.querySelector('[data-memory-security]').innerHTML=sec.map(item=>`<article class="${tone(item.status)}"><span>${esc(item.label)}</span><b>${esc(item.value)}</b><em>${esc(item.status)}</em></article>`).join('');
      root.querySelector('[data-memory-truth]').innerHTML=(memory.truthStores||[]).map(item=>`<article class="${tone(item.status)}"><img src="${BeastAssets.icon(item.id==='evidence'?'evidence':item.id==='crystal'?'crystallization':'memory')}" alt=""><div><b>${esc(item.label)}</b><small>${Number(item.records||0).toLocaleString()} records</small></div><em>${esc(item.status)}</em></article>`).join('')||'<div class="cortex-empty-list">No truth stores.</div>';
      root.querySelector('[data-skill-radar]').textContent=memory.skillCandidates||0;
      root.querySelector('[data-memory-events]').innerHTML=(memory.events||[]).map(item=>`<div><time>${esc(item.time)}</time><span>${esc(item.label)}</span></div>`).join('')||'<div class="cortex-empty-list">No memory events.</div>';
    }
    const unsubscribe=BeastStore.subscribe(patch);
    root.addEventListener('click',async event=>{
      const layer=event.target.closest('[data-memory-layer]');if(layer){BeastTrustMemoryBridge.selectLayer(layer.dataset.memoryLayer);return;}
      const record=event.target.closest('[data-memory-record]');if(record){BeastTrustMemoryBridge.selectRecord(record.dataset.memoryRecord);return;}
      const action=event.target.closest('[data-memory-action]')?.dataset.memoryAction;if(!action)return;
      try{
        if(action==='refresh')await BeastTrustMemoryBridge.refreshMemory({signal});
        if(action==='compact'){await BeastTrustMemoryBridge.compact({signal});BeastFX.trigger('burst',event.target,{size:260});}
        if(action==='promote'){await BeastTrustMemoryBridge.promoteSkill('top candidate',{signal});BeastFX.trigger('success',event.target,{size:260});}
        if(action==='export'){
          const memory=BeastStore.get().memory;const blob=new Blob([JSON.stringify(memory,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=`beast-memory-index-${Date.now()}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);BeastStore.addLedger('Memory index exported');
        }
      }catch(error){BeastStore.patch('memory',{loading:false,error:String(error.message||error)});BeastFX.trigger('warning',event.target,{size:280});}
    });
    root.querySelector('[data-memory-recall-form]').addEventListener('submit',async event=>{event.preventDefault();const input=root.querySelector('[data-memory-query]');try{await BeastTrustMemoryBridge.recall(input.value,{signal});BeastFX.trigger('scan',input,{size:260});}catch(error){BeastStore.patch('memory',{loading:false,error:String(error.message||error)});}});
    if(!BeastStore.get().memory?.updatedAt)queueMicrotask(()=>BeastTrustMemoryBridge.refreshMemory({signal}).catch(()=>{}));
    return{node:root,dispose(){disposed=true;unsubscribe();memoryCanvasDispose();}};
  }
  window.BeastMemoryPage={renderer};
})();
