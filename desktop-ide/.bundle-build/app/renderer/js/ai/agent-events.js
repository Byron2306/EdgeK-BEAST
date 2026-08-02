// BEAST Pair Programmer renderer module: agent-events.js
(() => {
  const registry = window.BeastAICodingModules = window.BeastAICodingModules || {};
  registry.createAgentEvents = runtime => {
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
  const fail = (...args) => api.fail(...args);
  const patch = (...args) => api.patch(...args);

  function appendTrace(kind, text) {
    const clean = String(text || '').trim();
    if (!clean) return;
    const trace = [...BeastStore.get().aiCoding.trace, { id:`trace-${now()}-${Math.random()}`, kind, text:clean, at:now() }].slice(-80);
    patch({ trace });
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

  function clearWatchdog() { if (runtime.streamState.watchdog) clearTimeout(runtime.streamState.watchdog); runtime.streamState.watchdog = null; runtime.streamState.lastEventAt = 0; }

  function armWatchdog(assistantId, eventSource) {
    clearWatchdog();
    runtime.streamState.lastEventAt = now();
    const watch = () => {
      if (runtime.streamState.stream !== eventSource || !BeastStore.get().aiCoding.streaming) return;
      const silentFor = now() - runtime.streamState.lastEventAt;
      if (silentFor >= 300000) {
        fail('The coding run stopped producing events for five minutes. Retry the request or choose another model.', assistantId, eventSource);
        return;
      }
      updateProgress(assistantId, 'waiting', 'Still working', `No provider event for ${Math.max(1, Math.round(silentFor / 1000))} seconds · keeping the governed run active`, 'active');
      appendTrace('waiting', `Provider/verification work continues (${Math.max(1, Math.round(silentFor / 1000))}s without an event)`);
      runtime.streamState.watchdog = setTimeout(watch, 15000);
    };
    runtime.streamState.watchdog = setTimeout(watch, 15000);
  }

  function eventPayload(event) {
    const sequence = Number(event?.lastEventId || 0);
    if (Number.isFinite(sequence) && sequence > Number(runtime.streamState.sequence || 0)) {
      runtime.streamState.sequence = sequence;
      patch({ activeRunSequence:sequence });
      const stamp = now();
      if (sequence % 10 === 0 || stamp - Number(runtime.streamState.lastCursorPersistAt || 0) >= 1000) {
        runtime.streamState.lastCursorPersistAt = stamp;
        if (typeof api.persist === 'function') api.persist();
      }
    }
    const parsed = JSON.parse(event.data || '{}');
    return parsed && typeof parsed.payload === 'object' ? parsed.payload : parsed;
  }

    return { appendTrace, updateProgress, finishProgress, clearWatchdog, armWatchdog, eventPayload };
  };
})();
