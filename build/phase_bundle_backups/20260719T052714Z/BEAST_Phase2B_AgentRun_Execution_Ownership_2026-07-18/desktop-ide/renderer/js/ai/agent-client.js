// BEAST Pair Programmer renderer module: agent-client.js
(() => {
  const registry = window.BeastAICodingModules = window.BeastAICodingModules || {};
  registry.createAgentClient = runtime => {
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
  const addMessage = (...args) => api.addMessage(...args);
  const agentTurnProfile = (...args) => api.agentTurnProfile(...args);
  const appendAssistant = (...args) => api.appendAssistant(...args);
  const appendProposalTurns = (...args) => api.appendProposalTurns(...args);
  const appendTrace = (...args) => api.appendTrace(...args);
  const appendTurn = (...args) => api.appendTurn(...args);
  const applyCompute = (...args) => api.applyCompute(...args);
  const applyCrystal = (...args) => api.applyCrystal(...args);
  const armWatchdog = (...args) => api.armWatchdog(...args);
  const clearWatchdog = (...args) => api.clearWatchdog(...args);
  const contextFilesFor = (...args) => api.contextFilesFor(...args);
  const draftPreviewFromRaw = (...args) => api.draftPreviewFromRaw(...args);
  const eventPayload = (...args) => api.eventPayload(...args);
  const finishProgress = (...args) => api.finishProgress(...args);
  const initialAgentProgress = (...args) => api.initialAgentProgress(...args);
  const initialAgentTurns = (...args) => api.initialAgentTurns(...args);
  const instructionFor = (...args) => api.instructionFor(...args);
  const isAgentAnalysisPrompt = (...args) => api.isAgentAnalysisPrompt(...args);
  const isStructuredEditStream = (...args) => api.isStructuredEditStream(...args);
  const mentionedFiles = (...args) => api.mentionedFiles(...args);
  const normalizeContextFiles = (...args) => api.normalizeContextFiles(...args);
  const patch = (...args) => api.patch(...args);
  const persist = (...args) => api.persist(...args);
  const proposalSummary = (...args) => api.proposalSummary(...args);
  const resolvedModeForPrompt = (...args) => api.resolvedModeForPrompt(...args);
  const runDoneSentence = (...args) => api.runDoneSentence(...args);
  const stageSourcePlan = (...args) => api.stageSourcePlan(...args);
  const structuredDraftStatus = (...args) => api.structuredDraftStatus(...args);
  const updateAssistant = (...args) => api.updateAssistant(...args);
  const updateAssistantPreview = (...args) => api.updateAssistantPreview(...args);
  const updateProgress = (...args) => api.updateProgress(...args);
  const handlePermissionRequest = (...args) => api.handlePermissionRequest(...args);

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
    patch({ streaming:true, status:'creating', activeRunId:'', error:'', prompt:'', sourcePlanReady:false, sourcePlanId:'', contextFiles:files });
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
      runtime.streamState.stream = eventSource;
      updateProgress(assistantId,'connect','Connecting to model',`${route.provider} / ${route.model}`,'active');
      armWatchdog(assistantId, eventSource);
      eventSource.onopen = () => { if (runtime.streamState.stream === eventSource) { armWatchdog(assistantId,eventSource);patch({ status:'streaming' }); appendTrace('connection', `Connected to ${route.provider}/${route.model}`);appendTurn(assistantId,{type:'model_connection',kind:'connection',text:`Connected to ${route.provider}/${route.model}`,state:'done',role:'model'});updateProgress(assistantId,'connect','Model connected',`${route.provider} / ${route.model}`,'done');updateProgress(assistantId,'draft','Drafting response',mode === 'ask'||analysisRun ? 'Streaming answer' : 'Streaming model output','active'); } };
      eventSource.addEventListener('agent_run_registered', event => { if(runtime.streamState.stream===eventSource){armWatchdog(assistantId,eventSource);const payload=eventPayload(event);runtime.streamState.runId=String(payload.run_id||'');patch({activeRunId:runtime.streamState.runId});appendTrace('run',`Durable run registered: ${runtime.streamState.runId||'unknown'}`);persist();} });
      eventSource.addEventListener('agent_run_started', event => { if(runtime.streamState.stream===eventSource){armWatchdog(assistantId,eventSource);const payload=eventPayload(event);runtime.streamState.runId=String(payload.run_id||'');patch({activeRunId:runtime.streamState.runId});const detail=payload.run_id?`Run ${String(payload.run_id).slice(-8)}`:(payload.session_id?`Session ${String(payload.session_id).slice(-6)}`:'Session ready');appendTurn(assistantId,{type:'agent_turn',kind:'run',text:`Coding run started · ${detail}`,state:'done',role:'agent',authority:'selected workspace scope'});updateProgress(assistantId,'run','Coding run started',detail,'done');persist();} });
      eventSource.addEventListener('agent_run_preflight', event => { if(runtime.streamState.stream===eventSource){armWatchdog(assistantId,eventSource);const payload=eventPayload(event);const recipes=Array.isArray(payload.recipes)?payload.recipes:[];const skipped=Array.isArray(payload.skipped_tools)?payload.skipped_tools:[];const detail=`Pathfinder ${payload.route_id||'ready'} · ${recipes.length} verified recipe(s) · ${skipped.length} optional tool(s) skipped`;appendTrace('preflight',detail);appendTurn(assistantId,{type:'tool_result',kind:'preflight',tool:'Pathfinder/SkillTree',text:detail,state:'done',role:'tool',authority:'advisory only'});updateProgress(assistantId,'preflight','Pathfinder preflight',`${recipes.length} verified recipe(s) · advisory only`,'done');} });
      eventSource.addEventListener('agent_run_context', event => { if(runtime.streamState.stream===eventSource){armWatchdog(assistantId,eventSource);const payload=eventPayload(event);const locked=Array.isArray(payload.files)?payload.files:files;const unreadable=Array.isArray(payload.unreadable_files)?payload.unreadable_files:[];const missing=files.filter(path=>!locked.includes(path));const loaded=payload.content_loaded!==false&&locked.length>0&&!missing.length;patch({contextFiles:normalizeContextFiles([...files,...locked])});const failure=[...unreadable.map(item=>`${item.path||'file'}: ${item.error||'unreadable'}`),...missing.map(path=>`${path}: not locked by backend`)].join(' · ');const detail=loaded?`Content loaded: ${locked.join(', ')}`:`Context mismatch/read failure: ${failure||'no readable file reached the run'}`;updateProgress(assistantId,'context',loaded?'Context content loaded':'Context mismatch or read failure',loaded?locked.join(' · '):failure||'No readable file reached the agent',loaded?'done':'failed');appendTrace('context',detail);appendTurn(assistantId,{type:'tool_result',kind:'context_read',tool:'Workspace File Read',text:detail,state:loaded?'done':'failed',role:'tool',authority:'selected files only'});} });
      eventSource.addEventListener('agent_run_stage', event => { if (runtime.streamState.stream === eventSource) {armWatchdog(assistantId,eventSource);const text=String(eventPayload(event).text||'Working').replaceAll('_',' ');appendTrace('stage',text);appendTurn(assistantId,{type:'agent_reasoning',kind:'stage',text,state:'active',role:'agent'});updateProgress(assistantId,'stage',text,'Agent stage','active');} });
      eventSource.addEventListener('agent_run_tool', event => { if (runtime.streamState.stream === eventSource) {armWatchdog(assistantId,eventSource);const payload=eventPayload(event);const text=String(payload.text||'Using repository tool');const turnType=payload.type||'tool_result';const turnState=payload.status==='deferred'?'failed':turnType==='tool_call'?'active':'done';appendTrace('tool',text);appendTurn(assistantId,{type:turnType,kind:payload.phase||'tool',tool:payload.tool||'BEAST governed tool',text,state:turnState,role:'tool',authority:payload.authority||'read-only/governed',evidence:payload.evidence||''});updateProgress(assistantId,'tools',turnType==='tool_call'?'Using repository tool':'Repository tool finished',`${payload.tool?`${payload.tool}: `:''}${text}`,turnState);} });
      eventSource.addEventListener('agent_run_permission_request', async event => {
        await handlePermissionRequest({ event, assistantId, eventSource });
      });
      eventSource.addEventListener('agent_run_token', event => {
        if (runtime.streamState.stream !== eventSource) return;
        armWatchdog(assistantId,eventSource);
        const text=String(eventPayload(event).text||'');rawAssistant=`${rawAssistant}${text}`.slice(-60000);
        if(mode==='ask'||analysisRun)appendAssistant(assistantId,text);
        else if(isStructuredEditStream(rawAssistant)){const draft=draftPreviewFromRaw(rawAssistant);const current=BeastStore.get().aiCoding.messages.find(message=>message.id===assistantId)||{};updateAssistant(assistantId,{content:current.narrating&&current.content?current.content:structuredDraftStatus(draft),draftPreview:draft,internalFormat:'beast.action_intent.v1'});}
        else appendAssistant(assistantId,text);
        if(now()-lastDraftProgressAt>=120){lastDraftProgressAt=now();updateProgress(assistantId,'draft',mode==='ask'||analysisRun?'Streaming answer':'Streaming model output',`${rawAssistant.length.toLocaleString()} characters received`,'active');if(mode!=='ask'&&!analysisRun)updateAssistantPreview(assistantId,draftPreviewFromRaw(rawAssistant));}
      });
      eventSource.addEventListener('agent_run_provider_done', () => { if(runtime.streamState.stream===eventSource){armWatchdog(assistantId,eventSource);patch({status:mode==='ask'||analysisRun?'finishing':'building-changes'});appendTurn(assistantId,{type:'model_output',kind:'provider',text:`Provider stream complete · ${rawAssistant.length.toLocaleString()} characters`,state:'done',role:'model',authority:analysisRun?'read-only analysis':'draft only'});if(mode!=='ask'&&!analysisRun)updateAssistantPreview(assistantId,draftPreviewFromRaw(rawAssistant));updateProgress(assistantId,'draft',mode==='ask'||analysisRun?'Answer received':'Model output received',`${rawAssistant.length.toLocaleString()} characters`,'done');updateProgress(assistantId,'compile',mode==='ask'||analysisRun?'Finalizing answer':'Compiling reviewable patch',mode==='ask'||analysisRun?'Formatting response':'Translating Action IR into safe operations','active');} });
      eventSource.addEventListener('agent_run_validation', event => {
        if(runtime.streamState.stream!==eventSource)return;armWatchdog(assistantId,eventSource);const payload=eventPayload(event);const status=String(payload.status||'checking');const verifiers=payload.isolated_verifiers||{};const approvalNeeded=verifiers.status==='approval_required';const verifierDetail=verifiers.status?` · isolated ${verifiers.status}${Number(verifiers.passed||0)?` (${Number(verifiers.passed)} passed)`:''}${Number(verifiers.skipped||0)?` · ${Number(verifiers.skipped)} skipped`:''}`:'';const detail=approvalNeeded?`Test approval needed${verifierDetail}`:`${status} · ${Number(payload.check_count||0)} checks${verifierDetail}`;patch({status:approvalNeeded?'test-approval-needed':'validating-changes'});updateProgress(assistantId,'compile','Patch compiled','Operations are bounded to attached files','done');updateProgress(assistantId,'validate',approvalNeeded?'Test approval needed':(payload.repair?'Rechecking repaired edits':'Validating proposed files'),approvalNeeded?'Approve the isolated verifier capability; BEAST will continue the governed loop when the approval reaches the run.':detail,approvalNeeded?'active':status==='passed'||status==='partial'?'done':'active');appendTrace('validation',detail);appendTurn(assistantId,{type:'verification',kind:'validation',text:detail,state:approvalNeeded?'active':status==='passed'||status==='partial'?'done':'active',role:'verifier',authority:'local syntax/sourceplan'});
        (Array.isArray(verifiers.commands)?verifiers.commands:[]).slice(0,6).forEach(item=>appendTurn(assistantId,{type:approvalNeeded?'command_request':'command_result',kind:'command',command:String(item.command||'verifier'),text:String(item.message||item.status||'verifier'),state:approvalNeeded?'active':String(item.status||'done'),role:'command',authority:'isolated temporary workspace'}));
      });
      eventSource.addEventListener('agent_run_request', event => {
        if (runtime.streamState.stream !== eventSource) return;
        armWatchdog(assistantId,eventSource);
        const payload=eventPayload(event);
        appendTrace('request', String(payload.text || payload.command || payload.query || 'Agent requested a follow-up action'));
        appendTurn(assistantId,{type:payload.type||'agent_request',kind:payload.request_type||'request',text:String(payload.text||payload.query||payload.command||'Agent requested a follow-up action'),command:String(payload.command||''),state:'active',role:'agent',authority:payload.authority||'operator approval required'});
      });
      eventSource.addEventListener('agent_run_crystal', event => { if (runtime.streamState.stream === eventSource) {armWatchdog(assistantId,eventSource);applyCrystal(eventPayload(event));} });
      eventSource.addEventListener('agent_run_compute', event => { if (runtime.streamState.stream === eventSource) {armWatchdog(assistantId,eventSource);applyCompute(eventPayload(event));} });
      eventSource.addEventListener('agent_run_scorecard', event => { if (runtime.streamState.stream === eventSource) {armWatchdog(assistantId,eventSource);const score=eventPayload(event);const lattice=score.lattice?.match_strength?` · crystal match ${Math.round(Number(score.lattice.match_strength)*100)}%`:'';const worktree=score.worktree?.recommended?' · worktree advised':'';appendTrace('review',`Scorecard: ${score.risk_level||'unknown'} risk · ${score.decision||'review'}${lattice}${worktree}`);updateProgress(assistantId,'scorecard','BEAST review scorecard',`${score.risk_level||'unknown'} risk · ${score.decision||'review'}`,'done');} });
      eventSource.addEventListener('agent_run_intelligence', event => { if (runtime.streamState.stream === eventSource) {armWatchdog(assistantId,eventSource);const data=eventPayload(event);appendTrace('intelligence',`Pathfinder + Quality Cascade ${data.quality||'completed'} · Conductor ${data.workflow||'advisory'} (${data.dispatch||'not dispatched'}) · Canon ${data.canon_valid?'valid':'review'}${data.tool_skips?` · ${data.tool_skips} optional tool(s) skipped`:''}`);updateProgress(assistantId,'intelligence','Intelligence fabric',`Quality ${data.quality||'completed'} · Canon ${data.canon_valid?'valid':'review'}`,'done');} });
      eventSource.addEventListener('agent_run_sourceplan', event => {
        if (runtime.streamState.stream !== eventSource) return;
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
        if (runtime.streamState.stream !== eventSource) return;
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
        if (runtime.streamState.stream !== eventSource) return;
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
        if (runtime.streamState.stream !== eventSource) return;
        terminalEventSeen = true;
        eventSource.close(); runtime.streamState.stream = null; runtime.streamState.runId = ''; patch({activeRunId:''}); clearWatchdog();
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
        if (runtime.streamState.stream !== eventSource) return;
        terminalEventSeen = true;
        let error = 'AI coding stream failed.';
        try { error = eventPayload(event).error || error; } catch (_) {}
        fail(error, assistantId, eventSource);
      });
      eventSource.addEventListener('error', () => {
        if (runtime.streamState.stream === eventSource && BeastStore.get().aiCoding.streaming) fail('AI coding stream disconnected.', assistantId, eventSource);
      });
      eventSource.addEventListener('end', () => {
        // Electron distinguishes a normal finite SSE close from a transport
        // error. A completed run closes itself on agent_run_done; reaching
        // here therefore means the gateway ended before a terminal result.
        if (terminalEventSeen) return;
        if (runtime.streamState.stream === eventSource && BeastStore.get().aiCoding.streaming) fail('The gateway ended the coding stream before BEAST returned a terminal result.', assistantId, eventSource);
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
    if (!eventSource || runtime.streamState.stream === eventSource) runtime.streamState.stream = null;
    runtime.streamState.runId = '';
    clearWatchdog();
    const messages = BeastStore.get().aiCoding.messages.map(message => message.id === assistantId ? { ...message, content:String(message.content||'').trim()||`The coding run stopped before it produced a safe result.\n\n${String(error||'AI coding failed.')}`, streaming:false, activity:'', error:true, progress:(message.progress||[]).map(item=>item.state==='active'?{...item,state:'failed',detail:String(error||'AI coding failed.').slice(0,240)}:item) } : message);
    patch({ streaming:false, status:'error', activeRunId:'', error:String(error || 'AI coding failed.'), messages });
    appendTrace('error', error);
    BeastMascot.setState('alert');
    persist();
  }

  function cancel() {
    const activeRunId = String(runtime.streamState.runId || BeastStore.get().aiCoding.activeRunId || '');
    if (activeRunId && root()) {
      BeastRuntime.request(`/edgek/agent-runs/${encodeURIComponent(activeRunId)}/cancel`, {
        method:'POST', timeoutMs:10000,
        body:{ root_path:root(), reason:'operator_cancelled_from_pair_programmer' }
      }).catch(error => appendTrace('cancel', `Backend cancellation acknowledgement failed: ${String(error.message || error)}`));
    }
    if (runtime.streamState.stream) { runtime.streamState.stream.close(); runtime.streamState.stream = null; }
    runtime.streamState.runId = '';
    clearWatchdog();
    if (BeastStore.get().aiCoding.streaming) {
      const messages=BeastStore.get().aiCoding.messages.map(message=>message.streaming?{...message,streaming:false,activity:'',content:String(message.content||'').trim()||'Run stopped. No files were changed.',progress:(message.progress||[]).map(item=>item.state==='active'?{...item,state:'failed',detail:'Stopped by operator'}:item)}:message);
      patch({ streaming:false, status:'cancelled', activeRunId:'', error:'Stopped by operator. No files were changed.', messages });
    } else {
      patch({ activeRunId:'' });
    }
    BeastMascot.setState('idle');
    persist();
  }

  function clear() {
    cancel();
    patch({ sessionId:'', activeRunId:'', messages:[], trace:[], status:'idle', error:'', prompt:'', selection:null, sourcePlanReady:false, sourcePlanId:'', crystal:{ action:'', source:'', confidence:0, reused:false, avoidedTokens:0, decisionId:'', recorded:false, candidate:false }, compute:{ selectedFiles:0, readableFiles:0, sourceChars:0, suppliedChars:0, truncatedFiles:0, policy:'', kvCache:'', crystal:'' } });
    persist();
  }

    return { runInWorktree, retryLastRequest, recoverInvalidPacket, continueWithAddedContext, syncModel, providerStateRoute, resolveCodingRoute, createSession, send, fail, cancel, clear };
  };
})();
