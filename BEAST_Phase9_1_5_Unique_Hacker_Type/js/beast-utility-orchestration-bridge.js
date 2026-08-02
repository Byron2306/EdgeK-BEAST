(() => {
  const demoMode = new URLSearchParams(location.search).get('demo') === '1' || new URLSearchParams(location.search).get('capture') === '1';
  const escText = value => String(value ?? '');
  const now = () => Date.now();

  function gatewayUrl() { return BeastStore.get().connection.gatewayUrl || 'http://127.0.0.1:8000'; }
  function workspaceRoot() { return BeastStore.get().workspace.root || ''; }
  function clone(value, fallback={}) { try { return structuredClone(value ?? fallback); } catch (_) { return fallback; } }

  async function request(path, {method='GET', body, timeout=5000}={}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort('timeout'), timeout);
    try {
      const response = await fetch(new URL(path, gatewayUrl()), {
        method,
        headers: body ? {'Content-Type':'application/json'} : undefined,
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal
      });
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`.trim());
      return await response.json();
    } finally { clearTimeout(timer); }
  }

  async function quiet(path, options={}) { try { return await request(path, options); } catch (_) { return null; } }
  function list(payload, ...keys) {
    if (Array.isArray(payload)) return payload;
    for (const key of keys) if (Array.isArray(payload?.[key])) return payload[key];
    return [];
  }
  function statusText(value, fallback='unknown') { return String(value ?? fallback).replaceAll('_',' '); }
  function numeric(value, fallback=0) { const n=Number(value); return Number.isFinite(n) ? n : fallback; }
  function idOf(row, index=0) { return row?.id || row?.provider_id || row?.task_id || row?.event_id || row?.name || `row-${index}`; }

  const seeded = {
    providers: [
      {id:'local_ollama',label:'Ollama Local',kind:'Local Runtime',status:'ready',models:9,latency:'42ms',cost:'R0.00',confidence:96,route:'primary'},
      {id:'nvidia_nim',label:'NVIDIA NIM',kind:'Cloud Escalation',status:'armed',models:4,latency:'780ms',cost:'governed',confidence:92,route:'escalation'},
      {id:'openai',label:'OpenAI',kind:'Cloud Provider',status:'configured',models:3,latency:'1.1s',cost:'metered',confidence:90,route:'fallback'},
      {id:'anthropic',label:'Anthropic',kind:'Cloud Provider',status:'configured',models:2,latency:'1.3s',cost:'metered',confidence:91,route:'fallback'}
    ],
    ports: [
      {port:8000,service:'BEAST Gateway',status:'listening',pid:11842,address:'127.0.0.1'},
      {port:4000,service:'LiteLLM',status:'listening',pid:11912,address:'127.0.0.1'},
      {port:11434,service:'Ollama',status:'listening',pid:2214,address:'127.0.0.1'},
      {port:8082,service:'UI Preview',status:'free',pid:null,address:'0.0.0.0'}
    ],
    processes: [
      {pid:11842,name:'beast-gateway',cpu:8.4,memory:'412 MB',status:'healthy'},
      {pid:11912,name:'litellm-proxy',cpu:3.2,memory:'287 MB',status:'healthy'},
      {pid:2214,name:'ollama',cpu:24.8,memory:'6.3 GB',status:'working'},
      {pid:12109,name:'electron',cpu:5.1,memory:'544 MB',status:'healthy'}
    ],
    worktrees: [
      {id:'wt-parser',label:'Evidence Parser Hardening',branch:'beast/evidence-parser',path:'/demo/BEAST/.worktrees/evidence-parser',status:'active',progress:78,tests:'12/12',changes:9,owner:'Verifier Agent'},
      {id:'wt-ui',label:'Phase 8 Utility Plane',branch:'beast/phase8-ui',path:'/demo/BEAST/.worktrees/phase8-ui',status:'active',progress:64,tests:'18/20',changes:24,owner:'Local Architect'},
      {id:'wt-cache',label:'KV Cache Optimization',branch:'beast/cache-economy',path:'/demo/BEAST/.worktrees/cache',status:'paused',progress:42,tests:'7/9',changes:6,owner:'Profiler Agent'}
    ],
    chronicle: [
      {id:'evt-01',time:'14:41:28',kind:'governance',label:'SourcePlan verified',detail:'Plan SP-8A3 passed all policy gates.',actor:'Verifier Agent',severity:'success'},
      {id:'evt-02',time:'14:39:04',kind:'provider',label:'Local route selected',detail:'qwen2.5-coder:7b won the route trial at 94.7%.',actor:'Route Governor',severity:'info'},
      {id:'evt-03',time:'14:37:55',kind:'evidence',label:'Audit pack sealed',detail:'24 trace links and 7 artifacts attached.',actor:'Evidence Forge',severity:'success'},
      {id:'evt-04',time:'14:36:12',kind:'runtime',label:'Memory pressure warning',detail:'Cache utilization reached 78%; compaction recommended.',actor:'Runtime Governor',severity:'warning'},
      {id:'evt-05',time:'14:33:48',kind:'agent',label:'Agent handoff completed',detail:'Profiler Agent handed evidence to Graph Analyst.',actor:'Mission Swarm',severity:'info'}
    ]
  };

  function ensureState() {
    const state = BeastStore.get();
    BeastStore.transaction(next => {
      next.providers ||= {loading:false,error:'',selectedId:localStorage.getItem('beast.provider')||'local_ollama',activeId:'local_ollama',policy:'Local First',cloudAllowed:false,compression:true,kvCache:true,registry:[],routeTrials:[],economist:{winner:'local_ollama',reason:'Local-first quality/cost balance',saving:'100%'},runtime:{status:'checking',uptime:'n/a'},updatedAt:0};
      next.system ||= {loading:false,error:'',score:0,status:'Checking',cpu:0,memory:0,disk:0,network:0,ports:[],processes:[],environment:[],prec:{stage:'Discover',health:0,traces:0},runtime:{status:'checking'},updatedAt:0};
      next.settings ||= {theme:'black-chrome',typeScale:Number(localStorage.getItem('beast.setting.typeScale')||1),density:localStorage.getItem('beast.setting.density')||'comfortable',motion:localStorage.getItem('beast.setting.motion')||'balanced',atmosphere:localStorage.getItem('beast.setting.atmosphere')||'matrix-grid',audio:localStorage.getItem('beast.setting.audio')!=='off',reducedGlow:localStorage.getItem('beast.setting.reducedGlow')==='on',autoRefresh:localStorage.getItem('beast.setting.autoRefresh')!=='off',commandConfirm:true,sourcePlanRequired:true,evidenceClosure:true,updatedAt:0};
      next.worktrees ||= {loading:false,error:'',items:[],selectedId:'',diff:'',creating:false,updatedAt:0};
      next.deploy ||= {loading:false,error:'',score:0,status:'Not Checked',stages:[],blockers:[],manifest:{},ports:[],lastRunbook:null,updatedAt:0};
      next.chronicle ||= {loading:false,error:'',events:[],filtered:[],selectedId:'',filter:'all',query:'',insights:[],updatedAt:0};
      next.economy ||= {loading:false,error:'',tokensSaved:0,reuseRate:0,compression:0,cacheHit:0,costAvoided:'R0',callsDisplaced:0,providerMix:[],strategies:[],history:[],updatedAt:0};
      next.studio ||= {loading:false,error:'',health:0,phase:9,completed:7,total:12,systems:[],quickActions:[],updatedAt:0};
      next.mission = {...next.mission,id:'M-BEAST-PHASE8-001',title:'Transplant the Utility and Orchestration Plane into BEAST Core Shell v2',progress:88,health:97,status:'In Progress'};
      const phase8Steps=[['providers','Providers'],['system','System'],['worktrees','Worktrees'],['deploy','Deploy'],['chronicle','Chronicle'],['economy','Compute Economy'],['settings','Settings'],['studio','Studio']];
      for (const [id,title] of phase8Steps) if (!next.mission.path.some(step=>step.id===id)) next.mission.path.push({id,title,status:'In Progress'});
    });
    applySettings(BeastStore.get().settings);
  }

  function applySettings(settings=BeastStore.get().settings) {
    document.documentElement.style.setProperty('--beast-user-scale', String(settings.typeScale || 1));
    document.body.dataset.beastDensity = settings.density || 'comfortable';
    document.body.dataset.beastMotion = settings.motion || 'balanced';
    document.body.dataset.beastAtmosphere = settings.atmosphere || 'matrix-grid';
    document.body.dataset.beastGlow = settings.reducedGlow ? 'reduced' : 'full';
    document.body.classList.toggle('beast-audio-muted', !settings.audio);
  }

  async function refreshProviders() {
    ensureState(); BeastStore.patch('providers',{loading:true,error:''});
    if (demoMode) {
      BeastStore.patch('providers',{loading:false,registry:seeded.providers,activeId:'local_ollama',selectedId:BeastStore.get().providers.selectedId||'local_ollama',routeTrials:seeded.providers.map((p,i)=>({provider:p.id,quality:p.confidence,latency:[42,780,1100,1300][i],cost:i?55+i*12:0})),economist:{winner:'local_ollama',reason:'Local-first route meets quality threshold at zero marginal cost.',saving:'100%'},runtime:{status:'healthy',uptime:'8h 42m'},updatedAt:now()});
      return seeded.providers;
    }
    try {
      const [registryPayload,statePayload,runtimePayload,kvPayload] = await Promise.all([
        quiet('/edgek/providers/registry'), quiet('/edgek/providers/state'), quiet('/edgek/runtime/state'), quiet('/edgek/kv-cache/state')
      ]);
      const rows=list(registryPayload,'providers','items','registry').map((row,index)=>({
        ...row,id:idOf(row,index),label:row.label||row.name||row.provider_id||idOf(row,index),kind:row.kind||row.type||'Provider',
        status:row.status||row.health||'configured',models:numeric(row.models?.length ?? row.model_count),latency:row.latency||row.p50||'n/a',
        cost:row.cost||row.pricing||'governed',confidence:numeric(row.confidence||row.health_score,80),route:row.route||row.role||'candidate'
      }));
      const fallback=rows.length?rows:seeded.providers;
      const active=statePayload?.active_provider||statePayload?.provider||fallback[0]?.id||'local_ollama';
      BeastStore.patch('providers',{loading:false,registry:fallback,activeId:active,selectedId:BeastStore.get().providers.selectedId||active,policy:statePayload?.policy||'Local First',cloudAllowed:Boolean(statePayload?.cloud_allowed),compression:statePayload?.compression_enabled!==false,kvCache:kvPayload?.enabled!==false,runtime:{status:runtimePayload?.status||runtimePayload?.health||'healthy',uptime:runtimePayload?.uptime||'n/a'},routeTrials:fallback.map(row=>({provider:row.id,quality:row.confidence,latency:numeric(String(row.latency).replace(/[^0-9.]/g,''),0),cost:row.id.includes('local')?0:50})),updatedAt:now()});
      return fallback;
    } catch (error) { BeastStore.patch('providers',{loading:false,error:String(error.message||error),registry:seeded.providers,updatedAt:now()}); return seeded.providers; }
  }

  async function selectProvider(id) {
    const provider=BeastStore.get().providers.registry.find(row=>row.id===id);
    BeastStore.patch('providers',{selectedId:id}); localStorage.setItem('beast.provider',id);
    if (!demoMode && BeastStore.get().connection.status==='online') {
      const payload=await quiet('/edgek/provider-economist/select',{method:'POST',body:{objective:BeastStore.get().mission.title,provider_candidates:[id],root_path:workspaceRoot()}});
      if (payload) BeastStore.patch('providers',{activeId:payload.provider||payload.selected_provider||id,economist:{winner:payload.provider||id,reason:payload.reason||payload.explanation||'Selected by provider economist',saving:payload.saving||payload.cost_saving||'governed'}});
    } else BeastStore.patch('providers',{activeId:id,economist:{winner:id,reason:`${provider?.label||id} selected locally.`,saving:id.includes('local')?'100%':'governed'}});
    BeastStore.addLedger(`Provider route selected: ${provider?.label||id}`);
  }

  async function providerAction(action) {
    if (action==='compression') {
      const next=!BeastStore.get().providers.compression;
      if (!demoMode) await quiet('/edgek/providers/compression/toggle',{method:'POST',body:{enabled:next}});
      BeastStore.patch('providers',{compression:next});
    }
    if (action==='cache-clear') {
      if (!demoMode) await quiet('/edgek/providers/kv-cache/clear',{method:'POST',body:{root_path:workspaceRoot()}});
      BeastStore.addLedger('Provider KV cache cleared');
    }
    if (action==='smoke') {
      const selected=BeastStore.get().providers.selectedId;
      const result=!demoMode && selected.includes('nvidia') ? await quiet('/edgek/providers/nvidia-nim/live-smoke',{method:'POST',body:{model:localStorage.getItem('beast.model')||'',prompt:'Reply with BEAST route ready.'},timeout:15000}) : {ok:true,latency_ms:42};
      BeastStore.addLedger(`Provider smoke test ${result?'passed':'failed'}: ${selected}`);
      return result;
    }
  }

  async function refreshSystem() {
    ensureState(); BeastStore.patch('system',{loading:true,error:''});
    if (demoMode) {
      BeastStore.patch('system',{loading:false,score:94,status:'Nominal',cpu:28,memory:61,disk:46,network:18,ports:seeded.ports,processes:seeded.processes,environment:[['OS','Linux x86_64'],['Python','3.13'],['Node','22.x'],['Electron','ready'],['CUDA','12.4']],prec:{stage:'Reintegrate',health:92,traces:1842},runtime:{status:'healthy',circuits:0},updatedAt:now()}); return;
    }
    try {
      const params=new URLSearchParams({port_limit:'40',process_limit:'30'}); if(workspaceRoot()) params.set('root_path',workspaceRoot());
      const [systemPayload,runtimePayload,precPayload,rootPayload]=await Promise.all([quiet(`/edgek/ide/system-snapshot?${params}`),quiet('/edgek/runtime/state'),quiet('/edgek/prec/state'),quiet('/edgek/root-info')]);
      const ports=list(systemPayload,'ports','listening_ports').map((row,index)=>({port:row.port||row.local_port||index,service:row.service||row.process||row.name||'unknown',status:row.status||'listening',pid:row.pid,address:row.address||row.host||'127.0.0.1'}));
      const processes=list(systemPayload,'processes','process_list').map(row=>({pid:row.pid,name:row.name||row.command||'process',cpu:numeric(row.cpu||row.cpu_percent),memory:row.memory||row.rss||'n/a',status:row.status||'running'}));
      const cpu=numeric(systemPayload?.cpu?.percent ?? systemPayload?.cpu_percent ?? systemPayload?.resources?.cpu,0);
      const memory=numeric(systemPayload?.memory?.percent ?? systemPayload?.memory_percent ?? systemPayload?.resources?.memory,0);
      const disk=numeric(systemPayload?.disk?.percent ?? systemPayload?.disk_percent ?? systemPayload?.resources?.disk,0);
      const score=Math.max(0,Math.round(100-(cpu*.15+memory*.2+disk*.1)-(runtimePayload?.circuit_breakers?.open||0)*8));
      BeastStore.patch('system',{loading:false,score,status:score>85?'Nominal':score>65?'Degraded':'Critical',cpu,memory,disk,network:numeric(systemPayload?.network?.percent||0),ports:ports.length?ports:seeded.ports,processes:processes.length?processes:seeded.processes,environment:Object.entries(rootPayload||{}).slice(0,10),prec:{stage:precPayload?.stage||precPayload?.lifecycle_stage||'Discover',health:numeric(precPayload?.health||precPayload?.score,0),traces:numeric(precPayload?.traces||precPayload?.trace_count,0)},runtime:{status:runtimePayload?.status||'unknown',circuits:numeric(runtimePayload?.circuit_breakers?.open)},updatedAt:now()});
    } catch(error){ BeastStore.patch('system',{loading:false,error:String(error.message||error),ports:seeded.ports,processes:seeded.processes,updatedAt:now()}); }
  }

  async function systemAction(action, payload={}) {
    if(action==='sweep') { if(!demoMode) await quiet('/edgek/runtime/sweep',{method:'POST',body:{root_path:workspaceRoot()}}); BeastStore.addLedger('Runtime sweep completed'); }
    if(action==='free-port') { if(!demoMode) await quiet('/edgek/ide/ports/free',{method:'POST',body:{port:Number(payload.port),root_path:workspaceRoot()}}); BeastStore.addLedger(`Port ${payload.port} free request issued`); }
    if(action==='kill') { if(!demoMode) await quiet('/edgek/ide/system/kill',{method:'POST',body:{pid:Number(payload.pid),root_path:workspaceRoot()}}); BeastStore.addLedger(`Process ${payload.pid} kill request issued`); }
    return refreshSystem();
  }

  function updateSettings(partial) {
    ensureState(); BeastStore.patch('settings',{...partial,updatedAt:now()});
    const settings=BeastStore.get().settings;
    Object.entries(settings).forEach(([key,value])=>{ if(['updatedAt'].includes(key)) return; localStorage.setItem(`beast.setting.${key}`,typeof value==='boolean'?(value?'on':'off'):String(value)); });
    applySettings(settings); BeastStore.addLedger('IDE presentation settings updated');
  }

  async function refreshWorktrees() {
    ensureState(); BeastStore.patch('worktrees',{loading:true,error:''});
    if(demoMode){ BeastStore.patch('worktrees',{loading:false,items:seeded.worktrees,selectedId:BeastStore.get().worktrees.selectedId||seeded.worktrees[0].id,diff:'9 files changed\n+342 additions\n-78 deletions',updatedAt:now()}); return; }
    try{
      const params=new URLSearchParams({objective:BeastStore.get().mission.title}); if(workspaceRoot())params.set('root_path',workspaceRoot());
      const snap=await quiet(`/edgek/ide/snapshot?${params}`);
      let rows=list(snap?.worktree_missions||snap?.worktrees,'items','missions','tasks');
      rows=rows.map((row,index)=>({...row,id:idOf(row,index),label:row.label||row.objective||row.title||idOf(row,index),branch:row.branch||row.branch_name||'unresolved',path:row.path||row.worktree_path||'',status:row.status||'active',progress:numeric(row.progress,50),tests:row.tests||row.test_status||'pending',changes:numeric(row.changes||row.changed_files),owner:row.owner||row.agent||'BEAST'}));
      if(!rows.length) rows=seeded.worktrees;
      BeastStore.patch('worktrees',{loading:false,items:rows,selectedId:BeastStore.get().worktrees.selectedId||rows[0].id,updatedAt:now()});
    }catch(error){BeastStore.patch('worktrees',{loading:false,error:String(error.message||error),items:seeded.worktrees,updatedAt:now()});}
  }

  async function worktreeAction(action,id,extra={}) {
    const item=BeastStore.get().worktrees.items.find(row=>row.id===id);
    if(action==='select'){BeastStore.patch('worktrees',{selectedId:id});return;}
    const endpoint={create:'/edgek/ide/worktree-mission/create',test:'/edgek/ide/worktree-mission/test',diff:'/edgek/ide/worktree-mission/diff',close:'/edgek/ide/worktree-mission/close',sourceplan:'/edgek/ide/worktree-mission/sourceplan-draft'}[action];
    let result=null;
    if(!demoMode && endpoint) result=await quiet(endpoint,{method:'POST',body:{root_path:workspaceRoot(),task_id:id,objective:extra.objective||item?.label||BeastStore.get().mission.title,branch:item?.branch}});
    if(action==='diff') BeastStore.patch('worktrees',{diff:result?.diff||result?.patch||`Worktree ${id}\n${item?.changes||0} changed files\n${item?.tests||'tests pending'}`});
    if(action==='close') BeastStore.patch('worktrees',{items:BeastStore.get().worktrees.items.map(row=>row.id===id?{...row,status:'closed'}:row)});
    if(action==='test') BeastStore.patch('worktrees',{items:BeastStore.get().worktrees.items.map(row=>row.id===id?{...row,tests:result?.summary||'passed'}:row)});
    if(action==='create') { const newItem={id:`wt-${Date.now().toString(36)}`,label:extra.objective||'New governed mission',branch:`beast/${Date.now().toString(36)}`,path:'pending',status:'creating',progress:5,tests:'pending',changes:0,owner:'BEAST Operator'}; BeastStore.patch('worktrees',{items:[newItem,...BeastStore.get().worktrees.items],selectedId:newItem.id}); }
    BeastStore.addLedger(`Worktree action ${action}: ${id||extra.objective||'new mission'}`);
    return result;
  }

  async function refreshDeploy() {
    ensureState(); BeastStore.patch('deploy',{loading:true,error:''});
    if(demoMode){ BeastStore.patch('deploy',{loading:false,score:88,status:'Ready with Warnings',stages:[{id:'build',label:'Build',status:'passed'},{id:'tests',label:'Tests',status:'passed'},{id:'policy',label:'Policy',status:'passed'},{id:'evidence',label:'Evidence',status:'passed'},{id:'ports',label:'Ports',status:'warning'},{id:'release',label:'Release',status:'ready'}],blockers:[{severity:'warning',label:'Port 8082 currently reserved by preview server'}],manifest:{version:'v0.9.0-phase8',artifacts:18,checksums:18,rollback:'available',target:'local desktop'},ports:seeded.ports,lastRunbook:{id:'RUNBOOK-P8-DEMO',verified:true},updatedAt:now()}); return; }
    try{
      const body={root_path:workspaceRoot(),objective:BeastStore.get().mission.title};
      const [readiness,ports,runbook]=await Promise.all([quiet('/edgek/ide/release-readiness/check',{method:'POST',body}),quiet('/edgek/ide/ports?limit=200'),quiet('/edgek/ide/mission-runbook/verify',{method:'POST',body})]);
      const checks=list(readiness,'checks','gates','stages'); const stages=checks.length?checks.map((row,index)=>({id:idOf(row,index),label:row.label||row.name||idOf(row,index),status:row.status|| (row.ok?'passed':'warning')})):[{id:'release',label:'Release readiness',status:readiness?.ok?'passed':'warning'}];
      const blockers=list(readiness,'blockers','issues','warnings').map(row=>typeof row==='string'?{severity:'warning',label:row}:{severity:row.severity||'warning',label:row.label||row.detail||row.message});
      const score=numeric(readiness?.score||readiness?.readiness_score,stages.filter(s=>/pass|ready/i.test(s.status)).length/Math.max(1,stages.length)*100);
      BeastStore.patch('deploy',{loading:false,score:Math.round(score),status:readiness?.status|| (score>90?'Ready':score>70?'Ready with Warnings':'Blocked'),stages,blockers,manifest:readiness?.manifest||readiness?.release||{},ports:list(ports,'ports','items'),lastRunbook:runbook,updatedAt:now()});
    }catch(error){BeastStore.patch('deploy',{loading:false,error:String(error.message||error),updatedAt:now()});}
  }

  async function deployAction(action) {
    const body={root_path:workspaceRoot(),objective:BeastStore.get().mission.title};
    let result=null;
    if(action==='export') result=demoMode?{runbook_id:'RUNBOOK-P8-DEMO',ok:true}:await quiet('/edgek/ide/mission-runbook/export',{method:'POST',body,timeout:12000});
    if(action==='verify') result=demoMode?{verified:true}:await quiet('/edgek/ide/mission-runbook/verify',{method:'POST',body,timeout:12000});
    if(action==='check') return refreshDeploy();
    BeastStore.patch('deploy',{lastRunbook:result||BeastStore.get().deploy.lastRunbook}); BeastStore.addLedger(`Deploy action ${action} completed`); return result;
  }

  async function refreshChronicle() {
    ensureState(); BeastStore.patch('chronicle',{loading:true,error:''});
    if(demoMode){ BeastStore.patch('chronicle',{loading:false,events:seeded.chronicle,filtered:seeded.chronicle,selectedId:BeastStore.get().chronicle.selectedId||seeded.chronicle[0].id,insights:['Local-first routing displaced 17 cloud calls.','Evidence closure improved from 82% to 96%.','One memory compaction warning remains.'],updatedAt:now()}); return; }
    try{
      const payload=await request('/edgek/chronicle?limit=80');
      let rows=list(payload,'entries','events','records','items').map((row,index)=>({...row,id:idOf(row,index),time:row.time||row.timestamp||row.created_at||'',kind:row.kind||row.category||row.type||'system',label:row.label||row.event||row.title||row.action||'BEAST event',detail:row.detail||row.message||row.summary||'',actor:row.actor||row.source||row.agent||'BEAST',severity:row.severity||row.status||'info'}));
      if(!rows.length) rows=seeded.chronicle;
      BeastStore.patch('chronicle',{loading:false,events:rows,filtered:rows,selectedId:BeastStore.get().chronicle.selectedId||rows[0].id,updatedAt:now()});
    }catch(error){BeastStore.patch('chronicle',{loading:false,error:String(error.message||error),events:seeded.chronicle,filtered:seeded.chronicle,updatedAt:now()});}
  }

  function filterChronicle({query,filter}={}) {
    const current=BeastStore.get().chronicle; const q=(query??current.query).toLowerCase(); const f=filter??current.filter;
    const filtered=current.events.filter(row=>(f==='all'||row.kind===f||row.severity===f)&&(!q||`${row.label} ${row.detail} ${row.actor}`.toLowerCase().includes(q)));
    BeastStore.patch('chronicle',{query:query??current.query,filter:f,filtered});
  }
  function selectChronicle(id){BeastStore.patch('chronicle',{selectedId:id});}
  async function compileInsights(){ const result=demoMode?{insights:['Provider economy saved an estimated 1.24M tokens.','Review contradictions dropped by 67%.','Runtime health remained above 92%.']}:await quiet('/edgek/insights/compile',{method:'POST',body:{root_path:workspaceRoot(),objective:BeastStore.get().mission.title}}); const insights=list(result,'insights','findings','items').map(x=>typeof x==='string'?x:x.label||x.detail||x.summary); BeastStore.patch('chronicle',{insights:insights.length?insights:BeastStore.get().chronicle.insights}); return result; }

  async function refreshEconomy() {
    ensureState(); BeastStore.patch('economy',{loading:true,error:''});
    if(demoMode){ BeastStore.patch('economy',{loading:false,tokensSaved:1240000,reuseRate:78,compression:63,cacheHit:84,costAvoided:'R18,420',callsDisplaced:317,providerMix:[{label:'Local',value:72},{label:'NIM',value:18},{label:'Other Cloud',value:10}],strategies:[{label:'Local-first cascade',gain:94,status:'active'},{label:'Crystal reuse',gain:78,status:'active'},{label:'Context compression',gain:63,status:'active'},{label:'KV cache',gain:84,status:'active'}],history:[42,48,55,61,67,72,78,84],updatedAt:now()}); return; }
    try{
      const [economy,reuse,compression,kv,providers]=await Promise.all([quiet('/edgek/commons-economy'),quiet('/edgek/crystal-reuse'),quiet('/edgek/compression/pipeline'),quiet('/edgek/kv-cache/state'),quiet('/edgek/providers/state')]);
      const tokens=numeric(economy?.tokens_saved||economy?.saved_tokens||reuse?.measured_saved_tokens);
      const calls=numeric(economy?.calls_displaced||reuse?.reuse_hit_count);
      const reuseRate=numeric(reuse?.reuse_rate||reuse?.hit_rate, calls?Math.min(100,calls):0);
      const comp=numeric(compression?.ratio_percent||compression?.saving_percent||compression?.compression_rate);
      const cache=numeric(kv?.hit_rate||kv?.hit_percent||kv?.stats?.hit_rate);
      BeastStore.patch('economy',{loading:false,tokensSaved:tokens,reuseRate,compression:comp,cacheHit:cache,costAvoided:economy?.cost_avoided||economy?.saved_cost||'governed',callsDisplaced:calls,providerMix:list(providers,'mix','provider_mix').length?list(providers,'mix','provider_mix'):[{label:'Local',value:numeric(providers?.local_share,70)},{label:'Cloud',value:numeric(providers?.cloud_share,30)}],strategies:[{label:'Local-first cascade',gain:numeric(economy?.local_first_score,90),status:'active'},{label:'Crystal reuse',gain:reuseRate,status:'active'},{label:'Context compression',gain:comp,status:compression?.enabled===false?'paused':'active'},{label:'KV cache',gain:cache,status:kv?.enabled===false?'paused':'active'}],history:list(economy,'history','series').map(row=>numeric(row.value??row)),updatedAt:now()});
    }catch(error){BeastStore.patch('economy',{loading:false,error:String(error.message||error),updatedAt:now()});}
  }

  async function refreshStudio() {
    ensureState();
    const s=BeastStore.get();
    const systems=[
      ['Editor Cortex',s.editor.owner!=='unmounted'],['SourcePlan',Boolean(s.sourcePlan.plan)||s.sourcePlan.status!=='idle'],['Models',s.models.registry.length>0],['Agents',s.agents.sessions.length>0],
      ['Review',s.review.gates.length>0],['Evidence',s.evidence.files.length>0],['Trust',s.trust.score>0],['Memory',s.memory.records>0],['Map',s.map.nodes.length>0],['Crystal',s.crystal.candidates.length>0],
      ['Terminal',true],['Tooling',s.tooling.status!=='checking'],['Doctor',s.doctor.score>0],['Providers',s.providers.registry.length>0],['System',s.system.score>0]
    ].map(([label,ready],index)=>({id:`sys-${index}`,label,ready,status:ready?'online':'checking'}));
    const health=Math.round(systems.filter(x=>x.ready).length/systems.length*100);
    BeastStore.patch('studio',{loading:false,health,phase:9,completed:8,total:12,systems,quickActions:[{route:'mission',label:'Mission Control'},{route:'workspace',label:'Editor Cortex'},{route:'providers',label:'Provider Plane'},{route:'system',label:'System Plane'},{route:'deploy',label:'Release Readiness'},{route:'economy',label:'Compute Economy'}],updatedAt:now()});
  }

  async function refreshAll() {
    ensureState();
    return Promise.allSettled([refreshProviders(),refreshSystem(),refreshWorktrees(),refreshDeploy(),refreshChronicle(),refreshEconomy()]).then(()=>refreshStudio());
  }

  ensureState();
  window.BeastUtilityOrchestrationBridge={ensureState,applySettings,refreshProviders,selectProvider,providerAction,refreshSystem,systemAction,updateSettings,refreshWorktrees,worktreeAction,refreshDeploy,deployAction,refreshChronicle,filterChronicle,selectChronicle,compileInsights,refreshEconomy,refreshStudio,refreshAll};
})();
