(() => {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[char]);
  const items = [
    ['Artifact Registry','Signed manifests, OCI artifacts, SBOMs and attestations','Registry'],
    ['Artifact Vault','Content-addressed snapshots, refs and verified chunks','Vault'],
    ['Chunk Store','Deduplicated resumable model and dataset chunks','Storage'],
    ['Dataset River','Parquet/Arrow streams, filters, shards and lineage','Data'],
    ['Job Choir','Capability-advertised nodes, pressure budget and attestation','Compute'],
    ['Route Damping','Provider/node flap penalties, suppression and recovery','Trust'],
    ['Space Forge','Signed runnable Spaces with mounts and network policy','Runtime']
  ];

  async function request(path, options={}) {
    return await BeastRuntime.request(path, {timeoutMs:8000, attempts:1, cacheTtl:0, ...options});
  }

  function setNotice(root, message, kind='') {
    const node=root.querySelector('[data-commons-notice]');
    node.textContent=message || '';
    node.className=`cortex-empty-list ${kind}`;
  }

  async function loadBuckets(root, nodeId) {
    if(!nodeId) return;
    root.dataset.selectedNode=nodeId;
    const target=root.querySelector('[data-remote-buckets]');
    target.innerHTML='<span class="cortex-empty-list">Loading signed bucket inventory…</span>';
    try {
      const result=await request(`/edgek/control-plane/commons/remote/nodes/${encodeURIComponent(nodeId)}/buckets`);
      const rows=result.buckets||[];
      target.innerHTML=rows.length ? `<div class="commons-bucket-grid">${rows.map(bucket=>`<article class="beast-card compact commons-bucket-card"><header class="beast-panel-head"><div><h3>${esc(bucket.bucket_id)}</h3><span>${esc(bucket.description||'No description')}</span></div><span class="beast-pill ${bucket.visibility==='public'?'live':''}">${esc(bucket.visibility)}</span></header><div class="commons-live-status"><b>${Number(bucket.revision_count||0)} revisions</b><small>Owner ${esc(bucket.owner)} · immutable content-addressed files</small></div><div class="commons-card-footer"><span>CONTENT ADDRESSED</span><button class="beast-button secondary" data-bucket-revisions="${esc(bucket.bucket_id)}">View Revisions</button></div></article>`).join('')}</div>` : '<span class="cortex-empty-list">This node has no visible buckets yet.</span>';
      target.querySelectorAll('[data-bucket-revisions]').forEach(button=>button.addEventListener('click',()=>loadRevisions(root,nodeId,button.dataset.bucketRevisions)));
    } catch(error) {
      target.innerHTML=`<span class="cortex-empty-list">${esc(error.message||error)}</span>`;
    }
  }

  async function loadRevisions(root,nodeId,bucketId) {
    const [owner,name]=String(bucketId||'').split('/');
    if(!owner||!name) return;
    const target=root.querySelector('[data-remote-buckets]');
    target.innerHTML=`<span class="cortex-empty-list">Loading ${esc(bucketId)} revisions…</span>`;
    try {
      const result=await request(`/edgek/control-plane/commons/remote/nodes/${encodeURIComponent(nodeId)}/buckets/${encodeURIComponent(owner)}/${encodeURIComponent(name)}/revisions`);
      const rows=result.revisions||[];
      target.innerHTML=`<div class="commons-card-toolbar"><button class="beast-button secondary" data-back-buckets>Back to Buckets</button><span>${esc(bucketId)} · immutable revision ledger</span></div>`+(rows.length?`<div class="commons-revision-grid">${rows.map(row=>`<article class="beast-card compact commons-revision-card"><header class="beast-panel-head"><div><h3>${esc(bucketId)}@${esc(row.revision)}</h3><span>${esc(row.manifest_digest)}</span></div><span class="beast-pill">VERIFY ONLY</span></header><div class="commons-card-footer"><span>LOCAL REPRODUCTION REQUIRED</span><button class="beast-button hot" data-import-revision="${esc(row.revision)}">Import to Local Quarantine</button></div></article>`).join('')}</div>`:'<span class="cortex-empty-list">No revisions committed yet.</span>');
      target.querySelector('[data-back-buckets]')?.addEventListener('click',()=>loadBuckets(root,nodeId));
      target.querySelectorAll('[data-import-revision]').forEach(button=>button.addEventListener('click',async()=>{
        setNotice(root,`Pulling and verifying ${bucketId}@${button.dataset.importRevision}…`);
        try {
          const imported=await request(`/edgek/control-plane/commons/remote/nodes/${encodeURIComponent(nodeId)}/buckets/${encodeURIComponent(owner)}/${encodeURIComponent(name)}/revisions/${encodeURIComponent(button.dataset.importRevision)}/import`,{method:'POST',body:{}});
          setNotice(root,`${bucketId}@${button.dataset.importRevision}: ${imported.status}; local reproduction still required.`,'live');
        } catch(error){setNotice(root,String(error.message||error),'error');}
      }));
    } catch(error){target.innerHTML=`<span class="cortex-empty-list">${esc(error.message||error)}</span>`;}
  }

  function renderRemote(root, remote) {
    const nodes=remote.nodes||[];
    root.querySelector('[data-remote-readiness]').innerHTML=[
      ['Registered Nodes',nodes.length,'Pinned origins only'],
      ['Client Signing',remote.client_signing_ready?'READY':'LOCKED',remote.client_signing_ready?'Scoped Ed25519 writes':'Configure BEAST_COMMONS_REMOTE_CLIENT_KEY'],
      ['Lattice Verify',remote.lattice_verification_ready?'READY':'LOCKED',remote.lattice_verification_ready?'Crystal-compute trust root active':'Configure BEAST_COMMONS_LATTICE_TRUST_STORE'],
      ['ARDA Substrate',remote.arda_verification_ready?'READY':'OPTIONAL',remote.arda_verification_ready?'Additive hardware assurance active':'Optional TPM/ARDA appraisal'],
      ['Egress Gate',remote.egress?.policy||'LOCKED',(remote.egress?.allowed_hosts||[]).join(', ')||'Explicit HTTPS origins']
    ].map(([label,value,detail])=>`<article class="beast-card compact terminal-metric"><div><h3>${esc(label)}</h3><strong>${esc(value)}</strong><span>${esc(detail)}</span></div></article>`).join('');
    root.querySelector('[data-remote-nodes]').innerHTML=nodes.length ? `<div class="commons-node-grid">${nodes.map(node=>{
      const probe=node.last_probe||{};
      const admitted=['lattice_attested','lattice_hardware_attested','hardware_attested','authenticated_unattested'].includes(node.state);
      return `<article class="beast-card compact commons-node-card"><header class="beast-panel-head"><div><h3>${esc(node.node_id)}</h3><span>${esc(node.endpoint)}</span></div><span class="beast-pill ${admitted?'live':''}">${esc(node.state)}</span></header><div class="commons-live-status"><b>${esc(String(node.trust_policy||'pinned').toUpperCase())}</b><small>${esc(probe.workload_digest||node.expected_workload_digest||'workload pending probe')}</small></div><div class="commons-card-footer"><button class="beast-button secondary" data-probe-node="${esc(node.node_id)}">Probe Identity</button><button class="beast-button secondary" data-browse-node="${esc(node.node_id)}" ${admitted?'':'disabled'}>Browse Buckets</button></div></article>`;
    }).join('')}</div>` : '<span class="cortex-empty-list">No remote Commons nodes are registered. Pin a node identity below; BEAST never performs trust-on-first-use.</span>';
    root.querySelectorAll('[data-probe-node]').forEach(button=>button.addEventListener('click',async()=>{
      setNotice(root,`Probing ${button.dataset.probeNode}…`);
      try {
        const result=await request(`/edgek/control-plane/commons/remote/nodes/${encodeURIComponent(button.dataset.probeNode)}/probe`,{method:'POST',body:{}});
        const basis=result.lattice_attestation_verified?'lattice witnessed':result.arda_appraisal_verified?'ARDA substrate verified':'cryptographically pinned';
        setNotice(root,`${result.node_id}: ${result.state} · ${basis}`,'live');
        await load(root);
      } catch(error) { setNotice(root,String(error.message||error),'error'); }
    }));
    root.querySelectorAll('[data-browse-node]').forEach(button=>button.addEventListener('click',()=>loadBuckets(root,button.dataset.browseNode)));
  }

  function renderDiscovery(root, discovery={}) {
    const rows=discovery.candidates||[];
    root.querySelector('[data-discovery-summary]').textContent=`${Number(discovery.candidate_count||0)} observed · ${Number(discovery.trusted_candidate_count||0)} lattice-trusted · ${(discovery.sources||[]).join(', ')||'no adapters configured'}`;
    root.querySelector('[data-remote-discovery]').innerHTML=rows.length?`<div class="commons-discovery-grid">${rows.map(row=>{
      const verification=row.trust?.verification||{};
      const lattice=verification.lattice_attestation||{};
      return `<article class="beast-card compact commons-discovery-card"><header class="beast-panel-head"><div><h3>${esc(row.node_id)}</h3><span>${esc(row.origin)}</span></div><span class="beast-pill ${row.state==='trusted_candidate'?'live':''}">${esc(row.state)}</span></header><div class="commons-live-status"><b>${esc(row.source)} · ${esc(lattice.assurance_class||'UNVERIFIED')}</b><small>${esc(lattice.authority||row.trust?.error||'candidate evidence pending')} ${lattice.lattice_head_hash?'· '+esc(String(lattice.lattice_head_hash).slice(0,24))+'…':''}</small></div></article>`;
    }).join('')}</div>`:'<span class="cortex-empty-list">No candidates observed. Add explicit origins or feed a signed envelope through another discovery adapter.</span>';
  }

  async function load(root) {
    const paths=['/edgek/control-plane/services','/edgek/control-plane/tool-buckets?phase=Observe','/edgek/control-plane/workspace-identity','/edgek/control-plane/commons','/edgek/control-plane/enterprise','/edgek/control-plane/commons/remote'];
    const results=await Promise.all(paths.map(async path=>{try{return await request(path,{timeoutMs:1800});}catch(error){return {error:String(error.message||error),path};}}));
    const [services,tools,workspace,commons,enterprise,remote]=results;
    const metrics=[['Services',Object.keys(services.services||{}).length,services.registry_digest||'unavailable'],['Tool Schemas',(tools.visible_tools||[]).length,`${(tools.buckets||[]).length} governed buckets`],['Workspace',workspace.digest?'BOUND':'ERROR',workspace.digest||workspace.error||'unavailable'],['Commons',commons.status||'ERROR',commons.mode||commons.error||'unavailable'],['Remote Nodes',remote.node_count??'ERROR',remote.mode||remote.error||'unavailable'],['Identity Guard',enterprise.workspace_identity?.guard_mode||'ERROR',enterprise.workspace_identity?.digest||enterprise.error||'unavailable']];
    root.querySelector('[data-commons-metrics]').innerHTML=metrics.map(([label,value,detail])=>`<article class="beast-card compact terminal-metric"><div><h3>${esc(label)}</h3><strong>${esc(value)}</strong><span>${esc(String(detail).slice(0,64))}</span></div></article>`).join('');
    const routeRows=Object.values(commons.route_damping?.routes||{}); const suppressed=routeRows.filter(row=>row.suppressed).length;
    const jobChoirReady=Boolean(
      commons.job_choir?.attestation_verifier_configured &&
      commons.tpm_attestation?.submission_verifier_live
    );
    const details=[
      [`${commons.artifact_registry?.count||0} manifests`,commons.artifact_registry?.signature_verifier_configured?'Ed25519 authority verifier active':'ADMISSION LOCKED · trust store not configured'],
      [`${commons.artifact_vault?.objects||0} objects`,`${commons.artifact_vault?.bytes||0} bytes retained`],
      [`${commons.chunk_store?.chunks||0} chunks`,`${commons.chunk_store?.bytes||0} bytes deduplicated`],
      [`${(commons.dataset_river?.privacy_labels||[]).length} privacy classes`,commons.dataset_river?.lineage_required?'Lineage required':'Lineage unavailable'],
      [
        jobChoirReady ? 'READY' : 'LOCKED',
        jobChoirReady
          ? 'Attested node verification and TPM appraisal submission are active'
          : commons.job_choir?.attestation_verifier_configured
            ? 'TPM appraisal submission is not live yet'
            : 'Self-reported node state is not accepted'
      ],
      [`${routeRows.length} routes`,`${suppressed} suppressed · half-life ${commons.route_damping?.half_life_seconds||0}s`],
      [commons.admission?.ready?'READY':'LOCKED',commons.admission?.ready?'Signed authority gates active; remote lattice evidence remains verify-only':'Configure Commons authority trust roots']
    ];
    root.querySelector('[data-commons-grid]').querySelectorAll('.beast-card').forEach((card,i)=>{const [value,detail]=details[i];card.querySelector('.commons-surface-reading').innerHTML=`<b>${esc(value)}</b><small>${esc(detail)}</small><i aria-hidden="true"></i>`;});
    renderRemote(root,remote.error?{nodes:[],...remote}:remote);
    renderDiscovery(root,remote.discovery||{});
    if(remote.error){
      const detail=/not found/i.test(String(remote.error))
        ? 'Remote Commons is absent from this running gateway. Restart BEAST Desktop to load the current remote-node control-plane route.'
        : `Remote Commons is unavailable: ${remote.error}`;
      setNotice(root,detail,'error');
    }
    if(root.dataset.selectedNode) await loadBuckets(root,root.dataset.selectedNode);
  }

  function bindForms(root) {
    root.querySelector('[data-discovery-form]').addEventListener('submit',async event=>{
      event.preventDefault();
      const data=new FormData(event.currentTarget);
      const origins=String(data.get('origins')||'').split(/[\s,]+/).filter(Boolean);
      if(!origins.length){setNotice(root,'Enter at least one explicit Commons origin.','error');return;}
      setNotice(root,`Discovering ${origins.length} candidate origin${origins.length===1?'':'s'}…`);
      try {
        const result=await request('/edgek/control-plane/commons/remote/discovery',{method:'POST',body:{origins,source:data.get('source')||'well_known',auto_register:true},timeoutMs:15000});
        const admitted=(result.results||[]).filter(row=>row.registered).length;
        setNotice(root,`${result.results?.length||0} origins checked · ${admitted} admitted by lattice evidence.`,'live');
        await load(root);
      } catch(error){setNotice(root,String(error.message||error),'error');}
    });
    root.querySelector('[data-node-form]').addEventListener('submit',async event=>{
      event.preventDefault();
      const data=new FormData(event.currentTarget);
      const payload={node_id:data.get('node_id'),endpoint:data.get('endpoint'),node_public_key:data.get('node_public_key'),expected_workload_digest:data.get('expected_workload_digest'),trust_policy:data.get('trust_policy')||'lattice',require_arda:false,expected_policy_generation:data.get('expected_policy_generation')};
      setNotice(root,'Registering pinned node…');
      try { await request('/edgek/control-plane/commons/remote/nodes',{method:'POST',body:payload});setNotice(root,`${payload.node_id} registered. Probe before use.`,'live');await load(root); }
      catch(error){setNotice(root,String(error.message||error),'error');}
    });
    root.querySelector('[data-bucket-form]').addEventListener('submit',async event=>{
      event.preventDefault();
      const nodeId=root.dataset.selectedNode;
      if(!nodeId){setNotice(root,'Browse an admitted node before creating a bucket.','error');return;}
      const data=new FormData(event.currentTarget);
      const payload={owner:data.get('owner'),name:data.get('name'),visibility:data.get('visibility'),description:data.get('description')};
      setNotice(root,`Creating ${payload.owner}/${payload.name} on ${nodeId}…`);
      try { await request(`/edgek/control-plane/commons/remote/nodes/${encodeURIComponent(nodeId)}/buckets`,{method:'POST',body:payload});setNotice(root,'Remote bucket created with signed control-plane authority.','live');await loadBuckets(root,nodeId); }
      catch(error){setNotice(root,String(error.message||error),'error');}
    });
  }

  function renderer() {
    const root=document.createElement('div'); root.className='beast-page beast-commons-page';
    root.innerHTML=`<header class="beast-page-head"><div><h2>Commons Forge</h2><div class="sub">ARTIFACTS // REMOTE BUCKETS // DATA RIVERS // JOB CHOIR // ATTESTED NODES // SPACE RUNTIME</div></div><div class="beast-page-actions"><button class="beast-button secondary" data-commons-refresh>Refresh Surfaces</button></div></header><section class="p8-metric-grid" data-commons-metrics></section><div class="p8-economy-grid" data-commons-grid></div><section class="beast-card wide is-active"><header class="beast-panel-head"><div><h3>Remote Commons Space Nodes</h3><span>Pinned service identity · scoped writes · replay resistance · signed revision receipts</span></div><span class="beast-pill live">GATE OF NIGHT</span></header><section class="p8-metric-grid" data-remote-readiness></section><div class="p8-economy-grid commons-subgrid"><section class="commons-subpanel"><h3>Registered nodes</h3><div data-remote-nodes></div></section><section class="commons-subpanel"><h3>Visible buckets</h3><div data-remote-buckets><span class="cortex-empty-list">Browse an admitted node to load its buckets.</span></div></section></div><div class="cortex-empty-list" data-commons-notice aria-live="polite"></div></section><div class="p8-economy-grid"><section class="beast-card"><header class="beast-panel-head"><div><h3>Pin Remote Node</h3><span>No trust-on-first-use. Copy the node's out-of-band Ed25519 pin.</span></div></header><form data-node-form class="p8-setting-stack"><label class="p8-setting"><span>Node ID</span><input name="node_id" required placeholder="commons-node-a"></label><label class="p8-setting"><span>HTTPS origin</span><input name="endpoint" required placeholder="https://commons.example.org"></label><label class="p8-setting"><span>Ed25519 public pin (base64)</span><input name="node_public_key" required placeholder="32-byte raw public key"></label><label class="p8-setting"><span>Expected workload digest</span><input name="expected_workload_digest" placeholder="sha256:…"></label><label class="p8-setting"><span>ARDA policy generation</span><input name="expected_policy_generation" placeholder="policy-…"></label><label class="p8-setting"><span>Require ARDA hardware appraisal</span><input name="require_arda" type="checkbox" checked></label><button class="beast-button hot" type="submit">Register Pinned Node</button></form></section><section class="beast-card"><header class="beast-panel-head"><div><h3>Create Remote Bucket</h3><span>Writes go through BEAST; private signing material never enters the renderer.</span></div></header><form data-bucket-form class="p8-setting-stack"><label class="p8-setting"><span>Owner</span><input name="owner" required placeholder="team"></label><label class="p8-setting"><span>Bucket</span><input name="name" required placeholder="verified-crystals"></label><label class="p8-setting"><span>Visibility</span><select name="visibility"><option value="private">Private</option><option value="public">Public</option></select></label><label class="p8-setting"><span>Description</span><input name="description" placeholder="Proof-carrying reusable artifacts"></label><button class="beast-button hot" type="submit">Create on Selected Node</button></form></section></div><section class="beast-card wide"><header class="beast-panel-head"><div><h3>Commons operating model</h3><span>Remote contributions remain hypotheses until locally reproduced and attested.</span></div><span class="beast-pill live">LOCAL-FIRST</span></header><p>Bucket commits are immutable, content addressed and signed by the remote node. They carry <code>verify_only</code> authority; BEAST still requires local reproduction, held-out verification, policy match and a fresh node appraisal before promotion or execution.</p></section>`;
    const remotePanel=root.querySelector('[data-remote-readiness]').closest('.beast-card');
    remotePanel.insertAdjacentHTML('afterend',`<section class="beast-card wide"><header class="beast-panel-head"><div><h3>Agnostic Discovery</h3><span>HTTP well-known, static seeds, DNS-SD, peer exchange, registries and offline bootstrap converge on one signed candidate envelope.</span></div><span class="beast-pill live">DISCOVERY ≠ TRUST</span></header><form data-discovery-form class="p8-setting-stack"><label class="p8-setting"><span>Explicit origins</span><input name="origins" required placeholder="http://127.0.0.1:8111, https://commons.example.org"></label><label class="p8-setting"><span>Discovery adapter</span><select name="source"><option value="well_known">HTTP well-known</option><option value="static_seed">Static seed</option><option value="peer_exchange">Peer exchange</option><option value="registry">Registry</option><option value="qr_bootstrap">QR / offline bootstrap</option><option value="manual">Manual envelope</option></select></label><button class="beast-button hot" type="submit">Discover + Verify Lattice</button></form><p class="cortex-empty-list" data-discovery-summary>Discovery proposes candidates; signed lattice evidence plus live endpoint possession admits.</p><div data-remote-discovery></div></section>`);
    const pinForm=root.querySelector('[data-node-form]');
    const pinHeader=pinForm.closest('.beast-card').querySelector('.beast-panel-head div');
    pinHeader.innerHTML='<h3>Pinned Fallback</h3><span>Manual pins remain available for explicit operator policy; lattice is the production default.</span>';
    pinForm.querySelector('input[name="require_arda"]').closest('label').outerHTML='<label class="p8-setting"><span>Trust policy</span><select name="trust_policy"><option value="lattice">Crystal lattice (default)</option><option value="lattice_or_arda">Lattice or ARDA</option><option value="lattice_and_arda">Lattice + ARDA</option><option value="arda">ARDA substrate only</option><option value="pinned">Pinned development</option></select></label>';
    const operatingCopy=root.querySelectorAll('.beast-card.wide p');
    if(operatingCopy.length) operatingCopy[operatingCopy.length-1].innerHTML='Bucket commits are immutable, content addressed and signed by the remote node. They carry <code>verify_only</code> authority; BEAST still requires local reproduction, held-out verification and policy match. The crystal-compute lattice is the native Commons trust root; ARDA/TPM may add substrate assurance.';
    const grid=root.querySelector('[data-commons-grid]'); grid.classList.add('commons-forge-grid'); grid.innerHTML=items.map(([title,detail,status])=>`<article class="beast-card commons-surface-card"><header class="beast-panel-head"><div><h3>${title}</h3><span>${detail}</span></div><span class="beast-pill">${status}</span></header><div class="commons-surface-reading"><b>SYNCING</b><small>Live inventory loads from the Commons control plane.</small><i aria-hidden="true"></i></div></article>`).join('');
    root.querySelector('[data-commons-refresh]').addEventListener('click',()=>load(root));
    bindForms(root);
    queueMicrotask(()=>load(root));
    return root;
  }
  window.BeastCommonsPage={renderer};
})();
