(() => {
  const demoMode = window.BEAST_ENABLE_DEMO === true && (new URLSearchParams(location.search).get('demo') === '1' || new URLSearchParams(location.search).get('capture') === '1');
  const escText = value => String(value ?? '');
  const now = () => Date.now();

  function gatewayUrl() { return BeastRuntime.gatewayUrl || BeastStore.get().connection.gatewayUrl || 'http://127.0.0.1:8101'; }
  function workspaceRoot() { return BeastStore.get().workspace.root || ''; }
  function clone(value, fallback={}) { try { return structuredClone(value ?? fallback); } catch (_) { return fallback; } }

  async function request(path, {method='GET', body, timeout=5000, signal}={}) {
    return await BeastRuntime.request(path, { method, body, timeoutMs: timeout, signal });
  }

  function list(payload, ...keys) {
    if (Array.isArray(payload)) return payload;
    for (const key of keys) if (Array.isArray(payload?.[key])) return payload[key];
    return [];
  }
  function requireConfirmation(result, action) {
    if (!result || result.ok === false || result.success === false || result.applied === false) {
      throw new Error(result?.error || result?.detail || `${action} was not confirmed by the gateway.`);
    }
    return result;
  }
  function statusText(value, fallback='unknown') { return String(value ?? fallback).replaceAll('_',' '); }
  function numeric(value, fallback=0) { const n=Number(value); return Number.isFinite(n) ? n : fallback; }
  function idOf(row, index=0) { return row?.id || row?.provider_id || row?.task_id || row?.event_id || row?.name || `row-${index}`; }

  const seeded = {
    providers: [
      {id:'ollama',label:'Ollama Local',kind:'Local Runtime',status:'ready',models:1,latency:'42ms',cost:'R0.00',confidence:96,route:'primary'},
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
    ],
    platform: {
      health: 82,
      status: 'healthy',
      summary: { pipeline_status: 'passed', capability_count: 24, memory_layers: 4, vector_adapters: 5, route_cards: 7, chronicles: 5, swarm_runs: 3, forensic_events: 18 },
      sections: [
        { id: 'pipeline', title: 'Task Pipeline', status: 'healthy', summary: 'Envelope -> quality cascade -> context packet -> forge scorecard -> insight packet', metrics: [
          { label: 'Envelope', value: 'platform_diagnostics', detail: 'task class' },
          { label: 'Quality', value: 'passed', detail: '5 checks' },
          { label: 'Scorecard', value: 'approve', detail: 'risk 0.18' },
          { label: 'Insights', value: 5, detail: 'ranked evidence' },
        ]},
        { id: 'memory', title: 'L0-L4 Memory', status: 'healthy', summary: 'Governance boundary, hot caches, workspace graph, skills, and forensic archive', metrics: [
          { label: 'Layers', value: 4, detail: 'L0-L4' },
          { label: 'Truth stores', value: 8, detail: 'append-only anchors' },
          { label: 'Retrieval views', value: 7, detail: 'query surfaces' },
          { label: 'Forensic events', value: 18, detail: 'L4 archive' },
        ]},
        { id: 'capabilities', title: 'Capabilities And Skills', status: 'healthy', summary: 'Capability registry, skill tree, and tool-bucket exposure rules', metrics: [
          { label: 'Capabilities', value: 24, detail: 'verified / local mix' },
          { label: 'Skills', value: 12, detail: 'patterns + candidates' },
          { label: 'Exposure', value: 12, detail: 'lazy schemas' },
          { label: 'Meta tools', value: 8, detail: 'discovery bridge' },
        ]},
        { id: 'vectors', title: 'Vector RAG And KV Cache', status: 'healthy', summary: 'Current retrieval adapters, optional embeddings, and cache-compatible routing', metrics: [
          { label: 'Adapters', value: 5, detail: 'sqlite + future targets' },
          { label: 'Dense vectors', value: 3, detail: 'optional' },
          { label: 'Lexical fallback', value: 5, detail: 'mandatory' },
          { label: 'KV transport', value: 'ready', detail: 'cross-engine' },
        ]},
        { id: 'swarm', title: 'Swarm And Orchestration', status: 'healthy', summary: 'Role lanes, recent runs, value logs, and governed planning', metrics: [
          { label: 'Runs', value: 3, detail: 'recent cycles' },
          { label: 'Roles', value: 7, detail: 'governed lanes' },
          { label: 'Value logs', value: 8, detail: 'local benefit ledger' },
          { label: 'Recent chronicles', value: 5, detail: 'task envelopes' },
        ]},
        { id: 'sensorium', title: 'Sensorium And Interception', status: 'healthy', summary: 'Payload-free operational sensing, event mesh, and observatory projections', metrics: [
          { label: 'Events', value: 48, detail: 'read model' },
          { label: 'Observatory', value: 'ready', detail: 'projection' },
          { label: 'Mesh layers', value: 4, detail: 'L1-L4' },
          { label: 'Telemetry', value: 16, detail: 'signals' },
        ]},
        { id: 'tools', title: 'Chronicle And Tool Laziness', status: 'healthy', summary: 'Ledger history, insight compiler outputs, and learned tool-skip guidance', metrics: [
          { label: 'Chronicles', value: 5, detail: 'recent records' },
          { label: 'Insights', value: 5, detail: 'ranked evidence' },
          { label: 'Tool samples', value: 9, detail: 'learn_more' },
          { label: 'Route cards', value: 7, detail: 'workflow contracts' },
        ]},
      ]
    }
  };

  function ensureState() {
    const state = BeastStore.get();
    BeastStore.transaction(next => {
      next.providers ||= {loading:false,error:'',selectedId:'',activeId:'',policy:'unreported',cloudAllowed:false,compression:false,kvCache:false,registry:[],routeTrials:[],economist:{winner:'',reason:'unreported',saving:'unreported'},runtime:{status:'checking',uptime:'n/a'},updatedAt:0};
      next.system ||= {loading:false,error:'',score:0,status:'Checking',cpu:0,memory:0,disk:0,network:0,ports:[],processes:[],environment:[],prec:{stage:'Discover',health:0,traces:0},runtime:{status:'checking'},updatedAt:0};
      next.settings ||= {theme:'black-chrome',typeScale:Number(localStorage.getItem('beast.setting.typeScale')||1),density:localStorage.getItem('beast.setting.density')||'comfortable',motion:localStorage.getItem('beast.setting.motion')||'balanced',atmosphere:localStorage.getItem('beast.setting.atmosphere')||'matrix-grid',audio:localStorage.getItem('beast.setting.audio')!=='off',reducedGlow:localStorage.getItem('beast.setting.reducedGlow')==='on',autoRefresh:localStorage.getItem('beast.setting.autoRefresh')!=='off',commandConfirm:true,sourcePlanRequired:true,evidenceClosure:true,updatedAt:0};
      next.worktrees ||= {loading:false,error:'',root:'',registryRoot:'',items:[],selectedId:'',diff:'',creating:false,updatedAt:0};
      next.deploy ||= {loading:false,error:'',score:0,status:'Not Checked',stages:[],blockers:[],manifest:{},ports:[],lastRunbook:null,updatedAt:0};
      next.chronicle ||= {loading:false,error:'',events:[],filtered:[],selectedId:'',filter:'all',query:'',insights:[],sensorium:{},updatedAt:0};
      next.economy ||= {loading:false,error:'',tokensSaved:0,reuseRate:0,compression:0,cacheHit:0,costAvoided:'unreported',callsDisplaced:0,providerMix:[],strategies:[],history:[],measurement:'',updatedAt:0};
      next.system ||= {loading:false,error:'',score:0,status:'Checking',cpu:0,memory:0,disk:0,network:0,ports:[],processes:[],environment:[],prec:{stage:'Discover',health:0,traces:0},runtime:{status:'checking',circuits:0},updatedAt:0};
      next.platform ||= {loading:false,error:'',status:'checking',health:0,summary:{},sections:[],snapshots:{},raw:null,updatedAt:0};
      next.studio ||= {loading:false,error:'',health:0,phase:0,completed:0,total:0,systems:[],quickActions:[],updatedAt:0};
      const phase8Steps=[['providers','Providers'],['system','System'],['worktrees','Worktrees'],['deploy','Deploy'],['chronicle','Chronicle'],['economy','Compute Economy'],['settings','Settings'],['studio','Studio']];
      for (const [id,title] of phase8Steps) if (!next.mission.path.some(step=>step.id===id)) next.mission.path.push({id,title,status:'Unverified'});
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
      BeastStore.patch('providers',{loading:false,registry:seeded.providers,activeId:'ollama',selectedId:BeastStore.get().providers.selectedId||'ollama',routeTrials:seeded.providers.map((p,i)=>({provider:p.id,quality:p.confidence,latency:[42,780,1100,1300][i],cost:i?55+i*12:0})),economist:{winner:'ollama',reason:'Local-first route meets quality threshold at zero marginal cost.',saving:'100%'},runtime:{status:'healthy',uptime:'8h 42m'},updatedAt:now()});
      return seeded.providers;
    }
    try {
      const [registryPayload,statePayload,runtimePayload,kvPayload,litellmPayload] = await Promise.all([
        request('/edgek/providers/registry'), request('/edgek/providers/state'), request('/edgek/runtime/state'), request('/edgek/kv-cache/state'), request('/edgek/deploy/litellm-sidecar/state')
      ]);
      const credentials=statePayload?.credentials&&typeof statePayload.credentials==='object'?statePayload.credentials:{};
      const credentialAlias={codex:'openai',local_nim:'nvidia_nim'};
      const rows=list(registryPayload,'providers','items','registry').map((row,index)=>{
        const id=idOf(row,index);const credentialKey=credentialAlias[id]||id;
        const credentialKnown=Object.prototype.hasOwnProperty.call(credentials,credentialKey);
        const credentialReady=credentialKnown?Boolean(credentials[credentialKey]):null;
        return {...row,id,label:row.label||row.name||row.provider_id||id,kind:row.kind||row.type||row.backend||'Provider',
          status:row.status||row.health||(credentialReady===false?'credential missing':'ready'),credentialReady,
          models:numeric(row.models?.length ?? row.model_count, row.default_model?1:0),defaultModel:row.default_model||'',latency:row.latency||row.p50||'n/a',
          cost:row.cost||row.pricing||'unreported',confidence:numeric(row.confidence||row.health_score,credentialReady===true?100:0),route:row.route||row.role||'candidate'};
      });
      const active=statePayload?.active_provider||statePayload?.provider||rows.find(row=>row.credentialReady!==false)?.id||rows[0]?.id||'';
      const routeTrials=list(statePayload,'route_trials','trials').map((row,index)=>({provider:row.provider||row.provider_id||rows[index]?.id||`route-${index}`,quality:numeric(row.quality||row.confidence||row.score),latency:numeric(row.latency_ms||row.latency),cost:row.cost??row.cost_estimate??'unreported'}));
      const litellmReady=litellmPayload?.running===true && litellmPayload?.health?.responding===true;
      const selected=BeastStore.get().providers.selectedId;
      BeastStore.patch('providers',{loading:false,registry:rows,activeId:active,selectedId:rows.some(row=>row.id===selected)?selected:active,policy:statePayload?.policy||'credential-aware live registry',cloudAllowed:Boolean(statePayload?.cloud_allowed),compression:statePayload?.compression_enabled===true,kvCache:kvPayload?.enabled===true,credentials,runtime:{status:litellmReady?'LiteLLM ready via /v1/models':runtimePayload?.status||runtimePayload?.health||'unknown',uptime:runtimePayload?.uptime||'n/a',litellm:{running:litellmPayload?.running===true,path:litellmPayload?.health?.path||'',statusCode:litellmPayload?.health?.status_code||0,baseUrl:litellmPayload?.base_url||''}},routeTrials,updatedAt:now()});
      return rows;
    } catch (error) { BeastStore.patch('providers',{loading:false,error:String(error.message||error),registry:[],activeId:'',selectedId:'',routeTrials:[],updatedAt:now()}); throw error; }
  }

  async function selectProvider(id) {
    const provider=BeastStore.get().providers.registry.find(row=>row.id===id);
    if (!provider) throw new Error('Select a provider from the live registry first.');
    BeastStore.patch('providers',{selectedId:id}); localStorage.setItem('beast.provider',id);
    if (demoMode) { BeastStore.addLedger(`Demo provider selected: ${provider.label||id}`); return provider; }
    if (BeastStore.get().connection.status!=='online') throw new Error('Provider activation requires a live gateway.');
    const candidate={provider:id,recommended_role:provider.route||'unknown',auth_confidence:numeric(provider.auth_confidence),sample_size:numeric(provider.sample_size),hidden_clean_completed:numeric(provider.hidden_clean_completed),hidden_clean_rate:numeric(provider.hidden_clean_rate),rescued_completed:numeric(provider.rescued_completed),latency_ms:numeric(provider.latency_ms),cost_observed:provider.cost_observed===true};
    const payload=await request('/edgek/provider-economist/select',{method:'POST',body:{objective:BeastStore.get().mission.title,candidates:[candidate],root_path:workspaceRoot()}});
    const selected=payload?.selected?.provider||payload?.provider||payload?.selected_provider;
    if (!selected) throw new Error(payload?.reason || 'Provider Economist has no eligible route; run a real route diagnostic first.');
    BeastStore.patch('providers',{activeId:selected,economist:{winner:selected,reason:payload.reason||payload.explanation||'Selected by Provider Economist',saving:payload.saving||payload.cost_saving||'unreported'}});
    BeastStore.addLedger(`Provider route selected by Economist: ${provider.label||id}`);
    return payload;
  }

  async function providerAction(action) {
    if (action==='compression') {
      const next=!BeastStore.get().providers.compression;
      if (demoMode) { BeastStore.patch('providers',{compression:next}); return {enabled:next,demo:true}; }
      const result=await request('/edgek/providers/compression/toggle',{method:'POST',body:{enabled:next}});
      if (typeof result?.enabled!=='boolean') throw new Error('Compression control returned no authoritative state.');
      BeastStore.patch('providers',{compression:result.enabled});
      BeastStore.addLedger(`Provider compression ${result.enabled?'enabled':'disabled'}`);
      return result;
    }
    if (action==='cache-clear') {
      if (demoMode) { BeastStore.addLedger('Demo KV cache cleared'); return {cleared:true,demo:true}; }
      const result=await request('/edgek/providers/kv-cache/clear',{method:'POST',body:{root_path:workspaceRoot()}});
      if (result?.cleared!==true) throw new Error('KV cache clear was not confirmed by the gateway.');
      BeastStore.addLedger('Provider KV cache cleared');
      return result;
    }
    if (action==='smoke') {
      const selected=BeastStore.get().providers.selectedId;
      if (!selected) throw new Error('Select a live provider before smoke testing.');
      const result=selected.includes('nvidia') ? await request('/edgek/providers/nvidia-nim/live-smoke',{method:'POST',body:{model:localStorage.getItem('beast.model')||'',prompt:'Reply with BEAST route ready.',confirm_live:true},timeout:15000}) : await request(`/edgek/route/provider-diagnostic/${encodeURIComponent(selected)}`,{method:'POST',body:{root_path:workspaceRoot(),objective:BeastStore.get().mission.title},timeout:15000});
      const trial={provider:selected,quality:numeric(result?.route_quality_score??result?.quality??result?.score,0),latency:result?.latency_ms??result?.latency??'diagnostic complete',cost:result?.cost_estimate??result?.cost??'governed'};
      const prior=BeastStore.get().providers.routeTrials||[];
      BeastStore.patch('providers',{routeTrials:[trial,...prior.filter(row=>row.provider!==selected)].slice(0,12),economist:{...BeastStore.get().providers.economist,winner:selected,reason:result?.reason||result?.summary||`Route diagnostic completed for ${selected}`},error:''});
      BeastStore.addLedger(`Provider diagnostic completed: ${selected}`);
      document.dispatchEvent(new CustomEvent('beast:operation',{detail:{message:`Route diagnostic complete · ${selected} · ${Math.round(trial.quality)}% quality`,tone:'ok'}}));
      return result;
    }
  }

  async function refreshPlatform() {
    ensureState();
    BeastStore.patch('platform',{loading:true,error:''});
    BeastStore.patch('system',{loading:true,error:''});
    if (demoMode) {
      BeastStore.patch('platform',{loading:false,status:seeded.platform.status,health:seeded.platform.health,summary:seeded.platform.summary,sections:seeded.platform.sections,snapshots:{},updatedAt:now()});
      BeastStore.patch('system',{loading:false,score:94,status:'Nominal',cpu:28,memory:61,disk:46,network:18,ports:seeded.ports,processes:seeded.processes,environment:[['OS','Linux x86_64'],['Python','3.13'],['Node','22.x'],['Electron','ready'],['CUDA','12.4']],prec:{stage:'Reintegrate',health:92,traces:1842},runtime:{status:'healthy',circuits:0},updatedAt:now()});
      return seeded.platform;
    }
    try {
      const params=new URLSearchParams({session_id:'default',limit:'8',route_limit:'10',event_limit:'8',process_limit:'30',port_limit:'40'});
      if(workspaceRoot()) params.set('root_path',workspaceRoot());
      const [platformPayload,rootPayload]=await Promise.all([request(`/edgek/platform/snapshot?${params}`,{timeout:15000}),request('/edgek/root-info')]);
      const snapshot = platformPayload;
      const systemPayload = snapshot.snapshots?.system || snapshot.system || {};
      const runtimePayload = snapshot.snapshots?.runtime || snapshot.runtime || {};
      const precPayload = snapshot.snapshots?.prec || snapshot.prec || {};
      const ports = list(systemPayload,'ports','listening_ports').map((row,index)=>({port:row.port||row.local_port||index,service:row.service||row.process||row.name||'unknown',status:row.status||'listening',pid:row.pid,address:row.address||row.host||'127.0.0.1'}));
      const processes = list(systemPayload,'processes','process_list').map(row=>({pid:row.pid,name:row.name||row.command||'process',cpu:numeric(row.cpu||row.cpu_percent),memory:row.memory||row.rss||'n/a',status:row.status||'running'}));
      const cpuValue=systemPayload?.cpu?.percent ?? systemPayload?.cpu_percent ?? systemPayload?.resources?.cpu;
      const memoryValue=systemPayload?.memory?.percent ?? systemPayload?.memory_percent ?? systemPayload?.resources?.memory;
      const diskValue=systemPayload?.disk?.percent ?? systemPayload?.disk_percent ?? systemPayload?.resources?.disk;
      const hasResourceTelemetry=[cpuValue,memoryValue,diskValue].some(value=>Number.isFinite(Number(value)));
      const cpu=numeric(cpuValue,0);
      const memory=numeric(memoryValue,0);
      const disk=numeric(diskValue,0);
      const score=hasResourceTelemetry?Math.max(0,Math.round(100-(cpu*.15+memory*.2+disk*.1)-(runtimePayload?.circuit_breakers?.open||0)*8)):0;
      const recentPrec=Array.isArray(precPayload?.recent)?precPayload.recent[0]:{};
      const precCounts=Array.isArray(precPayload?.counts)?precPayload.counts:[];
      const precTraceCount=precCounts.reduce((sum,row)=>sum+Number(row.count||0),0);
      const precStage=recentPrec.current_phase||precPayload?.stage||precPayload?.lifecycle_stage||'perceive';
      const precHealth=Number(precPayload?.health||precPayload?.score)|| (precTraceCount?Math.min(100,Math.round(60+Math.log10(precTraceCount+1)*12)):0);
      const sections = Array.isArray(snapshot.sections) ? snapshot.sections : [];
      BeastStore.patch('platform',{loading:false,status:snapshot.status||'watch',health:numeric(snapshot.health,Math.round(sections.length?sections.filter(section=>!/needs attention|watch|failed/i.test(String(section.status||''))).length/sections.length*100:0)),summary:snapshot.summary||{},sections,snapshots:snapshot.snapshots||{},raw:snapshot,updatedAt:now()});
      BeastStore.patch('system',{loading:false,score,status:hasResourceTelemetry?(score>85?'Nominal':score>65?'Degraded':'Critical'):'Unreported',cpu,memory,disk,network:numeric(systemPayload?.network?.percent||0),ports,processes,environment:Object.entries(rootPayload||{}).slice(0,10),prec:{stage:precStage,health:precHealth,traces:numeric(precPayload?.traces||precPayload?.trace_count,precTraceCount)},runtime:{status:runtimePayload?.status||'unknown',circuits:numeric(runtimePayload?.circuit_breakers?.open)},updatedAt:now()});
      return snapshot;
    } catch(error){
      BeastStore.patch('platform',{loading:false,error:String(error.message||error),status:'offline',health:0,sections:[],summary:{},snapshots:{},raw:null,updatedAt:now()});
      BeastStore.patch('system',{loading:false,error:String(error.message||error),status:'Offline',score:0,ports:[],processes:[],updatedAt:now()});
      throw error;
    }
  }

  async function refreshSystem() {
    return refreshPlatform();
  }

  async function systemAction(action, payload={}) {
    const contract={
      sweep:['/edgek/runtime/sweep',{root_path:workspaceRoot()},'Runtime sweep'],
      'free-port':['/edgek/ide/ports/free',{port:Number(payload.port),root_path:workspaceRoot()},`Port ${payload.port} release`],
      kill:['/edgek/ide/system/kill',{pid:Number(payload.pid),root_path:workspaceRoot()},`Process ${payload.pid} stop`]
    }[action];
    if (!contract) throw new Error(`Unsupported system action: ${action}`);
    const [endpoint,body,label]=contract;
    const mutation=action==='free-port'||action==='kill';
    const response=demoMode?{ok:true,demo:true}:await request(endpoint,{method:'POST',body:{...body,approved:mutation?Boolean(payload.approved):undefined,dry_run:mutation?Boolean(payload.dryRun):undefined}});
    if (payload.dryRun) return response;
    const normalized=action==='sweep'&&response&&response.ok===undefined?{...response,ok:true}:response;
    const result=requireConfirmation(normalized,label);
    BeastStore.addLedger(`${label} confirmed${result.demo?' (demo)':''}`);
    await refreshSystem();
    document.dispatchEvent(new CustomEvent('beast:operation',{detail:{message:action==='sweep'?`Runtime sweep complete · ${Number(result.swept_attempts||0)} expired attempt(s) cleared`:`${label} confirmed`,tone:'ok'}}));
    return result;
  }

  async function previewSystemAction(action, payload={}) {
    const result=await systemAction(action,{...payload,dryRun:true});
    const targets=action==='free-port'?(result.results||[]):[result];
    const protectedTarget=targets.find(item=>item?.protected);
    if (protectedTarget) throw new Error(`Protected target: ${protectedTarget.protected_reason||'this process cannot be stopped from the IDE'}.`);
    if (!result?.ok) throw new Error(result?.error||result?.reason||'The system action preview was not accepted by the gateway.');
    return result;
  }

  function updateSettings(partial) {
    ensureState(); BeastStore.patch('settings',{...partial,updatedAt:now()});
    const settings=BeastStore.get().settings;
    Object.entries(settings).forEach(([key,value])=>{ if(['updatedAt'].includes(key)) return; localStorage.setItem(`beast.setting.${key}`,typeof value==='boolean'?(value?'on':'off'):String(value)); });
    applySettings(settings); BeastStore.addLedger('IDE presentation settings updated');
  }

  async function refreshWorktrees() {
    const registryRoot=BeastStore.get().worktrees.registryRoot||workspaceRoot();
    ensureState(); BeastStore.patch('worktrees',{loading:true,error:'',root:registryRoot});
    if(demoMode){ BeastStore.patch('worktrees',{loading:false,items:seeded.worktrees,selectedId:BeastStore.get().worktrees.selectedId||seeded.worktrees[0].id,diff:'9 files changed\n+342 additions\n-78 deletions',updatedAt:now()}); return; }
    try{
      const params=new URLSearchParams(); if(registryRoot)params.set('root_path',registryRoot);
      const registry=await request(`/edgek/ide/worktree-mission/list?${params}`);
      let rows=list(registry,'tasks','items','missions');
      rows=rows.map((row,index)=>({...row,id:idOf(row,index),label:row.label||row.objective||row.title||idOf(row,index),branch:row.branch||row.branch_name||'unresolved',path:row.path||row.worktree_path||'',status:row.status||'unreported',progress:numeric(row.progress),tests:row.tests||row.test_status||'unreported',changes:numeric(row.changes||row.changed_files),owner:row.owner||row.agent||'unreported'}));
      BeastStore.patch('worktrees',{loading:false,root:registry.workspace_root||registryRoot,registryRoot:registry.workspace_root||registryRoot,items:rows,selectedId:BeastStore.get().worktrees.selectedId||rows[0]?.id||'',updatedAt:now()});
    }catch(error){BeastStore.patch('worktrees',{loading:false,root:registryRoot,error:String(error.message||error),items:[],selectedId:'',updatedAt:now()});}
  }

  async function worktreeAction(action,id,extra={}) {
    const item=BeastStore.get().worktrees.items.find(row=>row.id===id);
    if(action==='select'){BeastStore.patch('worktrees',{selectedId:id});return;}
    const endpoint={create:'/edgek/ide/worktree-mission/create',test:'/edgek/ide/worktree-mission/test',diff:'/edgek/ide/worktree-mission/diff',close:'/edgek/ide/worktree-mission/close',sourceplan:'/edgek/ide/worktree-mission/sourceplan-draft'}[action];
    if (!endpoint) throw new Error(`Unsupported worktree action: ${action}`);
    if (!demoMode && action !== 'create' && !item) throw new Error('Select a live worktree mission first.');
    BeastStore.patch('worktrees',{creating:action==='create',error:''});
    try {
      const objective=extra.objective||item?.label||BeastStore.get().mission.draftObjective||BeastStore.get().mission.title;
      const result=demoMode?{ok:true,demo:true}:requireConfirmation(await request(endpoint,{method:'POST',body:{root_path:BeastStore.get().worktrees.registryRoot||workspaceRoot(),task_id:id,objective,branch:item?.branch}}),`Worktree ${action}`);
      if(action==='diff') BeastStore.patch('worktrees',{diff:result?.diff||result?.patch||''});
      if(action==='create' && result?.task?.task_id) BeastStore.patch('worktrees',{selectedId:String(result.task.task_id),registryRoot:String(result.task.workspace_root||workspaceRoot())});
      if(!demoMode && ['create','close','test'].includes(action)) await refreshWorktrees();
      BeastStore.addLedger(`Worktree ${action} confirmed: ${id||extra.objective||'new mission'}`);
      document.dispatchEvent(new CustomEvent('beast:operation',{detail:{message:action==='sourceplan'?'SourcePlan draft created for the selected worktree.':`Worktree ${action} complete`,tone:'ok'}}));
      return result;
    } finally { BeastStore.patch('worktrees',{creating:false}); }
  }

  async function refreshDeploy() {
    ensureState(); BeastStore.patch('deploy',{loading:true,error:''});
    if(demoMode){ BeastStore.patch('deploy',{loading:false,score:88,status:'Ready with Warnings',stages:[{id:'build',label:'Build',status:'passed'},{id:'tests',label:'Tests',status:'passed'},{id:'policy',label:'Policy',status:'passed'},{id:'evidence',label:'Evidence',status:'passed'},{id:'ports',label:'Ports',status:'warning'},{id:'release',label:'Release',status:'ready'}],blockers:[{severity:'warning',label:'Port 8082 currently reserved by preview server'}],manifest:{version:'v0.9.0-phase8',artifacts:18,checksums:18,rollback:'available',target:'local desktop'},ports:seeded.ports,lastRunbook:{id:'RUNBOOK-P8-DEMO',verified:true},updatedAt:now()}); return; }
    try{
      const body={root_path:workspaceRoot(),objective:BeastStore.get().mission.title};
      const [readiness,ports,runbook]=await Promise.all([request('/edgek/ide/release-readiness/check',{method:'POST',body}),request('/edgek/ide/ports?limit=200'),request('/edgek/ide/mission-runbook/verify',{method:'POST',body})]);
      if(readiness?.ok===false&&readiness?.status==='error') throw new Error(readiness.error||'IDE readiness check failed before producing a report.');
      const checks=list(readiness,'checks','gates','stages'); const stages=checks.length?checks.map((row,index)=>({id:idOf(row,index),label:row.label||row.name||row.check||idOf(row,index),status:row.status||((row.ok===true||row.passed===true)?'passed':'warning')})):[];
      const blockers=list(readiness,'blockers','issues','warnings').map(row=>typeof row==='string'?{severity:'warning',label:row}:{severity:row.severity||'warning',label:row.label||row.detail||row.message});
      const score=numeric(readiness?.score||readiness?.readiness_score,readiness?.summary?.checks?Number(readiness.summary.passed||0)/Number(readiness.summary.checks)*100:stages.length?stages.filter(s=>/pass|ready/i.test(s.status)).length/stages.length*100:0);
      BeastStore.patch('deploy',{loading:false,score:Math.round(score),status:readiness?.status||'unreported',stages,blockers,manifest:readiness?.manifest||readiness?.release||{},ports:list(ports,'ports','items'),lastRunbook:runbook,error:'',updatedAt:now()});
      document.dispatchEvent(new CustomEvent('beast:operation',{detail:{message:`IDE readiness checked · ${Math.round(score)}% · ${readiness?.summary?.passed||0}/${readiness?.summary?.checks||0} gates passed`,tone:readiness?.ok===false?'warning':'ok'}}));
    }catch(error){const message=String(error.message||error);BeastStore.patch('deploy',{loading:false,status:'readiness error',error:message,blockers:[{severity:'critical',label:`Readiness could not run: ${message}`}],updatedAt:now()});document.dispatchEvent(new CustomEvent('beast:operation',{detail:{message:`IDE readiness failed · ${message}`,tone:'error'}}));}
  }

  async function deployAction(action) {
    const body={root_path:workspaceRoot(),objective:BeastStore.get().mission.title};
    let result=null;
    if(action==='export') result=demoMode?{runbook_id:'RUNBOOK-P8-DEMO',ok:true}:requireConfirmation(await request('/edgek/ide/mission-runbook/export',{method:'POST',body,timeout:12000}),'Runbook export');
    if(action==='verify') result=demoMode?{verified:true}:requireConfirmation(await request('/edgek/ide/mission-runbook/verify',{method:'POST',body,timeout:12000}),'Runbook verification');
    if(action==='check') return refreshDeploy();
    if (!['export','verify'].includes(action)) throw new Error(`Unsupported deploy action: ${action}`);
    BeastStore.patch('deploy',{lastRunbook:result||BeastStore.get().deploy.lastRunbook}); BeastStore.addLedger(`Deploy ${action} confirmed`); document.dispatchEvent(new CustomEvent('beast:operation',{detail:{message:`Release runbook ${action} complete`,tone:'ok'}})); return result;
  }

  async function refreshChronicle() {
    ensureState(); BeastStore.patch('chronicle',{loading:true,error:''});
    if(demoMode){ BeastStore.patch('chronicle',{loading:false,events:seeded.chronicle,filtered:seeded.chronicle,selectedId:BeastStore.get().chronicle.selectedId||seeded.chronicle[0].id,insights:['Local-first routing displaced 17 cloud calls.','Evidence closure improved from 82% to 96%.','One memory compaction warning remains.'],updatedAt:now()}); return; }
    try{
      const [payload,sensorium,observatory]=await Promise.all([
        request('/edgek/chronicle?limit=80'),
        request('/edgek/sensorium/state?event_limit=25&episode_limit=10'),
        request('/edgek/observatory')
      ]);
      const rows=list(payload,'chronicles','entries','events','records','items').map((row,index)=>{
        const category=String(row.kind||row.category||row.type||row.chronicle_type||'system').toLowerCase();
        const kind=/provider/.test(category)||row.provider&&row.provider!=='local'?'provider':/evidence|intercept/.test(category)?'evidence':/agent|swarm/.test(category)?'agent':/runtime|sensor/.test(category)?'runtime':/govern|trust|policy/.test(category)?'governance':'system';
        const severity=row.severity||row.status||(/auth|error|fail|warning/.test(category)?'warning':row.memory_candidate?'success':'info');
        return {...row,id:idOf(row,index),time:row.time||row.timestamp||row.created_at||'',kind,label:row.label||row.event||row.title||row.action||row.summary||'BEAST event',detail:row.detail||row.message||row.root_cause||row.summary||'',actor:row.actor||row.source||row.agent||row.provider||row.task_id||'BEAST',severity};
      });
      const current=BeastStore.get().chronicle;
      const query=String(current.query||'').toLowerCase(), filter=current.filter||'all';
      const filtered=rows.filter(row=>(filter==='all'||row.kind===filter||row.severity===filter)&&(!query||`${row.label} ${row.detail} ${row.actor}`.toLowerCase().includes(query)));
      BeastStore.patch('chronicle',{loading:false,events:rows,filtered,selectedId:current.selectedId&&rows.some(row=>row.id===current.selectedId)?current.selectedId:filtered[0]?.id||rows[0]?.id||'',sensorium:{...sensorium,observatory},updatedAt:now()});
    }catch(error){BeastStore.patch('chronicle',{loading:false,error:String(error.message||error),events:[],filtered:[],selectedId:'',updatedAt:now()});}
  }

  function filterChronicle({query,filter}={}) {
    const current=BeastStore.get().chronicle; const q=(query??current.query).toLowerCase(); const f=filter??current.filter;
    const filtered=current.events.filter(row=>(f==='all'||row.kind===f||row.severity===f)&&(!q||`${row.label} ${row.detail} ${row.actor}`.toLowerCase().includes(q)));
    BeastStore.patch('chronicle',{query:query??current.query,filter:f,filtered});
  }
  function selectChronicle(id){BeastStore.patch('chronicle',{selectedId:id});}
  async function compileInsights(){ const result=demoMode?{insights:['Provider economy saved an estimated 1.24M tokens.','Review contradictions dropped by 67%.','Runtime health remained above 92%.']}:await request('/edgek/insights/compile',{method:'POST',body:{root_path:workspaceRoot(),objective:BeastStore.get().mission.title,scope:'desktop IDE operator workflow',success_criteria:['surface actionable findings','show PREC lifecycle context']}}); const raw=[...list(result,'insights','findings','items'),...(result?.ranked||[]),...(result?.evidence||[])]; const insights=raw.map(x=>typeof x==='string'?x:x.label||x.detail||x.summary||x.recommended_action||x.recommended_actions?.[0]).filter(Boolean); if(!insights.length&&result?.summary) insights.push(String(result.summary)); if(!insights.length) throw new Error('Insight Compiler returned no displayable findings.'); BeastStore.patch('chronicle',{insights,error:''}); return result; }

  async function refreshEconomy() {
    ensureState(); BeastStore.patch('economy',{loading:true,error:''});
    if(demoMode){ BeastStore.patch('economy',{loading:false,tokensSaved:1240000,reuseRate:78,compression:63,cacheHit:84,costAvoided:'R18,420',callsDisplaced:317,providerMix:[{label:'Local',value:72},{label:'NIM',value:18},{label:'Other Cloud',value:10}],strategies:[{label:'Local-first cascade',gain:94,status:'active'},{label:'Crystal reuse',gain:78,status:'active'},{label:'Context compression',gain:63,status:'active'},{label:'KV cache',gain:84,status:'active'}],history:[42,48,55,61,67,72,78,84],updatedAt:now()}); return; }
    try{
      const [economy,reuse,compression,kv,providers]=await Promise.all([request('/edgek/commons-economy'),request('/edgek/crystal-reuse'),request('/edgek/compression/pipeline'),request('/edgek/kv-cache/state'),request('/edgek/providers/state')]);
      const storage=reuse?.storage||{};
      const tokens=numeric(economy?.tokens_saved||economy?.saved_tokens||reuse?.measured_saved_tokens||storage?.measured_reuse_tokens_saved||storage?.total_avoided_tokens);
      const calls=numeric(economy?.calls_displaced||reuse?.reuse_hit_count||storage?.total_reuse_count);
      const reuseRate=numeric(reuse?.reuse_rate??reuse?.hit_rate, 0);
      const comp=numeric(compression?.ratio_percent||compression?.saving_percent||compression?.compression_rate);
      const cache=numeric(kv?.hit_rate||kv?.hit_percent||kv?.stats?.hit_rate);
      const creditUnits=numeric(economy?.issued_units);
      const measuredStrategies=list(economy,'strategies','interventions').map(row=>({label:row.label||row.name||'Measured intervention',gain:numeric(row.gain||row.value||row.score),status:row.status||'unreported'}));
      const strategies=measuredStrategies.length?measuredStrategies:[
        {label:'Crystal reuse',gain:reuseRate,status:calls?`${calls} recorded reuse event(s)`:'no recorded reuse events'},
        {label:'Context compression',gain:comp,status:compression?.enabled?`${compression.backend||'local'} ready; no measured reduction yet`:'disabled'},
        {label:'KV cache',gain:cache,status:Number(kv?.total_blocks||0)?`${kv.total_blocks} cache block(s) observed`:'no cache blocks observed'}
      ];
      const providerMix=list(providers,'mix','provider_mix');
      const observedMix=providerMix.length?providerMix:(calls?[{label:'Local crystal reuse',value:calls}]:[]);
      BeastStore.patch('economy',{loading:false,tokensSaved:tokens,reuseRate,compression:comp,cacheHit:cache,costAvoided:economy?.cost_avoided||economy?.saved_cost||'unreported',callsDisplaced:calls,providerMix:observedMix,strategies,history:list(economy,'history','series').map(row=>numeric(row.value??row)),measurement:`${tokens} observed avoided token(s) · ${creditUnits} non-financial verified credit unit(s) · ${Number(economy?.adoption_history?.verified_count||0)} verified adoption(s)`,updatedAt:now()});
    }catch(error){BeastStore.patch('economy',{loading:false,error:String(error.message||error),updatedAt:now()});}
  }

  async function refreshStudio() {
    ensureState();
    const s=BeastStore.get();
    const live=s.connection.status==='online';
    const stateOf=(verified, available=live)=>verified?'verified':available?'available':'offline';
    const systems=[
      ['Editor Cortex',Boolean(s.workspace.root||s.editor.activePath)],['SourcePlan',Boolean(s.sourcePlan.updatedAt||s.sourcePlan.plan)],['Models',s.models.registry.length>0],['Agents',s.agents.lastRefreshAt>0],
      ['Review',Boolean(s.review.updatedAt||s.review.gates.length)],['Evidence',Boolean(s.evidence.updatedAt||s.evidence.files.length)],['Trust',Boolean(s.trust.updatedAt||s.trust.score>0)],['Memory',Boolean(s.memory.updatedAt||s.memory.records>0)],['Map',Boolean(s.map.updatedAt||s.map.nodes.length)],['Crystal',Boolean(s.crystal.updatedAt||s.crystal.candidates.length)],
      ['Terminal',Boolean(s.terminal.chatSessionId||s.terminal.executions?.length)],['Tooling',Boolean(s.tooling.updatedAt)],['Doctor',Boolean(s.doctor.lastScanAt)],['Providers',s.providers.registry.length>0],['System',Boolean(s.system.updatedAt)],['Platform Atlas',Boolean(s.platform.updatedAt||s.platform.sections?.length)]
    ].map(([label,verified],index)=>{const status=stateOf(verified);return{id:`sys-${index}`,label,ready:status!=='offline',status,verified};});
    const health=Math.round(systems.filter(x=>x.ready).length/systems.length*100);
    const completed=systems.filter(x=>x.ready).length;
    BeastStore.patch('studio',{loading:false,health,phase:completed,total:systems.length,completed,systems,quickActions:[
      {route:'mission',label:'Mission Control'},
      {route:'workspace',label:'Editor Cortex'},
      {route:'atlas',label:'Systems Atlas'},
      {route:'providers',label:'RAG + KV Cache'},
      {route:'system',label:'Runtime + PREC'},
      {route:'agents',label:'Swarm'},
      {route:'memory',label:'Memory Atlas'},
      {route:'chronicle',label:'Chronicle + Sensorium'},
      {route:'terminal',label:'Terminal Nexus'},
      {route:'deploy',label:'Release Readiness'},
      {route:'economy',label:'Economizer'}
    ],updatedAt:now()});
  }

  async function refreshAll() {
    ensureState();
    // The platform snapshot compiles an operator-grade cross-plane report.  Do not
    // stampede that expensive endpoint during every IDE boot; System/Atlas owns it.
    return Promise.allSettled([refreshProviders(),refreshWorktrees(),refreshDeploy(),refreshChronicle(),refreshEconomy()]).then(()=>refreshStudio());
  }

  ensureState();
  window.BeastUtilityOrchestrationBridge={ensureState,applySettings,refreshProviders,selectProvider,providerAction,refreshPlatform,refreshSystem,systemAction,previewSystemAction,updateSettings,refreshWorktrees,worktreeAction,refreshDeploy,deployAction,refreshChronicle,filterChronicle,selectChronicle,compileInsights,refreshEconomy,refreshStudio,refreshAll};
})();
