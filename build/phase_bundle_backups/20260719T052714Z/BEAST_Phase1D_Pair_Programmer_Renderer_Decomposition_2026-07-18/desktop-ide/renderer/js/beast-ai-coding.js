// Keep the budget at module scope as well as in the Pair Programmer closure.
// This protects the normalizer when the file is evaluated by lightweight
// harnesses that extract individual helpers for testing.
const MAX_CONTEXT_FILES = 48;
const RELIABLE_LOCAL_CODER = 'qwen2.5-coder:1.5b';
const RELIABLE_LOCAL_PROFILE = Object.freeze({ maxFiles:3, contextChars:2400, askTokens:768, editTokens:1024 });

(() => {
  let stream = null;
  let streamWatchdog = null;
  let streamLastEventAt = 0;
  const root = () => BeastStore.get().workspace.root || '';
  const gatewayUrl = () => BeastRuntime.gatewayUrl || BeastStore.get().connection.gatewayUrl || 'http://127.0.0.1:8101';
  const stateKey = () => `beast.v2.ai-coding:${root() || 'workspace'}`;
  const now = () => Date.now();
  const { openRunStream } = window.BeastAITransport;
  const { parseActionIntent, looksLikeActionIntent } = window.BeastAIIntent;
  const { runDoneSentence, narrationFromTurn } = window.BeastAINarration;
  const { isAgentAnalysisPrompt, agentTurnProfile, initialAgentTurns, initialAgentProgress } = window.BeastAIProfile;

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

  function patch(values) { BeastStore.patch('aiCoding', { ...values, updatedAt: now() }); }

  function persist() {
    const state = BeastStore.get().aiCoding;
    const payload = {
      open: state.open,
      expanded: state.expanded,
      mode: state.mode,
      sessionId: state.sessionId,
      messages: state.messages.slice(-40),
      trace: state.trace.slice(-80),
      contextFiles: state.contextFiles.slice(0, 16),
      contextSuggestions: state.contextSuggestions.slice(0, 12),
      contextPolicy: 'explicit-only-v2',
      provider: state.provider,
      model: state.model,
      crystal: state.crystal,
      compute: state.compute,
      sourcePlanReady: state.sourcePlanReady,
      sourcePlanId: state.sourcePlanId
    };
    try { localStorage.setItem(stateKey(), JSON.stringify(payload)); } catch (_) {}
  }

  function restore() {
    if (BeastStore.get().aiCoding.streaming) return;
    let payload = {};
    try { payload = JSON.parse(localStorage.getItem(stateKey()) || '{}'); } catch (_) {}
    const storedMessages = Array.isArray(payload.messages) ? payload.messages.slice(-40) : [];
    const interrupted = storedMessages.some(message => message?.streaming);
    // Older sessions persisted Code Cortex discoveries as though the operator
    // had attached them. Clear that expanded set once; thereafter every file
    // in contextFiles is an explicit attachment.
    const activePath = String(BeastStore.get().editor.activePath || '');
    const restoredContext = Array.isArray(payload.contextFiles) ? payload.contextFiles.slice(0,16) : [];
    const contextFiles = payload.contextPolicy === 'explicit-only-v2'
      ? restoredContext
      : (activePath ? restoredContext.filter(path => path === activePath) : []);
    patch({
      open: Boolean(payload.open),
      expanded: Boolean(payload.expanded),
      mode: ['ask','edit','agent'].includes(payload.mode) ? payload.mode : 'agent',
      sessionId: String(payload.sessionId || ''),
      messages: storedMessages.map(message => normalizedRestoredMessage(message, Boolean(payload.sourcePlanReady), String(payload.sourcePlanId || ''))),
      trace: Array.isArray(payload.trace) ? payload.trace.slice(-80) : [],
      contextFiles,
      contextSuggestions: Array.isArray(payload.contextSuggestions) ? payload.contextSuggestions.slice(0,12) : [],
      contextSuggestionStatus: 'idle',
      provider: String(payload.provider || BeastStore.get().models.provider || localStorage.getItem('beast.provider') || ''),
      model: String(payload.model || BeastStore.get().models.selectedId || BeastStore.get().models.active || localStorage.getItem('beast.model') || ''),
      crystal: payload.crystal && typeof payload.crystal === 'object' ? payload.crystal : BeastStore.get().aiCoding.crystal,
      compute: payload.compute && typeof payload.compute === 'object' ? payload.compute : BeastStore.get().aiCoding.compute,
      sourcePlanReady: Boolean(payload.sourcePlanReady),
      sourcePlanId: String(payload.sourcePlanId || ''),
      streaming: false,
      status: interrupted ? 'interrupted' : payload.sessionId ? 'ready' : 'idle',
      error: interrupted ? 'The previous run was interrupted. Your conversation was kept; send again to retry.' : ''
    });
    if (payload.contextPolicy !== 'explicit-only-v2' && restoredContext.length > contextFiles.length) {
      appendTrace('context', 'Previous auto-expanded context was cleared. Attach additional files explicitly when you want them in scope.');
    }
  }

  function setOpen(open = true) { patch({ open: Boolean(open) }); persist(); }
  function setExpanded(expanded = true) { patch({ expanded:Boolean(expanded) }); persist(); }

  function setMode(mode) {
    const next = ['ask','edit','agent'].includes(mode) ? mode : 'agent';
    const current = BeastStore.get().aiCoding;
    if (next === current.mode) return;
    cancel();
    patch({ mode:next, sessionId:'', status:'idle', error:'', sourcePlanReady:false, sourcePlanId:'', selection:null });
    persist();
  }

  function setPrompt(prompt) { patch({ prompt:String(prompt || '') }); }

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

  async function runInWorktree(prompt, options = {}) {
    const objective = String(prompt || BeastStore.get().aiCoding.prompt || '').trim();
    if (!objective) throw new Error('Describe the coding task before creating an isolated mission.');
    if (BeastStore.get().connection.status !== 'online' || BeastDesktopBridge.demoMode) throw new Error('An isolated agent mission requires a live BEAST gateway.');
    if (BeastStore.get().aiCoding.streaming) throw new Error('Wait for the current AI turn to finish before isolating a new mission.');
    const sourceRoot = root();
    if (!sourceRoot) throw new Error('Choose a workspace before creating an isolated agent mission.');
    const files = contextFilesFor(objective);
    patch({ status:'creating-worktree', error:'' });
    appendTrace('worktree', 'Creating isolated mission workspace…');
    const mission = await BeastRuntime.request('/edgek/ide/worktree-mission/create', {
      method:'POST', timeoutMs:60000,
      body:{ root_path:sourceRoot, objective, mode:'editor_agent', risk:'high', provider:BeastStore.get().aiCoding.provider || localStorage.getItem('beast.provider') || '', files }
    });
    const task = mission?.task || {};
    const worktreeRoot = String(task.worktree_path || '');
    if (!mission?.ok || !worktreeRoot) throw new Error(mission?.error || 'BEAST could not create the isolated worktree mission.');
    BeastDesktopBridge.setRoot(worktreeRoot, { preserveWorktreeRegistry:true });
    await BeastDesktopBridge.listFiles({ limit:2000 });
    patch({ open:true, mode:'agent', prompt:objective, contextFiles:files.filter(path => BeastStore.get().workspace.files.some(row => row.path === path)), status:'isolated-ready', error:'' });
    appendTrace('worktree', `Isolated mission ready: ${task.branch || task.task_id || worktreeRoot}`);
    BeastStore.patch('worktrees', { registryRoot:sourceRoot, selectedId:String(task.task_id || ''), updatedAt:now() });
    await send(objective, { ...options, isolatedMission:task.task_id || '' });
    return { ok:true, task };
  }

  async function retryLastRequest(options = {}) {
    if (BeastStore.get().aiCoding.streaming) throw new Error('The current AI turn is still running.');
    const previous = [...(BeastStore.get().aiCoding.messages || [])]
      .reverse()
      .find(message => message?.role === 'user' && String(message.content || '').trim());
    if (!previous) throw new Error('There is no prior coding request to retry.');
    const local=/^(?:ollama|local_ollama)$/i.test(String(BeastStore.get().aiCoding.provider||localStorage.getItem('beast.provider')||''))&&String(BeastStore.get().aiCoding.model||localStorage.getItem('beast.model')||'')===RELIABLE_LOCAL_CODER;
    const focused=options.focused===undefined?local:Boolean(options.focused);
    appendTrace('retry', focused?'Retrying with a focused one-file recovery profile.':'Retrying the last request with the retained locked context.');
    return send(String(previous.content), {...options,focused,maxTokens:options.maxTokens||(focused?768:undefined),contextMaxCharsEach:options.contextMaxCharsEach||(focused?1800:undefined)});
  }

  async function recoverInvalidPacket(options = {}) {
    if (BeastStore.get().aiCoding.streaming) throw new Error('The current AI turn is still running.');
    const state = BeastStore.get();
    const files = state.aiCoding.contextFiles || [];
    appendTrace('recovery', `Repairing invalid Action IR with ${files.length} retained context file(s).`);
    return retryLastRequest({
      ...options,
      focused:false,
      preserveContext:true,
      actionIrRecovery:true,
      maxTokens:options.maxTokens || 4096,
      contextMaxCharsEach:options.contextMaxCharsEach || 12000
    });
  }

  async function continueWithAddedContext(options = {}) {
    if (BeastStore.get().aiCoding.streaming) throw new Error('The current AI turn is still running.');
    const state = BeastStore.get();
    const contextFiles = state.aiCoding.contextFiles || [];
    if (!contextFiles.length) throw new Error('Add at least one context file before continuing this agent loop.');
    appendProposalTurns(String(state.sourcePlan?.plan?.plan_id || state.aiCoding.sourcePlanId || ''), {
      kind:'context',
      type:'context_continue',
      role:'agent',
      text:`Continuing with ${contextFiles.length} context file${contextFiles.length === 1 ? '' : 's'}.`,
      state:'active',
      tool:'Pair Programmer loop controller',
      authority:'operator selected context'
    }, { activity:'Continuing with added context' });
    appendTrace('context', `Continuing the last request with ${contextFiles.length} retained context file(s).`);
    return retryLastRequest({
      ...options,
      focused:false,
      contextMaxCharsEach:options.contextMaxCharsEach || 50000
    });
  }

  function syncModel(modelId = '') {
    const app = BeastStore.get();
    const selected = app.models.registry.find(row => row.id === modelId)
      || app.models.registry.find(row => row.id === app.models.selectedId)
      || app.models.registry[0] || {};
    let model = String(selected.id || modelId || app.models.selectedId || app.models.active || localStorage.getItem('beast.model') || '');
    let provider = String(selected.provider || app.models.provider || localStorage.getItem('beast.provider') || '');
    // Migrate the pair programmer once to the installed, CPU-safe coder
    // model. Later explicit model selections remain respected.
    const isLocalOllama = /^(?:ollama|local_ollama)$/i.test(provider);
    const preferred = app.models.registry.find(row => row.id === RELIABLE_LOCAL_CODER && /^(?:ollama|local_ollama)$/i.test(String(row.provider || '')));
    if (isLocalOllama && preferred && localStorage.getItem('beast.pair-programmer.local-model-migrated') !== '1') {
      model = RELIABLE_LOCAL_CODER;
      provider = String(preferred.provider || provider);
      localStorage.setItem('beast.pair-programmer.local-model-migrated', '1');
      appendTrace('routing', `Reliable local coding profile selected: ${RELIABLE_LOCAL_CODER} · 8K context · 4K output`);
    }
    if (model) localStorage.setItem('beast.model', model);
    if (provider) localStorage.setItem('beast.provider', provider);
    patch({ model, provider });
    persist();
    return { model, provider };
  }

  function providerStateRoute(state = {}, modelHint = '') {
    const providers = state && typeof state === 'object' && state.providers && typeof state.providers === 'object' ? state.providers : {};
    const credentials = state && typeof state === 'object' && state.credentials && typeof state.credentials === 'object' ? state.credentials : {};
    const route = state && typeof state === 'object' && (state.route || state.active_route || state.routing) || {};
    const rows = Object.entries(providers).map(([id, provider]) => ({ id, ...(provider && typeof provider === 'object' ? provider : {}) }));
    const credentialReady = row => {
      if (/^(?:ollama|local_ollama|llama_cpp|vllm|tgi|sglang|tensorrt_llm)$/i.test(row.id)) return true;
      if (typeof row.credential_ready === 'boolean') return row.credential_ready;
      if (Object.prototype.hasOwnProperty.call(credentials, row.id)) return Boolean(credentials[row.id]);
      return true;
    };
    const usable = row => row && row.enabled !== false && (row.default_model || row.model || row.models?.[0]) && credentialReady(row);
    const hinted = String(modelHint || route.model || state.active_model || state.selected_model || '').trim();
    const selected = rows.find(row => usable(row) && (row.default_model === hinted || row.model === hinted || (Array.isArray(row.models) && row.models.includes(hinted))))
      || rows.find(row => row.id === 'nvidia_nim' && usable(row))
      || rows.find(usable);
    if (!selected) return { model:'', provider:'' };
    return {
      provider:String(selected.provider_id || selected.provider || selected.id || ''),
      model:String(hinted && (selected.default_model === hinted || selected.model === hinted || (Array.isArray(selected.models) && selected.models.includes(hinted))) ? hinted : (selected.default_model || selected.model || selected.models?.[0] || ''))
    };
  }

  async function resolveCodingRoute(modelId = '') {
    let route = syncModel(modelId);
    if (route.model && route.provider) return route;
    appendTrace('routing', 'Model registry was not ready; refreshing live providers before starting the Pair Programmer.');
    try {
      if (window.BeastModelAgentBridge?.refreshModels) {
        await window.BeastModelAgentBridge.refreshModels({ timeoutMs:8000, cacheTtl:0 });
        route = syncModel(modelId || BeastStore.get().aiCoding.model);
        if (route.model && route.provider) return route;
      }
    } catch (error) {
      appendTrace('routing', `Live model refresh did not complete: ${String(error.message || error)}`);
    }
    try {
      const state = await BeastRuntime.request('/edgek/providers/state', { timeoutMs:6000, cacheTtl:0 });
      route = providerStateRoute(state, modelId || BeastStore.get().aiCoding.model);
      if (route.model && route.provider) {
        localStorage.setItem('beast.model', route.model);
        localStorage.setItem('beast.provider', route.provider);
        patch({ model:route.model, provider:route.provider });
        appendTrace('routing', `Recovered live provider route: ${route.provider}/${route.model}`);
        persist();
        return route;
      }
    } catch (error) {
      appendTrace('routing', `Provider state fallback unavailable: ${String(error.message || error)}`);
    }
    return route;
  }

  function toggleContext(path) {
    const clean = String(path || '').trim();
    if (!clean) return;
    const context = new Set(BeastStore.get().aiCoding.contextFiles || []);
    context.has(clean) ? context.delete(clean) : context.add(clean);
    patch({ contextFiles:[...context].slice(0,16) });
    persist();
  }

  function addActiveFile() {
    const path = BeastStore.get().editor.activePath;
    if (path && !BeastStore.get().aiCoding.contextFiles.includes(path)) toggleContext(path);
  }

  function captureSelection() {
    const selection = BeastEditorCortex.getSelection();
    if (!selection.path || !selection.text) {
      patch({ error:'Select code in the active editor before attaching a selection.' });
      return null;
    }
    patch({ selection:{ ...selection, text:String(selection.text).slice(0,6000) }, error:'' });
    if (!BeastStore.get().aiCoding.contextFiles.includes(selection.path)) toggleContext(selection.path);
    persist();
    return selection;
  }

  function removeSelection() { patch({ selection:null }); persist(); }

  function appendTrace(kind, text) {
    const clean = String(text || '').trim();
    if (!clean) return;
    const trace = [...BeastStore.get().aiCoding.trace, { id:`trace-${now()}-${Math.random()}`, kind, text:clean, at:now() }].slice(-80);
    patch({ trace });
  }

  function addMessage(role, content, extra = {}) {
    const message = { id:`msg-${now()}-${Math.random()}`, role, content:String(content || ''), at:now(), ...extra };
    patch({ messages:[...BeastStore.get().aiCoding.messages, message].slice(-40) });
    persist();
    return message.id;
  }

  function appendAssistant(messageId, chunk) {
    if (!chunk) return;
    const messages = BeastStore.get().aiCoding.messages.map(message => message.id === messageId
      ? { ...message, content:`${message.content || ''}${chunk}`.slice(-60000) }
      : message);
    patch({ messages });
  }

  function appendTurn(messageId, kind, text = '', state = 'active') {
    const payload = kind && typeof kind === 'object' ? kind : { kind, text, state };
    const clean = String(payload.text || payload.detail || payload.command || '').trim();
    if (!clean) return;
    const type = String(payload.type || payload.kind || 'event');
    const label = String(payload.label || payload.kind || type || 'event');
    const narration = narrationFromTurn({ ...payload, type, state:payload.state || payload.status || state });
    const messages = BeastStore.get().aiCoding.messages.map(message => {
      if (message.id !== messageId) return message;
      const turns = Array.isArray(message.turns) ? message.turns : [];
      const narrationRows = narration ? [...(Array.isArray(message.narration) ? message.narration : []), narration].filter((row,index,rows)=>row&&rows.indexOf(row)===index).slice(-5) : (Array.isArray(message.narration) ? message.narration : []);
      const shouldNarrate = message.role === 'assistant' && message.mode !== 'ask' && message.streaming && !message.proposal;
      return {
        ...message,
        narration:narrationRows,
        narrating:shouldNarrate || Boolean(message.narrating),
        content:message.content,
        turns:[...turns, {
          id:`turn-${now()}-${Math.random()}`,
          kind:label,
          type,
          role:String(payload.role || (type.startsWith('tool') ? 'tool' : type.startsWith('command') ? 'command' : 'agent')),
          text:clean.slice(0,500),
          state:String(payload.state || payload.status || state || 'active'),
          command:String(payload.command || ''),
          tool:String(payload.tool || ''),
          authority:String(payload.authority || ''),
          evidence:String(payload.evidence || ''),
          at:now()
        }].slice(-80)
      };
    });
    patch({ messages });
  }

  function updateAssistant(messageId, values = {}) {
    const messages = BeastStore.get().aiCoding.messages.map(message => message.id === messageId ? { ...message, ...values } : message);
    patch({ messages });
    persist();
  }

  function updateAssistantPreview(messageId, draftPreview) {
    const messages=BeastStore.get().aiCoding.messages.map(message=>message.id===messageId?{...message,draftPreview}:message);
    patch({messages});
  }

  function updateProgress(messageId, phase, label, detail = '', state = 'active') {
    const messages = BeastStore.get().aiCoding.messages.map(message => {
      if (message.id !== messageId) return message;
      const prior = Array.isArray(message.progress) ? message.progress : [];
      const progress = prior.map(item => item.state === 'active' && item.phase !== phase ? { ...item, state:'done' } : item);
      const index = progress.findIndex(item => item.phase === phase);
      const entry = { phase:String(phase), label:String(label), detail:String(detail || ''), state, at:now() };
      if (index >= 0) progress[index] = { ...progress[index], ...entry };
      else progress.push(entry);
      return { ...message, progress:progress.slice(-8), activity:String(label || message.activity || 'Working…') };
    });
    patch({ messages });
  }

  function finishProgress(messageId, detail = '') {
    const messages = BeastStore.get().aiCoding.messages.map(message => message.id === messageId
      ? { ...message, progress:(message.progress || []).map(item => item.state === 'active' ? { ...item, state:'done', detail:detail || item.detail } : item) }
      : message);
    patch({ messages });
  }

  function clearWatchdog() { if (streamWatchdog) clearTimeout(streamWatchdog); streamWatchdog = null; streamLastEventAt = 0; }
  function armWatchdog(assistantId, eventSource) {
    clearWatchdog();
    streamLastEventAt = now();
    const watch = () => {
      if (stream !== eventSource || !BeastStore.get().aiCoding.streaming) return;
      const silentFor = now() - streamLastEventAt;
      if (silentFor >= 300000) {
        fail('The coding run stopped producing events for five minutes. Retry the request or choose another model.', assistantId, eventSource);
        return;
      }
      updateProgress(assistantId, 'waiting', 'Still working', `No provider event for ${Math.max(1, Math.round(silentFor / 1000))} seconds · keeping the governed run active`, 'active');
      appendTrace('waiting', `Provider/verification work continues (${Math.max(1, Math.round(silentFor / 1000))}s without an event)`);
      streamWatchdog = setTimeout(watch, 15000);
    };
    streamWatchdog = setTimeout(watch, 15000);
  }

  function mentionedFiles(prompt) {
    const text = String(prompt || '');
    return BeastStore.get().workspace.files
      .map(row => row.path)
      .filter(path => text.includes(`@${path}`))
      .slice(0,16);
  }

  function normalizeContextFiles(files = []) {
    const contextLimit = typeof MAX_CONTEXT_FILES === 'number' ? MAX_CONTEXT_FILES : 48;
    const known = new Set((BeastStore.get().workspace.files || []).map(row => row.path));
    const rows = [];
    const dropped = [];
    for (const value of files) {
      const file=String(value || '').trim();
      if (!file) continue;
      if (file.startsWith('beast-remote://') || known.has(file) || /^@[^/]+\/.+/.test(file)) rows.push(file);
      else dropped.push(file);
    }
    const unique=[...new Set(rows)].slice(0,contextLimit);
    if (dropped.length) appendTrace('context', `Ignored unknown attachment(s): ${dropped.slice(0,8).join(', ')}`);
    if (rows.length > unique.length) appendTrace('context', `Context capped at ${contextLimit} file(s); refine the prompt or attach a selection for the rest.`);
    return unique;
  }

  function contextFilesFor(prompt) {
    const active = BeastStore.get().editor.activePath;
    return normalizeContextFiles([active, ...BeastStore.get().aiCoding.contextFiles, ...mentionedFiles(prompt)].filter(Boolean));
  }

  async function suggestContext(prompt = '') {
    const objective = String(prompt || BeastStore.get().aiCoding.prompt || '').trim();
    if (!objective) throw new Error('Describe the task first so BEAST can suggest relevant context.');
    if (BeastStore.get().connection.status !== 'online' || BeastDesktopBridge.demoMode) throw new Error('Context suggestions require a live BEAST gateway.');
    const selectedFiles = contextFilesFor(objective);
    patch({ contextSuggestionStatus:'loading', error:'' });
    try {
      const payload = await BeastRuntime.request('/edgek/workspace/context-header', {
        method:'POST', timeoutMs:15000,
        body:{ root_path:root(), objective, selected_files:selectedFiles, limit:8, token_budget:5000 }
      });
      const known = new Set((BeastStore.get().workspace.files || []).map(row => row.path));
      const suggestions = (Array.isArray(payload?.suggestions) ? payload.suggestions : [])
        .filter(item => item && known.has(String(item.path || '')) && !selectedFiles.includes(String(item.path || '')))
        .map(item => ({ path:String(item.path), reason:String(item.reason || 'retrieval match'), line:item.line || null, endLine:item.end_line || null, backends:Array.isArray(item.projection_backends) ? item.projection_backends : [] }))
        .slice(0,8);
      patch({ contextSuggestions:suggestions, contextSuggestionStatus:'ready' });
      appendTrace('context', suggestions.length ? `${suggestions.length} context suggestion(s) ready for your approval.` : 'No additional context suggestions were found.');
      persist();
      return suggestions;
    } catch (error) {
      patch({ contextSuggestionStatus:'error' });
      throw error;
    }
  }

  function acceptSuggestedContext(path) {
    const target = String(path || '');
    if (!target) return;
    const state = BeastStore.get();
    const existing = state.aiCoding.contextFiles || [];
    if (!existing.includes(target)) toggleContext(target);
    patch({ contextSuggestions:(BeastStore.get().aiCoding.contextSuggestions || []).filter(item => item.path !== target) });
    appendTrace('context', `Accepted suggested context: ${target}`);
    appendProposalTurns(String(state.sourcePlan?.plan?.plan_id || state.aiCoding.sourcePlanId || ''), {
      kind:'context',
      type:'context_attach',
      role:'operator',
      text:target,
      state:'done',
      tool:'Workspace context manager',
      authority:'operator accepted suggestion'
    }, { activity:'Context added for next run' });
    persist();
  }

  function agentContextRequests(plan) {
    const requests = Array.isArray(plan?.non_mutating_requests) ? plan.non_mutating_requests : [];
    const actions = Array.isArray(plan?.action_ir?.actions) ? plan.action_ir.actions : [];
    return [...requests, ...actions].filter(item => item && String(item.type || item.op || '') === 'ask_for_context');
  }

  function appendProposalTurns(planId = '', turnsToAdd = [], values = {}) {
    const additions = Array.isArray(turnsToAdd) ? turnsToAdd : [turnsToAdd];
    const messages = BeastStore.get().aiCoding.messages;
    const latestProposal = [...messages].reverse().find(item => item.role === 'assistant' && item.proposal);
    const patched = messages.map(message => {
      if (message.role !== 'assistant' || !message.proposal) return message;
      const samePlan = planId && String(message.proposal.planId || '') === String(planId);
      if (!samePlan && message !== latestProposal) return message;
      const turns = Array.isArray(message.turns) ? message.turns : [];
      const normalized = additions.map(item => ({
        id:`turn-${now()}-${Math.random()}`,
        kind:String(item.kind || item.type || 'agent'),
        type:String(item.type || item.kind || 'agent_turn'),
        role:String(item.role || 'agent'),
        text:String(item.text || '').slice(0,500),
        state:String(item.state || 'active'),
        command:String(item.command || ''),
        tool:String(item.tool || ''),
        authority:String(item.authority || ''),
        evidence:String(item.evidence || ''),
        at:now()
      }));
      return { ...message, ...values, turns:[...turns, ...normalized].slice(-80) };
    });
    patch({ messages:patched });
  }

  async function resolveRequestedContext() {
    const state = BeastStore.get();
    const plan = state.sourcePlan?.plan || {};
    const requests = agentContextRequests(plan);
    if (!requests.length) throw new Error('No agent context request is available.');
    if (state.connection.status !== 'online' || BeastDesktopBridge.demoMode) throw new Error('Context resolution requires a live BEAST gateway.');
    const selectedFiles = contextFilesFor(state.aiCoding.prompt || plan.objective || '');
    const known = new Set((state.workspace.files || []).map(row => row.path));
    const direct = [];
    const queryParts = [];
    for (const item of requests) {
      const parameters = item.parameters && typeof item.parameters === 'object' ? item.parameters : {};
      const candidates = [item.path, item.target?.path, parameters.path, ...(Array.isArray(parameters.paths) ? parameters.paths : [])].filter(Boolean).map(String);
      for (const path of candidates) {
        if (known.has(path) && !selectedFiles.includes(path)) direct.push({ path, reason:String(item.intent || 'agent requested context'), line:null, endLine:null, backends:['agent_request'] });
      }
      const query = String(parameters.query || item.query || item.intent || '').trim();
      if (query) queryParts.push(query);
    }
    patch({ contextSuggestionStatus:'loading', error:'' });
    const planId = String(plan.plan_id || state.aiCoding.sourcePlanId || '');
    appendProposalTurns(planId, {
      kind:'context',
      type:'context_search',
      role:'agent',
      text:queryParts.length ? queryParts.join(' · ').slice(0,300) : 'specific files requested by the model',
      state:'active',
      tool:'BEAST context header retrieval',
      authority:'metadata-first search; review before attaching'
    }, { activity:'Finding requested context' });
    try {
      let retrieved = [];
      if (queryParts.length) {
        const payload = await BeastRuntime.request('/edgek/workspace/context-header', {
          method:'POST', timeoutMs:15000,
          body:{ root_path:root(), objective:`${plan.objective || state.aiCoding.prompt || 'Resolve agent context request'}\n\nAgent requested context:\n${queryParts.join('\n')}`, selected_files:selectedFiles, limit:8, token_budget:5000 }
        });
        retrieved = (Array.isArray(payload?.suggestions) ? payload.suggestions : [])
          .filter(item => item && known.has(String(item.path || '')) && !selectedFiles.includes(String(item.path || '')))
          .map(item => ({ path:String(item.path), reason:String(item.reason || 'agent context request'), line:item.line || null, endLine:item.end_line || null, backends:Array.isArray(item.projection_backends) ? item.projection_backends : [] }));
      }
      const merged = [...direct, ...retrieved, ...(state.aiCoding.contextSuggestions || [])].filter((item, index, rows) => item?.path && rows.findIndex(row => row.path === item.path) === index).slice(0,8);
      patch({ contextSuggestions:merged, contextSuggestionStatus:'ready' });
      appendTrace('context', merged.length ? `${merged.length} agent-requested context suggestion(s) ready for your approval.` : 'No files matched the agent context request.');
      appendProposalTurns(planId, {
        kind:'context',
        type:'context_result',
        role:'tool',
        text:merged.length ? `${merged.length} candidate file${merged.length === 1 ? '' : 's'} ready; review before adding.` : 'No matching files were found.',
        state:merged.length ? 'done' : 'failed',
        tool:'BEAST context header retrieval',
        authority:'metadata-first search; review before attaching'
      }, { activity:merged.length ? 'Requested context found' : 'No requested context found' });
      persist();
      return merged;
    } catch (error) {
      patch({ contextSuggestionStatus:'error' });
      appendProposalTurns(planId, {
        kind:'context',
        type:'context_result',
        role:'tool',
        text:String(error.message || error).slice(0,240),
        state:'failed',
        tool:'BEAST context header retrieval',
        authority:'metadata-first search; review before attaching'
      }, { activity:'Context search failed' });
      throw error;
    }
  }

  function resolvedModeForPrompt(mode,prompt) {
    // The mode picker is an explicit user contract.  Previous heuristic
    // routing silently changed Edit/Agent to Ask for prompts starting with
    // words such as "review" or "explain", so a selected editing mode could
    // never produce a SourcePlan.  Keep the selection intact; Ask remains the
    // only intentionally conversational mode.
    return ['ask','edit','agent'].includes(mode) ? mode : 'agent';
  }

  async function expandContext(prompt, selectedFiles) {
    if (BeastStore.get().connection.status !== 'online' || BeastDesktopBridge.demoMode) return selectedFiles;
    try {
      patch({ status:'gathering-context', error:'' });
      const payload = await BeastRuntime.request('/edgek/workspace/context', {
        // Code Cortex can legitimately need several seconds on a cold index.
        // Keep this bounded, but do not discard the wider change surface at
        // the old 8-second cutoff while the agent is otherwise healthy.
        method:'POST', timeoutMs:15000,
        body:{ root_path:root(), objective:prompt, selected_files:selectedFiles, token_budget:8000, limit:12, interactive_timeout_ms:4500 }
      });
      const known = new Set(BeastStore.get().workspace.files.map(row => row.path));
      const discovered = [];
      const visit = (value, depth = 0) => {
        if (depth > 6 || value == null) return;
        if (Array.isArray(value)) { value.forEach(item => visit(item, depth + 1)); return; }
        if (typeof value !== 'object') return;
        for (const key of ['path','file','relative_path']) {
          const path = typeof value[key] === 'string' ? value[key] : '';
          if (known.has(path)) discovered.push(path);
        }
        Object.values(value).forEach(item => visit(item, depth + 1));
      };
      visit(payload);
      const files = normalizeContextFiles([...selectedFiles, ...discovered]);
      const lost = selectedFiles.filter(path => !files.includes(path));
      if (lost.length) appendTrace('context', `Explicit attachment(s) retained by request but unavailable in index: ${lost.join(', ')}`);
      appendTrace('context', payload?.context_pending
        ? `${files.length} file(s) ready; deeper Code Cortex context continues with the agent`
        : `${files.length} file(s) selected by Code Cortex`);
      return files;
    } catch (error) {
      appendTrace('context', `Code Cortex expansion unavailable: ${String(error.message || error)}`);
      return selectedFiles;
    }
  }

  function instructionFor(mode, prompt, files, selection, compactLocal = false) {
    const scope = files.length ? files.map(path => `- ${path}`).join('\n') : '- no files attached';
    const selected = selection?.text
      ? `\n\nSelected code in ${selection.path} (${JSON.stringify(selection.range || {})}):\n---\n${selection.text}\n---`
      : '';
    if (mode === 'ask') return `Act as my coding partner. Answer from the attached repository context, cite relevant files, and identify uncertainty.\n\nQuestion: ${prompt}\n\nAttached workspace scope:\n${scope}${selected}`;
    if (mode === 'agent' && isAgentAnalysisPrompt(prompt)) return `Act as my agentic coding partner in first person. Inspect the attached repository context before answering. Use the available governed repository tools conceptually as evidence: read the active file, map important symbols/dependencies, call out uncertainty, and ask for more context if needed. This is an analysis turn, not an edit request: do not propose a patch, do not return Action IR, and do not claim files changed. Give a deep, context-aware analysis with concrete references to the attached files and likely follow-up checks.\n\nQuestion: ${prompt}\n\nAttached workspace scope:\n${scope}${selected}`;
    const actionRules = `\n\nReturn BEAST Action IR JSON only after inspecting the attached files. Use this exact shape:\n{"kind":"beast.action_intent.v1","objective":"...","actions":[{"type":"replace_exact","target":{"path":"relative/file"},"old":"exact current snippet","new":"replacement","intent":"why"},{"type":"run_verifier","intent":"run focused checks","parameters":{"command":"python -m pytest relevant/test.py -q"}}],"verify":["relevant test or check"]}\nUse only attached files and copy old snippets exactly. Every source-edit action must make a real, complete source change: never emit an unchanged old/new pair, an ellipsis, or prose such as "rest of the function remains the same." You may include non-mutating run_verifier or ask_for_context actions for the next governed loop; they cannot edit files and require approval. Never satisfy an implementation request with a cosmetic comment, a signature-only change, or the first plausible one-line tweak. Emit at most one source-edit action per file: when a file needs several changes, make one complete anchor replacement containing all of them. Trace the requested behavior through every attached implementation, caller, configuration, and test surface; emit all edits that are genuinely required. A one-hunk plan is valid only when the attached scope proves the behavior is truly isolated. ${compactLocal ? 'For the local Qwen route, emit at most three replace_exact actions and only lightweight syntax checks. ' : 'Keep scope controlled, but make the implementation complete. If multiple files are attached because the feature crosses UI, runtime, tests, and docs, produce a coordinated multi-file patch rather than a tiny isolated edit. '}Do not include markdown or prose outside the JSON.`;
    if (mode === 'edit') return `${prompt}\n\nEdit scope:\n${scope}${selected}${actionRules}`;
    return `Act as BEAST's autonomous implementation agent. Investigate with the available governed repository tools before deciding on edits: search symbols and references, read the attached files, inspect Code Cortex relationships, and use relevant verified BEAST skill recipes when available. Follow the resulting evidence through callers, configuration, and tests. Then return the complete reviewable Action IR needed to implement this task. BEAST will run only allowlisted verification in a temporary isolated workspace; it will ask for approval before any expanded file reads, skill use, or command execution.\n\nTask: ${prompt}\n\nInitial workspace scope:\n${scope}${selected}${actionRules}`;
  }

  async function createSession(prompt, files, model, provider, uiMode) {
    // Agent is the full implementation lane.  It retains SourcePlan approval
    // for mutations, but no longer degrades into a conversational planning
    // session that cannot produce or verify a patch.
    const mode = uiMode === 'ask' ? 'chat' : uiMode === 'analysis' ? 'analysis' : 'implementer';
    const payload = await BeastRuntime.request('/edgek/ide/agent-sessions/create', {
      method:'POST', timeoutMs:12000,
      body:{
        root_path:root(), objective:prompt, mode, provider, model, files,
        tools:['Code Cortex Search','Workspace File Read','Verified Skill Recipes','Isolated Test Verifier','Crystal Reuse','SourcePlan','Evidence'],
        budget:{ tokens:120000, seconds:3600, cost_usd:0 }
      }
    });
    const sessionId = payload?.session?.session_id || payload?.session_id || payload?.id;
    if (!sessionId) throw new Error('AI coding session returned no session id.');
    patch({ sessionId:String(sessionId) });
    persist();
    return String(sessionId);
  }

  function eventPayload(event) {
    const parsed = JSON.parse(event.data || '{}');
    return parsed && typeof parsed.payload === 'object' ? parsed.payload : parsed;
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

  function applyCrystal(payload = {}) {
    const decision = payload.decision && typeof payload.decision === 'object' ? payload.decision : {};
    const record = payload.record && typeof payload.record === 'object' ? payload.record : {};
    const crystal = {
      action:String(decision.action || ''),
      source:String(decision.source || ''),
      confidence:Number(decision.confidence || 0),
      reused:Boolean(payload.reused),
      avoidedTokens:Number(decision.avoided_tokens_estimate || 0),
      decisionId:String(decision.decision_id || ''),
      recorded:Boolean(record.verified === true || record.promotion_status === 'verified'),
      candidate:Boolean(Object.keys(record).length)
    };
    patch({ crystal });
    appendTrace('crystal', crystal.reused
      ? `Reused ${crystal.source || 'crystal'} · ${crystal.avoidedTokens} tokens avoided`
      : `${crystal.action || 'reuse preflight'} · ${crystal.source || 'local execution'}`);
    persist();
  }

  function applyCompute(payload = {}) {
    const row = payload.context && typeof payload.context === 'object' ? payload.context : {};
    patch({ compute:{
      selectedFiles:Number(row.selected_files || 0), readableFiles:Number(row.readable_files || 0),
      sourceChars:Number(row.source_chars || 0), suppliedChars:Number(row.supplied_chars || 0),
      truncatedFiles:Number(row.truncated_files || 0), policy:String(row.policy || ''),
      kvCache:String(row.kv_cache || ''), crystal:String(row.crystal || ''),
      historyOriginalTokens:Number(row.history_original_tokens || 0), historyFinalTokens:Number(row.history_final_tokens || 0), historyChanged:Boolean(row.history_changed)
    }});
    const saved=Math.max(0,Number(row.source_chars || 0)-Number(row.supplied_chars || 0));
    appendTrace('economizer', `${row.readable_files || 0} selected file(s) bounded to ${row.supplied_chars || 0} chars${saved ? ` · ${saved} chars withheld` : ''}`);
  }

  async function send(prompt, options = {}) {
    const clean = String(prompt || BeastStore.get().aiCoding.prompt || '').trim();
    if (!clean) throw new Error('Describe the coding task first.');
    if (BeastStore.get().aiCoding.streaming) throw new Error('The current AI turn is still running.');
    const selection = BeastStore.get().aiCoding.selection;
    const route = await resolveCodingRoute(options.model || BeastStore.get().aiCoding.model);
    if (!route.model || !route.provider) throw new Error('Select a ready model and provider before running AI coding.');
    const localCoder = /^(?:ollama|local_ollama)$/i.test(route.provider) && route.model === RELIABLE_LOCAL_CODER;
    // Pair Programmer scope is an operator boundary. Code Cortex can help
    // discover files elsewhere, but it must never add files to this request.
    let files = contextFilesFor(clean);
    const selectedMode=BeastStore.get().aiCoding.mode;const mode=resolvedModeForPrompt(selectedMode,clean);
    const analysisRun = mode === 'agent' && isAgentAnalysisPrompt(clean) && !options.actionIrRecovery && !options.forcePatch;
    // An investigation starts from the active file, not every attachment
    // accumulated by earlier turns. Additional files enter only through an
    // explicit @mention or an approved capability request.
    if (mode === 'agent' && !analysisRun && !options.focused && !options.preserveContext) {
      const active=BeastStore.get().editor.activePath;
      const scoped=normalizeContextFiles([active,...mentionedFiles(clean)].filter(Boolean));
      if (files.length > scoped.length) appendTrace('context', `Agent investigation starts with ${scoped.length} explicit file(s); prior attachments remain available for approval, not automatically sent.`);
      files=scoped;
    }
    if (localCoder && files.length > RELIABLE_LOCAL_PROFILE.maxFiles) {
      files = files.slice(0, RELIABLE_LOCAL_PROFILE.maxFiles);
      appendTrace('routing', `Local coding context bounded to ${RELIABLE_LOCAL_PROFILE.maxFiles} files for responsive CPU inference.`);
    }
    if (options.focused && files.length > 1) { files=files.slice(0,1);appendTrace('retry', `Focused recovery retained ${files[0]} and excluded ${Math.max(0,contextFilesFor(clean).length-1)} additional context file(s).`); }
    if(mode!=='ask'&&!files.length)throw new Error('Edit and Agent modes require an open or attached workspace file. Open the target file, then retry.');
    const retryDirective=options.focused?'\n\nRecovery mode: make one exact, reviewable edit in the single attached file. Do not inspect or propose changes outside it; return valid Action IR JSON before output ends.':(options.actionIrRecovery?'\n\nRecovery mode: your previous response looked like an edit packet but failed BEAST SourcePlan compilation. Return one valid BEAST Action IR JSON object only. Include complete exact replacements, at most one source-edit action per file, and no markdown or prose. If you cannot make a safe exact edit, emit ask_for_context instead of advisory prose.':'');
    const runPrompt = `${instructionFor(mode, clean, files, selection, localCoder)}${retryDirective}`;
    const agentProfile = agentTurnProfile(clean, mode, analysisRun, files);
    addMessage('user', clean, { mode, files, selection:selection ? { path:selection.path, range:selection.range } : null });
    const assistantId = addMessage('assistant', '', {
      streaming:true, mode, activity:mode === 'ask' ? 'Thinking…' : `Starting ${agentProfile.kind} loop…`,
      agentProfile,
      turns:mode === 'ask'
        ? [{ id:`turn-${now()}-context`, kind:'context', type:'context_read', role:'tool', tool:'Workspace File Read', text:`Context gathered · ${files.length} file${files.length === 1 ? '' : 's'} in scope`, state:'done', authority:'selected files only', at:now() }]
        : initialAgentTurns(agentProfile, files),
      progress:mode === 'ask'
        ? [{ phase:'context', label:'Context gathered', detail:`${files.length} file${files.length === 1 ? '' : 's'} in scope`, state:'done', at:now() }]
        : initialAgentProgress(agentProfile, files)
    });
    patch({ streaming:true, status:'creating', error:'', prompt:'', sourcePlanReady:false, sourcePlanId:'', contextFiles:files });
    let sessionId = analysisRun ? '' : BeastStore.get().aiCoding.sessionId;
    let proposalReady = false;
    let needsOperator = false;
    let advisoryReceived = false;
    let terminalEventSeen = false;
    let rawAssistant = '';
    let lastDraftProgressAt = 0;
    try {
      if (!sessionId) sessionId = await createSession(clean, files, route.model, route.provider, analysisRun ? 'analysis' : mode);
      const params = new URLSearchParams({
        root_path:root(), prompt:runPrompt, provider:route.provider, model:route.model,
        max_tokens:String(Number(options.maxTokens || (localCoder ? (mode === 'ask' ? RELIABLE_LOCAL_PROFILE.askTokens : RELIABLE_LOCAL_PROFILE.editTokens) : (mode === 'ask' ? 6000 : 16000)))),
        context_max_chars_each:String(Number(options.contextMaxCharsEach || (localCoder ? RELIABLE_LOCAL_PROFILE.contextChars : 50000)))
      });
      files.forEach(path => params.append('context_files', path));
      const eventSource = await openRunStream(`${gatewayUrl()}/edgek/ide/agent-sessions/${encodeURIComponent(sessionId)}/run-events?${params.toString()}`);
      stream = eventSource;
      updateProgress(assistantId,'connect','Connecting to model',`${route.provider} / ${route.model}`,'active');
      armWatchdog(assistantId, eventSource);
      eventSource.onopen = () => { if (stream === eventSource) { armWatchdog(assistantId,eventSource);patch({ status:'streaming' }); appendTrace('connection', `Connected to ${route.provider}/${route.model}`);appendTurn(assistantId,{type:'model_connection',kind:'connection',text:`Connected to ${route.provider}/${route.model}`,state:'done',role:'model'});updateProgress(assistantId,'connect','Model connected',`${route.provider} / ${route.model}`,'done');updateProgress(assistantId,'draft','Drafting response',mode === 'ask'||analysisRun ? 'Streaming answer' : 'Streaming model output','active'); } };
      eventSource.addEventListener('agent_run_started', event => { if(stream===eventSource){armWatchdog(assistantId,eventSource);const payload=eventPayload(event);const detail=payload.session_id?`Session ${String(payload.session_id).slice(-6)}`:'Session ready';appendTurn(assistantId,{type:'agent_turn',kind:'run',text:`Coding run started · ${detail}`,state:'done',role:'agent',authority:'selected workspace scope'});updateProgress(assistantId,'run','Coding run started',detail,'done');} });
      eventSource.addEventListener('agent_run_preflight', event => { if(stream===eventSource){armWatchdog(assistantId,eventSource);const payload=eventPayload(event);const recipes=Array.isArray(payload.recipes)?payload.recipes:[];const skipped=Array.isArray(payload.skipped_tools)?payload.skipped_tools:[];const detail=`Pathfinder ${payload.route_id||'ready'} · ${recipes.length} verified recipe(s) · ${skipped.length} optional tool(s) skipped`;appendTrace('preflight',detail);appendTurn(assistantId,{type:'tool_result',kind:'preflight',tool:'Pathfinder/SkillTree',text:detail,state:'done',role:'tool',authority:'advisory only'});updateProgress(assistantId,'preflight','Pathfinder preflight',`${recipes.length} verified recipe(s) · advisory only`,'done');} });
      eventSource.addEventListener('agent_run_context', event => { if(stream===eventSource){armWatchdog(assistantId,eventSource);const payload=eventPayload(event);const locked=Array.isArray(payload.files)?payload.files:files;const unreadable=Array.isArray(payload.unreadable_files)?payload.unreadable_files:[];const missing=files.filter(path=>!locked.includes(path));const loaded=payload.content_loaded!==false&&locked.length>0&&!missing.length;patch({contextFiles:normalizeContextFiles([...files,...locked])});const failure=[...unreadable.map(item=>`${item.path||'file'}: ${item.error||'unreadable'}`),...missing.map(path=>`${path}: not locked by backend`)].join(' · ');const detail=loaded?`Content loaded: ${locked.join(', ')}`:`Context mismatch/read failure: ${failure||'no readable file reached the run'}`;updateProgress(assistantId,'context',loaded?'Context content loaded':'Context mismatch or read failure',loaded?locked.join(' · '):failure||'No readable file reached the agent',loaded?'done':'failed');appendTrace('context',detail);appendTurn(assistantId,{type:'tool_result',kind:'context_read',tool:'Workspace File Read',text:detail,state:loaded?'done':'failed',role:'tool',authority:'selected files only'});} });
      eventSource.addEventListener('agent_run_stage', event => { if (stream === eventSource) {armWatchdog(assistantId,eventSource);const text=String(eventPayload(event).text||'Working').replaceAll('_',' ');appendTrace('stage',text);appendTurn(assistantId,{type:'agent_reasoning',kind:'stage',text,state:'active',role:'agent'});updateProgress(assistantId,'stage',text,'Agent stage','active');} });
      eventSource.addEventListener('agent_run_tool', event => { if (stream === eventSource) {armWatchdog(assistantId,eventSource);const payload=eventPayload(event);const text=String(payload.text||'Using repository tool');const turnType=payload.type||'tool_result';const turnState=payload.status==='deferred'?'failed':turnType==='tool_call'?'active':'done';appendTrace('tool',text);appendTurn(assistantId,{type:turnType,kind:payload.phase||'tool',tool:payload.tool||'BEAST governed tool',text,state:turnState,role:'tool',authority:payload.authority||'read-only/governed',evidence:payload.evidence||''});updateProgress(assistantId,'tools',turnType==='tool_call'?'Using repository tool':'Repository tool finished',`${payload.tool?`${payload.tool}: `:''}${text}`,turnState);} });
      eventSource.addEventListener('agent_run_permission_request', async event => {
        if (stream !== eventSource) return;
        armWatchdog(assistantId,eventSource);
        const payload=eventPayload(event);const caps=Array.isArray(payload.capabilities)?payload.capabilities:[];
        const labels=caps.map(item=>`• ${item.label||item.id}: ${item.scope||'read-only'}`).join('\n');
        const approved=window.confirm(`BEAST requests governed capabilities for this agent run:\n\n${labels}\n\nSource writes always remain a separate SourcePlan approval. Test commands, if requested, run only in an isolated temporary workspace. Approve?`);
        if(!approved){appendTrace('permission','Agent capability request declined');appendTurn(assistantId,{type:'permission_request',kind:'permission',text:'Capability request declined',state:'failed',authority:'operator declined'});return;}
        const paths=caps.flatMap(item=>Array.isArray(item.paths)?item.paths:[]);
        try { await BeastRuntime.request('/edgek/ide/agent-sessions/capabilities/grant',{method:'POST',timeoutMs:10000,body:{root_path:root(),session_id:payload.session_id,request_id:payload.request_id,capabilities:caps.map(item=>item.id),paths}});appendTrace('permission',`Approved ${caps.length} governed capability request(s); BEAST will use them before provider dispatch when the grant arrives in time.`);appendTurn(assistantId,{type:'permission_request',kind:'permission',text:`Approved ${caps.length} governed capability request(s)`,state:'done',authority:'operator approved'}); }
        catch(error){appendTrace('permission',`Capability approval could not be saved: ${String(error.message||error)}`);}
      });
      eventSource.addEventListener('agent_run_token', event => {
        if (stream !== eventSource) return;
        armWatchdog(assistantId,eventSource);
        const text=String(eventPayload(event).text||'');rawAssistant=`${rawAssistant}${text}`.slice(-60000);
        if(mode==='ask'||analysisRun)appendAssistant(assistantId,text);
        else if(isStructuredEditStream(rawAssistant)){const draft=draftPreviewFromRaw(rawAssistant);const current=BeastStore.get().aiCoding.messages.find(message=>message.id===assistantId)||{};updateAssistant(assistantId,{content:current.narrating&&current.content?current.content:structuredDraftStatus(draft),draftPreview:draft,internalFormat:'beast.action_intent.v1'});}
        else appendAssistant(assistantId,text);
        if(now()-lastDraftProgressAt>=120){lastDraftProgressAt=now();updateProgress(assistantId,'draft',mode==='ask'||analysisRun?'Streaming answer':'Streaming model output',`${rawAssistant.length.toLocaleString()} characters received`,'active');if(mode!=='ask'&&!analysisRun)updateAssistantPreview(assistantId,draftPreviewFromRaw(rawAssistant));}
      });
      eventSource.addEventListener('agent_run_provider_done', () => { if(stream===eventSource){armWatchdog(assistantId,eventSource);patch({status:mode==='ask'||analysisRun?'finishing':'building-changes'});appendTurn(assistantId,{type:'model_output',kind:'provider',text:`Provider stream complete · ${rawAssistant.length.toLocaleString()} characters`,state:'done',role:'model',authority:analysisRun?'read-only analysis':'draft only'});if(mode!=='ask'&&!analysisRun)updateAssistantPreview(assistantId,draftPreviewFromRaw(rawAssistant));updateProgress(assistantId,'draft',mode==='ask'||analysisRun?'Answer received':'Model output received',`${rawAssistant.length.toLocaleString()} characters`,'done');updateProgress(assistantId,'compile',mode==='ask'||analysisRun?'Finalizing answer':'Compiling reviewable patch',mode==='ask'||analysisRun?'Formatting response':'Translating Action IR into safe operations','active');} });
      eventSource.addEventListener('agent_run_validation', event => {
        if(stream!==eventSource)return;armWatchdog(assistantId,eventSource);const payload=eventPayload(event);const status=String(payload.status||'checking');const verifiers=payload.isolated_verifiers||{};const approvalNeeded=verifiers.status==='approval_required';const verifierDetail=verifiers.status?` · isolated ${verifiers.status}${Number(verifiers.passed||0)?` (${Number(verifiers.passed)} passed)`:''}${Number(verifiers.skipped||0)?` · ${Number(verifiers.skipped)} skipped`:''}`:'';const detail=approvalNeeded?`Test approval needed${verifierDetail}`:`${status} · ${Number(payload.check_count||0)} checks${verifierDetail}`;patch({status:approvalNeeded?'test-approval-needed':'validating-changes'});updateProgress(assistantId,'compile','Patch compiled','Operations are bounded to attached files','done');updateProgress(assistantId,'validate',approvalNeeded?'Test approval needed':(payload.repair?'Rechecking repaired edits':'Validating proposed files'),approvalNeeded?'Approve the isolated verifier capability; BEAST will continue the governed loop when the approval reaches the run.':detail,approvalNeeded?'active':status==='passed'||status==='partial'?'done':'active');appendTrace('validation',detail);appendTurn(assistantId,{type:'verification',kind:'validation',text:detail,state:approvalNeeded?'active':status==='passed'||status==='partial'?'done':'active',role:'verifier',authority:'local syntax/sourceplan'});
        (Array.isArray(verifiers.commands)?verifiers.commands:[]).slice(0,6).forEach(item=>appendTurn(assistantId,{type:approvalNeeded?'command_request':'command_result',kind:'command',command:String(item.command||'verifier'),text:String(item.message||item.status||'verifier'),state:approvalNeeded?'active':String(item.status||'done'),role:'command',authority:'isolated temporary workspace'}));
      });
      eventSource.addEventListener('agent_run_request', event => {
        if (stream !== eventSource) return;
        armWatchdog(assistantId,eventSource);
        const payload=eventPayload(event);
        appendTrace('request', String(payload.text || payload.command || payload.query || 'Agent requested a follow-up action'));
        appendTurn(assistantId,{type:payload.type||'agent_request',kind:payload.request_type||'request',text:String(payload.text||payload.query||payload.command||'Agent requested a follow-up action'),command:String(payload.command||''),state:'active',role:'agent',authority:payload.authority||'operator approval required'});
      });
      eventSource.addEventListener('agent_run_crystal', event => { if (stream === eventSource) {armWatchdog(assistantId,eventSource);applyCrystal(eventPayload(event));} });
      eventSource.addEventListener('agent_run_compute', event => { if (stream === eventSource) {armWatchdog(assistantId,eventSource);applyCompute(eventPayload(event));} });
      eventSource.addEventListener('agent_run_scorecard', event => { if (stream === eventSource) {armWatchdog(assistantId,eventSource);const score=eventPayload(event);const lattice=score.lattice?.match_strength?` · crystal match ${Math.round(Number(score.lattice.match_strength)*100)}%`:'';const worktree=score.worktree?.recommended?' · worktree advised':'';appendTrace('review',`Scorecard: ${score.risk_level||'unknown'} risk · ${score.decision||'review'}${lattice}${worktree}`);updateProgress(assistantId,'scorecard','BEAST review scorecard',`${score.risk_level||'unknown'} risk · ${score.decision||'review'}`,'done');} });
      eventSource.addEventListener('agent_run_intelligence', event => { if (stream === eventSource) {armWatchdog(assistantId,eventSource);const data=eventPayload(event);appendTrace('intelligence',`Pathfinder + Quality Cascade ${data.quality||'completed'} · Conductor ${data.workflow||'advisory'} (${data.dispatch||'not dispatched'}) · Canon ${data.canon_valid?'valid':'review'}${data.tool_skips?` · ${data.tool_skips} optional tool(s) skipped`:''}`);updateProgress(assistantId,'intelligence','Intelligence fabric',`Quality ${data.quality||'completed'} · Canon ${data.canon_valid?'valid':'review'}`,'done');} });
      eventSource.addEventListener('agent_run_sourceplan', event => {
        if (stream !== eventSource) return;
        armWatchdog(assistantId,eventSource);
        const payload = eventPayload(event);
        const proposal = stageSourcePlan(payload.plan);
        proposalReady = Boolean(proposal?.ready);
        if (proposal) updateAssistant(assistantId,{ content:proposalSummary(proposal, payload.plan?.objective), proposal, activity:'Changes ready for review', internalFormat:'beast.action_intent.v1' });
        updateProgress(assistantId,'review','Changes ready for review',`${payload.operation_count || proposal?.operations?.length || 0} governed operation(s)`,'ready');
        patch({ status:'ready-to-review', error:'' });
        appendTrace('sourceplan', `${payload.operation_count || 0} governed operation(s) ready`);
        appendTurn(assistantId,'sourceplan',`${payload.operation_count || 0} governed operation(s) ready for review`,'done');
      });
      eventSource.addEventListener('agent_run_advisory', event => {
        if (stream !== eventSource) return;
        armWatchdog(assistantId, eventSource);
        advisoryReceived = true;
        const payload = eventPayload(event);
        const text = String(payload.text || '').trim();
        const invalidPacket = looksLikeActionIntent(text);
        if (invalidPacket) {
          needsOperator = true;
          const recovery = {
            type:'invalid_action_ir',
            title:'Edit packet needs repair',
            message:'The model produced a structured edit draft, but BEAST could not compile it into a safe SourcePlan. No files changed.',
            actions:[
              { id:'agent-repair-packet', label:'Repair edit packet', detail:'rerun with stricter Action IR contract' },
              { id:'retry', label:'Retry normally', detail:'same request and context' }
            ]
          };
          updateAssistant(assistantId, { content:'BEAST caught an edit-packet problem before it could become a patch. No files changed.', recovery, activity:'Recovery needed', error:false, internalFormat:'beast.action_intent.v1' });
          updateProgress(assistantId,'compile','Edit packet needs repair','No files changed; repair or retry from the retained context.','failed');
          patch({ status:'review-needed', error:'' });
          appendTrace('recovery', 'Invalid Action IR held for recovery. No SourcePlan was created.');
          appendTurn(assistantId,{type:'recovery_request',kind:'recovery',text:'I caught a structured edit draft that needs repair before it can become a SourcePlan.',state:'failed',role:'agent',authority:'no source mutation'});
          return;
        }
        const content = text || 'The model returned an advisory response. No files were changed.';
        updateAssistant(assistantId, { content, activity:'Advisory response', error:false, internalFormat:'' });
        updateProgress(assistantId,'compile','Advisory response',String(payload.message || 'No files were changed.'),'done');
        patch({ status:'complete', error:'' });
        appendTrace('advisory', String(payload.message || 'Model returned advice without a patch.'));
        appendTurn(assistantId,'advisory',String(payload.message || 'Model returned advice without a patch.'),'done');
      });
      eventSource.addEventListener('agent_run_needs_operator', event => {
        if (stream !== eventSource) return;
        armWatchdog(assistantId,eventSource);
        const payload = eventPayload(event);
        needsOperator = true;
        const reason=String(payload.error || 'The model response could not be translated into a safe patch.');
        // A raw Action IR is not a proposal. The backend just rejected it, so
        // rendering its claimed edits as a preview makes a failed compile look
        // like a safe, reviewable patch.
        const intent=parseActionIntent(rawAssistant);const proposal=null;
        const returned=String(payload.assistant_text||rawAssistant||'').trim();const readable=returned&&!/^[\s`]*[\[{]/.test(returned)?returned:'';
        const failureCopy=readable?`The agent inspected the selected file but returned advice instead of reviewable edits. No file was changed.\n\n${readable}\n\nPatch compiler: ${reason}`:`I could not safely turn the model response into file edits. No file was changed.\n\nPatch compiler: ${reason}\n\nThe selected file remained attached; retry Edit/Agent or select the exact code range.`;
        updateAssistant(assistantId,{ content:failureCopy, proposal, draftPreview:draftPreviewFromRaw(returned), activity:'Needs your input', error:true, internalFormat:intent?'beast.action_intent.v1':'' });
        patch({ status:'review-needed', error:reason });
        appendTrace('review', payload.error || 'Operator translation required');
        appendTurn(assistantId,'review',reason,'failed');
      });
      eventSource.addEventListener('agent_run_done', event => {
        if (stream !== eventSource) return;
        terminalEventSeen = true;
        eventSource.close(); stream = null; clearWatchdog();
        const payload = eventPayload(event);
        const recoveredPlan=payload.session?.output?.sourceplan_plan;
        if(!proposalReady&&recoveredPlan?.operations?.length){const proposal=stageSourcePlan(recoveredPlan);proposalReady=Boolean(proposal?.ready);if(proposal)updateAssistant(assistantId,{content:proposalSummary(proposal,recoveredPlan.objective),proposal,internalFormat:'beast.action_intent.v1'});}
        const current=BeastStore.get().aiCoding.messages.find(message=>message.id===assistantId);
        let fallback='';
        if((mode==='ask'||analysisRun)&&!String(current?.content||'').trim())fallback='I did not receive a text response. Try again or choose another model.';
        if(mode!=='ask'&&!analysisRun&&!proposalReady&&!needsOperator&&!advisoryReceived)fallback=`I finished investigating, but no safe patch was produced. The locked context was kept (${files.join(', ') || 'no files'}). Retry with the exact selection or ask for a smaller governed patch.`;
        finishProgress(assistantId,fallback?'Stopped before a safe result was produced':'Run complete');
        updateAssistant(assistantId,{ streaming:false, activity:'', ...(fallback?{content:fallback,error:true}:{}) });
        patch({ streaming:false, status:proposalReady?'ready-to-review':needsOperator||fallback?'review-needed':'complete', error:needsOperator?BeastStore.get().aiCoding.error:fallback });
        const completeText = runDoneSentence(payload.sourceplan_status || 'complete', { needsOperator, proposalReady, advisoryReceived, analysisRun });
        appendTrace('complete', completeText);
        appendTurn(assistantId,'complete',completeText,'done');
        BeastStore.addLedger(`AI coding turn complete: ${clean.slice(0,80)}`);
        BeastMascot.setState('finished');
        persist();
      });
      eventSource.addEventListener('agent_run_error', event => {
        if (stream !== eventSource) return;
        terminalEventSeen = true;
        let error = 'AI coding stream failed.';
        try { error = eventPayload(event).error || error; } catch (_) {}
        fail(error, assistantId, eventSource);
      });
      eventSource.addEventListener('error', () => {
        if (stream === eventSource && BeastStore.get().aiCoding.streaming) fail('AI coding stream disconnected.', assistantId, eventSource);
      });
      eventSource.addEventListener('end', () => {
        // Electron distinguishes a normal finite SSE close from a transport
        // error. A completed run closes itself on agent_run_done; reaching
        // here therefore means the gateway ended before a terminal result.
        if (terminalEventSeen) return;
        if (stream === eventSource && BeastStore.get().aiCoding.streaming) fail('The gateway ended the coding stream before BEAST returned a terminal result.', assistantId, eventSource);
      });
      BeastMascot.setState('working');
      persist();
      return { ok:true, session_id:sessionId };
    } catch (error) {
      fail(String(error.message || error), assistantId);
      throw error;
    }
  }

  function fail(error, assistantId, eventSource = null) {
    if (eventSource) eventSource.close();
    if (!eventSource || stream === eventSource) stream = null;
    clearWatchdog();
    const messages = BeastStore.get().aiCoding.messages.map(message => message.id === assistantId ? { ...message, content:String(message.content||'').trim()||`The coding run stopped before it produced a safe result.\n\n${String(error||'AI coding failed.')}`, streaming:false, activity:'', error:true, progress:(message.progress||[]).map(item=>item.state==='active'?{...item,state:'failed',detail:String(error||'AI coding failed.').slice(0,240)}:item) } : message);
    patch({ streaming:false, status:'error', error:String(error || 'AI coding failed.'), messages });
    appendTrace('error', error);
    BeastMascot.setState('alert');
    persist();
  }

  function cancel() {
    if (stream) { stream.close(); stream = null; }
    clearWatchdog();
    if (BeastStore.get().aiCoding.streaming) {
      const messages=BeastStore.get().aiCoding.messages.map(message=>message.streaming?{...message,streaming:false,activity:'',content:String(message.content||'').trim()||'Run stopped. No files were changed.',progress:(message.progress||[]).map(item=>item.state==='active'?{...item,state:'failed',detail:'Stopped by operator'}:item)}:message);
      patch({ streaming:false, status:'cancelled', error:'Stopped by operator. No files were changed.', messages });
    }
    BeastMascot.setState('idle');
    persist();
  }

  function clear() {
    cancel();
    patch({ sessionId:'', messages:[], trace:[], status:'idle', error:'', prompt:'', selection:null, sourcePlanReady:false, sourcePlanId:'', crystal:{ action:'', source:'', confidence:0, reused:false, avoidedTokens:0, decisionId:'', recorded:false, candidate:false }, compute:{ selectedFiles:0, readableFiles:0, sourceChars:0, suppliedChars:0, truncatedFiles:0, policy:'', kvCache:'', crystal:'' } });
    persist();
  }

  async function openSourcePlan() {
    if (!BeastStore.get().aiCoding.sourcePlanReady) throw new Error('No AI SourcePlan is ready yet.');
    await BeastRouter.navigate('source');
  }

  async function verifyRequestedChecks() {
    const state = BeastStore.get();
    const plan = state.sourcePlan?.plan;
    if (!plan?.operations?.length) throw new Error('No AI SourcePlan is ready to verify.');
    const planId = String(plan.plan_id || state.aiCoding.sourcePlanId || '');
    patch({ status:'verifying-agent-checks', error:'' });
    appendTrace('tests', 'Running agent-requested checks in an isolated temporary workspace');
    const requestedCommands = [
      ...((plan.action_ir?.verify || []).map(command => String(command || '').trim()).filter(Boolean)),
      ...((plan.non_mutating_requests || []).map(item => {
        const parameters = item && typeof item.parameters === 'object' ? item.parameters : {};
        return String(parameters.command || item?.command || '').trim();
      }).filter(Boolean))
    ].slice(0,6);
    const queuedCommands = requestedCommands.length ? requestedCommands : ['BEAST isolated verifier suite'];
    const beforeMessages = BeastStore.get().aiCoding.messages.map(message => {
      if (message.role !== 'assistant' || !message.proposal) return message;
      const samePlan = planId && String(message.proposal.planId || '') === planId;
      if (!samePlan && message !== [...BeastStore.get().aiCoding.messages].reverse().find(item => item.role === 'assistant' && item.proposal)) return message;
      const turns = Array.isArray(message.turns) ? message.turns : [];
      const commandTurns = queuedCommands.map(command => ({
        id:`turn-${now()}-${Math.random()}`,
        kind:'command',
        type:'command_call',
        role:'command',
        text:'Operator approved; running in an isolated temporary workspace.',
        state:'active',
        command,
        tool:'BEAST isolated verifier',
        authority:'isolated temporary workspace',
        evidence:'',
        at:now()
      }));
      return {
        ...message,
        activity:'Running isolated checks',
        turns:[...turns, { id:`turn-${now()}-${Math.random()}`, kind:'permission', type:'permission_request', role:'operator', text:'Operator approved isolated verifier checks.', state:'done', authority:'operator approved isolated verifier', evidence:'', at:now() }, ...commandTurns].slice(-80)
      };
    });
    patch({ messages:beforeMessages });
    const result = await BeastRuntime.request('/edgek/ide/agent-sessions/verify-sourceplan', {
      method:'POST', timeoutMs:90000,
      body:{ root_path:root(), session_id:state.aiCoding.sessionId, plan }
    });
    const verifiedPlan = result?.plan && typeof result.plan === 'object' ? result.plan : { ...plan, validation:result?.validation || plan.validation || {} };
    const validation = verifiedPlan.validation || result?.validation || {};
    const proposal = proposalFromActions(verifiedPlan.operations || [], true, verifiedPlan.plan_id || planId, validation, verifiedPlan.intelligence || {}, verifiedPlan.non_mutating_requests || []);
    BeastStore.patch('sourcePlan', {
      plan:verifiedPlan, lifecycle:null,
      status:validation.ok ? 'verified' : 'verification-failed',
      message:`Agent requested checks ${validation.status || 'completed'} · ${Number(validation.check_count || 0)} checks`,
      error:validation.ok ? '' : (validation.failures || []).slice(0,3).join(' · '),
      updatedAt:now()
    });
    const messages = BeastStore.get().aiCoding.messages.map(message => {
      if (message.role !== 'assistant' || !message.proposal) return message;
      const samePlan = planId && String(message.proposal.planId || '') === planId;
      if (!samePlan && message !== [...BeastStore.get().aiCoding.messages].reverse().find(item => item.role === 'assistant' && item.proposal)) return message;
      const turns = Array.isArray(message.turns) ? message.turns : [];
      const commandTurns = (Array.isArray(validation.isolated_verifiers?.commands) ? validation.isolated_verifiers.commands : []).slice(0,6).map(item => ({
        id:`turn-${now()}-${Math.random()}`,
        kind:'command',
        type:'command_result',
        role:'command',
        text:String(item.message || item.status || 'verifier completed').slice(0,500),
        state:String(item.status || (validation.ok ? 'done' : 'failed')),
        command:String(item.command || 'verifier'),
        tool:'BEAST isolated verifier',
        authority:'isolated temporary workspace',
        evidence:String(result?.evidence_receipt?.receipt_id || ''),
        at:now()
      }));
      return {
        ...message,
        content:proposalSummary(proposal, verifiedPlan.objective),
        proposal,
        turns:[...turns, { id:`turn-${now()}-${Math.random()}`, kind:'validation', type:'verification', role:'verifier', text:`Agent requested checks ${validation.status || 'completed'} · ${Number(validation.check_count || 0)} checks`, state:validation.ok?'done':'failed', authority:'operator approved isolated verifier', evidence:String(result?.evidence_receipt?.receipt_id || ''), at:now() }, ...commandTurns].slice(-80)
      };
    });
    patch({ messages, status:validation.ok?'agent-checks-passed':'agent-checks-failed' });
    appendTrace('tests', `Agent requested checks ${validation.status || 'completed'} · ${(validation.isolated_verifiers || {}).passed || 0} passed · ${(validation.isolated_verifiers || {}).failed || 0} failed`);
    persist();
    return result;
  }

  window.BeastAICoding = {
    restore, persist, setOpen, setExpanded, setMode, setPrompt, syncModel, toggleContext, addActiveFile,
    suggestContext, acceptSuggestedContext, resolveRequestedContext,
    captureSelection, removeSelection, send, runInWorktree, retryLastRequest, recoverInvalidPacket, continueWithAddedContext, cancel, clear, openSourcePlan, verifyRequestedChecks, noteSourcePlanApply
  };
  document.addEventListener('beast:agent-sourceplan-applied', noteSourcePlanApply);
})();
