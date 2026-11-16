// Run against the local Electron debugging port. Never submits credentials.
const assert = require('node:assert/strict');
async function main() {
  const pages = await (await fetch('http://127.0.0.1:9223/json/list')).json();
  const ws = new WebSocket(pages.find(p => p.type === 'page').webSocketDebuggerUrl);
  await new Promise(resolve => ws.addEventListener('open', resolve, {once:true}));
  let id=0; const pending=new Map();
  ws.addEventListener('message', event => {const r=JSON.parse(event.data); if(pending.has(r.id)){pending.get(r.id)(r);pending.delete(r.id);}});
  const call=(method,params={})=>new Promise(resolve=>{pending.set(++id,resolve);ws.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression=>{
    const r=await call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
    if(r.result?.exceptionDetails) throw Error(r.result.exceptionDetails.text);
    return r.result?.result?.value;
  };
  try {
    const occupied=await evaluate("Boolean(document.querySelector('[data-provider-secret-value]')?.value)");
    assert.equal(occupied,false,'Do not reload while an operator has entered a key');
    await call('Page.reload',{ignoreCache:true});
    for(let i=0;i<40;i++){
      await new Promise(resolve=>setTimeout(resolve,250));
      if(await evaluate("Boolean(window.BeastProvidersPage && window.BeastRouter?.active)"))break;
    }
    await evaluate("(async()=>{await BeastUtilityOrchestrationBridge.refreshProviders();BeastStore.patch('providers',{selectedId:'nvidia_nim'});await BeastRouter.navigate('providers');})()");
    assert.equal(await evaluate("Boolean(document.querySelector('[data-provider-secret-value]'))"),true);
    await evaluate("window.__inputProbe=document.querySelector('[data-provider-secret-value]');window.__inputProbe.focus()");
    await call('Input.insertText',{text:'ui-input-test-not-a-secret'});
    assert.equal(await evaluate("(()=>{for(let i=0;i<25;i++)BeastStore.patch('providers',{loading:false});return document.querySelector('[data-provider-secret-value]')===window.__inputProbe && document.activeElement===window.__inputProbe && window.__inputProbe.value==='ui-input-test-not-a-secret'})()"),true);
    await evaluate("window.__inputProbe.value='';delete window.__inputProbe");
    console.log('PASS: secret field retains node, focus, and pasted text across 25 updates; test text cleared, nothing submitted.');
  } finally {ws.close();}
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
