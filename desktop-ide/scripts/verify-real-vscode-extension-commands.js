#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const { handle } = require('./beast-extension-host');

function copyRealExtension(targetRoot) {
  fs.cpSync(path.resolve(__dirname, '..', '..', 'vscode-extension'), targetRoot, {
    recursive: true,
    filter: source => {
      const normalized = String(source).replace(/\\/g, '/');
      return !normalized.includes('/.vscode-test/') && !normalized.endsWith('/.vscode-test');
    },
  });
}

function missionSnapshot(workspaceRoot) {
  return {
    beast_object_type: 'beast_ide_snapshot',
    workspace_root: workspaceRoot,
    code_cortex: { front_door: 'code_cortex' },
    policy: { mode_route: { selected_mode: 'implementer' }, architecture_decisions: { status: 'accepted_implemented' } },
    mission_cockpit: { cards: [{ title: 'Gateway', value: 'healthy', detail: 'mock gateway ready' }] },
    sourceplan_queue: [{ plan_id: 'plan-demo', status: 'draft' }],
    evidence_bus: { total: 4 },
    mission_lattice: { cell_count: 2 },
    agent_sessions: { count: 1 },
    worktrees: { count: 1 },
  };
}

async function main() {
  const scratchBase = path.resolve(__dirname, '..', '..', '.tmp');
  fs.mkdirSync(scratchBase, { recursive: true });
  const root = fs.mkdtempSync(path.join(scratchBase, 'beast-real-extension-flow-'));
  const workspaceRoot = path.join(root, 'workspace');
  const hostRoot = path.join(workspaceRoot, '.beast', 'extensions');
  const targetRoot = path.join(hostRoot, 'edgek-beast');
  fs.mkdirSync(hostRoot, { recursive: true });
  copyRealExtension(targetRoot);

  const roots = [{ path: hostRoot, origin: 'workspace' }];
  const configuration = { 'edgekBeast.proxyUrl': 'http://127.0.0.1:8765' };
  const mockFetchResponses = {
    'GET /health': { status: 200, body: { ok: true, mode: 'mock' } },
    'GET /edgek/ide/snapshot': { status: 200, body: missionSnapshot(workspaceRoot) },
  };
  await handle({ operation: 'activateByEvent', roots, workspaceRoot, activationEvent: 'onStartupFinished', configuration, mockFetchResponses });
  const mission = await handle({
    operation: 'execute',
    roots,
    workspaceRoot,
    extensionId: 'edgek.edgek-beast',
    command: 'edgekBeast.openMissionControl',
    configuration,
    mockFetchResponses,
  });
  const kinds = new Set((mission.actions || []).map(action => action.kind));
  const webviews = (mission.actions || []).filter(action => action.kind === 'webview');
  const notices = (mission.actions || []).filter(action => action.kind === 'notice');
  const commands = (mission.actions || []).filter(action => action.kind === 'command');
  const checks = [
    mission.ok !== false,
    kinds.has('webview'),
    webviews.some(action => action.payload?.created === true && action.payload?.viewType === 'beastMissionControl'),
    webviews.some(action => (action.payload?.htmlBytes || 0) > 0),
    commands.some(action => action.payload?.id === 'mock.fetch'),
  ];
  const failed = checks.map((ok, index) => ok ? null : index + 1).filter(Boolean);
  console.log(JSON.stringify({
    ok: failed.length === 0,
    checks: checks.length,
    failed,
    actionKinds: [...kinds].sort(),
    webviewCount: webviews.length,
    noticeCount: notices.length,
    commandCount: commands.length,
  }, null, 2));
  process.exit(failed.length === 0 ? 0 : 1);
}

main().catch(error => {
  console.error(error.stack || String(error));
  process.exit(1);
});
