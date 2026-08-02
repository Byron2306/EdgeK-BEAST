(() => {
  'use strict';

  // file:// renderer pages cannot reliably open a cross-origin EventSource to
  // the local gateway. Route SSE through Electron when available; browser
  // EventSource remains a useful fallback for web and visual harnesses.
  async function openRunStream(url) {
    const runtime = window.BeastRuntime;
    const desktop = runtime?.desktop || window.beastDesktop;
    if (!desktop?.gatewayStreamStart || !desktop?.onGatewayStreamMessage) return new EventSource(url);
    const target = new URL(url);
    const identityDigest = runtime?.diagnostics?.().workspaceIdentityDigest;
    const started = await desktop.gatewayStreamStart({
      path: `${target.pathname}${target.search}`,
      headers: identityDigest ? { 'X-BEAST-Workspace-Identity': identityDigest } : {},
    });
    if (!started?.ok || !started.id) throw new Error(started?.error || 'Unable to open the AI event stream.');
    const listeners = new Map();
    const dispatch = (name, event) => (listeners.get(name) || []).forEach(handler => handler(event));
    let dispose = () => {};
    const source = {
      id: started.id,
      closed: false,
      onopen: null,
      onerror: null,
      addEventListener(name, handler) {
        if (!listeners.has(name)) listeners.set(name, []);
        listeners.get(name).push(handler);
      },
      close() {
        if (source.closed) return;
        source.closed = true;
        dispose();
        desktop.gatewayStreamStop(source.id).catch(() => {});
      },
    };
    dispose = desktop.onGatewayStreamMessage(message => {
      if (!message || message.id !== source.id || source.closed) return;
      if (message.type === 'open') { source.onopen?.({}); return; }
      if (message.type === 'event') { dispatch(message.event || 'message', { data: String(message.data || ''), lastEventId:String(message.lastEventId || '') }); return; }
      if (message.type === 'end') { dispatch('end', { message: message.reason || '' }); return; }
      if (message.type === 'error') source.onerror?.({ message: message.error || 'AI coding stream disconnected.' });
    });
    return source;
  }

  window.BeastAITransport = Object.freeze({ openRunStream });
})();
