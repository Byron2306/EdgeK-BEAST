(() => {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[char]);
  const pct = value => Math.max(0,Math.min(100,Number(value)||0));
  const tone = value => /error|fail|invalid|critical/i.test(value) ? 'danger' : /warn|review|partial/i.test(value) ? 'amber' : /valid|pass|verified|indexed/i.test(value) ? 'live' : '';

  function template(){
    const root=document.createElement('div');
    root.className='beast-page beast-evidence-page';
    root.innerHTML=`
      <header class="beast-page-head sticky-phase-head">
        <div><h2>Evidence Forge</h2><div class="sub">COLLECT // VALIDATE // TRACE // PACKAGE // EXPORT</div></div>
        <div class="beast-page-actions"><button class="beast-button secondary" data-evidence-action="clear">Clear Selection</button><button class="beast-button" data-evidence-action="pack">Build Audit Pack</button><button class="beast-button hot" data-evidence-action="refresh">Refresh Evidence</button></div>
      </header>
      <section class="evidence-summary-grid">
        <article class="beast-card evidence-summary"><img src="${BeastAssets.icon('evidence')}" alt=""><div><h3>Artifacts Indexed</h3><strong data-evidence-total>0</strong><span>workspace + evidence bus</span></div></article>
        <article class="beast-card evidence-summary"><img src="${BeastAssets.icon('trust')}" alt=""><div><h3>Overall Validity</h3><strong data-evidence-validity>0%</strong><span>schema and trace confidence</span></div></article>
        <article class="beast-card evidence-summary"><img src="${BeastAssets.icon('context')}" alt=""><div><h3>Selected Evidence</h3><strong data-evidence-selected>0</strong><span data-evidence-ready>pack not ready</span></div></article>
        <article class="beast-card evidence-summary"><img src="${BeastAssets.icon('network')}" alt=""><div><h3>Trace Links</h3><strong data-evidence-traces>0</strong><span>cross-artifact relationships</span></div></article>
      </section>

      <div class="evidence-main-grid">
        <section class="beast-card evidence-library-panel">
          <header class="beast-panel-head"><div><h3>Evidence Library</h3><span data-evidence-count>0 visible</span></div><button class="beast-button secondary" data-evidence-action="select-visible">Select Visible</button></header>
          <div class="evidence-filter-bar"><input class="beast-filter" data-evidence-search placeholder="Search paths, source, status…"><select data-evidence-filter><option value="all">All status</option><option value="validated">Validated</option><option value="review">Review</option><option value="warning">Warning</option><option value="selected">Selected only</option></select></div>
          <div class="evidence-file-list" data-evidence-list></div>
        </section>

        <section class="beast-card wide evidence-detail-panel">
          <header class="beast-panel-head"><div><h3>Selected Artifact</h3><span data-evidence-path>none</span></div><div class="evidence-detail-actions"><button class="beast-button secondary" data-evidence-action="toggle">Toggle Selection</button><button class="beast-button" data-evidence-action="preview">Load Preview</button></div></header>
          <article class="evidence-artifact-hero" data-evidence-hero></article>
          <section class="evidence-metric-grid" data-evidence-metrics></section>
          <div class="evidence-preview-tabs"><button class="active">Content Preview</button><button>Trace Context</button><button>Metadata</button></div>
          <pre class="evidence-content-preview" data-evidence-preview>Select an artifact and load its preview.</pre>
          <section class="evidence-trace-strip" data-evidence-trace-strip></section>
        </section>
      </div>

      <div class="evidence-lower-grid">
        <section class="beast-card wide audit-pack-panel">
          <header class="beast-panel-head"><div><h3>Audit Pack Assembly</h3><span>Immutable review bundle</span></div><span class="beast-pill" data-pack-state>NOT READY</span></header>
          <div class="audit-pack-progress"><div class="audit-pack-ring" data-pack-ring style="--value:0"><span data-pack-value>0%</span></div><div class="audit-pack-checks" data-pack-checks></div><div class="audit-pack-actions"><button class="beast-button hot" data-evidence-action="pack">Compile Pack</button><button class="beast-button" data-evidence-action="export">Export JSON</button><button class="beast-button secondary" data-nav="review">Open Review</button></div></div>
        </section>
        <section class="beast-card trace-map-panel">
          <header class="beast-panel-head"><div><h3>Trace Lattice</h3><span>Selected artifact relationships</span></div><i class="activity-live-dot"></i></header>
          <div class="trace-lattice" data-trace-lattice><div class="trace-core"><img src="${BeastAssets.icon('evidence')}" alt=""><span>Evidence</span></div></div>
        </section>
      </div>`;
    return root;
  }

  function renderer({signal}={}){
    const root=template();
    let disposed=false;
    let lastListKey='';

    function patch(state){
      if(disposed)return;
      const evidence=state.evidence||{};
      const files=evidence.files||[];
      const visibleIds=evidence.filteredIds?.length || evidence.query || evidence.filter!=='all' ? evidence.filteredIds||[] : files.map(row=>row.id);
      const visible=files.filter(row=>visibleIds.includes(row.id));
      const selected=files.find(row=>row.id===evidence.selectedId)||files[0];
      const selectedSet=new Set(evidence.selectedIds||[]);
      const traces=files.reduce((sum,row)=>sum+(Number(row.traces)||0),0);
      const pack=evidence.pack||{};
      const packScore=Math.min(100,Math.round((Math.min(3,selectedSet.size)/3)*45 + (selectedSet.size? (pack.validationPassed/selectedSet.size)*40:0) + (pack.generatedAt?15:0)));

      root.querySelector('[data-evidence-total]').textContent=files.length;
      root.querySelector('[data-evidence-validity]').textContent=`${pct(evidence.validity)}%`;
      root.querySelector('[data-evidence-selected]').textContent=selectedSet.size;
      root.querySelector('[data-evidence-ready]').textContent=pack.ready?'audit pack ready':'select at least 3 artifacts';
      root.querySelector('[data-evidence-traces]').textContent=traces;
      root.querySelector('[data-evidence-count]').textContent=`${visible.length} visible`;
      root.querySelector('[data-evidence-search]').value=evidence.query||'';
      root.querySelector('[data-evidence-filter]').value=evidence.filter||'all';

      const listKey=JSON.stringify([visible,evidence.selectedId,evidence.selectedIds]);
      if(listKey!==lastListKey){lastListKey=listKey;root.querySelector('[data-evidence-list]').innerHTML=visible.length?visible.map(row=>`
        <button class="evidence-file-row ${row.id===selected?.id?'active':''} ${selectedSet.has(row.id)?'selected':''}" data-evidence-id="${esc(row.id)}">
          <span class="evidence-check" data-evidence-check="${esc(row.id)}">${selectedSet.has(row.id)?'✓':'○'}</span><img src="${BeastAssets.icon(row.type==='PY'?'project':row.type==='JSON'?'context':row.type==='LOG'?'terminal':'files')}" alt=""><div><b>${esc(row.name)}</b><small>${esc(row.path)} · ${esc(row.source)}</small></div><em class="${tone(row.status)}">${esc(row.status)}</em><i>${pct(row.validity)}%</i>
        </button>`).join(''):'<div class="cortex-empty-list">No evidence matches this filter.</div>';}

      root.querySelector('[data-evidence-path]').textContent=selected?.path||'none';
      root.querySelector('[data-evidence-hero]').innerHTML=selected?`<img src="${BeastAssets.icon(selected.type==='PY'?'project':selected.type==='LOG'?'terminal':'evidence')}" alt=""><div><span>ARTIFACT ${esc(selected.id)}</span><h4>${esc(selected.name)}</h4><p>${esc(selected.summary)}</p><small>${esc(selected.type)} · ${esc(selected.size)} · ${esc(selected.source)} · ${esc(selected.added)}</small></div><b class="${tone(selected.status)}">${esc(selected.status)}</b>`:'<p>No artifact selected.</p>';
      root.querySelector('[data-evidence-metrics]').innerHTML=selected?`
        <div><span>Extraction Confidence</span><b>${pct(selected.validity)}%</b><i style="--metric:${pct(selected.validity)}%"></i></div><div><span>Schema Validation</span><b class="${tone(selected.schema)}">${esc(selected.schema)}</b><small>${/valid/i.test(selected.schema)?'No schema violations':'Review required'}</small></div><div><span>Trace Links</span><b>${selected.traces||0}</b><small>linked artifacts</small></div><div><span>Fingerprint</span><b>${esc(selected.hash?selected.hash.slice(0,12):'pending')}</b><small>SHA-256 / local</small></div>`:'';
      root.querySelector('[data-evidence-preview]').textContent=evidence.previewPath===selected?.path&&evidence.preview?evidence.preview:'Select “Load Preview” to inspect the current artifact without rebuilding the page.';
      root.querySelector('[data-evidence-trace-strip]').innerHTML=(evidence.traceLinks||[]).slice(0,8).map(link=>`<button data-trace-id="${esc(link.id)}"><img src="${BeastAssets.icon('network')}" alt=""><span>${esc(link.label)}</span><em>${esc(link.status)}</em></button>`).join('')||'<span class="muted">No trace links reported.</span>';

      root.querySelector('[data-pack-state]').textContent=pack.ready?'PACK READY':'NOT READY';
      root.querySelector('[data-pack-state]').className=`beast-pill ${pack.ready?'live':'amber'}`;
      root.querySelector('[data-pack-ring]').style.setProperty('--value',packScore);
      root.querySelector('[data-pack-value]').textContent=`${packScore}%`;
      root.querySelector('[data-pack-checks]').innerHTML=[
        ['Minimum 3 artifacts',selectedSet.size>=3,`${selectedSet.size}/3`],['Validation threshold',selectedSet.size>0&&pack.validationPassed===selectedSet.size,`${pack.validationPassed||0}/${selectedSet.size}`],['Trace links present',selectedSet.size>0&&files.filter(row=>selectedSet.has(row.id)).every(row=>row.traces>0),'required'],['Review state captured',Boolean(state.review?.updatedAt),'review'],['Manifest compiled',Boolean(pack.generatedAt),'manifest']
      ].map(([label,ok,value])=>`<div class="audit-check ${ok?'pass':''}"><span>${ok?'✓':'○'}</span><b>${esc(label)}</b><em>${esc(value)}</em></div>`).join('');

      const lattice=root.querySelector('[data-trace-lattice]');
      lattice.innerHTML=`<div class="trace-core"><img src="${BeastAssets.icon('evidence')}" alt=""><span>${esc(selected?.name||'Evidence')}</span></div>${(evidence.traceLinks||[]).slice(0,6).map((link,index)=>`<div class="trace-node n${index+1}"><span></span><b>${esc(link.label)}</b></div>`).join('')}<svg viewBox="0 0 500 260" preserveAspectRatio="none" aria-hidden="true"><path d="M250 130 L90 45 M250 130 L250 28 M250 130 L410 45 M250 130 L75 205 M250 130 L250 232 M250 130 L425 205"/></svg>`;
    }

    const unsubscribe=BeastStore.subscribe(patch);
    root.addEventListener('input',event=>{if(event.target.matches('[data-evidence-search]'))BeastReviewEvidenceBridge.applyEvidenceFilter(event.target.value,root.querySelector('[data-evidence-filter]').value);});
    root.addEventListener('change',event=>{if(event.target.matches('[data-evidence-filter]'))BeastReviewEvidenceBridge.applyEvidenceFilter(root.querySelector('[data-evidence-search]').value,event.target.value);});
    root.addEventListener('click',async event=>{
      const check=event.target.closest('[data-evidence-check]');if(check){event.stopPropagation();BeastReviewEvidenceBridge.toggleEvidence(check.dataset.evidenceCheck);return;}
      const row=event.target.closest('[data-evidence-id]');if(row){BeastReviewEvidenceBridge.selectEvidence(row.dataset.evidenceId);return;}
      const action=event.target.closest('[data-evidence-action]')?.dataset.evidenceAction;if(!action)return;
      try{
        const state=BeastStore.get();
        if(action==='refresh')await BeastReviewEvidenceBridge.refreshEvidence({signal});
        if(action==='toggle'&&state.evidence.selectedId)BeastReviewEvidenceBridge.toggleEvidence(state.evidence.selectedId);
        if(action==='preview'&&state.evidence.selectedId)await BeastReviewEvidenceBridge.loadEvidencePreview(state.evidence.selectedId);
        if(action==='clear')BeastStore.patch('evidence',{selectedIds:[],pack:{...state.evidence.pack,ready:false,selected:0,validationPassed:0,generatedAt:0,manifest:null}});
        if(action==='select-visible'){const ids=state.evidence.filteredIds?.length?state.evidence.filteredIds:state.evidence.files.map(row=>row.id);const validationPassed=ids.filter(id=>(state.evidence.files.find(row=>row.id===id)?.validity||0)>=85).length;BeastStore.patch('evidence',{selectedIds:ids,pack:{...state.evidence.pack,selected:ids.length,ready:ids.length>=3,validationPassed}});}
        if(action==='pack'){BeastReviewEvidenceBridge.buildAuditPack();BeastFX.trigger('success',event.target,{size:310});BeastMascot.setState('working');setTimeout(()=>BeastMascot.setState('idle'),1300);}
        if(action==='export')BeastReviewEvidenceBridge.exportAuditPack();
      }catch(error){BeastStore.patch('evidence',{loading:false,error:String(error.message||error)});BeastFX.trigger('warning',event.target,{size:240});}
    });
    if(!BeastStore.get().evidence?.updatedAt)queueMicrotask(()=>BeastReviewEvidenceBridge.refreshEvidence({signal}).catch(()=>{}));
    return{node:root,dispose(){disposed=true;unsubscribe();}};
  }
  window.BeastEvidencePage={renderer};
})();
