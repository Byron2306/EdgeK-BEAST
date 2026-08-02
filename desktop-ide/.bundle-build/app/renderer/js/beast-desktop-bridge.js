(() => {
  const listeners = { workspace: new Set(), refresh: new Set(), log: new Set() };
  const demoMode = window.BEAST_ENABLE_DEMO === true && new URLSearchParams(location.search).get('demo') === '1';
  const DEMO_FILES = {
    'src/core/router.py': `from dataclasses import dataclass\n\n@dataclass\nclass RouteDecision:\n    provider: str\n    model: str\n    reason: str\n\ndef choose_route(task: str) -> RouteDecision:\n    \"\"\"Prefer local inference, escalate only when evidence demands it.\"\"\"\n    if len(task) < 240:\n        return RouteDecision('ollama', 'qwen2.5-coder:7b', 'local-first')\n    return RouteDecision('nvidia_nim', 'nemotron', 'complexity escalation')\n`,
    'src/core/evidence_parser.py': `import json\nfrom pathlib import Path\n\ndef parse_evidence(path: Path) -> list[dict]:\n    rows: list[dict] = []\n    for line in path.read_text(encoding='utf-8').splitlines():\n        if not line.strip():\n            continue\n        rows.append(json.loads(line))\n    return rows\n`,
    'src/ui/mission.ts': `export type MissionState = 'idle' | 'working' | 'alert' | 'complete';\n\nexport function missionLabel(state: MissionState): string {\n  return state === 'complete' ? 'CRYSTALLIZED' : state.toUpperCase();\n}\n`,
    'config/beast.yaml': `runtime:\n  local_first: true\n  max_context_files: 64\n  token_budget: 4000\ngovernance:\n  sourceplan_required: true\n  evidence_closure: true\n`,
    'README.md': `# BEAST Editor Cortex\n\nPhase 2 demonstrates multi-tab editing, persistent dirty buffers, governed SourcePlan drafting, diff review, verification, and apply readiness.\n`
  };

  function desktop() { return window.BeastRuntime?.desktop || window.beastDesktop || null; }
  function workspaceRoot() { return BeastStore.get().workspace.root || ''; }
  const remotePrefix='beast-remote://';
  function remoteRef(host,path) { return `${remotePrefix}${encodeURIComponent(String(host || ''))}/${encodeURIComponent(String(path || ''))}`; }
  function parseRemoteRef(value) { const text=String(value || '');if(!text.startsWith(remotePrefix))return null;const body=text.slice(remotePrefix.length);const cut=body.indexOf('/');if(cut<1)return null;try{return {host:decodeURIComponent(body.slice(0,cut)),path:decodeURIComponent(body.slice(cut+1))};}catch(_){return null;} }
  function gatewayUrl() { return window.BeastRuntime?.gatewayUrl || BeastStore.get().connection.gatewayUrl || window.gatewayUrl || 'http://127.0.0.1:8101'; }

  async function fetchJson(path, options = {}) {
    return await BeastRuntime.request(path, { ...options, timeoutMs: options.timeoutMs ?? 15000 });
  }

  async function status(options = {}) {
    if (demoMode) {
      const result = { gatewayUrl: 'http://127.0.0.1:8000', repoRoot: '/demo/BEAST', version: 'phase10-demo', health: { ok: true, local_mode: true } };
      BeastStore.patch('connection', { status: 'online', gatewayUrl: 'http://127.0.0.1:8000', localMode: true, demoMode: true, build: 'BEAST Phase 10 Demo', checkedAt: Date.now(), error: '' });
      if (workspaceRoot() !== '/demo/BEAST') setRoot('/demo/BEAST');
      return result;
    }
    const api = desktop();
    try {
      const result = api?.status ? await BeastRuntime.desktopCall('status',[]) : await fetchJson('/edgek/root-info', options);
      const gateway = result?.gatewayUrl || BeastRuntime.gatewayUrl || window.gatewayUrl || 'http://127.0.0.1:8101';
      BeastStore.patch('connection', {
        status: result?.health?.ok === false ? 'offline' : 'online', gatewayUrl: gateway,
        localMode: Boolean(result?.health?.local_mode), build: result?.desktopVersion || result?.version || 'BEAST Phase 10',
        checkedAt: Date.now(), error: ''
      });
      if (!workspaceRoot() && result?.repoRoot) setRoot(result.repoRoot,{folders:result.workspaceFolders||[]});
      else if(Array.isArray(result?.workspaceFolders)&&result.workspaceFolders.length)setWorkspaceFolders(result.workspaceFolders);
      window.gatewayUrl = gateway;
      return result;
    } catch (error) {
      BeastStore.patch('connection', { status: 'offline', checkedAt: Date.now(), error: String(error.message || error) });
      return null;
    }
  }

  function setWorkspaceFolders(folders) { const rows=(Array.isArray(folders)?folders:[]).filter(item=>item&&item.path).slice(0,12).map(item=>({id:String(item.id||''),name:String(item.name||item.id||''),path:String(item.path),primary:Boolean(item.primary)}));try { localStorage.setItem('beast.v2.workspace.folders',JSON.stringify(rows)); } catch (_) {} BeastStore.patch('workspace',{roots:rows});return rows; }
  function setExecutionTarget(target={}) { const next=['local','ssh','container'].includes(target.kind)?{...target,kind:target.kind}:{kind:'local'};try{localStorage.setItem('beast.v2.workspace.execution-target',JSON.stringify(next));}catch(_){}BeastStore.patch('workspace',{executionTarget:next});const api=desktop();if(api?.setExecutionTarget)BeastRuntime.desktopCall('setExecutionTarget',[next]).then(result=>{if(result?.target){try{localStorage.setItem('beast.v2.workspace.execution-target',JSON.stringify(result.target));}catch(_){}BeastStore.patch('workspace',{executionTarget:result.target});}}).catch(error=>BeastStore.patch('workspace',{error:String(error.message||error)}));return next; }
  async function listExecutionTargets(payload={}) { const api=desktop();if(!api?.listExecutionTargets)return {ok:true,active:BeastStore.get().workspace.executionTarget,targets:[{kind:'local',label:'Local workspace',root:workspaceRoot(),active:true}]};const result=await BeastRuntime.desktopCall('listExecutionTargets',[payload],{required:true});if(result?.active){try{localStorage.setItem('beast.v2.workspace.execution-target',JSON.stringify(result.active));}catch(_){}BeastStore.patch('workspace',{executionTarget:result.active});}return result; }
  function setRoot(root, options = {}) {
    const value = String(root || '').trim();
    const explicitFolders = Array.isArray(options.folders) ? options.folders.filter(item => item && item.path) : [];
    const rootName = value ? value.replace(/[\/]+$/, '').split(/[\/]/).pop() || 'workspace' : 'workspace';
    const activeFolders = explicitFolders.length ? explicitFolders : (value ? [{ id:'active-workspace', name:rootName, path:value, primary:true }] : []);
    if (value === workspaceRoot()) { if(activeFolders.length)setWorkspaceFolders(activeFolders); return value; }
    window.BeastAICoding?.cancel?.();
    localStorage.setItem('beast.v2.workspace.root', value);
    BeastStore.transaction(next => {
      next.workspace = { ...next.workspace, root: value, roots:activeFolders, selectedPath: '', currentText: '', originalText: '', dirty: false, error: '', indexedAt: 0 };
      next.editor = { ...next.editor, openTabs: [], activePath: '', dirtyPaths: [], outline: [], owner: 'unmounted' };
      next.sourcePlan = { ...next.sourcePlan, status: 'idle', message: 'No editor draft yet.', plan: null, lifecycle: null, selectedOperationIds: [], previewText: '', originalText: '', proposedText: '', activeOperationId: '', stale: false, error: '', lastApply: null };
      next.aiCoding = { ...next.aiCoding, sessionId:'', streaming:false, status:'idle', error:'', messages:[], trace:[], contextFiles:[], selection:null, sourcePlanReady:false, sourcePlanId:'', crystal:{ action:'', source:'', confidence:0, reused:false, avoidedTokens:0, decisionId:'', recorded:false } };
      if (!options.preserveWorktreeRegistry && next.worktrees) next.worktrees = { ...next.worktrees, registryRoot: '', root: '', items: [], selectedId: '', diff: '' };
    });
    window.workspaceRoot = value;
    if(Array.isArray(options.folders))setWorkspaceFolders(options.folders);
    return value;
  }

  async function chooseWorkspace() {
    if (demoMode) return setRoot('/demo/BEAST');
    const api = desktop();
    if (!api?.chooseWorkspace) throw new Error('Workspace chooser is available only inside the BEAST desktop shell.');
    const selected = await BeastRuntime.desktopCall('chooseWorkspace',[],{required:true});
    const root=typeof selected==='string'?selected:selected?.root;
    if (root) {
      setRoot(root,{folders:selected?.folders||[]});
      listeners.workspace.forEach(listener => listener(root));
      BeastStore.addLedger(`Workspace selected: ${root}`);
    }
    return root||'';
  }
  async function refreshWorkspaceFolders(){const result=await BeastRuntime.desktopCall('workspaceFolders',[],{required:true});if(result?.root)setRoot(result.root,{folders:result.folders||[]});return result||{root:workspaceRoot(),folders:BeastStore.get().workspace.roots||[]};}
  async function addWorkspaceFolder(){const result=await BeastRuntime.desktopCall('addWorkspaceFolder',[],{required:true});if(result?.root)setRoot(result.root,{folders:result.folders||[]});return result;}
  async function removeWorkspaceFolder(id){const result=await BeastRuntime.desktopCall('removeWorkspaceFolder',[id],{required:true});if(result?.ok&&result.root)setRoot(result.root,{folders:result.folders||[]});return result;}

  function normalizeFiles(payload) {
    const rows = Array.isArray(payload) ? payload : payload?.files || payload?.items || payload?.entries || [];
    return rows.map(row => {
      if (typeof row === 'string') return { path: row, name: row.split('/').pop(), type: 'file', size: '' };
      const path = row.path || row.name || row.file || '';
      return { ...row, path, name: row.name || path.split('/').pop(), type: row.type || row.kind || (path.endsWith('/') ? 'directory' : 'file'), size: row.size ?? row.bytes ?? '' };
    }).filter(row => row.path);
  }

  async function listFiles(options = {}) {
    const root = workspaceRoot();
    if (!root) return [];
    BeastStore.patch('workspace', { loading: true, error: '' });
    try {
      let files;
      if (demoMode) files = Object.entries(DEMO_FILES).map(([path, text]) => ({ path, name: path.split('/').pop(), type: 'file', size: text.length }));
      else {
        const api = desktop();
        let payload;
        const target=BeastStore.get().workspace.executionTarget || {kind:'local'};
        // Local worktrees must be listed by their absolute active root. Using the
        // previous workspace-folder ID here makes a freshly created worktree look
        // empty even though Git checked out every tracked file correctly.
        if (target.kind === 'local' && api?.listFiles) payload = await BeastRuntime.desktopCall('listFiles',[root, options.limit || 2000],{required:true});
        else if (api?.listTargetFiles) payload = await BeastRuntime.desktopCall('listTargetFiles',[{rootId:workspaceFolderForPath('').folder?.id || '',rootPath:root,limit:options.limit || 2000,target}],{required:true});
        else if (api?.listFiles) payload = await BeastRuntime.desktopCall('listFiles',[root, options.limit || 2000],{required:true});
        else payload = await fetchJson(`/edgek/workspace/files?${new URLSearchParams({ root_path: root, limit: String(options.limit || 1000) })}`, options);
        files = normalizeFiles(payload);
      }
      BeastStore.patch('workspace', { files, loading: false, error: '', indexedAt: Date.now() });
      BeastStore.addLedger(`Workspace indexed: ${files.length} entries`);
      return files;
    } catch (error) {
      BeastStore.patch('workspace', { loading: false, error: String(error.message || error) });
      return [];
    }
  }

  async function loadFile(path, options = {}) {
    const root = workspaceRoot();
    const remote=parseRemoteRef(path);
    if ((!root && !remote) || !path) return null;
    if (demoMode) return { path, text: DEMO_FILES[path] ?? '', payload: { content: DEMO_FILES[path] ?? '', demo: true } };
    const api = desktop();
    let payload;
    if (remote) {
      if (!api?.readRemoteFile) throw new Error('Remote file access is available only in the BEAST desktop shell.');
      payload=await BeastRuntime.desktopCall('readRemoteFile',[{host:remote.host,path:remote.path}],{required:true});
    } else if (api?.readTargetFile) payload = await BeastRuntime.desktopCall('readTargetFile',[{rootId:workspaceFolderForPath(path).folder?.id || '',path:workspaceFolderForPath(path).path,maxChars:options.maxChars || 1000000,target:BeastStore.get().workspace.executionTarget || {kind:'local'}}]);
    else if (api?.readFile) payload = await BeastRuntime.desktopCall('readFile',[root, path, options.maxChars || 1000000]);
    else payload = await fetchJson(`/edgek/workspace/file?${new URLSearchParams({ root_path: root, path, max_chars: String(options.maxChars || 1000000) })}`, options);
    const text = typeof payload === 'string' ? payload : payload?.content ?? payload?.text ?? '';
    if (payload?.ok===false) throw new Error(payload.error || 'Unable to read remote file.');
    return { path, text, payload, remote };
  }

  async function sha256(value) { if(!globalThis.crypto?.subtle)return '';const bytes=new TextEncoder().encode(String(value||''));const digest=await globalThis.crypto.subtle.digest('SHA-256',bytes);return [...new Uint8Array(digest)].map(byte=>byte.toString(16).padStart(2,'0')).join(''); }

  async function saveRemoteFile(reference, content, originalContent) {
    const remote=parseRemoteRef(reference);if(!remote)throw new Error('Active editor tab is not a remote file.');
    const api=desktop();if(!api?.writeRemoteFile)throw new Error('Remote file saves are available only in the BEAST desktop shell.');
    const expectedDigest=originalContent===undefined?'':await sha256(originalContent);const result=await BeastRuntime.desktopCall('writeRemoteFile',[{host:remote.host,path:remote.path,content:String(content || ''),expectedDigest}],{required:true});if(!result?.ok){const error=new Error(result?.error || 'Remote file save failed.');error.conflict=Boolean(result?.conflict);throw error;}return result;
  }

  async function saveTargetFile(reference, content, originalContent) {
    const target=BeastStore.get().workspace.executionTarget || {kind:'local'}; const folder=workspaceFolderForPath(reference); const api=desktop();
    if (target.kind==='local') throw new Error('Local files remain SourcePlan-governed.');
    if (!api?.writeTargetFile) throw new Error('Target-aware file saves are available only in the BEAST desktop shell.');
    const expectedDigest=originalContent===undefined?'':`sha256:${await sha256(originalContent)}`;
    const result=await BeastRuntime.desktopCall('writeTargetFile',[{rootId:folder.folder?.id || '',path:folder.path,content:String(content ?? ''),expectedDigest,target}],{required:true});
    if (!result?.ok) { const error=new Error(result?.error || 'Target file save failed.'); error.conflict=Boolean(result?.conflict); throw error; }
    return result;
  }

  async function readFile(path, options = {}) {
    try {
      const loaded = await loadFile(path, options);
      if (!loaded) return null;
      BeastStore.patch('workspace', { selectedPath: path, currentText: loaded.text, originalText: loaded.text, dirty: false, language: inferLanguage(path), error: '' });
      BeastStore.addLedger(`Opened ${path}`);
      return loaded;
    } catch (error) {
      BeastStore.patch('workspace', { error: String(error.message || error) });
      return null;
    }
  }

  function inferLanguage(path) {
    const ext = String(path || '').split('.').pop().toLowerCase();
    return ({ js:'javascript', jsx:'javascript', ts:'typescript', tsx:'typescript', py:'python', json:'json', ipynb:'jupyter-notebook', md:'markdown', html:'html', css:'css', yml:'yaml', yaml:'yaml', sh:'shell', rs:'rust', go:'go', java:'java', c:'c', cpp:'cpp' })[ext] || 'plaintext';
  }
  function workspaceFolderForPath(reference){const value=String(reference||'');const match=value.match(/^@([^/]+)\/(.+)$/);const folders=BeastStore.get().workspace.roots||[];if(!match)return {root:workspaceRoot(),path:value,folder:folders.find(item=>item.primary)||folders[0]||null};const folder=folders.find(item=>item.id===match[1]);return {root:folder?.path||workspaceRoot(),path:match[2],folder:folder||null};}

  function normalizeMission(snapshot = {}, route = {}) {
    const current = BeastStore.get().mission;
    const receipts = snapshot.evidence_bus?.receipts || snapshot.evidence_bus?.items || [];
    const agents = snapshot.agent_sessions?.sessions || (Array.isArray(snapshot.agent_sessions) ? snapshot.agent_sessions : []);
    const graphNodes = snapshot.code_cortex?.nodes || snapshot.code_cortex?.files || [];
    const steps = route.steps || route.route || route.faces || [];
    const ids = ['mission','workspace','source','models','agents','review','crystallization'];
    const path = steps.length ? steps.slice(0, ids.length).map((step, index) => ({ id: ids[index], title: step.title || step.face || step.name || current.path[index]?.title || ids[index], status: step.status || current.path[index]?.status || (index < 1 ? 'Complete' : index < 3 ? 'In Progress' : 'Pending') })) : current.path;
    const health = snapshot.mission_cockpit?.health || snapshot.policy?.reintegration_health || {};
    return {
      id: snapshot.mission_cockpit?.mission_id || snapshot.mission_id || current.id,
      title: snapshot.objective || current.title,
      status: snapshot.status || current.status,
      progress: Number(snapshot.progress ?? snapshot.mission_cockpit?.progress ?? current.progress),
      health: Number(health.score ?? health.overall ?? health.health ?? current.health),
      confidence: health.confidence || current.confidence, risk: health.risk || current.risk,
      metrics: {
        artifacts: Number(snapshot.evidence_bus?.total ?? receipts.length ?? current.metrics.artifacts),
        checks: Number(snapshot.policy?.architecture_decisions?.decision_count ?? current.metrics.checks),
        traces: Number(snapshot.mission_lattice?.nodes ?? graphNodes.length ?? current.metrics.traces),
        evidenceItems: Number(snapshot.workspace_files?.files ?? receipts.length ?? current.metrics.evidenceItems),
        agents: Number(agents.length || current.metrics.agents)
      }, path, timeline: current.timeline
    };
  }

  async function snapshot(options = {}) {
    if (demoMode) {
      BeastStore.patch('mission', { progress: 58, health: 96, status: 'In Progress', lastRefreshAt: Date.now(), loading: false, error: '', metrics: { artifacts: 18, checks: 31, traces: 1842, evidenceItems: 96, agents: 7 } });
      return { demo: true };
    }
    const root = workspaceRoot();
    BeastStore.patch('mission', { loading: true, error: '' });
    try {
      const params = new URLSearchParams();
      if (root) params.set('root_path', root);
      const selected = BeastStore.get().workspace.selectedPath;
      const fullSnapshot = options.full === true;
      if (selected) params.set('active_file', selected);
      // The IDE boot path is an availability probe.  The full Mission Cockpit
      // and Code Cortex aggregation can take tens of seconds on a large repo;
      // those subsystems have their own interactive surfaces and must not block
      // the entire desktop shell.
      params.set('objective', fullSnapshot ? (selected ? `Work on ${selected}` : 'BEAST desktop mission') : 'desktop-health');
      const snap = await fetchJson(`/edgek/ide/snapshot?${params}`, options);
      if (snap?.mode === 'lightweight_health_probe') {
        BeastStore.patch('mission', { loading: false, error: '', lastRefreshAt: Date.now() });
        BeastStore.addLedger('Gateway health snapshot refreshed');
        return snap;
      }
      let route = {};
      try { route = await fetchJson(`/edgek/mission/route?${params}`, { ...options, timeoutMs: 3000 }); } catch (_) {}
      const normalized = normalizeMission(snap, route || {});
      BeastStore.transaction(next => { next.mission = { ...next.mission, ...normalized, loading: false, error: '', lastRefreshAt: Date.now() }; });
      BeastStore.addLedger('Mission snapshot refreshed');
      return snap;
    } catch (error) {
      BeastStore.patch('mission', { loading: false, error: String(error.message || error) });
      return null;
    }
  }

  async function actionsManifest(options = {}) {
    if (demoMode) return [];
    try {
      const payload = await fetchJson('/edgek/ide/actions/manifest', options);
      const actions = payload?.actions || payload?.items || (Array.isArray(payload) ? payload : []);
      BeastStore.set('actions', actions);
      return actions;
    } catch (_) { return []; }
  }

  function operationCommand(operation) {
    const q = value => `"${String(value || '').replace(/(["\\$`])/g, '\\$1')}"`;
    if (operation.op === 'create_file') return `touch ${q(operation.path)}`;
    if (operation.op === 'create_folder') return `mkdir -p ${q(operation.path)}`;
    if (operation.op === 'rename') return `mv ${q(operation.path)} ${q(operation.target)}`;
    if (operation.op === 'delete_file') return `rm ${q(operation.path)}`;
    return `workspace-file-op ${q(operation.path)}`;
  }

  async function classifyFileOperation(operation, options = {}) {
    if (demoMode || BeastStore.get().connection.status !== 'online') return { decision: 'warn', risk_level: 'local', reasons: [{ detail: 'Gateway unavailable or demo mode; operator confirmation required.' }] };
    return await fetchJson('/edgek/safety-governor/classify-command', { ...options, method: 'POST', body: { root_path: workspaceRoot(), command: operationCommand(operation), mode: 'operator', task_id: '', operator_override: 'Desktop IDE file mutation requires explicit operator confirmation.' } });
  }

  async function fileOperation(operation, options = {}) {
    const api = desktop();
    if (demoMode) return { ok: false, error: 'Demo workspace is read-only.' };
    if (!api?.fileOperation) throw new Error('Desktop fileOperation API is unavailable.');
    return await BeastRuntime.desktopCall('fileOperation',[workspaceRoot(), operation, options],{required:true});
  }

  async function draftSourcePlan({ path, originalText, newText, selectedHunks = [] }, options = {}) {
    if (!path) throw new Error('Select a file before drafting SourcePlan.');
    const localPreview = () => {
      const opId = `op-${Date.now().toString(36)}`;
      const changed = String(originalText || '') !== String(newText || '');
      const diff = localDiff(originalText, newText);
      return {
        ok: true,
        local: true,
        plan: {
          plan_id: `LOCAL-${Date.now().toString(36).toUpperCase()}`,
          status: changed ? 'local_preview_requires_gateway' : 'local_preview',
          path,
          operations: [{
            operation_id: opId,
            op: changed ? 'replace_file' : 'inspect_file',
            path,
            selected: true,
            risk: changed ? 'medium' : 'low',
            summary: changed
              ? 'Replace active editor buffer through governed apply.'
              : 'Inspect the active file and compile a no-op SourcePlan.'
          }],
          selected_operations: [opId]
        },
        preview_text: diff,
        preview: { operations: [{ operation_id: opId, diff_lines: diff.split('\n') }] },
        error: 'Gateway is unavailable. The diff is local preview only; no SourcePlan was verified or applied.'
      };
    };
    if (demoMode) return localPreview();
    if (BeastStore.get().connection.status !== 'online') return localPreview();
    const target=workspaceFolderForPath(path);
    try {
      const result = await fetchJson('/edgek/ide/sourceplan/from-editor', {
        ...options,
        method: 'POST', timeoutMs: options.timeoutMs || 60000,
        body: {
          root_path: target.root,
          path: target.path,
          original_text: originalText,
          new_text: newText,
          objective: `Apply governed BEAST editor changes to ${path}`,
          provider: localStorage.getItem('beast.provider') || 'nvidia_nim',
          model: localStorage.getItem('beast.model') || 'meta/llama-3.1-8b-instruct',
          selected_hunks: selectedHunks
        }
      });
      if (!result) throw new Error('Gateway returned no SourcePlan draft.');
      if (result.ok === false) {
        const fallback = localPreview();
        fallback.gatewayError = String(result.error || 'Gateway rejected the SourcePlan draft.');
        fallback.error = fallback.gatewayError;
        return fallback;
      }
      if(result.plan&&typeof result.plan==='object')result.plan.__beastWorkspaceRoot=target.root;else if(typeof result==='object')result.__beastWorkspaceRoot=target.root;
      return result;
    } catch (error) {
      const fallback = localPreview();
      fallback.gatewayError = String(error.message || error);
      fallback.error = `Gateway confirmation unavailable: ${fallback.gatewayError}`;
      return fallback;
    }
  }

  async function sourcePlanLifecycle(plan, options = {}) {
    if (!plan) return null;
    const unavailable = {
      plan_id: plan.plan_id,
      status: 'gateway_unavailable',
      can_verify: false,
      can_apply: false,
      score: 0,
      risk: 'unverified',
      stale_operations: [],
      operations: plan.operations || [],
      checks: [
        { label: 'Gateway verification', status: 'missing' },
        { label: 'Rollback receipt', status: 'missing' }
      ],
      action_contract: { requires_approval: true, evidence_closure: true, rollback_required: true }
    };
    if (demoMode || BeastStore.get().connection.status !== 'online') return unavailable;
    try {
      return await fetchJson('/edgek/ide/sourceplan/lifecycle', { ...options, method: 'POST', timeoutMs: options.timeoutMs ?? 30000, body: { root_path: plan.__beastWorkspaceRoot||workspaceRoot(), plan, verification: options.verification || null, include_verification: Boolean(options.includeVerification) } });
    } catch (error) {
      throw new Error(`SourcePlan lifecycle requires gateway confirmation: ${String(error.message || error)}`);
    }
  }

  async function verifySourcePlan(plan, options = {}) {
    if (!plan) throw new Error('No SourcePlan draft to verify.');
    if (demoMode || BeastStore.get().connection.status !== 'online') throw new Error('SourcePlan verification requires a live gateway.');
    try {
      return await fetchJson('/edgek/sourceplan/verify', { ...options, method: 'POST', timeoutMs: options.timeoutMs || 90000, body: { root_path: plan.__beastWorkspaceRoot||workspaceRoot(), plan } });
    } catch (error) {
      throw new Error(`SourcePlan verification failed: ${String(error.message || error)}`);
    }
  }

  async function applySourcePlan(plan, options = {}) {
    if (!plan) throw new Error('No SourcePlan draft to apply.');
    if (demoMode || BeastStore.get().connection.status !== 'online') throw new Error('SourcePlan apply requires a live gateway.');
    try {
      return await fetchJson('/edgek/sourceplan/apply', { ...options, method: 'POST', timeoutMs: options.timeoutMs || 90000, body: { root_path: plan.__beastWorkspaceRoot||workspaceRoot(), plan, approved: true, approval_source: options.approval_source || 'sourceplan_apply_button' } });
    } catch (error) {
      throw new Error(`SourcePlan apply failed: ${String(error.message || error)}`);
    }
  }

  async function rollbackLatestSourcePlan(options = {}) {
    if (demoMode || BeastStore.get().connection.status !== 'online') throw new Error('SourcePlan rollback requires a live gateway.');
    try {
      return await fetchJson('/edgek/sourceplan/rollback-latest', { ...options, method: 'POST', timeoutMs: options.timeoutMs || 90000, body: { root_path: workspaceRoot() } });
    } catch (error) {
      throw new Error(`SourcePlan rollback failed: ${String(error.message || error)}`);
    }
  }

  function localDiff(originalText = '', newText = '') {
    const before = String(originalText).split('\n');
    const after = String(newText).split('\n');
    const out = ['--- original', '+++ proposed'];
    const max = Math.max(before.length, after.length);
    for (let i = 0; i < max; i += 1) {
      if (before[i] === after[i]) { if (before[i] !== undefined) out.push(`  ${before[i]}`); continue; }
      if (before[i] !== undefined) out.push(`- ${before[i]}`);
      if (after[i] !== undefined) out.push(`+ ${after[i]}`);
    }
    return out.join('\n');
  }

  let desktopEventsBound = false;
  function bindDesktopEvents() {
    if (desktopEventsBound) return;
    desktopEventsBound = true;
    BeastRuntime.on('workspace', payload => {
      const root=typeof payload==='string'?payload:payload?.root;
      if (!root) return;
      if (String(root) === workspaceRoot()) { if(Array.isArray(payload?.folders))setWorkspaceFolders(payload.folders); return; }
      setRoot(root,{folders:payload?.folders||[]}); listeners.workspace.forEach(listener => listener(root));
    });
    BeastRuntime.on('refresh', () => listeners.refresh.forEach(listener => listener()));
    BeastRuntime.on('log', lines => listeners.log.forEach(listener => listener(lines)));
    BeastRuntime.bindDesktopEvents?.();
  }

  function on(type, listener) { listeners[type]?.add(listener); return () => listeners[type]?.delete(listener); }

  window.BeastDesktopBridge = {
    status, chooseWorkspace, setRoot, setWorkspaceFolders, setExecutionTarget, listExecutionTargets, refreshWorkspaceFolders, addWorkspaceFolder, removeWorkspaceFolder, listFiles, loadFile, readFile, snapshot, actionsManifest,
    inferLanguage, workspaceFolderForPath, remoteRef, parseRemoteRef, saveRemoteFile, saveTargetFile, classifyFileOperation, fileOperation, draftSourcePlan, sourcePlanLifecycle,
    verifySourcePlan, applySourcePlan, rollbackLatestSourcePlan, localDiff, bindDesktopEvents, on, fetchJson,
    get workspaceRoot() { return workspaceRoot(); }, get gatewayUrl() { return gatewayUrl(); }, get demoMode() { return demoMode; }
  };
})();
