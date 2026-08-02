(() => {
  const demoMode = new URLSearchParams(location.search).get('demo') === '1' || new URLSearchParams(location.search).get('capture') === '1';
  let stream = null;
  let demoTimer = null;
  let toolingPromise = null;
  let doctorPromise = null;

  const terminalHistoryKey = () => `beast.v2.terminal.history:${BeastStore.get().workspace.root || 'workspace'}`;
  const terminalExecutionsKey = () => `beast.v2.terminal.executions:${BeastStore.get().workspace.root || 'workspace'}`;
  const gatewayUrl = () => BeastStore.get().connection.gatewayUrl || window.gatewayUrl || 'http://127.0.0.1:8000';
  const root = () => BeastStore.get().workspace.root || '';
  const activeFile = () => BeastStore.get().editor.activePath || BeastStore.get().workspace.selectedPath || '';
  const nowLabel = () => new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'});

  function timeoutSignal(signal, timeoutMs = 6000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort('timeout'), timeoutMs);
    if (signal) signal.addEventListener('abort', () => controller.abort(signal.reason), {once:true});
    return { signal: controller.signal, done: () => clearTimeout(timer) };
  }

  async function fetchJson(path, options = {}) {
    const target = new URL(path, gatewayUrl());
    const t = timeoutSignal(options.signal, options.timeoutMs || 6000);
    try {
      const response = await fetch(target, {
        method: options.method || 'GET',
        headers: options.body ? {'Content-Type':'application/json'} : undefined,
        body: options.body ? JSON.stringify(options.body) : undefined,
        signal: t.signal
      });
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`.trim());
      return await response.json();
    } finally { t.done(); }
  }

  async function safeGet(path, timeoutMs = 4500) {
    try { return {ok:true, data:await fetchJson(path,{timeoutMs})}; }
    catch (error) { return {ok:false, error:String(error.message || error)}; }
  }

  async function safePost(path, body, timeoutMs = 10000) {
    try { return {ok:true, data:await fetchJson(path,{method:'POST',body,timeoutMs})}; }
    catch (error) { return {ok:false, error:String(error.message || error)}; }
  }

  function loadTerminalState() {
    let history = [];
    let executions = [];
    try { history = JSON.parse(localStorage.getItem(terminalHistoryKey()) || '[]').filter(Boolean).slice(0,80); } catch (_) {}
    try { executions = JSON.parse(localStorage.getItem(terminalExecutionsKey()) || '[]').filter(Boolean).slice(0,30); } catch (_) {}
    BeastStore.patch('terminal', {
      history,
      executions,
      lastReceipt: executions[0] || null,
      cwd: BeastStore.get().terminal.cwd || root() || ''
    });
  }

  function rememberCommand(command) {
    const clean = String(command || '').trim();
    if (!clean) return;
    const state = BeastStore.get().terminal;
    const history = [clean, ...state.history.filter(item => item !== clean)].slice(0,80);
    localStorage.setItem(terminalHistoryKey(), JSON.stringify(history));
    BeastStore.patch('terminal',{history,command:clean});
  }

  function recordExecution(result = {}) {
    const terminal = BeastStore.get().terminal;
    const item = {
      at: new Date().toISOString(),
      ok: Boolean(result.ok),
      command: result.command || terminal.command,
      cwd: result.cwd || terminal.cwd || root(),
      returncode: result.returncode,
      duration_ms: result.duration_ms ?? terminal.durationMs,
      decision: result.safety?.decision || terminal.decision || '',
      risk: result.safety?.risk_level || terminal.risk || '',
      evidence_receipt: result.evidence_receipt || result.receipt || null,
      stdout: String(result.stdout || '').slice(-16000),
      stderr: String(result.stderr || result.error || '').slice(-8000),
      error: result.error || ''
    };
    const executions = [item, ...terminal.executions].slice(0,30);
    localStorage.setItem(terminalExecutionsKey(),JSON.stringify(executions));
    BeastStore.patch('terminal',{executions,lastReceipt:item,returncode:item.returncode,durationMs:item.duration_ms || 0});
    return item;
  }

  async function classify(command, options = {}) {
    const clean = String(command || '').trim();
    if (!clean) throw new Error('Enter a command before classification.');
    rememberCommand(clean);
    BeastStore.patch('terminal',{status:'classifying',error:'',command:clean,cwd:options.cwd || BeastStore.get().terminal.cwd || root()});
    if (demoMode) {
      const dangerous = /\b(rm\s+-rf|mkfs|shutdown|reboot|dd\s+if=|:(){)/i.test(clean);
      const warn = /\b(kill|docker\s+rm|npm\s+install|pip\s+install|sudo)\b/i.test(clean);
      const decision = dangerous ? 'block' : warn ? 'require_approval' : 'allow';
      const receipt = {
        command:clean, decision, risk_level:dangerous?'critical':warn?'medium':'low',
        reasons:[dangerous?'Destructive command signature matched.':warn?'Mutation requires explicit operator approval.':'Command is read-only or low-risk within the active workspace.']
      };
      BeastStore.patch('terminal',{status:'classified',decision:receipt.decision,risk:receipt.risk_level,reasons:receipt.reasons,error:''});
      BeastStore.addLedger(`Terminal classified ${decision}: ${clean}`);
      return receipt;
    }
    const result = await safePost('/edgek/safety-governor/classify-command', {
      root_path:root(), command:clean, mode:'operator', task_id:options.taskId || ''
    },7000);
    if (!result.ok) {
      BeastStore.patch('terminal',{status:'error',error:result.error,decision:'',risk:'',reasons:[]});
      throw new Error(result.error);
    }
    const receipt = result.data || {};
    const reasons = (receipt.reasons || receipt.findings || []).map(item => typeof item === 'string' ? item : item.detail || item.reason || JSON.stringify(item)).slice(0,8);
    BeastStore.patch('terminal',{
      status:'classified', decision:receipt.decision || receipt.status || 'allow', risk:receipt.risk_level || 'unknown', reasons, error:''
    });
    BeastStore.addLedger(`Terminal classified ${receipt.decision || receipt.status || 'allow'}: ${clean}`);
    return receipt;
  }

  function appendOutput(text, channel='stdout') {
    const terminal = BeastStore.get().terminal;
    const key = channel === 'stderr' ? 'stderr' : 'stdout';
    BeastStore.patch('terminal',{[key]:`${terminal[key] || ''}${text}`.slice(key === 'stderr' ? -12000 : -30000)});
  }

  function simulateTerminal(command, options = {}) {
    cancel(false);
    const lines = [
      `[${nowLabel()}] GOVERNOR  decision=${BeastStore.get().terminal.decision || 'allow'} risk=${BeastStore.get().terminal.risk || 'low'}\n`,
      `[${nowLabel()}] CONTEXT   cwd=${options.cwd || root() || '/demo/BEAST'}\n`,
      `[${nowLabel()}] EXECUTE   ${command}\n`,
      `[${nowLabel()}] CORE      workspace integrity ........ OK\n`,
      `[${nowLabel()}] ROUTE     local tools ................. READY\n`,
      `[${nowLabel()}] EVIDENCE  receipt staging ............. OK\n`,
      `[${nowLabel()}] RESULT    command completed ............ 0\n`
    ];
    let index=0;
    BeastStore.patch('terminal',{streaming:true,status:'streaming',stdout:'',stderr:'',startedAt:Date.now(),returncode:null,error:''});
    BeastMascot.setState('working');
    demoTimer=setInterval(() => {
      appendOutput(lines[index] || '');
      index += 1;
      if (index >= lines.length) {
        clearInterval(demoTimer); demoTimer=null;
        const duration=Date.now()-BeastStore.get().terminal.startedAt;
        const result={ok:true,command,cwd:options.cwd || root(),returncode:0,duration_ms:duration,stdout:BeastStore.get().terminal.stdout,evidence_receipt:{receipt_id:`TERM-DEMO-${Date.now()}`}};
        BeastStore.patch('terminal',{streaming:false,status:'complete',returncode:0,durationMs:duration});
        recordExecution(result);
        BeastStore.addLedger(`Terminal execution complete: ${command}`);
        BeastMascot.setState('finished');
        BeastFX.trigger('success',document.querySelector('[data-terminal-console]'),{size:260});
      }
    },180);
  }

  async function execute(command, options = {}) {
    const clean=String(command || '').trim();
    if (!clean) throw new Error('Enter a command before execution.');
    let decision=BeastStore.get().terminal.decision;
    if (!decision || BeastStore.get().terminal.command !== clean) {
      const receipt=await classify(clean,options);
      decision=receipt.decision || receipt.status || 'allow';
    }
    if (decision === 'block') throw new Error('Safety Governor blocked this command.');
    let approved=Boolean(options.approved);
    let override='';
    if (['warn','require_approval','sandbox/worktree_only'].includes(decision) && !approved) {
      approved=window.confirm(`Safety decision: ${decision}. Execute with an evidence-logged operator override?`);
      if (!approved) return false;
      override=`Approved from BEAST Phase 7 after ${decision}`;
    }
    rememberCommand(clean);
    if (demoMode) { simulateTerminal(clean,{...options,approved,override}); return true; }
    cancel(false);
    const params=new URLSearchParams({
      command:clean,
      cwd:options.cwd || BeastStore.get().terminal.cwd || root(),
      mode:'operator',
      approved:String(approved),
      operator_override:override,
      timeout:String(Number(options.timeout || BeastStore.get().terminal.timeout || 120))
    });
    if (root()) params.set('root_path',root());
    BeastStore.patch('terminal',{streaming:true,status:'streaming',stdout:'',stderr:'',startedAt:Date.now(),returncode:null,error:'',command:clean,cwd:params.get('cwd')});
    BeastMascot.setState('working');
    stream=new EventSource(`${gatewayUrl()}/edgek/ide/terminal/stream?${params.toString()}`);
    stream.addEventListener('chunk',event => {
      const payload=JSON.parse(event.data || '{}');
      appendOutput(payload.text || '',payload.stream);
    });
    stream.addEventListener('heartbeat',event => {
      const payload=JSON.parse(event.data || '{}');
      BeastStore.patch('terminal',{durationMs:Number(payload.elapsed_ms || 0)});
    });
    stream.addEventListener('done',event => {
      const payload=JSON.parse(event.data || '{}');
      if (stream) stream.close(); stream=null;
      const duration=payload.duration_ms ?? Date.now()-BeastStore.get().terminal.startedAt;
      BeastStore.patch('terminal',{streaming:false,status:payload.ok?'complete':'failed',returncode:payload.returncode,durationMs:duration,error:payload.error || ''});
      recordExecution({...payload,command:clean,cwd:params.get('cwd'),stdout:BeastStore.get().terminal.stdout,stderr:BeastStore.get().terminal.stderr});
      BeastStore.addLedger(`Terminal ${payload.ok?'complete':'failed'}: ${clean}`);
      BeastMascot.setState(payload.ok?'finished':'alert');
    });
    stream.addEventListener('error',event => {
      if (stream) stream.close(); stream=null;
      let error='Terminal stream failed or closed.';
      try { if (event.data) error=JSON.parse(event.data).error || error; } catch (_) {}
      BeastStore.patch('terminal',{streaming:false,status:'error',error});
      recordExecution({ok:false,command:clean,cwd:params.get('cwd'),error,stdout:BeastStore.get().terminal.stdout,stderr:BeastStore.get().terminal.stderr});
      BeastMascot.setState('alert');
    });
    return true;
  }

  function cancel(record=true) {
    if (stream) { stream.close(); stream=null; }
    if (demoTimer) { clearInterval(demoTimer); demoTimer=null; }
    const terminal=BeastStore.get().terminal;
    if (terminal.streaming) {
      BeastStore.patch('terminal',{streaming:false,status:'cancelled',error:'Cancelled by operator.'});
      if (record) recordExecution({ok:false,command:terminal.command,cwd:terminal.cwd,error:'Cancelled by operator.',stdout:terminal.stdout,stderr:terminal.stderr});
      BeastMascot.setState('idle');
    }
  }

  function clearOutput() { BeastStore.patch('terminal',{stdout:'',stderr:'',error:'',returncode:null,durationMs:0,status:'idle'}); }
  function clearHistory() { localStorage.removeItem(terminalHistoryKey()); BeastStore.patch('terminal',{history:[]}); }
  function setCommand(command) { BeastStore.patch('terminal',{command:String(command || '')}); }
  function setCwd(cwd) { BeastStore.patch('terminal',{cwd:String(cwd || '')}); }
  function setTimeoutSeconds(value) { BeastStore.patch('terminal',{timeout:Math.max(5,Math.min(900,Number(value)||120))}); }
  async function copyReceipt() {
    const receipt=BeastStore.get().terminal.lastReceipt;
    if (!receipt) return false;
    await navigator.clipboard?.writeText(JSON.stringify(receipt,null,2));
    BeastStore.addLedger('Terminal execution receipt copied');
    return true;
  }

  function normalizeTooling(snapshot={},extras={}) {
    const syntax=snapshot.syntax || {};
    const linting=snapshot.linting || {};
    const mcp={...(snapshot.mcp || {}),...(extras.mcpState?.data || {})};
    const pluginsPayload=extras.plugins?.data || {};
    const plugins={...(snapshot.plugins || {}), count:(pluginsPayload.plugins || []).length || snapshot.plugins?.count || 0, items:pluginsPayload.plugins || snapshot.plugins?.items || []};
    const environments=Array.isArray(snapshot.environments) ? snapshot.environments : [];
    return {
      status:snapshot.status || (snapshot.ok===false?'warning':'ready'),
      source:snapshot.source || (extras.local?'electron':'gateway'), syntax, linting, mcp, plugins, environments,
      catalog:snapshot.catalog || extras.catalog?.data || {},
      servers:extras.servers?.data?.servers || [], approvals:extras.approvals?.data?.approvals || [],
      schemaPins:extras.pins?.data?.schema_pins || [], audit:extras.audit?.data?.events || extras.audit?.data?.entries || [],
      executions:extras.executions?.data?.executions || [], actions:extras.actions?.data?.actions || extras.actions?.data?.items || [],
      raw:{snapshot,extras}
    };
  }

  function demoTooling() {
    return {
      status:'ready', source:'demo runtime',
      syntax:{status:'passed',kind:'Python / JS',path:activeFile() || 'src/core/router.py',detail:'No syntax defects detected.'},
      linting:{has_root_lint:true,has_desktop_smoke:true,recommendation:'Run lint and smoke before applying SourcePlan.',scripts:{root:['lint','test'],desktop:['smoke','check'] }},
      mcp:{status:'healthy',configured:true,registered_servers:4,pending_approvals:1,executions:{executed:18,blocked:2}},
      plugins:{status:'healthy',count:6,items:[{name:'Code Graph',risk_class:'low',tools:['graph']},{name:'Profiler',risk_class:'low',tools:['profile']},{name:'Evidence Parser',risk_class:'governed',tools:['parse','verify']}]},
      environments:[{command:'python',version:'Python 3.13.5',ok:true},{command:'node',version:'v24.3.0',ok:true},{command:'npm',version:'11.4.2',ok:true},{command:'git',version:'2.48.1',ok:true}],
      catalog:{summary:{tools:14,tools_installed:12,mcp_runners_available:4,vscode_extensions:1}},
      servers:[{name:'filesystem',status:'ready'},{name:'github',status:'ready'},{name:'postgres',status:'ready'},{name:'code-graph',status:'ready'}],
      approvals:[{request_id:'MCP-APR-001',status:'pending',tool:'filesystem.write'}],
      schemaPins:[{server:'filesystem',schema:'2026-07'},{server:'code-graph',schema:'v2'}],
      audit:[{time:nowLabel(),label:'MCP broker checked'},{time:'14:28:11',label:'Plugin manifest validated'}],
      executions:[{tool:'code_graph.search',status:'ok'},{tool:'profiler.run',status:'ok'}],
      actions:[{id:'tooling.refresh',label:'Refresh Tooling'},{id:'tooling.syntax',label:'Syntax Check'},{id:'tooling.mcp_ops',label:'MCP Operations'}],
      raw:{demo:true}
    };
  }

  async function refreshTooling(options={}) {
    if (toolingPromise) return toolingPromise;
    toolingPromise=(async () => {
      BeastStore.patch('tooling',{loading:true,error:''});
      if (demoMode) {
        await new Promise(resolve => setTimeout(resolve,180));
        const data=demoTooling();
        BeastStore.patch('tooling',{...data,loading:false,error:'',updatedAt:Date.now()});
        BeastStore.addLedger('Tooling Forge refreshed from demo runtime');
        return data;
      }
      let snapshot=null;
      let local=false;
      if (window.beastDesktop?.toolingSnapshot) {
        try { snapshot=await window.beastDesktop.toolingSnapshot(root(),activeFile()); local=true; } catch (_) {}
      }
      if (!snapshot) {
        const params=new URLSearchParams();
        if (root()) params.set('root_path',root());
        if (activeFile()) params.set('active_file',activeFile());
        const response=await safeGet(`/edgek/ide/tooling-snapshot?${params}`,7000);
        if (response.ok) snapshot=response.data;
      }
      const extras={local};
      const endpoints={
        mcpState:'/edgek/mcp/state',servers:'/edgek/mcp/servers',pins:'/edgek/mcp/schema-pins?limit=50',
        approvals:'/edgek/mcp/approvals?limit=20',audit:'/edgek/mcp/audit?limit=20',executions:'/edgek/mcp/executions?limit=20',
        plugins:'/edgek/plugins',actions:'/edgek/ide/actions/manifest'
      };
      await Promise.all(Object.entries(endpoints).map(async ([key,path]) => { extras[key]=await safeGet(path,4500); }));
      if (!snapshot) snapshot={ok:false,status:'warning',source:'unavailable'};
      const data=normalizeTooling(snapshot,extras);
      const failures=Object.values(extras).filter(item => item && item.ok===false).length;
      BeastStore.patch('tooling',{...data,loading:false,error:snapshot.ok===false && failures ? `${failures} tooling route(s) unavailable.` : '',updatedAt:Date.now()});
      BeastStore.addLedger(`Tooling Forge refreshed · ${data.servers.length} MCP servers · ${data.plugins.count || 0} plugins`);
      return data;
    })().finally(() => { toolingPromise=null; });
    return toolingPromise;
  }

  async function validatePluginManifest(manifest) {
    let payload=manifest;
    if (!payload) {
      const raw=window.prompt('Paste plugin manifest JSON to validate');
      if (!raw) return null;
      try { payload=JSON.parse(raw); } catch (error) { throw new Error(`Invalid JSON: ${error.message}`); }
    }
    if (demoMode) return {valid:true,errors:[],manifest:payload};
    const result=await safePost('/edgek/plugins/manifest/validate',payload,7000);
    if (!result.ok) throw new Error(result.error);
    BeastStore.addLedger(`Plugin manifest ${result.data?.valid===false?'rejected':'validated'}`);
    await refreshTooling({force:true});
    return result.data;
  }

  async function resolveMcpApproval(id,decision) {
    if (!id) return null;
    if (!window.confirm(`${decision === 'approve' ? 'Approve' : 'Deny'} MCP request ${id}?`)) return null;
    if (demoMode) {
      BeastStore.transaction(next => { next.tooling.approvals=next.tooling.approvals.map(item => item.request_id===id?{...item,status:decision==='approve'?'approved':'denied'}:item); });
      return {ok:true,demo:true};
    }
    const result=await safePost(`/edgek/mcp/approvals/${encodeURIComponent(id)}/${decision}`,{reason:`${decision} from BEAST Phase 7`,operator:'beast_desktop'},7000);
    if (!result.ok) throw new Error(result.error);
    await refreshTooling({force:true});
    return result.data;
  }

  async function runBenchmark() {
    const packetDir=root()?`${root()}/benchmarks/results/full_blind_test_packet`:'/home/byron/EdgeK-BEAST/benchmarks/results/full_blind_test_packet';
    if (demoMode) {
      const benchmark={claim_status:'supported',structural_claim_status:'supported',packet_dir:packetDir};
      BeastStore.patch('tooling',{benchmark}); return benchmark;
    }
    const result=await safePost('/edgek/benchmarks/public-grading-daemon',{packet_dir:packetDir},20000);
    if (!result.ok) throw new Error(result.error);
    BeastStore.patch('tooling',{benchmark:result.data});
    BeastStore.addLedger(`Benchmark daemon: ${result.data?.claim_status || 'complete'}`);
    return result.data;
  }

  function demoDoctor() {
    const checks=[
      ['Gateway Core','online','127.0.0.1:8000'],['Capabilities','healthy','18 actions'],['Safety Governor','healthy','classification ready'],
      ['Tooling Snapshot','healthy','syntax + lint + environment'],['MCP Broker','warning','1 approval pending'],['Plugin Registry','healthy','6 installed'],
      ['Workspace Index','healthy','5 files indexed'],['Evidence Bus','healthy','receipts available']
    ].map(([label,status,detail],index)=>({id:`check-${index}`,label,status,detail,latency:index<2?'12ms':'n/a'}));
    return {
      score:94,status:'Excellent',checks,
      routes:checks.map(item=>({path:item.label,ok:item.status!=='offline',status:item.status,detail:item.detail})),
      system:{summary:{listening_ports:7,processes_total:42,python:'3.13.5',node_manifests:2,vscode_commands:18},ports:{ports:[{proto:'tcp',port:8000,address:'127.0.0.1',process:'uvicorn',pid:4312},{proto:'tcp',port:4000,address:'127.0.0.1',process:'litellm',pid:4401}]},processes:{processes:[{name:'BEAST Gateway',pid:4312,rss_mb:184,status:'healthy'},{name:'LiteLLM',pid:4401,rss_mb:226,status:'healthy'},{name:'Electron',pid:4200,rss_mb:312,status:'healthy'}]}},
      recommendations:[{tone:'warn',title:'Resolve MCP approval',detail:'One governed tool request is waiting for an operator decision.',action:'Open Tooling'},{tone:'good',title:'System nominal',detail:'No restart or repair action is required.',action:'Refresh'}]
    };
  }

  function makeCheck(id,label,result,detail='') {
    return {id,label,ok:Boolean(result?.ok),status:result?.ok?'healthy':'offline',detail:result?.ok ? (detail || 'route available') : (result?.error || 'unavailable'),latency:result?.latency || 'n/a'};
  }

  async function refreshDoctor() {
    if (doctorPromise) return doctorPromise;
    doctorPromise=(async () => {
      BeastStore.patch('doctor',{loading:true,error:''});
      BeastMascot.setState('working');
      if (demoMode) {
        await new Promise(resolve=>setTimeout(resolve,220));
        const data=demoDoctor();
        BeastStore.patch('doctor',{...data,loading:false,error:'',report:data,lastScanAt:Date.now()});
        BeastMascot.setState('finished');
        BeastStore.addLedger('Doctor deep scan complete · score 94%');
        return data;
      }
      const start=performance.now();
      const endpoints={
        rootInfo:'/edgek/root-info',snapshot:`/edgek/ide/snapshot?${new URLSearchParams({root_path:root(),objective:'doctor-scan'})}`,
        actions:'/edgek/ide/actions/manifest',tooling:`/edgek/ide/tooling-snapshot?${new URLSearchParams({root_path:root(),active_file:activeFile()})}`,
        system:`/edgek/ide/system-snapshot?${new URLSearchParams({root_path:root(),port_limit:'30',process_limit:'30'})}`,
        mcp:'/edgek/mcp/state',plugins:'/edgek/plugins'
      };
      const results={};
      await Promise.all(Object.entries(endpoints).map(async ([key,path]) => {
        const t=performance.now(); results[key]=await safeGet(path,6500); results[key].latency=`${Math.round(performance.now()-t)}ms`;
      }));
      let localSystem=null;
      if (!results.system.ok && window.beastDesktop?.systemSnapshot) {
        try { localSystem=await window.beastDesktop.systemSnapshot(root()); results.system={ok:true,data:localSystem,latency:'local'}; } catch (_) {}
      }
      const checks=[
        makeCheck('gateway','Gateway Core',results.rootInfo,'root contract ready'),
        makeCheck('snapshot','IDE Snapshot',results.snapshot,'workspace snapshot ready'),
        makeCheck('actions','Capabilities',results.actions,`${results.actions.data?.actions?.length || results.actions.data?.items?.length || 0} actions`),
        makeCheck('tooling','Tooling Snapshot',results.tooling,'tooling routes ready'),
        makeCheck('system','System Plane',results.system,'ports and processes visible'),
        makeCheck('mcp','MCP Broker',results.mcp,'broker state visible'),
        makeCheck('plugins','Plugin Registry',results.plugins,`${results.plugins.data?.plugins?.length || 0} plugins`)
      ];
      const healthy=checks.filter(item=>item.ok).length;
      const score=Math.round((healthy/checks.length)*100);
      const system=results.system.data || localSystem || {};
      const recommendations=[];
      checks.filter(item=>!item.ok).forEach(item=>recommendations.push({tone:'warn',title:`Repair ${item.label}`,detail:item.detail,action:'Inspect'}));
      const pending=results.mcp.data?.stats?.pending_approvals || results.mcp.data?.pending_approvals || 0;
      if (pending) recommendations.unshift({tone:'warn',title:'Resolve MCP approvals',detail:`${pending} request(s) wait for operator review.`,action:'Open Tooling'});
      if (!recommendations.length) recommendations.push({tone:'good',title:'System nominal',detail:'All diagnostic contracts responded successfully.',action:'Refresh'});
      const data={score,status:score>=90?'Excellent':score>=75?'Operational':score>=50?'Degraded':'Critical',checks,routes:checks,system,recommendations,report:{results,elapsed_ms:Math.round(performance.now()-start),checked_at:new Date().toISOString()}};
      BeastStore.patch('doctor',{...data,loading:false,error:score<50?'Core services are unavailable.':'',lastScanAt:Date.now()});
      BeastMascot.setState(score>=75?'finished':'alert');
      BeastStore.addLedger(`Doctor deep scan complete · score ${score}%`);
      return data;
    })().finally(()=>{ doctorPromise=null; });
    return doctorPromise;
  }

  async function restartGateway() {
    if (!window.beastDesktop?.restartGateway) throw new Error('Gateway restart is available only inside the BEAST Electron shell.');
    if (!window.confirm('Restart the BEAST gateway now? Active streams will be interrupted.')) return null;
    BeastStore.patch('doctor',{loading:true,error:''});
    const result=await window.beastDesktop.restartGateway();
    await new Promise(resolve=>setTimeout(resolve,900));
    await BeastDesktopBridge.status();
    await refreshDoctor();
    return result;
  }

  async function copyDoctorReport() {
    const report=BeastStore.get().doctor.report;
    if (!report || !Object.keys(report).length) return false;
    await navigator.clipboard?.writeText(JSON.stringify(report,null,2));
    BeastStore.addLedger('Doctor report copied');
    return true;
  }

  function destroy() { cancel(false); }

  window.BeastTerminalToolingDoctorBridge={
    loadTerminalState,rememberCommand,classify,execute,cancel,clearOutput,clearHistory,setCommand,setCwd,setTimeoutSeconds,copyReceipt,
    refreshTooling,validatePluginManifest,resolveMcpApproval,runBenchmark,
    refreshDoctor,restartGateway,copyDoctorReport,destroy
  };
})();
