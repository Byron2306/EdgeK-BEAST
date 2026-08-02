// BEAST Pair Programmer renderer module: agent-store.js
(() => {
  const registry = window.BeastAICodingModules = window.BeastAICodingModules || {};
  registry.createAgentStore = runtime => {
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
  const normalizedRestoredMessage = (...args) => api.normalizedRestoredMessage(...args);

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

    return { patch, persist, restore };
  };
})();
