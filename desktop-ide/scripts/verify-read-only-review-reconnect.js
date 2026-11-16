'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

async function reconnect(run) {
  const assistant = {id:'a',role:'assistant',content:'Recovering…'};
  const app = {aiCoding:{messages:[assistant]}};
  const requests = [];
  const context = vm.createContext({
    window:{}, BeastStore:{get:()=>app},
    BeastRuntime:{request:async url=>{requests.push(url);return {run};}},
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../renderer/js/ai/agent-client.js'), 'utf8'), context);
  const client = context.window.BeastAICodingModules.createAgentClient({
    root:()=>'/tmp/beast-test', streamState:{}, constants:{},
    api:{patch:fields=>Object.assign(app.aiCoding, fields), persist(){},
      updateAssistant:(id,fields)=>{assert.equal(id,'a');Object.assign(assistant,fields);}},
  });
  assert.equal((await client.reconnectActiveRun('review-1')).terminal,true);
  return {assistant, app, requests};
}

(async () => {
  const findings = 'openai_adapter.py:2 returns a fixed status instead of the upstream value.';
  const result = await reconnect({mode:'analysis',state:'completed',checkpoint:{planner:{final_summary:findings}}});
  assert.equal(result.assistant.content, findings);
  assert.equal(result.assistant.error, false);
  assert.equal(result.app.aiCoding.status, 'complete');
  assert.equal(result.requests.length, 1);

  const blocked = await reconnect({mode:'chat',state:'policy_blocked',error:'Could not read attached file openai_adapter.py'});
  assert.match(blocked.assistant.content, /Could not read attached file openai_adapter\.py/);
  assert.doesNotMatch(blocked.assistant.content, /graduation|promoted|worktree/i);
  assert.equal(blocked.assistant.error, true);

  const edit = await reconnect({mode:'agent',state:'policy_blocked',error:'verification failed'});
  assert.match(edit.assistant.content, /graduation not accepted/i);
  console.log('Read-only review reconnect checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
