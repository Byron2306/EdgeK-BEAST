(() => {
  const dapSessions=new Map();
  const readyWaiters=new Map();
  const initializedWaiters=new Map();
  let notebookKernel=null;
  let notebookKernelReady=null;
  const desktop=()=>window.beastDesktop;
  const root=()=>BeastStore.get().workspace.root || '';
  const executionTarget=()=>BeastStore.get().workspace.executionTarget || {kind:'local'};
  function targetPath(value,target=executionTarget()) { const source=String(value||'').replace(/\\/g,'/'); if(!source||target?.kind==='local')return source; const workspace=String(root()||'').replace(/\\/g,'/').replace(/\/$/,''); const relative=source===workspace?'':source.startsWith(`${workspace}/`)?source.slice(workspace.length+1):source.replace(/^\/+/,''); const base=String(target.kind==='ssh'?(target.remoteRoot||target.path||'~'):(target.workspaceFolder||'/workspace')).replace(/\\/g,'/').replace(/\/$/,''); return `${base}/${relative}`.replace(/\/+/g,'/'); }
  const runtime=()=>BeastStore.get().compatibility.runtime || { debug:{status:'idle',output:[],stack:[],threads:[],breakpoints:[]}, notebook:{status:'idle',cells:[]}, remote:{status:'idle',host:'',path:'~',files:[]} };
  const clampLines=value=>String(value || '').split(',').map(item=>Number(item.trim())).filter(value=>Number.isInteger(value)&&value>0&&value<100000).slice(0,100);
  const parseJsonc=value=>{const source=String(value||'').replace(/\/\*[\s\S]*?\*\//g,'').replace(/(^|[^:])\/\/.*$/gm,'$1').replace(/,\s*([}\]])/g,'$1');return JSON.parse(source);};
  const watchStorageKey=()=>`beast.ide.debug.watches:${root()||'workspace'}`;
  const savedWatches=()=>{try{return JSON.parse(localStorage.getItem(watchStorageKey())||'[]').filter(value=>typeof value==='string'&&value.trim()).slice(0,20);}catch(_){return [];}};
  const watchExpressions=()=>{const rows=runtime().debug?.watches||[];return rows.length?rows.map(row=>typeof row==='string'?row:row.expression).filter(Boolean).slice(0,20):savedWatches();};
  function setWatchExpressions(expressions) { const next=[...new Set((expressions||[]).map(value=>String(value||'').trim()).filter(value=>value&&value.length<=500))].slice(0,20);localStorage.setItem(watchStorageKey(),JSON.stringify(next));patchRuntime('debug',{watches:next.map(expression=>({expression,result:'',type:'',pending:true}))});return next; }

  function patchRuntime(section, change) {
    const current=runtime();
    BeastStore.patch('compatibility',{runtime:{...current,[section]:{...(current[section] || {}),...change}}});
  }

  function waitFor(map,id,label) {
    return new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{map.delete(id);reject(new Error(`${label} timed out.`));},12000);
      map.set(id,{resolve:()=>{clearTimeout(timer);resolve();},reject:error=>{clearTimeout(timer);reject(error instanceof Error ? error : new Error(String(error)));}});
    });
  }

  async function request(session,method,params={},timeoutMs=10000) {
    return desktop().requestIdeProtocol({sessionId:session.id,method,params,timeoutMs});
  }
  async function notify(session,method,params={}) {
    return desktop().notifyIdeProtocol({sessionId:session.id,method,params});
  }

  async function ensureDebugAdapter(adapter='debugpy') {
    const available=(BeastStore.get().compatibility.debug || []).find(item=>item.id===adapter&&item.available);
    if (!available) throw new Error(`${adapter} is not installed. Install its debugger, then probe capabilities again.`);
    const summary=await desktop().startIdeProtocol({kind:'dap',adapter,root:root(),target:executionTarget()});
    const session={...summary,status:'running',ready:false,initialized:false,capabilities:{},configurationDone:null};
    dapSessions.set(summary.id,session);
    BeastStore.patch('compatibility',{sessions:[...(BeastStore.get().compatibility.sessions || []),session]});
    await waitFor(readyWaiters,summary.id,'Debug adapter initialization');
    return dapSessions.get(summary.id);
  }

  function activeDebugSource() {
    const file=BeastEditorCortex?.getActive?.() || {};
    if (!file.path) throw new Error('Open a source file in Editor Cortex before starting debug.');
    const workspace=root();
    if (!workspace) throw new Error('Choose a workspace before debugging.');
    return { name:file.path.split('/').pop(), relativePath:file.path, path:`${workspace.replace(/[\\/]$/,'')}/${file.path.replace(/^[/\\]+/,'')}`.replace(/\\/g,'/') };
  }

  function debugAdapterFor(source,requested='auto') {
    if(requested&&requested!=='auto')return requested;
    if(/\.py$/i.test(source.relativePath))return 'debugpy';
    if(/\.go$/i.test(source.relativePath))return 'delve';
    if(/\.(?:c|cc|cpp|cxx|h|hpp|rs)$/i.test(source.relativePath))return 'lldb';
    throw new Error('Choose a Python, Go, C/C++, or Rust source file, or select a debugger explicitly.');
  }

  function launchConfiguration(adapter,source,target='',configuration={}) {
    if(configuration&&typeof configuration==='object'&&Object.keys(configuration).length){const clean={...configuration};delete clean.__beastName;clean.request=clean.request==='attach'?'attach':'launch';clean.type=clean.type||adapter;clean.cwd=clean.cwd||root();if(clean.program&&!/^(?:[A-Za-z]:[\\/]|\/)/.test(clean.program))clean.program=`${root().replace(/[\\/]$/,'')}/${String(clean.program).replace(/^[/\\]+/,'')}`;return clean;}
    if(adapter==='debugpy')return {name:'BEAST Python debug',type:'python',request:'launch',program:source.path,cwd:root(),console:'internalConsole',stopOnEntry:false,justMyCode:true};
    if(adapter==='delve')return {name:'BEAST Go debug',type:'go',request:'launch',mode:'debug',program:target||source.path,cwd:root(),stopOnEntry:false};
    const program=String(target||'').trim();if(!program)throw new Error('LLDB requires the compiled executable path in Debug target.');
    const absolute=/^(?:[A-Za-z]:[\\/]|\/)/.test(program)?program:`${root().replace(/[\\/]$/,'')}/${program.replace(/^[/\\]+/,'')}`;
    return {name:'BEAST native debug',type:'lldb',request:'launch',program:absolute,cwd:root(),stopOnEntry:false,args:[]};
  }

  async function startDebug({breakpoints='',adapter='auto',target='',configuration=null,condition='',logMessage='',functionBreakpoints=[]}={}) {
    const source=activeDebugSource();const selected=debugAdapterFor(source,adapter);const launch=launchConfiguration(selected,source,target,configuration||{});const selectedTarget=executionTarget();if(selectedTarget.kind!=='local'){launch.cwd=targetPath(launch.cwd,selectedTarget);if(launch.program)launch.program=targetPath(launch.program,selectedTarget);if(launch.connect?.host)launch.connect={...launch.connect};}
    patchRuntime('debug',{status:'starting',error:'',output:[],stack:[],threads:[],adapter:selected,program:launch.program,source:source.path,breakpoints:clampLines(breakpoints)});
    try {
      const session=await ensureDebugAdapter(selected);
      await notify(session,launch.request==='attach'?'attach':'launch',launch);
      if (!session.initialized) await waitFor(initializedWaiters,session.id,'Debug adapter launch');
      const lines=clampLines(breakpoints);
      const breakpointSource={...source,path:targetPath(source.path,selectedTarget)};await request(session,'setBreakpoints',{source:breakpointSource,breakpoints:lines.map(line=>({line,...(condition?{condition:String(condition).slice(0,500)}:{}),...(logMessage?{logMessage:String(logMessage).slice(0,1000)}:{})}))});
      const functions=[...new Set((Array.isArray(functionBreakpoints)?functionBreakpoints:String(functionBreakpoints||'').split(',')).map(value=>String(value||'').trim()).filter(Boolean))].slice(0,50);
      if(functions.length)await request(session,'setFunctionBreakpoints',{breakpoints:functions.map(name=>({name}))});
      try{await request(session,'setExceptionBreakpoints',{filters:selected==='debugpy'?['raised']:[]});}catch(_){}
      if (session.capabilities?.supportsConfigurationDoneRequest !== false) {
        try { await request(session,'configurationDone',{});session.configurationDone=true; }
        catch(error) { if(!/only allowed during handling of a "(?:launch|attach)" request/i.test(String(error.message||error))) throw error; session.configurationDone=false;appendDebugOutput(`Adapter completed launch before configurationDone; continuing without a second configuration handshake.\n`); }
      } else session.configurationDone=false;
      patchRuntime('debug',{status:'running',sessionId:session.id,adapter:selected,program:launch.program||launch.connect?.host||'',source:source.path,targetSource:breakpointSource.path,breakpoints:lines,condition:String(condition||''),logMessage:String(logMessage||''),functionBreakpoints:functions,configurationName:launch.name||'',request:launch.request,error:''});
      BeastStore.addLedger(`Debug session started: ${selected} · ${launch.program}`);
      return session;
    } catch (error) {
      patchRuntime('debug',{status:'error',error:String(error.message || error)});
      throw error;
    }
  }
  async function startPythonDebug(options={}) { return startDebug({...options,adapter:'debugpy'}); }
  async function loadLaunchConfigurations() {
    const workspace=root();if(!workspace||!desktop()?.readFile)return {configurations:[],compounds:[]};
    try{const result=await desktop().readFile(workspace,'.vscode/launch.json',256000);const document=parseJsonc(result?.text||result?.content||'{}');return {configurations:Array.isArray(document?.configurations)?document.configurations.slice(0,80):[],compounds:Array.isArray(document?.compounds)?document.compounds.slice(0,30):[]};}catch(_){return {configurations:[],compounds:[]};}
  }
  async function startLaunchConfiguration(name,options={}) { const catalog=await loadLaunchConfigurations();const config=catalog.configurations.find(item=>item&&item.name===name);if(!config)throw new Error(`Launch configuration “${name}” was not found in .vscode/launch.json.`);return startDebug({...options,adapter:config.type==='python'?'debugpy':config.type==='go'?'delve':config.type==='lldb'?'lldb':'auto',configuration:{...config,__beastName:config.name}}); }
  async function startCompound(name,options={}) { const catalog=await loadLaunchConfigurations();const compound=catalog.compounds.find(item=>item&&item.name===name);if(!compound)throw new Error(`Compound “${name}” was not found in .vscode/launch.json.`);const names=(compound.configurations||[]).map(item=>typeof item==='string'?item:item?.name).filter(Boolean).slice(0,8);if(!names.length)throw new Error('This compound has no launch configurations.');const sessions=[];for(const configName of names)sessions.push(await startLaunchConfiguration(configName,options));patchRuntime('debug',{compound:name,compoundSessions:sessions.map(session=>session.id)});return sessions; }

  async function inspectStop(session,body={}) {
    try {
      const threadId=Number(body.threadId || 0);
      const threads=(await request(session,'threads',{})).threads || [];
      const selected=threadId || Number(threads[0]?.id || 0);
      const frames=selected ? ((await request(session,'stackTrace',{threadId:selected,startFrame:0,levels:20})).stackFrames || []) : [];
      let scopes=[];
      let variables=[];
      if (frames[0]?.id != null) {
        scopes=(await request(session,'scopes',{frameId:frames[0].id})).scopes || [];
        variables=await Promise.all(scopes.slice(0,6).map(async scope=>{
          if (!Number(scope.variablesReference)) return {...scope,variables:[]};
          try {
            const response=await request(session,'variables',{variablesReference:Number(scope.variablesReference),start:0,count:100});
            return {...scope,variables:(response.variables || []).slice(0,100)};
          } catch (error) {
            return {...scope,variables:[],error:String(error.message || error)};
          }
        }));
      }
      const watches=await Promise.all(watchExpressions().map(async expression=>{try{const response=await request(session,'evaluate',{expression,frameId:frames[0]?.id,context:'watch'});return {expression,result:String(response.result||''),type:String(response.type||''),variablesReference:Number(response.variablesReference||0)};}catch(error){return {expression,error:String(error.message||error)};}}));
      patchRuntime('debug',{status:'stopped',threadId:selected,threads,stack:frames,scopes,variables,watches,reason:body.reason || 'breakpoint'});
    } catch (error) { patchRuntime('debug',{status:'stopped',error:String(error.message || error)}); }
  }

  async function debugControl(action) {
    const debug=runtime().debug || {}; const session=dapSessions.get(debug.sessionId);
    if (!session) throw new Error('No active debug session.');
    const threadId=Number(debug.threadId || debug.threads?.[0]?.id || 0);
    const methods={continue:'continue',next:'next',stepIn:'stepIn',stepOut:'stepOut',pause:'pause'};
    if (action==='stop') {
      try { await request(session,'disconnect',{restart:false,terminateDebuggee:true}); } finally { await desktop().stopIdeProtocol(session.id); dapSessions.delete(session.id); patchRuntime('debug',{status:'terminated',sessionId:'',threadId:0}); }
      return;
    }
    const method=methods[action]; if (!method) throw new Error('Unsupported debug command.');
    if(['continue','next','stepIn','stepOut'].includes(action) && debug.status!=='stopped') { appendDebugOutput(`Ignored ${action}: debugger is ${debug.status||'not stopped'}.\n`); return {ignored:true,status:debug.status}; }
    await request(session,method,threadId?{threadId}:{});
    patchRuntime('debug',{status:action==='pause'?'pausing':'running',error:''});
  }
  async function evaluateDebug(expression) {
    const text=String(expression||'').trim();if(!text)throw new Error('Enter a debug expression to evaluate.');if(text.length>4000)throw new Error('Debug expressions are limited to 4,000 characters.');const debug=runtime().debug||{};const session=dapSessions.get(debug.sessionId);if(!session)throw new Error('No active debug session.');const response=await request(session,'evaluate',{expression:text,frameId:debug.stack?.[0]?.id,context:'repl'});const entry={text:`> ${text}\n${String(response.result||'')}${response.type?` · ${response.type}`:''}\n`,category:'console'};patchRuntime('debug',{repl:[...(debug.repl||[]),entry].slice(-100)});return response;
  }
  function addWatchExpression(expression) { return setWatchExpressions([...watchExpressions(),expression]); }
  function removeWatchExpression(expression) { return setWatchExpressions(watchExpressions().filter(value=>value!==String(expression||''))); }

  async function ensureNotebookKernel() {
    if (notebookKernel?.status==='ready') return notebookKernel;
    if (!desktop()?.startNotebookKernel) throw new Error('Jupyter kernel sessions are available only in the BEAST desktop shell.');
    patchRuntime('notebook',{status:'starting-kernel',error:'',kernelStatus:'starting'});
    const summary=await desktop().startNotebookKernel(root());
    const prior=notebookKernel;notebookKernel={...summary,...prior,status:prior?.status==='ready'||summary.status==='running'?'ready':'starting'};
    if (notebookKernel.status!=='ready') {
      notebookKernelReady=new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('Jupyter kernel startup timed out.')),25000);notebookKernel.resolve=()=>{clearTimeout(timer);resolve(notebookKernel);};notebookKernel.reject=error=>{clearTimeout(timer);reject(error);};});
      await notebookKernelReady;
    }
    patchRuntime('notebook',{status:'kernel-ready',kernelStatus:'ready',kernel:'beast-python'});
    BeastStore.addLedger('Jupyter kernel ready: BEAST Python');
    return notebookKernel;
  }

  async function stopNotebookKernel() {
    if (desktop()?.stopNotebookKernel) await desktop().stopNotebookKernel();
    notebookKernel=null;notebookKernelReady=null;
    patchRuntime('notebook',{status:'idle',kernelStatus:'stopped',kernel:''});
  }

  async function runPythonCell(code) {
    if (!desktop()?.executeNotebookCell) throw new Error('Notebook execution is available only in the BEAST desktop shell.');
    patchRuntime('notebook',{status:'running',error:''});
    try {
      let result;
      if (desktop()?.requestNotebookKernel) {
        await ensureNotebookKernel();
        result=await desktop().requestNotebookKernel({operation:'execute',code:String(code || ''),timeout:60});
        result={...result,stdout:(result.outputs||[]).map(item=>item.text||item.evalue||'').join(''),stderr:(result.outputs||[]).filter(item=>item.type==='error').map(item=>`${item.ename||'Error'}: ${item.evalue||''}\n${(item.traceback||[]).join('\n')}`).join('\n'),returncode:result.ok?0:1};
      } else result=await desktop().executeNotebookCell({language:'python',code,timeoutMs:30000});
      const cells=[{id:result.receipt?.id || `NB-${Date.now()}`,code:String(code || ''),...result,at:Date.now()},...(runtime().notebook?.cells || [])].slice(0,12);
      patchRuntime('notebook',{status:result.ok?'complete':'failed',error:result.error || '',cells,lastReceipt:result.receipt || null});
      BeastStore.addLedger(`Notebook cell ${result.ok?'completed':'failed'}: ${result.receipt?.id || 'unreceipted'}`);
      return result;
    } catch (error) { patchRuntime('notebook',{status:'error',error:String(error.message || error)}); throw error; }
  }

  async function probeRemote({host,path}) {
    if (!desktop()?.probeRemote) throw new Error('Remote development is available only in the BEAST desktop shell.');
    patchRuntime('remote',{status:'connecting',host:String(host || ''),path:String(path || '~'),error:'',files:[]});
    try {
      const result=await desktop().probeRemote({host,path});
      if(result.target)BeastDesktopBridge.setExecutionTarget(result.target);
      patchRuntime('remote',{status:result.ok?'connected':'error',host:result.host || host,path:result.remote_root || path,remoteRoot:result.remote_root || '',error:result.error || '',verification:result.verification || '',lastProbe:result,target:result.target||null});
      if (result.ok) BeastStore.addLedger(`Remote SSH verified: ${result.host} · ${result.remote_root}`);
      return result;
    } catch (error) { patchRuntime('remote',{status:'error',error:String(error.message || error)}); throw error; }
  }

  async function listRemoteFiles() {
    const remote=runtime().remote || {};
    if (!remote.host || !remote.path) throw new Error('Connect a remote workspace before listing files.');
    patchRuntime('remote',{status:'indexing',error:''});
    try {
      const result=await desktop().listRemoteFiles({host:remote.host,path:remote.path});
      patchRuntime('remote',{status:result.ok?'connected':'error',files:result.files || [],error:result.error || '',lastList:result});
      return result;
    } catch (error) { patchRuntime('remote',{status:'error',error:String(error.message || error)}); throw error; }
  }
  async function openRemoteWorkspaceFile(filePath) {
    const remote=runtime().remote || {};const target=String(filePath || '').trim();
    if (!remote.host || !target) throw new Error('Connect a remote workspace and select a file first.');
    await BeastEditorCortex.openFile(BeastDesktopBridge.remoteRef(remote.host,target));
    BeastStore.addLedger(`Remote file opened: ${target} · ${remote.host}`);
    await BeastRouter.navigate('workspace');
  }
  async function searchRemoteWorkspace(query) {
    const remote=runtime().remote || {};if(!remote.host||!remote.path)throw new Error('Connect a remote workspace before searching.');if(!desktop()?.searchRemoteWorkspace)throw new Error('Remote search is available only in the BEAST desktop shell.');
    patchRuntime('remote',{searchStatus:'searching',searchError:'',searchResults:[]});
    try { const result=await desktop().searchRemoteWorkspace({host:remote.host,path:remote.path,query:String(query||'')});patchRuntime('remote',{searchStatus:result.ok?'complete':'error',searchError:result.error||'',searchResults:result.results||[],lastSearch:result});if(result.ok)BeastStore.addLedger(`Remote search: ${result.results?.length||0} result(s) · ${remote.host}`);return result; }
    catch(error){patchRuntime('remote',{searchStatus:'error',searchError:String(error.message||error)});throw error;}
  }
  async function reconnectRemote() {
    if(!desktop()?.reconnectRemote) throw new Error('Remote reconnect is available only in the BEAST desktop shell.');
    patchRuntime('remote',{status:'reconnecting',error:''});const result=await desktop().reconnectRemote();patchRuntime('remote',{status:result.ok?'connected':'error',host:result.host||runtime().remote?.host||'',path:result.remote_root||result.path||runtime().remote?.path||'~',remoteRoot:result.remote_root||'',verification:result.verification||'',error:result.error||''});if(result.ok){await Promise.allSettled([listRemoteFiles(),refreshRemoteTerminals(),refreshRemoteForwards(),refreshExecutionTargets()]);BeastStore.addLedger(`Remote workspace rehydrated: ${result.host||runtime().remote?.host}`);}return result;
  }
  async function runRemoteTerminal(command) {
    const remote=runtime().remote||{};if(!remote.host)throw new Error('Connect a remote workspace before running a remote command.');if(!desktop()?.runRemoteTerminal)throw new Error('Remote terminal is available only in the BEAST desktop shell.');patchRuntime('remote',{terminalStatus:'running',terminalError:'',terminalOutput:''});try{const result=await desktop().runRemoteTerminal({host:remote.host,command,timeoutMs:30000});patchRuntime('remote',{terminalStatus:result.ok?'complete':'failed',terminalError:result.error||'',terminalOutput:`${result.stdout||''}${result.stderr?`\n[stderr]\n${result.stderr}`:''}`,lastRemoteReceipt:result.receipt||null});return result;}catch(error){patchRuntime('remote',{terminalStatus:'error',terminalError:String(error.message||error)});throw error;}
  }
  async function refreshRemoteTerminals() {
    if (!desktop()?.listRemoteTerminals) return [];
    const result=await desktop().listRemoteTerminals();const terminals=result.terminals || [];
    patchRuntime('remote',{terminals});return terminals;
  }
  async function startRemoteTerminal({shell='bash'}={}) {
    const remote=runtime().remote||{};if(!remote.host||!remote.path)throw new Error('Connect a remote workspace before starting a terminal.');if(!desktop()?.startRemoteTerminal)throw new Error('Persistent remote terminals are available only in the BEAST desktop shell.');
    patchRuntime('remote',{terminalStatus:'starting',terminalError:''});
    try { const result=await desktop().startRemoteTerminal({host:remote.host,path:remote.path,shell});const terminals=await refreshRemoteTerminals();const terminal=result.terminal||{};patchRuntime('remote',{terminalStatus:'running',terminalError:'',terminalId:terminal.id||'',terminals,terminalOutput:runtime().remote?.terminalOutput||''});BeastStore.addLedger(`Remote terminal connected: ${terminal.host||remote.host} · ${terminal.cwd||remote.path}`);return result; }
    catch(error){patchRuntime('remote',{terminalStatus:'error',terminalError:String(error.message||error)});throw error;}
  }
  async function sendRemoteTerminal(input) {
    const remote=runtime().remote||{};const id=remote.terminalId||remote.terminals?.find(item=>item.status==='running')?.id;if(!id)throw new Error('Start a persistent remote terminal first.');if(!desktop()?.sendRemoteTerminal)throw new Error('Persistent remote terminals are available only in the BEAST desktop shell.');
    const result=await desktop().sendRemoteTerminal({id,input:String(input||'')});patchRuntime('remote',{terminalStatus:'running',terminalError:'',terminalId:id});return result;
  }
  async function stopRemoteTerminal(id='') {
    const remote=runtime().remote||{};const target=id||remote.terminalId;if(!target||!desktop()?.stopRemoteTerminal)return;await desktop().stopRemoteTerminal(target);const terminals=await refreshRemoteTerminals();patchRuntime('remote',{terminalStatus:'stopped',terminalId:'',terminals});BeastStore.addLedger('Remote terminal disconnected.');
  }
  async function refreshTerminalSessions() { if(!desktop()?.listTerminalSessions)return []; const result=await desktop().listTerminalSessions();const terminals=result.terminals||[];patchRuntime('terminal',{sessions:terminals});return terminals; }
  async function startTerminalSession({cwd='',shell='bash'}={}) { if(!desktop()?.startTerminalSession)throw new Error('Integrated terminal sessions are available only in the BEAST desktop shell.');patchRuntime('terminal',{sessionStatus:'starting',sessionError:''});try{const result=await desktop().startTerminalSession({rootId:'',cwd,shell});await refreshTerminalSessions();patchRuntime('terminal',{sessionStatus:'running',sessionId:result.terminal?.id||'',sessionError:''});return result;}catch(error){patchRuntime('terminal',{sessionStatus:'error',sessionError:String(error.message||error)});throw error;} }
  async function sendTerminalSession(input) { const state=runtime().terminal||{};const id=state.sessionId||state.sessions?.find(item=>item.status==='running')?.id;if(!id||!desktop()?.sendTerminalSession)throw new Error('Start an integrated terminal session first.');const result=await desktop().sendTerminalSession({id,input:String(input||'')});patchRuntime('terminal',{sessionStatus:'running',sessionId:id});return result; }
  async function stopTerminalSession(id='') { const state=runtime().terminal||{};const target=id||state.sessionId;if(!target||!desktop()?.stopTerminalSession)return;await desktop().stopTerminalSession(target);await refreshTerminalSessions();patchRuntime('terminal',{sessionStatus:'stopped',sessionId:''}); }

  async function refreshRemoteForwards() {
    if (!desktop()?.listRemoteForwards) return [];
    const result=await desktop().listRemoteForwards();
    const forwards=result.forwards || [];
    patchRuntime('remote',{forwards});
    return forwards;
  }

  async function startRemoteForward({direction='local',localPort,remotePort,targetHost='127.0.0.1'}={}) {
    const remote=runtime().remote || {};
    if (!remote.host) throw new Error('Verify and connect an SSH workspace before creating a forward.');
    if (!desktop()?.startRemoteForward) throw new Error('SSH forwarding is available only in the BEAST desktop shell.');
    patchRuntime('remote',{forwardStatus:'starting',forwardError:''});
    try {
      const result=await desktop().startRemoteForward({host:remote.host,direction,localPort,remotePort,targetHost});
      const forwards=await refreshRemoteForwards();
      patchRuntime('remote',{forwardStatus:'running',forwardError:'',forwards,lastForward:result.forward || null});
      const forward=result.forward || {}; BeastStore.addLedger(`SSH ${forward.direction==='reverse'?'reverse tunnel':'port forward'} started: ${forward.host} · ${forward.url}`);
      return result;
    } catch (error) { patchRuntime('remote',{forwardStatus:'error',forwardError:String(error.message || error)}); throw error; }
  }

  async function stopRemoteForward(id) {
    if (!desktop()?.stopRemoteForward) return;
    await desktop().stopRemoteForward(id);
    await refreshRemoteForwards();
    patchRuntime('remote',{forwardStatus:'stopped'});
    BeastStore.addLedger('SSH port forward stopped.');
  }

  async function refreshExecutionTargets() {
    const result=await BeastDesktopBridge.listExecutionTargets?.({rootId:''});
    patchRuntime('remote',{executionTargets:result?.targets||[],activeTarget:result?.active||executionTarget()});
    return result;
  }

  async function setExecutionTarget(target) {
    const selected=BeastDesktopBridge.setExecutionTarget(target || {kind:'local'});
    patchRuntime('remote',{activeTarget:selected});
    await refreshExecutionTargets().catch(()=>{});
    return selected;
  }

  async function inspectDevContainers() {
    if(!desktop()?.inspectDevContainers)throw new Error('Dev Containers are available only in the BEAST desktop shell.');
    patchRuntime('remote',{containerStatus:'inspecting',containerError:''});
    const result=await desktop().inspectDevContainers({root:root()});
    patchRuntime('remote',{containerStatus:result.ok?'ready':'error',containerError:result.error||'',devContainers:result.containers||[],devContainerConfig:result.config||null,workspaceKey:result.workspaceKey||''});
    await refreshExecutionTargets().catch(()=>{});
    return result;
  }
  async function startDevContainer() {
    if(!desktop()?.startDevContainer)throw new Error('Dev Container start is available only in the BEAST desktop shell.');
    patchRuntime('remote',{containerStatus:'starting',containerError:''});
    const result=await desktop().startDevContainer({root:root()});
    if(result.target)BeastDesktopBridge.setExecutionTarget(result.target);
    patchRuntime('remote',{containerStatus:result.ok?'attached':'error',containerError:result.error||'',devContainers:result.containers||[],activeTarget:result.target||executionTarget(),devContainerAttached:result.attached||null});
    BeastStore.addLedger(result.ok?`Dev Container attached: ${result.attached?.name||result.attached?.id||'container'}`:`Dev Container start failed: ${result.error||'unknown'}`);
    await refreshExecutionTargets().catch(()=>{});
    return result;
  }
  async function attachDevContainer(id='') {
    if(!desktop()?.attachDevContainer)throw new Error('Dev Container attach is available only in the BEAST desktop shell.');
    const result=await desktop().attachDevContainer({root:root(),id});
    if(result.target)BeastDesktopBridge.setExecutionTarget(result.target);
    patchRuntime('remote',{containerStatus:result.ok?'attached':'error',containerError:result.error||'',devContainers:result.containers||[],activeTarget:result.target||executionTarget(),devContainerAttached:result.attached||null});
    await refreshExecutionTargets().catch(()=>{});
    return result;
  }
  async function stopDevContainer(id='') {
    if(!desktop()?.stopDevContainer)throw new Error('Dev Container stop is available only in the BEAST desktop shell.');
    const result=await desktop().stopDevContainer({root:root(),id});
    if(executionTarget().kind==='container')BeastDesktopBridge.setExecutionTarget({kind:'local'});
    patchRuntime('remote',{containerStatus:result.ok?'stopped':'error',containerError:result.error||'',devContainers:result.containers||[],activeTarget:executionTarget()});
    await refreshExecutionTargets().catch(()=>{});
    return result;
  }
  async function rebuildDevContainer() {
    if(!desktop()?.rebuildDevContainer)throw new Error('Dev Container rebuild is available only in the BEAST desktop shell.');
    patchRuntime('remote',{containerStatus:'rebuilding',containerError:''});
    const result=await desktop().rebuildDevContainer({root:root()});
    if(result.target)BeastDesktopBridge.setExecutionTarget(result.target);
    patchRuntime('remote',{containerStatus:result.ok?'attached':'error',containerError:result.error||'',devContainers:result.containers||[],activeTarget:result.target||executionTarget(),devContainerAttached:result.attached||null});
    await refreshExecutionTargets().catch(()=>{});
    return result;
  }
  async function devContainerLogs(id='') {
    if(!desktop()?.devContainerLogs)throw new Error('Dev Container logs are available only in the BEAST desktop shell.');
    const result=await desktop().devContainerLogs({root:root(),id});
    patchRuntime('remote',{containerLogs:result.logs||'',containerError:result.error||''});
    return result;
  }
  async function runDevContainerTerminal(command,id='') {
    if(!desktop()?.runDevContainerTerminal)throw new Error('Dev Container terminal is available only in the BEAST desktop shell.');
    patchRuntime('remote',{containerTerminalStatus:'running',containerTerminalOutput:'',containerError:''});
    const result=await desktop().runDevContainerTerminal({root:root(),id,command});
    patchRuntime('remote',{containerTerminalStatus:result.ok?'complete':'failed',containerTerminalOutput:`${result.stdout||''}${result.stderr?`\n[stderr]\n${result.stderr}`:''}`,containerError:result.error||'',lastContainerReceipt:result.receipt||null});
    return result;
  }

  function patchExtensions(summary={}) { patchRuntime('extensions',{status:summary.status || 'stopped',pid:summary.pid || null,mode:summary.mode || 'declarative-manifests',items:summary.extensions || [],error:''}); }
  async function discoverExtensions() {
    if (!desktop()?.discoverExtensions) throw new Error('Extension runtime is available only in the BEAST desktop shell.');
    patchRuntime('extensions',{status:'starting',error:''});
    try { const summary=await desktop().discoverExtensions(root());patchExtensions(summary);BeastStore.addLedger(`Extension host ready: ${(summary.extensions || []).length} manifest(s)`);return summary; }
    catch (error) { patchRuntime('extensions',{status:'error',error:String(error.message || error)});throw error; }
  }
  async function grantExtensionCapabilities(id, capabilities) {
    if (!desktop()?.grantExtensionCapabilities) throw new Error('Extension grants are available only in the BEAST desktop shell.');
    const summary=await desktop().grantExtensionCapabilities({id,capabilities});patchExtensions(summary);BeastStore.addLedger(`Extension capability grants updated: ${id}`);return summary;
  }
  async function setExtensionEnabled(id, enabled) { if(!desktop()?.setExtensionEnabled)throw new Error('Extension lifecycle controls are available only in the BEAST desktop shell.');const summary=await desktop().setExtensionEnabled({id,enabled:Boolean(enabled)});patchExtensions(summary);BeastStore.addLedger(`Extension ${enabled?'enabled':'disabled'}: ${id}`);return summary; }
  async function installWorkspaceExtension() { if(!desktop()?.installWorkspaceExtension)throw new Error('Extension installation is available only in the BEAST desktop shell.');const summary=await desktop().installWorkspaceExtension();patchExtensions(summary);BeastStore.addLedger('Workspace extension install completed.');return summary; }
  async function uninstallWorkspaceExtension(id) { if(!desktop()?.uninstallWorkspaceExtension)throw new Error('Extension removal is available only in the BEAST desktop shell.');const summary=await desktop().uninstallWorkspaceExtension({id});patchExtensions(summary);BeastStore.addLedger(`Workspace extension removed: ${id}`);return summary; }
  async function executeExtensionCommand(id, command) {
    if (!desktop()?.executeExtensionCommand) throw new Error('Extension commands are available only in the BEAST desktop shell.');
    const result=await desktop().executeExtensionCommand({id,command,target:executionTarget()});
    for (const action of result.actions||[]) {
      if (action.kind==='navigate'&&action.payload?.route) await BeastRouter.navigate(action.payload.route);
      if (action.kind==='notice') { const message=String(action.payload?.message||'Extension notice');BeastStore.addLedger(`Extension ${id}: ${message}`);document.dispatchEvent(new CustomEvent('beast:operation',{detail:{message,tone:action.payload?.severity==='error'?'bad':action.payload?.severity==='warning'?'warn':'ok'}})); }
      if (action.kind==='command') BeastStore.addLedger(`Extension ${id} requested mediated command: ${action.payload?.id||'unknown'}`);
    }
    BeastStore.addLedger(`Extension command completed: ${id} · ${command}`);
    return result;
  }
  async function stopExtensionHost() { if (desktop()?.stopExtensionHost) await desktop().stopExtensionHost();patchRuntime('extensions',{status:'stopped',pid:null}); }

  function appendDebugOutput(value,category='console') {
    const debug=runtime().debug || {};
    const output=[...(debug.output || []),{text:String(value || ''),category,at:Date.now()}].slice(-120);
    patchRuntime('debug',{output});
  }

  function handleMessage(event={}) {
    const session=dapSessions.get(event.sessionId); if (!session) return;
    if (event.type==='ready') { session.ready=true;session.capabilities=event.capabilities||{};dapSessions.set(session.id,session); readyWaiters.get(session.id)?.resolve(); readyWaiters.delete(session.id); return; }
    if (event.type==='error') { const error=new Error(event.error || 'Debug adapter error');session.status='error';readyWaiters.get(session.id)?.reject(error); initializedWaiters.get(session.id)?.reject(error); readyWaiters.delete(session.id); initializedWaiters.delete(session.id);if(runtime().debug?.sessionId===session.id)patchRuntime('debug',{status:'error',error:error.message}); return; }
    if (event.type==='exit') { session.status='terminated';dapSessions.delete(event.sessionId);if(runtime().debug?.sessionId===session.id)patchRuntime('debug',{status:'terminated',sessionId:'',error:'Debug adapter disconnected; start Debug again to reconnect.'}); return; }
    const message=event.message || {};
    if (message.type!=='event') return;
    if (message.event==='initialized') { session.initialized=true; dapSessions.set(session.id,session); initializedWaiters.get(session.id)?.resolve(); initializedWaiters.delete(session.id); return; }
    if (message.event==='output') { appendDebugOutput(message.body?.output,message.body?.category || 'console'); return; }
    if (message.event==='stopped') { inspectStop(session,message.body || {}); return; }
    if (message.event==='continued') { patchRuntime('debug',{status:'running'}); return; }
    if (message.event==='terminated'||message.event==='exited') { patchRuntime('debug',{status:'terminated'}); BeastStore.addLedger('Debug session terminated.'); }
  }

  function handleNotebookKernelMessage(message={}) {
    if (message.type==='ready') { notebookKernel={...(notebookKernel||{}),status:'ready',pid:message.pid,kernel:message.kernel};notebookKernel?.resolve?.();return; }
    if (message.type==='fatal'||message.type==='error') { const error=new Error(message.error||'Notebook kernel failed');notebookKernel?.reject?.(error);patchRuntime('notebook',{status:'error',kernelStatus:'error',error:error.message});return; }
    if (message.type==='exit') { notebookKernel=null;patchRuntime('notebook',{kernelStatus:'stopped'}); }
  }

  function handleRemoteForwardMessage(message={}) {
    const forward=message.forward || {};
    if (message.type==='error'||message.type==='exit') patchRuntime('remote',{forwardStatus:'error',forwardError:message.error || `Forward ${forward.id || ''} stopped.`});
    else if (message.type==='started') patchRuntime('remote',{forwardStatus:'running',forwardError:''});
    refreshRemoteForwards().catch(()=>{});
  }
  function handleRemoteTerminalMessage(message={}) {
    const terminal=message.terminal||{};const remote=runtime().remote||{};const output=`${remote.terminalOutput||''}${message.text||''}`.slice(-256000);
    const terminals=(remote.terminals||[]).filter(item=>item.id!==terminal.id);if(terminal.id)terminals.unshift(terminal);
    if(message.type==='error'||message.type==='exit')patchRuntime('remote',{terminalStatus:'error',terminalError:message.error||'Remote terminal stopped.',terminalId:terminal.id||remote.terminalId||'',terminals,terminalOutput:output});
    else if(message.type==='stopped')patchRuntime('remote',{terminalStatus:'stopped',terminalId:'',terminals,terminalOutput:output});
    else patchRuntime('remote',{terminalStatus:'running',terminalError:'',terminalId:terminal.id||remote.terminalId||'',terminals,terminalOutput:output});
  }
  function handleTerminalSessionMessage(message={}) { const terminal=message.terminal||{};const state=runtime().terminal||{};const output=`${state.sessionOutput||''}${message.text||''}`.slice(-256000);const sessions=(state.sessions||[]).filter(item=>item.id!==terminal.id);if(terminal.id)sessions.unshift(terminal);patchRuntime('terminal',{sessionOutput:output,sessions,sessionId:message.type==='stopped'?'':terminal.id||state.sessionId||'',sessionStatus:message.type==='error'||message.type==='exit'?'error':message.type==='stopped'?'stopped':'running',sessionError:message.error||''}); }
  function handleExtensionHostMessage(message={}) {
    if (message.type==='error'||message.type==='exit') patchRuntime('extensions',{status:'error',error:message.error || 'Extension host stopped.'});
    if (message.type==='ready') patchRuntime('extensions',{status:'running',error:''});
  }

  desktop()?.onIdeProtocolMessage?.(handleMessage);
  desktop()?.onNotebookKernelMessage?.(handleNotebookKernelMessage);
  desktop()?.onRemoteForwardMessage?.(handleRemoteForwardMessage);
  desktop()?.onRemoteTerminalMessage?.(handleRemoteTerminalMessage);
  desktop()?.onTerminalSessionMessage?.(handleTerminalSessionMessage);
  desktop()?.onExtensionHostMessage?.(handleExtensionHostMessage);
  window.BeastIDERuntime={startDebug,startPythonDebug,startLaunchConfiguration,startCompound,loadLaunchConfigurations,debugControl,evaluateDebug,addWatchExpression,removeWatchExpression,runPythonCell,ensureNotebookKernel,stopNotebookKernel,probeRemote,listRemoteFiles,openRemoteWorkspaceFile,searchRemoteWorkspace,reconnectRemote,runRemoteTerminal,refreshRemoteTerminals,startRemoteTerminal,sendRemoteTerminal,stopRemoteTerminal,refreshTerminalSessions,startTerminalSession,sendTerminalSession,stopTerminalSession,refreshRemoteForwards,startRemoteForward,stopRemoteForward,refreshExecutionTargets,setExecutionTarget,inspectDevContainers,startDevContainer,attachDevContainer,stopDevContainer,rebuildDevContainer,devContainerLogs,runDevContainerTerminal,discoverExtensions,grantExtensionCapabilities,setExtensionEnabled,installWorkspaceExtension,uninstallWorkspaceExtension,executeExtensionCommand,stopExtensionHost};
})();
