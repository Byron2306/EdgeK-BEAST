(() => {
  'use strict';
  const DEFAULT_GATEWAY = 'http://127.0.0.1:8000';
  const EXPECTED_DESKTOP = [
    'status','chooseWorkspace','listFiles','readFile','fileOperation','toolingSnapshot','systemSnapshot',
    'releaseReadiness','restartGateway','openWorkspaceWindow','openGateway','gatewayRequest',
    'onWorkspaceSelected','onRefresh','onGatewayLog','onDesktopVersion'
  ];
  const state = {
    initialized:false, mode:'offline', gatewayUrl:DEFAULT_GATEWAY, desktopCapabilities:{},
    endpointHealth:new Map(), inFlight:new Map(), cache:new Map(), exclusive:new Map(),
    listeners:new Map(), eventDisposers:[], controllers:new Set(), errors:[], visible:!document.hidden,
    bootedAt:0, lastProbeAt:0, desktopVersion:'', gatewayVersion:''
  };

  const emit = (type, detail={}) => {
    const set=state.listeners.get(type); if(set) [...set].forEach(fn=>{try{fn(detail)}catch(error){console.error('[BEAST Runtime listener]',error)}});
    document.dispatchEvent(new CustomEvent(`beast:runtime:${type}`,{detail}));
  };
  const on = (type, listener) => { if(!state.listeners.has(type)) state.listeners.set(type,new Set()); state.listeners.get(type).add(listener); return ()=>state.listeners.get(type)?.delete(listener); };
  const desktop = () => window.beastDesktop || null;
  const hasDesktop = name => typeof desktop()?.[name] === 'function';
  const normalizeGateway = value => {
    try { const url=new URL(value || DEFAULT_GATEWAY); return url.origin; } catch (_) { return DEFAULT_GATEWAY; }
  };
  const setGatewayUrl = value => {
    state.gatewayUrl=normalizeGateway(value); window.gatewayUrl=state.gatewayUrl;
    try { BeastStore.patch('connection',{gatewayUrl:state.gatewayUrl}); } catch (_) {}
    return state.gatewayUrl;
  };
  const stableBody = body => { try{return JSON.stringify(body??null)}catch(_){return String(body)} };
  const hash = value => { let h=2166136261; for(let i=0;i<value.length;i++){h^=value.charCodeAt(i);h=Math.imul(h,16777619)} return (h>>>0).toString(36); };
  const requestKey = (path, options) => `${(options.method||'GET').toUpperCase()}:${path}:${hash(stableBody(options.body))}`;
  const joinSignal = (external, timeoutMs) => {
    const controller=new AbortController(); state.controllers.add(controller);
    const timer=setTimeout(()=>controller.abort(new DOMException('Request timeout','TimeoutError')),timeoutMs);
    if(external){ if(external.aborted) controller.abort(external.reason); else external.addEventListener('abort',()=>controller.abort(external.reason),{once:true}); }
    return {controller, signal:controller.signal, done(){clearTimeout(timer);state.controllers.delete(controller)}};
  };
  const markHealth = (path, ok, detail={}) => {
    const current=state.endpointHealth.get(path)||{successes:0,failures:0};
    const next={...current,ok,status:detail.status||0,latencyMs:detail.latencyMs||0,error:detail.error||'',checkedAt:Date.now(),successes:current.successes+(ok?1:0),failures:current.failures+(ok?0:1)};
    state.endpointHealth.set(path,next); emit('route-health',{path,...next}); return next;
  };
  async function desktopCall(method,args=[],options={}) {
    const api=desktop();
    if(typeof api?.[method] !== 'function') {
      if(options.required) throw new Error(`Electron preload method unavailable: ${method}`);
      return undefined;
    }
    const started=performance.now();
    try { const result=await api[method](...args); markHealth(`ipc:${method}`,true,{latencyMs:Math.round(performance.now()-started)}); return result; }
    catch(error){ markHealth(`ipc:${method}`,false,{latencyMs:Math.round(performance.now()-started),error:String(error.message||error)}); throw error; }
  }
  async function rawRequest(path, options, signal) {
    const method=(options.method||'GET').toUpperCase();
    const url=new URL(path,state.gatewayUrl).toString();
    if(hasDesktop('gatewayRequest') && options.preferFetch !== true) {
      const payload=await desktopCall('gatewayRequest',[{url,path,method,body:options.body??null,headers:options.headers||{},timeoutMs:options.timeoutMs||6000}],{required:true});
      if(payload?.ok===false) throw new Error(payload.error||`${payload.status||''} gateway request failed`.trim());
      return payload?.data ?? payload?.body ?? payload;
    }
    const response=await fetch(url,{method,headers:{Accept:'application/json',...(options.body?{'Content-Type':'application/json'}:{}),...(options.headers||{})},body:options.body===undefined?undefined:JSON.stringify(options.body),signal});
    if(!response.ok){ const text=await response.text().catch(()=> ''); const error=new Error(`${response.status} ${response.statusText}${text?`: ${text.slice(0,240)}`:''}`); error.status=response.status; throw error; }
    if(response.status===204) return null;
    const type=response.headers.get('content-type')||'';
    return type.includes('application/json') ? response.json() : response.text();
  }
  async function request(path, options={}) {
    const method=(options.method||'GET').toUpperCase();
    const key=options.key||requestKey(path,options);
    const cacheTtl=Number(options.cacheTtl ?? (method==='GET'?250:0));
    const cached=state.cache.get(key);
    if(cacheTtl>0 && cached && Date.now()-cached.at<cacheTtl) return structuredClone(cached.value);
    if(options.dedupe!==false && state.inFlight.has(key)) return state.inFlight.get(key);
    const promise=(async()=>{
      const attempts=Math.max(1,Number(options.attempts ?? (method==='GET'?2:1)));
      let lastError;
      for(let attempt=1;attempt<=attempts;attempt++){
        const joined=joinSignal(options.signal,Number(options.timeoutMs||options.timeout||6000));
        const started=performance.now();
        try {
          const value=await rawRequest(path,options,joined.signal);
          markHealth(path,true,{latencyMs:Math.round(performance.now()-started),status:200});
          if(cacheTtl>0) state.cache.set(key,{at:Date.now(),value:structuredClone(value)});
          return value;
        } catch(error) {
          lastError=error; markHealth(path,false,{latencyMs:Math.round(performance.now()-started),status:error.status||0,error:String(error.message||error)});
          if(joined.signal.aborted || attempt>=attempts || (error.status && error.status<500)) throw error;
          await new Promise(resolve=>setTimeout(resolve,120*attempt+Math.random()*80));
        } finally { joined.done(); }
      }
      throw lastError;
    })();
    state.inFlight.set(key,promise);
    try { return await promise; } finally { if(state.inFlight.get(key)===promise) state.inFlight.delete(key); }
  }
  async function runExclusive(key, task) {
    if(state.exclusive.has(key)) return state.exclusive.get(key);
    const promise=Promise.resolve().then(task);
    state.exclusive.set(key,promise);
    try{return await promise}finally{if(state.exclusive.get(key)===promise)state.exclusive.delete(key)}
  }
  async function probe(options={}) {
    const started=performance.now(); let result=null; let mode='offline';
    try {
      if(hasDesktop('status')) { result=await desktopCall('status',[]); mode='electron'; }
      else { result=await request('/edgek/root-info',{...options,cacheTtl:0,attempts:1,timeoutMs:options.timeoutMs||3500}); mode='gateway'; }
      const url=result?.gatewayUrl||result?.gateway_url||state.gatewayUrl; setGatewayUrl(url);
      state.gatewayVersion=result?.version||result?.health?.version||'';
      state.mode=result?.health?.ok===false?'offline':mode;
    } catch(error) {
      state.mode='offline'; state.errors.unshift({at:Date.now(),scope:'probe',message:String(error.message||error)}); state.errors=state.errors.slice(0,50);
    }
    state.lastProbeAt=Date.now();
    document.body.dataset.runtimeMode=state.mode;
    document.body.dataset.runtimeFault=state.mode==='offline'?'true':'false';
    emit('probe',{ok:state.mode!=='offline',mode:state.mode,result,latencyMs:Math.round(performance.now()-started)});
    return result;
  }
  function bindDesktopEvents() {
    if(state.eventDisposers.length) return ()=>{};
    const api=desktop();
    const bind=(method,type)=>{
      if(typeof api?.[method]!=='function')return;
      try{const maybeDispose=api[method](payload=>emit(type,payload));if(typeof maybeDispose==='function')state.eventDisposers.push(maybeDispose)}catch(error){state.errors.unshift({at:Date.now(),scope:method,message:String(error.message||error)})}
    };
    bind('onWorkspaceSelected','workspace'); bind('onRefresh','refresh'); bind('onGatewayLog','log'); bind('onDesktopVersion','desktop-version');
    return ()=>{state.eventDisposers.splice(0).forEach(fn=>{try{fn()}catch(_){}})};
  }
  function cancelAll(reason='runtime shutdown'){ [...state.controllers].forEach(controller=>controller.abort(reason)); state.controllers.clear(); state.inFlight.clear(); }
  function diagnostics(){
    return {
      initialized:state.initialized,mode:state.mode,gatewayUrl:state.gatewayUrl,visible:state.visible,
      desktopCapabilities:{...state.desktopCapabilities},inFlight:state.inFlight.size,cacheEntries:state.cache.size,
      endpointHealth:Object.fromEntries(state.endpointHealth),errors:[...state.errors],bootedAt:state.bootedAt,lastProbeAt:state.lastProbeAt
    };
  }
  let syncTimer=0;
  function syncStoreNow() {
    syncTimer=0;if(!window.BeastStore)return;
    BeastStore.patch('runtime',{mode:state.mode,gatewayUrl:state.gatewayUrl,desktopCapabilities:{...state.desktopCapabilities},inFlight:state.inFlight.size,errors:state.errors.slice(0,10),lastProbeAt:state.lastProbeAt,visible:state.visible});
  }
  function syncStore() { if(syncTimer)return; syncTimer=setTimeout(syncStoreNow,80); }
  async function init() {
    if(state.initialized)return diagnostics(); state.initialized=true;state.bootedAt=Date.now();
    const api=desktop(); state.desktopCapabilities=Object.fromEntries(EXPECTED_DESKTOP.map(name=>[name,typeof api?.[name]==='function']));
    bindDesktopEvents();
    on('desktop-version',value=>{state.desktopVersion=typeof value==='string'?value:value?.version||'';syncStore()});
    on('probe',syncStore); on('route-health',syncStore);
    document.addEventListener('visibilitychange',()=>{state.visible=!document.hidden;document.body.classList.toggle('beast-hidden',!state.visible);syncStore();emit('visibility',{visible:state.visible})});
    window.addEventListener('unhandledrejection',event=>{state.errors.unshift({at:Date.now(),scope:'promise',message:String(event.reason?.message||event.reason)});state.errors=state.errors.slice(0,50);syncStore()});
    window.addEventListener('error',event=>{state.errors.unshift({at:Date.now(),scope:'window',message:String(event.message||event.error||'unknown error')});state.errors=state.errors.slice(0,50);syncStore()});
    const params=new URLSearchParams(location.search);
    if(params.get('capture')==='1'||params.get('demo')==='1'){state.mode='offline';document.body.dataset.runtimeMode='offline';document.body.dataset.runtimeFault='false';}
    else await probe();
    syncStore(); return diagnostics();
  }
  function destroy(){cancelAll();clearTimeout(syncTimer);syncTimer=0;state.eventDisposers.splice(0).forEach(fn=>{try{fn()}catch(_){}});state.cache.clear();state.initialized=false;}
  window.BeastRuntime={init,destroy,request,probe,desktopCall,hasDesktop,on,emit,runExclusive,cancelAll,diagnostics,setGatewayUrl,bindDesktopEvents,get gatewayUrl(){return state.gatewayUrl},get desktop(){return desktop()},get mode(){return state.mode},get visible(){return state.visible}};
})();
