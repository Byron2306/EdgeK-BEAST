'use strict';

const http = require('http');

class GatewayEventStreamHost {
  constructor({ gatewayUrl }) {
    if (typeof gatewayUrl !== 'function') throw new TypeError('gatewayUrl resolver is required');
    this.gatewayUrl = gatewayUrl;
    this.sessions = new Map();
    this.sequence = 0;
  }

  start(payload = {}, sender) {
    let target;
    try {
      const base = new URL(this.gatewayUrl());
      target = new URL(payload.path || payload.url || '/', base);
      if (target.origin !== base.origin || !['127.0.0.1', '::1', 'localhost'].includes(target.hostname)) throw new Error('gateway stream escaped the active loopback origin');
    } catch (error) { throw new Error(String(error.message || error)); }
    if (String(payload.method || 'GET').toUpperCase() !== 'GET') throw new Error('gateway event streams only support GET requests');
    const id = `gateway-stream-${Date.now()}-${++this.sequence}`;
    const headers = { Accept: 'text/event-stream', 'Cache-Control': 'no-cache' };
    for (const [name, value] of Object.entries(payload.headers || {})) {
      if (!['host', 'connection', 'content-length', 'transfer-encoding'].includes(String(name).toLowerCase())) headers[String(name)] = String(value);
    }
    const emit = message => { if (sender && !sender.isDestroyed()) sender.send('beast:gateway-stream-message', { id, ...message }); };
    const request = http.request(target, { method: 'GET', headers, timeout: Math.max(1000, Math.min(Number(payload.timeoutMs || 3700000), 3700000)) });
    const session = { id, request, response: null, closed: false, buffer: '', event: 'message', data: [] };
    const close = (reason = '') => { if (session.closed) return; session.closed = true; this.sessions.delete(id); try { session.request.destroy(); } catch (_) {} if (reason) emit({ type: 'closed', reason }); };
    this.sessions.set(id, session);
    const flush = () => {
      if (!session.data.length) { session.event = 'message'; return; }
      emit({ type: 'event', event: session.event || 'message', data: session.data.join('\n') });
      session.event = 'message'; session.data = [];
    };
    request.on('response', response => {
      session.response = response;
      if (response.statusCode < 200 || response.statusCode >= 300) { emit({ type: 'error', error: `gateway stream returned ${response.statusCode}` }); close(); return; }
      emit({ type: 'open', status: response.statusCode });
      response.setEncoding('utf8');
      response.on('data', chunk => {
        session.buffer += chunk;
        let newline;
        while ((newline = session.buffer.indexOf('\n')) >= 0) {
          const line = session.buffer.slice(0, newline).replace(/\r$/, ''); session.buffer = session.buffer.slice(newline + 1);
          if (!line) { flush(); continue; }
          if (line.startsWith(':')) continue;
          const colon = line.indexOf(':'); const field = colon < 0 ? line : line.slice(0, colon); const value = (colon < 0 ? '' : line.slice(colon + 1)).replace(/^ /, '');
          if (field === 'event') session.event = value || 'message'; else if (field === 'data') session.data.push(value);
        }
      });
      response.on('end', () => { flush(); if (!session.closed) { emit({ type: 'end' }); close(); } });
      response.on('error', error => { if (!session.closed) { emit({ type: 'error', error: String(error.message || error) }); close(); } });
    });
    request.on('timeout', () => { if (!session.closed) { emit({ type: 'error', error: 'gateway event stream timed out' }); close(); } });
    request.on('error', error => { if (!session.closed) { emit({ type: 'error', error: String(error.message || error) }); close(); } });
    request.end();
    return { ok: true, id };
  }

  stop(id) {
    const session = this.sessions.get(String(id || ''));
    if (!session) return { ok: true, stopped: false };
    session.closed = true;
    this.sessions.delete(session.id);
    try { session.request.destroy(); } catch (_) {}
    return { ok: true, stopped: true };
  }

  stopAll() { for (const id of [...this.sessions.keys()]) this.stop(id); }
}

module.exports = { GatewayEventStreamHost };
