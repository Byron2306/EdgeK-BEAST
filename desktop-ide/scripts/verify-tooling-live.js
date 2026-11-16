// Live Electron proof for gateway tooling, MCP built-ins, and meta skills.
const assert = require('node:assert/strict');

async function main() {
  const pages = await (await fetch('http://127.0.0.1:9223/json/list')).json();
  const page = pages.find(item => item.type === 'page');
  assert.ok(page?.webSocketDebuggerUrl, 'No Electron renderer debugging target');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise(resolve => ws.addEventListener('open', resolve, {once:true}));
  let id = 0;
  const pending = new Map();
  ws.addEventListener('message', event => {
    const reply = JSON.parse(event.data);
    if (pending.has(reply.id)) {
      pending.get(reply.id)(reply);
      pending.delete(reply.id);
    }
  });
  const call = (method, params = {}) => new Promise(resolve => {
    pending.set(++id, resolve);
    ws.send(JSON.stringify({id, method, params}));
  });
  const evaluate = async expression => {
    const reply = await call('Runtime.evaluate', {expression, awaitPromise:true, returnByValue:true});
    if (reply.result?.exceptionDetails) throw new Error(reply.result.exceptionDetails.text);
    return reply.result?.result?.value;
  };
  try {
    const result = await evaluate(`(async()=>{
      const tooling=await BeastTerminalToolingDoctorBridge.refreshTooling({cacheTtl:0});
      await BeastModelAgentBridge.verifyHostedNemotron({cacheTtl:0});
      const row=BeastStore.get().models.registry.find(item=>item.id==='nvidia/nemotron-3.5-lightning-30b-a3b');
      const route=BeastAICodingModules.selectCodingModel(row.id);
      return {
        pytest:tooling.linting?.has_pytest===true,
        ruff:tooling.linting?.has_ruff===true,
        builtinTools:Number(tooling.mcp?.builtin_tool_count||0),
        skills:Number(tooling.skills?.count||0),
        candidates:Number(tooling.skills?.candidateCount||0),
        hostedCoding:row?.hostedCoding===true,
        provider:route.provider,
        model:route.model,
      };
    })()`);
    assert.equal(result.pytest, true);
    assert.equal(result.ruff, true);
    assert.ok(result.builtinTools >= 1);
    assert.ok(result.skills >= 1);
    assert.equal(result.hostedCoding, true);
    assert.equal(result.provider, 'nvidia_nim');
    console.log(JSON.stringify({ok:true, ...result}));
  } finally {
    ws.close();
  }
}

main().catch(error => {
  console.error(error.stack || error.message);
  process.exitCode = 1;
});
