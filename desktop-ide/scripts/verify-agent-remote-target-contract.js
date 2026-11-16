'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');
const source = fs.readFileSync(path.join(__dirname, '../renderer/js/ai/agent-client.js'), 'utf8');
const start = source.indexOf('  function codingRunTarget() {');
const end = source.indexOf('  function isGatewayTimeout(', start);
assert(start >= 0 && end > start, 'remote coding target functions not found');
const state = { workspace: { executionTarget: {kind:'local'} } };
const context = {
  BeastStore: { get: () => state },
  root: () => '/test/local/repo',
};
vm.createContext(context);
vm.runInContext(source.slice(start, end) + '\nthis.contract = { codingRunTarget, agentRunCreatePayload };', context);
const {codingRunTarget, agentRunCreatePayload} = context.contract;
const options = {
  sessionId:'s', runPrompt:'fix calc', mode:'agent', analysisRun:false,
  route:{provider:'ollama',model:'qwen3:4b'}, files:['calc.py'],
  semanticContext:{}, semanticRisk:{}, selection:null, options:{},
  maxOutputTokens:256, maxContextChars:2000, launch:true,
};
function runFor(selected) {
  state.workspace.executionTarget = selected;
  const target = codingRunTarget();
  const body = agentRunCreatePayload({...options, target});
  assert.strictEqual(body.execution_target, selected.kind);
  assert.strictEqual(body.execution_target_payload.kind, selected.kind);
  assert.strictEqual(body.request.launch_strategy, 'typed_planner');
  return body;
}
assert.strictEqual(runFor({kind:'local'}).execution_target, 'local');
const ssh = runFor({kind:'ssh',host:'beast-ide-loopback',remoteRoot:'/tmp/beast-remote-proof'});
assert.strictEqual(ssh.execution_target_payload.host, 'beast-ide-loopback');
const container = runFor({kind:'container',containerId:'beast-ide-proof',workspaceFolder:'/workspace'});
assert.strictEqual(container.execution_target_payload.containerId, 'beast-ide-proof');
for (const invalid of [
  {kind:'ssh',host:'beast-ide-loopback',remoteRoot:'~'},
  {kind:'ssh',host:'-unsafe',remoteRoot:'/tmp'},
  {kind:'container',containerId:'beast-ide-proof',workspaceFolder:'../wrong'},
  {kind:'unknown'},
]) {
  state.workspace.executionTarget = invalid;
  assert.throws(() => codingRunTarget(), /REFUSE_REMOTE_TARGET/);
}
console.log('BEAST_AGENT_REMOTE_TARGET_CONTRACT=PASS (local/SSH/container, malformed destinations refused)');
