// BEAST Pair Programmer composition root.
// Behaviour lives in renderer/js/ai/*.js; this file wires the public API.
(() => {
  const registry = window.BeastAICodingModules || {};
  const requiredFactories = ['createAgentClient', 'createAgentStore', 'createAgentEvents', 'createAgentView', 'createContextPicker', 'createContextManifest', 'createApprovalCards', 'createToolCards', 'createPlanView', 'createVerificationView', 'createSourceplanHandoff', 'createConversationRenderer', 'createModeController', 'createBudgetView'];
  const missing = requiredFactories.filter(name => typeof registry[name] !== 'function');
  if (missing.length) throw new Error(`BEAST AI renderer modules missing: ${missing.join(', ')}`);

  const runtime = {
    api: {},
    streamState: { stream:null, watchdog:null, lastEventAt:0, runId:'' },
    constants: {
      MAX_CONTEXT_FILES:48,
      RELIABLE_LOCAL_CODER:'qwen2.5-coder:1.5b',
      RELIABLE_LOCAL_PROFILE:Object.freeze({ maxFiles:3, contextChars:2400, askTokens:768, editTokens:1024 })
    },
    root:() => BeastStore.get().workspace.root || '',
    gatewayUrl:() => BeastRuntime.gatewayUrl || BeastStore.get().connection.gatewayUrl || 'http://127.0.0.1:8101',
    stateKey:() => `beast.v2.ai-coding:${BeastStore.get().workspace.root || 'workspace'}`,
    now:() => Date.now(),
    openRunStream:window.BeastAITransport.openRunStream,
    parseActionIntent:window.BeastAIIntent.parseActionIntent,
    looksLikeActionIntent:window.BeastAIIntent.looksLikeActionIntent
  };

  for (const factoryName of requiredFactories) Object.assign(runtime.api, registry[factoryName](runtime));

  const publicMethods = ['restore', 'persist', 'setOpen', 'setExpanded', 'setMode', 'setPrompt', 'syncModel', 'toggleContext', 'addActiveFile', 'suggestContext', 'acceptSuggestedContext', 'resolveRequestedContext', 'captureSelection', 'removeSelection', 'send', 'runInWorktree', 'retryLastRequest', 'recoverInvalidPacket', 'continueWithAddedContext', 'cancel', 'clear', 'openSourcePlan', 'verifyRequestedChecks', 'noteSourcePlanApply'];
  window.BeastAICoding = Object.fromEntries(publicMethods.map(name => [name, (...args) => runtime.api[name](...args)]));
  window.BeastAICodingModuleManifest = Object.freeze(requiredFactories.map(name => name.replace(/^create/, '')));
  document.addEventListener('beast:agent-sourceplan-applied', event => runtime.api.noteSourcePlanApply(event));
})();
