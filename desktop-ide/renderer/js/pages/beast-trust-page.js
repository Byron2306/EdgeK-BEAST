(() => {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[char]);
  const pct = value => Math.max(0,Math.min(100,Number(value)||0));
  const tone = value => /fail|invalid|missing|degrad|violation|critical/i.test(value) ? 'danger' : /warn|review|guarded|scheduled|required/i.test(value) ? 'amber' : /secure|verified|valid|healthy|enforced|armed/i.test(value) ? 'live' : '';

  function template() {
    const root=document.createElement('div');
    root.className='beast-page beast-trust-page';
    root.innerHTML=`
      <header class="beast-page-head sticky-phase-head">
        <div><h2>Trust Posture</h2><div class="sub">LOCAL BOUNDARY // INTEGRITY // POLICY GUARDRAILS // ATTESTATION</div></div>
        <div class="beast-page-actions"><button class="beast-button secondary" data-trust-action="policies"><img src="${BeastAssets.icon('policies')}" alt="">Policy Matrix</button><button class="beast-button amber" data-trust-action="verify"><img src="${BeastAssets.icon('trust')}" alt="">Verify Integrity</button><button class="beast-button hot" data-trust-action="refresh"><img src="${BeastAssets.icon('diagnostics')}" alt="">Refresh Trust</button></div>
      </header>

      <section class="trust-summary-grid">
        <article class="beast-card trust-score-card"><div class="trust-score-orbit" data-trust-orbit style="--value:0"><span data-trust-score>0%</span><small>trust score</small></div><div><h3 data-trust-status>Checking</h3><p data-trust-policy>Policy loading</p><strong data-trust-systems>0/0 systems</strong></div></article>
        <article class="beast-card trust-summary-card"><img src="${BeastAssets.icon('workspace')}" alt=""><div><h3>Data Boundary</h3><strong data-boundary-mode>Local-First</strong><span data-boundary-network>checking network posture</span></div></article>
        <article class="beast-card trust-summary-card"><img src="${BeastAssets.icon('trust')}" alt=""><div><h3>Integrity</h3><strong data-integrity-status>Checking</strong><span data-integrity-facts>agents · models · evidence</span></div></article>
        <article class="beast-card trust-summary-card"><img src="${BeastAssets.icon('policies')}" alt=""><div><h3>Policy Guardrails</h3><strong data-guardrail-status>Checking</strong><span data-guardrail-facts>decisions · approvals · violations</span></div></article>
      </section>

      <div class="trust-main-grid">
        <section class="beast-card wide trust-provenance-panel">
          <header class="beast-panel-head"><div><h3>Provenance & Signatures</h3><span>Mission artifact root and cryptographic identity</span></div><span class="beast-pill" data-provenance-valid>CHECKING</span></header>
          <div class="trust-provenance-body">
            <div class="trust-proof-emblem"><img src="${BeastAssets.icon('trust-core')}" alt="BEAST trust proof"></div>
            <div class="trust-provenance-facts">
              <div><span>Root ID</span><b data-provenance-root>unresolved</b></div><div><span>Algorithm</span><b data-provenance-algorithm>SHA-256</b></div><div><span>Signed By</span><b data-provenance-signer>pending</b></div><div><span>Signed At</span><b data-provenance-time>pending</b></div>
            </div>
            <div class="trust-chain-premium" aria-label="Verified provenance chain"><span></span><span></span><span></span><span></span><span></span></div>
          </div>
        </section>
        <section class="beast-card trust-security-panel">
          <header class="beast-panel-head"><div><h3>Memory Security Triad</h3><span>Hull // Residue Seal // Agent Passport</span></div><span class="beast-pill" data-security-state>CHECKING</span></header>
          <div class="trust-security-triad" data-security-triad></div>
        </section>
      </div>

      <div class="trust-ops-grid">
        <section class="beast-card trust-canary-panel">
          <header class="beast-panel-head"><div><h3>Canary Network</h3><span>Continuous subsystem monitoring</span></div><i class="trust-live-dot"></i></header>
          <div class="trust-canary-grid" data-trust-canaries></div>
        </section>
        <section class="beast-card trust-controls-panel">
          <header class="beast-panel-head"><div><h3>Trust Controls</h3><span>Select a control to inspect its contract</span></div><span class="beast-pill" data-control-count>0 CONTROLS</span></header>
          <div class="trust-control-grid" data-trust-controls></div>
          <article class="trust-control-detail" data-control-detail></article>
        </section>
      </div>

      <div class="trust-lower-grid">
        <section class="beast-card wide trust-permissions-panel">
          <header class="beast-panel-head"><div><h3>Permission Lattice</h3><span>Role-based access with least-privilege enforcement</span></div><button class="beast-button secondary" data-trust-action="access"><img src="${BeastAssets.icon('trust')}" alt="">Manage Access</button></header>
          <div class="trust-permission-table"><div class="head"><span>Principal</span><span>Access</span><span>Scope</span><span>Verification</span></div><div data-trust-permissions></div></div>
        </section>
        <section class="beast-card trust-attestations-panel">
          <header class="beast-panel-head"><div><h3>Attestations</h3><span>Hardware and workspace proofs</span></div><img src="${BeastAssets.icon('trust')}" onerror="this.src='${BeastAssets.icon('trust')}'" alt=""></header>
          <div class="trust-attestation-list" data-trust-attestations></div>
        </section>
        <section class="beast-card trust-activity-panel">
          <header class="beast-panel-head"><div><h3>Audit Timeline</h3><span>Live trust ledger</span></div><i class="trust-live-dot"></i></header>
          <div class="trust-activity-list" data-trust-activity></div>
        </section>
      </div>`;
    return root;
  }

  function renderer({signal}={}) {
    const root=template(); let disposed=false; let lastKey='';
    function patch(state) {
      if(disposed) return;
      const trust=state.trust||{};
      const key=JSON.stringify([trust,state.ledger.slice(0,10)]); if(key===lastKey) return; lastKey=key;
      const score=pct(trust.score);
      root.querySelector('[data-trust-orbit]').style.setProperty('--value',score);
      root.querySelector('[data-trust-score]').textContent=`${score}%`;
      root.querySelector('[data-trust-status]').textContent=trust.status||'Checking';
      root.querySelector('[data-trust-policy]').textContent=`Policy: ${trust.policy||'Local First'}`;
      root.querySelector('[data-trust-systems]').textContent=`${trust.systemsHealthy||0}/${trust.systemsTotal||0} systems healthy`;
      root.querySelector('[data-boundary-mode]').textContent=trust.boundary?.mode||'Local-First';
      root.querySelector('[data-boundary-network]').textContent=`Network ${trust.boundary?.network||'checking'} · Telemetry ${trust.boundary?.telemetry||'checking'}${trust.boundary?.airGap?' · Air-gap capable':''}`;
      root.querySelector('[data-integrity-status]').textContent=trust.integrity?.status||'Checking';
      root.querySelector('[data-integrity-facts]').textContent=`${trust.integrity?.agents||0} agents · ${trust.integrity?.models||0} models · ${trust.integrity?.evidence||0} evidence`;
      root.querySelector('[data-guardrail-status]').textContent=trust.guardrails?.status||'Checking';
      root.querySelector('[data-guardrail-facts]').textContent=`${trust.guardrails?.decisions||0} decisions · ${trust.guardrails?.approvals||0} approvals · ${trust.guardrails?.violations||0} violations`;
      const provenance=trust.provenance||{};
      root.querySelector('[data-provenance-root]').textContent=provenance.rootId||'unresolved';
      root.querySelector('[data-provenance-algorithm]').textContent=provenance.algorithm||'SHA-256';
      root.querySelector('[data-provenance-signer]').textContent=provenance.signedBy||'pending';
      root.querySelector('[data-provenance-time]').textContent=provenance.signedAt||'pending';
      const valid=root.querySelector('[data-provenance-valid]'); valid.textContent=provenance.valid?'VALID SIGNATURE':'UNVERIFIED'; valid.className=`beast-pill ${provenance.valid?'live':'amber'}`;
      const security=trust.security||{};
      const securityItems=[
        {id:'hull',label:'Memory Hull',icon:'memory',value:`${security.hull?.verified||0} verified`,status:security.hull?.status||'Checking',detail:`${security.hull?.failed||0} failed sidecars`},
        {id:'seal',label:'Residue Seal',icon:'crystallization',value:security.seal?.mode||'unavailable',status:security.seal?.status||'Checking',detail:security.seal?.exists?'Fingerprint key available':'No key reported'},
        {id:'passport',label:'Agent Passport',icon:'agents',value:`${security.passport?.policies||0} policies`,status:security.passport?.status||'Checking',detail:security.passport?.valid?'Policy lint valid':'Policy review required'}
      ];
      root.querySelector('[data-security-triad]').innerHTML=securityItems.map(item=>`<article class="trust-security-node ${tone(item.status)}"><img src="${BeastAssets.icon(item.icon)}" alt=""><div><span>${esc(item.label)}</span><b>${esc(item.value)}</b><small>${esc(item.detail)}</small></div><em>${esc(item.status)}</em></article>`).join('');
      const securityOk=security.hull?.failed===0 && security.seal?.exists && security.passport?.valid;
      const securityPill=root.querySelector('[data-security-state]'); securityPill.textContent=securityOk?'TRIAD SECURE':'REVIEW'; securityPill.className=`beast-pill ${securityOk?'live':'amber'}`;
      const canaries=trust.canaries||[];
      root.querySelector('[data-trust-canaries]').innerHTML=canaries.length?canaries.map((item,index)=>`<article class="trust-canary ${tone(item.status)}"><div class="canary-orbit"><span>${String(index+1).padStart(2,'0')}</span></div><div><b>${esc(item.label)}</b><small>${esc(item.detail)}</small></div><em>${esc(item.status)}</em></article>`).join(''):'<div class="cortex-empty-list">No canary telemetry.</div>';
      const controls=trust.controls||[]; const selected=controls.find(item=>item.id===trust.selectedControlId)||controls[0];
      root.querySelector('[data-control-count]').textContent=`${controls.length} CONTROLS`;
      root.querySelector('[data-trust-controls]').innerHTML=controls.map(item=>`<button class="trust-control-node ${item.id===selected?.id?'selected':''} ${tone(item.status)}" data-control-id="${esc(item.id)}"><img src="${BeastAssets.icon(item.id==='evidence'?'evidence':item.id==='agent'?'agents':item.id==='policy'?'policies':'trust')}" alt=""><span>${esc(item.label)}</span><em>${esc(item.status)}</em></button>`).join('');
      root.querySelector('[data-control-detail]').innerHTML=selected?`<img src="${BeastAssets.icon('trust')}" alt=""><div><span>CONTROL CONTRACT</span><h4>${esc(selected.label)}</h4><p>${esc(selected.detail)}</p><small>Status: ${esc(selected.status)} · least-privilege governed</small></div>`:'<p>Select a control.</p>';
      const permissions=trust.permissions||[];
      root.querySelector('[data-trust-permissions]').innerHTML=permissions.length?permissions.map(item=>`<div class="row"><b>${esc(item.role)}</b><span>${esc(item.access)}</span><span>${esc(item.scope)}</span><em class="${tone(item.status)}">${esc(item.status)}</em></div>`).join(''):'<div class="cortex-empty-list">No permission records.</div>';
      const attestations=trust.attestations||[];
      root.querySelector('[data-trust-attestations]').innerHTML=attestations.length?attestations.map(item=>`<article class="trust-attestation ${tone(item.status)}"><img src="${BeastAssets.icon('trust')}" alt=""><div><b>${esc(item.label)}</b><small>${esc(item.id)} · valid until ${esc(item.expires)}</small></div><em>${esc(item.status)}</em></article>`).join(''):'<div class="cortex-empty-list">No attestations.</div>';
      root.querySelector('[data-trust-activity]').innerHTML=state.ledger.slice(0,10).map(item=>`<div><time>${esc(item.time)}</time><span>${esc(item.label)}</span></div>`).join('');
    }
    const unsubscribe=BeastStore.subscribe(patch);
    root.addEventListener('click',async event=>{
      const control=event.target.closest('[data-control-id]'); if(control){BeastTrustMemoryBridge.selectControl(control.dataset.controlId);return;}
      const action=event.target.closest('[data-trust-action]')?.dataset.trustAction; if(!action)return;
      try{
        if(action==='refresh') await BeastTrustMemoryBridge.refreshTrust({signal});
        if(action==='verify'){BeastMascot.setState('working');await BeastTrustMemoryBridge.verifyIntegrity({signal});BeastFX.trigger('success',event.target,{size:320});BeastMascot.setState('finished');setTimeout(()=>BeastMascot.setState('idle'),1900);}
        if(action==='policies') document.dispatchEvent(new CustomEvent('beast:command',{detail:{command:'/policy matrix'}}));
        if(action==='access') document.dispatchEvent(new CustomEvent('beast:command',{detail:{command:'/trust access'}}));
      }catch(error){BeastStore.patch('trust',{loading:false,error:String(error.message||error)});BeastFX.trigger('warning',event.target,{size:280});}
    });
    if(!BeastStore.get().trust?.updatedAt) queueMicrotask(()=>BeastTrustMemoryBridge.refreshTrust({signal}).catch(()=>{}));
    return{node:root,dispose(){disposed=true;unsubscribe();}};
  }
  window.BeastTrustPage={renderer};
})();
