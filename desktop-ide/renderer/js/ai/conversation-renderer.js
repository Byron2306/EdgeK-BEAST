// BEAST Pair Programmer renderer module: conversation-renderer.js
(() => {
  const registry = window.BeastAICodingModules = window.BeastAICodingModules || {};
  registry.createConversationRenderer = runtime => {
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
  const narrationFromTurn = (...args) => api.narrationFromTurn(...args);
  const patch = (...args) => api.patch(...args);
  const persist = (...args) => api.persist(...args);

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
          detail:String(payload.detail || ''),
          provider:String(payload.provider || ''),
          from:String(payload.from || ''),
          to:String(payload.to || ''),
          reason:String(payload.reason || ''),
          execution_target:String(payload.execution_target || ''),
          target_execution:String(payload.target_execution || ''),
          repair_cycle:Number(payload.repair_cycle || payload.repair_round || 0),
          failure_analysis:payload.failure_analysis && typeof payload.failure_analysis === 'object' ? payload.failure_analysis : null,
          validation_strategy:payload.validation_strategy && typeof payload.validation_strategy === 'object' ? payload.validation_strategy : null,
          prior_failure:payload.prior_failure && typeof payload.prior_failure === 'object' ? payload.prior_failure : null,
          route:payload.route && typeof payload.route === 'object' ? payload.route : null,
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
        detail:String(item.detail || ''),
        provider:String(item.provider || ''),
        from:String(item.from || ''),
        to:String(item.to || ''),
        reason:String(item.reason || ''),
        execution_target:String(item.execution_target || ''),
        target_execution:String(item.target_execution || ''),
        repair_cycle:Number(item.repair_cycle || item.repair_round || 0),
        failure_analysis:item.failure_analysis && typeof item.failure_analysis === 'object' ? item.failure_analysis : null,
        validation_strategy:item.validation_strategy && typeof item.validation_strategy === 'object' ? item.validation_strategy : null,
        prior_failure:item.prior_failure && typeof item.prior_failure === 'object' ? item.prior_failure : null,
        route:item.route && typeof item.route === 'object' ? item.route : null,
        at:now()
      }));
      return { ...message, ...values, turns:[...turns, ...normalized].slice(-80) };
    });
    patch({ messages:patched });
  }

    return { addMessage, appendAssistant, appendTurn, updateAssistant, updateAssistantPreview, appendProposalTurns };
  };
})();
