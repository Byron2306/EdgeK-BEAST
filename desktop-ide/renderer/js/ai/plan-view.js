// BEAST Pair Programmer renderer module: plan-view.js
(() => {
  const registry = window.BeastAICodingModules = window.BeastAICodingModules || {};
  registry.createPlanView = runtime => {
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
  function draftPreviewFromRaw(value) {
    const raw=String(value||'');const decode=value=>{try{return JSON.parse(`"${value}"`);}catch(_){return value.replaceAll('\\n',' ');}};
    const collect=key=>{const values=[];const pattern=new RegExp(`"${key}"\\s*:\\s*"((?:\\\\.|[^"\\\\])*)"`,'g');let match;while((match=pattern.exec(raw))&&values.length<8)values.push(decode(match[1]));return values;};
    const files=[...new Set(collect('path').filter(Boolean))];const intents=collect('intent').filter(Boolean);const actions=(raw.match(/"(?:type|op)"\s*:/g)||[]).length;
    return { chars:raw.length, files, intents, actions };
  }

  function structuredDraftStatus(draft = {}) {
    const actions = Number(draft.actions || 0);
    const files = Array.isArray(draft.files) ? draft.files : [];
    const latestIntent = Array.isArray(draft.intents) ? draft.intents.at(-1) : '';
    const summary = actions
      ? `Receiving a structured edit plan: ${actions} proposed edit${actions === 1 ? '' : 's'}${files.length ? ` across ${files.length} file${files.length === 1 ? '' : 's'}` : ''}.`
      : 'Receiving a structured edit plan from the model.';
    return [
      summary,
      latestIntent ? `Current intent: ${latestIntent}` : '',
      'BEAST is compiling this into a governed SourcePlan. No files can change until you review and approve the diff.'
    ].filter(Boolean).join('\n\n');
  }

  function runDoneSentence(status = '', { needsOperator = false, proposalReady = false, advisoryReceived = false, analysisRun = false } = {}) {
    const raw = String(status || '').replaceAll('_', ' ').trim();
    if (proposalReady) return 'Run complete: I prepared a governed SourcePlan for review.';
    if (needsOperator) return 'Recovery is waiting for your review. No files changed.';
    if (analysisRun || /chat complete|analysis/i.test(raw)) return 'Run complete: I finished the read-only analysis.';
    if (advisoryReceived) return 'Run complete: I returned a read-only answer and made no file changes.';
    if (/advisory response/i.test(raw)) return 'Run complete: no SourcePlan was created and no files changed.';
    return raw ? `Run complete: ${raw}.` : 'Run complete.';
  }

  function isStructuredEditStream(value) {
    const body = String(value || '').trim();
    return Boolean(body) && (
      looksLikeActionIntent(body)
      || /^[{\[]/.test(body)
      || body.includes('"actions"')
      || body.includes('"kind"')
      || body.includes('beast.action_intent')
    );
  }

  function proposalFromActions(actions = [], ready = false, planId = '', validation = {}, intelligence = {}, nonMutatingRequests = []) {
    const nonMutatingTypes = new Set(['run_verifier','ask_for_context']);
    const requests = [
      ...nonMutatingRequests,
      ...actions.filter(action => nonMutatingTypes.has(String(action?.type || action?.op || '')))
    ].slice(0, 20).map((action, index) => ({
      id:String(action.id || action.action_ir_id || `request-${index + 1}`),
      type:String(action.type || action.op || 'request'),
      path:String(action.path || action.target?.path || ''),
      intent:String(action.intent || action.description || 'Non-mutating agent request'),
      command:String(action.parameters?.command || action.command || ''),
      query:String(action.parameters?.query || action.query || '')
    }));
    const operations = actions.filter(action => !nonMutatingTypes.has(String(action?.type || action?.op || ''))).slice(0, 50).map((action, index) => ({
      id:String(action.operation_id || action.op_id || action.id || `op-${index + 1}`),
      op:String(action.op || action.type || 'edit'),
      path:String(action.path || action.target?.path || ''),
      intent:String(action.description || action.intent || 'Proposed code change'),
      old:String(action.old ?? action.before ?? '').slice(0, 2400),
      new:String(action.new ?? action.after ?? action.content ?? '').slice(0, 2400)
    })).filter(item => item.path);
    return {
      ready:Boolean(ready), planId:String(planId || ''), operations,
      validation:validation && typeof validation === 'object' ? validation : {},
      intelligence:intelligence && typeof intelligence === 'object' ? intelligence : {},
      requests,
      files:[...new Set(operations.map(item => item.path))]
    };
  }

  function proposalSummary(proposal, objective = '') {
    const operationCount = proposal.operations.length;
    const fileCount = proposal.files.length;
    const headline = operationCount
      ? `I prepared ${operationCount} reviewable change${operationCount === 1 ? '' : 's'} across ${fileCount} file${fileCount === 1 ? '' : 's'}.`
      : 'I finished investigating, but no safe file change was produced.';
    const details = proposal.operations.slice(0, 5).map(item => `- \`${item.path}\` — ${item.intent}`).join('\n');
    const validation = proposal.validation?.status
      ? `Validation: ${proposal.validation.status}${proposal.validation.check_count ? ` · ${proposal.validation.check_count} checks` : ''}.`
      : '';
    const requests = proposal.requests?.length
      ? `Agent requested ${proposal.requests.length} non-mutating follow-up${proposal.requests.length === 1 ? '' : 's'}: ${proposal.requests.slice(0, 3).map(item => item.command || item.query || item.type).join(', ')}.`
      : '';
    const next = proposal.ready
      ? 'The files have not been written yet. Review the diff, then apply the governed SourcePlan when it looks right.'
      : 'The response could not be compiled into a safe patch. Refine the request or attach the exact file and selection, then retry.';
    return [headline, objective ? String(objective).trim() : '', details, validation, requests, next].filter(Boolean).join('\n\n');
  }

  function normalizedRestoredMessage(message, sourcePlanReady, sourcePlanId) {
    const next = { ...message, streaming:false };
    const intent = message?.role === 'assistant' ? parseActionIntent(message.content) : null;
    if (!intent && message?.role === 'assistant' && isStructuredEditStream(message.content)) {
      const draft = draftPreviewFromRaw(message.content);
      return { ...next, content:structuredDraftStatus(draft), draftPreview:draft, internalFormat:'beast.action_intent.v1' };
    }
    if (!intent) return next;
    const proposal = proposalFromActions(intent.actions || [], sourcePlanReady, sourcePlanId);
    return { ...next, content:proposalSummary(proposal, intent.objective), proposal, internalFormat:'beast.action_intent.v1' };
  }

    return { draftPreviewFromRaw, structuredDraftStatus, runDoneSentence, isStructuredEditStream, proposalFromActions, proposalSummary, normalizedRestoredMessage };
  };
})();
