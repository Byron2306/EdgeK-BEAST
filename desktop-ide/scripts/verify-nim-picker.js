const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const model = 'nvidia/nemotron-3.5-lightning-30b-a3b';
const local = 'granite3.3:2b';
const bridgeDir = path.join(__dirname, '../renderer/js');

function setup({ verified = true, credential = true, configuredNim = false } = {}) {
  const state = {
    connection:{gatewayUrl:'http://127.0.0.1:18101'}, workspace:{root:'/fixture',files:[{path:'dummy.py'},{path:'test_dummy.py'}]},
    editor:{activePath:'dummy.py'},
    models:{registry:[]}, aiCoding:{model:local,provider:'ollama'}
  };
  const calls = [];
  const requests = [];
  const store = new Map();
  const window = {beastDesktop:{listOllamaModels:async () => ({ok:true, models:[{name:local}]})}};
  const ctx = vm.createContext({
    window, URLSearchParams,
    BeastStore:{get:() => state, patch:(key,v) => Object.assign(state[key],v), addLedger(){}},
    localStorage:{setItem:(k,v) => store.set(k,v), getItem:k => store.get(k)},
    BeastRuntime:{request:async (url, options) => {
      requests.push({url, options});
      if (url.endsWith('/agent-sessions/create')) return {session_id:'test-session'};
      if (url.endsWith('/agent-runs')) return {ok:true,run:{run_id:'test-run'}};
      return {};
    }},
    BeastMascot:{setState(){}},
    BeastDesktopBridge:{
      demoMode:false,
      async fetchJson(url, opts) {
        calls.push({url,opts});
        if (url.includes('inference-stats')) throw Error('404');
        if (url.endsWith('/registry') && configuredNim) return {providers:[{provider_id:'nvidia_nim',default_model:'nvidia/test-coder',enabled:true,backend:'openai_compatible'}]};
        if (url.endsWith('/state')) return { providers:{ nvidia_nim:{enabled:true,default_model:model} },credentials:{nvidia_nim:credential} };
        if (url.endsWith('/verify-picker-model')) return { ok:verified, provider:'nvidia_nim', model:verified ? model : 'other', status:verified?'verified':'model_mismatch' };
        return {};
      }
    }
  });
  for (const file of ['beast-model-agent-bridge.js', 'ai/agent-client.js'])
    vm.runInContext(fs.readFileSync(path.join(bridgeDir,file),'utf8'),ctx,{filename:file});
  const client = window.BeastAICodingModules.createAgentClient({
    root:() => state.workspace.root, gatewayUrl:() => state.connection.gatewayUrl,
    openRunStream:async () => ({addEventListener(){}}), streamState:{},
    constants:{RELIABLE_PLANNER_PROFILE:{maxFiles:4,editTokens:4096,contextChars:8000}},
    api:{
      patch:v => Object.assign(state.aiCoding,v),persist(){},
      contextFilesFor:() => ['dummy.py'],normalizeContextFiles:files => [...new Set(files)],
      resolvedModeForPrompt:mode => mode, instructionFor:(_mode,prompt) => prompt,
      isAgentAnalysisPrompt:() => false, mentionedFiles:() => [],
      agentTurnProfile:() => ({kind:'test'}),addMessage:() => 'msg',
      initialAgentTurns:() => [],initialAgentProgress:() => [],
      appendTrace(){},updateProgress(){},armWatchdog(){}
    }
  });
  return {state,calls,requests,store,bridge:window.BeastModelAgentBridge,client};
}

test('credential and configured default alone never insert or select hosted Nemotron', async () => {
  const {state,calls,bridge} = setup();
  await bridge.refreshModels();
  assert.equal(state.models.registry.length,1);
  assert.equal(state.models.error,'');
  assert.equal(state.models.registry[0].id,local);
  assert.equal(state.aiCoding.provider,'ollama');
  assert.equal(calls.some(c => c.url.endsWith('/verify-picker-model')),false);
});

test('credential-ready NIM coding route resolves exactly and is invalidated on gateway change', async () => {
  const {state,bridge,client} = setup({configuredNim:true});
  await bridge.refreshModels();
  const route=client.syncModel('nvidia/test-coder',{explicitSelection:true});
  assert.equal(route.provider,'nvidia_nim');
  assert.equal(route.hostedCoding,false);
  assert.equal((await client.resolveCodingRoute()).model,'nvidia/test-coder');
  state.connection.gatewayUrl='http://different-gateway';
  assert.throws(()=>client.syncModel('nvidia/test-coder'),/available model inventory/);
});

