(() => {
  const now = () => new Date().toLocaleTimeString([], { hour:'2-digit', minute:'2-digit', second:'2-digit' });
  const clamp = value => Math.max(0, Math.min(100, Number(value) || 0));
  const list = (...values) => values.find(Array.isArray) || [];
  const label = (value, fallback='Unknown') => typeof value === 'string' ? value : value?.label || value?.name || value?.title || value?.id || value?.path || fallback;
  const rootParams = extra => new URLSearchParams({ ...(BeastDesktopBridge.workspaceRoot ? { root_path:BeastDesktopBridge.workspaceRoot } : {}), ...extra });

  const DEMO_NODES = [
    {id:'main.py',label:'main.py',type:'entry',path:'src/main.py',language:'Python',description:'Application entry point and mission bootstrap.',coverage:96,freshness:98,x:50,y:8},
    {id:'router.py',label:'router.py',type:'parser',path:'src/core/router.py',language:'Python',description:'Selects local-first inference routes.',coverage:94,freshness:96,x:29,y:24},
    {id:'evidence_parser.py',label:'evidence_parser.py',type:'parser',path:'src/core/evidence_parser.py',language:'Python',description:'Parses raw evidence into verified records.',coverage:92,freshness:97,x:50,y:27},
    {id:'profiler.py',label:'profiler.py',type:'parser',path:'src/core/profiler.py',language:'Python',description:'Profiles runtime paths and hotspots.',coverage:86,freshness:91,x:71,y:24},
    {id:'schema_validator.py',label:'schema_validator.py',type:'entry',path:'src/validation/schema_validator.py',language:'Python',description:'Validates evidence schemas and contracts.',coverage:97,freshness:89,x:18,y:44},
    {id:'anomaly_detector.py',label:'anomaly_detector.py',type:'store',path:'src/analysis/anomaly_detector.py',language:'Python',description:'Detects inconsistent evidence patterns.',coverage:84,freshness:83,x:39,y:44},
    {id:'evidence_index.db',label:'evidence_index.db',type:'store',path:'data/evidence_index.db',language:'SQLite',description:'Durable evidence and trace index.',coverage:100,freshness:99,x:60,y:44},
    {id:'policy_guard.py',label:'policy_guard.py',type:'entry',path:'src/governance/policy_guard.py',language:'Python',description:'Enforces local-first and approval policies.',coverage:95,freshness:95,x:82,y:44},
    {id:'planner-agent',label:'Planner Agent',type:'agent',path:'agent://planner',language:'Agent',description:'Plans governed mission execution.',coverage:90,freshness:100,x:29,y:64},
    {id:'verifier-agent',label:'Verifier Agent',type:'agent',path:'agent://verifier',language:'Agent',description:'Validates evidence and final receipts.',coverage:93,freshness:100,x:50,y:64},
    {id:'graph-agent',label:'Graph Analyst',type:'agent',path:'agent://graph',language:'Agent',description:'Maintains dependency topology.',coverage:91,freshness:100,x:71,y:64},
    {id:'README.md',label:'README.md',type:'external',path:'README.md',language:'Markdown',description:'Repository overview and operator guide.',coverage:88,freshness:72,x:18,y:83},
    {id:'beast.yaml',label:'beast.yaml',type:'external',path:'config/beast.yaml',language:'YAML',description:'Runtime and governance configuration.',coverage:91,freshness:87,x:39,y:83},
    {id:'tests',label:'tests/',type:'entry',path:'tests/',language:'Python',description:'Verification and regression suite.',coverage:86,freshness:78,x:61,y:83},
    {id:'pydantic',label:'pydantic',type:'external',path:'external://pydantic',language:'Dependency',description:'External schema and validation dependency.',coverage:100,freshness:76,x:82,y:83}
  ];

  const DEMO_EDGES = [
    ['main.py','router.py','calls'],['main.py','evidence_parser.py','calls'],['main.py','profiler.py','calls'],
    ['router.py','schema_validator.py','imports'],['router.py','anomaly_detector.py','routes'],['evidence_parser.py','evidence_index.db','writes'],
    ['profiler.py','policy_guard.py','reports'],['schema_validator.py','planner-agent','validates'],['anomaly_detector.py','verifier-agent','alerts'],
    ['evidence_index.db','verifier-agent','feeds'],['policy_guard.py','graph-agent','governs'],['planner-agent','verifier-agent','handoff'],
    ['verifier-agent','graph-agent','handoff'],['planner-agent','README.md','reads'],['planner-agent','beast.yaml','reads'],
    ['verifier-agent','tests','runs'],['graph-agent','pydantic','depends'],['evidence_parser.py','pydantic','imports'],['tests','evidence_parser.py','covers']
  ].map(([source,target,type],index)=>({id:`e${index}`,source,target,type,tone:type==='handoff'?'violet':type==='writes'?'amber':type==='governs'?'green':'cyan'}));

  function stablePositions(nodes) {
    const rows = nodes.length || 1;
    const columns = Math.max(3, Math.ceil(Math.sqrt(rows * 1.8)));
    return nodes.map((node,index) => {
      if (Number.isFinite(Number(node.x)) && Number.isFinite(Number(node.y))) return node;
      const row = Math.floor(index / columns);
      const col = index % columns;
      const rowCount = Math.ceil(rows / columns);
      return { ...node, x:12 + col * (76 / Math.max(1, columns - 1)), y:10 + row * (78 / Math.max(1, rowCount - 1)) };
    });
  }

  function addOperationalTopology(nodes, edges) {
    // Code analysis alone cannot show the governed runtime that acts on that
    // code. Keep these nodes explicitly derived and linked to the live store,
    // so Map is a mission topology rather than a file-only constellation.
    const present = new Set(nodes.map(node => node.type));
    const firstCore = nodes.find(node => node.type === 'entry')?.id || nodes[0]?.id;
    const additions = [];
    const add = (node, target, relation, tone) => {
      if (present.has(node.type)) return;
      additions.push(node); present.add(node.type);
      if (target) edges.push({id:`operational:${node.id}`,source:node.id,target,type:relation,tone});
    };
    const state=BeastStore.get();
    add({id:'beast-core',label:'BEAST Core',type:'entry',path:'beast://core',language:'Runtime',description:'Derived live control-plane node for the selected workspace and governed task pipeline.',coverage:100,freshness:100,x:50,y:8},firstCore,'governs','green');
    add({id:'beast-agents',label:'Agent Swarm',type:'agent',path:'beast://agents',language:'Agent',description:`Derived from the live agent plane (${(state.agents?.items||[]).length} visible agent record(s)).`,coverage:90,freshness:100,x:18,y:62},firstCore,'handoff','violet');
    add({id:'beast-external',label:'Governed Gateway',type:'external',path:state.connection?.gatewayUrl||'beast://gateway',language:'HTTP',description:'Active provider, remote-attestation, and capability boundary for this session.',coverage:100,freshness:95,x:82,y:62},firstCore,'routes','cyan');
    add({id:'beast-risk',label:'Trust And Risk Gates',type:'risk',path:'beast://trust',language:'Policy',description:'Trust, evidence, and approval controls that must be satisfied before governed mutations.',coverage:100,freshness:100,x:50,y:88},firstCore,'guards','red');
    return {nodes:[...nodes,...additions],edges};
  }

  function normalizeGraph(payload={}) {
    const rawNodes = list(payload.nodes,payload.items,payload.vertices,payload.graph?.nodes);
    const rawEdges = list(payload.edges,payload.links,payload.relationships,payload.graph?.edges);
    let nodes = rawNodes.map((node,index) => {
      const id = String(node.id || node.node_id || node.path || node.file || node.name || `node-${index}`);
      const path = node.path || node.file || id;
      const rawType = String(node.type || node.kind || node.category || '').toLowerCase();
      const type = /agent/.test(rawType) ? 'agent' : /db|store|database/.test(rawType) ? 'store' : /external|dependency|package/.test(rawType) ? 'external' : /entry|test|validator|guard/.test(rawType) ? 'entry' : /risk|orphan|stale/.test(rawType) ? 'risk' : 'parser';
      return {
        id,label:node.label || node.name || path.split('/').pop() || id,type,path,
        language:node.language || node.lang || node.runtime || (path.split('.').pop() || 'Node').toUpperCase(),
        description:node.description || node.summary || node.doc || `${type} node in the active mission topology.`,
        coverage:clamp(node.coverage ?? node.test_coverage ?? 82),freshness:clamp(node.freshness ?? node.freshness_score ?? 86),
        x:Number(node.x ?? node.position?.x),y:Number(node.y ?? node.position?.y),meta:node
      };
    });
    if (!nodes.length) {
      // A graph index may still be building. Project the live workspace index
      // into a clearly derived topology instead of rendering an empty canvas.
      const liveFiles = list(payload.workspace_files?.files, payload.files, payload.workspace?.files, BeastStore.get().workspace?.files);
      nodes = liveFiles.filter(item => item && (item.path || item.name || typeof item === 'string')).slice(0,24).map((item,index) => {
        const path=String(typeof item==='string'?item:(item.path||item.name||`file-${index}`));
        const name=path.split('/').pop()||path;
        const type=/test|spec/i.test(path)?'risk':/\.md$|readme/i.test(path)?'external':/\.json$|\.ya?ml$|config/i.test(path)?'store':index===0?'entry':'parser';
        return {id:`workspace:${path}`,label:name,type,path,language:(path.split('.').pop()||'file').toUpperCase(),description:'Derived from the live workspace index while graph analysis is pending.',coverage:0,freshness:100};
      });
    }
    if (!nodes.length && BeastDesktopBridge.demoMode) nodes = DEMO_NODES.map(node=>({...node}));
    nodes = stablePositions(nodes.slice(0,28));
    const known = new Set(nodes.map(node=>node.id));
    let edges = rawEdges.map((edge,index) => {
      const source = String(edge.source || edge.from || edge.source_id || edge.parent || '');
      const target = String(edge.target || edge.to || edge.target_id || edge.child || '');
      return { id:String(edge.id || `edge-${index}`),source,target,type:edge.type || edge.kind || edge.relation || 'link',tone:edge.tone || 'green' };
    }).filter(edge=>known.has(edge.source)&&known.has(edge.target));
    if (!edges.length && BeastDesktopBridge.demoMode && nodes.length >= DEMO_NODES.length) edges = DEMO_EDGES.filter(edge=>known.has(edge.source)&&known.has(edge.target));
    if (!edges.length && nodes.length > 1 && !BeastDesktopBridge.demoMode) edges = nodes.slice(1).map((node,index)=>({id:`derived-${index}`,source:nodes[Math.max(0,index-1)].id,target:node.id,type:'workspace adjacency',tone:'cyan'}));
    if (!edges.length && BeastDesktopBridge.demoMode) edges = nodes.slice(1).map((node,index)=>({id:`auto-${index}`,source:nodes[Math.max(0,index-1)]?.id || nodes[0].id,target:node.id,type:'dependency',tone:'green'}));
    ({nodes,edges}=addOperationalTopology(nodes,edges));
    nodes=stablePositions(nodes);
    const orphaned = Number(payload.orphaned ?? payload.orphan_count ?? nodes.filter(node=>!edges.some(edge=>edge.source===node.id||edge.target===node.id)).length);
    const coverage = clamp(payload.coverage ?? payload.metrics?.coverage ?? Math.round(nodes.reduce((sum,node)=>sum+node.coverage,0)/nodes.length));
    const freshness = clamp(payload.freshness ?? payload.metrics?.freshness ?? Math.round(nodes.reduce((sum,node)=>sum+node.freshness,0)/nodes.length));
    const consistency = clamp(payload.consistency ?? payload.metrics?.consistency ?? Math.max(70,100-orphaned*4));
    const health = clamp(payload.health ?? payload.score ?? Math.round((coverage+freshness+consistency)/3));
    return {nodes,edges,orphaned,coverage,freshness,consistency,health};
  }

  async function refreshMap(options={}) {
    BeastStore.patch('map',{loading:true,error:''});
    try {
      let payload={};
      if (!BeastDesktopBridge.demoMode && BeastStore.get().connection.status==='online') {
        const params=rootParams({node_limit:'80',edge_limit:'160'});
        try { payload=await BeastDesktopBridge.fetchJson(`/edgek/workspace/graph?${params}`,options); }
        catch (_) {
          const snap=await BeastDesktopBridge.fetchJson(`/edgek/ide/snapshot?${rootParams({objective:'mission-map'})}`,options);
          payload=snap?.workspace_graph || snap?.code_cortex || snap?.mission_lattice || {};
        }
      }
      const normalized=normalizeGraph(payload);
      BeastStore.transaction(next=>{
        next.map={...next.map,...normalized,loading:false,error:'',updatedAt:Date.now(),selectedId:next.map.selectedId&&normalized.nodes.some(node=>node.id===next.map.selectedId)?next.map.selectedId:normalized.nodes[0]?.id||''};
      });
      BeastStore.addLedger(`Mission Map synchronized: ${normalized.nodes.length} nodes · ${normalized.edges.length} links`);
      return normalized;
    } catch(error) {
      const normalized=normalizeGraph({});
      BeastStore.transaction(next=>{next.map={...next.map,...normalized,loading:false,error:String(error.message||error),updatedAt:Date.now(),selectedId:normalized.nodes[0]?.id||''};});
      BeastStore.addLedger(`Mission Map unavailable: ${String(error.message||error)}`);
      return normalized;
    }
  }

  function selectMapNode(id){BeastStore.patch('map',{selectedId:id});}
  function setMapFilter(filter){BeastStore.patch('map',{filter});}
  function setMapQuery(query){BeastStore.patch('map',{query:String(query||'')});}
  function setMapZoom(zoom){BeastStore.patch('map',{zoom:Math.max(.65,Math.min(1.7,Number(zoom)||1))});}

  const DEMO_CANDIDATES = [
    {id:'local-evidence-parser',label:'Local Evidence Parser',domain:'Evidence · Code Graph',value:'Highest Value',ready:94,description:'Verified parser architecture, trace links, tests, and governed routing residue.',artifacts:32,checks:127,traces:1842},
    {id:'profiler-agent-integration',label:'Profiler Agent Integration',domain:'Agent · Orchestration',value:'High Value',ready:91,description:'Reusable agent and profiler coordination pattern with verified handoff receipts.',artifacts:18,checks:84,traces:760},
    {id:'decision-trace-analyzer',label:'Decision Trace Analyzer',domain:'Review · Trace',value:'High Value',ready:88,description:'Decision trace analysis and contradiction-resolution pattern.',artifacts:21,checks:73,traces:912},
    {id:'filesystem-summarizer',label:'File System Summarizer',domain:'Tool · Utility',value:'Medium',ready:76,description:'Local repository summarization residue with bounded context use.',artifacts:12,checks:48,traces:305},
    {id:'memory-integrity-verifier',label:'Memory Integrity Verifier',domain:'Trust · Verification',value:'Medium',ready:72,description:'Memory Hull, Residue Seal, and Agent Passport verification sequence.',artifacts:15,checks:62,traces:433}
  ];

  function normalizeCandidates(payload={}) {
    const rows=list(payload.candidates,payload.credits,payload.items,payload.reusable,payload.summary?.candidates);
    if (!rows.length) {
      if (BeastDesktopBridge.demoMode) return DEMO_CANDIDATES.map(item=>({...item}));
      const storage=payload.storage||{};
      const capabilities=storage.crystallized_by_type||{};
      const count=Number(storage.active_credits||0)+Object.values(capabilities).reduce((sum,value)=>sum+Number(value||0),0);
      return count?[{
        id:'durable-reuse-inventory',label:'Durable Reuse Inventory',domain:'Crystal Reuse · Local Store',value:`${count} retained capability record(s)`,ready:100,
        description:`Observed ${Number(storage.total_reuse_count||0)} reuse event(s), ${Number(storage.total_avoided_tokens||0)} avoided token(s), and ${Number(storage.artifact_blob_count||0)} durable artifact blob(s). This is existing inventory, not a new promotion request.`,
        artifacts:Number(storage.artifact_blob_count||0),checks:0,traces:Number(storage.total_reuse_count||0),meta:{inventory:true,storage}
      }]:[];
    }
    return rows.slice(0,10).map((item,index)=>({
      id:String(item.id||item.credit_id||item.name||item.title||`candidate-${index+1}`),label:label(item,`Candidate ${index+1}`),
      domain:item.domain||item.kind||item.category||'Verified Residue',value:item.value||item.priority||item.tier||'Candidate',
      ready:clamp(item.readiness??item.score??item.confidence??80),description:item.description||item.summary||item.reason||'Verified inference residue eligible for governed crystallization.',
      artifacts:Number(item.artifacts??item.artifact_count??12),checks:Number(item.checks??item.check_count??48),traces:Number(item.traces??item.trace_count??240),meta:item
    }));
  }

  function deriveGates(state) {
    const evidence=state.evidence||{},review=state.review||{},trust=state.trust||{},memory=state.memory||{};
    return [
      {id:'integrity',label:'Evidence Integrity',detail:'All source evidence verified',status:(evidence.validity||0)>=80?'Passed':'Pending',icon:'evidence'},
      {id:'consistency',label:'Graph Consistency',detail:'No critical topology contradictions',status:(state.map.consistency||0)>=80?'Passed':'Pending',icon:'map'},
      {id:'trace',label:'Trace Completeness',detail:'Sufficient coverage achieved',status:(state.map.coverage||0)>=80?'Passed':'Pending',icon:'network'},
      {id:'agents',label:'Agent Validation',detail:'Agent outputs remain within trust boundary',status:(trust.score||0)>=80?'Passed':'Pending',icon:'agents'},
      {id:'determinism',label:'Determinism Check',detail:'Reproducible mission receipts',status:(review.tests?.passed||0)>0 || (state.crystal?.chain?.valid && state.crystal?.lattice?.valid)?'Passed':'Pending',icon:'review'},
      {id:'residue',label:'Residue Quality',detail:'Reusable verified memory residue',status:(memory.residueQuality||0)>=70?'Passed':'Pending',icon:'memory'}
    ];
  }

  function normalizeChain(chain={}) {
    const head=chain.head_hash||chain.hash||chain.head||'sha256:unresolved';
    return {blocks:Number(chain.block_count??chain.blocks?.length??chain.count??0),valid:chain.valid!==false&&Boolean(chain.valid??chain.block_count??chain.blocks),headHash:String(head),authority:chain.authority||chain.signed_by||'BEAST',attestedAt:chain.attested_at||chain.updated_at||''};
  }
  function normalizeLattice(lattice={}) {
    const verify=lattice.verification||lattice;
    return {checkpoints:Number(verify.checkpoint_count??lattice.checkpoints?.length??lattice.count??0),valid:verify.valid!==false&&Boolean(verify.valid??verify.checkpoint_count??lattice.checkpoints),headHash:String(verify.head_hash||lattice.head_hash||'sha256:unresolved'),claim:verify.claim_boundary||lattice.claim_boundary||'append-only',checkpointAt:verify.checked_at||lattice.updated_at||''};
  }

  async function refreshCrystal(options={}) {
    BeastStore.patch('crystal',{loading:true,error:''});
    try {
      let reuse={},chain={},lattice={};
      if (!BeastDesktopBridge.demoMode && BeastStore.get().connection.status==='online') {
        const results=await Promise.allSettled([
          BeastDesktopBridge.fetchJson('/edgek/crystal-reuse',options),
          BeastDesktopBridge.fetchJson('/edgek/crystal-chain?include_blocks=true&limit=12',options),
          BeastDesktopBridge.fetchJson('/edgek/crystal-lattice',options)
        ]);
        reuse=results[0].status==='fulfilled'?results[0].value:{};
        chain=results[1].status==='fulfilled'?results[1].value:{};
        lattice=results[2].status==='fulfilled'?results[2].value:{};
      }
      const current=BeastStore.get();
      let candidates=normalizeCandidates(reuse);
      const evidenceCount=Number(current.memory?.evidenceItems||current.memory?.records||0);
      const gateCount=(current.grandClosure?.gates && typeof current.grandClosure.gates==='object') ? Object.keys(current.grandClosure.gates).length : 0;
      if (!candidates.length && evidenceCount > 0) {
        candidates=[{
          id:'repository-evidence-residue',
          label:'Repository Evidence Residue',
          domain:'Evidence · Repository Receipts',
          value:`${evidenceCount} trace-linked record(s)`,
          ready:clamp(current.memory?.residueQuality || (gateCount ? Math.round(evidenceCount / Math.max(1, gateCount) * 100) : 0)),
          description:'Evidence is available for inspection, but no live crystallization candidate has been admitted. Promotion remains gated until the gateway and verification contracts are live.',
          artifacts:evidenceCount,
          checks:gateCount,
          traces:Number(current.memory?.records||0),
          meta:{evidence_only:true}
        }];
      }
      const chainState=normalizeChain(Object.keys(chain).length ? chain : current.crystal.chain);
      const latticeState=normalizeLattice(Object.keys(lattice).length ? lattice : current.crystal.lattice);
      const gates=deriveGates(current);
      const passed=gates.filter(g=>g.status==='Passed').length;
      const readiness=clamp(reuse.readiness??reuse.summary?.readiness??Math.round(candidates[0]?.ready*.55+(passed/gates.length)*45));
      const artifacts=list(chain.blocks,chain.artifacts,reuse.artifacts).slice(0,8).map((item,index)=>({id:String(item.id||item.hash||`CRYS-${index+1}`),label:label(item,`Crystal ${index+1}`),size:item.size||item.bytes||'verified',status:item.status||'Committed',createdAt:item.created_at||item.time||'live'}));
      const fallbackArtifacts=artifacts.length?artifacts:(BeastDesktopBridge.demoMode ? [
        {id:'CRYS-PHASE5-TRUST',label:'Trust Posture Residue',size:'1.2 MB',status:'Committed',createdAt:'Phase 5'},
        {id:'CRYS-PHASE5-MEMORY',label:'Memory Observatory Residue',size:'2.1 MB',status:'Committed',createdAt:'Phase 5'},
        {id:'CRYS-PHASE4-EVIDENCE',label:'Evidence Forge Receipt',size:'812 KB',status:'Committed',createdAt:'Phase 4'}
      ] : []);
      BeastStore.transaction(next=>{
        next.crystal={...next.crystal,loading:false,error:'',readiness,immutable:chainState.valid&&latticeState.valid,candidates,gates,chain:chainState,lattice:latticeState,artifacts:fallbackArtifacts,promotion:{available:BeastDesktopBridge.demoMode,reason:BeastDesktopBridge.demoMode?'Demo-only promotion simulation':'Promotion is not exposed by the live Chamber. Use the Commons Space promotion flow with a verified execution receipt.'},events:[
          {time:now(),label:`Candidate lattice loaded: ${candidates.length}`},{time:now(),label:`Quality gates: ${passed}/${gates.length}`},{time:now(),label:`Crystal chain blocks: ${chainState.blocks}`},{time:now(),label:`Lattice checkpoints: ${latticeState.checkpoints}`}
        ],selectedId:next.crystal.selectedId&&candidates.some(c=>c.id===next.crystal.selectedId)?next.crystal.selectedId:candidates[0]?.id||'',updatedAt:Date.now()};
      });
      BeastStore.addLedger(`Crystallization Chamber synchronized: ${readiness}% ready`);
      return BeastStore.get().crystal;
    } catch(error) {
      BeastStore.patch('crystal',{loading:false,error:String(error.message||error)});
      BeastStore.addLedger('Crystal bridge degraded; retained last verified chamber state');
      return BeastStore.get().crystal;
    }
  }

  function selectCandidate(id){BeastStore.patch('crystal',{selectedId:id});}

  async function verifyCandidate() {
    if (!BeastDesktopBridge.demoMode && BeastStore.get().connection.status!=='online') throw new Error('Gateway offline: Crystal verification was not performed.');
    BeastStore.patch('crystal',{verifying:true,error:''});
    if (BeastDesktopBridge.demoMode) await new Promise(resolve=>setTimeout(resolve,450));
    const acceptance=BeastDesktopBridge.demoMode ? {accepted_count:0,capability_count:0,receipt_hash:'demo'} : await BeastDesktopBridge.fetchJson('/edgek/crystal-reuse/acceptance?probe=false');
    const state=BeastStore.get();
    // Acceptance attests local capability contracts only.  It is not evidence
    // that an arbitrary candidate passed its own gates, so never promote a
    // pending gate just because the gateway answered.
    const gates=deriveGates(state);
    const passed=gates.filter(g=>g.status==='Passed').length;
    const accepted=Number(acceptance?.accepted_count||0), total=Number(acceptance?.capability_count||0);
    BeastStore.patch('crystal',{verifying:false,gates,verification:{accepted,total,receiptHash:acceptance?.receipt_hash||'',checkedAt:acceptance?.created_at||now()},events:[{time:now(),label:`Local reuse acceptance: ${accepted}/${total||'?'} · ${acceptance?.receipt_hash||'no receipt hash'}`},...state.crystal.events].slice(0,12)});
    BeastStore.addLedger(`Crystal local capability acceptance observed: ${accepted}/${total||'?'}`);
    return acceptance;
  }

  async function attestChain(options={}) {
    if (!BeastDesktopBridge.demoMode && BeastStore.get().connection.status!=='online') throw new Error('Gateway offline: Crystal Chain attestation was not performed.');
    if (BeastDesktopBridge.demoMode) {
      const result={status:'simulated'};
      BeastStore.transaction(next=>{next.crystal.chain={...next.crystal.chain,valid:true,blocks:Math.max(1,next.crystal.chain.blocks),attestedAt:now()};next.crystal.events=[{time:now(),label:'Demo crystal chain attested'},...next.crystal.events].slice(0,12);});
      return result;
    }
    const result=await BeastDesktopBridge.fetchJson('/edgek/crystal-chain/attest',{...options,method:'POST',body:{root_path:BeastDesktopBridge.workspaceRoot}});
    if (!result?.attestation || !result?.record) throw new Error('Crystal Chain attestation returned no witness receipt.');
    const chain=await BeastDesktopBridge.fetchJson('/edgek/crystal-chain',options);
    const chainState=normalizeChain(chain);
    BeastStore.transaction(next=>{next.crystal.chain=chainState;next.crystal.immutable=chainState.valid&&next.crystal.lattice.valid;next.crystal.events=[{time:now(),label:`Crystal chain witnessed: ${chainState.headHash}`},...next.crystal.events].slice(0,12);});
    BeastStore.addLedger('Crystal chain witness receipt recorded');
    return result;
  }

  async function checkpointLattice(options={}) {
    if (!BeastDesktopBridge.demoMode && BeastStore.get().connection.status!=='online') throw new Error('Gateway offline: Crystal lattice checkpoint was not performed.');
    if (BeastDesktopBridge.demoMode) {
      const result={status:'simulated'};
      BeastStore.transaction(next=>{next.crystal.lattice={...next.crystal.lattice,valid:true,checkpoints:next.crystal.lattice.checkpoints+1,checkpointAt:now()};next.crystal.events=[{time:now(),label:'Demo crystal lattice checkpoint sealed'},...next.crystal.events].slice(0,12);});
      return result;
    }
    const result=await BeastDesktopBridge.fetchJson('/edgek/crystal-lattice/checkpoint',{...options,method:'POST',body:{root_path:BeastDesktopBridge.workspaceRoot}});
    if (!result?.checkpoint || !result?.state) throw new Error('Crystal lattice checkpoint returned no ledger receipt.');
    const [chain,lattice]=await Promise.all([BeastDesktopBridge.fetchJson('/edgek/crystal-chain',options),BeastDesktopBridge.fetchJson('/edgek/crystal-lattice',options)]);
    const chainState=normalizeChain(chain), latticeState=normalizeLattice(lattice);
    BeastStore.transaction(next=>{next.crystal.chain=chainState;next.crystal.lattice=latticeState;next.crystal.immutable=chainState.valid&&latticeState.valid;next.crystal.events=[{time:now(),label:`Crystal lattice checkpoint: ${latticeState.headHash}`},...next.crystal.events].slice(0,12);});
    BeastStore.addLedger('Crystal lattice checkpoint receipt recorded');
    return result;
  }

  async function commitCrystal(options={}) {
    const state=BeastStore.get();
    const candidate=state.crystal.candidates.find(c=>c.id===state.crystal.selectedId)||state.crystal.candidates[0];
    if (!candidate) throw new Error('No crystal candidate selected.');
    if (!BeastDesktopBridge.demoMode) throw new Error('Live Chamber promotion is intentionally unavailable: select a verified Commons Space and promote it through its evidence-backed Commons workflow. The Chamber remains read/verify/attest/checkpoint only.');
    BeastStore.patch('crystal',{committing:true,error:''});
    try {
      await verifyCandidate();
      await attestChain(options);
      await checkpointLattice(options);
      const artifact={id:`CRYS-${Date.now().toString(36).toUpperCase()}`,label:candidate.label,size:`${candidate.artifacts} artifacts`,status:'Committed',createdAt:now()};
      BeastStore.transaction(next=>{
        next.crystal.committing=false;next.crystal.immutable=true;next.crystal.readiness=100;
        next.crystal.artifacts=[artifact,...next.crystal.artifacts].slice(0,10);
        next.crystal.events=[{time:now(),label:`Crystal committed: ${candidate.label}`},...next.crystal.events].slice(0,12);
      });
      BeastStore.addLedger(`Immutable crystal committed: ${candidate.label}`);
      return artifact;
    } catch(error){BeastStore.patch('crystal',{committing:false,error:String(error.message||error)});throw error;}
  }

  window.BeastMapCrystalBridge={refreshMap,selectMapNode,setMapFilter,setMapQuery,setMapZoom,refreshCrystal,selectCandidate,verifyCandidate,attestChain,checkpointLattice,commitCrystal};
})();
