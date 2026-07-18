(() => {
  const firstArray = (...values) => (values.find(Array.isArray) || []).filter(item => item != null);
  const clamp = value => Math.max(0, Math.min(100, Number(value) || 0));
  const settled = result => result?.status === 'fulfilled' ? result.value : null;
  const label = (value, fallback='Unknown') => {
    if (value == null) return fallback;
    if (typeof value === 'string' || typeof value === 'number') return String(value);
    return String(value.label || value.name || value.title || value.id || value.key || fallback);
  };
  const timeLabel = value => {
    if (!value) return 'live';
    const text = String(value);
    const date = new Date(text);
    return Number.isNaN(date.getTime()) ? text : date.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'});
  };
  const rootQuery = () => {
    const root = BeastStore.get().workspace.root;
    return root ? `?root_path=${encodeURIComponent(root)}` : '';
  };

  const demoTrust = {
    score: 96,
    status: 'Secure',
    policy: 'Local First',
    systemsTotal: 31,
    systemsHealthy: 30,
    warnings: 1,
    failedChecks: 0,
    boundary: { mode:'Local-First', network:'Governed', telemetry:'Disabled', airGap:true },
    integrity: { status:'Verified', agents:7, models:4, evidence:23, files:1284, lastChecked:'8s ago' },
    guardrails: { status:'Enforced', decisions:28, approvals:4, violations:0, leastPrivilege:true },
    provenance: { rootId:'c3b7e2f0…9a17d2e1', algorithm:'SHA-256', signedBy:'BEAST Operator', signedAt:'14:31:05', valid:true },
    canaries: [
      {id:'file',label:'File Canary',status:'Healthy',detail:'Workspace integrity stable'},
      {id:'network',label:'Network Canary',status:'Healthy',detail:'No uncontrolled egress'},
      {id:'agent',label:'Agent Canary',status:'Healthy',detail:'Mission scopes enforced'},
      {id:'memory',label:'Memory Canary',status:'Watch',detail:'One residue nearing compaction'}
    ],
    controls: [
      {id:'evidence',label:'Evidence Verification',status:'Enforced',detail:'All proof artifacts require traceable validation.'},
      {id:'agent',label:'Agent Verification',status:'Enforced',detail:'Agent passports and mission scopes are checked.'},
      {id:'signing',label:'Artifact Signing',status:'Required',detail:'Committed outputs require a valid provenance signature.'},
      {id:'change',label:'Change Approvals',status:'Required',detail:'SourcePlan mutations require governed approval.'},
      {id:'policy',label:'Policy Enforcement',status:'Enforced',detail:'Local-first and least-privilege guardrails are active.'},
      {id:'access',label:'Access Reviews',status:'Scheduled',detail:'Permission posture is periodically recalculated.'}
    ],
    permissions: [
      {role:'You (Owner)',access:'Full Control',scope:'Mission + Workspace',status:'Verified'},
      {role:'Planner Agent',access:'Mission Write',scope:'Plans + Runbooks',status:'Verified'},
      {role:'Graph Analyst',access:'Evidence Read',scope:'Code Graph',status:'Verified'},
      {role:'Profiler Agent',access:'Evidence Read',scope:'Runtime Telemetry',status:'Verified'},
      {role:'Verifier Agent',access:'Verify Only',scope:'Evidence + Gates',status:'Verified'}
    ],
    attestations: [
      {id:'att-9f2b7c4a',label:'System Attestation',status:'Valid',expires:'15:31:05'},
      {id:'att-a812c0e1',label:'Workspace Attestation',status:'Valid',expires:'15:28:11'},
      {id:'att-77bc8d09',label:'Agent Passport Set',status:'Valid',expires:'16:00:00'}
    ],
    security: {
      hull:{verified:8,failed:0,status:'Verified'},
      seal:{exists:true,mode:'hardware-bound',status:'Armed'},
      passport:{policies:12,valid:true,status:'Valid'}
    }
  };

  const demoMemory = {
    records:12458,
    evidenceItems:1842,
    recallHealth:94,
    freshness:91,
    compactionQueue:7,
    skillCandidates:4,
    residueQuality:96,
    layers:[
      {id:'L0',name:'Working Memory',scope:'Current mission buffers, active files, and transient route state.',records:128,freshness:99,status:'Hot'},
      {id:'L1',name:'Mission Memory',scope:'Trace-linked decisions, evidence, agent handoffs, and review gates.',records:3421,freshness:96,status:'Warm'},
      {id:'L2',name:'Verified Residue',scope:'Fingerprint-bound inference residue and reusable local capability.',records:6843,freshness:92,status:'Stable'},
      {id:'L3',name:'Archive',scope:'Historical missions, retired routes, and compacted evidence bundles.',records:2066,freshness:78,status:'Cold'}
    ],
    truthStores:[
      {id:'chronicle',label:'Chronicle',records:3861,status:'Healthy'},
      {id:'evidence',label:'Evidence Bus',records:1842,status:'Healthy'},
      {id:'crystal',label:'Crystal Lattice',records:428,status:'Healthy'}
    ],
    retrievalViews:['Mission Recall','Evidence Trace','Agent Handoff','Route Wisdom','Skill Candidates'],
    events:[
      {time:'14:32:11',label:'Mission context compacted into L1'},
      {time:'14:31:58',label:'Evidence residue fingerprint verified'},
      {time:'14:31:42',label:'Route heuristic promoted to skill candidate'},
      {time:'14:31:05',label:'Agent handoff persisted with provenance'},
      {time:'14:30:22',label:'Stale cache entry retired'},
      {time:'14:29:48',label:'Recall graph recalculated'}
    ],
    recallResults:[
      {id:'mem-1',label:'Local-first route decision',layer:'L2',score:98,source:'router.py',age:'2m'},
      {id:'mem-2',label:'Evidence parser edge-case contract',layer:'L1',score:94,source:'parser_design.md',age:'7m'},
      {id:'mem-3',label:'Review gate recipe',layer:'L2',score:91,source:'review receipt',age:'11m'},
      {id:'mem-4',label:'Rollback proof bundle',layer:'L3',score:86,source:'crystal chain',age:'1h'}
    ],
    security: demoTrust.security
  };

  function normalizeSecurity(payload={}) {
    const hull = payload.memory_hull || payload.hull || {};
    const seal = payload.residue_seal || payload.seal || {};
    const passport = payload.agent_passport || payload.passport || {};
    const lint = passport.policy_lint || passport.lint || {};
    const verified = Number(hull.verified_sidecars ?? hull.verified ?? hull.ok ?? 0);
    const failed = Number(hull.failed_sidecars ?? hull.failed ?? hull.errors ?? 0);
    const exists = Boolean(seal.key_exists ?? seal.exists ?? seal.key_mode);
    const policies = Number(lint.policy_count ?? passport.policy_count ?? passport.policies ?? 0);
    const valid = Boolean(lint.valid ?? passport.valid ?? policies > 0);
    return {
      hull:{verified,failed,status:failed ? 'Degraded' : verified ? 'Verified' : 'Checking'},
      seal:{exists,mode:String(seal.key_mode || seal.mode || (exists ? 'available':'unavailable')),status:exists ? 'Armed':'Missing'},
      passport:{policies,valid,status:valid ? 'Valid':'Review'}
    };
  }

  function normalizeTrust(snapshot={}, system={}, securityPayload={}, approvals={}, chronicle={}, enterprise={}) {
    const current = BeastStore.get().trust || {};
    const integrity = system.workspace_integrity || system.integrity || snapshot.workspace_integrity || {};
    const policy = snapshot.policy || system.policy || enterprise.manifests?.policy || {};
    const security = Object.keys(securityPayload || {}).length ? normalizeSecurity(securityPayload) : (current.security || {hull:{verified:0,failed:0,status:'Checking'},seal:{exists:false,mode:'unavailable',status:'Checking'},passport:{policies:0,valid:false,status:'Checking'}});
    const failed = Number(integrity.failed ?? integrity.failures ?? security.hull.failed ?? 0);
    const warnings = Number(integrity.warnings ?? system.warnings ?? (security.seal.exists ? 0 : 1));
    const decisions = Number(policy.architecture_decisions?.decision_count ?? policy.decisions ?? approvals.total ?? 0);
    const healthRaw = integrity.health ?? integrity.score ?? policy.reintegration_health?.score ?? snapshot.health?.score;
    const inferredSignals = Number(security.hull.verified > 0) + Number(security.seal.exists) + Number(security.passport.valid) + Number(Boolean(enterprise.workspace_identity?.digest));
    const inferredScore = security.hull.failed ? 0 : (security.hull.verified ? 35 : 0) + (security.seal.exists ? 30 : 0) + (security.passport.valid ? 20 : 0) + (enterprise.workspace_identity?.digest ? 15 : 0);
    const score = clamp(healthRaw == null ? inferredScore : healthRaw);
    const total = Math.max(0, Number(integrity.total ?? integrity.checks ?? decisions ?? 0) || inferredSignals);
    const healthy = Math.max(0, Number(integrity.passed ?? integrity.healthy ?? 0) || inferredSignals);
    const agentRows = firstArray(snapshot.agent_sessions?.sessions,snapshot.agent_sessions,system.agents);
    const modelRows = firstArray(system.models,system.model_registry,snapshot.models);
    const evidenceRows = firstArray(snapshot.evidence_bus?.receipts,snapshot.evidence_bus?.items,system.evidence);
    const fileCount = Number(snapshot.workspace_files?.count ?? snapshot.workspace_files?.files?.length ?? system.files ?? 0);
    const approvalsRows = firstArray(approvals.approvals,approvals.items,approvals.requests);
    const chronicleRows = firstArray(chronicle.entries,chronicle.records,chronicle.items);
    const provenanceSource = chronicleRows.find(row => row.hash || row.root_id || row.fingerprint) || snapshot.provenance || {};
    const rootId = provenanceSource.root_id || provenanceSource.hash || provenanceSource.fingerprint || current.provenance?.rootId || 'unresolved';
    const derivedControls = [
      {id:'workspace-identity',label:'Workspace Identity Guard',status:enterprise.workspace_identity?.guard_mode || 'reported',detail:enterprise.workspace_identity?.digest ? `Workspace digest ${enterprise.workspace_identity.digest}` : 'Workspace identity was not reported.'},
      {id:'memory-hull',label:'Memory Hull Sidecars',status:security.hull.status,detail:`${security.hull.verified} verified · ${security.hull.failed} failed sidecars`},
      {id:'residue-seal',label:'Residue Seal',status:security.seal.status,detail:`Key mode ${security.seal.mode}`},
      {id:'agent-passport',label:'Agent Passport Policy Set',status:security.passport.status,detail:`${security.passport.policies} policies evaluated`},
      {id:'commons-policy',label:'Commons Admission Policy',status:enterprise.commons?.attestation_required ? 'Enforced' : 'reported',detail:enterprise.commons?.attestation_required ? 'Remote contributions require attestation and local reproduction.' : 'Commons policy was not reported.'}
    ];
    const controlsRaw=firstArray(policy.controls,system.controls);
    const controls = (controlsRaw.length ? controlsRaw : derivedControls).slice(0,12).map((item,index) => ({
      id:String(item.id || item.key || `control-${index + 1}`),label:label(item,`Control ${index + 1}`),
      status:String(item.status || item.state || 'reported'),detail:String(item.detail || item.description || item.scope || '')
    }));
    const derivedCanaries = [
      {id:'memory-hull',label:'Memory Hull',status:security.hull.status,detail:`${security.hull.verified} verified sidecars`},
      {id:'residue-seal',label:'Residue Seal',status:security.seal.status,detail:security.seal.exists ? 'Purpose-specific signing key available' : 'Signing key unavailable'},
      {id:'agent-passport',label:'Agent Passport',status:security.passport.status,detail:`${security.passport.policies} policy rules evaluated`}
    ];
    const canariesRaw = firstArray(system.canaries,snapshot.canaries,integrity.canaries);
    const canaries = (canariesRaw.length ? canariesRaw : derivedCanaries).slice(0,8).map((item,index)=>({
      id:String(item.id || item.key || `canary-${index}`),
      label:label(item,`Canary ${index+1}`),
      status:String(item.status || item.health || item.state || 'Healthy'),
      detail:String(item.detail || item.description || item.scope || 'Monitoring governed subsystem')
    }));
    const passportRows=firstArray(securityPayload.agent_passport?.sample_passports);
    const permissionsRaw = firstArray(system.permissions,policy.permissions,snapshot.permissions,passportRows);
    const permissions = permissionsRaw.slice(0,10).map((item,index)=>({
      role:String(item.role || item.subject || item.agent || item.component || item.name || `Principal ${index+1}`),
      access:String(item.access || item.permission || item.level || (item.spiffe_id ? 'Policy Bound' : 'Read')),
      scope:String(item.scope || item.resource || item.identity_boundary || item.boundary || 'Mission'),
      status:String(item.status || item.verification || 'Verified')
    }));
    const derivedAttestations = [
      {id:'memory-hull',label:'Memory Hull Verification',status:security.hull.failed ? 'Invalid' : security.hull.verified ? 'Valid' : 'Reported',expires:'live'},
      {id:'residue-seal',label:'Residue Seal Key',status:security.seal.exists ? 'Valid' : 'Missing',expires:'live'},
      {id:'agent-passport-policy',label:'Agent Passport Policy Lint',status:security.passport.valid ? 'Valid' : 'Review',expires:'session'},
      {id:'workspace-identity',label:'Workspace Identity',status:enterprise.workspace_identity?.digest ? 'Valid' : 'Reported',expires:'workspace'}
    ];
    const attestationsRaw = firstArray(system.attestations,snapshot.attestations,securityPayload.attestations);
    const attestations = (attestationsRaw.length ? attestationsRaw : derivedAttestations).slice(0,8).map((item,index)=>({
      id:String(item.id || item.attestation_id || `att-${index+1}`),
      label:label(item,`Attestation ${index+1}`),
      status:String(item.status || item.validity || (item.valid === false ? 'Invalid':'Valid')),
      expires:String(item.expires || item.valid_until || item.expiry || 'session')
    }));
    return {
      ...current,
      loading:false,
      error:'',
      score,
      status: failed ? 'Degraded' : warnings ? 'Guarded' : total ? 'Secure' : 'Not reported',
      policy:String(policy.mode || policy.name || 'not reported'),
      systemsTotal:total,
      systemsHealthy:Math.min(total,healthy),
      warnings,
      failedChecks:failed,
      boundary:{
        // The platform is local-first by architecture. Absence of an optional
        // policy field must not be rendered as absence of the boundary itself.
        mode:String(policy.data_boundary || policy.local_first || 'Local-First'),
        network:String(system.network_policy || policy.network || 'Governed'),
        telemetry:String(policy.telemetry || 'Local operational only'),
        airGap:Boolean(policy.air_gap_capable ?? false)
      },
      integrity:{
        status:failed ? 'Failed' : warnings ? 'Verified with warnings':'Verified',
        agents:agentRows.length || Number(integrity.agents || 0),
        models:modelRows.length || Number(integrity.models || 0),
        evidence:evidenceRows.length || Number(integrity.evidence || 0),
        files:fileCount || Number(integrity.files || 0),
        lastChecked:String(integrity.checked_at || integrity.updated_at || 'not reported')
      },
      guardrails:{
        status:failed ? 'Review' : 'Enforced',
        decisions,
        approvals:approvalsRows.length,
        violations:Number(policy.violations ?? integrity.violations ?? 0),
        leastPrivilege:Boolean(policy.least_privilege ?? true)
      },
      provenance:{
        rootId:String(rootId).slice(0,22),
        algorithm:String(provenanceSource.algorithm || provenanceSource.hash_algorithm || 'not reported'),
        signedBy:String(provenanceSource.signed_by || provenanceSource.actor || 'not reported'),
        signedAt:String(provenanceSource.signed_at || provenanceSource.timestamp || 'not reported'),
        valid:Boolean(provenanceSource.valid ?? provenanceSource.verified ?? false)
      },
      canaries,controls,permissions,attestations,security,
      selectedControlId:current.selectedControlId || controls[0]?.id || '',
      updatedAt:Date.now()
    };
  }

  function normalizeMemory(memoryPayload={}, securityPayload={}, evidence={}, chronicle={}, query='') {
    const current = BeastStore.get().memory || {};
    const security = Object.keys(securityPayload || {}).length ? normalizeSecurity(securityPayload) : (current.security || {hull:{verified:0,failed:0,status:'Checking'},seal:{exists:false,mode:'unavailable',status:'Checking'},passport:{policies:0,valid:false,status:'Checking'}});
    const layersObject = memoryPayload.layers && !Array.isArray(memoryPayload.layers) ? memoryPayload.layers : null;
    const layersRaw = layersObject ? Object.entries(layersObject).map(([id,item])=>({id,...item})) : firstArray(memoryPayload.layers,memoryPayload.stack,memoryPayload.memory_layers);
    const recordsRaw = firstArray(memoryPayload.records,memoryPayload.items,memoryPayload.memories,memoryPayload.results);
    const truthRaw = firstArray(memoryPayload.truth_stores,memoryPayload.truthStores,memoryPayload.stores);
    const viewsRaw = firstArray(memoryPayload.retrieval_views,memoryPayload.views,memoryPayload.retrievers);
    const eventsRaw = firstArray(memoryPayload.events,memoryPayload.recent,memoryPayload.timeline,chronicle.entries,chronicle.records);
    const evidenceRows = firstArray(evidence.receipts,evidence.items,evidence.records);
    const layers = layersRaw.slice(0,8).map((item,index)=>({
      id:String(item.id || item.layer_id || `L${index}`),
      name:label(item,`Memory Layer ${index}`),
      scope:String(item.scope || item.description || item.purpose || 'Governed memory layer'),
      records:Number(item.records ?? item.count ?? item.items?.length ?? 0),
      freshness:clamp(item.freshness ?? item.health ?? 0),
      status:String(item.status || item.temperature || 'reported')
    }));
    const truthStores = truthRaw.slice(0,8).map((item,index)=>({
      id:String(item.id || item.key || `truth-${index}`),
      label:label(item,`Truth Store ${index+1}`),
      records:Number(item.records ?? item.count ?? 0),
      status:String(item.status || item.health || 'Healthy')
    }));
    const retrievalViews = viewsRaw.map(item=>label(item)).slice(0,10);
    const records = Number(memoryPayload.total ?? memoryPayload.count ?? recordsRaw.length ?? layers.reduce((sum,item)=>sum+item.records,0)) || layers.reduce((sum,item)=>sum+item.records,0);
    const evidenceItems = Number(evidence.total ?? evidence.count ?? evidenceRows.length ?? current.evidenceItems ?? 0);
    const recallHealth = clamp(memoryPayload.health ?? memoryPayload.recall_health ?? memoryPayload.score ?? 0);
    const freshness = clamp(memoryPayload.freshness ?? memoryPayload.freshness_score ?? (layers.length ? Math.round(layers.reduce((s,item)=>s+item.freshness,0)/layers.length):0));
    const compactionQueue = Number(memoryPayload.compaction_queue ?? memoryPayload.queue ?? memoryPayload.pending_compaction ?? 0);
    const skillCandidates = Number(memoryPayload.skill_candidates ?? memoryPayload.skills?.length ?? memoryPayload.candidates?.length ?? 0);
    const residueQuality = clamp(memoryPayload.residue_quality ?? evidence.validity ?? evidence.validity_score ?? 0);
    const events = eventsRaw.slice(0,10).map(item=>({time:timeLabel(item.time || item.timestamp || item.created_at),label:label(item,'Memory event')}));
    const queryText = String(query || current.query || '').trim();
    let recallRaw = firstArray(memoryPayload.recall_results,memoryPayload.matches,memoryPayload.results);
    if (!recallRaw.length && queryText) {
      const needle=queryText.toLowerCase();
      recallRaw=recordsRaw.filter(item=>JSON.stringify(item).toLowerCase().includes(needle));
    }
    const recallResults = recallRaw.slice(0,12).map((item,index)=>({
      id:String(item.id || item.memory_id || item.key || `mem-${index}`),
      label:label(item,`Recall Result ${index+1}`),
      layer:String(item.layer || item.layer_id || layers[index % Math.max(1,layers.length)]?.id || 'L1'),
      score:clamp(item.score ?? item.confidence ?? item.similarity ?? 88),
      source:String(item.source || item.path || item.origin || 'memory stack'),
      age:String(item.age || item.updated_at || item.created_at || 'live')
    }));
    return {
      ...current,
      loading:false,error:'',records,evidenceItems,recallHealth,freshness,compactionQueue,skillCandidates,residueQuality,
      layers,truthStores,retrievalViews,events,recallResults,query:queryText,
      selectedLayerId:current.selectedLayerId && layers.some(item=>item.id===current.selectedLayerId) ? current.selectedLayerId : layers[0]?.id || '',
      selectedRecordId:current.selectedRecordId && recallResults.some(item=>item.id===current.selectedRecordId) ? current.selectedRecordId : recallResults[0]?.id || '',
      security,updatedAt:Date.now()
    };
  }

  async function refreshTrust(options={}) {
    BeastStore.patch('trust',{loading:true,error:''});
    if (BeastDesktopBridge.demoMode) {
      const trust={...BeastStore.get().trust,...demoTrust,loading:false,error:'',updatedAt:Date.now()};
      BeastStore.patch('trust',trust);
      BeastStore.addLedger('Trust Posture refreshed from demo telemetry');
      return trust;
    }
    try {
      const root=rootQuery();
      const results=await Promise.allSettled([
        BeastDesktopBridge.fetchJson(`/edgek/ide/snapshot${root}`,options),
        BeastDesktopBridge.fetchJson(`/edgek/ide/system-snapshot${root}`,options),
        BeastDesktopBridge.fetchJson('/edgek/memory-security?verify=true',options),
        BeastDesktopBridge.fetchJson('/edgek/mcp/approvals?limit=20',options),
        BeastDesktopBridge.fetchJson('/edgek/chronicle?limit=20',options),
        BeastDesktopBridge.fetchJson('/edgek/control-plane/enterprise',options)
      ]);
      const trust=normalizeTrust(settled(results[0])||{},settled(results[1])||{},settled(results[2])||{},settled(results[3])||{},settled(results[4])||{},settled(results[5])||{});
      const nextTrust = trust;
      BeastStore.patch('trust',nextTrust);
      BeastStore.addLedger(`Trust Posture refreshed: ${nextTrust.score}% secure`);
      return nextTrust;
    } catch(error) {
      const trust={...BeastStore.get().trust,score:0,status:'Unavailable',loading:false,error:String(error.message||error),updatedAt:Date.now()};
      BeastStore.patch('trust',trust);
      BeastStore.addLedger(`Trust Posture unavailable: ${String(error.message || error)}`);
      return trust;
    }
  }

  async function refreshMemory(options={},query='') {
    BeastStore.patch('memory',{loading:true,error:''});
    if (BeastDesktopBridge.demoMode) {
      const memory={...BeastStore.get().memory,...demoMemory,query:String(query||''),loading:false,error:'',updatedAt:Date.now()};
      if(query) memory.recallResults=demoMemory.recallResults.filter(item=>`${item.label} ${item.source}`.toLowerCase().includes(String(query).toLowerCase()));
      BeastStore.patch('memory',memory);
      BeastStore.addLedger(query ? `Memory recall executed: ${query}` : 'Memory Observatory refreshed from demo telemetry');
      return memory;
    }
    try {
      const root=BeastStore.get().workspace.root;
      const memoryParams=new URLSearchParams();
      if(root) memoryParams.set('root_path',root);
      if(query) memoryParams.set('query',query);
      memoryParams.set('limit','25');
      const results=await Promise.allSettled([
        BeastDesktopBridge.fetchJson(`/edgek/memory/stack?${memoryParams}`,options),
        BeastDesktopBridge.fetchJson('/edgek/memory-security?verify=true',options),
        BeastDesktopBridge.fetchJson('/edgek/evidence-bus/query?limit=25',options),
        BeastDesktopBridge.fetchJson('/edgek/chronicle?limit=20',options)
      ]);
      let memory=normalizeMemory(settled(results[0])||{},settled(results[1])||{},settled(results[2])||{},settled(results[3])||{},query);
      if (!memory.layers.length) memory={...memory,records:0,error:'No live L0–L4 memory telemetry was returned.',updatedAt:Date.now()};
      BeastStore.patch('memory',memory);
      BeastStore.addLedger(query ? `Memory recall executed: ${query}` : `Memory Observatory refreshed: ${memory.records} records`);
      return memory;
    } catch(error) {
      const failure={...BeastStore.get().memory,records:0,layers:[],truthStores:[],retrievalViews:[],events:[],recallResults:[],query:String(query||''),loading:false,error:String(error.message||error),updatedAt:Date.now()};
      BeastStore.patch('memory',failure);
      BeastStore.addLedger(`Memory Observatory unavailable: ${String(error.message || error)}`);
      return failure;
    }
  }

  async function verifyIntegrity(options={}) {
    const trust=await refreshTrust(options);
    BeastStore.addLedger(`Integrity verification complete: ${trust.failedChecks} failures`);
    document.dispatchEvent(new CustomEvent('beast:trust-verified',{detail:trust}));
    return trust;
  }

  function selectControl(id) { BeastStore.patch('trust',{selectedControlId:id}); }
  function selectLayer(id) { BeastStore.patch('memory',{selectedLayerId:id}); }
  function selectRecord(id) { BeastStore.patch('memory',{selectedRecordId:id}); }

  async function recall(query,options={}) {
    const text=String(query||'').trim();
    BeastStore.patch('memory',{query:text});
    return await refreshMemory(options,text);
  }

  async function compact(options={}) {
    const state=BeastStore.get();
    if (BeastDesktopBridge.demoMode) {
      const queue=Math.max(0,(state.memory.compactionQueue||0)-1);
      BeastStore.patch('memory',{compactionQueue:queue,freshness:clamp((state.memory.freshness||0)+1),updatedAt:Date.now()});
      BeastStore.addLedger('Memory compaction simulated locally');
      return {ok:true,local:true,queue};
    }
    if (state.connection.status !== 'online') throw new Error('Gateway offline: memory compaction was not performed.');
    try {
      const result=await BeastDesktopBridge.fetchJson('/edgek/memory/compact',{...options,method:'POST',body:{root_path:state.workspace.root,limit:10}});
      await refreshMemory(options);
      BeastStore.addLedger('Memory compaction completed');
      return result;
    } catch(error) {
      BeastStore.addLedger(`Memory compaction unavailable: ${String(error.message||error)}`);
      throw error;
    }
  }

  async function promoteSkill(labelText,options={}) {
    const state=BeastStore.get();
    if (BeastDesktopBridge.demoMode) {
      BeastStore.patch('memory',{skillCandidates:Math.max(0,(state.memory.skillCandidates||0)-1),updatedAt:Date.now()});
      BeastStore.addLedger(`Skill candidate promoted locally: ${labelText||'selected candidate'}`);
      return {ok:true,local:true};
    }
    if (state.connection.status !== 'online') throw new Error('Gateway offline: skill promotion was not performed.');
    try {
      const candidates=await BeastDesktopBridge.fetchJson('/edgek/skills/promotion-candidates?limit=20',options);
      const rows=candidates?.promotion_candidates||candidates?.items||[];
      const selected=rows.find(row=>row.eligible!==false);
      if(!selected?.candidate_id) throw new Error('No eligible skill promotion candidate is available.');
      const result=await BeastDesktopBridge.fetchJson('/edgek/skills/promote',{...options,method:'POST',body:{root_path:state.workspace.root,candidate_id:selected.candidate_id,approved_by:'operator',require_eligible:true}});
      await refreshMemory(options);
      BeastStore.addLedger(`Skill candidate promoted: ${labelText||'selected candidate'}`);
      return result;
    } catch(error) {
      BeastStore.addLedger(`Skill promotion unavailable: ${String(error.message||error)}`);
      BeastStore.patch('memory',{error:`Skill promotion unavailable: ${String(error.message||error)}`,updatedAt:Date.now()});
      throw error;
    }
  }

  window.BeastTrustMemoryBridge={
    refreshTrust,refreshMemory,verifyIntegrity,selectControl,selectLayer,selectRecord,recall,compact,promoteSkill,
    normalizeTrust,normalizeMemory,normalizeSecurity
  };
})();
