'use strict';

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { SshForwardHost, RemoteTerminalHost, LocalTerminalHost } = require('./session-hosts');
const { createTargetSessionRegistry } = require('./target-session-registry');

function createExecutionTargetHost({
  repoRoot,
  boundedProcess,
  gitReceipt,
  readWorkspaceFile,
  safeWorkspacePath,
  taskCwd,
  workspaceFileCandidates,
  getActiveWorkspaceRoot,
}) {
  if (!repoRoot || typeof boundedProcess !== 'function' || typeof getActiveWorkspaceRoot !== 'function') {
    throw new Error('createExecutionTargetHost requires repository, process, and workspace dependencies');
  }

  function remoteTarget(value) {
    const host = String(value || '').trim();
    return /^[A-Za-z0-9][A-Za-z0-9@._:-]{0,252}$/.test(host) ? host : '';
  }

  function remotePath(value) {
    const target = String(value || '~').trim();
    if (!/^[~\/@A-Za-z0-9._+\-]+$/.test(target) || target.split('/').includes('..')) return '';
    return target;
  }

  let lastRemoteWorkspace=null;
  let activeExecutionTarget={kind:'local',label:'Local workspace',root:getActiveWorkspaceRoot()||repoRoot,transport:'local'};
  const targetSessionRegistry = createTargetSessionRegistry();
  const targetWatchers = new Map();
  let targetWatchSeq = 0;
  const targetSoakHistory = [];

  const sshForwardHost = new SshForwardHost({ repoRoot, remoteTarget });
  const remoteTerminalHost = new RemoteTerminalHost({ repoRoot, remoteTarget, remotePath, getLastRemoteWorkspace: () => lastRemoteWorkspace });
  const localTerminalHost = new LocalTerminalHost({ repoRoot, taskCwd, getActiveWorkspaceRoot: () => getActiveWorkspaceRoot() });

  function remoteSshArgs(host, remoteCommand) {
    return ['-o','BatchMode=yes','-o','ConnectTimeout=7','-o','StrictHostKeyChecking=yes',host,remoteCommand];
  }

  function shellQuote(value) { return `'${String(value ?? '').replace(/'/g, `'\\''`)}'`; }
  function containerId(value) { const id=String(value||'').trim();return /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(id)?id:''; }
  function sessionIdentity(target={}) {
    const selected = target?.kind ? target : activeExecutionTarget;
    if (selected?.kind === 'ssh') return { kind:'ssh', identity:`${selected.host}:${selected.remoteRoot || selected.path || '~'}` };
    if (selected?.kind === 'container') return { kind:'container', identity:`${selected.containerId || selected.name}:${selected.workspaceFolder || '/workspace'}` };
    return { kind:'local', identity:path.resolve(selected?.root || getActiveWorkspaceRoot() || repoRoot) };
  }
  function syncSession(target, patch={}) {
    const selected = executionTargetSummary(target);
    const identity = sessionIdentity(selected);
    return targetSessionRegistry.touch(identity.kind, identity.identity, { target:selected, transport:selected.transport, ...patch });
  }
  function executionTargetSummary(target=activeExecutionTarget) {
    const base={kind:'local',label:'Local workspace',root:getActiveWorkspaceRoot()||repoRoot,transport:'local'};
    let selected = base;
    if(target?.kind==='ssh')selected = {kind:'ssh',label:`SSH · ${target.host}`,host:target.host,path:target.path||target.remoteRoot||'~',remoteRoot:target.remoteRoot||target.path||'~',transport:'ssh'};
    else if(target?.kind==='container')selected = {kind:'container',label:`Container · ${target.name||target.containerId}`,containerId:target.containerId,name:target.name||target.containerId,root:target.root||getActiveWorkspaceRoot()||repoRoot,workspaceFolder:target.workspaceFolder||'/workspace',transport:'docker'};
    const session = targetSessionRegistry.summary(targetSessionRegistry.ensure(sessionIdentity(selected).kind, sessionIdentity(selected).identity, { label:selected.label, target:selected, transport:selected.transport }));
    return { ...selected, session };
  }
  function setActiveExecutionTarget(target={}) {
    if(target.kind==='ssh') {
      const host=remoteTarget(target.host || lastRemoteWorkspace?.host);const remoteRoot=remotePath(target.remoteRoot || target.path || lastRemoteWorkspace?.path || '~');
      if(!host||!remoteRoot)return {ok:false,error:'SSH target requires a verified host and safe remote path.',target:executionTargetSummary()};
      activeExecutionTarget={kind:'ssh',host,path:remoteRoot,remoteRoot,label:`SSH · ${host}`,transport:'ssh'};
      targetSessionRegistry.activate('ssh', `${host}:${remoteRoot}`, { label:activeExecutionTarget.label, target:activeExecutionTarget, transport:'ssh', health:'healthy' });
    } else if(target.kind==='container') {
      const id=containerId(target.containerId || target.id || target.name);const workspaceFolder=remotePath(target.workspaceFolder || target.path || '/workspace');
      if(!id||!workspaceFolder)return {ok:false,error:'Container target requires a safe container id/name and workspace folder.',target:executionTargetSummary()};
      activeExecutionTarget={kind:'container',containerId:id,name:String(target.name||id),root:path.resolve(target.root||getActiveWorkspaceRoot()||repoRoot),workspaceFolder,label:`Container · ${String(target.name||id)}`,transport:'docker'};
      targetSessionRegistry.activate('container', `${id}:${workspaceFolder}`, { label:activeExecutionTarget.label, target:activeExecutionTarget, transport:'docker', health:'healthy' });
    } else {
      activeExecutionTarget={kind:'local',label:'Local workspace',root:getActiveWorkspaceRoot()||repoRoot,transport:'local'};
      targetSessionRegistry.activate('local', path.resolve(activeExecutionTarget.root), { label:activeExecutionTarget.label, target:activeExecutionTarget, transport:'local', health:'healthy' });
    }
    return {ok:true,target:executionTargetSummary()};
  }
  async function listExecutionTargets(rootPath=getActiveWorkspaceRoot()||repoRoot) {
    const local={kind:'local',label:'Local workspace',root:path.resolve(rootPath||repoRoot),active:activeExecutionTarget.kind==='local',transport:'local'};
    const targets=[local];
    if(lastRemoteWorkspace)targets.push({...executionTargetSummary({kind:'ssh',...lastRemoteWorkspace,remoteRoot:lastRemoteWorkspace.path}),active:activeExecutionTarget.kind==='ssh'&&activeExecutionTarget.host===lastRemoteWorkspace.host});
    const containers=await inspectDevContainers(rootPath).catch(error=>({ok:false,error:String(error.message||error),containers:[]}));
    for(const item of containers.containers||[])targets.push({kind:'container',label:`Container · ${item.name||item.id}`,containerId:item.id,name:item.name,root:path.resolve(rootPath||repoRoot),workspaceFolder:containers.config?.workspaceFolder||'/workspace',status:item.status,active:activeExecutionTarget.kind==='container'&&(activeExecutionTarget.containerId===item.id||activeExecutionTarget.name===item.name),transport:'docker'});
    return {ok:true,active:executionTargetSummary(),targets,containers,sessions:targetSessionRegistry.list()};
  }
  async function runOnExecutionTarget(target, rootPath, command, args=[], options={}) {
    const selected=target?.kind ? executionTargetSummary(target) : executionTargetSummary();
    const root=path.resolve(rootPath||getActiveWorkspaceRoot()||repoRoot);
    if(selected.kind==='ssh') {
      const remoteRoot=remotePath(selected.remoteRoot||selected.path||'~');const host=remoteTarget(selected.host);
      if(!host||!remoteRoot)return {ok:false,error:'SSH execution target is not connected.'};
      syncSession(selected, { activate:true, used:true, status:'active' });
      const relative=path.relative(root,path.resolve(options.cwd||root));
      const remoteCwd=relative&&!relative.startsWith('..')&&!path.isAbsolute(relative)?`${remoteRoot.replace(/\/$/,'')}/${relative.replace(/\\/g,'/')}`:remoteRoot;
      const remoteCommand=`cd ${shellQuote(remoteCwd)} && ${[command,...args].map(shellQuote).join(' ')}`;
      const result = await boundedProcess('ssh',remoteSshArgs(host,remoteCommand),{timeoutMs:options.timeoutMs||60000,outputLimit:options.outputLimit||512000});
      syncSession(selected, { health:result.ok ? 'healthy' : 'degraded', error:result.ok ? '' : (result.stderr || result.error || 'SSH execution failed'), used:true, status:result.ok ? 'active' : 'degraded' });
      return result;
    }
    if(selected.kind==='container') {
      const id=containerId(selected.containerId||selected.name);const base=remotePath(selected.workspaceFolder||'/workspace');
      if(!id||!base)return {ok:false,error:'Container execution target is not attached.'};
      syncSession(selected, { activate:true, used:true, status:'active' });
      const relative=path.relative(root,path.resolve(options.cwd||root));
      const cwd=relative&&!relative.startsWith('..')&&!path.isAbsolute(relative)?`${base.replace(/\/$/,'')}/${relative.replace(/\\/g,'/')}`:base;
      const result = await boundedProcess('docker',['exec','-i','-w',cwd,id,command,...args],{timeoutMs:options.timeoutMs||60000,outputLimit:options.outputLimit||512000});
      syncSession(selected, { health:result.ok ? 'healthy' : 'degraded', error:result.ok ? '' : (result.stderr || result.error || 'Container execution failed'), used:true, status:result.ok ? 'active' : 'degraded' });
      return result;
    }
    syncSession(selected, { activate:true, used:true, status:'active', health:'healthy' });
    const result = await boundedProcess(command,args,{cwd:options.cwd||root,env:options.env||process.env,timeoutMs:options.timeoutMs||60000,outputLimit:options.outputLimit||512000,shell:Boolean(options.shell)});
    syncSession(selected, { health:result.ok ? 'healthy' : 'degraded', error:result.ok ? '' : (result.stderr || result.error || 'Local execution failed'), used:true, status:result.ok ? 'active' : 'degraded' });
    return result;
  }

  async function soakExecutionTarget(rootPath, payload = {}) {
    const selected = payload.target?.kind ? executionTargetSummary(payload.target) : executionTargetSummary();
    const iterations = Math.max(1, Math.min(Number(payload.iterations || 3), 20));
    const interruptEvery = Math.max(0, Math.min(Number(payload.interruptEvery || 0), iterations));
    const startedAt = Date.now();
    const rows = [];
    for (let index = 0; index < iterations; index += 1) {
      const before = Date.now();
      if (interruptEvery && index > 0 && index % interruptEvery === 0) {
        if (selected.kind === 'ssh') await reconnectRemoteWorkspace().catch(error => ({ ok:false, error:String(error.message || error) }));
        if (selected.kind === 'container') await attachDevContainer(rootPath, selected.containerId || selected.name).catch(error => ({ ok:false, error:String(error.message || error) }));
      }
      const result = await runOnExecutionTarget(selected, rootPath, 'sh', ['-lc', 'pwd && git rev-parse --show-toplevel 2>/dev/null || true && printf BEAST_TARGET_SOAK_OK'], { timeoutMs:30000, outputLimit:64000 });
      rows.push({ iteration:index + 1, ok:Boolean(result.ok), returncode:result.returncode, durationMs:Date.now() - before, interrupted:Boolean(interruptEvery && index > 0 && index % interruptEvery === 0), stdoutTail:String(result.stdout || '').slice(-1000), stderrTail:String(result.stderr || '').slice(-1000), error:result.ok ? '' : String(result.stderr || result.error || 'target soak command failed').slice(0,500) });
    }
    const digest = crypto.createHash('sha256').update(JSON.stringify({ selected, rows })).digest('hex');
    const receipt = { id:`SOAK-${digest.slice(0,16).toUpperCase()}`, digest:`sha256:${digest}`, evidence:'operator-initiated', mode:`${selected.kind}:target-soak` };
    const summary = { ok:rows.every(row => row.ok), target:selected, iterations, failures:rows.filter(row => !row.ok).length, interrupted:rows.some(row => row.interrupted), durationMs:Date.now() - startedAt, rows, receipt };
    targetSoakHistory.push({ ...summary, rows:rows.slice(-5), recordedAt:Date.now() });
    while (targetSoakHistory.length > 50) targetSoakHistory.shift();
    syncSession(selected, { status:summary.ok ? 'soak-passed' : 'soak-failed', health:summary.ok ? 'healthy' : 'degraded', metadata:{ lastSoak:receipt.id, failures:summary.failures } });
    return summary;
  }

  function targetWorkspaceBase(target, rootPath) {
    const selected = target?.kind ? executionTargetSummary(target) : executionTargetSummary();
    if (selected.kind === 'ssh') return { selected, base: remotePath(selected.remoteRoot || selected.path || '') };
    if (selected.kind === 'container') return { selected, base: remotePath(selected.workspaceFolder || '') };
    return { selected, base: path.resolve(rootPath || getActiveWorkspaceRoot() || repoRoot) };
  }
  function targetRelativePath(value) {
    const relative = String(value || '').replace(/\\/g, '/').replace(/^\/+/, '');
    if (!relative || relative === '.' || relative.split('/').some(part => !part || part === '..')) return '';
    return relative;
  }
  async function workspaceTargetListFiles(rootPath, payload={}) {
    const { selected, base } = targetWorkspaceBase(payload.target, rootPath);
    const limit = Math.max(1, Math.min(Number(payload.limit || 2000), 2000));
    if (!base) return { ok:false, error:'Execution target has no workspace folder.', files:[], target:selected };
    if (selected.kind === 'local') return { ok:true, files:workspaceFileCandidates(base, limit), target:selected };
    const command = `find ${shellQuote(base)} -maxdepth 6 -type f ! -path '*/.git/*' ! -path '*/node_modules/*' ! -path '*/.beast/*' -printf '%p\\t%s\\n' 2>/dev/null | head -n ${limit}`;
    const result = await runOnExecutionTarget(selected, rootPath, 'sh', ['-lc', command], { timeoutMs:20000, outputLimit:512000 });
    const files = String(result.stdout || '').split(/\r?\n/).filter(Boolean).map(line => { const [remoteFile,size=''] = line.split('\t'); const relative = remoteFile.startsWith(`${base.replace(/\/$/,'')}/`) ? remoteFile.slice(base.replace(/\/$/,'').length + 1) : remoteFile; return { path:relative, size:Number(size)||0, source:`execution_target_${selected.kind}`, target:selected }; }).filter(item => targetRelativePath(item.path));
    return { ...result, files, target:selected, root:base, transport:selected.transport, truncated:files.length >= limit };
  }
  async function workspaceTargetReadFile(rootPath, payload={}) {
    const { selected, base } = targetWorkspaceBase(payload.target, rootPath); const relative = targetRelativePath(payload.path); const maxChars = Math.max(1, Math.min(Number(payload.maxChars || 1000000), 2000000));
    if (!base || !relative) return { ok:false, error:'A safe workspace-relative file path is required.', path:payload.path, target:selected };
    if (selected.kind === 'local') return { ...readWorkspaceFile(base, relative, maxChars), target:selected };
    const remoteFile = `${base.replace(/\/$/,'')}/${relative}`;
    const command = `test -f ${shellQuote(remoteFile)} && head -c ${maxChars} -- ${shellQuote(remoteFile)}`;
    const result = await runOnExecutionTarget(selected, rootPath, 'sh', ['-lc', command], { timeoutMs:20000, outputLimit:maxChars + 65536 });
    const content = String(result.stdout || ''); const digest = crypto.createHash('sha256').update(content).digest('hex');
    return { ...result, path:relative, content, digest:`sha256:${digest}`, target:selected, remotePath:remoteFile, truncated:content.length >= maxChars };
  }
  async function workspaceTargetWriteFile(rootPath, payload={}) {
    const { selected, base } = targetWorkspaceBase(payload.target, rootPath); const relative = targetRelativePath(payload.path); const content = String(payload.content ?? '');
    if (!base || !relative) return { ok:false, error:'A safe workspace-relative file path is required.', path:payload.path, target:selected };
    if (Buffer.byteLength(content,'utf8') > 2000000) return { ok:false, error:'Workspace file exceeds the 2 MB write limit.', path:relative, target:selected };
    if (selected.kind === 'local') {
      const check = safeWorkspacePath(base, relative); if (!check.ok) return { ok:false, error:check.error, target:selected };
      const expected = String(payload.expectedDigest || ''); if (expected) { let before=''; try { before=fs.readFileSync(check.target,'utf8'); } catch (_) { return {ok:false,conflict:true,error:'File changed or no longer exists.',target:selected}; } const actual=`sha256:${crypto.createHash('sha256').update(before).digest('hex')}`; if (actual !== expected) return {ok:false,conflict:true,error:'File changed since it was opened. Reload before saving.',expectedDigest:expected,actualDigest:actual,target:selected}; }
      fs.mkdirSync(path.dirname(check.target), {recursive:true}); fs.writeFileSync(check.target, content, 'utf8'); const digest=`sha256:${crypto.createHash('sha256').update(content).digest('hex')}`; return {ok:true,path:relative,digest,target:selected,receipt:gitReceipt(base,'write-file',relative,{stdout:content,stderr:'',returncode:0})};
    }
    const remoteFile = `${base.replace(/\/$/,'')}/${relative}`; const expected = String(payload.expectedDigest || '').replace(/^sha256:/,'');
    if (expected) { const verify = await runOnExecutionTarget(selected, rootPath, 'sh', ['-lc', `test -f ${shellQuote(remoteFile)} && sha256sum -- ${shellQuote(remoteFile)}`], {timeoutMs:20000,outputLimit:32000}); const actual=String(verify.stdout||'').trim().match(/^([a-f0-9]{64})\b/i)?.[1]?.toLowerCase() || ''; if (!verify.ok || actual !== expected.toLowerCase()) return {ok:false,conflict:true,error:'Remote file changed since it was opened. Reload before saving.',expectedDigest:`sha256:${expected}`,actualDigest:actual?`sha256:${actual}`:'',target:selected}; }
    const encoded=Buffer.from(content,'utf8').toString('base64'); const parent=path.posix.dirname(remoteFile); const command=`mkdir -p ${shellQuote(parent)} && tmp=$(mktemp ${shellQuote(`${parent}/.beast-write.XXXXXX`)}) && printf %s ${shellQuote(encoded)} | base64 -d > "$tmp" && mv -f "$tmp" ${shellQuote(remoteFile)}`; const result=await runOnExecutionTarget(selected, rootPath, 'sh', ['-lc', command], {timeoutMs:20000,outputLimit:32000}); const digest=`sha256:${crypto.createHash('sha256').update(content).digest('hex')}`; return {...result,path:relative,remotePath:remoteFile,digest,target:selected,atomic:Boolean(result.ok),receipt:result.ok?gitReceipt(base,'write-file',relative,result):null};
  }

  function parseTargetWatchSnapshot(text) {
    const rows = new Map();
    for (const line of String(text || '').split(/\r?\n/)) {
      if (!line) continue;
      const [file, size = '', mtime = ''] = line.split('\t');
      const relative = targetRelativePath(file);
      if (!relative) continue;
      rows.set(relative, { path:relative, size:Number(size)||0, mtime:Number(mtime)||0 });
      if (rows.size >= 2000) break;
    }
    return rows;
  }
  function targetWatchDiff(previous, next) {
    const events = [];
    for (const [pathKey, row] of next.entries()) {
      const before = previous.get(pathKey);
      if (!before) events.push({ eventType:'created', path:pathKey, size:row.size, mtime:row.mtime });
      else if (before.size !== row.size || before.mtime !== row.mtime) events.push({ eventType:'changed', path:pathKey, size:row.size, mtime:row.mtime });
      if (events.length >= 300) return events;
    }
    for (const pathKey of previous.keys()) {
      if (!next.has(pathKey)) events.push({ eventType:'deleted', path:pathKey });
      if (events.length >= 300) return events;
    }
    return events;
  }
  async function targetWatchSnapshot(rootPath, selected, base, limit) {
    if (selected.kind === 'local') {
      const root = path.resolve(base || rootPath || getActiveWorkspaceRoot() || repoRoot);
      const rows = new Map();
      for (const item of workspaceFileCandidates(root, limit)) rows.set(item.path.replace(/\\/g, '/'), { path:item.path.replace(/\\/g, '/'), size:Number(item.size)||0, mtime:Number(item.mtimeMs)||0 });
      return { ok:true, rows, stdout:'', stderr:'' };
    }
    const command = `cd ${shellQuote(base)} && find . -maxdepth 8 -type f ! -path './.git/*' ! -path './node_modules/*' ! -path './.beast/*' ! -path './.venv/*' ! -path './venv/*' -printf '%P\\t%s\\t%T@\\n' 2>/dev/null | head -n ${limit}`;
    const result = await runOnExecutionTarget(selected, rootPath, 'sh', ['-lc', command], { timeoutMs:20000, outputLimit:512000 });
    return { ...result, rows:parseTargetWatchSnapshot(result.stdout) };
  }
  function workspaceTargetStartWatch(rootPath, sender, payload = {}) {
    const { selected, base } = targetWorkspaceBase(payload.target, rootPath);
    if (!base) return { ok:false, error:'Execution target has no workspace folder.', target:selected };
    const id = `target-watch-${++targetWatchSeq}`;
    const intervalMs = Math.max(1000, Math.min(Number(payload.intervalMs || 2500), 30000));
    const limit = Math.max(100, Math.min(Number(payload.limit || 2000), 2000));
    const root = path.resolve(rootPath || getActiveWorkspaceRoot() || repoRoot);
    const session = syncSession(selected, { status:'watching', used:true, metadata:{ watcherCount:targetWatchers.size + 1 } });
    const watcher = { id, root, base, selected, intervalMs, limit, timer:null, running:false, stopped:false, snapshot:new Map(), initialized:false, sessionId:session?.sessionId || '' };
    const emit = message => {
      if (sender?.isDestroyed?.()) {
        workspaceTargetStopWatch(id);
        return;
      }
      sender?.send?.('beast:workspace-watch-event', { id, root, target:selected.kind, executionTarget:selected, sessionId:watcher.sessionId, at:Date.now(), ...message });
    };
    const tick = async () => {
      if (watcher.stopped || watcher.running) return;
      watcher.running = true;
      try {
        const next = await targetWatchSnapshot(root, selected, base, limit);
        if (!next.ok) {
          emit({ error:String(next.stderr || next.error || 'Target watch snapshot failed.'), mode:'target_polling_watch' });
          syncSession(selected, { health:'degraded', status:'watching', error:next.stderr || next.error || 'Target watch snapshot failed.' });
        } else if (!watcher.initialized) {
          watcher.snapshot = next.rows;
          watcher.initialized = true;
          emit({ eventType:'ready', path:'', mode:'target_polling_watch', files:next.rows.size, truncated:next.rows.size >= limit });
          syncSession(selected, { health:'healthy', status:'watching', used:true });
        } else {
          const events = targetWatchDiff(watcher.snapshot, next.rows);
          watcher.snapshot = next.rows;
          for (const event of events) emit({ ...event, mode:'target_polling_watch', truncated:events.length >= 300 || next.rows.size >= limit });
          if (events.length) syncSession(selected, { health:'healthy', status:'watching', used:true, metadata:{ lastWatchEvents:events.length } });
        }
      } catch (error) {
        emit({ error:String(error.message || error), mode:'target_polling_watch' });
        syncSession(selected, { health:'degraded', status:'watching', error:String(error.message || error) });
      } finally {
        watcher.running = false;
      }
    };
    targetWatchers.set(id, watcher);
    watcher.timer = setInterval(tick, intervalMs);
    tick();
    return { ok:true, id, root, target:selected.kind, executionTarget:selected, sessionId:watcher.sessionId, mode:'target_polling_watch', intervalMs, limit };
  }
  function workspaceTargetStopWatch(id) {
    const watcher = targetWatchers.get(String(id || ''));
    if (!watcher) return { ok:false, stopped:false };
    watcher.stopped = true;
    clearInterval(watcher.timer);
    targetWatchers.delete(watcher.id);
    syncSession(watcher.selected, { status:'active', metadata:{ watcherCount:targetWatchers.size } });
    return { ok:true, stopped:true, id:watcher.id, target:watcher.selected.kind, executionTarget:watcher.selected, sessionId:watcher.sessionId };
  }

  async function probeRemoteWorkspace(payload = {}) {
    const host = remoteTarget(payload.host); const target = remotePath(payload.path || '~');
    if (!host || !target) return { ok:false, error:'Remote host or path contains unsupported characters.' };
    const result = await boundedProcess('ssh',remoteSshArgs(host,`test -d ${target} && printf 'BEAST_REMOTE_READY\\n' && cd ${target} && pwd`),{ timeoutMs:10000, outputLimit:32000 });
    const lines=String(result.stdout || '').trim().split(/\r?\n/);
    const resolved=lines.find(line => line && line !== 'BEAST_REMOTE_READY') || '';
    const summary={ ...result, host, path:target, remote_root:resolved, transport:'ssh', verification:'strict-known-host' };
    if(summary.ok){
      lastRemoteWorkspace={host,path:resolved || target};
      targetSessionRegistry.touch('ssh', `${host}:${resolved || target}`, { label:`SSH · ${host}`, target:{kind:'ssh',host,remoteRoot:resolved || target,path:resolved || target,transport:'ssh'}, transport:'ssh', health:'healthy', status:'connected', activate:true });
      summary.target=setActiveExecutionTarget({kind:'ssh',host,remoteRoot:resolved||target}).target;
    } else {
      targetSessionRegistry.touch('ssh', `${host}:${target}`, { label:`SSH · ${host}`, target:{kind:'ssh',host,remoteRoot:target,path:target,transport:'ssh'}, transport:'ssh', health:'degraded', status:'disconnected', error:summary.stderr || summary.error || 'SSH probe failed' });
    }
    summary.session = targetSessionRegistry.summary(targetSessionRegistry.ensure('ssh', `${host}:${resolved || target}`, { label:`SSH · ${host}`, transport:'ssh' }));
    return summary;
  }

  async function listRemoteWorkspaceFiles(payload = {}) {
    const host = remoteTarget(payload.host); const target = remotePath(payload.path || '~');
    if (!host || !target) return { ok:false, error:'Remote host or path contains unsupported characters.', files:[] };
    const command=`find ${target} -maxdepth 3 -type f -printf '%p\\t%s\\n' 2>/dev/null | head -n 500`;
    const result=await boundedProcess('ssh',remoteSshArgs(host,command),{timeoutMs:15000,outputLimit:256000});
    const files=String(result.stdout || '').split(/\r?\n/).filter(Boolean).map(line=>{const [file,size='']=line.split('\t');return {path:file,size:Number(size)||0};});
    return { ...result, host, path:target, files, transport:'ssh' };
  }

  async function searchRemoteWorkspace(payload={}) {
    const host=remoteTarget(payload.host || lastRemoteWorkspace?.host);const target=remotePath(payload.path || lastRemoteWorkspace?.path || '~');const query=String(payload.query || '').trim();
    if(!host||!target||!query||Buffer.byteLength(query,'utf8')>600||/[\r\n\0]/.test(query))return {ok:false,error:'Remote search requires a connected host and 1–600 bytes of single-line text.',results:[]};
    const encoded=Buffer.from(query,'utf8').toString('base64');const command=`cd ${target} && needle=$(printf %s ${encoded} | base64 -d) && grep -RInF --binary-files=without-match --exclude-dir=.git --exclude-dir=.beast --exclude-dir=node_modules --exclude-dir=.venv -- "$needle" . 2>/dev/null | head -n 300`;
    const result=await boundedProcess('ssh',remoteSshArgs(host,command),{timeoutMs:15000,outputLimit:320000});const results=String(result.stdout||'').split(/\r?\n/).filter(Boolean).map(line=>{const match=line.match(/^(.*?):([0-9]+):(.*)$/);if(!match)return null;const relative=match[1].replace(/^\.\//,'');const file=remotePath(`${target.replace(/\/$/,'')}/${relative}`);return file?{path:file,line:Number(match[2])||0,preview:match[3].slice(0,900)}:null;}).filter(Boolean).slice(0,300);
    return {...result,ok:result.ok||result.returncode===1,host,path:target,query,results,transport:'ssh',verification:'strict-known-host',truncated:results.length>=300};
  }

  async function reconnectRemoteWorkspace() {
    if(!lastRemoteWorkspace)return {ok:false,error:'No verified remote workspace is available to reconnect.'};
    const result = await probeRemoteWorkspace(lastRemoteWorkspace);
    if (result.ok) {
      targetSessionRegistry.touch('ssh', `${result.host}:${result.remote_root || result.path}`, { reconnected:true, health:'healthy', status:'connected', activate:true });
    }
    return result;
  }
  async function remoteWorkspaceHealth(payload={}) { const host=remoteTarget(payload.host||lastRemoteWorkspace?.host);const target=remotePath(payload.path||lastRemoteWorkspace?.path||'~');if(!host||!target)return {ok:false,error:'Remote health requires a verified SSH host and workspace path.',tools:{}};const command=`cd ${shellQuote(target)} && printf 'PWD\\t%s\\n' "$PWD" && for tool in node git python3 ssh; do if command -v "$tool" >/dev/null 2>&1; then printf '%s\\t%s\\n' "$tool" "$(command -v "$tool")"; else printf '%s\\t\\n' "$tool"; fi; done && if command -v node >/dev/null 2>&1; then printf 'NODE_VERSION\\t%s\\n' "$(node --version)"; fi`;const result=await boundedProcess('ssh',remoteSshArgs(host,command),{timeoutMs:15000,outputLimit:64000});const tools={};let workspace='';let nodeVersion='';for(const line of String(result.stdout||'').split(/\r?\n/)){const [key,value='']=line.split('\t');if(key==='PWD')workspace=value;if(key==='NODE_VERSION')nodeVersion=value;else if(['node','git','python3','ssh'].includes(key))tools[key]={available:Boolean(value),path:value};}return {...result,ok:result.ok,host,path:target,workspace,nodeVersion,tools,transport:'ssh',verification:'strict-known-host',healthy:Boolean(result.ok&&workspace&&tools.ssh?.available)}; }
  async function readRemoteWorkspaceFile(payload={}) { const host=remoteTarget(payload.host || lastRemoteWorkspace?.host);const target=remotePath(payload.path || '');if(!host||!target)return {ok:false,error:'Remote host or file path contains unsupported characters.'};const result=await boundedProcess('ssh',remoteSshArgs(host,`test -f ${shellQuote(target)} && head -c 200000 -- ${shellQuote(target)}`),{timeoutMs:15000,outputLimit:220000});const content=String(result.stdout||'');const digest=crypto.createHash('sha256').update(content).digest('hex');return {...result,host,path:target,content,digest:`sha256:${digest}`,transport:'ssh',verification:'strict-known-host'}; }
  async function writeRemoteWorkspaceFile(payload={}) { const host=remoteTarget(payload.host || lastRemoteWorkspace?.host);const target=remotePath(payload.path || '');const content=String(payload.content || '');const expectedDigest=String(payload.expectedDigest||'').replace(/^sha256:/,'');if(!host||!target)return {ok:false,error:'Remote host or file path contains unsupported characters.'};if(Buffer.byteLength(content,'utf8')>200000)return {ok:false,error:'Remote file exceeds the 200 KiB write limit.'};if(expectedDigest&&!/^[a-f0-9]{64}$/i.test(expectedDigest))return {ok:false,error:'Remote expected digest must be a SHA-256 value.',host,path:target};if(expectedDigest){const current=await boundedProcess('ssh',remoteSshArgs(host,`test -f ${shellQuote(target)} && sha256sum -- ${shellQuote(target)}`),{timeoutMs:15000,outputLimit:32000});const actual=String(current.stdout||'').trim().match(/^([a-f0-9]{64})\b/i)?.[1]?.toLowerCase()||'';if(!current.ok||actual!==expectedDigest.toLowerCase())return {ok:false,conflict:true,error:'Remote file changed since it was opened. Reload or compare before saving.',host,path:target,expectedDigest:`sha256:${expectedDigest}`,actualDigest:actual?`sha256:${actual}`:'',transport:'ssh',verification:'strict-known-host'};}const encoded=Buffer.from(content,'utf8').toString('base64');const parent=path.posix.dirname(target);const command=`mkdir -p ${shellQuote(parent)} && tmp=$(mktemp ${shellQuote(`${parent}/.beast-write.XXXXXX`)}) && printf %s ${shellQuote(encoded)} | base64 -d > "$tmp" && mv -f "$tmp" ${shellQuote(target)}`;const result=await boundedProcess('ssh',remoteSshArgs(host,command),{timeoutMs:15000,outputLimit:32000});const digest=crypto.createHash('sha256').update(content).digest('hex');return {...result,host,path:target,digest:`sha256:${digest}`,transport:'ssh',verification:'strict-known-host',atomic:Boolean(result.ok),receipt:result.ok?{id:`RFS-${digest.slice(0,16).toUpperCase()}`,digest:`sha256:${digest}`,evidence:'operator-initiated'}:null}; }
  async function runRemoteTerminal(payload={}) { const host=remoteTarget(payload.host || lastRemoteWorkspace?.host);const command=String(payload.command || '').trim();if(!host||!command||Buffer.byteLength(command,'utf8')>16000)return {ok:false,error:'Remote host or command is outside allowed bounds.'};const result=await boundedProcess('ssh',remoteSshArgs(host,command),{timeoutMs:Math.max(1000,Math.min(Number(payload.timeoutMs||30000),60000)),outputLimit:512000});const digest=crypto.createHash('sha256').update(`${host}\n${command}\n${result.stdout}\n${result.stderr}\n${result.returncode}`).digest('hex');return {...result,host,command,transport:'ssh',verification:'strict-known-host',receipt:{id:`RTERM-${digest.slice(0,16).toUpperCase()}`,digest:`sha256:${digest}`,evidence:'operator-initiated'}}; }
  function devContainerConfig(rootPath) { const root=path.resolve(rootPath||repoRoot);const file=path.join(root,'.devcontainer','devcontainer.json');try{const raw=JSON.parse(fs.readFileSync(file,'utf8'));const image=String(raw?.image||'');if(image&&!/^[A-Za-z0-9][A-Za-z0-9._/:@-]{0,255}$/.test(image))return {ok:false,error:'Dev container image is outside allowed syntax.'};const composeEntries=(Array.isArray(raw?.dockerComposeFile)?raw.dockerComposeFile:[raw?.dockerComposeFile]).filter(Boolean).map(value=>String(value));const composeFiles=[];for(const entry of composeEntries){if(!/^[A-Za-z0-9._/-]{1,240}$/.test(entry))return {ok:false,error:'Dev container compose file contains unsupported characters.'};const target=path.resolve(path.dirname(file),entry);if(!(target===root||target.startsWith(`${root}${path.sep}`))||!fs.existsSync(target))return {ok:false,error:`Dev container compose file was not found in this workspace: ${entry}`};composeFiles.push(target);}const service=String(raw?.service||'').trim();if(composeFiles.length&&!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,120}$/.test(service))return {ok:false,error:'Compose dev containers require a safe service name.'};return {ok:true,root,file,config:{name:String(raw?.name||path.basename(root)).slice(0,120),image,workspaceFolder:String(raw?.workspaceFolder||`/workspaces/${path.basename(root)}`).slice(0,240),dockerFile:Boolean(raw?.dockerFile),compose:composeFiles.length>0,composeFiles,service}};}catch(_){return {ok:false,error:'No readable .devcontainer/devcontainer.json exists in this workspace.'};} }
  function composeArgs(state, command, extra=[]) { return ['compose','--project-directory',state.root,...state.config.composeFiles.flatMap(file=>['-f',file]),command,...extra]; }
  function parseDevContainerRows(text, managed) { return String(text||'').split(/\r?\n/).filter(Boolean).map(line=>{const [id,name,image,status]=line.split('\t');return {id,name,image,status,managed};}); }
  async function devContainerPorts(id) { const result=await boundedProcess('docker',['port',String(id||'')],{timeoutMs:8000,outputLimit:32000});if(!result.ok)return [];const seen=new Set();return String(result.stdout||'').split(/\r?\n/).map(line=>{const match=line.match(/^(\d+)\/(tcp|udp)\s+->\s+(?:0\.0\.0\.0|127\.0\.0\.1|\[::\]|::):([0-9]+)$/i);if(!match||match[2].toLowerCase()!=='tcp')return null;const containerPort=Number(match[1]);const hostPort=Number(match[3]);if(!Number.isInteger(containerPort)||!Number.isInteger(hostPort)||containerPort<1||containerPort>65535||hostPort<1||hostPort>65535)return null;const key=`${containerPort}:${hostPort}`;if(seen.has(key))return null;seen.add(key);return {containerPort,hostPort,protocol:'tcp',url:`http://127.0.0.1:${hostPort}`};}).filter(Boolean).slice(0,32); }
  async function inspectDevContainers(rootPath) { const config=devContainerConfig(rootPath);if(!config.ok)return {...config,containers:[]};const workspaceKey=crypto.createHash('sha256').update(config.root).digest('hex').slice(0,20);const result=config.config.compose?await boundedProcess('docker',composeArgs(config,'ps',['-a','--format','{{.ID}}\t{{.Name}}\t{{.Image}}\t{{.Status}}']),{timeoutMs:20000,outputLimit:128000}):await boundedProcess('docker',['ps','-a','--filter',`label=beast.workspace=${workspaceKey}`,'--format','{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}'],{timeoutMs:10000,outputLimit:64000});const containers=await Promise.all(parseDevContainerRows(result.stdout, !config.config.compose).map(async container=>({...container,ports:await devContainerPorts(container.id)})));for(const container of containers){targetSessionRegistry.touch('container', `${container.id}:${config.config.workspaceFolder}`, { label:`Container · ${container.name||container.id}`, target:{kind:'container',containerId:container.id,name:container.name,root:config.root,workspaceFolder:config.config.workspaceFolder,transport:'docker'}, transport:'docker', health:/\bUp\b|\brunning\b/i.test(container.status)?'healthy':'idle', status:/\bUp\b|\brunning\b/i.test(container.status)?'connected':'inactive', metadata:{status:container.status,ports:container.ports||[]} });}return {...config,ok:result.ok,containers,error:result.ok?'':String(result.stderr||'Docker inspection failed.').trim(),workspaceKey,sessions:targetSessionRegistry.list('container')}; }
  async function startDevContainer(rootPath) { const state=await inspectDevContainers(rootPath);if(!state.ok) return state;const running=state.containers.find(item=>/\bUp\b|\brunning\b/i.test(item.status));if(running)return {...state,attached:running,target:setActiveExecutionTarget({kind:'container',containerId:running.id,name:running.name,root:state.root,workspaceFolder:state.config.workspaceFolder}).target};let result;if(state.config.compose)result=await boundedProcess('docker',composeArgs(state,'up',['-d',state.config.service]),{timeoutMs:180000,outputLimit:128000});else {if(!state.config.image)return {...state,ok:false,error:'Dev container start requires image, Dockerfile, or dockerComposeFile.'};const name=`beast-dev-${state.workspaceKey}`;result=await boundedProcess('docker',['run','-d','--rm','--name',name,'--label',`beast.workspace=${state.workspaceKey}`,'--label','beast.managed=true','-v',`${state.root}:${state.config.workspaceFolder}`,'-w',state.config.workspaceFolder,state.config.image,'sleep','infinity'],{timeoutMs:120000,outputLimit:64000});}if(!result.ok)return {...state,ok:false,error:String(result.stderr||'Dev container start failed.').trim()};const next=await inspectDevContainers(state.root);const attached=next.containers.find(item=>/\bUp\b|\brunning\b/i.test(item.status))||next.containers[0];return {...next,attached,target:attached?setActiveExecutionTarget({kind:'container',containerId:attached.id,name:attached.name,root:state.root,workspaceFolder:state.config.workspaceFolder}).target:executionTargetSummary()}; }
  async function stopDevContainer(rootPath,id) { const state=await inspectDevContainers(rootPath);const target=state.containers.find(item=>item.id===String(id||'')||item.name===String(id||''));if(!target)return {...state,ok:false,error:'Only the selected workspace dev container can be stopped.'};const result=state.config.compose?await boundedProcess('docker',composeArgs(state,'stop',[state.config.service]),{timeoutMs:60000,outputLimit:64000}):await boundedProcess('docker',['stop',target.id],{timeoutMs:30000,outputLimit:32000});if(result.ok)targetSessionRegistry.deactivate('container', `${target.id}:${state.config.workspaceFolder}`, { status:'stopped', health:'idle' });return result.ok?inspectDevContainers(rootPath):{...state,ok:false,error:String(result.stderr||'Dev container stop failed.').trim()}; }
  async function restartDevContainer(rootPath,id) { const state=await inspectDevContainers(rootPath);const target=state.containers.find(item=>item.id===String(id||'')||item.name===String(id||''))||state.containers.find(item=>/\bUp\b|\brunning\b/i.test(item.status))||state.containers[0];if(!target)return {...state,ok:false,error:'No workspace dev container is available to restart.'};const stopped=await stopDevContainer(rootPath,target.id);if(!stopped.ok)return {...stopped,restarted:false};const started=await startDevContainer(rootPath);return {...started,restarted:Boolean(started.ok),previousContainer:target}; }
  async function attachDevContainer(rootPath,id) { const state=await inspectDevContainers(rootPath);if(!state.ok)return state;const target=state.containers.find(item=>item.id===String(id||'')||item.name===String(id||''))||state.containers.find(item=>/\bUp\b/i.test(item.status))||state.containers[0];if(!target)return {...state,ok:false,error:'No BEAST-managed dev container is available to attach.'};return {...state,attached:target,target:setActiveExecutionTarget({kind:'container',containerId:target.id,name:target.name,root:state.root,workspaceFolder:state.config.workspaceFolder}).target}; }
  async function rebuildDevContainer(rootPath) { const state=devContainerConfig(rootPath);if(!state.ok)return {...state,containers:[]};let result;if(state.config.compose)result=await boundedProcess('docker',composeArgs(state,'up',['-d','--build',state.config.service]),{timeoutMs:600000,outputLimit:512000});else if(state.config.dockerFile){const dockerfile=path.join(state.root,'.devcontainer','Dockerfile');if(!fs.existsSync(dockerfile))return {...state,ok:false,error:'devcontainer.json references a Dockerfile but .devcontainer/Dockerfile was not found.'};const tag=`beast-dev-image-${crypto.createHash('sha256').update(state.root).digest('hex').slice(0,20)}`;result=await boundedProcess('docker',['build','-t',tag,'-f',dockerfile,state.root],{timeoutMs:600000,outputLimit:512000});if(result.ok)state.config.image=tag;}else if(state.config.image)result=await boundedProcess('docker',['pull',state.config.image],{timeoutMs:600000,outputLimit:512000});else return {...state,ok:false,error:'Dev container rebuild requires image, Dockerfile, or dockerComposeFile.'};return result.ok?startDevContainer(state.root):{...state,ok:false,error:String(result.stderr||'Dev container rebuild failed.').trim(),stdout:result.stdout,stderr:result.stderr}; }
  async function devContainerLogs(rootPath,id) { const state=await inspectDevContainers(rootPath);const target=state.containers.find(item=>item.id===String(id||'')||item.name===String(id||''))||state.containers[0];if(!target)return {...state,ok:false,error:'No workspace dev container is available for logs.',logs:''};const result=state.config.compose?await boundedProcess('docker',composeArgs(state,'logs',['--tail','300',state.config.service]),{timeoutMs:30000,outputLimit:256000}):await boundedProcess('docker',['logs','--tail','300',target.id],{timeoutMs:15000,outputLimit:256000});return {...result,container:target,logs:`${result.stdout||''}${result.stderr||''}`.slice(-256000)}; }
  async function runDevContainerTerminal(rootPath,payload={}) { const state=await inspectDevContainers(rootPath);const target=state.containers.find(item=>item.id===String(payload.id||'')||item.name===String(payload.id||''))||state.containers.find(item=>/\bUp\b/i.test(item.status))||state.containers[0];const command=String(payload.command||'').trim();if(!target)return {...state,ok:false,error:'No BEAST-managed dev container is available for terminal execution.'};if(!command||Buffer.byteLength(command,'utf8')>16000||/[\0]/.test(command))return {...state,ok:false,error:'Container terminal command must be 1–16000 bytes.'};const result=await boundedProcess('docker',['exec','-i','-w',state.config.workspaceFolder,target.id,'sh','-lc',command],{timeoutMs:Math.max(1000,Math.min(Number(payload.timeoutMs||30000),120000)),outputLimit:512000});const digest=crypto.createHash('sha256').update(`${target.id}\n${command}\n${result.stdout}\n${result.stderr}\n${result.returncode}`).digest('hex');return {...result,container:target,transport:'docker-exec',receipt:{id:`DCTR-${digest.slice(0,16).toUpperCase()}`,digest:`sha256:${digest}`,evidence:'operator-initiated'}}; }

  function getActiveExecutionTarget() { return executionTargetSummary(); }
  function targetSessions() { return targetSessionRegistry.list(); }
  function targetSoakSummary() { return { ok:true, soaks:targetSoakHistory.slice().reverse(), counts:{soaks:targetSoakHistory.length, failures:targetSoakHistory.filter(item=>!item.ok).length} }; }
  function shutdown() {
    for (const id of [...targetWatchers.keys()]) workspaceTargetStopWatch(id);
    sshForwardHost.stopAll();
    remoteTerminalHost.stopAll();
    localTerminalHost.stopAll();
  }

  return {
    remoteTarget,
    remotePath,
    remoteSshArgs,
    shellQuote,
    containerId,
    executionTargetSummary,
    targetSessions,
    getActiveExecutionTarget,
    setActiveExecutionTarget,
    listExecutionTargets,
    runOnExecutionTarget,
    soakExecutionTarget,
    targetSoakSummary,
    targetWorkspaceBase,
    targetRelativePath,
    workspaceTargetListFiles,
    workspaceTargetReadFile,
    workspaceTargetWriteFile,
    workspaceTargetStartWatch,
    workspaceTargetStopWatch,
    probeRemoteWorkspace,
    listRemoteWorkspaceFiles,
    searchRemoteWorkspace,
    reconnectRemoteWorkspace,
    remoteWorkspaceHealth,
    readRemoteWorkspaceFile,
    writeRemoteWorkspaceFile,
    runRemoteTerminal,
    devContainerConfig,
    composeArgs,
    parseDevContainerRows,
    devContainerPorts,
    inspectDevContainers,
    startDevContainer,
    stopDevContainer,
    restartDevContainer,
    attachDevContainer,
    rebuildDevContainer,
    devContainerLogs,
    runDevContainerTerminal,
    sshForwardHost,
    remoteTerminalHost,
    localTerminalHost,
    shutdown,
  };
}

module.exports = { createExecutionTargetHost };
