(() => {
  function escapeHtml(value) { return String(value ?? '').replace(/[&<>"']/g, char => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' })[char]); }
  function operationsFrom(state) {
    const plan = state.sourcePlan.plan || {};
    const rows = Array.isArray(plan.operations) && plan.operations.length ? plan.operations : Array.isArray(state.sourcePlan.lifecycle?.operations) ? state.sourcePlan.lifecycle.operations : Array.isArray(plan.selected_operations) && typeof plan.selected_operations[0] === 'object' ? plan.selected_operations : [];
    return rows.map((op, index) => ({ ...op, id: op.operation_id || op.id || `op-${index + 1}`, selected: state.sourcePlan.selectedOperationIds.includes(op.operation_id || op.id || `op-${index + 1}`) }));
  }

  function template() {
    const root = document.createElement('div');
    root.className = 'beast-page beast-sourceplan-page';
    root.innerHTML = `
      <header class="beast-page-head">
        <div><h2>SourcePlan Forge</h2><div class="sub">DIFF → OPERATIONS → VERIFICATION → ROLLBACK → EVIDENCE CLOSURE</div></div>
        <div class="beast-page-actions"><button class="beast-button secondary" data-plan-action="clear">Clear</button><button class="beast-button secondary" data-plan-action="draft">Re-Draft</button><button class="beast-button" data-plan-action="lifecycle">Refresh Lifecycle</button><button class="beast-button amber" data-plan-action="verify">Verify</button><button class="beast-button hot" data-plan-action="apply">Apply</button><button class="beast-button danger-button" data-plan-action="rollback" title="Restore the latest captured SourcePlan rollback snapshot">Rollback Latest</button></div>
      </header>
      <section class="sourceplan-summary-grid">
        <article class="beast-card"><h3>Active Buffer</h3><strong class="metric small" data-plan-file>none</strong><p data-plan-buffer-state>No staged changes.</p></article>
        <article class="beast-card"><h3>Plan Identity</h3><strong class="metric small" data-plan-id>none</strong><p data-plan-status>No plan compiled.</p></article>
        <article class="beast-card"><h3>Operation Contract</h3><strong class="metric small" data-plan-ops>0 selected</strong><p data-plan-contract>Awaiting lifecycle.</p></article>
        <article class="beast-card"><h3>Apply Readiness</h3><div class="beast-ring small" data-plan-ring style="--value:0"><span data-plan-score>0%</span></div><p data-plan-ready>Not ready.</p></article>
      </section>
      <div class="sourceplan-main-grid">
        <section class="beast-card sourceplan-diff-panel wide">
          <header class="beast-panel-head"><div><h3>Governed Diff Preview</h3><span data-diff-label>No active diff</span></div><span class="beast-pill" data-diff-mode>LOCAL PREVIEW</span></header>
          <div class="sourceplan-diff-host" data-plan-diff-host></div>
          <pre class="sourceplan-diff-fallback" data-plan-diff-fallback>No diff preview.</pre>
        </section>
        <aside class="sourceplan-side-stack">
          <section class="beast-card sourceplan-operation-panel"><header class="beast-panel-head"><h3>Operations</h3><span data-operation-count>0</span></header><div class="sourceplan-operation-list" data-operation-list></div></section>
          <section class="beast-card sourceplan-lifecycle-panel"><header class="beast-panel-head"><h3>Lifecycle Checks</h3><span data-lifecycle-state>idle</span></header><div class="sourceplan-check-list" data-lifecycle-list></div></section>
        </aside>
      </div>
      <section class="beast-card sourceplan-ledger wide">
        <header class="beast-panel-head"><h3>Action Contract & Apply Timeline</h3><span data-plan-updated>never</span></header>
        <div class="sourceplan-contract-grid"><div data-contract-list></div><div data-apply-list></div></div>
      </section>`;
    return root;
  }

  async function renderer() {
    const root = template();
    let disposed = false;
    let disposeDiff = () => {};
    let diffKey = '';

    async function refreshDiff(state) {
      const key = `${state.sourcePlan.originalText.length}:${state.sourcePlan.proposedText.length}:${state.sourcePlan.updatedAt}`;
      if (key === diffKey) return; diffKey = key;
      disposeDiff();
      root.querySelector('[data-plan-diff-fallback]').textContent = state.sourcePlan.previewText || 'No diff preview.';
      disposeDiff = await BeastEditorCortex.mountDiff(root.querySelector('[data-plan-diff-host]'), root.querySelector('[data-plan-diff-fallback]'));
    }

    function patch(state) {
      if (disposed) return;
      const planState = state.sourcePlan;
      const active = state.editor.activePath;
      const plan = planState.plan || {};
      const lifecycle = planState.lifecycle || {};
      const validation = plan.validation && typeof plan.validation === 'object' ? plan.validation : {};
      const operations = operationsFrom(state);
      root.querySelector('[data-plan-file]').textContent = active ? active.split('/').pop() : 'none';
      root.querySelector('[data-plan-buffer-state]').textContent = active ? (state.editor.dirtyPaths.includes(active) ? 'Staged buffer requires governed write.' : 'Active buffer is clean.') : 'Select a file in Editor Cortex.';
      root.querySelector('[data-plan-id]').textContent = plan.plan_id || 'none';
      root.querySelector('[data-plan-status]').textContent = planState.message || planState.status;
      root.querySelector('[data-plan-ops]').textContent = `${planState.selectedOperationIds.length} selected`;
      root.querySelector('[data-plan-contract]').textContent = validation.status ? `${validation.check_count || 0} proposal checks · ${validation.status}` : lifecycle.action_contract?.rollback_required === false ? 'Direct apply contract' : 'Approval + rollback + evidence';
      const score = Number(lifecycle.score ?? (lifecycle.can_apply ? 100 : plan ? 72 : 0));
      root.querySelector('[data-plan-ring]').style.setProperty('--value', Math.max(0, Math.min(100, score)));
      root.querySelector('[data-plan-score]').textContent = `${score}%`;
      root.querySelector('[data-plan-ready]').textContent = lifecycle.can_apply ? 'Ready for governed apply.' : validation.ok ? 'Proposal checks passed. Run governed verification.' : validation.status === 'failed' ? 'Proposal checks failed. Return to Pair Programmer.' : planState.status === 'local-preview' ? 'Preview only — gateway verification required.' : 'Verification incomplete.';
      root.querySelector('[data-diff-label]').textContent = active || 'No active file';
      root.querySelector('[data-diff-mode]').textContent = state.connection.status === 'online' && !state.connection.demoMode ? 'GATEWAY PLAN' : 'LOCAL PREVIEW';
      root.querySelector('[data-operation-count]').textContent = `${operations.length} operations`;
      const opHost = root.querySelector('[data-operation-list]');
      opHost.innerHTML = operations.length ? operations.map(op => `<button class="sourceplan-op ${op.selected ? 'selected' : ''} ${planState.activeOperationId === op.id ? 'active' : ''}" data-plan-op="${escapeHtml(op.id)}"><span>${op.selected ? '✓' : '○'}</span><div><b>${escapeHtml(op.op || op.kind || 'operation')}</b><small>${escapeHtml(op.path || active || '')}</small><em>${escapeHtml(op.description || op.summary || op.risk || 'governed mutation')}</em></div></button>`).join('') : '<div class="cortex-empty-list">Draft a plan to inspect operations.</div>';
      const proposalChecks = Array.isArray(validation.checks) ? validation.checks.map(check => ({label:`${check.path || 'proposal'} · ${check.kind || 'check'}`,status:check.passed?'pass':'fail'})) : [];
      const checks = [...proposalChecks,...(lifecycle.checks || [])];
      root.querySelector('[data-lifecycle-state]').textContent = lifecycle.can_apply ? 'ready' : validation.status || planState.status;
      root.querySelector('[data-lifecycle-list]').innerHTML = checks.length ? checks.map(check => `<div class="sourceplan-check ${check.status === 'pass' ? 'pass' : check.status === 'fail' ? 'fail' : ''}"><span>${check.status === 'pass' ? '✓' : check.status === 'fail' ? '!' : '○'}</span><b>${escapeHtml(check.label || check.name || 'check')}</b><em>${escapeHtml(check.status || 'pending')}</em></div>`).join('') : '<div class="cortex-empty-list">Lifecycle has not been scored.</div>';
      const contract = lifecycle.action_contract || {};
      const contractRows = [
        ['Approval required', contract.requires_approval ?? true], ['Rollback required', contract.rollback_required ?? true],
        ['Evidence closure', contract.evidence_closure ?? true], ['Can verify', lifecycle.can_verify ?? false], ['Can apply', lifecycle.can_apply ?? false]
      ];
      root.querySelector('[data-contract-list]').innerHTML = `<h4>Contract</h4>${contractRows.map(([label, value]) => `<div class="contract-row"><span>${escapeHtml(label)}</span><b class="${value ? 'yes' : 'no'}">${value ? 'YES' : 'NO'}</b></div>`).join('')}`;
      const apply = planState.lastApply;
      root.querySelector('[data-apply-list]').innerHTML = `<h4>Apply Timeline</h4>${apply ? Object.entries(apply).slice(0, 8).map(([key, value]) => `<div class="contract-row"><span>${escapeHtml(key)}</span><b>${escapeHtml(Array.isArray(value) ? value.join(', ') : typeof value === 'object' ? JSON.stringify(value) : value)}</b></div>`).join('') : '<div class="cortex-empty-list">No apply receipt yet.</div>'}`;
      root.querySelector('[data-plan-updated]').textContent = planState.updatedAt ? new Date(planState.updatedAt).toLocaleTimeString() : 'never';
      root.querySelector('[data-plan-action="verify"]').disabled = !plan || planState.verifying;
      // Apply performs the authoritative verification again on the backend.
      // Keep it usable after a draft even when the optional lifecycle refresh
      // has not run yet; requiring lifecycle.can_apply here made the button
      // appear permanently dead after AI proposals.
      root.querySelector('[data-plan-action="apply"]').disabled = !plan || planState.applying || planState.status === 'local-preview' || planState.stale;
      root.querySelector('[data-plan-action="rollback"]').disabled = planState.applying || !planState.lastApply;
      root.querySelector('[data-plan-action="lifecycle"]').disabled = !plan;
      root.querySelector('[data-plan-action="clear"]').disabled = !plan;
      refreshDiff(state);
    }

    const unsubscribe = BeastStore.subscribe(patch);
    root.addEventListener('click', async event => {
      const op = event.target.closest('[data-plan-op]'); if (op) { BeastEditorCortex.toggleOperation(op.dataset.planOp); return; }
      const action = event.target.closest('[data-plan-action]')?.dataset.planAction; if (!action) return;
      try {
        if (action === 'clear') BeastEditorCortex.clearPlan();
        if (action === 'draft') await BeastEditorCortex.draftSourcePlan();
        if (action === 'lifecycle') await BeastEditorCortex.refreshLifecycle();
        if (action === 'verify') { await BeastEditorCortex.verifyPlan(); BeastFX.trigger('success', event.target, { size: 230 }); }
        if (action === 'apply') { await BeastEditorCortex.applyPlan(); BeastFX.trigger('success', event.target, { size: 320 }); BeastMascot.setState('finished'); setTimeout(() => BeastMascot.setState('idle'), 1600); }
        if (action === 'rollback') { await BeastEditorCortex.rollbackLatestPlan(); BeastFX.trigger('warning', event.target, { size: 280 }); BeastMascot.setState('working'); setTimeout(() => BeastMascot.setState('idle'), 1200); }
      } catch (error) { BeastStore.patch('sourcePlan', { status: 'error', message: String(error.message || error), error: String(error.message || error) }); BeastFX.trigger('warning', event.target, { size: 250 }); }
    });

    return { node: root, dispose() { disposed = true; unsubscribe(); disposeDiff(); } };
  }

  window.BeastSourcePlanPage = { renderer };
})();
