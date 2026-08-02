// BEAST Pair Programmer renderer module: sourceplan-handoff.js
(() => {
  const registry = window.BeastAICodingModules = window.BeastAICodingModules || {};
  registry.createSourceplanHandoff = runtime => {
  const api = runtime.api;
  const root = runtime.root;
  const gatewayUrl = runtime.gatewayUrl;
  const stateKey = runtime.stateKey;
  const now = runtime.now;
  const openRunStream = runtime.openRunStream;
  const parseActionIntent = runtime.parseActionIntent;
  const looksLikeActionIntent = runtime.looksLikeActionIntent;
  const MAX_CONTEXT_FILES = runtime.constants.MAX_CONTEXT_FILES;
  const RELIABLE_LOCAL_CODER = runtime.constants.RELIABLE_LOCAL_CODER;
  const RELIABLE_LOCAL_PROFILE = runtime.constants.RELIABLE_LOCAL_PROFILE;
  const appendTrace = (...args) => api.appendTrace(...args);
  const patch = (...args) => api.patch(...args);
  const persist = (...args) => api.persist(...args);
  const proposalFromActions = (...args) => api.proposalFromActions(...args);

  function noteSourcePlanApply(event) {
    const plan = event?.detail?.plan || {};
    const result = event?.detail?.result || {};
    if (!plan.agent_session_id || plan.agent_session_id !== BeastStore.get().aiCoding.sessionId) return;
    const applied = Array.isArray(result.applied) ? result.applied : [];
    const verified = result.verification?.ok === true ? 'verification passed' : 'apply receipt recorded';
    appendTrace('apply', `Governed SourcePlan applied · ${applied.length || plan.operations?.length || 0} file(s) · ${verified}`);
    const status = result.workspace_feedback?.git?.status;
    if (Array.isArray(status) && status.length) appendTrace('workspace', `Post-apply Git status: ${status.slice(0,4).join(' · ')}`);
    const tests = result.workspace_feedback?.test_candidates;
    if (Array.isArray(tests) && tests.length) appendTrace('tests', `Focused test candidate(s): ${tests.slice(0,4).join(', ')} · approve the isolated verifier to run them`);
    patch({ status:'follow-up-ready' });
    persist();
  }

  function stageSourcePlan(plan) {
    if (!plan || !Array.isArray(plan.operations) || !plan.operations.length) return null;
    const normalized = structuredClone(plan);
    normalized.operations = normalized.operations.map((operation, index) => ({
      ...operation,
      op: operation.op || operation.type || 'replace_exact',
      old: operation.old ?? operation.old_text ?? operation.before ?? '',
      new: operation.new ?? operation.new_text ?? operation.after ?? operation.content ?? '',
      operation_id: operation.operation_id || operation.op_id || operation.id || `op-${index + 1}`
    }));
    normalized.selected_operations = normalized.operations.map(operation => operation.operation_id);
    const active = BeastEditorCortex.getActive() || { path:'', text:'' };
    let proposed = String(active.text || '');
    for (const operation of normalized.operations.filter(item => item.path === active.path && item.op === 'replace_exact')) {
      if (operation.old && proposed.includes(operation.old)) proposed = proposed.replace(operation.old, operation.new || '');
    }
    const activeOperations = normalized.operations.filter(item => item.path === active.path);
    const previewText = active.path && activeOperations.length
      ? BeastDesktopBridge.localDiff(active.text, proposed)
      : normalized.operations.map(item => `${item.op} ${item.path}${item.description ? ` — ${item.description}` : ''}`).join('\n');
    BeastStore.patch('sourcePlan', {
      status:'draft', message:`AI SourcePlan ready: ${normalized.plan_id || 'draft'}`,
      plan:normalized, lifecycle:null, selectedOperationIds:normalized.selected_operations,
      previewText, originalText:active.text, proposedText:proposed,
      activeOperationId:normalized.selected_operations[0] || '', stale:false, error:'', updatedAt:now()
    });
    // Keep the Review Center bound to the same proposal even when it was
    // opened before this coding run.  Its bridge derives a usable review from
    // the SourcePlan if no remote review snapshot exists yet.
    Promise.resolve().then(() => window.BeastReviewEvidenceBridge?.refreshReview?.().catch?.(() => {}));
    patch({ sourcePlanReady:true, sourcePlanId:String(normalized.plan_id || '') });
    if (typeof document !== 'undefined' && typeof CustomEvent === 'function') document.dispatchEvent(new CustomEvent('beast:ai-proposal-ready', { detail:{ plan:normalized } }));
    persist();
    return proposalFromActions(normalized.operations, true, normalized.plan_id || '', normalized.validation || {}, normalized.intelligence || {}, normalized.non_mutating_requests || []);
  }

  async function openSourcePlan() {
    if (!BeastStore.get().aiCoding.sourcePlanReady) throw new Error('No AI SourcePlan is ready yet.');
    await BeastRouter.navigate('source');
  }

    return { noteSourcePlanApply, stageSourcePlan, openSourcePlan };
  };
})();
