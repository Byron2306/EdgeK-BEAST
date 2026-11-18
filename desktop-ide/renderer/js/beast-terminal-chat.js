/* Terminal chat: a real streamed agent turn inside Terminal Nexus.
 *
 * Uses the existing session run-events SSE endpoint through
 * BeastAITransport.openRunStream, so the Electron main process owns the stream
 * when available.  Output and trace are separate: the model text goes to
 * .terminal-chat-output, and every lifecycle/tool event is receipted in
 * .terminal-chat-trace with its event name and sequence.
 *
 * Maturity controls: start, stop, clear, copy, replay of the last prompt, and an
 * explicit simulate toggle.  Nothing is fabricated: if the gateway is
 * unreachable the trace records the error and the output stays empty.
 */
(() => {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));

  const TEXT_EVENTS = new Set([
    'message', 'agent_run_token', 'agent_run_delta', 'agent_run_text',
    'assistant_delta', 'token', 'delta', 'content',
  ]);
  const TERMINAL_EVENTS = new Set(['end', 'agent_run_completed', 'agent_run_finished', 'done']);

  function payloadOf(event) {
    try {
      const parsed = JSON.parse(String(event?.data || '{}'));
      if (!parsed || typeof parsed !== 'object') return {};
      // beast_ide_event wraps the useful fields: {event_type, payload:{...}}.
      // Unwrap so token text and error messages are actually found.
      if (parsed.payload && typeof parsed.payload === 'object') {
        return { event_type: parsed.event_type, ...parsed.payload };
      }
      return parsed;
    } catch (_) {
      return { text: String(event?.data || '') };
    }
  }

  function textOf(payload) {
    for (const key of ['delta', 'token', 'text', 'content', 'chunk']) {
      const value = payload[key];
      if (typeof value === 'string' && value) return value;
      if (value && typeof value === 'object' && typeof value.text === 'string') return value.text;
    }
    return '';
  }

  function mount(container) {
    if (!container) return { dispose() {} };
    container.innerHTML = `
      <section class="beast-card wide terminal-chat-card">
        <header class="beast-panel-head"><div>
          <h3>Agent Chat Stream</h3>
          <span>Governed session run-events · receipted per event</span>
        </div><span class="beast-pill" data-chat-state>IDLE</span></header>
        <div class="terminal-command-controls">
          <label class="terminal-command-field"><span>PROMPT</span>
            <input data-chat-prompt spellcheck="false" placeholder="Summarize the physical plane ledger contract"></label>
          <button class="terminal-icon-button execute" data-chat-action="start" title="Start chat stream">▶</button>
          <button class="terminal-icon-button cancel" data-chat-action="stop" title="Stop chat stream">■</button>
        </div>
        <div class="terminal-meta-controls">
          <label><span>MODEL</span><input data-chat-model spellcheck="false" placeholder="qwen2.5-coder:7b"></label>
          <label><span>PROVIDER</span><input data-chat-provider spellcheck="false" value="ollama"></label>
          <label><span>MAX TOKENS</span><select data-chat-max-tokens><option>512</option><option selected>1024</option><option>2048</option></select></label>
          <label class="beast-checkbox"><input type="checkbox" data-chat-simulate> Simulate</label>
        </div>
        <div class="terminal-quick-row">
          <button data-chat-action="replay">Replay Last</button>
          <button data-chat-action="clear">Clear</button>
          <button data-chat-action="copy">Copy Output</button>
          <button data-chat-action="refresh-models">Use Active Model</button>
        </div>
        <pre class="terminal-chat-output" data-chat-output aria-live="polite"></pre>
        <div class="terminal-chat-trace" data-chat-trace></div>
      </section>`;

    const q = sel => container.querySelector(sel);
    let stream = null;
    let disposed = false;
    let lastPrompt = '';
    let sequence = 0;

    function setState(value) { q('[data-chat-state]').textContent = value; }

    function trace(kind, detail) {
      const row = document.createElement('div');
      row.className = 'fabric-trace-row';
      row.innerHTML = `<span>${++sequence}</span><b>${esc(kind)}</b><em>${esc(String(detail || '').slice(0, 240))}</em>`;
      q('[data-chat-trace]').appendChild(row);
      q('[data-chat-trace]').scrollTop = q('[data-chat-trace]').scrollHeight;
    }

    function appendOutput(text) {
      const node = q('[data-chat-output]');
      node.textContent = (node.textContent + text).slice(-60000);
      node.scrollTop = node.scrollHeight;
    }

    function stop(reason = 'stopped by operator') {
      if (stream) { try { stream.close(); } catch (_) {} stream = null; }
      if (!disposed) { setState('IDLE'); trace('stop', reason); }
    }

    async function startChat() {
      if (stream) { trace('refused', 'a chat stream is already active'); return; }
      const prompt = q('[data-chat-prompt]').value.trim();
      if (!prompt) { trace('refused', 'prompt is empty'); return; }
      lastPrompt = prompt;
      const state = BeastStore.get();
      const gateway = state.connection?.gatewayUrl || window.BeastRuntime?.gatewayUrl || 'http://127.0.0.1:8101';
      const model = q('[data-chat-model]').value.trim() || state.models?.activeModel || '';
      const provider = q('[data-chat-provider]').value.trim() || 'ollama';
      const simulate = q('[data-chat-simulate]').checked;
      if (!model && !simulate) { trace('refused', 'select a model, or enable Simulate'); return; }
      const rootPath = state.workspace?.root || '';
      let sessionId = '';
      try {
        // run-events only serves a session the gateway already knows about, so
        // create a real governed session first instead of inventing an id.
        const created = await window.BeastRuntime.request('/edgek/ide/agent-sessions/create', {
          method: 'POST',
          timeoutMs: 20000,
          body: {
            objective: prompt.slice(0, 400),
            mode: 'architect',
            provider,
            model,
            root_path: rootPath,
            tools: [],
            files: [],
          },
        });
        sessionId = String(created?.session?.session_id || created?.session_id || created?.session?.id || created?.id || '');
      } catch (error) {
        setState('ERROR');
        trace('session_create_failed', String(error?.message || error));
        return;
      }
      if (!sessionId) { setState('ERROR'); trace('session_create_failed', 'gateway returned no session_id'); return; }
      const params = new URLSearchParams({
        prompt,
        provider,
        model,
        simulate: String(simulate),
        max_tokens: q('[data-chat-max-tokens]').value,
      });
      if (rootPath) params.set('root_path', rootPath);
      const url = `${String(gateway).replace(/\/$/, '')}/edgek/ide/agent-sessions/${sessionId}/run-events?${params}`;

      q('[data-chat-output]').textContent = '';
      setState(simulate ? 'SIMULATING' : 'STREAMING');
      trace('start', `${provider}/${model || 'simulated'} · ${sessionId}`);
      try {
        stream = await window.BeastAITransport.openRunStream(url);
      } catch (error) {
        stream = null;
        setState('ERROR');
        trace('open_failed', String(error?.message || error));
        return;
      }
      const active = stream;
      active.onopen = () => { if (!disposed) trace('open', 'stream connected'); };
      active.onerror = event => {
        if (disposed) return;
        setState('ERROR');
        trace('error', event?.message || 'stream error');
      };
      const onEvent = name => event => {
        if (disposed || stream !== active) return;
        const payload = payloadOf(event);
        const text = textOf(payload);
        if (text && (TEXT_EVENTS.has(name) || name === 'message')) appendOutput(text);
        else if (name !== 'message') trace(name, payload.error || payload.detail || payload.summary || payload.status || payload.message || text || event.lastEventId || JSON.stringify(payload).slice(0, 200));
        if (TERMINAL_EVENTS.has(name)) stop(name);
      };
      // Named lifecycle events plus the default message channel.
      [
        'message', 'agent_run_started', 'agent_run_context', 'agent_run_preflight',
        'agent_run_token', 'agent_run_delta', 'agent_run_text', 'agent_run_completed',
        'agent_run_error', 'agent_run_integration', 'end', 'done',
      ].forEach(name => active.addEventListener(name, onEvent(name)));
    }

    container.addEventListener('click', async event => {
      const action = event.target.closest('[data-chat-action]')?.dataset.chatAction;
      if (!action) return;
      try {
        if (action === 'start') await startChat();
        if (action === 'stop') stop();
        if (action === 'replay') { q('[data-chat-prompt]').value = lastPrompt; await startChat(); }
        if (action === 'clear') { q('[data-chat-output]').textContent = ''; q('[data-chat-trace]').innerHTML = ''; sequence = 0; setState('IDLE'); }
        if (action === 'copy') await navigator.clipboard.writeText(q('[data-chat-output]').textContent);
        if (action === 'refresh-models') {
          const state = BeastStore.get();
          q('[data-chat-model]').value = state.models?.activeModel || state.models?.selectedModel || '';
          q('[data-chat-provider]').value = state.models?.activeProvider || 'ollama';
          trace('model', q('[data-chat-model]').value || 'no active model reported');
        }
      } catch (error) {
        trace('error', String(error?.message || error));
      }
    });
    container.addEventListener('keydown', event => {
      if (event.key === 'Enter' && event.target.matches('[data-chat-prompt]')) {
        event.preventDefault();
        startChat();
      }
    });

    return {
      startChat,
      stop,
      dispose() { disposed = true; stop('chat surface disposed'); },
    };
  }

  window.BeastTerminalChat = { mount };
})();
