// BEAST Pair Programmer renderer module: budget-view.js
(() => {
  const registry = window.BeastAICodingModules = window.BeastAICodingModules || {};
  registry.createBudgetView = runtime => {
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

    return { applyCrystal, applyCompute };
  };
})();
