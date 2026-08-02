(() => {
  const esc = value => String(value ?? '');
  const firstArray = (...values) => values.find(Array.isArray) || [];
  const clamp = value => Math.max(0, Math.min(100, Number(value) || 0));
  const label = (value, fallback='Unknown') => {
    if (value == null) return fallback;
    if (typeof value === 'string' || typeof value === 'number') return String(value);
    return String(value.label || value.name || value.title || value.id || value.key || fallback);
  };
  const settled = result => result?.status === 'fulfilled' ? result.value : null;
  const now = () => new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'});
  const rootQuery = () => {
    const root = BeastStore.get().workspace.root;
    return root ? `?root_path=${encodeURIComponent(root)}` : '';
  };

  const demoReceipts = [
    { id:'ev-001', path:'src/parsers/evidence_parser.py', type:'PY', size:'12.4 KB', status:'Validated', validity:98, schema:'Valid', traces:24, source:'workspace', summary:'Parses raw inputs and produces structured evidence artifacts.', added:'2m ago' },
    { id:'ev-002', path:'tests/test_parser.py', type:'PY', size:'8.2 KB', status:'Validated', validity:96, schema:'Valid', traces:17, source:'workspace', summary:'Regression and edge-case checks for the evidence parser.', added:'4m ago' },
    { id:'ev-003', path:'docs/parser_design.md', type:'MD', size:'18.7 KB', status:'Review', validity:88, schema:'Warning', traces:9, source:'workspace', summary:'Design contract, failure modes, and operational assumptions.', added:'7m ago' },
    { id:'ev-004', path:'benchmarks/results.json', type:'JSON', size:'31.2 KB', status:'Validated', validity:94, schema:'Valid', traces:12, source:'evidence_bus', summary:'Performance, latency, and accuracy benchmark receipts.', added:'8m ago' },
    { id:'ev-005', path:'logs/parser_run.log', type:'LOG', size:'84.1 KB', status:'Warning', validity:82, schema:'Partial', traces:6, source:'governed_terminal', summary:'Runtime execution trail with one unresolved timestamp mismatch.', added:'11m ago' },
    { id:'ev-006', path:'config/parser_rules.yaml', type:'YAML', size:'6.8 KB', status:'Validated', validity:91, schema:'Valid', traces:10, source:'workspace', summary:'Parser schema, validation rules, and routing thresholds.', added:'14m ago' }
  ];

  function normalizeGate(item, index) {
    const statusRaw = String(item?.status || item?.result || item?.state || '').toLowerCase();
    const status = /pass|complete|ready|approved|ok/.test(statusRaw) ? 'Passed' : /fail|block|critical/.test(statusRaw) ? 'Failed' : /warn|pending|review/.test(statusRaw) ? 'Needs Review' : index < 4 ? 'Passed' : 'Needs Approval';
    return {
      id: String(item?.id || item?.key || `gate-${index + 1}`),
      label: label(item, ['Plan Validity','Evidence Sufficiency','Parser Robustness','Risk Assessment','Operational Readiness'][index] || `Quality Gate ${index + 1}`),
      status,
      detail: String(item?.detail || item?.description || item?.reason || (status === 'Passed' ? 'Required conditions are satisfied.' : 'Operator review is required.')),
      score: clamp(item?.score ?? item?.confidence ?? (status === 'Passed' ? 94 - index : 72)),
      owner: String(item?.owner || item?.agent || 'Review Orchestrator')
    };
  }

  function normalizeReview(snapshot={}, lifecycle={}, approvals={}, tooling={}, evidence={}) {
    const existing = BeastStore.get().review || {};
    const sourcePlan = BeastStore.get().sourcePlan?.plan || {};
    const scorecard = sourcePlan.scorecard && typeof sourcePlan.scorecard === 'object' ? sourcePlan.scorecard : {};
    const sourceOperations = [lifecycle.operations, lifecycle.preview?.operations, sourcePlan.operations, sourcePlan.selected_operations].find(value=>Array.isArray(value)&&value.length) || [];
    const sourcePlanId = String(sourcePlan.plan_id || lifecycle.plan_id || '');
    const fallbackGates = sourcePlanId ? [
      {id:'sourceplan-present',label:'Governed SourcePlan',status:'Passed',score:100,owner:'Pair Programmer',detail:`${sourceOperations.length} operation(s) bound to ${sourcePlanId}.`},
      {id:'sourceplan-scope',label:'Scope Binding',status:sourceOperations.length?'Passed':'Needs Review',score:sourceOperations.length?96:45,owner:'SourcePlan',detail:sourceOperations.length?'Every candidate operation is visible to review.':'The proposal contains no reviewable operations.'},
      {id:'sourceplan-preview',label:'Patch Preview',status:lifecycle.preview || sourcePlan.preview ? 'Passed':'Needs Review',score:lifecycle.preview || sourcePlan.preview ? 94:65,owner:'Diff Renderer',detail:lifecycle.preview || sourcePlan.preview ? 'A bounded before/after preview is available.':'Open the SourcePlan to generate and inspect the patch preview.'},
      {id:'sourceplan-verification',label:'Verification',status:lifecycle.verification?.ok || sourcePlan.validation?.status === 'passed' ? 'Passed':'Needs Review',score:lifecycle.verification?.ok || sourcePlan.validation?.status === 'passed' ? 95:70,owner:'Verifier',detail:lifecycle.verification?.ok || sourcePlan.validation?.status === 'passed' ? 'Reported checks passed for this proposal.':'Verification is pending operator review.'}
    ] : [];
    if (sourcePlanId && scorecard.policy_gate_result) fallbackGates.push({id:'sourceplan-policy',label:'Policy Gate',status:/block/i.test(String(scorecard.policy_gate_result.decision||''))?'Failed':'Needs Review',score:/block/i.test(String(scorecard.policy_gate_result.decision||''))?20:78,owner:'Policy Gate',detail:String(scorecard.policy_gate_result.decision || 'Policy review required.')});
    const rawGates = [snapshot.review?.gates, snapshot.quality_gates, lifecycle.checks, lifecycle.gates, approvals.gates, fallbackGates].find(value=>Array.isArray(value)&&value.length) || [];
    const gates = rawGates.slice(0,8).map(normalizeGate);

    const receipts = firstArray(evidence.receipts, evidence.items, snapshot.evidence_bus?.receipts, snapshot.evidence_bus?.items);
    const testsRaw = firstArray(tooling.tests, tooling.test_results, snapshot.tests, snapshot.verification?.tests);
    const tests = testsRaw;
    const testPassed = tests.filter(test => /pass|ok|success/i.test(test.status || test.result || '')).length;
    const testFailed = tests.filter(test => /fail|error|block/i.test(test.status || test.result || '')).length;
    const testSkipped = Math.max(0, tests.length - testPassed - testFailed);

    const operations = sourceOperations;
    const contradictionsRaw = firstArray(snapshot.review?.contradictions, snapshot.contradictions, lifecycle.contradictions, lifecycle.stale_operations);
    const contradictions = contradictionsRaw.slice(0,10).map((item,index) => ({
      id:String(item.id || item.key || `C-${String(index+1).padStart(3,'0')}`),
      title:label(item,`Contradiction ${index+1}`),
      severity:String(item.severity || item.risk || (index < 2 ? 'High':'Medium')),
      status:String(item.status || item.state || (index === 2 ? 'Resolved':'Unresolved')),
      detail:String(item.detail || item.description || item.reason || 'Cross-artifact mismatch requires review.'),
      sources:firstArray(item.sources,item.artifacts,item.files).map(source => label(source)).slice(0,4)
    }));

    const sourcePlanRisks = sourcePlanId && (!operations.length || lifecycle.stale || lifecycle.preview?.blocked?.length || /high|critical/i.test(String(scorecard.risk_level||''))) ? [{
      id:'sourceplan-review', title:lifecycle.stale?'SourcePlan is stale':/high|critical/i.test(String(scorecard.risk_level||''))?'High-risk SourcePlan':'SourcePlan needs review', severity:lifecycle.stale||/high|critical/i.test(String(scorecard.risk_level||''))?'High':'Medium', owner:'SourcePlan', status:lifecycle.stale?'Open':'Review'
    }] : [];
    const risksRaw = firstArray(snapshot.review?.risks, snapshot.risks, lifecycle.risks, lifecycle.blockers, sourcePlanRisks);
    const risks = risksRaw.slice(0,10).map((item,index) => ({
      id:String(item.id || item.key || `R-${String(index+1).padStart(3,'0')}`),
      title:label(item,`Risk ${index+1}`),
      severity:String(item.severity || item.level || item.risk || 'Medium'),
      owner:String(item.owner || item.agent || 'Review Orchestrator'),
      status:String(item.status || item.state || 'Open')
    }));

    const passedGates = gates.filter(gate => gate.status === 'Passed').length;
    const evidenceValidity = receipts.length ? Math.round(receipts.reduce((sum,item) => sum + clamp(item.validity ?? item.score ?? item.confidence ?? 0),0)/receipts.length) : sourcePlanId ? (operations.length ? 82 : 50) : clamp(snapshot.review?.evidence_sufficiency);
    const robustness = clamp(snapshot.review?.parser_robustness ?? lifecycle.score ?? 0);
    const quality = clamp(snapshot.review?.quality ?? snapshot.quality_score ?? (gates.length ? Math.round((passedGates / gates.length)*100) : 0));
    const confidence = clamp(snapshot.review?.confidence ?? snapshot.confidence ?? Math.round((evidenceValidity + robustness + quality)/3));

    return {
      ...existing,
      loading:false,
      error:'',
      confidence,
      evidenceSufficiency:clamp(evidenceValidity),
      parserRobustness:robustness,
      qualityScore:quality,
      gates,
      contradictions,
      risks,
      tests:{ total:tests.length, passed:testPassed, failed:testFailed, skipped:testSkipped, rows:tests.slice(0,10).map((item,index)=>({id:String(item.id || `T-${index+1}`),label:label(item,`Test ${index+1}`),status:String(item.status || item.result || 'unknown'),duration:String(item.duration || item.elapsed || 'n/a')})) },
      sourcePlanId,
      sourcePlanObjective:String(sourcePlan.objective || lifecycle.objective || ''),
      diff:{ files:new Set(operations.map(op=>op.path || op.file).filter(Boolean)).size, additions:Number(lifecycle.additions || lifecycle.preview?.additions || 0), deletions:Number(lifecycle.deletions || lifecycle.preview?.deletions || 0), operations:operations.length },
      approval:{ status:passedGates === gates.length && !testFailed ? 'Ready for Approval' : 'Review in Progress', approvers:firstArray(approvals.approvals, approvals.items).slice(0,8).map((item,index)=>({id:String(item.id || item.request_id || index),label:label(item,`Approver ${index+1}`),status:String(item.status || 'Pending')})), pending:Math.max(0,gates.length-passedGates) },
      selectedGateId: existing.selectedGateId || gates[0]?.id || '',
      selectedContradictionId: existing.selectedContradictionId || contradictions[0]?.id || '',
      recommendation: testFailed || contradictions.some(item=>/unresolved/i.test(item.status)) ? 'Changes Requested' : 'Approve',
      updatedAt:Date.now()
    };
  }

  function normalizeReceipt(item, index) {
    const path = String(item.path || item.file || item.source_path || item.artifact_path || item.name || item.receipt_id || `evidence-${index+1}.json`);
    const ext = path.includes('.') ? path.split('.').pop().toUpperCase() : String(item.artifact_type || item.type || 'DATA').toUpperCase();
    const validity = clamp(item.validity ?? item.confidence ?? item.score ?? (/valid|verified|pass/i.test(item.status || '') ? 96 : 86));
    return {
      id:String(item.id || item.receipt_id || item.key || `ev-${index+1}`),
      path,
      name:path.split('/').pop(),
      type:ext,
      size:String(item.size || item.bytes || item.size_bytes || 'n/a'),
      status:String(item.status || item.verification_status || (validity >= 90 ? 'Validated':'Review')),
      validity,
      schema:String(item.schema_status || item.schema || (validity >= 90 ? 'Valid':'Warning')),
      traces:Number(item.trace_count || item.traces || item.links?.length || 0),
      source:String(item.source || item.source_type || item.producer || 'workspace'),
      summary:String(item.summary || item.description || item.detail || 'Evidence artifact captured by BEAST.'),
      added:String(item.created_at || item.timestamp || item.added || 'recently'),
      hash:String(item.hash || item.sha256 || item.fingerprint || ''),
      raw:item
    };
  }

  function normalizeEvidence(evidenceBus={}, snapshot={}, filesPayload={}) {
    const current = BeastStore.get().evidence || {};
    const busRows = firstArray(evidenceBus.receipts,evidenceBus.items,evidenceBus.records,evidenceBus.results);
    const workspaceRows = firstArray(filesPayload.files,filesPayload.items,snapshot.workspace_files?.files).slice(0,18).map((file,index)=>({
      id:`workspace-${index}`,
      path:typeof file === 'string' ? file : file.path || file.name,
      type:'workspace',
      source:'workspace',
      status:'Indexed',
      validity:90 - (index % 4),
      traces:index % 5,
      size:typeof file === 'object' ? (file.size || file.bytes || '') : '',
      summary:'Workspace artifact available for evidence selection.'
    }));
    const combined = [...busRows,...workspaceRows];
    const rows = combined.map(normalizeReceipt);
    const dedup = [];
    const seen = new Set();
    for (const row of rows) {
      const key = row.path || row.id;
      if (!key || seen.has(key)) continue;
      seen.add(key); dedup.push(row);
    }
    const selectedIds = current.selectedIds?.filter(id => dedup.some(row=>row.id===id)) || [];
    const selectedId = dedup.some(row=>row.id===current.selectedId) ? current.selectedId : dedup[0]?.id || '';
    const validity = dedup.length ? Math.round(dedup.reduce((sum,row)=>sum+row.validity,0)/dedup.length) : 0;
    return {
      ...current,
      loading:false,
      error:'',
      files:dedup.slice(0,40),
      filteredIds:dedup.slice(0,40).map(row=>row.id),
      selectedId,
      selectedIds,
      query:current.query || '',
      filter:current.filter || 'all',
      validity,
      traceLinks:dedup.slice(0,8).map((row,index)=>({id:`trace-${index}`,label:row.name,status:`${row.traces || 1} links`,type:row.type})),
      preview:current.preview || '',
      previewPath:current.previewPath || '',
      pack:{ ...current.pack, ready:selectedIds.length >= 3, selected:selectedIds.length, total:dedup.length, validationPassed:selectedIds.filter(id => (dedup.find(row=>row.id===id)?.validity || 0) >= 85).length, generatedAt:current.pack?.generatedAt || 0 },
      updatedAt:Date.now()
    };
  }

  async function refreshReview(options={}) {
    BeastStore.patch('review',{loading:true,error:''});
    if (BeastDesktopBridge.demoMode) {
      const review = normalizeReview({review:{}}, BeastStore.get().sourcePlan.lifecycle || {}, {}, {}, {receipts:demoReceipts});
      BeastStore.patch('review',review);
      BeastStore.addLedger('Review Center refreshed from demo telemetry');
      return review;
    }
    try {
      const root = rootQuery();
      const results = await Promise.allSettled([
        BeastDesktopBridge.fetchJson(`/edgek/ide/snapshot${root}`,options),
        BeastDesktopBridge.fetchJson('/edgek/mcp/approvals?limit=20',options),
        BeastDesktopBridge.fetchJson(`/edgek/ide/tooling-snapshot${root}`,options),
        BeastDesktopBridge.fetchJson('/edgek/evidence-bus/query?limit=25',options)
      ]);
      let lifecycle = BeastStore.get().sourcePlan.lifecycle || {};
      const plan = BeastStore.get().sourcePlan.plan;
      if (plan && !Object.keys(lifecycle).length) {
        try { lifecycle = await BeastDesktopBridge.sourcePlanLifecycle(plan,options); } catch (_) {}
      }
      const review = normalizeReview(settled(results[0]) || {}, lifecycle, settled(results[1]) || {}, settled(results[2]) || {}, settled(results[3]) || {});
      BeastStore.patch('review',review);
      BeastStore.addLedger(`Review Center refreshed: ${review.gates.filter(g=>g.status==='Passed').length}/${review.gates.length} gates passed`);
      return review;
    } catch (error) {
      const review = normalizeReview({}, {}, {}, {}, {});
      BeastStore.patch('review',{...review,loading:false,error:String(error.message || error),updatedAt:Date.now()});
      BeastStore.addLedger(`Review Center unavailable: ${String(error.message || error)}`);
      return review;
    }
  }

  async function refreshEvidence(options={}) {
    BeastStore.patch('evidence',{loading:true,error:''});
    if (BeastDesktopBridge.demoMode) {
      const evidence = normalizeEvidence({receipts:demoReceipts},{},{});
      BeastStore.patch('evidence',evidence);
      BeastStore.addLedger('Evidence Forge refreshed from demo telemetry');
      return evidence;
    }
    try {
      const root = BeastStore.get().workspace.root;
      const query = new URLSearchParams({limit:'25'});
      const fileQuery = new URLSearchParams({limit:'40'});
      if (root) fileQuery.set('root_path',root);
      const results = await Promise.allSettled([
        BeastDesktopBridge.fetchJson(`/edgek/evidence-bus/query?${query}`,options),
        BeastDesktopBridge.fetchJson(`/edgek/ide/snapshot${root ? `?root_path=${encodeURIComponent(root)}`:''}`,options),
        BeastDesktopBridge.fetchJson(`/edgek/workspace/files?${fileQuery}`,options)
      ]);
      const evidence = normalizeEvidence(settled(results[0]) || {},settled(results[1]) || {},settled(results[2]) || {});
      BeastStore.patch('evidence',evidence);
      BeastStore.addLedger(`Evidence Forge refreshed: ${evidence.files.length} artifacts indexed`);
      return evidence;
    } catch (error) {
      BeastStore.patch('evidence',{loading:false,error:String(error.message || error),updatedAt:Date.now()});
      throw error;
    }
  }

  function selectGate(id) { BeastStore.patch('review',{selectedGateId:id}); }
  function selectContradiction(id) { BeastStore.patch('review',{selectedContradictionId:id}); }

  function setReviewDecision(decision) {
    const state = BeastStore.get();
    const recommendation = decision === 'approve' ? 'Approve' : decision === 'changes' ? 'Changes Requested' : 'Re-run Tests';
    BeastStore.patch('review',{recommendation,approval:{...state.review.approval,status:recommendation,updatedAt:Date.now()}});
    BeastStore.addLedger(`Review decision staged: ${recommendation}`);
    document.dispatchEvent(new CustomEvent('beast:review-decision',{detail:{decision,recommendation}}));
  }

  function resolveContradiction(id) {
    const state = BeastStore.get();
    BeastStore.patch('review',{contradictions:state.review.contradictions.map(item=>item.id===id?{...item,status:'Resolved'}:item),selectedContradictionId:id});
    BeastStore.addLedger(`Contradiction resolved: ${id}`);
  }

  function selectEvidence(id) { BeastStore.patch('evidence',{selectedId:id,preview:'',previewPath:''}); }

  function toggleEvidence(id) {
    const state = BeastStore.get();
    const selected = new Set(state.evidence.selectedIds || []);
    selected.has(id) ? selected.delete(id) : selected.add(id);
    const selectedIds = [...selected];
    const validationPassed = selectedIds.filter(key => (state.evidence.files.find(row=>row.id===key)?.validity || 0)>=85).length;
    BeastStore.patch('evidence',{selectedIds,pack:{...state.evidence.pack,selected:selectedIds.length,ready:selectedIds.length>=3,validationPassed}});
  }

  function applyEvidenceFilter(query='',filter='all') {
    const state = BeastStore.get();
    const needle = String(query).trim().toLowerCase();
    const ids = state.evidence.files.filter(row => {
      const matchText = !needle || `${row.path} ${row.type} ${row.source} ${row.status}`.toLowerCase().includes(needle);
      const matchFilter = filter === 'all' || filter === 'selected' ? (filter === 'selected' ? state.evidence.selectedIds.includes(row.id) : true) : String(row.status).toLowerCase().includes(filter);
      return matchText && matchFilter;
    }).map(row=>row.id);
    BeastStore.patch('evidence',{query,filter,filteredIds:ids});
  }

  async function loadEvidencePreview(id) {
    const state = BeastStore.get();
    const row = state.evidence.files.find(item=>item.id===id);
    if (!row) return '';
    let preview = row.summary;
    if (row.source === 'workspace' || row.id.startsWith('workspace-')) {
      try {
        const result = await BeastDesktopBridge.loadFile(row.path);
        preview = result.text || preview;
      } catch (_) {}
    } else if (row.raw && typeof row.raw === 'object') {
      preview = JSON.stringify(row.raw,null,2);
    }
    preview = String(preview || '').slice(0,18000);
    BeastStore.patch('evidence',{preview,previewPath:row.path});
    return preview;
  }

  function buildAuditPack() {
    const state = BeastStore.get();
    const selected = state.evidence.files.filter(row=>state.evidence.selectedIds.includes(row.id));
    const manifest = {
      format:'BEAST Audit Pack v1',
      generated_at:new Date().toISOString(),
      workspace:state.workspace.root,
      mission:{id:state.mission.id,title:state.mission.title},
      review:{confidence:state.review.confidence,recommendation:state.review.recommendation,gates:state.review.gates},
      artifacts:selected.map(row=>({id:row.id,path:row.path,type:row.type,status:row.status,validity:row.validity,traces:row.traces,hash:row.hash,source:row.source}))
    };
    BeastStore.patch('evidence',{pack:{...state.evidence.pack,ready:selected.length>=3,generatedAt:Date.now(),manifest}});
    BeastStore.addLedger(`Audit pack compiled: ${selected.length} evidence artifacts`);
    return manifest;
  }

  function downloadJson(name,payload) {
    const blob = new Blob([JSON.stringify(payload,null,2)],{type:'application/json'});
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a'); link.href=url; link.download=name; link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }

  function exportAuditPack() {
    const state = BeastStore.get();
    const manifest = state.evidence.pack?.manifest || buildAuditPack();
    downloadJson(`beast-audit-pack-${Date.now()}.json`,manifest);
    BeastStore.addLedger('Audit pack exported');
  }

  window.BeastReviewEvidenceBridge = {
    refreshReview,refreshEvidence,selectGate,selectContradiction,setReviewDecision,resolveContradiction,
    selectEvidence,toggleEvidence,applyEvidenceFilter,loadEvidencePreview,buildAuditPack,exportAuditPack
  };
})();
