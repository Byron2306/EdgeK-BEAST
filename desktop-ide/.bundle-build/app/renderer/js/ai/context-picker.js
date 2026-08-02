// BEAST Pair Programmer renderer module: context-picker.js
(() => {
  const registry = window.BeastAICodingModules = window.BeastAICodingModules || {};
  registry.createContextPicker = runtime => {
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
  const agentContextRequests = (...args) => api.agentContextRequests(...args);
  const appendProposalTurns = (...args) => api.appendProposalTurns(...args);
  const appendTrace = (...args) => api.appendTrace(...args);
  const contextFilesFor = (...args) => api.contextFilesFor(...args);
  const patch = (...args) => api.patch(...args);
  const persist = (...args) => api.persist(...args);

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

    return { toggleContext, addActiveFile, captureSelection, removeSelection, suggestContext, acceptSuggestedContext, resolveRequestedContext };
  };
})();
