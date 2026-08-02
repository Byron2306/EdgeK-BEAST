// BEAST Pair Programmer renderer module: agent-view.js
(() => {
  const registry = window.BeastAICodingModules = window.BeastAICodingModules || {};
  registry.createAgentView = runtime => {
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
  const patch = (...args) => api.patch(...args);
  const persist = (...args) => api.persist(...args);

  function setOpen(open = true) { patch({ open: Boolean(open) }); persist(); }

  function setExpanded(expanded = true) { patch({ expanded:Boolean(expanded) }); persist(); }

  function setPrompt(prompt) { patch({ prompt:String(prompt || '') }); }

    return { setOpen, setExpanded, setPrompt };
  };
})();
