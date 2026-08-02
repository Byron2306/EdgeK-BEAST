(() => {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[char]);
  const pct = value => Math.max(0,Math.min(100,Number(value)||0));
  const tone = value => /fail|block|critical|high|unresolved|error/i.test(value) ? 'danger' : /warn|medium|review|pending|changes/i.test(value) ? 'amber' : /pass|approve|ready|resolved|low/i.test(value) ? 'live' : '';

  function template() {
    const root = document.createElement('div');
    root.className = 'beast-page beast-review-page';
    root.innerHTML = `
      <header class="beast-page-head sticky-phase-head">
        <div><h2>Review Center</h2><div class="sub">QUALITY GATES // CONTRADICTION CONTROL // TESTS // APPROVAL DECISION</div></div>
        <div class="beast-page-actions"><button class="beast-button secondary" data-review-action="tests">Re-run Tests</button><button class="beast-button" data-review-action="report">Export Report</button><button class="beast-button hot" data-review-action="refresh">Refresh Review</button></div>
      </header>

      <section class="review-summary-grid">
        <article class="beast-card review-summary-card"><img src="${BeastAssets.icon('trust')}" alt=""><div><h3>Overall Confidence</h3><strong data-review-confidence>0%</strong><span data-review-recommendation>calculating</span></div></article>
        <article class="beast-card review-summary-card"><img src="${BeastAssets.icon('evidence')}" alt=""><div><h3>Evidence Sufficiency</h3><strong data-review-evidence>0%</strong><span>coverage and trace depth</span></div></article>
        <article class="beast-card review-summary-card"><img src="${BeastAssets.icon('alerts')}" alt=""><div><h3>Open Risks</h3><strong data-review-risks>0</strong><span data-review-blockers>0 blockers</span></div></article>
        <article class="beast-card review-summary-card"><img src="${BeastAssets.icon('review')}" alt=""><div><h3>Contradictions</h3><strong data-review-contradictions>0</strong><span data-review-unresolved>0 unresolved</span></div></article>
        <article class="beast-card review-summary-card"><img src="${BeastAssets.icon('policies')}" alt=""><div><h3>Quality Gates</h3><strong data-review-gates>0/0</strong><span data-review-gate-status>pending</span></div></article>
      </section>

      <div class="review-main-grid">
        <section class="beast-card wide review-gates-panel">
          <header class="beast-panel-head"><div><h3>Quality Gates</h3><span>Select a gate to inspect its evidence contract</span></div><span class="beast-pill" data-review-gate-pill>CHECKING</span></header>
          <div class="review-gate-list" data-review-gate-list></div>
          <article class="review-selected-detail" data-review-gate-detail></article>
        </section>
        <section class="beast-card review-approval-panel">
          <header class="beast-panel-head"><div><h3>Approval Workflow</h3><span>Operator decision surface</span></div><span class="beast-pill" data-approval-state>REVIEW</span></header>
          <div class="review-confidence-orbit" data-review-orbit style="--value:0"><span data-review-orbit-value>0%</span><small>confidence</small></div>
          <div class="review-decision-copy" data-review-decision-copy>Review telemetry is loading.</div>
          <div class="review-decision-actions">
            <button class="review-decision approve" data-review-decision="approve"><img src="${BeastAssets.icon('trust')}" alt=""><b>Approve</b><span>Proceed to evidence closure</span></button>
            <button class="review-decision changes" data-review-decision="changes"><img src="${BeastAssets.icon('alerts')}" alt=""><b>Request Changes</b><span>Return blockers to mission</span></button>
            <button class="review-decision rerun" data-review-decision="rerun"><img src="${BeastAssets.icon('review')}" alt=""><b>Re-run Tests</b><span>Validate against current plan</span></button>
          </div>
        </section>
      </div>

      <div class="review-ops-grid">
        <section class="beast-card review-contradiction-panel">
          <header class="beast-panel-head"><div><h3>Contradiction Matrix</h3><span data-contradiction-count>0 findings</span></div><button class="beast-button secondary" data-review-action="resolve">Resolve Selected</button></header>
          <div class="contradiction-list" data-contradiction-list></div>
          <article class="contradiction-detail" data-contradiction-detail></article>
        </section>
        <section class="beast-card review-risk-panel">
          <header class="beast-panel-head"><div><h3>Risks & Blockers</h3><span>Ordered by severity</span></div><button class="beast-button secondary" data-review-action="risk">Open Register</button></header>
          <div class="review-risk-list" data-review-risk-list></div>
        </section>
        <section class="beast-card review-test-panel">
          <header class="beast-panel-head"><div><h3>Test Summary</h3><span data-review-test-meta>0 tests</span></div><span class="beast-pill" data-test-pass-pill>0%</span></header>
          <div class="review-test-ring" data-test-ring style="--value:0"><span data-test-rate>0%</span></div>
          <div class="review-test-list" data-review-test-list></div>
        </section>
      </div>

      <div class="review-lower-grid">
        <section class="beast-card wide review-diff-panel">
          <header class="beast-panel-head"><div><h3>Change Surface</h3><span data-review-plan>SourcePlan and review footprint</span></div><button class="beast-button secondary" data-nav="source">Open SourcePlan</button></header>
          <div class="review-diff-stats">
            <div><span>Changed Files</span><b data-diff-files>0</b></div><div class="plus"><span>Additions</span><b data-diff-additions>0</b></div><div class="minus"><span>Deletions</span><b data-diff-deletions>0</b></div><div><span>Operations</span><b data-diff-operations>0</b></div>
          </div>
          <div class="review-diff-lanes"><div class="before"><b>Previous Plan</b><span>Stable baseline</span><i></i></div><div class="review-diff-arrow">⟶</div><div class="after"><b>Current Plan</b><span>Governed candidate</span><i></i></div></div>
        </section>
        <section class="beast-card review-activity-panel">
          <header class="beast-panel-head"><div><h3>Review Activity</h3><span>Live ledger</span></div><i class="activity-live-dot"></i></header>
          <div class="review-activity-list" data-review-activity></div>
        </section>
      </div>`;
    return root;
  }

  function renderer({signal}={}) {
    const root = template();
    let disposed = false;
    let lastKey = '';
    let observedPlanId = '';

    function patch(state) {
      if (disposed) return;
      const review = state.review || {};
      const livePlanId=String(state.sourcePlan?.plan?.plan_id || '');
      if(livePlanId && livePlanId!==observedPlanId){observedPlanId=livePlanId;queueMicrotask(()=>BeastReviewEvidenceBridge.refreshReview({signal}).catch(()=>{}));}
      const key = JSON.stringify([review,state.ledger.slice(0,8),livePlanId]);
      if (key === lastKey) return; lastKey = key;
      const gates = review.gates || [];
      const contradictions = review.contradictions || [];
      const risks = review.risks || [];
      const tests = review.tests || {total:0,passed:0,failed:0,skipped:0,rows:[]};
      const passed = gates.filter(item=>item.status==='Passed').length;
      const unresolved = contradictions.filter(item=>!/resolved/i.test(item.status)).length;
      const blockers = risks.filter(item=>/blocker|critical/i.test(item.severity)).length;
      const testRate = tests.total ? Math.round((tests.passed/tests.total)*100) : 0;
      const selectedGate = gates.find(item=>item.id===review.selectedGateId) || gates[0];
      const selectedContradiction = contradictions.find(item=>item.id===review.selectedContradictionId) || contradictions[0];

      root.querySelector('[data-review-confidence]').textContent = `${pct(review.confidence)}%`;
      root.querySelector('[data-review-recommendation]').textContent = review.recommendation || 'Review in progress';
      root.querySelector('[data-review-evidence]').textContent = `${pct(review.evidenceSufficiency)}%`;
      root.querySelector('[data-review-risks]').textContent = risks.length;
      root.querySelector('[data-review-blockers]').textContent = `${blockers} blockers`;
      root.querySelector('[data-review-contradictions]').textContent = contradictions.length;
      root.querySelector('[data-review-unresolved]').textContent = `${unresolved} unresolved`;
      root.querySelector('[data-review-gates]').textContent = `${passed}/${gates.length}`;
      root.querySelector('[data-review-gate-status]').textContent = passed === gates.length ? 'all passed' : `${gates.length-passed} pending`;
      root.querySelector('[data-review-gate-pill]').textContent = passed === gates.length ? 'ALL PASSED' : `${gates.length-passed} OPEN`;
      root.querySelector('[data-review-gate-pill]').className = `beast-pill ${passed === gates.length ? 'live':'amber'}`;

      root.querySelector('[data-review-gate-list]').innerHTML = gates.length ? gates.map((gate,index)=>`
        <button class="review-gate ${gate.id===selectedGate?.id?'selected':''} ${tone(gate.status)}" data-review-gate="${esc(gate.id)}">
          <span class="gate-index">${String(index+1).padStart(2,'0')}</span><div><b>${esc(gate.label)}</b><small>${esc(gate.detail)}</small></div><em>${esc(gate.status)}</em><i style="--score:${pct(gate.score)}%"></i>
        </button>`).join('') : '<div class="cortex-empty-list">No quality gates reported.</div>';
      root.querySelector('[data-review-gate-detail]').innerHTML = selectedGate ? `<img src="${BeastAssets.icon(selectedGate.status==='Passed'?'trust':'alerts')}" alt=""><div><span>SELECTED GATE</span><h4>${esc(selectedGate.label)}</h4><p>${esc(selectedGate.detail)}</p><small>Owner: ${esc(selectedGate.owner)} · Score ${pct(selectedGate.score)}%</small></div>` : '<p>Select a quality gate.</p>';

      root.querySelector('[data-review-orbit]').style.setProperty('--value',pct(review.confidence));
      root.querySelector('[data-review-orbit-value]').textContent = `${pct(review.confidence)}%`;
      root.querySelector('[data-approval-state]').textContent = review.approval?.status || 'REVIEW';
      root.querySelector('[data-approval-state]').className = `beast-pill ${tone(review.approval?.status)}`;
      root.querySelector('[data-review-decision-copy]').textContent = review.recommendation === 'Approve' ? 'All critical conditions are satisfied. The candidate can advance to evidence closure and crystallization.' : review.recommendation === 'Changes Requested' ? 'The candidate is promising, but unresolved contradictions or failed tests require correction before approval.' : 'Re-run the governed test surface before making a final decision.';

      root.querySelector('[data-contradiction-count]').textContent = `${contradictions.length} findings`;
      root.querySelector('[data-contradiction-list]').innerHTML = contradictions.length ? contradictions.map(item=>`
        <button class="contradiction-row ${item.id===selectedContradiction?.id?'selected':''} ${tone(item.severity+' '+item.status)}" data-contradiction-id="${esc(item.id)}"><span>${esc(item.id)}</span><div><b>${esc(item.title)}</b><small>${esc(item.status)}</small></div><em>${esc(item.severity)}</em></button>`).join('') : '<div class="cortex-empty-list">No contradictions detected.</div>';
      root.querySelector('[data-contradiction-detail]').innerHTML = selectedContradiction ? `<span class="severity ${tone(selectedContradiction.severity)}">${esc(selectedContradiction.severity)}</span><h4>${esc(selectedContradiction.title)}</h4><p>${esc(selectedContradiction.detail)}</p><small>${selectedContradiction.sources?.length ? `Sources: ${esc(selectedContradiction.sources.join(' · '))}`:'Cross-artifact comparison'}</small>` : '<p>Select a contradiction.</p>';

      root.querySelector('[data-review-risk-list]').innerHTML = risks.length ? risks.map(item=>`<div class="review-risk ${tone(item.severity+' '+item.status)}"><span>${esc(item.id)}</span><div><b>${esc(item.title)}</b><small>${esc(item.owner)}</small></div><em>${esc(item.severity)}</em></div>`).join('') : '<div class="cortex-empty-list">No open risks.</div>';
      root.querySelector('[data-review-test-meta]').textContent = `${tests.total} tests · ${tests.failed} failed`;
      root.querySelector('[data-test-pass-pill]').textContent = `${testRate}% PASS`;
      root.querySelector('[data-test-pass-pill]').className = `beast-pill ${tests.failed ? 'amber':'live'}`;
      root.querySelector('[data-test-ring]').style.setProperty('--value',testRate);
      root.querySelector('[data-test-rate]').textContent = `${testRate}%`;
      root.querySelector('[data-review-test-list]').innerHTML = (tests.rows||[]).map(item=>`<div class="review-test ${tone(item.status)}"><span>${/pass|ok/i.test(item.status)?'✓':/fail|error/i.test(item.status)?'!':'○'}</span><b>${esc(item.label)}</b><em>${esc(item.duration)}</em></div>`).join('') || '<div class="cortex-empty-list">No test telemetry.</div>';

      const diff = review.diff || {};
      root.querySelector('[data-review-plan]').textContent = review.sourcePlanId ? `${review.sourcePlanObjective || 'Pair Programmer proposal'} · ${review.sourcePlanId}` : 'No governed SourcePlan has been selected yet.';
      root.querySelector('[data-diff-files]').textContent = diff.files || 0;
      root.querySelector('[data-diff-additions]').textContent = `+${diff.additions || 0}`;
      root.querySelector('[data-diff-deletions]').textContent = `-${diff.deletions || 0}`;
      root.querySelector('[data-diff-operations]').textContent = diff.operations || 0;
      root.querySelector('[data-review-activity]').innerHTML = state.ledger.slice(0,10).map(item=>`<div><time>${esc(item.time)}</time><span>${esc(item.label)}</span></div>`).join('');
    }

    const unsubscribe = BeastStore.subscribe(patch);
    root.addEventListener('click', async event => {
      const gate = event.target.closest('[data-review-gate]'); if (gate) { BeastReviewEvidenceBridge.selectGate(gate.dataset.reviewGate); return; }
      const contradiction = event.target.closest('[data-contradiction-id]'); if (contradiction) { BeastReviewEvidenceBridge.selectContradiction(contradiction.dataset.contradictionId); return; }
      const decision = event.target.closest('[data-review-decision]')?.dataset.reviewDecision;
      if (decision) { BeastReviewEvidenceBridge.setReviewDecision(decision); BeastFX.trigger(decision==='approve'?'success':'warning',event.target,{size:300}); if(decision==='approve'){BeastMascot.setState('finished');setTimeout(()=>BeastMascot.setState('idle'),1800);} return; }
      const action = event.target.closest('[data-review-action]')?.dataset.reviewAction; if (!action) return;
      try {
        if (action === 'refresh') await BeastReviewEvidenceBridge.refreshReview({signal});
        if (action === 'resolve') { const id=BeastStore.get().review.selectedContradictionId; if(id) BeastReviewEvidenceBridge.resolveContradiction(id); BeastFX.trigger('success',event.target,{size:220}); }
        if (action === 'tests') { BeastReviewEvidenceBridge.setReviewDecision('rerun'); await BeastReviewEvidenceBridge.refreshReview({signal}); }
        if (action === 'report') {
          const state=BeastStore.get();
          const blob=new Blob([JSON.stringify({mission:state.mission,review:state.review},null,2)],{type:'application/json'}); const url=URL.createObjectURL(blob); const link=document.createElement('a'); link.href=url; link.download=`beast-review-${Date.now()}.json`; link.click(); setTimeout(()=>URL.revokeObjectURL(url),1000); BeastStore.addLedger('Review report exported');
        }
        if (action === 'risk') document.dispatchEvent(new CustomEvent('beast:command',{detail:{command:'/review risks'}}));
      } catch(error) { BeastStore.patch('review',{loading:false,error:String(error.message||error)}); BeastFX.trigger('warning',event.target,{size:250}); }
    });

    if (!BeastStore.get().review?.updatedAt) queueMicrotask(()=>BeastReviewEvidenceBridge.refreshReview({signal}).catch(()=>{}));
    return {node:root,dispose(){disposed=true;unsubscribe();}};
  }

  window.BeastReviewPage={renderer};
})();
