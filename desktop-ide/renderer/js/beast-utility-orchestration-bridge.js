(() => {
  const demoMode = new URLSearchParams(location.search).get('demo') === '1' || new URLSearchParams(location.search).get('capture') === '1';
  const escText = value => String(value ?? '');
  const now = () => Date.now();

  function gatewayUrl() { return BeastStore.get().connection.gatewayUrl || 'http://127.0.0.1:8101'; }
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
  async function command(path, options={}) {
    const result = await request(path, options);
    if (result == null || result.ok === false ||
        result.success === false || result.verified === false ||
        result.status === 'failed' || result.status === 'refused') {
      throw new Error(`BEAST command not confirmed: ${path}`);
    }
    return result;
  }

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
      {id:'local_ollama',label:'Ollama Local',kind:'Local Runtime',status:'ready',models:9,latency:'42ms',cost:'non-financial',confidence:96,route:'primary'},
      {id:'nvidia_nim',label:'NVIDIA NIM',kind:'Cloud Escalation',status:'armed',models:4,latency:'780ms',cost:'governed',confidence:92,route:'escalation'},
      {id:'openai',label:'OpenAI',kind:'Cloud Provider',status:'configured',models:3,latency:'1.1s',cost:'governed',confidence:90,route:'fallback'},
      {id:'anthropic',label:'Anthropic',kind:'Cloud Provider',status:'configured',models:2,latency:'1.3s',cost:'governed',confidence:91,route:'fallback'}
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
      next.providers ||= {loading:false,error:'',selectedId:localStorage.getItem('beast.provider')||'',activeId:'',policy:'Local First',cloudAllowed:false,compression:true,kvCache:true,registry:[],routeTrials:[],economist:{winner:'local_ollama',reason:'Local-first quality/cost balance',saving:'100%'},runtime:{status:'checking',uptime:'n/a'},updatedAt:0};
      next.system ||= {loading:false,error:'',score:0,status:'Checking',cpu:0,memory:0,disk:0,network:0,ports:[],processes:[],environment:[],prec:{stage:'Discover',health:0,traces:0},runtime:{status:'checking'},updatedAt:0};
      next.settings ||= {theme:'black-chrome',typeScale:Number(localStorage.getItem('beast.setting.typeScale')||1),density:localStorage.getItem('beast.setting.density')||'comfortable',motion:localStorage.getItem('beast.setting.motion')||'balanced',atmosphere:localStorage.getItem('beast.setting.atmosphere')||'quiet',audio:localStorage.getItem('beast.setting.audio')!=='off',reducedGlow:localStorage.getItem('beast.setting.reducedGlow')==='on',autoRefresh:localStorage.getItem('beast.setting.autoRefresh')!=='off',commandConfirm:true,sourcePlanRequired:true,evidenceClosure:true,updatedAt:0};
      next.worktrees ||= {loading:false,error:'',items:[],selectedId:'',diff:'',creating:false,updatedAt:0};
      next.deploy ||= {loading:false,error:'',score:0,status:'Not Checked',stages:[],blockers:[],manifest:{},ports:[],lastRunbook:null,updatedAt:0};
      next.chronicle ||= {loading:false,error:'',events:[],filtered:[],selectedId:'',filter:'all',query:'',insights:[],updatedAt:0};
      next.economy ||= {loading:false,error:'',tokensSaved:0,reuseRate:0,compression:0,cacheHit:0,costAvoided:'non-financial',callsDisplaced:0,activeCredits:0,creditMode:'non_financial_simulation',providerMix:[],strategies:[],history:[],updatedAt:0};
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
    if (settings.atmosphere === 'matrix-grid') window.BeastAtmosphere?.start?.();
    else window.BeastAtmosphere?.stop?.();
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
      const credentials=statePayload?.credentials || {};
      const inventory=await quiet('/edgek/ide/model-inventory');
      let rows=list(registryPayload,'providers','items','registry').map((row,index)=>({
        ...row,id:idOf(row,index),label:row.label||row.name||row.provider_id||idOf(row,index),kind:row.kind||row.type||'Provider',
        status:row.status||row.health||(credentials[row.provider_id] ? 'credentials ready' : (row.provider_id==='ollama'||row.provider_id==='tgi'?'local':'secret required')),
        models:numeric(row.models?.length ?? row.model_count ?? (row.default_model ? 1 : 0)),latency:row.latency||row.p50||'n/a',
        cost:row.cost||row.pricing||'governed',confidence:numeric(row.confidence||row.health_score,0),route:row.route||row.role||'candidate'
      }));
      if (inventory?.registry?.length) {
        const present=new Set(['beast', ...(inventory.providers_present||[])]);
        const fromInventory=[{id:'beast',label:'Auto (BEAST governed)',kind:'Capability router',status:'default',models:inventory.count||0,latency:'routed per call',cost:'governed',confidence:0,route:'auto',default_model:'auto'}];
        for (const lane of inventory.registry) {
          if (!lane.provider || lane.provider==='beast') continue;
          let rec=fromInventory.find(row=>row.id===lane.provider);
          if (!rec) {
            rec={id:lane.provider,label:lane.provider,kind:lane.runtime||'Provider',status:lane.live===true?'live':'credentials ready',models:0,latency:'n/a',cost:'governed',confidence:0,route:'lane',default_model:lane.model};
            fromInventory.push(rec);
          }
          rec.models+=1;
          if (lane.confidence>rec.confidence) rec.confidence=lane.confidence;
        }
        rows=fromInventory;
      }
      const active=BeastStore.get().models.provider || statePayload?.active_provider || rows[0]?.id || 'beast';
      BeastStore.patch('providers',{loading:false,error:'',registry:rows,activeId:active,selectedId:BeastStore.get().providers.selectedId||active,policy:inventory?.policy||statePayload?.policy||'Auto (BEAST governed)',cloudAllowed:Boolean(statePayload?.cloud_allowed),compression:statePayload?.compression_enabled!==false,kvCache:kvPayload?.enabled!==false,runtime:{status:runtimePayload?.status||runtimePayload?.health||'unknown',uptime:runtimePayload?.uptime||'n/a'},routeTrials:(inventory?.tests||inventory?.family_leaders)?Object.entries(inventory.family_leaders||{}).map(([family,leader])=>({provider:leader.provider,quality:Math.round((Number(leader.pass_rate)||0)*100),latency:0,cost:0,family})):rows.map(row=>({provider:row.id,quality:row.confidence||0,latency:0,cost:0})),updatedAt:now()});
      return rows;
    } catch (error) { BeastStore.patch('providers',{loading:false,error:String(error.message||error),registry:[],updatedAt:now()}); return []; }
  }

  async function selectProvider(id) {
    if (id==='beast' || id==='auto') {
      window.BeastModelAgentBridge?.selectModel?.('auto');
      BeastStore.patch('providers',{selectedId:'beast',activeId:'beast',error:'',notice:'Agent Coder selected: Auto (BEAST governed)'});
      return;
    }
    const provider=BeastStore.get().providers.registry.find(row=>row.id===id);
    if (!provider) throw new Error('Provider is not in the current registry.');
    BeastStore.patch('providers',{selectedId:id,error:''});
    const models=BeastStore.get().models.registry||[];
    const available=models.find(row=>row.provider===id && row.selectable!==false);
    if (available) {
      window.BeastModelAgentBridge?.selectModel?.(available.id);
      BeastStore.patch('providers',{activeId:id,notice:`Agent Coder selected: ${id} / ${available.model || available.id}`});
    }
  }

  async function setProviderSecret(providerId, envName, value) {
    if (demoMode) throw new Error('Secrets cannot be stored in demo mode.');
    if (!String(value || '').trim()) throw new Error('Enter a secret value.');
    const result=await request('/edgek/providers/secrets/set',{method:'POST',body:{provider_id:providerId,env_name:envName,value}});
    await refreshProviders();
    await selectProvider(providerId);
    return result;
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
      if (!selected.includes('nvidia')) throw new Error(`No live smoke endpoint is implemented for ${selected}; credentials may be ready but inference is unverified.`);
      const provider=BeastStore.get().providers.registry.find(row=>row.id===selected);
      const result=await request('/edgek/providers/nvidia-nim/live-smoke',{method:'POST',body:{confirm_live:true,model:provider?.default_model||'',prompt:'Reply with BEAST route ready.',timeout_seconds:30,max_tokens:128},timeout:65000});
      if(result?.status !== 'ok') throw new Error(`NIM smoke failed: ${result?.error || result?.status || 'no receipt'}`);
      BeastStore.patch('providers',{notice:`NIM responded successfully using ${result.model || provider?.default_model}.`,error:''});
      BeastStore.addLedger(`Provider smoke test passed: ${selected}`);
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
    if(action==='sweep') { if(!demoMode) await command('/edgek/runtime/sweep',{method:'POST',body:{root_path:workspaceRoot()}}); BeastStore.addLedger('Runtime sweep completed'); }
    if(action==='free-port') { if(!demoMode) await command('/edgek/ide/ports/free',{method:'POST',body:{port:Number(payload.port),root_path:workspaceRoot()}}); BeastStore.addLedger(`Port ${payload.port} free request issued`); }
    if(action==='kill') { if(!demoMode) await command('/edgek/ide/system/kill',{method:'POST',body:{pid:Number(payload.pid),root_path:workspaceRoot()}}); BeastStore.addLedger(`Process ${payload.pid} kill request issued`); }
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
    if(!demoMode && endpoint) result=await command(endpoint,{method:'POST',body:{root_path:workspaceRoot(),task_id:id,objective:extra.objective||item?.label||BeastStore.get().mission.title,branch:item?.branch}});
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
    if(action==='export') result=demoMode?{runbook_id:'RUNBOOK-P8-DEMO',ok:true}:await command('/edgek/ide/mission-runbook/export',{method:'POST',body,timeout:12000});
    if(action==='verify') result=demoMode?{verified:true}:await command('/edgek/ide/mission-runbook/verify',{method:'POST',body,timeout:12000});
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
    if(demoMode){ BeastStore.patch('economy',{loading:false,tokensSaved:1240000,reuseRate:78,compression:63,cacheHit:84,costAvoided:'1,240,000 tokens avoided (non-financial credits)',callsDisplaced:317,activeCredits:16,creditMode:'non_financial_simulation',providerMix:[{label:'Local',value:72},{label:'NIM',value:18},{label:'Other Cloud',value:10}],strategies:[{label:'Local-first cascade',gain:94,status:'active'},{label:'Crystal reuse',gain:78,status:'active'},{label:'Context compression',gain:63,status:'active'},{label:'KV cache',gain:84,status:'active'}],history:[42,48,55,61,67,72,78,84],updatedAt:now()}); return; }
    try{
      const [economy,reuse,compression,kv,providers,phase]=await Promise.all([quiet('/edgek/commons-economy'),quiet('/edgek/crystal-reuse'),quiet('/edgek/compression/pipeline'),quiet('/edgek/kv-cache/state'),quiet('/edgek/providers/state'),quiet('/edgek/ide/phase-evidence')]);
      const storage=reuse?.storage||{};
      const phaseEconomy=phase?.economy||{};
      const tokens=numeric(storage.total_avoided_tokens||storage.measured_reuse_tokens_saved||phaseEconomy.savedTokens||phaseEconomy.netSavings||economy?.tokens_saved||economy?.saved_tokens||reuse?.measured_saved_tokens);
      const calls=numeric(storage.total_reuse_count||economy?.calls_displaced||reuse?.reuse_hit_count);
      const totalCredits=numeric(storage.total_credits||economy?.credit_count);
      const activeCredits=numeric(storage.active_credits||totalCredits);
      const reuseRate=numeric(reuse?.reuse_rate||reuse?.hit_rate, totalCredits?Math.min(100,Math.round((calls/Math.max(1,totalCredits))*100)):(calls?Math.min(100,calls):0));
      const compRaw=compression?.ratio_percent||compression?.saving_percent||compression?.compression_rate;
      const comp=numeric(compRaw<=1&&compRaw>0?Number(compRaw)*100:compRaw);
      const cache=numeric(kv?.hit_rate||kv?.hit_percent||kv?.stats?.hit_rate||(kv?.memory_utilization<=1?Number(kv.memory_utilization)*100:kv?.memory_utilization));
      const creditMode=economy?.mode||'non_financial_simulation';
      const costAvoided=tokens?`${Number(tokens).toLocaleString()} tokens avoided (non-financial credits)`:'non-financial credits · no measured token savings yet';
      const mix=list(providers,'mix','provider_mix');
      BeastStore.patch('economy',{loading:false,tokensSaved:tokens,reuseRate,compression:comp,cacheHit:cache,costAvoided,callsDisplaced:calls,activeCredits,creditMode,breakEven:phaseEconomy.breakEven||'',publication:phaseEconomy.credits||economy?.credit_count||0,providerMix:mix.length?mix:[],strategies:[{label:'Local-first cascade',gain:numeric(economy?.local_first_score, reuseRate||0),status:'active'},{label:'Crystal reuse',gain:reuseRate,status:'active'},{label:'Context compression',gain:comp,status:compression?.enabled===false?'paused':'active'},{label:'KV cache',gain:cache,status:kv?.enabled===false?'paused':'active'}],history:list(economy,'history','series','adoption_history').map(row=>numeric(row.value??row.verified_count??row)),updatedAt:now()});
    }catch(error){BeastStore.patch('economy',{loading:false,error:String(error.message||error),updatedAt:now()});}
  }

  let studioRefreshPromise=null;
  async function refreshStudio({force=false}={}) {
    ensureState();
    if (studioRefreshPromise) return studioRefreshPromise;

    studioRefreshPromise=(async()=>{
      BeastStore.patch('studio',{loading:true});
      const stale=(state,field)=>force||Boolean(state.error)||!Number(state[field]||0)||now()-Number(state[field])>60000;
      const jobs=[
        [BeastStore.get().models,'lastRefreshAt',()=>BeastModelAgentBridge.refreshModels()],
        [BeastStore.get().agents,'lastRefreshAt',()=>BeastModelAgentBridge.refreshAgents()],
        [BeastStore.get().review,'updatedAt',()=>BeastReviewEvidenceBridge.refreshReview()],
        [BeastStore.get().evidence,'updatedAt',()=>BeastReviewEvidenceBridge.refreshEvidence()],
        [BeastStore.get().trust,'updatedAt',()=>BeastTrustMemoryBridge.refreshTrust()],
        [BeastStore.get().memory,'updatedAt',()=>BeastTrustMemoryBridge.refreshMemory()],
        [BeastStore.get().map,'updatedAt',()=>BeastMapCrystalBridge.refreshMap()],
        [BeastStore.get().crystal,'updatedAt',()=>BeastMapCrystalBridge.refreshCrystal()],
        [BeastStore.get().tooling,'updatedAt',()=>BeastTerminalToolingDoctorBridge.refreshTooling()],
        [BeastStore.get().doctor,'lastScanAt',()=>BeastTerminalToolingDoctorBridge.refreshDoctor()],
        [BeastStore.get().providers,'updatedAt',()=>refreshProviders()],
        [BeastStore.get().system,'updatedAt',()=>refreshSystem()],
        [BeastStore.get().worktrees,'updatedAt',()=>refreshWorktrees()],
        [BeastStore.get().deploy,'updatedAt',()=>refreshDeploy()],
        [BeastStore.get().chronicle,'updatedAt',()=>refreshChronicle()],
        [BeastStore.get().economy,'updatedAt',()=>refreshEconomy()]
      ].filter(([state,field])=>stale(state,field));
      await Promise.allSettled(jobs.map(([, ,refresh])=>refresh()));

      const s=BeastStore.get();
      const maxAge=60000;
      const doctorCheckedAt=Number(s.doctor.lastScanAt||0);
      const doctorCurrent=!BeastDesktopBridge.demoMode&&doctorCheckedAt>0&&now()-doctorCheckedAt<=maxAge;
      const service=(label,state,field,available=()=>true,unavailableReason='Service contract did not report ready')=>{
        const checkedAt=Number(state[field]||0);
        let status='ready';
        let detail='Live check passed';
        if(BeastDesktopBridge.demoMode){status='simulated';detail='Demo telemetry; live readiness is not verified';}
        else if(state.error){status='error';detail=String(state.error);}
        else if(state.loading){status='checking';detail='Live check is still running';}
        else if(!checkedAt){status='not_checked';detail='No successful live check recorded';}
        else if(now()-checkedAt>maxAge){status='stale';detail='Last successful check is older than 60 seconds';}
        else if(label!=='Doctor'&&(!doctorCurrent||Number(s.doctor.score)!==100)){status='blocked';detail=doctorCurrent?`Doctor route checks are ${Number(s.doctor.score)||0}%; inspect Doctor for failed contracts`:'Doctor route checks have not passed in the last 60 seconds';}
        else if(!available(state)){status='blocked';detail=unavailableReason;}
        return {id:`sys-${label.toLowerCase().replace(/[^a-z0-9]+/g,'-')}`,label,ready:status==='ready',status,detail,checkedAt};
      };
      const local=(label,ready,detail)=>({id:`sys-${label.toLowerCase().replace(/[^a-z0-9]+/g,'-')}`,label,ready,status:ready?'ready':'blocked',detail,checkedAt:now()});
      const hasWorkspace=Boolean(s.workspace.root);
      const systems=[
        local('Editor Cortex',hasWorkspace&&typeof BeastEditorCortex?.mount==='function',hasWorkspace?'Workspace editor runtime is available':'Choose a workspace to enable editor readiness'),
        local('SourcePlan',hasWorkspace&&typeof BeastEditorCortex?.draftSourcePlan==='function',hasWorkspace?'SourcePlan runtime is available':'Choose a workspace to enable SourcePlan'),
        service('Models',s.models,'lastRefreshAt',state=>state.registry.length>0,'No model routes are registered'),
        service('Agents',s.agents,'lastRefreshAt'),
        service('Review',s.review,'updatedAt'),
        service('Evidence',s.evidence,'updatedAt'),
        service('Trust',s.trust,'updatedAt',state=>Number(state.failedChecks||0)===0,'Trust checks reported failures'),
        service('Memory',s.memory,'updatedAt'),
        service('Map',s.map,'updatedAt'),
        service('Crystal',s.crystal,'updatedAt'),
        local('Terminal',typeof BeastTerminalToolingDoctorBridge?.execute==='function','Terminal execution capability is unavailable'),
        service('Tooling',s.tooling,'updatedAt',state=>state.status!=='checking','Tooling check did not complete'),
        service('Doctor',s.doctor,'lastScanAt',state=>Number(state.score)===100,'Doctor checks report unresolved readiness issues'),
        service('Providers',s.providers,'updatedAt',state=>state.registry.length>0,'No provider routes are registered'),
        service('System',s.system,'updatedAt',state=>state.status==='Nominal','System status is not nominal')
      ];
      const ready=systems.filter(row=>row.ready).length;
      const health=Math.round(ready/systems.length*100);
      BeastStore.patch('studio',{loading:false,health,readiness:{ready,total:systems.length,checkedAt:now()},phase:9,completed:8,total:12,systems,quickActions:[{route:'mission',label:'Mission Control'},{route:'workspace',label:'Editor Cortex'},{route:'providers',label:'Provider Plane'},{route:'system',label:'System Plane'},{route:'deploy',label:'Release Readiness'},{route:'economy',label:'Compute Economy'}],updatedAt:now()});
    })().finally(()=>{studioRefreshPromise=null;});
    return studioRefreshPromise;
  }

  async function refreshAll() {
    ensureState();
    return Promise.allSettled([refreshProviders(),refreshSystem(),refreshWorktrees(),refreshDeploy(),refreshChronicle(),refreshEconomy()]).then(()=>refreshStudio());
  }

  ensureState();
  window.BeastUtilityOrchestrationBridge={ensureState,applySettings,refreshProviders,selectProvider,setProviderSecret,providerAction,refreshSystem,systemAction,updateSettings,refreshWorktrees,worktreeAction,refreshDeploy,deployAction,refreshChronicle,filterChronicle,selectChronicle,compileInsights,refreshEconomy,refreshStudio,refreshAll};
})();
