// BEAST Pair Programmer renderer module: context-manifest.js
(() => {
  const registry = window.BeastAICodingModules = window.BeastAICodingModules || {};
  registry.createContextManifest = runtime => {
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

  function agentContextRequests(plan) {
    const requests = Array.isArray(plan?.non_mutating_requests) ? plan.non_mutating_requests : [];
    const actions = Array.isArray(plan?.action_ir?.actions) ? plan.action_ir.actions : [];
    return [...requests, ...actions].filter(item => item && String(item.type || item.op || '') === 'ask_for_context');
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

    return { mentionedFiles, normalizeContextFiles, contextFilesFor, agentContextRequests, expandContext };
  };
})();
