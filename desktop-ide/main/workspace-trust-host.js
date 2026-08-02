'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const TRUST_SCHEMA = 'beast.workspace-trust.v1';
const MODES = new Set(['restricted', 'trusted']);

function stableId(value) {
  return crypto.createHash('sha256').update(String(value || '')).digest('hex').slice(0, 24);
}

function createWorkspaceTrustHost({ app, getActiveWorkspaceRoot }) {
  if (!app || typeof getActiveWorkspaceRoot !== 'function') {
    throw new Error('createWorkspaceTrustHost requires app and getActiveWorkspaceRoot');
  }
  const statePath = path.join(app.getPath('userData'), 'workspace-trust.json');
  let broadcast = () => {};

  function readState() {
    try {
      const parsed = JSON.parse(fs.readFileSync(statePath, 'utf8'));
      return parsed && parsed.schema === TRUST_SCHEMA && parsed.workspaces ? parsed : { schema: TRUST_SCHEMA, workspaces: {} };
    } catch (_) {
      return { schema: TRUST_SCHEMA, workspaces: {} };
    }
  }

  function writeState(state) {
    fs.mkdirSync(path.dirname(statePath), { recursive: true });
    const temporary = `${statePath}.tmp-${process.pid}-${Date.now()}`;
    fs.writeFileSync(temporary, `${JSON.stringify(state, null, 2)}\n`, { mode: 0o600 });
    fs.renameSync(temporary, statePath);
  }

  function normalizeRoot(rootPath) {
    return path.resolve(String(rootPath || getActiveWorkspaceRoot() || process.cwd()));
  }

  function snapshot(rootPath) {
    const root = normalizeRoot(rootPath);
    const state = readState();
    const key = stableId(root);
    const record = state.workspaces[key] || {};
    const mode = MODES.has(record.mode) ? record.mode : 'restricted';
    return {
      ok: true,
      schema: TRUST_SCHEMA,
      workspaceRoot: root,
      workspaceId: key,
      mode,
      trusted: mode === 'trusted',
      restricted: mode !== 'trusted',
      reason: record.reason || 'Workspace has not been explicitly trusted.',
      decidedAt: Number(record.decidedAt || 0),
      decidedBy: record.decidedBy || 'BEAST default policy',
      restrictions: mode === 'trusted' ? [] : [
        'agents', 'terminals', 'tasks', 'debugging', 'notebooks',
        'executable_extensions', 'workspace_settings', 'automatic_hooks', 'source_mutation'
      ],
      statePath,
    };
  }

  function setMode(payload = {}) {
    const root = normalizeRoot(payload.workspaceRoot);
    const mode = String(payload.mode || '').toLowerCase();
    if (!MODES.has(mode)) throw new Error(`Unsupported workspace trust mode: ${mode}`);
    const state = readState();
    const key = stableId(root);
    state.workspaces[key] = {
      workspaceRoot: root,
      mode,
      reason: String(payload.reason || (mode === 'trusted' ? 'Explicit operator trust decision.' : 'Operator restricted this workspace.')).slice(0, 500),
      decidedAt: Date.now(),
      decidedBy: String(payload.decidedBy || 'BEAST operator').slice(0, 120),
    };
    writeState(state);
    const result = snapshot(root);
    broadcast(result);
    return result;
  }

  function categoryFor(channel, args = []) {
    const payload = args.find(value => value && typeof value === 'object') || {};
    if (channel === 'beast:workspace-trust-get' || channel === 'beast:workspace-trust-set') return null;
    if (/editor-document-save|workspace-target-write-file|remote-write-file|file-operation|workspace-git-(action|hunk-action|resolve|commit|branch|operation)/.test(channel)) return 'source_mutation';
    if (/workspace-settings-save|settings-scope-set|project-profile-save/.test(channel)) return 'workspace_settings';
    if (/terminal.*(start|send|run)|remote-terminal-run|dev-container-terminal-run/.test(channel)) return 'terminals';
    if (/workspace-(task-start|task-run|test-run)/.test(channel)) return 'tasks';
    if (/notebook-(execute|kernel-start|kernel-request)/.test(channel)) return 'notebooks';
    if (/extension-host-(grant|enable|install|deploy|uninstall|execute)/.test(channel)) return 'executable_extensions';
    if (channel === 'beast:ide-protocol-start' && String(payload.kind || payload.protocol || payload.type || '').toLowerCase().includes('dap')) return 'debugging';
    if (channel === 'beast:ide-protocol-request' && String(payload.kind || payload.protocol || payload.type || '').toLowerCase().includes('dap')) return 'debugging';
    if (channel === 'beast:gateway-request') {
      const method = String(payload.method || 'GET').toUpperCase();
      const target = String(payload.path || payload.url || '').toLowerCase();
      if (/agent|sourceplan.*apply|mission.*(start|execute)|hook/.test(target)) return /hook/.test(target) ? 'automatic_hooks' : 'agents';
      if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) return 'source_mutation';
    }
    return null;
  }

  function assertAllowed(channel, args = []) {
    const current = snapshot();
    const category = categoryFor(String(channel || ''), args);
    if (!category || current.trusted) return current;
    const error = new Error(`Workspace restricted mode blocks ${category}: ${channel}`);
    error.code = 'BEAST_WORKSPACE_RESTRICTED';
    error.beast = {
      beast_object_type: 'workspace_trust_refusal',
      channel,
      category,
      workspaceRoot: current.workspaceRoot,
      mode: current.mode,
      no_effect: true,
    };
    throw error;
  }

  return {
    snapshot,
    setMode,
    assertAllowed,
    categoryFor,
    setBroadcaster(callback) { broadcast = typeof callback === 'function' ? callback : () => {}; },
  };
}

module.exports = { TRUST_SCHEMA, createWorkspaceTrustHost };