test('missing NIM credentials do not create a coding route', async () => {
  const {state,bridge} = setup({configuredNim:true,credential:false});
  await bridge.refreshModels();
  assert.equal(state.models.registry.some(row=>row.id==='nvidia/test-coder'),false);
});

test('explicit verification makes hosted model selectable without claiming local installation', async () => {
  const {state,calls,bridge,client,store} = setup();
  await bridge.verifyHostedNemotron();
  const row = state.models.registry.find(r => r.id === model);
  assert.equal(row?.inferenceVerified,true);
  assert.notEqual(row.installed,true);
  assert.deepEqual(JSON.parse(JSON.stringify(calls.find(c => c.url.endsWith('/verify-picker-model')).opts.body)),{confirm_live:true});
  assert.equal(state.aiCoding.provider,'ollama');
  assert.throws(() => client.syncModel(model), /provider/);
  assert.equal(client.syncModel(model,{explicitSelection:true}).provider,'nvidia_nim');
  assert.equal((await client.resolveCodingRoute()).model,model);
  assert.equal(store.get('beast.provider'),'nvidia_nim');
  assert.equal(client.syncModel(local,{explicitSelection:true}).provider,'ollama');
  assert.equal(store.get('beast.provider'),'ollama');
});

test('failed verification does not create a selectable hosted model', async () => {
  const {state,bridge} = setup({verified:false});
  await assert.rejects(async () => bridge.verifyHostedNemotron(),/model_mismatch/);
  assert.equal(state.models.registry.some(r => r.id === model),false);
});

test('changing gateway invalidates prior hosted verification', async () => {
  const {state,bridge,client} = setup();
  await bridge.verifyHostedNemotron();
  client.syncModel(model,{explicitSelection:true});
  state.connection.gatewayUrl='http://127.0.0.1:8101';
  await assert.rejects(client.resolveCodingRoute(),/unavailable/);
  assert.equal(state.models.registry.some(r => r.id === model),false);
});

test('verified hosted picker selection starts an NVIDIA agent coding run', async () => {
  const {state,requests,bridge,client} = setup();
  await bridge.verifyHostedNemotron();
  client.syncModel(model,{explicitSelection:true});
  state.aiCoding.mode='agent';
  assert.equal((await client.send('Change dummy.py safely')).run_id,'test-run');
  const run = requests.find(r => r.url.endsWith('/agent-runs')).options.body;
  assert.equal(run.provider,'nvidia_nim');
  assert.equal(run.model,model);
  assert.equal(run.mode,'agent');
  assert.equal(run.request.implementation_target,'dummy.py');
  assert.deepEqual(JSON.parse(JSON.stringify(run.request.required_test_files)),['test_dummy.py']);
});

test('hosted review creates an exact NVIDIA read-only run without the IDE-wide index', async () => {
  const {state,requests,bridge,client} = setup();
  await bridge.verifyHostedNemotron();
  client.syncModel(model,{explicitSelection:true});
  state.aiCoding.mode='review';
  state.editor={activePath:'dummy.py'};
  assert.equal((await client.send('Review dummy.py')).run_id,'test-run');
  const session = requests.find(r => r.url.endsWith('/agent-sessions/create')).options.body;
  const run = requests.find(r => r.url.endsWith('/agent-runs')).options.body;
  assert.equal(session.provider,'nvidia_nim');
  assert.equal(run.model,model);
  assert.equal(run.provider,'nvidia_nim');
  assert.equal(run.mode,'analysis');
  assert.equal(run.request.read_only_file_review,true);
  assert.equal(run.request.semantic_context,null);
  assert.deepEqual(JSON.parse(JSON.stringify(run.request.context_files)),['dummy.py']);
  assert.equal(run.request.nim_base_url,undefined);
});

test('an inspection selection cannot silently authorize hosted inference', async () => {
  const {state,bridge,client} = setup();
  await bridge.verifyHostedNemotron();
  state.aiCoding.model='';
  state.aiCoding.provider='';
  bridge.selectModel(model);
  assert.throws(() => client.syncModel(), /explicitly select the hosted provider/);
  assert.equal(state.aiCoding.provider,'');
});
