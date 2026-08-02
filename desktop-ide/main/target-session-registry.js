'use strict';

const crypto = require('crypto');

function createTargetSessionRegistry() {
  const sessions = new Map();
  let activeSessionId = '';

  function nowIso() {
    return new Date().toISOString();
  }

  function sessionId(kind, identity) {
    const digest = crypto.createHash('sha256').update(`${kind}\n${identity}`).digest('hex').slice(0, 20);
    return `target-${kind}-${digest}`;
  }

  function cloneSession(session) {
    return session ? JSON.parse(JSON.stringify(session)) : null;
  }

  function summary(session) {
    if (!session) return null;
    return cloneSession({
      sessionId: session.sessionId,
      kind: session.kind,
      identity: session.identity,
      label: session.label,
      target: session.target,
      status: session.status,
      health: session.health,
      transport: session.transport,
      reconnectCount: session.reconnectCount,
      attachedAt: session.attachedAt,
      lastSeenAt: session.lastSeenAt,
      lastHealthyAt: session.lastHealthyAt,
      lastUsedAt: session.lastUsedAt,
      lastError: session.lastError,
      metadata: session.metadata,
      active: session.sessionId === activeSessionId,
    });
  }

  function ensure(kind, identity, payload = {}) {
    const id = sessionId(kind, identity);
    const existing = sessions.get(id);
    const stamp = nowIso();
    if (existing) {
      existing.kind = kind;
      existing.identity = identity;
      existing.label = String(payload.label || existing.label || identity);
      existing.target = payload.target ? { ...existing.target, ...payload.target } : existing.target;
      existing.transport = String(payload.transport || existing.transport || kind);
      existing.lastSeenAt = stamp;
      if (payload.metadata && typeof payload.metadata === 'object') existing.metadata = { ...existing.metadata, ...payload.metadata };
      return existing;
    }
    const created = {
      sessionId: id,
      kind,
      identity,
      label: String(payload.label || identity),
      target: payload.target && typeof payload.target === 'object' ? { ...payload.target } : {},
      transport: String(payload.transport || kind),
      status: 'idle',
      health: 'unknown',
      reconnectCount: 0,
      attachedAt: stamp,
      lastSeenAt: stamp,
      lastHealthyAt: '',
      lastUsedAt: '',
      lastError: '',
      metadata: payload.metadata && typeof payload.metadata === 'object' ? { ...payload.metadata } : {},
    };
    sessions.set(id, created);
    return created;
  }

  function activate(kind, identity, payload = {}) {
    const entry = ensure(kind, identity, payload);
    activeSessionId = entry.sessionId;
    entry.status = String(payload.status || 'active');
    entry.lastSeenAt = nowIso();
    return summary(entry);
  }

  function touch(kind, identity, patch = {}) {
    const entry = ensure(kind, identity, patch);
    const stamp = nowIso();
    entry.lastSeenAt = stamp;
    if (patch.used) entry.lastUsedAt = stamp;
    if (patch.status) entry.status = String(patch.status);
    if (patch.health) {
      entry.health = String(patch.health);
      if (entry.health === 'healthy') entry.lastHealthyAt = stamp;
    }
    if (patch.error !== undefined) entry.lastError = String(patch.error || '');
    if (patch.reconnected) entry.reconnectCount = Number(entry.reconnectCount || 0) + 1;
    if (patch.label) entry.label = String(patch.label);
    if (patch.target && typeof patch.target === 'object') entry.target = { ...entry.target, ...patch.target };
    if (patch.metadata && typeof patch.metadata === 'object') entry.metadata = { ...entry.metadata, ...patch.metadata };
    if (patch.activate) activeSessionId = entry.sessionId;
    return summary(entry);
  }

  function deactivate(kind, identity, patch = {}) {
    const entry = ensure(kind, identity, patch);
    entry.status = String(patch.status || 'inactive');
    if (patch.health) entry.health = String(patch.health);
    if (patch.error !== undefined) entry.lastError = String(patch.error || '');
    entry.lastSeenAt = nowIso();
    if (activeSessionId === entry.sessionId) activeSessionId = '';
    return summary(entry);
  }

  function list(kind = '') {
    const rows = [...sessions.values()].map(summary).filter(Boolean);
    return kind ? rows.filter(item => item.kind === kind) : rows;
  }

  function active() {
    return summary(sessions.get(activeSessionId) || null);
  }

  return {
    ensure,
    activate,
    touch,
    deactivate,
    list,
    active,
    summary,
  };
}

module.exports = { createTargetSessionRegistry };
