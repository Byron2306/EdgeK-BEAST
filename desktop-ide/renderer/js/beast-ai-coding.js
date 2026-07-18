// Keep the budget at module scope as well as in the Pair Programmer closure.
// This protects the normalizer when the file is evaluated by lightweight
// harnesses that extract individual helpers for testing.
const MAX_CONTEXT_FILES = 48;
const RELIABLE_LOCAL_CODER = 'qwen2.5-coder:1.5b';
const RELIABLE_LOCAL_PROFILE = Object.freeze({ maxFiles:3, contextChars:2400, askTokens:768, editTokens:1024 });

(() => {
  let stream = null;
  let streamWatchdog = null;
  const root = () => BeastStore.get().workspace.root || '';
  const gatewayUrl = () => BeastRuntime.gatewayUrl || BeastStore.get().connection.gatewayUrl || 'http://127.0.0.1:8101';
  const stateKey = () => `beast.v2.ai-coding:${root() || 'workspace'}`;
  const now = () => Date.now();

  // file:// renderer pages cannot reliably open a cross-origin EventSource to
  // the local gateway. Route SSE through Electron when available; browser
  // EventSource remains a useful fallback for the web/dev harness.
  async function openRunStream(url) {
    const desktop = BeastRuntime?.desktop || window.beastDesktop;
    if (!desktop?.gatewayStreamStart || !desktop?.onGatewayStreamMessage) return new EventSource(url);
    const target = new URL(url);
    const started = await desktop.gatewayStreamStart({
      path: `${target.pathname}${target.search}`,
      headers: BeastRuntime?.diagnostics?.().workspaceIdentityDigest ? { 'X-BEAST-Workspace-Identity': BeastRuntime.diagnostics().workspaceIdentityDigest } : {}
    });
    if (!started?.ok || !started.id) throw new Error(started?.error || 'Unable to open the AI event stream.');
    const listeners = new Map();
    const dispatch = (name, event) => (listeners.get(name) || []).forEach(handler => handler(event));
    const source = {
      id: started.id, closed: false, onopen: null, onerror: null,
      addEventListener(name, handler) { if (!listeners.has(name)) listeners.set(name, []); listeners.get(name).push(handler); },
      close() { if (source.closed) return; source.closed = true; dispose(); desktop.gatewayStreamStop(source.id).catch(() => {}); }
    };
    const dispose = desktop.onGatewayStreamMessage(message => {
      if (!message || message.id !== source.id || source.closed) return;
      if (message.type === 'open') { source.onopen?.({}); return; }
      if (message.type === 'event') { dispatch(message.event || 'message', { data: String(message.data || '') }); return; }
      if (message.type === 'error' || message.type === 'end') source.onerror?.({ message: message.error || 'AI coding stream disconnected.' });
    });
    return source;
  }

  function parseActionIntent(value) {
    let body = String(value || '').trim();
    const fence = body.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
    if (fence) body = fence[1].trim();
    const start = body.indexOf('{'); const end = body.lastIndexOf('}');
    if (start < 0 || end <= start) return null;
    try {
      const parsed = JSON.parse(body.slice(start, end + 1));
      return parsed && (parsed.kind === 'beast.action_intent.v1' || Array.isArray(parsed.actions)) ? parsed : null;
    } catch (_) { return null; }
  }

  function draftPreviewFromRaw(value) {
    const raw=String(value||'');const decode=value=>{try{return JSON.parse(`"${value}"`);}catch(_){return value.replaceAll('\\n',' ');}};
    const collect=key=>{const values=[];const pattern=new RegExp(`"${key}"\\s*:\\s*"((?:\\\\.|[^"\\\\])*)"`,'g');let match;while((match=pattern.exec(raw))&&values.length<8)values.push(decode(match[1]));return values;};
    const files=[...new Set(collect('path').filter(Boolean))];const intents=collect('intent').filter(Boolean);const actions=(raw.match(/"(?:type|op)"\s*:/g)||[]).length;
    return { chars:raw.length, files, intents, actions };
  }

  function proposalFromActions(actions = [], ready = false, planId = '', validation = {}) {
    const operations = actions.slice(0, 50).map((action, index) => ({
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
    const next = proposal.ready
      ? 'The files have not been written yet. Review the diff, then apply the governed SourcePlan when it looks right.'
      : 'The response could not be compiled into a safe patch. Refine the request or attach the exact file and selection, then retry.';
    return [headline, objective ? String(objective).trim() : '', details, validation, next].filter(Boolean).join('\n\n');
  }

  function normalizedRestoredMessage(message, sourcePlanReady, sourcePlanId) {
    const next = { ...message, streaming:false };
    const intent = message?.role === 'assistant' ? parseActionIntent(message.content) : null;
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
      provider: state.provider,
      model: state.model,
      crystal: state.crystal,
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
    patch({
      open: Boolean(payload.open),
      expanded: Boolean(payload.expanded),
      mode: ['ask','edit','agent'].includes(payload.mode) ? payload.mode : 'agent',
      sessionId: String(payload.sessionId || ''),
      messages: storedMessages.map(message => normalizedRestoredMessage(message, Boolean(payload.sourcePlanReady), String(payload.sourcePlanId || ''))),
      trace: Array.isArray(payload.trace) ? payload.trace.slice(-80) : [],
      contextFiles: Array.isArray(payload.contextFiles) ? payload.contextFiles.slice(0,16) : [],
      provider: String(payload.provider || BeastStore.get().models.provider || localStorage.getItem('beast.provider') || ''),
      model: String(payload.model || BeastStore.get().models.selectedId || BeastStore.get().models.active || localStorage.getItem('beast.model') || ''),
      crystal: payload.crystal && typeof payload.crystal === 'object' ? payload.crystal : BeastStore.get().aiCoding.crystal,
      sourcePlanReady: Boolean(payload.sourcePlanReady),
      sourcePlanId: String(payload.sourcePlanId || ''),
      streaming: false,
      status: interrupted ? 'interrupted' : payload.sessionId ? 'ready' : 'idle',
      error: interrupted ? 'The previous run was interrupted. Your conversation was kept; send again to retry.' : ''
    });
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
    appendTrace('retry', 'Retrying the last request with the retained locked context.');
    return send(String(previous.content), options);
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

  function clearWatchdog() { if (streamWatchdog) clearTimeout(streamWatchdog); streamWatchdog = null; }
  function armWatchdog(assistantId, eventSource) {
    clearWatchdog();
    streamWatchdog = setTimeout(() => {
      if (stream === eventSource && BeastStore.get().aiCoding.streaming) fail('The coding run stopped producing events. Retry the request or choose another model.', assistantId, eventSource);
    }, 180000);
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

  function resolvedModeForPrompt(mode,prompt) {
    if(mode==='ask')return mode;const text=String(prompt||'').trim().toLowerCase();
    const advisory=/^(?:explain|analy[sz]e|review|describe|summari[sz]e|what\b|how\b|why\b|give me (?:an )?(?:assessment|overview)|look (?:at|over)\b|suggest(?:ions)?\b)/.test(text);
    const explicitMutation=/\b(?:implement|apply|make (?:the|these|a) changes?|edit|fix|refactor|add|remove|rename|update|create|write|modify|change)\b/.test(text);
    return advisory&&!explicitMutation?'ask':mode;
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
    const actionRules = `\n\nReturn BEAST Action IR JSON only after inspecting the attached files. Use this exact shape:\n{"kind":"beast.action_intent.v1","objective":"...","actions":[{"type":"replace_exact","target":{"path":"relative/file"},"old":"exact current snippet","new":"replacement","intent":"why"}],"verify":["relevant test or check"]}\nUse only attached files and copy old snippets exactly. ${compactLocal ? 'For the local Qwen route, emit at most three replace_exact actions and only lightweight syntax checks. ' : 'Emit every necessary file edit as its own action—do not stop after a single edit when the task needs coordinated changes. Keep scope tight, but make the implementation complete. If multiple files are attached because the feature crosses UI, runtime, tests, and docs, produce a coordinated multi-file patch instead of a tiny isolated edit. '}Do not include markdown or prose outside the JSON.`;
    if (mode === 'edit') return `${prompt}\n\nEdit scope:\n${scope}${selected}${actionRules}`;
    return `Act as an autonomous coding agent. Investigate the attached workspace context, implement the requested change as a governed patch, account for dependencies and tests, and keep the change minimal.\n\nTask: ${prompt}\n\nAllowed files:\n${scope}${selected}${actionRules}`;
  }

  async function createSession(prompt, files, model, provider) {
    const mode = BeastStore.get().aiCoding.mode === 'ask' ? 'chat' : 'editor_agent';
    const payload = await BeastRuntime.request('/edgek/ide/agent-sessions/create', {
      method:'POST', timeoutMs:12000,
      body:{
        root_path:root(), objective:prompt, mode, provider, model, files,
        tools:['Code Cortex','Workspace Context','Crystal Reuse','SourcePlan','Evidence'],
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
    patch({ sourcePlanReady:true, sourcePlanId:String(normalized.plan_id || '') });
    if (typeof document !== 'undefined' && typeof CustomEvent === 'function') document.dispatchEvent(new CustomEvent('beast:ai-proposal-ready', { detail:{ plan:normalized } }));
    persist();
    return proposalFromActions(normalized.operations, true, normalized.plan_id || '', normalized.validation || {});
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
      recorded:Boolean(Object.keys(record).length)
    };
    patch({ crystal });
    appendTrace('crystal', crystal.reused
      ? `Reused ${crystal.source || 'crystal'} · ${crystal.avoidedTokens} tokens avoided`
      : `${crystal.action || 'reuse preflight'} · ${crystal.source || 'local execution'}`);
    persist();
  }

  async function send(prompt, options = {}) {
    const clean = String(prompt || BeastStore.get().aiCoding.prompt || '').trim();
    if (!clean) throw new Error('Describe the coding task first.');
    if (BeastStore.get().aiCoding.streaming) throw new Error('The current AI turn is still running.');
    const selection = BeastStore.get().aiCoding.selection;
    const route = syncModel(options.model || BeastStore.get().aiCoding.model);
    if (!route.model || !route.provider) throw new Error('Select a ready model and provider before running AI coding.');
    const localCoder = /^(?:ollama|local_ollama)$/i.test(route.provider) && route.model === RELIABLE_LOCAL_CODER;
    let files = localCoder
      ? contextFilesFor(clean)
      : await expandContext(clean, contextFilesFor(clean));
    const selectedMode=BeastStore.get().aiCoding.mode;const mode=resolvedModeForPrompt(selectedMode,clean);
    if (localCoder && files.length > RELIABLE_LOCAL_PROFILE.maxFiles) {
      files = files.slice(0, RELIABLE_LOCAL_PROFILE.maxFiles);
      appendTrace('routing', `Local coding context bounded to ${RELIABLE_LOCAL_PROFILE.maxFiles} files for responsive CPU inference.`);
    }
    if(mode!==selectedMode){patch({mode,sessionId:'',status:'routing',error:''});appendTrace('routing',`Advisory request routed to Ask mode; ${files.length} selected file(s) retained.`);}
    if(mode!=='ask'&&!files.length)throw new Error('Edit and Agent modes require an open or attached workspace file. Open the target file, then retry.');
    const runPrompt = instructionFor(mode, clean, files, selection, localCoder);
    addMessage('user', clean, { mode, files, selection:selection ? { path:selection.path, range:selection.range } : null });
    const assistantId = addMessage('assistant', '', {
      streaming:true, mode, activity:mode === 'ask' ? 'Thinking…' : 'Inspecting files…',
      progress:[{ phase:'context', label:'Context gathered', detail:`${files.length} file${files.length === 1 ? '' : 's'} in scope`, state:'done', at:now() }]
    });
    patch({ streaming:true, status:'creating', error:'', prompt:'', sourcePlanReady:false, sourcePlanId:'', contextFiles:files });
    let sessionId = BeastStore.get().aiCoding.sessionId;
    let proposalReady = false;
    let needsOperator = false;
    let rawAssistant = '';
    let lastDraftProgressAt = 0;
    try {
      if (!sessionId) sessionId = await createSession(clean, files, route.model, route.provider);
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
      eventSource.onopen = () => { if (stream === eventSource) { armWatchdog(assistantId,eventSource);patch({ status:'streaming' }); appendTrace('connection', `Connected to ${route.provider}/${route.model}`);updateProgress(assistantId,'connect','Model connected',`${route.provider} / ${route.model}`,'done');updateProgress(assistantId,'draft','Drafting response',mode === 'ask' ? 'Streaming answer' : 'Preparing governed edits','active'); } };
      eventSource.addEventListener('agent_run_started', event => { if(stream===eventSource){armWatchdog(assistantId,eventSource);const payload=eventPayload(event);updateProgress(assistantId,'run','Coding run started',payload.session_id?`Session ${String(payload.session_id).slice(-6)}`:'Session ready','done');} });
      eventSource.addEventListener('agent_run_context', event => { if(stream===eventSource){armWatchdog(assistantId,eventSource);const payload=eventPayload(event);const locked=Array.isArray(payload.files)?payload.files:files;const unreadable=Array.isArray(payload.unreadable_files)?payload.unreadable_files:[];const missing=files.filter(path=>!locked.includes(path));const loaded=payload.content_loaded!==false&&locked.length>0&&!missing.length;patch({contextFiles:normalizeContextFiles([...files,...locked])});const failure=[...unreadable.map(item=>`${item.path||'file'}: ${item.error||'unreadable'}`),...missing.map(path=>`${path}: not locked by backend`)].join(' · ');updateProgress(assistantId,'context',loaded?'Context content loaded':'Context mismatch or read failure',loaded?locked.join(' · '):failure||'No readable file reached the agent',loaded?'done':'failed');appendTrace('context',loaded?`Content loaded: ${locked.join(', ')}`:`Context mismatch/read failure: ${failure||'no readable file reached the run'}`);} });
      eventSource.addEventListener('agent_run_stage', event => { if (stream === eventSource) {armWatchdog(assistantId,eventSource);const text=String(eventPayload(event).text||'Working').replaceAll('_',' ');appendTrace('stage',text);updateProgress(assistantId,'stage',text,'Agent stage','active');} });
      eventSource.addEventListener('agent_run_tool', event => { if (stream === eventSource) {armWatchdog(assistantId,eventSource);const text=String(eventPayload(event).text||'Using repository tool');appendTrace('tool',text);updateProgress(assistantId,'tools','Inspecting repository',text,'active');} });
      eventSource.addEventListener('agent_run_token', event => {
        if (stream !== eventSource) return;
        armWatchdog(assistantId,eventSource);
        const text=String(eventPayload(event).text||'');rawAssistant=`${rawAssistant}${text}`.slice(-60000);
        if(mode==='ask')appendAssistant(assistantId,text);
        if(now()-lastDraftProgressAt>=120){lastDraftProgressAt=now();updateProgress(assistantId,'draft',mode==='ask'?'Streaming answer':'Drafting governed edits',`${rawAssistant.length.toLocaleString()} characters received`,'active');if(mode!=='ask')updateAssistantPreview(assistantId,draftPreviewFromRaw(rawAssistant));}
      });
      eventSource.addEventListener('agent_run_provider_done', () => { if(stream===eventSource){armWatchdog(assistantId,eventSource);patch({status:mode==='ask'?'finishing':'building-changes'});if(mode!=='ask')updateAssistantPreview(assistantId,draftPreviewFromRaw(rawAssistant));updateProgress(assistantId,'draft',mode==='ask'?'Answer received':'Edit draft received',`${rawAssistant.length.toLocaleString()} characters`,'done');updateProgress(assistantId,'compile',mode==='ask'?'Finalizing answer':'Compiling reviewable patch',mode==='ask'?'Formatting response':'Translating Action IR into safe operations','active');} });
      eventSource.addEventListener('agent_run_validation', event => {
        if(stream!==eventSource)return;armWatchdog(assistantId,eventSource);const payload=eventPayload(event);const status=String(payload.status||'checking');const verifiers=payload.isolated_verifiers||{};const verifierDetail=verifiers.status?` · isolated ${verifiers.status}${Number(verifiers.passed||0)?` (${Number(verifiers.passed)} passed)`:''}${Number(verifiers.skipped||0)?` · ${Number(verifiers.skipped)} skipped`:''}`:'';patch({status:'validating-changes'});updateProgress(assistantId,'compile','Patch compiled','Operations are bounded to attached files','done');updateProgress(assistantId,'validate',payload.repair?'Rechecking repaired edits':'Validating proposed files',`${status} · ${Number(payload.check_count||0)} checks${verifierDetail}`,status==='passed'||status==='partial'?'done':'active');appendTrace('validation',`${status} · ${Number(payload.check_count||0)} checks${verifierDetail}`);
      });
      eventSource.addEventListener('agent_run_crystal', event => { if (stream === eventSource) {armWatchdog(assistantId,eventSource);applyCrystal(eventPayload(event));} });
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
      });
      eventSource.addEventListener('agent_run_needs_operator', event => {
        if (stream !== eventSource) return;
        armWatchdog(assistantId,eventSource);
        const payload = eventPayload(event);
        needsOperator = true;
        const reason=String(payload.error || 'The model response could not be translated into a safe patch.');
        const intent=parseActionIntent(rawAssistant);const proposal=intent?proposalFromActions(intent.actions||[],false,''):null;
        const returned=String(payload.assistant_text||rawAssistant||'').trim();const readable=returned&&!/^[\s`]*[\[{]/.test(returned)?returned:'';
        const failureCopy=readable?`The agent inspected the selected file but returned advice instead of reviewable edits. No file was changed.\n\n${readable}\n\nPatch compiler: ${reason}`:`I could not safely turn the model response into file edits. No file was changed.\n\nPatch compiler: ${reason}\n\nThe selected file remained attached; retry Edit/Agent or select the exact code range.`;
        updateAssistant(assistantId,{ content:proposal?proposalSummary(proposal,intent.objective):failureCopy, proposal, draftPreview:draftPreviewFromRaw(returned), activity:'Needs your input', error:true, internalFormat:intent?'beast.action_intent.v1':'' });
        patch({ status:'review-needed', error:reason });
        appendTrace('review', payload.error || 'Operator translation required');
      });
      eventSource.addEventListener('agent_run_done', event => {
        if (stream !== eventSource) return;
        eventSource.close(); stream = null; clearWatchdog();
        const payload = eventPayload(event);
        const recoveredPlan=payload.session?.output?.sourceplan_plan;
        if(!proposalReady&&recoveredPlan?.operations?.length){const proposal=stageSourcePlan(recoveredPlan);proposalReady=Boolean(proposal?.ready);if(proposal)updateAssistant(assistantId,{content:proposalSummary(proposal,recoveredPlan.objective),proposal,internalFormat:'beast.action_intent.v1'});}
        const current=BeastStore.get().aiCoding.messages.find(message=>message.id===assistantId);
        let fallback='';
        if(mode==='ask'&&!String(current?.content||'').trim())fallback='I did not receive a text response from the selected model. Try again or choose another model.';
        if(mode!=='ask'&&!proposalReady&&!needsOperator)fallback=`I finished investigating, but no safe patch was produced. The locked context was kept (${files.join(', ') || 'no files'}). Retry with the exact selection or ask for a smaller governed patch.`;
        finishProgress(assistantId,fallback?'Stopped before a safe result was produced':'Run complete');
        updateAssistant(assistantId,{ streaming:false, activity:'', ...(fallback?{content:fallback,error:true}:{}) });
        patch({ streaming:false, status:proposalReady?'ready-to-review':needsOperator||fallback?'review-needed':'complete', error:needsOperator?BeastStore.get().aiCoding.error:fallback });
        appendTrace('complete', payload.sourceplan_status || 'complete');
        BeastStore.addLedger(`AI coding turn complete: ${clean.slice(0,80)}`);
        BeastMascot.setState('finished');
        persist();
      });
      eventSource.addEventListener('agent_run_error', event => {
        if (stream !== eventSource) return;
        let error = 'AI coding stream failed.';
        try { error = eventPayload(event).error || error; } catch (_) {}
        fail(error, assistantId, eventSource);
      });
      eventSource.addEventListener('error', () => {
        if (stream === eventSource && BeastStore.get().aiCoding.streaming) fail('AI coding stream disconnected.', assistantId, eventSource);
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
    patch({ sessionId:'', messages:[], trace:[], status:'idle', error:'', prompt:'', selection:null, sourcePlanReady:false, sourcePlanId:'', crystal:{ action:'', source:'', confidence:0, reused:false, avoidedTokens:0, decisionId:'', recorded:false } });
    persist();
  }

  async function openSourcePlan() {
    if (!BeastStore.get().aiCoding.sourcePlanReady) throw new Error('No AI SourcePlan is ready yet.');
    await BeastRouter.navigate('source');
  }

  window.BeastAICoding = {
    restore, persist, setOpen, setExpanded, setMode, setPrompt, syncModel, toggleContext, addActiveFile,
    captureSelection, removeSelection, send, runInWorktree, retryLastRequest, cancel, clear, openSourcePlan
  };
})();
