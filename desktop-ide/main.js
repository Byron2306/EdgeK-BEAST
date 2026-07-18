const { app, BrowserWindow, Menu, dialog, ipcMain, shell, screen } = require('electron');
const { spawn, spawnSync } = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const http = require('http');
const net = require('net');
const os = require('os');
const path = require('path');
const yaml = require('js-yaml');
const { IdeCompatibilityHost } = require('./ide-compatibility-host');

const DESKTOP_IDE_VERSION = '0.1.2-enterprise-control-plane';

const DEFAULT_WINDOW_BOUNDS = Object.freeze({ width: 1560, height: 980, minWidth: 1180, minHeight: 760 });
let windowStateWriteTimer = null;

function windowStatePath() { return path.join(app.getPath('userData'), 'beast-desktop-window-state.json'); }
function workspaceFoldersStatePath() { return path.join(app.getPath('userData'), 'beast-desktop-workspace-folders.json'); }
function readWindowState() {
  try {
    const raw = JSON.parse(fs.readFileSync(windowStatePath(), 'utf8'));
    const width = Math.max(DEFAULT_WINDOW_BOUNDS.minWidth, Number(raw.width) || DEFAULT_WINDOW_BOUNDS.width);
    const height = Math.max(DEFAULT_WINDOW_BOUNDS.minHeight, Number(raw.height) || DEFAULT_WINDOW_BOUNDS.height);
    const candidate = { width, height, x: Number.isFinite(raw.x) ? raw.x : undefined, y: Number.isFinite(raw.y) ? raw.y : undefined, maximized: Boolean(raw.maximized) };
    const visible = screen.getAllDisplays().some(display => {
      const area = display.workArea; const x = candidate.x ?? area.x; const y = candidate.y ?? area.y;
      return x + Math.min(width, 80) > area.x && x < area.x + area.width && y + Math.min(height, 80) > area.y && y < area.y + area.height;
    });
    return visible ? candidate : { width, height, maximized: candidate.maximized };
  } catch (_) { return { ...DEFAULT_WINDOW_BOUNDS, maximized: false }; }
}
function persistWindowState(windowRef) {
  if (!windowRef || windowRef.isDestroyed()) return;
  const bounds = windowRef.isMaximized() ? windowRef.getNormalBounds() : windowRef.getBounds();
  const state = { x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height, maximized: windowRef.isMaximized() };
  try { fs.mkdirSync(path.dirname(windowStatePath()), { recursive: true }); fs.writeFileSync(windowStatePath(), JSON.stringify(state)); } catch (error) { appendLog(`window state persistence failed: ${error.message || error}`); }
}
function scheduleWindowStatePersist(windowRef) {
  clearTimeout(windowStateWriteTimer);
  windowStateWriteTimer = setTimeout(() => persistWindowState(windowRef), 220);
}

function resolveRepoRoot() {
  const candidates = [
    process.env.BEAST_REPO_ROOT,
    process.env.BEAST_WORKSPACE,
    process.cwd(),
    path.resolve(__dirname, '..'),
    path.resolve(__dirname, '..', '..', '..', '..'),
    path.resolve(__dirname, '..', '..', '..', '..', '..'),
  ].filter(Boolean);
  for (const candidate of candidates) {
    const root = path.resolve(candidate);
    if (fs.existsSync(path.join(root, 'bin', 'beast')) && fs.existsSync(path.join(root, 'app', 'main.py'))) {
      return root;
    }
  }
  return path.resolve(__dirname, '..');
}

const repoRoot = resolveRepoRoot();
const ideCompatibilityHost = new IdeCompatibilityHost(repoRoot);
function runtimeResourcePath(...parts) {
  const resource = process.resourcesPath ? path.join(process.resourcesPath,...parts) : '';
  return resource && fs.existsSync(resource) ? resource : path.join(__dirname,...parts);
}
function pythonToolRoot() {
  const resource = process.resourcesPath ? path.join(process.resourcesPath,'python-tools') : '';
  return resource && fs.existsSync(resource) ? resource : path.join(__dirname,'.beast-python-tools');
}
class NotebookKernelHost {
  constructor() { this.session=null; this.sequence=0; }
  summary() { const s=this.session; return { status:s?.status || 'stopped', pid:s?.process?.pid || null, root:s?.root || '', kernel:'beast-python' }; }
  emit(message) { const sender=this.session?.sender; if (sender && !sender.isDestroyed()) sender.send('beast:notebook-kernel-message',message); }
  start(root, sender) {
    const workspace=path.resolve(root || repoRoot);
    if (this.session?.status === 'running' && this.session.root === workspace) return this.summary();
    this.stop();
    const tools=pythonToolRoot(); const ipythonDir=path.join(os.tmpdir(),'beast-ide-ipython');
    try { fs.mkdirSync(ipythonDir,{recursive:true}); } catch (_) {}
    const processRef=spawn('python3',[runtimeResourcePath('scripts','notebook-kernel-relay.py')],{cwd:workspace,env:{...process.env,PYTHONPATH:[tools,process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),JUPYTER_PATH:path.join(tools,'share','jupyter'),IPYTHONDIR:ipythonDir,BEAST_ACTIVE_WORKSPACE:workspace,BEAST_JUPYTER_KERNEL:'beast-python'},stdio:['pipe','pipe','pipe'],shell:false,windowsHide:true});
    const session={process:processRef,sender,root:workspace,status:'starting',buffer:'',pending:new Map()};this.session=session;
    const rejectAll=error=>{for(const pending of session.pending.values()){clearTimeout(pending.timer);pending.reject(error);}session.pending.clear();};
    processRef.stdout.on('data',chunk=>{session.buffer+=String(chunk);let cut;while((cut=session.buffer.indexOf('\n'))>=0){const line=session.buffer.slice(0,cut);session.buffer=session.buffer.slice(cut+1);if(!line.trim())continue;try{const message=JSON.parse(line);if(message.id!=null&&session.pending.has(message.id)){const pending=session.pending.get(message.id);session.pending.delete(message.id);clearTimeout(pending.timer);message.ok===false?pending.reject(new Error(message.error||'kernel request failed')):pending.resolve(message);}else{if(message.type==='ready')session.status='running';if(message.type==='fatal')session.status='error';this.emit(message);}}catch(error){this.emit({type:'error',error:`Malformed kernel relay message: ${error.message}`});}}});
    processRef.stderr.on('data',chunk=>this.emit({type:'stderr',text:String(chunk).slice(-4000)}));
    processRef.on('error',error=>{session.status='error';rejectAll(error);this.emit({type:'error',error:String(error.message||error)});});
    processRef.on('exit',(code,signal)=>{if(this.session===session)this.session=null;rejectAll(new Error(`notebook kernel exited ${code ?? signal}`));this.emit({type:'exit',code,signal});});
    return this.summary();
  }
  request(payload={}) { const session=this.session;if(!session?.process?.stdin?.writable)throw new Error('Notebook kernel is not running');const operation=String(payload.operation||'');const code=String(payload.code||'');if(operation==='execute'&&Buffer.byteLength(code,'utf8')>128*1024)throw new Error('Notebook cell exceeds the 128 KiB safety limit.');const id=++this.sequence;session.process.stdin.write(`${JSON.stringify({id,operation,code,timeout:Math.max(1,Math.min(Number(payload.timeout||30),120))})}\n`);return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{session.pending.delete(id);reject(new Error('Notebook kernel request timed out.'));},125000);session.pending.set(id,{resolve:message=>{const digest=crypto.createHash('sha256').update(`${session.root}\n${code}\n${JSON.stringify(message.outputs||[])}\n${message.execution_count||''}`).digest('hex');resolve({...message,root:session.root,receipt:{id:`NBK-${digest.slice(0,16).toUpperCase()}`,digest:`sha256:${digest}`,mode:'persistent-jupyter-kernel',evidence:'operator-initiated'}});},reject,timer});}); }
  stop() { const session=this.session;if(!session)return {ok:true,status:'stopped'};this.session=null;try{if(session.process.stdin?.writable)session.process.stdin.write(`${JSON.stringify({id:++this.sequence,operation:'shutdown'})}\n`);}catch(_){}if(!session.process.killed)session.process.kill('SIGTERM');for(const pending of session.pending.values()){clearTimeout(pending.timer);pending.reject(new Error('Notebook kernel stopped'));}session.pending.clear();return {ok:true,status:'stopped'}; }
}
const notebookKernelHost = new NotebookKernelHost();
function forwardPort(value) {
  const port=Number(value);
  return Number.isInteger(port) && port >= 1 && port <= 65535 ? port : 0;
}
function forwardTarget(value) {
  const target=String(value || '127.0.0.1').trim().toLowerCase();
  return ['127.0.0.1','localhost'].includes(target) ? target : '';
}
class SshForwardHost {
  constructor() { this.sessions=new Map(); this.sequence=0; }
  summary(session) {
    return { id:session.id, status:session.status, pid:session.process?.pid || null, host:session.host, direction:session.direction, localPort:session.localPort, remotePort:session.remotePort, targetHost:session.targetHost, url:session.direction==='local' ? `http://127.0.0.1:${session.localPort}` : `http://127.0.0.1:${session.remotePort}`, visibility:'loopback-only', verification:'strict-known-host' };
  }
  emit(session, message) { if (session.sender && !session.sender.isDestroyed()) session.sender.send('beast:remote-forward-message',{forward:this.summary(session),...message}); }
  list() { return [...this.sessions.values()].map(session=>this.summary(session)); }
  start(payload={}, sender) {
    const host=remoteTarget(payload.host); const direction=payload.direction==='reverse' ? 'reverse' : 'local';
    const localPort=forwardPort(payload.localPort); const remotePort=forwardPort(payload.remotePort); const targetHost=forwardTarget(payload.targetHost);
    if (!host || !localPort || !remotePort || !targetHost) throw new Error('Forwarding requires a verified SSH host, loopback target, and ports from 1 to 65535.');
    const existing=[...this.sessions.values()].find(session=>session.host===host&&session.direction===direction&&session.localPort===localPort&&session.remotePort===remotePort&&session.targetHost===targetHost&&session.status==='running');
    if (existing) { existing.sender=sender; return this.summary(existing); }
    const id=`forward-${Date.now()}-${++this.sequence}`;
    const spec=direction==='local' ? `127.0.0.1:${localPort}:${targetHost}:${remotePort}` : `127.0.0.1:${remotePort}:${targetHost}:${localPort}`;
    const flag=direction==='local' ? '-L' : '-R';
    const processRef=spawn('ssh',['-o','BatchMode=yes','-o','ConnectTimeout=7','-o','ServerAliveInterval=20','-o','ServerAliveCountMax=2','-o','StrictHostKeyChecking=yes','-o','ExitOnForwardFailure=yes','-N',flag,spec,host],{cwd:repoRoot,stdio:['ignore','pipe','pipe'],shell:false,windowsHide:true});
    const session={id,process:processRef,sender,host,direction,localPort,remotePort,targetHost,status:'starting',stderr:''};this.sessions.set(id,session);
    processRef.stderr.on('data',chunk=>{session.stderr=`${session.stderr}${String(chunk)}`.slice(-4000);this.emit(session,{type:'stderr',text:String(chunk).slice(-1000)});});
    processRef.on('error',error=>{session.status='error';this.emit(session,{type:'error',error:String(error.message||error)});});
    processRef.on('exit',(code,signal)=>{if(this.sessions.get(id)===session)this.sessions.delete(id);if(session.status!=='stopped'){session.status='error';this.emit(session,{type:'exit',code,signal,error:session.stderr||`SSH forward exited ${code ?? signal}`});}});
    session.status='running'; this.emit(session,{type:'started'});
    return this.summary(session);
  }
  stop(id) { const session=this.sessions.get(String(id||''));if(!session)return {ok:true,status:'stopped'};this.sessions.delete(session.id);session.status='stopped';if(!session.process.killed)session.process.kill('SIGTERM');this.emit(session,{type:'stopped'});return {ok:true,...this.summary(session)}; }
  stopAll() { return this.list().map(session=>this.stop(session.id)); }
}
const sshForwardHost = new SshForwardHost();
class RemoteTerminalHost {
  constructor() { this.sessions=new Map(); this.sequence=0; }
  summary(session) { return { id:session.id,status:session.status,pid:session.process?.pid || null,host:session.host,cwd:session.cwd,shell:session.shell,transport:'ssh-tty',verification:'strict-known-host',startedAt:session.startedAt }; }
  emit(session,message) { if(session.sender&&!session.sender.isDestroyed()) session.sender.send('beast:remote-terminal-message',{terminal:this.summary(session),...message}); }
  list() { return [...this.sessions.values()].map(session=>this.summary(session)); }
  start(payload={},sender) {
    const host=remoteTarget(payload.host || lastRemoteWorkspace?.host); const cwd=remotePath(payload.path || lastRemoteWorkspace?.path || '~'); const shell=['bash','sh','zsh','fish'].includes(String(payload.shell||'bash')) ? String(payload.shell||'bash') : '';
    if(!host||!cwd||!shell) throw new Error('Remote terminal requires a verified host, safe workspace path, and supported shell.');
    const existing=[...this.sessions.values()].find(session=>session.host===host&&session.cwd===cwd&&session.shell===shell&&session.status==='running');
    if(existing) { existing.sender=sender; this.emit(existing,{type:'attached',text:existing.output || ''}); return this.summary(existing); }
    const id=`remote-terminal-${Date.now()}-${++this.sequence}`;
    const command=`cd ${cwd} && exec ${shell} -i`;
    const processRef=spawn('ssh',['-tt','-o','BatchMode=yes','-o','ConnectTimeout=7','-o','ServerAliveInterval=20','-o','ServerAliveCountMax=2','-o','StrictHostKeyChecking=yes',host,command],{cwd:repoRoot,stdio:['pipe','pipe','pipe'],shell:false,windowsHide:true});
    const session={id,process:processRef,sender,host,cwd,shell,status:'starting',output:'',stderr:'',startedAt:Date.now()};this.sessions.set(id,session);
    const append=(text,stream)=>{const value=String(text||'');session.output=`${session.output}${value}`.slice(-256000);if(stream==='stderr')session.stderr=`${session.stderr}${value}`.slice(-12000);this.emit(session,{type:'output',stream,text:value});};
    processRef.stdout.on('data',chunk=>append(chunk,'stdout'));processRef.stderr.on('data',chunk=>append(chunk,'stderr'));
    processRef.on('error',error=>{session.status='error';this.emit(session,{type:'error',error:String(error.message||error)});});
    processRef.on('exit',(code,signal)=>{if(this.sessions.get(id)===session)this.sessions.delete(id);if(session.status!=='stopped'){session.status='error';this.emit(session,{type:'exit',code,signal,error:session.stderr || `Remote terminal exited ${code ?? signal}`});}});
    session.status='running';this.emit(session,{type:'started',text:`Connected to ${host} · ${cwd}\n`});return this.summary(session);
  }
  send(id,input) { const session=this.sessions.get(String(id||'')); const text=String(input ?? '');if(!session||session.status!=='running'||!session.process.stdin?.writable) throw new Error('Remote terminal session is not running.');if(!text||Buffer.byteLength(text,'utf8')>64*1024) throw new Error('Remote terminal input must be between 1 byte and 64 KiB.');session.process.stdin.write(`${text.endsWith('\n')?text:`${text}\n`}`);return {ok:true,...this.summary(session),bytes:Buffer.byteLength(text,'utf8')}; }
  stop(id) { const session=this.sessions.get(String(id||''));if(!session)return {ok:true,status:'stopped'};this.sessions.delete(session.id);session.status='stopped';try{if(session.process.stdin?.writable)session.process.stdin.write('exit\n');}catch(_){};if(!session.process.killed)session.process.kill('SIGTERM');this.emit(session,{type:'stopped'});return {ok:true,...this.summary(session)}; }
  stopAll() { return this.list().map(session=>this.stop(session.id)); }
}
const remoteTerminalHost = new RemoteTerminalHost();
class LocalTerminalHost {
  constructor() { this.sessions=new Map(); this.sequence=0; }
  summary(session) { return {id:session.id,status:session.status,pid:session.process?.pid||null,cwd:session.cwd,shell:session.shell,transport:'local-pty-compatible',verification:'workspace-bounded',startedAt:session.startedAt}; }
  emit(session,message) { if(session.sender&&!session.sender.isDestroyed())session.sender.send('beast:terminal-session-message',{terminal:this.summary(session),...message}); }
  list() { return [...this.sessions.values()].map(session=>this.summary(session)); }
  start(rootPath, payload={}, sender) {
    const root=path.resolve(rootPath||activeWorkspaceRoot||repoRoot); const cwd=taskCwd(root,payload.cwd||root); const shell=['bash','sh','zsh','fish'].includes(String(payload.shell||'bash'))?String(payload.shell||'bash'):'';
    if(!cwd||!shell) throw new Error('Local terminal requires a workspace-bounded cwd and supported shell.');
    const existing=[...this.sessions.values()].find(session=>session.cwd===cwd&&session.shell===shell&&session.status==='running'); if(existing){existing.sender=sender;return this.summary(existing);}
    const id=`terminal-${Date.now()}-${++this.sequence}`; const processRef=spawn(shell,['-i'],{cwd,env:{...process.env,TERM:process.env.TERM||'xterm-256color'},stdio:['pipe','pipe','pipe'],shell:false,windowsHide:true}); const session={id,process:processRef,sender,cwd,shell,status:'starting',output:'',stderr:'',startedAt:Date.now()};this.sessions.set(id,session);
    const append=(text,stream)=>{const value=String(text||'');session.output=`${session.output}${value}`.slice(-256000);if(stream==='stderr')session.stderr=`${session.stderr}${value}`.slice(-12000);this.emit(session,{type:'output',stream,text:value});};
    processRef.stdout.on('data',chunk=>append(chunk,'stdout'));processRef.stderr.on('data',chunk=>append(chunk,'stderr'));processRef.on('error',error=>{session.status='error';this.emit(session,{type:'error',error:String(error.message||error)});});processRef.on('exit',(code,signal)=>{if(this.sessions.get(id)===session)this.sessions.delete(id);if(session.status!=='stopped'){session.status='exited';this.emit(session,{type:'exit',code,signal,error:session.stderr||''});}});session.status='running';this.emit(session,{type:'started',text:`BEAST terminal · ${cwd}\n`});return this.summary(session);
  }
  send(id,input) { const session=this.sessions.get(String(id||''));const text=String(input??'');if(!session||session.status!=='running'||!session.process.stdin?.writable)throw new Error('Local terminal session is not running.');if(!text||Buffer.byteLength(text,'utf8')>64*1024)throw new Error('Terminal input must be between 1 byte and 64 KiB.');session.process.stdin.write(text.endsWith('\n')?text:`${text}\n`);return {ok:true,...this.summary(session),bytes:Buffer.byteLength(text,'utf8')}; }
  stop(id) { const session=this.sessions.get(String(id||''));if(!session)return {ok:true,status:'stopped'};this.sessions.delete(session.id);session.status='stopped';try{if(session.process.stdin?.writable)session.process.stdin.write('exit\n');}catch(_){}if(!session.process.killed)session.process.kill('SIGTERM');this.emit(session,{type:'stopped'});return {ok:true,...this.summary(session)}; }
  stopAll() { return this.list().map(session=>this.stop(session.id)); }
}
const localTerminalHost = new LocalTerminalHost();
const EXTENSION_CAPABILITIES=new Set(['workspace.read','workspace.write','language.client','terminal.execute','network.loopback']);
function extensionGrantFile(root) { return path.join(path.resolve(root || repoRoot),'.beast','ide-extension-grants.json'); }
function extensionDisableFile(root) { return path.join(path.resolve(root || repoRoot),'.beast','ide-extension-disabled.json'); }
function readExtensionGrants(root) { try { const value=JSON.parse(fs.readFileSync(extensionGrantFile(root),'utf8')); return value && typeof value==='object' ? value : {}; } catch (_) { return {}; } }
function writeExtensionGrants(root, grants) { const file=extensionGrantFile(root);fs.mkdirSync(path.dirname(file),{recursive:true,mode:0o700});fs.writeFileSync(file,`${JSON.stringify(grants,null,2)}\n`,{encoding:'utf8',mode:0o600}); }
function readDisabledExtensions(root) { try { const value=JSON.parse(fs.readFileSync(extensionDisableFile(root),'utf8'));return new Set(Array.isArray(value)?value.map(String):[]); } catch (_) { return new Set(); } }
function writeDisabledExtensions(root, value) { const file=extensionDisableFile(root);fs.mkdirSync(path.dirname(file),{recursive:true,mode:0o700});fs.writeFileSync(file,`${JSON.stringify([...value].sort(),null,2)}\n`,{encoding:'utf8',mode:0o600}); }
function workspaceExtensionRoot(root) { return path.join(path.resolve(root || repoRoot),'.beast','extensions'); }
function extensionPackage(source) { const folder=path.resolve(String(source||''));const manifest=path.join(folder,'beast-extension.json');let raw;try{if(!fs.statSync(folder).isDirectory()||fs.statSync(manifest).size>65536)return null;raw=JSON.parse(fs.readFileSync(manifest,'utf8'));}catch(_){return null;}const id=String(raw?.id||'');const main=String(raw?.main||'');if(!/^[a-z0-9][a-z0-9._-]{1,95}$/.test(id)||!main||!/^[A-Za-z0-9._/-]{1,180}$/.test(main)||main.split('/').includes('..'))return null;const entry=path.resolve(folder,main);try{if(!entry.startsWith(`${folder}${path.sep}`)||!fs.statSync(entry).isFile()||fs.statSync(entry).size>65536)return null;}catch(_){return null;}return {id,folder,manifest,entry,main}; }
class BeastExtensionHost {
  constructor() { this.session=null;this.sequence=0; }
  summary() { const s=this.session;return {status:s?.status || 'stopped',pid:s?.process?.pid || null,root:s?.root || '',target:s?.target || {kind:'local'},mode:s?.target?.kind==='local'?'declarative-manifests':'remote-declarative-manifests',extensions:s?.extensions || []}; }
  emit(message) { const sender=this.session?.sender;if(sender&&!sender.isDestroyed())sender.send('beast:extension-host-message',message); }
  roots(root,target={kind:'local'}) { return target.kind==='local' ? [{path:path.join(root,'.beast','extensions'),origin:'workspace'},{path:runtimeResourcePath('extensions'),origin:'bundled'}] : [{path:path.join(root,'.beast','extensions'),origin:'workspace'}]; }
  launch(root,target={kind:'local'}) {
    const script=runtimeResourcePath('scripts','beast-extension-host.js');
    if (target.kind==='ssh') {
      const encoded=fs.readFileSync(script).toString('base64');
      const command=`node -e ${shellQuote(`eval(Buffer.from('${encoded}','base64').toString())`)}`;
      return {command:'ssh',args:[...remoteSshArgs(remoteTarget(target.host),`cd ${shellQuote(remotePath(target.remoteRoot||'~'))} && ${command}`)],cwd:root};
    }
    if (target.kind==='container') return {command:'docker',args:['exec','-i','-w',remotePath(target.workspaceFolder||'/workspace'),containerId(target.containerId||target.name), 'node','-e',`eval(Buffer.from('${fs.readFileSync(script).toString('base64')}','base64').toString())`],cwd:root};
    return {command:process.execPath,args:[script],cwd:root};
  }
  async start(root, sender, target={kind:'local'}) {
    const workspace=path.resolve(root || repoRoot);
    const selected=executionTargetSummary(target);
    if (this.session?.status==='running'&&this.session.root===workspace&&JSON.stringify(this.session.target)===JSON.stringify(selected)) { this.session.sender=sender;return this.summary(); }
    this.stop();
    const launch=this.launch(workspace,selected);const processRef=spawn(launch.command,launch.args,{cwd:launch.cwd,env:{...process.env,ELECTRON_RUN_AS_NODE:'1',BEAST_ACTIVE_WORKSPACE:workspace},stdio:['pipe','pipe','pipe'],shell:false,windowsHide:true});
    const session={process:processRef,sender,root:workspace,target:selected,status:'starting',buffer:'',pending:new Map(),extensions:[],readyResolve:null,readyReject:null};this.session=session;
    const rejectAll=error=>{for(const pending of session.pending.values()){clearTimeout(pending.timer);pending.reject(error);}session.pending.clear();session.readyReject?.(error);session.readyReject=null;};
    processRef.stdout.on('data',chunk=>{session.buffer+=String(chunk);let cut;while((cut=session.buffer.indexOf('\n'))>=0){const line=session.buffer.slice(0,cut);session.buffer=session.buffer.slice(cut+1);if(!line.trim())continue;try{const message=JSON.parse(line);if(message.id!=null&&session.pending.has(message.id)){const pending=session.pending.get(message.id);session.pending.delete(message.id);clearTimeout(pending.timer);message.ok===false?pending.reject(new Error(message.error||'extension host request failed')):pending.resolve(message);}else if(message.type==='ready'){session.status='running';session.readyResolve?.(this.summary());session.readyResolve=null;session.readyReject=null;this.emit(message);}else this.emit(message);}catch(error){this.emit({type:'error',error:`Malformed extension host message: ${error.message}`});}}});
    processRef.stderr.on('data',chunk=>this.emit({type:'stderr',text:String(chunk).slice(-4000)}));
    processRef.on('error',error=>{session.status='error';rejectAll(error);this.emit({type:'error',error:String(error.message||error)});});
    processRef.on('exit',(code,signal)=>{if(this.session===session)this.session=null;rejectAll(new Error(`extension host exited ${code ?? signal}`));this.emit({type:'exit',code,signal});});
    return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{session.readyReject=null;this.stop();reject(new Error('Extension host startup timed out.'));},10000);session.readyResolve=value=>{clearTimeout(timer);resolve(value);};session.readyReject=error=>{clearTimeout(timer);reject(error);};});
  }
  request(operation,payload={}) { const session=this.session;if(!session?.process?.stdin?.writable)throw new Error('Extension host is not running');const id=++this.sequence;session.process.stdin.write(`${JSON.stringify({id,operation,...payload})}\n`);return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{session.pending.delete(id);reject(new Error(`Extension host ${operation} timed out.`));},12000);session.pending.set(id,{resolve,reject,timer});}); }
  async discover(root,sender,target={kind:'local'}) { const workspace=path.resolve(root || repoRoot);await this.start(workspace,sender,target);const selected=this.session.target;const result=await this.request('discover',{roots:this.roots(workspace,selected)});const grants=readExtensionGrants(workspace);const disabled=readDisabledExtensions(workspace);this.session.extensions=(result.extensions || []).map(extension=>{const granted=(Array.isArray(grants[extension.id])?grants[extension.id]:[]).filter(capability=>extension.capabilities.includes(capability));return {...extension,disabled:disabled.has(extension.id),granted,needsApproval:extension.capabilities.filter(capability=>!granted.includes(capability))};});return this.summary(); }
  async grant(root,id,capabilities,sender) { const workspace=path.resolve(root || repoRoot);const summary=await this.discover(workspace,sender);const extension=summary.extensions.find(item=>item.id===String(id||''));if(!extension)throw new Error('Extension manifest is not available in this workspace.');const requested=[...new Set((Array.isArray(capabilities)?capabilities:[]).map(String))];if(requested.some(capability=>!EXTENSION_CAPABILITIES.has(capability)||!extension.capabilities.includes(capability)))throw new Error('Requested extension grant is not declared by this manifest.');const grants=readExtensionGrants(workspace);grants[extension.id]=requested;writeExtensionGrants(workspace,grants);return this.discover(workspace,sender); }
  async setEnabled(root,id,enabled,sender) { const workspace=path.resolve(root||repoRoot);const summary=await this.discover(workspace,sender);if(!summary.extensions.some(item=>item.id===String(id||'')))throw new Error('Extension is not available in this workspace.');const disabled=readDisabledExtensions(workspace);enabled?disabled.delete(String(id)):disabled.add(String(id));writeDisabledExtensions(workspace,disabled);return this.discover(workspace,sender); }
  async installWorkspaceExtension(root,sender) { const workspace=path.resolve(root||repoRoot);const windowRef=BrowserWindow.fromWebContents(sender)||mainWindow;const choice=await dialog.showOpenDialog(windowRef,{title:'Install BEAST workspace extension',properties:['openDirectory']});if(choice.canceled||!choice.filePaths[0])return this.discover(workspace,sender);const source=extensionPackage(choice.filePaths[0]);if(!source)throw new Error('Choose an extension folder with a valid beast-extension.json and a bounded main entrypoint.');const destination=path.join(workspaceExtensionRoot(workspace),source.id);if(fs.existsSync(destination)){const confirm=await dialog.showMessageBox(windowRef,{type:'warning',buttons:['Replace','Cancel'],defaultId:1,cancelId:1,message:`Replace workspace extension “${source.id}”?`,detail:'The existing managed workspace copy will be removed before the selected manifest and entrypoint are installed.'});if(confirm.response!==0)return this.discover(workspace,sender);fs.rmSync(destination,{recursive:true,force:true});}fs.mkdirSync(destination,{recursive:true,mode:0o700});fs.copyFileSync(source.manifest,path.join(destination,'beast-extension.json'));const target=path.join(destination,source.main);fs.mkdirSync(path.dirname(target),{recursive:true,mode:0o700});fs.copyFileSync(source.entry,target);const disabled=readDisabledExtensions(workspace);disabled.delete(source.id);writeDisabledExtensions(workspace,disabled);return this.discover(workspace,sender); }
  async uninstallWorkspaceExtension(root,id,sender) { const workspace=path.resolve(root||repoRoot);const safeId=String(id||'');if(!/^[a-z0-9][a-z0-9._-]{1,95}$/.test(safeId))throw new Error('Extension identifier is invalid.');const folder=path.join(workspaceExtensionRoot(workspace),safeId);const source=extensionPackage(folder);if(!source||source.id!==safeId)throw new Error('Only installed workspace extensions can be removed.');const windowRef=BrowserWindow.fromWebContents(sender)||mainWindow;const confirm=await dialog.showMessageBox(windowRef,{type:'warning',buttons:['Remove','Cancel'],defaultId:1,cancelId:1,message:`Remove workspace extension “${safeId}”?`,detail:'This removes only BEAST’s managed copy in .beast/extensions.'});if(confirm.response!==0)return this.discover(workspace,sender);fs.rmSync(folder,{recursive:true,force:true});const grants=readExtensionGrants(workspace);delete grants[safeId];writeExtensionGrants(workspace,grants);const disabled=readDisabledExtensions(workspace);disabled.delete(safeId);writeDisabledExtensions(workspace,disabled);return this.discover(workspace,sender); }
  async execute(root,id,command,sender,target={kind:'local'}) { const workspace=path.resolve(root || repoRoot);const summary=await this.discover(workspace,sender,target);const extension=summary.extensions.find(item=>item.id===String(id||''));if(!extension)throw new Error('Extension is not available in this workspace.');if(extension.disabled)throw new Error('Extension is disabled for this workspace.');if(!extension.contributes?.commands?.some(item=>item.id===String(command||'')))throw new Error('Extension command is not declared by this manifest.');const result=await this.request('execute',{extensionId:extension.id,command:String(command||''),roots:this.roots(workspace,this.session.target),workspaceRoot:workspace,granted:extension.granted||[]});const routes=new Set(['workspace','mission','compatibility','source','review','evidence','crystallization','terminal','testing']);const actions=(result.actions||[]).filter(action=>action&&typeof action==='object').map(action=>{if(action.kind==='navigate'&&!routes.has(action.payload?.route))throw new Error('Extension requested an unsupported navigation target.');if(!['navigate','notice','command'].includes(action.kind))throw new Error('Extension requested an unsupported mediated action.');return action;});return {ok:true,extension:extension.id,target:this.session.target,granted:result.granted||[],actions}; }
  stop() { const session=this.session;if(!session)return {ok:true,status:'stopped'};this.session=null;session.status='stopped';for(const pending of session.pending.values()){clearTimeout(pending.timer);pending.reject(new Error('Extension host stopped'));}session.pending.clear();if(!session.process.killed)session.process.kill('SIGTERM');return {ok:true,status:'stopped'}; }
}
const beastExtensionHost = new BeastExtensionHost();
function serviceRegistryGateway(root) {
  try {
    const config = yaml.load(fs.readFileSync(path.join(root, '.byron', 'services.yaml'), 'utf8')) || {};
    const upstream = config?.services?.beast?.upstream;
    if (!/^(?:127\.0\.0\.1|\[::1\]):\d+$/.test(String(upstream || ''))) throw new Error('invalid BEAST upstream');
    return `http://${upstream}`;
  } catch (_) {
    return 'http://127.0.0.1:8101';
  }
}
let activeWorkspaceRoot = path.resolve(process.env.BEAST_ACTIVE_WORKSPACE || process.env.BEAST_WORKSPACE || repoRoot);
let activeWorkspaceRoots = [activeWorkspaceRoot];
function normalizeWorkspaceRoots(roots, primary=activeWorkspaceRoot) { const unique=[path.resolve(primary||repoRoot),...(Array.isArray(roots)?roots:[])].filter(item=>{try{return fs.existsSync(path.resolve(item))&&fs.statSync(path.resolve(item)).isDirectory();}catch(_){return false;}}).filter((item,index,all)=>all.indexOf(item)===index).slice(0,12);const used=new Map();return unique.map((root,index)=>{const base=path.basename(root).replace(/[^A-Za-z0-9._-]/g,'-')||`folder-${index+1}`;const count=(used.get(base)||0)+1;used.set(base,count);return {id:count===1?base:`${base}-${count}`,name:base,path:root,primary:index===0}; }); }
function workspaceFolders() { return normalizeWorkspaceRoots(activeWorkspaceRoots,activeWorkspaceRoot); }
function persistWorkspaceFolders() { try { const folders=workspaceFolders();fs.mkdirSync(path.dirname(workspaceFoldersStatePath()),{recursive:true});fs.writeFileSync(workspaceFoldersStatePath(),JSON.stringify({primary:activeWorkspaceRoot,roots:folders.map(item=>item.path)})); } catch (error) { appendLog(`workspace folder persistence failed: ${error.message || error}`); } }
function restoreWorkspaceFolders() { try { const saved=JSON.parse(fs.readFileSync(workspaceFoldersStatePath(),'utf8'));if(Array.isArray(saved?.roots)&&saved.roots.length)setWorkspaceRoots(saved.roots,saved.primary||saved.roots[0],false); } catch (_) {} }
function setWorkspaceRoots(roots, primary='', persist=true) { const first=primary?path.resolve(primary):path.resolve((roots||[])[0]||activeWorkspaceRoot||repoRoot);activeWorkspaceRoot=first;activeWorkspaceRoots=normalizeWorkspaceRoots(roots,first).map(item=>item.path);if(persist)persistWorkspaceFolders();return workspaceFolders(); }
function parseWorkspaceReference(reference) { const value=String(reference||'');const match=value.match(/^@([^/]+)\/(.+)$/);if(!match)return {folder:workspaceFolders()[0],relative:value};const folder=workspaceFolders().find(item=>item.id===match[1]);return {folder,relative:match[2]}; }
function multiRootFiles(limit=2000) { const folders=workspaceFolders();const perRoot=Math.max(1,Math.ceil(limit/Math.max(1,folders.length)));return folders.flatMap(folder=>workspaceFileCandidates(folder.path,perRoot).map(item=>({ ...item,path:folders.length===1?item.path:`@${folder.id}/${item.path}`,relativePath:item.path,rootId:folder.id,rootName:folder.name,rootPath:folder.path }))).slice(0,limit); }
const configuredGatewayUrl = serviceRegistryGateway(repoRoot);
const gatewayOverrideAllowed = process.env.BEAST_ALLOW_GATEWAY_OVERRIDE === '1';
let gatewayUrl = gatewayOverrideAllowed && process.env.BEAST_DESKTOP_GATEWAY ? process.env.BEAST_DESKTOP_GATEWAY : configuredGatewayUrl;
let gatewayProcess = null;
let gatewayStartupPromise = null;
let mainWindow = null;
const appWindows = new Set();
let lastGatewayCommand = '';
let gatewayLog = [];
let gatewayStartedAt = 0;
let localIdeMode = false;
let localIdeReason = '';
let resolvedBeastPython = null;

function appendLog(line) {
  const record = `[${new Date().toISOString()}] ${String(line || '').trim()}`;
  gatewayLog.push(record);
  gatewayLog = gatewayLog.slice(-500);
  try {
    const logDir = path.join(repoRoot, '.beast', 'logs');
    fs.mkdirSync(logDir, { recursive: true });
    fs.appendFileSync(path.join(logDir, 'desktop-gateway.log'), `${record}\n`, { encoding: 'utf8', mode: 0o600 });
  } catch (_) {}
  for (const windowRef of appWindows) {
    if (!windowRef.isDestroyed()) windowRef.webContents.send('beast:gateway-log', gatewayLog);
  }
}

function enterLocalIdeMode(reason) {
  localIdeMode = true;
  localIdeReason = reason || 'gateway unavailable; using local desktop IDE mode';
  appendLog(`Local IDE Mode: ${localIdeReason}`);
  return {
    ok: false,
    url: gatewayUrl,
    local_mode: true,
    error: localIdeReason,
    capabilities: {
      ok: true,
      mode: 'desktop_local_fallback',
      checks: {
        local_files: { ok: true, mode: 'desktop_ipc' },
        local_editor: { ok: true, mode: 'monaco' },
        sourceplan_gateway: { ok: false, mode: 'deferred_until_gateway_ready' },
      },
    },
  };
}

function workspaceFileCandidates(rootPath, limit = 400) {
  const root = path.resolve(rootPath || repoRoot);
  if (!fs.existsSync(root)) {
    throw new Error(`workspace path does not exist: ${root}`);
  }
  if (!fs.statSync(root).isDirectory()) {
    throw new Error(`workspace path is not a directory: ${root}`);
  }
  const ignore = new Set(['.git', '.beast', 'node_modules', '__pycache__', '.pytest_cache', 'dist', 'build', '.venv', 'venv']);
  const rows = [];
  function walk(dir) {
    if (rows.length >= limit) return;
    let entries = [];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch (_error) {
      return;
    }
    entries.sort((a, b) => a.name.localeCompare(b.name));
    for (const entry of entries) {
      if (rows.length >= limit) return;
      if (ignore.has(entry.name)) continue;
      const full = path.join(dir, entry.name);
      const rel = path.relative(root, full);
      if (entry.isDirectory()) {
        walk(full);
      } else if (entry.isFile()) {
        rows.push({ path: rel, source: 'desktop_local_files' });
      }
    }
  }
  walk(root);
  return rows;
}

function readWorkspaceFile(rootPath, relPath, maxChars = 200000) {
  const root = path.resolve(rootPath || repoRoot);
  const target = path.resolve(root, relPath || '');
  if (target !== root && !target.startsWith(`${root}${path.sep}`)) {
    return { ok: false, error: 'path escaped workspace', path: relPath };
  }
  try {
    const content = fs.readFileSync(target, 'utf8').slice(0, maxChars);
    return { ok: true, path: relPath, content, source: 'desktop_local_files' };
  } catch (error) {
    return { ok: false, error: String(error.message || error), path: relPath };
  }
}

function textWorkspaceSearch(rootPath, payload={}) {
  const root=path.resolve(rootPath || repoRoot); const query=String(payload.query || '');
  if (!query || query.length>300) return {ok:false,error:'Search text must be between 1 and 300 characters.',results:[]};
  const sensitive=Boolean(payload.caseSensitive); const needle=sensitive?query:query.toLowerCase(); const limit=Math.max(1,Math.min(Number(payload.limit || 200),1000));
  const results=[];
  for (const item of workspaceFileCandidates(root,1500)) {
    if (results.length>=limit || Number(item.size||0)>1024*1024) continue;
    const target=safeWorkspacePath(root,item.path);if(!target.ok)continue;
    let text='';try{text=fs.readFileSync(target.target,'utf8');}catch(_){continue;}
    if (text.includes('\u0000')) continue;
    const lines=text.split(/\r?\n/);
    for(let index=0;index<lines.length&&results.length<limit;index+=1){const hay=sensitive?lines[index]:lines[index].toLowerCase();const column=hay.indexOf(needle);if(column>=0)results.push({path:item.path,line:index+1,column:column+1,preview:lines[index].slice(0,600)});}
  }
  return {ok:true,query,results,truncated:results.length>=limit};
}

function workspaceReplacePreview(rootPath, payload={}) {
  const root=path.resolve(rootPath || repoRoot);const query=String(payload.query || '');const replacement=String(payload.replacement ?? '');
  if(!query || query.length>300 || Buffer.byteLength(replacement,'utf8')>64*1024)return {ok:false,error:'Replace text is outside allowed bounds.',files:[]};
  const requested=Array.isArray(payload.paths)?new Set(payload.paths.map(String)):null;const files=[];let total=0;
  for(const item of workspaceFileCandidates(root,1500)){if(requested&&!requested.has(item.path))continue;const target=safeWorkspacePath(root,item.path);if(!target.ok)continue;let text='';try{text=fs.readFileSync(target.target,'utf8');}catch(_){continue;}if(text.includes('\u0000'))continue;const count=text.split(query).length-1;if(count){files.push({path:item.path,count,before:text.slice(0,1600),after:text.replaceAll(query,replacement).slice(0,1600)});total+=count;}if(files.length>=300||total>=5000)break;}
  if(payload.apply){for(const file of files){const target=safeWorkspacePath(root,file.path);if(target.ok)fs.writeFileSync(target.target,fs.readFileSync(target.target,'utf8').replaceAll(query,replacement),'utf8');}}
  return {ok:true,applied:Boolean(payload.apply),query,replacement,total,files,truncated:files.length>=300||total>=5000};
}

function parseGitPorcelain(output) {
  const tokens=String(output||'').split('\u0000');const changes=[];let branch='';
  for(let index=0;index<tokens.length;index+=1){const token=tokens[index];if(!token)continue;if(token.startsWith('## ')){branch=token.slice(3);continue;}if(token.length<4)continue;const code=token.slice(0,2);const filePath=token.slice(3);let originalPath='';if(/[RC]/.test(code)&&tokens[index+1])originalPath=tokens[++index];const staged=code[0]!==' '&&code[0]!=='?';const unstaged=code[1]!==' '||code==='??';changes.push({index:code,path:filePath,originalPath,staged,unstaged,conflict:/U|AA|DD/.test(code),untracked:code==='??'});if(changes.length>=500)break;}
  return {branch,changes};
}
function gitReceipt(root, action, detail, result) {
  const digest=crypto.createHash('sha256').update(`${root}\n${action}\n${detail}\n${result.stdout||''}\n${result.stderr||''}\n${result.returncode}`).digest('hex');
  return {id:`GIT-${digest.slice(0,16).toUpperCase()}`,digest:`sha256:${digest}`,evidence:'operator-initiated',action};
}
function parseGitPatchHunks(source, mode, relPath) {
  const chunks=String(source||'').match(/[^\n]*\n|[^\n]+$/g)||[];const first=chunks.findIndex(line=>line.startsWith('@@ '));if(first<0)return [];const fileHeader=chunks.slice(0,first).join('');const hunks=[];
  for(let index=first;index<chunks.length;){if(!chunks[index].startsWith('@@ ')){index+=1;continue;}const start=index;index+=1;while(index<chunks.length&&!chunks[index].startsWith('@@ '))index+=1;const lines=chunks.slice(start,index);const patch=`${fileHeader}${lines.join('')}`;const range=lines[0].match(/^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@(.*)$/);const added=lines.slice(1).filter(line=>line.startsWith('+')&&!line.startsWith('+++')).length;const removed=lines.slice(1).filter(line=>line.startsWith('-')&&!line.startsWith('---')).length;const digest=crypto.createHash('sha256').update(`${mode}\u0000${relPath}\u0000${patch}`).digest('hex');hunks.push({id:`HUNK-${digest.slice(0,20).toUpperCase()}`,header:lines[0].trim(),context:String(range?.[5]||'').trim().slice(0,180),oldStart:Number(range?.[1]||0),oldLines:Number(range?.[2]||1),newStart:Number(range?.[3]||0),newLines:Number(range?.[4]||1),added,removed,lines:lines.slice(1).map(line=>line.replace(/\n$/,'')).slice(0,500),patch});if(hunks.length>=300)break;}
  return hunks;
}
async function workspaceGitStatus(rootPath) {
  const root=path.resolve(rootPath || repoRoot);
  const [status,worktreeStat,stagedStat,branchList]=await Promise.all([
    boundedProcess('git',['status','--porcelain=v1','--branch','-z'],{cwd:root,timeoutMs:10000,outputLimit:128000}),
    boundedProcess('git',['diff','--stat'],{cwd:root,timeoutMs:10000,outputLimit:64000}),
    boundedProcess('git',['diff','--cached','--stat'],{cwd:root,timeoutMs:10000,outputLimit:64000}),
    boundedProcess('git',['branch','--format=%(refname:short)%09%(HEAD)'],{cwd:root,timeoutMs:10000,outputLimit:64000})
  ]);
  const parsed=parseGitPorcelain(status.stdout);const branchName=parsed.branch.replace(/^No commits yet on /,'').split('...')[0].trim();const branches=String(branchList.stdout||'').split(/\r?\n/).filter(Boolean).map(line=>{const [name,head]=line.split('\t');return {name,current:head==='*'};}).slice(0,300);
  const stagedCount=parsed.changes.filter(change=>change.staged).length;const unstagedCount=parsed.changes.filter(change=>change.unstaged).length;
  return {ok:status.ok,branch:parsed.branch,branchName,branches,changes:parsed.changes,counts:{staged:stagedCount,unstaged:unstagedCount,conflicts:parsed.changes.filter(change=>change.conflict).length},diffStat:String(worktreeStat.stdout||''),stagedDiffStat:String(stagedStat.stdout||''),error:status.error||status.stderr||''};
}
async function gitTextAt(root, spec, fallbackPath='') {
  if(spec){const result=await boundedProcess('git',['show',spec],{cwd:root,timeoutMs:10000,outputLimit:1100000});if(result.ok){const text=String(result.stdout||'');if(text.includes('\u0000'))return {ok:false,binary:true,text:''};return {ok:true,text:text.slice(0,1000000),truncated:text.length>1000000};}}
  if(!fallbackPath)return {ok:true,text:''};const target=safeWorkspacePath(root,fallbackPath);if(!target.ok)return {ok:false,error:target.error,text:''};try{const stat=fs.statSync(target.target);if(!stat.isFile())return {ok:true,text:''};if(stat.size>1000000)return {ok:false,error:'Git diff preview is limited to 1 MB per side.',text:'',truncated:true};const value=fs.readFileSync(target.target);if(value.includes(0))return {ok:false,binary:true,text:''};return {ok:true,text:value.toString('utf8')};}catch(error){if(error?.code==='ENOENT')return {ok:true,text:''};return {ok:false,error:String(error.message||error),text:''};}
}
async function workspaceGitDiff(rootPath, payload={}) {
  const root=path.resolve(rootPath || repoRoot);const relPath=String(payload.path||'');const target=safeWorkspacePath(root,relPath);if(!target.ok)return {ok:false,error:target.error};const mode=payload.mode==='staged'?'staged':'worktree';const originalPath=String(payload.originalPath||relPath);const originalTarget=safeWorkspacePath(root,originalPath);if(!originalTarget.ok)return {ok:false,error:originalTarget.error};
  const baseline=mode==='staged'?`HEAD:${originalPath}`:`:${originalPath}`;const proposed=mode==='staged'?`:${relPath}`:'';const [before,after,patch]=await Promise.all([gitTextAt(root,baseline),gitTextAt(root,proposed,mode==='worktree'?relPath:''),boundedProcess('git',['diff',...(mode==='staged'?['--cached']:[]),'--no-ext-diff','--',relPath],{cwd:root,timeoutMs:10000,outputLimit:300000})]);
  if(before.binary||after.binary)return {ok:false,binary:true,path:relPath,mode,error:'Binary files cannot be shown in the text diff editor.'};if(!before.ok&&!before.text)return {ok:false,error:before.error||'Unable to load the Git baseline.'};if(!after.ok&&!after.text)return {ok:false,error:after.error||'Unable to load the changed file.'};
  return {ok:true,path:relPath,originalPath,mode,originalText:before.text||'',modifiedText:after.text||'',patch:String(patch.stdout||''),truncated:Boolean(before.truncated||after.truncated)};
}
async function workspaceGitHunks(rootPath, payload={}) {
  const root=path.resolve(rootPath||repoRoot);const relPath=String(payload.path||'');const target=safeWorkspacePath(root,relPath);if(!target.ok)return {ok:false,error:target.error,hunks:[]};const mode=payload.mode==='staged'?'staged':'worktree';const result=await boundedProcess('git',['diff',...(mode==='staged'?['--cached']:[]),'--no-color','--no-ext-diff','--unified=3','--',relPath],{cwd:root,timeoutMs:10000,outputLimit:1024*1024});if(!result.ok&&result.returncode!==0)return {...result,path:relPath,mode,hunks:[]};const hunks=parseGitPatchHunks(result.stdout,mode,relPath);return {ok:true,path:relPath,mode,hunks:hunks.map(({patch,...hunk})=>hunk),summary:{count:hunks.length,added:hunks.reduce((total,hunk)=>total+hunk.added,0),removed:hunks.reduce((total,hunk)=>total+hunk.removed,0)}};
}
async function workspaceGitHunkAction(rootPath, payload={}) {
  const root=path.resolve(rootPath||repoRoot);const relPath=String(payload.path||'');const target=safeWorkspacePath(root,relPath);if(!target.ok)return {ok:false,error:target.error};const action=payload.action==='unstage'?'unstage':payload.action==='stage'?'stage':'';if(!action)return {ok:false,error:'Unsupported hunk action.'};const mode=action==='unstage'?'staged':'worktree';const current=await boundedProcess('git',['diff',...(mode==='staged'?['--cached']:[]),'--no-color','--no-ext-diff','--unified=3','--',relPath],{cwd:root,timeoutMs:10000,outputLimit:1024*1024});const hunk=parseGitPatchHunks(current.stdout,mode,relPath).find(item=>item.id===String(payload.hunkId||''));if(!hunk)return {ok:false,error:'This hunk is stale or no longer exists. Refresh Source Control and try again.'};const args=['apply','--cached','--recount','--whitespace=nowarn',...(action==='unstage'?['--reverse']:[]),'-'];const result=await boundedProcess('git',args,{cwd:root,timeoutMs:20000,outputLimit:128000,input:hunk.patch});return {...result,action,path:relPath,hunk:{id:hunk.id,header:hunk.header,added:hunk.added,removed:hunk.removed},receipt:result.ok?gitReceipt(root,`${action}-hunk`,`${relPath}\n${hunk.id}`,result):null};
}
async function gitConflictStage(root, stage, relPath) {
  const result=await boundedProcess('git',['show',`:${stage}:${relPath}`],{cwd:root,timeoutMs:10000,outputLimit:1024*1024});if(!result.ok)return {present:false,text:''};const text=String(result.stdout||'');if(text.includes('\u0000'))return {present:true,binary:true,text:''};return {present:true,text:text.slice(0,1000000),truncated:text.length>1000000};
}
async function workspaceGitConflict(rootPath, payload={}) {
  const root=path.resolve(rootPath||repoRoot);const relPath=String(payload.path||'');const target=safeWorkspacePath(root,relPath);if(!target.ok)return {ok:false,error:target.error};const unmerged=await boundedProcess('git',['ls-files','-u','--',relPath],{cwd:root,timeoutMs:10000,outputLimit:128000});if(!unmerged.ok||!String(unmerged.stdout||'').trim())return {ok:false,error:'This file is not currently unmerged.'};const [base,current,incoming,working]=await Promise.all([gitConflictStage(root,1,relPath),gitConflictStage(root,2,relPath),gitConflictStage(root,3,relPath),gitTextAt(root,'',relPath)]);if([base,current,incoming,working].some(item=>item.binary))return {ok:false,binary:true,error:'Binary conflicts require an external merge tool.'};if(!working.ok)return {ok:false,error:working.error||'Unable to read the conflicted working file.'};const digest=crypto.createHash('sha256').update(working.text||'').digest('hex');return {ok:true,path:relPath,baseText:base.text||'',currentText:current.text||'',incomingText:incoming.text||'',resultText:working.text||'',stages:{base:base.present,current:current.present,incoming:incoming.present},digest:`sha256:${digest}`,regions:(String(working.text||'').match(/^<<<<<<< .*$/gm)||[]).length,truncated:Boolean(base.truncated||current.truncated||incoming.truncated||working.truncated)};
}
async function workspaceGitResolve(rootPath, payload={}) {
  const root=path.resolve(rootPath||repoRoot);const relPath=String(payload.path||'');const target=safeWorkspacePath(root,relPath);if(!target.ok)return {ok:false,error:target.error};const content=String(payload.content??'');if(Buffer.byteLength(content,'utf8')>1000000||content.includes('\u0000'))return {ok:false,error:'Resolved text must be UTF-8 and no larger than 1 MB.'};if(/^(?:<<<<<<< |=======\s*$|>>>>>>> )/m.test(content))return {ok:false,error:'Conflict markers remain in the proposed resolution.'};const expected=String(payload.expectedDigest||'');if(!/^sha256:[a-f0-9]{64}$/.test(expected))return {ok:false,error:'A valid conflict snapshot digest is required.'};const unmerged=await boundedProcess('git',['ls-files','-u','--',relPath],{cwd:root,timeoutMs:10000,outputLimit:128000});if(!unmerged.ok||!String(unmerged.stdout||'').trim())return {ok:false,error:'Conflict state changed; refresh before saving.'};let before='';try{before=fs.readFileSync(target.target,'utf8');}catch(error){return {ok:false,error:String(error.message||error)}}const beforeDigest=crypto.createHash('sha256').update(before).digest('hex');if(expected!==`sha256:${beforeDigest}`)return {ok:false,error:'The working file changed after the merge editor opened. Reload the conflict before saving.'};fs.writeFileSync(target.target,content,'utf8');const result=await boundedProcess('git',['add','--',relPath],{cwd:root,timeoutMs:20000,outputLimit:128000});const afterDigest=crypto.createHash('sha256').update(content).digest('hex');return {...result,path:relPath,beforeDigest:`sha256:${beforeDigest}`,afterDigest:`sha256:${afterDigest}`,receipt:result.ok?gitReceipt(root,'resolve-conflict',`${relPath}\n${beforeDigest}\n${afterDigest}`,result):null};
}
async function workspaceGitAction(rootPath, action, relPath) {
  const root=path.resolve(rootPath || repoRoot);const command=String(action||'');const pathActions=new Set(['stage','unstage','discard']);if(pathActions.has(command)){const target=safeWorkspacePath(root,relPath);if(!target.ok)return {ok:false,error:target.error};}
  const argsByAction={stage:['add','--',String(relPath)],unstage:['restore','--staged','--',String(relPath)],discard:['restore','--worktree','--',String(relPath)],'stage-all':['add','--all'],'unstage-all':['restore','--staged','.']};const args=argsByAction[command];if(!args)return {ok:false,error:'Unsupported Git action.'};
  const result=await boundedProcess('git',args,{cwd:root,timeoutMs:20000,outputLimit:128000});return {...result,action:command,path:String(relPath||''),receipt:gitReceipt(root,command,String(relPath||''),result)};
}
async function workspaceGitCommit(rootPath, payload={}) {
  const root=path.resolve(rootPath || repoRoot);const message=String(payload.message||'').trim();if(!message||Buffer.byteLength(message,'utf8')>10000)return {ok:false,error:'Commit message must be between 1 and 10,000 UTF-8 bytes.'};const args=['commit',...(payload.amend?['--amend']:[]),'-m',message];const result=await boundedProcess('git',args,{cwd:root,timeoutMs:60000,outputLimit:256000});return {...result,message,receipt:gitReceipt(root,payload.amend?'amend':'commit',message,result)};
}
async function workspaceGitBranch(rootPath, payload={}) {
  const root=path.resolve(rootPath || repoRoot);const operation=String(payload.operation||'checkout');const name=String(payload.name||'').trim();if(!name||Buffer.byteLength(name,'utf8')>240)return {ok:false,error:'A valid branch name is required.'};const valid=await boundedProcess('git',['check-ref-format','--branch',name],{cwd:root,timeoutMs:10000,outputLimit:16000});if(!valid.ok)return {ok:false,error:String(valid.stderr||'Invalid branch name.')};const args=operation==='create'?['switch','-c',name]:operation==='checkout'?['switch',name]:null;if(!args)return {ok:false,error:'Unsupported branch operation.'};const result=await boundedProcess('git',args,{cwd:root,timeoutMs:30000,outputLimit:128000});return {...result,operation,name,receipt:gitReceipt(root,`branch-${operation}`,name,result)};
}
function safeGitRevision(value) { return /^[0-9a-fA-F]{7,64}$/.test(String(value||'')) ? String(value) : ''; }
function safeGitRemote(value) { return /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(String(value||'')) ? String(value) : ''; }
async function workspaceGitHistory(rootPath, payload={}) {
  const root=path.resolve(rootPath||repoRoot);const limit=Math.max(1,Math.min(300,Number(payload.limit||80)));
  const result=await boundedProcess('git',['log',`--max-count=${limit}`,'--date=iso-strict','--format=%H%x1f%h%x1f%an%x1f%ad%x1f%s%x1e'],{cwd:root,timeoutMs:15000,outputLimit:512000});
  if(!result.ok)return {...result,commits:[]};
  const commits=String(result.stdout||'').split('\x1e').filter(Boolean).map(row=>{const [hash,shortHash,author,date,subject]=row.split('\x1f');return {hash,shortHash,author,date,subject};}).filter(row=>row.hash).slice(0,limit);
  return {ok:true,commits};
}
async function workspaceGitRemotes(rootPath) {
  const root=path.resolve(rootPath||repoRoot);const result=await boundedProcess('git',['remote','-v'],{cwd:root,timeoutMs:10000,outputLimit:128000});
  if(!result.ok&&result.returncode!==0)return {...result,remotes:[]};const seen=new Map();
  String(result.stdout||'').split(/\r?\n/).filter(Boolean).forEach(line=>{const match=line.match(/^(\S+)\s+(\S+)\s+\((fetch|push)\)$/);if(!match)return;const row=seen.get(match[1])||{name:match[1],fetch:'',push:''};row[match[3]]=match[2];seen.set(match[1],row);});
  return {ok:true,remotes:[...seen.values()].slice(0,80)};
}
async function workspaceGitOperation(rootPath, payload={}) {
  const root=path.resolve(rootPath||repoRoot);const action=String(payload.action||'');const remote=safeGitRemote(payload.remote||'origin');const revision=safeGitRevision(payload.revision);let args=null;let detail='';
  if(action==='fetch'){args=['fetch','--prune',remote];detail=remote;}
  if(action==='pull'){args=['pull','--ff-only',remote];detail=remote;}
  if(action==='push'){args=['push',remote,'HEAD'];detail=remote;}
  if(action==='rebase-start'){const base=String(payload.base||'').trim();if(!base||base.length>240||/[\s;&|`$<>]/.test(base))return {ok:false,error:'A safe rebase base is required.'};args=['rebase',base];detail=base;}
  if(action==='rebase-continue'){args=['rebase','--continue'];detail='continue';}
  if(action==='rebase-abort'){args=['rebase','--abort'];detail='abort';}
  if(action==='cherry-pick'){if(!revision)return {ok:false,error:'Cherry-pick requires a 7–64 character commit SHA.'};args=['cherry-pick',revision];detail=revision;}
  if(action==='cherry-pick-abort'){args=['cherry-pick','--abort'];detail='abort';}
  if(!args)return {ok:false,error:'Unsupported governed Git operation.'};
  const result=await boundedProcess('git',args,{cwd:root,timeoutMs:120000,outputLimit:512000});return {...result,action,detail,receipt:gitReceipt(root,action,detail,result)};
}

function parseJsonc(text) {
  const source=String(text || '');let clean='';let quote='';let escaped=false;
  for(let index=0;index<source.length;index+=1){const char=source[index];const next=source[index+1];if(quote){clean+=char;if(escaped)escaped=false;else if(char==='\\')escaped=true;else if(char===quote)quote='';continue;}if(char==='"'||char==="'"){quote=char;clean+=char;continue;}if(char==='/'&&next==='/'){while(index<source.length&&source[index]!=='\n')index+=1;clean+='\n';continue;}if(char==='/'&&next==='*'){index+=2;while(index<source.length&&(source[index]!=='*'||source[index+1]!=='/'))index+=1;index+=1;continue;}clean+=char;}
  let normalized='';quote='';escaped=false;
  for(let index=0;index<clean.length;index+=1){const char=clean[index];if(quote){normalized+=char;if(escaped)escaped=false;else if(char==='\\')escaped=true;else if(char===quote)quote='';continue;}if(char==='"'||char==="'"){quote=char;normalized+=char;continue;}if(char===','){let cursor=index+1;while(/\s/.test(clean[cursor]||''))cursor+=1;if(clean[cursor]===']'||clean[cursor]==='}')continue;}normalized+=char;}
  return JSON.parse(normalized);
}
function taskCwd(root, candidate) { const target=path.resolve(root,String(candidate||'.'));return target===root||target.startsWith(`${root}${path.sep}`) ? target : ''; }
function taskEnvironment(value) { const source=value&&typeof value==='object'&&!Array.isArray(value)?value:{};const pairs=Object.entries(source).slice(0,60).filter(([key,item])=>/^[A-Za-z_][A-Za-z0-9_]{0,127}$/.test(key)&&typeof item==='string'&&Buffer.byteLength(item,'utf8')<=8192);return Object.fromEntries(pairs); }
function taskFingerprint(value) { return crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex').slice(0,16); }
function safeTaskRegexSource(value) { const source=String(value||'');if(!source||source.length>256||/\\[1-9]|\(\?[=!<]|\([^)]*[+*][^)]*\)[+*{]/.test(source))return '';try{new RegExp(source);return source;}catch(_){return '';} }
function normalizeTaskMatcher(value) {
  if(typeof value==='string'){const name=String(value).slice(0,80);return /^\$[A-Za-z0-9._-]+$/.test(name)?{name}:null;}
  if(!value||typeof value!=='object'||Array.isArray(value))return null;const pattern=Array.isArray(value.pattern)?value.pattern[0]:value.pattern;const regexp=safeTaskRegexSource(pattern?.regexp);const field=name=>{const number=Number(pattern?.[name]||0);return Number.isInteger(number)&&number>=1&&number<=20?number:0;};const background=value.background&&typeof value.background==='object'?{activeOnStart:Boolean(value.background.activeOnStart),beginsPattern:safeTaskRegexSource(value.background.beginsPattern),endsPattern:safeTaskRegexSource(value.background.endsPattern)}:null;return {name:String(value.base||value.owner||'$custom').slice(0,80),pattern:regexp?{regexp,file:field('file')||1,line:field('line'),column:field('column'),severity:field('severity'),message:field('message'),code:field('code')}:null,background};
}
function normalizeTaskMatchers(value) { return (Array.isArray(value)?value:[value]).map(normalizeTaskMatcher).filter(Boolean).slice(0,8); }
function workspaceTasks(rootPath) {
  const root=path.resolve(rootPath || repoRoot);let scripts={};try{const pkg=JSON.parse(fs.readFileSync(path.join(root,'package.json'),'utf8'));scripts=pkg.scripts&&typeof pkg.scripts==='object'&&!Array.isArray(pkg.scripts)?pkg.scripts:{ };}catch(_){}
  const tasks=Object.keys(scripts).sort().slice(0,120).map(script=>({id:`npm:${script}`,label:`npm: ${script}`,command:`npm run ${script}`,kind:'npm',script,source:'package.json'}));
  const configPath=path.join(root,'.vscode','tasks.json');
  try{
    const config=parseJsonc(fs.readFileSync(configPath,'utf8'));const declared=Array.isArray(config?.tasks)?config.tasks:[];
    declared.slice(0,120).forEach((definition,index)=>{if(!definition||typeof definition!=='object')return;const type=String(definition.type||'shell').toLowerCase();const label=String(definition.label||definition.taskName||definition.command||'').trim().slice(0,160);const args=Array.isArray(definition.args)?definition.args.filter(value=>typeof value==='string'||typeof value==='number'||typeof value==='boolean').slice(0,80).map(String):[];const cwd=taskCwd(root,definition.options?.cwd);const env=taskEnvironment(definition.options?.env);if(!label||!cwd||!['shell','process','npm'].includes(type))return;const problemMatchers=normalizeTaskMatchers(definition.problemMatcher);let task={id:'',label,kind:type,source:'.vscode/tasks.json',command:'',args,cwd:path.relative(root,cwd)||'.',env,isBackground:Boolean(definition.isBackground),problemMatchers,group:typeof definition.group==='string'?definition.group:String(definition.group?.kind||'').slice(0,40)};if(type==='npm'){const script=String(definition.script||definition.command||'').trim();if(!script||!Object.prototype.hasOwnProperty.call(scripts,script))return;task={...task,kind:'npm',script,command:`npm run ${script}`};}else{const command=String(definition.command||'').trim();if(!command||Buffer.byteLength(command,'utf8')>4096)return;task={...task,command};}task.id=`vscode:${index+1}:${taskFingerprint({type:task.kind,label:task.label,command:task.command,args:task.args,cwd:task.cwd,script:task.script||''})}`;tasks.push(task);});
  }catch(_){}
  return {ok:true,tasks:tasks.slice(0,240)};
}
function workspaceSettings(rootPath) {
  const root=path.resolve(rootPath||repoRoot);const file=path.join(root,'.vscode','settings.json');
  try { const value=parseJsonc(fs.readFileSync(file,'utf8'));return {ok:true,path:'.vscode/settings.json',settings:value&&typeof value==='object'&&!Array.isArray(value)?value:{},exists:true}; }
  catch(error) { if(error?.code==='ENOENT')return {ok:true,path:'.vscode/settings.json',settings:{},exists:false};return {ok:false,path:'.vscode/settings.json',settings:{},error:`Unable to parse workspace settings: ${String(error.message||error)}`}; }
}
function writeWorkspaceSettings(rootPath, value) {
  const root=path.resolve(rootPath||repoRoot);if(!value||typeof value!=='object'||Array.isArray(value))return {ok:false,error:'Workspace settings must be a JSON object.'};const encoded=JSON.stringify(value,null,2);if(Buffer.byteLength(encoded,'utf8')>512000)return {ok:false,error:'Workspace settings exceed 512 KiB.'};
  const target=safeWorkspacePath(root,'.vscode/settings.json');if(!target.ok)return target;try{fs.mkdirSync(path.dirname(target.target),{recursive:true});fs.writeFileSync(target.target,`${encoded}\n`,'utf8');const digest=crypto.createHash('sha256').update(`${root}\n${encoded}`).digest('hex');return {ok:true,path:'.vscode/settings.json',settings:value,receipt:{id:`SET-${digest.slice(0,16).toUpperCase()}`,digest:`sha256:${digest}`,evidence:'operator-initiated'}};}catch(error){return {ok:false,error:String(error.message||error)};}
}
function pytestTestNodes(root, files) { const nodes=[];for(const file of files.filter(item=>item.path.endsWith('.py'))){const selected=safeWorkspacePath(root,file.path);if(!selected.ok||Number(file.size||0)>512000)continue;let source='';try{source=fs.readFileSync(selected.target,'utf8');}catch(_){continue;}let activeClass='';for(const line of source.split(/\r?\n/)){const classMatch=line.match(/^class\s+(Test[A-Za-z0-9_]*)\b/);if(classMatch){activeClass=classMatch[1];continue;}const functionMatch=line.match(/^(\s*)def\s+(test_[A-Za-z0-9_]*)\b/);if(functionMatch){const selector=activeClass&&functionMatch[1].length?`${file.path}::${activeClass}::${functionMatch[2]}`:`${file.path}::${functionMatch[2]}`;nodes.push({id:selector,path:file.path,label:activeClass?`${activeClass}::${functionMatch[2]}`:functionMatch[2],framework:'pytest'});if(nodes.length>=1000)return nodes;}else if(line&&/^\S/.test(line)&&!line.startsWith('#'))activeClass='';}}return nodes; }
function workspaceTests(rootPath) {
  const root=path.resolve(rootPath||repoRoot);const tests=[];const exists=name=>fs.existsSync(path.join(root,name));let scripts={};try{scripts=JSON.parse(fs.readFileSync(path.join(root,'package.json'),'utf8'))?.scripts||{};}catch(_){}
  for(const [name,command] of Object.entries(scripts))if(/(?:^|:|-)(test|spec|e2e|unit)(?:$|:|-)/i.test(name))tests.push({id:`npm:${name}`,label:`npm: ${name}`,framework:'npm',command:`npm run ${name}`,debuggable:false,source:'package.json'});
  if(exists('pytest.ini')||exists('pyproject.toml')||exists('setup.cfg')||exists('tests'))tests.push({id:'python:pytest',label:'pytest',framework:'pytest',command:'python3 -m pytest',debuggable:true,source:'python workspace'});
  if(exists('manage.py'))tests.push({id:'python:django',label:'Django tests',framework:'django',command:'python3 manage.py test',debuggable:true,source:'manage.py'});
  const files=workspaceFileCandidates(root,3000).filter(item=>/(^|\/)(test|tests|spec|__tests__)\/|(?:^|\/)(test_|.*_test|.*\.spec|.*\.test)\.(?:py|js|jsx|ts|tsx)$/i.test(item.path)).slice(0,500).map(item=>({path:item.path,name:item.name||path.basename(item.path),size:Number(item.size||0)}));
  return {ok:true,tests:tests.slice(0,120),files,nodes:pytestTestNodes(root,files)};
}
async function workspaceTestsForTarget(rootPath,payload={}) {
  const root=path.resolve(rootPath||repoRoot);const target=payload?.target?.kind?executionTargetSummary(payload.target):executionTargetSummary();
  if(target.kind==='local')return {...workspaceTests(root),executionTarget:target};
  const base=target.kind==='ssh'?remotePath(target.remoteRoot||target.path||''):remotePath(target.workspaceFolder||'');if(!base)return {ok:false,error:'Selected test target has no workspace folder.',tests:[],files:[],nodes:[],executionTarget:target};
  const command=`cd ${shellQuote(base)} && printf 'MARKERS\\n' && for f in package.json pyproject.toml pytest.ini setup.cfg manage.py; do test -f "$f" && printf '%s\\n' "$f"; done && printf 'FILES\\n' && find . -maxdepth 6 -type f \( -path './tests/*' -o -path './test/*' -o -name 'test_*.py' -o -name '*_test.py' -o -name '*.test.js' -o -name '*.spec.ts' \) -printf '%p\\t%s\\n' 2>/dev/null | head -n 500`;
  const result=await runOnExecutionTarget(target,root,'sh',['-lc',command],{timeoutMs:30000,outputLimit:256000});const lines=String(result.stdout||'').split(/\r?\n/);const marker=lines.indexOf('MARKERS');const fileMarker=lines.indexOf('FILES');const configs=(marker>=0&&fileMarker>marker?lines.slice(marker+1,fileMarker):[]).filter(Boolean);const files=(fileMarker>=0?lines.slice(fileMarker+1):[]).map(line=>{const [file,size='']=line.split('\t');return {path:String(file||'').replace(/^\.\//,''),name:path.basename(file||''),size:Number(size)||0};}).filter(item=>targetRelativePath(item.path));const tests=[];if(configs.some(item=>item==='package.json'))tests.push({id:'npm:test',label:'npm test',framework:'npm',command:'npm test',debuggable:false,source:'package.json'});if(configs.some(item=>['pyproject.toml','pytest.ini','setup.cfg'].includes(item))||files.some(item=>item.path.endsWith('.py')))tests.push({id:'python:pytest',label:'pytest',framework:'pytest',command:'python3 -m pytest',debuggable:true,source:'remote workspace'});if(configs.includes('manage.py'))tests.push({id:'python:django',label:'Django tests',framework:'django',command:'python3 manage.py test',debuggable:true,source:'manage.py'});return {...result,tests,files,nodes:[],executionTarget:target,remoteRoot:base,truncated:files.length>=500};
}
async function runWorkspaceTest(rootPath,payload) {
  const root=path.resolve(rootPath||repoRoot);const id=typeof payload==='string'?payload:payload?.id;const file=typeof payload==='object'?String(payload?.file||''):'';const node=typeof payload==='object'?String(payload?.node||''):'';const selectedTarget=typeof payload==='object'?payload?.target:null;const catalog=await workspaceTestsForTarget(root,payload||{});const test=catalog.tests.find(item=>item.id===String(id||''));if(!test)return {ok:false,error:'Test target is not declared by this workspace or execution target.'};const selected= file && (!selectedTarget||selectedTarget.kind==='local') ? safeWorkspacePath(root,file) : null;if(selected&&(!selected.ok||(!fs.existsSync(selected.target)||!fs.statSync(selected.target).isFile())))return {ok:false,error:'Selected test file is outside this workspace or no longer exists.'};const selectedNode=node?catalog.nodes.find(item=>item.id===node):null;if(node&&!selectedNode)return {ok:false,error:'Selected test node is outside this workspace or no longer exists.'};if((selected||selectedNode)&&test.id!=='python:pytest')return {ok:false,error:'Focused file and test-node runs currently support the pytest target.'};if(selected&&selectedNode&&selectedNode.path!==file)return {ok:false,error:'Selected test node does not belong to the selected test file.'};let result;if(test.id.startsWith('npm:'))result=await runOnExecutionTarget(selectedTarget,root,'npm',['run',test.id.slice(4)],{timeoutMs:600000,outputLimit:768000});else if(test.id==='python:pytest')result=await runOnExecutionTarget(selectedTarget,root,'python3',['-m','pytest',...(selectedNode?[selectedNode.id]:selected?[file]:[])],{timeoutMs:600000,outputLimit:768000});else result=await runOnExecutionTarget(selectedTarget,root,'python3',['manage.py','test'],{timeoutMs:600000,outputLimit:768000});const target=selectedNode?.id||file;const executionTarget=executionTargetSummary(selectedTarget||activeExecutionTarget);const digest=crypto.createHash('sha256').update(`${root}\n${test.id}\n${target}\n${executionTarget.kind}\n${result.stdout}\n${result.stderr}\n${result.returncode}`).digest('hex');return {...result,test,file:target,node:selectedNode?.id||'',executionTarget,receipt:{id:`TEST-${digest.slice(0,16).toUpperCase()}`,digest:`sha256:${digest}`,evidence:'operator-initiated',mode:`${test.framework}:${executionTarget.kind}`}};
}
async function runWorkspaceTask(rootPath,payload) {
  const root=path.resolve(rootPath || repoRoot);const taskId=String(typeof payload==='string'?payload:payload?.id||'');const selectedTarget=typeof payload==='object'?payload?.target:null;if(!/^[A-Za-z0-9:_./-]{1,120}$/.test(taskId))return {ok:false,error:'Unsupported task identifier.'};const listed=workspaceTasks(root).tasks;const task=listed.find(item=>item.id===taskId)||listed.find(item=>item.kind==='npm'&&item.script===taskId);if(!task)return {ok:false,error:'Task is not declared in package.json or .vscode/tasks.json.'};const cwd=taskCwd(root,task.cwd);if(!cwd)return {ok:false,error:'Task working directory escaped the active workspace.'};const env={...process.env,...taskEnvironment(task.env)};let result;if(task.kind==='npm')result=await runOnExecutionTarget(selectedTarget,root,'npm',['run',task.script],{cwd,env,timeoutMs:60000,outputLimit:512000});else result=await runOnExecutionTarget(selectedTarget,root,task.command,task.args,{cwd,env,timeoutMs:60000,outputLimit:512000,shell:task.kind==='shell'});const executionTarget=executionTargetSummary(selectedTarget||activeExecutionTarget);const digest=crypto.createHash('sha256').update(`${root}\n${task.id}\n${task.kind}\n${task.command}\n${task.args.join('\u0000')}\n${executionTarget.kind}\n${result.stdout}\n${result.stderr}\n${result.returncode}`).digest('hex');return {...result,executionTarget,task:{id:task.id,label:task.label,source:task.source,kind:task.kind},receipt:{id:`TASK-${digest.slice(0,16).toUpperCase()}`,digest:`sha256:${digest}`,evidence:'operator-initiated',mode:`${task.source}:${executionTarget.kind}`}};
}

function safeWorkspacePath(rootPath, relPath) {
  const root = path.resolve(rootPath || repoRoot);
  const target = path.resolve(root, relPath || '');
  if (target === root || !target.startsWith(`${root}${path.sep}`)) {
    return { ok: false, error: 'path escaped workspace', root, target };
  }
  return { ok: true, root, target };
}

function boundedProcess(command, args, options = {}) {
  const timeoutMs = Math.max(500, Math.min(Number(options.timeoutMs || 30000), 900000));
  const outputLimit = Math.max(4096, Math.min(Number(options.outputLimit || 512000), 1024 * 1024));
  return new Promise(resolve => {
    let stdout = ''; let stderr = ''; let settled = false; let timedOut = false; let timer = 0;
    const finish = result => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({ ...result, stdout:stdout.slice(-outputLimit), stderr:stderr.slice(-outputLimit), timed_out:timedOut });
    };
    const input=typeof options.input==='string'?options.input:'';if(Buffer.byteLength(input,'utf8')>512000){finish({ok:false,error:'process input exceeded 512 KiB',returncode:null});return;}let child;
    try {
      child = spawn(command, args, { cwd:options.cwd || repoRoot, env:options.env || process.env, stdio:[input?'pipe':'ignore','pipe','pipe'], shell:Boolean(options.shell), windowsHide:true });
    } catch (error) {
      finish({ ok:false, error:String(error.message || error), returncode:null });
      return;
    }
    const append = (key, chunk) => {
      if (key === 'out') stdout = `${stdout}${String(chunk)}`.slice(-outputLimit);
      else stderr = `${stderr}${String(chunk)}`.slice(-outputLimit);
    };
    child.stdout?.on('data', chunk => append('out',chunk));
    child.stderr?.on('data', chunk => append('err',chunk));
    child.once('error', error => finish({ ok:false, error:String(error.message || error), returncode:null }));
    child.once('close', (code, signal) => finish({ ok:code === 0 && !timedOut, returncode:code, signal:signal || '', error:timedOut ? `process timed out after ${timeoutMs}ms` : '' }));
    if(input)child.stdin.end(input);
    timer = setTimeout(() => {
      timedOut = true;
      if (!child.killed) child.kill('SIGTERM');
    }, timeoutMs);
  });
}

function taskProblemPath(root,cwd,value) { const candidate=String(value||'').replace(/^file:\/\//,'');const target=path.resolve(path.isAbsolute(candidate)?candidate:path.join(cwd,candidate));return target===root||target.startsWith(`${root}${path.sep}`)?path.relative(root,target).replace(/\\/g,'/'):''; }
function taskProblemFromLine(root,cwd,line,matchers=[]) {
  const text=String(line||'').slice(0,8000);const builtins=matchers.map(item=>item.name).filter(Boolean);let match=null;let row=null;
  if(builtins.some(name=>/^\$(?:tsc|tsc-watch)$/i.test(name))&&(match=text.match(/^(.+?)\((\d+),(\d+)\):\s*(error|warning|info)\s*([A-Za-z]+\d+)?:?\s*(.+)$/i)))row={file:match[1],line:Number(match[2]),column:Number(match[3]),severity:match[4],code:match[5]||'',message:match[6]};
  if(!row&&builtins.length&&(match=text.match(/^(.+?):(\d+)(?::(\d+))?:\s*(fatal error|error|warning|info|note)\s*:?\s*(.+)$/i)))row={file:match[1],line:Number(match[2]),column:Number(match[3]||1),severity:match[4],code:'',message:match[5]};
  if(!row){for(const matcher of matchers){if(!matcher.pattern?.regexp)continue;match=text.match(new RegExp(matcher.pattern.regexp));if(!match)continue;const field=name=>matcher.pattern[name]?match[matcher.pattern[name]]:'';row={file:field('file'),line:Number(field('line')||1),column:Number(field('column')||1),severity:field('severity')||'error',code:field('code')||'',message:field('message')||text};break;}}
  if(!row)return null;const file=taskProblemPath(root,cwd,row.file);if(!file)return null;const severity=/warn/i.test(row.severity)?'warning':/info|note/i.test(row.severity)?'info':'error';return {file,line:Math.max(1,Number(row.line)||1),column:Math.max(1,Number(row.column)||1),severity,code:String(row.code||'').slice(0,80),message:String(row.message||'').trim().slice(0,2000)};
}
class WorkspaceTaskHost {
  constructor(){this.sessions=new Map();this.sequence=0;}
  summary(session){return {id:session.id,status:session.status,pid:session.process?.pid||null,task:{id:session.task.id,label:session.task.label,source:session.task.source,kind:session.task.kind,group:session.task.group||'',isBackground:Boolean(session.task.isBackground)},startedAt:session.startedAt,problems:session.problems.slice(-500)};}
  emit(session,message){if(session.sender&&!session.sender.isDestroyed())session.sender.send('beast:workspace-task-message',{session:this.summary(session),...message});}
  list(){return [...this.sessions.values()].map(session=>this.summary(session));}
  start(rootPath,id,sender){const root=path.resolve(rootPath||repoRoot);const listed=workspaceTasks(root).tasks;const task=listed.find(item=>item.id===String(id||''));if(!task)throw new Error('Task is not declared in package.json or .vscode/tasks.json.');const cwd=taskCwd(root,task.cwd);if(!cwd)throw new Error('Task working directory escaped the active workspace.');const command=task.kind==='npm'?'npm':task.command;const args=task.kind==='npm'?['run',task.script]:task.args;const env={...process.env,...taskEnvironment(task.env)};const processRef=spawn(command,args,{cwd,env,stdio:['ignore','pipe','pipe'],shell:task.kind==='shell',windowsHide:true});const idValue=`workspace-task-${Date.now()}-${++this.sequence}`;const session={id:idValue,process:processRef,sender,root,cwd,task,status:task.isBackground?'background-starting':'running',startedAt:Date.now(),stdout:'',stderr:'',lineBuffer:'',problems:[],timer:0,finished:false};this.sessions.set(idValue,session);
    const background=(task.problemMatchers||[]).map(item=>item.background).find(Boolean)||null;const begins=background?.beginsPattern?new RegExp(background.beginsPattern):null;const ends=background?.endsPattern?new RegExp(background.endsPattern):null;if(task.isBackground&&background?.activeOnStart)session.status='background-active';
    const inspect=line=>{if(task.isBackground&&begins?.test(line))session.status='background-active';if(task.isBackground&&ends?.test(line))session.status='background-ready';const problem=taskProblemFromLine(root,cwd,line,task.problemMatchers||[]);if(problem&&!session.problems.some(item=>item.file===problem.file&&item.line===problem.line&&item.column===problem.column&&item.message===problem.message))session.problems.push(problem);};
    const append=(stream,chunk)=>{const value=String(chunk||'');if(stream==='stdout')session.stdout=`${session.stdout}${value}`.slice(-512000);else session.stderr=`${session.stderr}${value}`.slice(-512000);session.lineBuffer+=value;let cut;while((cut=session.lineBuffer.indexOf('\n'))>=0){inspect(session.lineBuffer.slice(0,cut).replace(/\r$/,''));session.lineBuffer=session.lineBuffer.slice(cut+1);}this.emit(session,{type:'output',stream,text:value});};
    const finish=(code,signal,error='')=>{if(session.finished)return;session.finished=true;clearTimeout(session.timer);if(session.lineBuffer)inspect(session.lineBuffer);session.status=error?'error':code===0?'completed':'failed';const digest=crypto.createHash('sha256').update(`${root}\n${task.id}\n${session.stdout}\n${session.stderr}\n${code}\n${JSON.stringify(session.problems)}`).digest('hex');const receipt={id:`TASK-${digest.slice(0,16).toUpperCase()}`,digest:`sha256:${digest}`,evidence:'operator-initiated',mode:task.source};this.emit(session,{type:'exit',ok:code===0&&!error,returncode:code,signal:signal||'',error,stdout:session.stdout,stderr:session.stderr,problems:session.problems,receipt});this.sessions.delete(session.id);};
    processRef.stdout?.on('data',chunk=>append('stdout',chunk));processRef.stderr?.on('data',chunk=>append('stderr',chunk));processRef.once('error',error=>finish(null,'',String(error.message||error)));processRef.once('close',(code,signal)=>finish(code,signal));if(!task.isBackground)session.timer=setTimeout(()=>{if(!processRef.killed)processRef.kill('SIGTERM');finish(null,'SIGTERM','Task timed out after 10 minutes.');},600000);this.emit(session,{type:'started'});return this.summary(session);
  }
  stop(id){const session=this.sessions.get(String(id||''));if(!session)return {ok:true,status:'stopped'};this.sessions.delete(session.id);session.finished=true;session.status='stopped';clearTimeout(session.timer);if(!session.process.killed)session.process.kill('SIGTERM');this.emit(session,{type:'stopped'});return {ok:true,...this.summary(session)};}
  stopAll(){return this.list().map(session=>this.stop(session.id));}
}
const workspaceTaskHost=new WorkspaceTaskHost();

async function executeNotebookCell(rootPath, payload = {}) {
  const root = path.resolve(rootPath || activeWorkspaceRoot || repoRoot);
  const code = String(payload.code || '');
  const language = String(payload.language || 'python').toLowerCase();
  if (!fs.existsSync(root) || !fs.statSync(root).isDirectory()) return { ok:false, error:'workspace root does not exist' };
  if (language !== 'python') return { ok:false, error:'Only the isolated Python cell runner is available in this build.' };
  if (!code.trim()) return { ok:false, error:'Notebook cell is empty.' };
  if (Buffer.byteLength(code,'utf8') > 64 * 1024) return { ok:false, error:'Notebook cell exceeds the 64 KiB safety limit.' };
  const startedAt = Date.now();
  const result = await boundedProcess('python3',['-I','-c',code],{
    cwd:root, timeoutMs:payload.timeoutMs || 30000,
    env:{ PATH:process.env.PATH || '', PYTHONNOUSERSITE:'1', BEAST_NOTEBOOK_EXECUTION:'1', BEAST_ACTIVE_WORKSPACE:root },
  });
  const digest = crypto.createHash('sha256').update(`${root}\n${code}\n${result.stdout}\n${result.stderr}\n${result.returncode}`).digest('hex');
  return {
    ...result, language, root, started_at:startedAt, duration_ms:Date.now()-startedAt,
    receipt:{ id:`NB-${digest.slice(0,16).toUpperCase()}`, digest:`sha256:${digest}`, mode:'explicit-local-cell', evidence:'operator-initiated' },
  };
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
let activeExecutionTarget={kind:'local',label:'Local workspace',root:activeWorkspaceRoot||repoRoot,transport:'local'};

function remoteSshArgs(host, remoteCommand) {
  return ['-o','BatchMode=yes','-o','ConnectTimeout=7','-o','StrictHostKeyChecking=yes',host,remoteCommand];
}

function shellQuote(value) { return `'${String(value ?? '').replace(/'/g, `'\\''`)}'`; }
function containerId(value) { const id=String(value||'').trim();return /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(id)?id:''; }
function executionTargetSummary(target=activeExecutionTarget) {
  const base={kind:'local',label:'Local workspace',root:activeWorkspaceRoot||repoRoot,transport:'local'};
  if(target?.kind==='ssh')return {kind:'ssh',label:`SSH · ${target.host}`,host:target.host,path:target.path||target.remoteRoot||'~',remoteRoot:target.remoteRoot||target.path||'~',transport:'ssh'};
  if(target?.kind==='container')return {kind:'container',label:`Container · ${target.name||target.containerId}`,containerId:target.containerId,name:target.name||target.containerId,root:target.root||activeWorkspaceRoot||repoRoot,workspaceFolder:target.workspaceFolder||'/workspace',transport:'docker'};
  return base;
}
function setActiveExecutionTarget(target={}) {
  if(target.kind==='ssh') {
    const host=remoteTarget(target.host || lastRemoteWorkspace?.host);const remoteRoot=remotePath(target.remoteRoot || target.path || lastRemoteWorkspace?.path || '~');
    if(!host||!remoteRoot)return {ok:false,error:'SSH target requires a verified host and safe remote path.',target:executionTargetSummary()};
    activeExecutionTarget={kind:'ssh',host,path:remoteRoot,remoteRoot,label:`SSH · ${host}`,transport:'ssh'};
  } else if(target.kind==='container') {
    const id=containerId(target.containerId || target.id || target.name);const workspaceFolder=remotePath(target.workspaceFolder || target.path || '/workspace');
    if(!id||!workspaceFolder)return {ok:false,error:'Container target requires a safe container id/name and workspace folder.',target:executionTargetSummary()};
    activeExecutionTarget={kind:'container',containerId:id,name:String(target.name||id),root:path.resolve(target.root||activeWorkspaceRoot||repoRoot),workspaceFolder,label:`Container · ${String(target.name||id)}`,transport:'docker'};
  } else activeExecutionTarget={kind:'local',label:'Local workspace',root:activeWorkspaceRoot||repoRoot,transport:'local'};
  return {ok:true,target:executionTargetSummary()};
}
async function listExecutionTargets(rootPath=activeWorkspaceRoot||repoRoot) {
  const local={kind:'local',label:'Local workspace',root:path.resolve(rootPath||repoRoot),active:activeExecutionTarget.kind==='local',transport:'local'};
  const targets=[local];
  if(lastRemoteWorkspace)targets.push({...executionTargetSummary({kind:'ssh',...lastRemoteWorkspace,remoteRoot:lastRemoteWorkspace.path}),active:activeExecutionTarget.kind==='ssh'&&activeExecutionTarget.host===lastRemoteWorkspace.host});
  const containers=await inspectDevContainers(rootPath).catch(error=>({ok:false,error:String(error.message||error),containers:[]}));
  for(const item of containers.containers||[])targets.push({kind:'container',label:`Container · ${item.name||item.id}`,containerId:item.id,name:item.name,root:path.resolve(rootPath||repoRoot),workspaceFolder:containers.config?.workspaceFolder||'/workspace',status:item.status,active:activeExecutionTarget.kind==='container'&&(activeExecutionTarget.containerId===item.id||activeExecutionTarget.name===item.name),transport:'docker'});
  return {ok:true,active:executionTargetSummary(),targets,containers};
}
async function runOnExecutionTarget(target, rootPath, command, args=[], options={}) {
  const selected=target?.kind ? executionTargetSummary(target) : executionTargetSummary();
  const root=path.resolve(rootPath||activeWorkspaceRoot||repoRoot);
  if(selected.kind==='ssh') {
    const remoteRoot=remotePath(selected.remoteRoot||selected.path||'~');const host=remoteTarget(selected.host);
    if(!host||!remoteRoot)return {ok:false,error:'SSH execution target is not connected.'};
    const relative=path.relative(root,path.resolve(options.cwd||root));
    const remoteCwd=relative&&!relative.startsWith('..')&&!path.isAbsolute(relative)?`${remoteRoot.replace(/\/$/,'')}/${relative.replace(/\\/g,'/')}`:remoteRoot;
    const remoteCommand=`cd ${shellQuote(remoteCwd)} && ${[command,...args].map(shellQuote).join(' ')}`;
    return boundedProcess('ssh',remoteSshArgs(host,remoteCommand),{timeoutMs:options.timeoutMs||60000,outputLimit:options.outputLimit||512000});
  }
  if(selected.kind==='container') {
    const id=containerId(selected.containerId||selected.name);const base=remotePath(selected.workspaceFolder||'/workspace');
    if(!id||!base)return {ok:false,error:'Container execution target is not attached.'};
    const relative=path.relative(root,path.resolve(options.cwd||root));
    const cwd=relative&&!relative.startsWith('..')&&!path.isAbsolute(relative)?`${base.replace(/\/$/,'')}/${relative.replace(/\\/g,'/')}`:base;
    return boundedProcess('docker',['exec','-i','-w',cwd,id,command,...args],{timeoutMs:options.timeoutMs||60000,outputLimit:options.outputLimit||512000});
  }
  return boundedProcess(command,args,{cwd:options.cwd||root,env:options.env||process.env,timeoutMs:options.timeoutMs||60000,outputLimit:options.outputLimit||512000,shell:Boolean(options.shell)});
}

function targetWorkspaceBase(target, rootPath) {
  const selected = target?.kind ? executionTargetSummary(target) : executionTargetSummary();
  if (selected.kind === 'ssh') return { selected, base: remotePath(selected.remoteRoot || selected.path || '') };
  if (selected.kind === 'container') return { selected, base: remotePath(selected.workspaceFolder || '') };
  return { selected, base: path.resolve(rootPath || activeWorkspaceRoot || repoRoot) };
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
  const encoded=Buffer.from(content,'utf8').toString('base64'); const command=`mkdir -p ${shellQuote(path.posix.dirname(remoteFile))} && printf %s ${shellQuote(encoded)} | base64 -d > ${shellQuote(remoteFile)}`; const result=await runOnExecutionTarget(selected, rootPath, 'sh', ['-lc', command], {timeoutMs:20000,outputLimit:32000}); const digest=`sha256:${crypto.createHash('sha256').update(content).digest('hex')}`; return {...result,path:relative,remotePath:remoteFile,digest,target:selected,receipt:result.ok?gitReceipt(base,'write-file',relative,result):null};
}

async function probeRemoteWorkspace(payload = {}) {
  const host = remoteTarget(payload.host); const target = remotePath(payload.path || '~');
  if (!host || !target) return { ok:false, error:'Remote host or path contains unsupported characters.' };
  const result = await boundedProcess('ssh',remoteSshArgs(host,`test -d ${target} && printf 'BEAST_REMOTE_READY\\n' && cd ${target} && pwd`),{ timeoutMs:10000, outputLimit:32000 });
  const lines=String(result.stdout || '').trim().split(/\r?\n/);
  const resolved=lines.find(line => line && line !== 'BEAST_REMOTE_READY') || '';
  const summary={ ...result, host, path:target, remote_root:resolved, transport:'ssh', verification:'strict-known-host' };if(summary.ok){lastRemoteWorkspace={host,path:resolved || target};summary.target=setActiveExecutionTarget({kind:'ssh',host,remoteRoot:resolved||target}).target;}return summary;
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

async function reconnectRemoteWorkspace() { if(!lastRemoteWorkspace)return {ok:false,error:'No verified remote workspace is available to reconnect.'};return probeRemoteWorkspace(lastRemoteWorkspace); }
async function readRemoteWorkspaceFile(payload={}) { const host=remoteTarget(payload.host || lastRemoteWorkspace?.host);const target=remotePath(payload.path || '');if(!host||!target)return {ok:false,error:'Remote host or file path contains unsupported characters.'};const result=await boundedProcess('ssh',remoteSshArgs(host,`test -f ${target} && head -c 200000 -- ${target}`),{timeoutMs:15000,outputLimit:220000});return {...result,host,path:target,content:String(result.stdout||''),transport:'ssh',verification:'strict-known-host'}; }
async function writeRemoteWorkspaceFile(payload={}) { const host=remoteTarget(payload.host || lastRemoteWorkspace?.host);const target=remotePath(payload.path || '');const content=String(payload.content || '');const expectedDigest=/^[a-f0-9]{64}$/i.test(String(payload.expectedDigest||''))?String(payload.expectedDigest).toLowerCase():'';if(!host||!target)return {ok:false,error:'Remote host or file path contains unsupported characters.'};if(Buffer.byteLength(content,'utf8')>200000)return {ok:false,error:'Remote file exceeds the 200 KiB write limit.'};if(expectedDigest){const current=await boundedProcess('ssh',remoteSshArgs(host,`test -f ${target} && sha256sum -- ${target}`),{timeoutMs:15000,outputLimit:32000});const actual=String(current.stdout||'').trim().match(/^([a-f0-9]{64})\b/i)?.[1]?.toLowerCase()||'';if(!current.ok||actual!==expectedDigest)return {ok:false,conflict:true,error:'Remote file changed since it was opened. Reload or compare before saving.',host,path:target,expectedDigest,actualDigest:actual,transport:'ssh',verification:'strict-known-host'};}const encoded=Buffer.from(content,'utf8').toString('base64');const result=await boundedProcess('ssh',remoteSshArgs(host,`printf %s ${encoded} | base64 -d > ${target}`),{timeoutMs:15000,outputLimit:32000});const digest=crypto.createHash('sha256').update(`${host}\n${target}\n${content}`).digest('hex');return {...result,host,path:target,transport:'ssh',verification:'strict-known-host',receipt:{id:`RFS-${digest.slice(0,16).toUpperCase()}`,digest:`sha256:${digest}`,evidence:'operator-initiated'}}; }
async function runRemoteTerminal(payload={}) { const host=remoteTarget(payload.host || lastRemoteWorkspace?.host);const command=String(payload.command || '').trim();if(!host||!command||Buffer.byteLength(command,'utf8')>16000)return {ok:false,error:'Remote host or command is outside allowed bounds.'};const result=await boundedProcess('ssh',remoteSshArgs(host,command),{timeoutMs:Math.max(1000,Math.min(Number(payload.timeoutMs||30000),60000)),outputLimit:512000});const digest=crypto.createHash('sha256').update(`${host}\n${command}\n${result.stdout}\n${result.stderr}\n${result.returncode}`).digest('hex');return {...result,host,command,transport:'ssh',verification:'strict-known-host',receipt:{id:`RTERM-${digest.slice(0,16).toUpperCase()}`,digest:`sha256:${digest}`,evidence:'operator-initiated'}}; }
function devContainerConfig(rootPath) { const root=path.resolve(rootPath||repoRoot);const file=path.join(root,'.devcontainer','devcontainer.json');try{const raw=JSON.parse(fs.readFileSync(file,'utf8'));const image=String(raw?.image||'');if(image&&!/^[A-Za-z0-9][A-Za-z0-9._/:@-]{0,255}$/.test(image))return {ok:false,error:'Dev container image is outside allowed syntax.'};return {ok:true,root,file,config:{name:String(raw?.name||path.basename(root)).slice(0,120),image,workspaceFolder:String(raw?.workspaceFolder||`/workspaces/${path.basename(root)}`).slice(0,240),dockerFile:Boolean(raw?.dockerFile),compose:Boolean(raw?.dockerComposeFile)}};}catch(_){return {ok:false,error:'No readable .devcontainer/devcontainer.json exists in this workspace.'};} }
async function inspectDevContainers(rootPath) { const config=devContainerConfig(rootPath);if(!config.ok)return {...config,containers:[]};const workspaceKey=crypto.createHash('sha256').update(config.root).digest('hex').slice(0,20);const result=await boundedProcess('docker',['ps','-a','--filter',`label=beast.workspace=${workspaceKey}`,'--format','{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}'],{timeoutMs:10000,outputLimit:64000});const containers=String(result.stdout||'').split(/\r?\n/).filter(Boolean).map(line=>{const [id,name,image,status]=line.split('\t');return {id,name,image,status,managed:true};});return {...config,ok:result.ok,containers,error:result.ok?'':String(result.stderr||'Docker inspection failed.').trim(),workspaceKey}; }
async function startDevContainer(rootPath) { const state=await inspectDevContainers(rootPath);if(!state.ok) return state;const running=state.containers.find(item=>/\bUp\b/i.test(item.status));if(running)return {...state,attached:running,target:setActiveExecutionTarget({kind:'container',containerId:running.id,name:running.name,root:state.root,workspaceFolder:state.config.workspaceFolder}).target};if(!state.config.image)return {...state,ok:false,error:'Automatic start currently supports image-based devcontainer.json only.'};const name=`beast-dev-${state.workspaceKey}`;const result=await boundedProcess('docker',['run','-d','--rm','--name',name,'--label',`beast.workspace=${state.workspaceKey}`,'--label','beast.managed=true','-v',`${state.root}:${state.config.workspaceFolder}`,'-w',state.config.workspaceFolder,state.config.image,'sleep','infinity'],{timeoutMs:120000,outputLimit:64000});if(!result.ok)return {...state,ok:false,error:String(result.stderr||'Dev container start failed.').trim()};const next=await inspectDevContainers(state.root);const attached=next.containers.find(item=>/\bUp\b/i.test(item.status))||next.containers[0];return {...next,attached,target:attached?setActiveExecutionTarget({kind:'container',containerId:attached.id,name:attached.name,root:state.root,workspaceFolder:state.config.workspaceFolder}).target:executionTargetSummary()}; }
async function stopDevContainer(rootPath,id) { const state=await inspectDevContainers(rootPath);const target=state.containers.find(item=>item.id===String(id||'')||item.name===String(id||''));if(!target)return {...state,ok:false,error:'Only BEAST-managed containers for this workspace can be stopped.'};const result=await boundedProcess('docker',['stop',target.id],{timeoutMs:30000,outputLimit:32000});return result.ok?inspectDevContainers(rootPath):{...state,ok:false,error:String(result.stderr||'Dev container stop failed.').trim()}; }
async function attachDevContainer(rootPath,id) { const state=await inspectDevContainers(rootPath);if(!state.ok)return state;const target=state.containers.find(item=>item.id===String(id||'')||item.name===String(id||''))||state.containers.find(item=>/\bUp\b/i.test(item.status))||state.containers[0];if(!target)return {...state,ok:false,error:'No BEAST-managed dev container is available to attach.'};return {...state,attached:target,target:setActiveExecutionTarget({kind:'container',containerId:target.id,name:target.name,root:state.root,workspaceFolder:state.config.workspaceFolder}).target}; }
async function rebuildDevContainer(rootPath) { const state=devContainerConfig(rootPath);if(!state.ok)return {...state,containers:[]};if(state.config.compose)return {...state,ok:false,error:'Compose rebuild requires the operator to run docker compose from a trusted terminal; BEAST currently manages image and Dockerfile dev containers.'};let result;if(state.config.dockerFile){const dockerfile=path.join(state.root,'.devcontainer','Dockerfile');if(!fs.existsSync(dockerfile))return {...state,ok:false,error:'devcontainer.json references a Dockerfile but .devcontainer/Dockerfile was not found.'};const tag=`beast-dev-image-${crypto.createHash('sha256').update(state.root).digest('hex').slice(0,20)}`;result=await boundedProcess('docker',['build','-t',tag,'-f',dockerfile,state.root],{timeoutMs:600000,outputLimit:512000});if(result.ok)state.config.image=tag;}else if(state.config.image)result=await boundedProcess('docker',['pull',state.config.image],{timeoutMs:600000,outputLimit:512000});else return {...state,ok:false,error:'Dev container rebuild requires image or Dockerfile.'};return result.ok?startDevContainer(state.root):{...state,ok:false,error:String(result.stderr||'Dev container rebuild failed.').trim(),stdout:result.stdout,stderr:result.stderr}; }
async function devContainerLogs(rootPath,id) { const state=await inspectDevContainers(rootPath);const target=state.containers.find(item=>item.id===String(id||'')||item.name===String(id||''))||state.containers[0];if(!target)return {...state,ok:false,error:'No BEAST-managed dev container is available for logs.',logs:''};const result=await boundedProcess('docker',['logs','--tail','300',target.id],{timeoutMs:15000,outputLimit:256000});return {...result,container:target,logs:`${result.stdout||''}${result.stderr||''}`.slice(-256000)}; }
async function runDevContainerTerminal(rootPath,payload={}) { const state=await inspectDevContainers(rootPath);const target=state.containers.find(item=>item.id===String(payload.id||'')||item.name===String(payload.id||''))||state.containers.find(item=>/\bUp\b/i.test(item.status))||state.containers[0];const command=String(payload.command||'').trim();if(!target)return {...state,ok:false,error:'No BEAST-managed dev container is available for terminal execution.'};if(!command||Buffer.byteLength(command,'utf8')>16000||/[\0]/.test(command))return {...state,ok:false,error:'Container terminal command must be 1–16000 bytes.'};const result=await boundedProcess('docker',['exec','-i','-w',state.config.workspaceFolder,target.id,'sh','-lc',command],{timeoutMs:Math.max(1000,Math.min(Number(payload.timeoutMs||30000),120000)),outputLimit:512000});const digest=crypto.createHash('sha256').update(`${target.id}\n${command}\n${result.stdout}\n${result.stderr}\n${result.returncode}`).digest('hex');return {...result,container:target,transport:'docker-exec',receipt:{id:`DCTR-${digest.slice(0,16).toUpperCase()}`,digest:`sha256:${digest}`,evidence:'operator-initiated'}}; }

function mutateWorkspaceFile(rootPath, operation = {}) {
  const op = String(operation.op || '').trim();
  const pathCheck = safeWorkspacePath(rootPath || repoRoot, operation.path || '');
  if (!pathCheck.ok) return { ok: false, error: pathCheck.error, op };
  try {
    if (op === 'create_file') {
      fs.mkdirSync(path.dirname(pathCheck.target), { recursive: true });
      if (!fs.existsSync(pathCheck.target)) fs.writeFileSync(pathCheck.target, String(operation.content || ''), 'utf8');
      return { ok: true, op, path: path.relative(pathCheck.root, pathCheck.target) };
    }
    if (op === 'create_folder') {
      fs.mkdirSync(pathCheck.target, { recursive: true });
      return { ok: true, op, path: path.relative(pathCheck.root, pathCheck.target) };
    }
    if (op === 'rename') {
      const targetCheck = safeWorkspacePath(rootPath || repoRoot, operation.target || '');
      if (!targetCheck.ok) return { ok: false, error: targetCheck.error, op };
      fs.mkdirSync(path.dirname(targetCheck.target), { recursive: true });
      fs.renameSync(pathCheck.target, targetCheck.target);
      return {
        ok: true,
        op,
        path: path.relative(pathCheck.root, pathCheck.target),
        target: path.relative(targetCheck.root, targetCheck.target),
      };
    }
    if (op === 'delete_file') {
      const stat = fs.statSync(pathCheck.target);
      if (!stat.isFile()) return { ok: false, error: 'delete_file only removes files', op };
      fs.unlinkSync(pathCheck.target);
      return { ok: true, op, path: path.relative(pathCheck.root, pathCheck.target) };
    }
    return { ok: false, error: `unsupported operation: ${op}`, op };
  } catch (error) {
    return { ok: false, error: String(error.message || error), op };
  }
}

function runDesktopScript(scriptName) {
  const scriptPath = path.join(__dirname, 'scripts', scriptName);
  if (!fs.existsSync(scriptPath)) {
    return { ran: false, ok: false, error: `${scriptName} missing`, script: scriptPath };
  }
  try {
    const completed = spawnSync('node', [scriptPath], {
      cwd: __dirname,
      encoding: 'utf8',
      timeout: 30000,
    });
    return {
      ran: true,
      ok: completed.status === 0,
      returncode: completed.status,
      stdout: String(completed.stdout || '').slice(-4000),
      stderr: String(completed.stderr || '').slice(-4000),
      script: scriptPath,
    };
  } catch (error) {
    return { ran: true, ok: false, error: String(error.message || error), script: scriptPath };
  }
}

function localReleaseReadiness(rootPath = repoRoot) {
  const root = path.resolve(rootPath || repoRoot);
  const files = {
    desktop_package: path.join(__dirname, 'package.json'),
    desktop_main: path.join(__dirname, 'main.js'),
    desktop_preload: path.join(__dirname, 'preload.js'),
    desktop_renderer: path.join(__dirname, 'renderer', 'app.js'),
    desktop_html: path.join(__dirname, 'renderer', 'index.html'),
    desktop_styles: path.join(__dirname, 'renderer', 'styles.css'),
    desktop_smoke: path.join(__dirname, 'scripts', 'smoke-desktop-ide.js'),
    desktop_launch_smoke: path.join(__dirname, 'scripts', 'launch-smoke-desktop-ide.js'),
    ide_routes: path.join(root, 'app', 'routes', 'ide.py'),
    desktop_tests: path.join(root, 'tests', 'test_desktop_ide_manifest.py'),
  };
  const read = filePath => {
    try {
      return fs.readFileSync(filePath, 'utf8');
    } catch (_error) {
      return '';
    }
  };
  const packageText = read(files.desktop_package);
  const rendererText = read(files.desktop_renderer);
  const htmlText = read(files.desktop_html);
  const mainText = read(files.desktop_main);
  const preloadText = read(files.desktop_preload);
  const routeText = read(files.ide_routes);
  const smoke = runDesktopScript('smoke-desktop-ide.js');
  const launchSmoke = runDesktopScript('launch-smoke-desktop-ide.js');
  const checks = [
    ...Object.entries(files).map(([name, filePath]) => ({ check: `${name}_exists`, passed: fs.existsSync(filePath), path: filePath })),
    { check: 'monaco_packaged', passed: packageText.includes('monaco-editor') },
    { check: 'command_palette_modal_present', passed: htmlText.includes('commandPaletteOverlay') && rendererText.includes('openCommandPaletteModal') },
    { check: 'status_chips_present', passed: htmlText.includes('statusChipBar') && rendererText.includes('updateStatusChips') },
    { check: 'local_readiness_ipc_present', passed: mainText.includes('localReleaseReadiness') && preloadText.includes('releaseReadiness') },
    { check: 'release_route_present', passed: routeText.includes('release-readiness/check') },
    { check: 'desktop_smoke_passed', passed: Boolean(smoke.ok), detail: smoke },
    { check: 'desktop_launch_smoke_passed', passed: Boolean(launchSmoke.ok), detail: launchSmoke },
  ];
  const passed = checks.filter(item => item.passed).length;
  return {
    ok: passed === checks.length,
    beast_object_type: 'beast_desktop_local_release_readiness',
    version: DESKTOP_IDE_VERSION,
    source: 'electron_main_local',
    created_at: Date.now(),
    repoRoot: root,
    desktopRoot: __dirname,
    status: passed === checks.length ? 'pass' : 'warn',
    summary: { checks: checks.length, passed, failed: checks.length - passed },
    checks,
    smoke,
    launch_smoke: launchSmoke,
    gateway: {
      url: gatewayUrl,
      local_mode: localIdeMode,
      processPid: gatewayProcess?.pid || null,
    },
    read_only: true,
  };
}

function commandVersion(command, args = ['--version']) {
  try {
    const completed = spawnSync(command, args, {
      cwd: repoRoot,
      encoding: 'utf8',
      timeout: 5000,
    });
    const output = String(completed.stdout || completed.stderr || '').trim().split('\n')[0] || 'available';
    return { ok: completed.status === 0, command, version: output, returncode: completed.status };
  } catch (error) {
    return { ok: false, command, error: String(error.message || error) };
  }
}

function syntaxCheckFile(rootPath = repoRoot, relPath = '') {
  if (!relPath) return { ok: true, status: 'idle', detail: 'No active file selected.' };
  const pathCheck = safeWorkspacePath(rootPath || repoRoot, relPath);
  if (!pathCheck.ok) return { ok: false, status: 'blocked', detail: pathCheck.error, path: relPath };
  const suffix = path.extname(pathCheck.target).toLowerCase();
  try {
    if (suffix === '.json') {
      JSON.parse(fs.readFileSync(pathCheck.target, 'utf8'));
      return { ok: true, status: 'pass', kind: 'json', path: relPath };
    }
    if (suffix === '.js' || suffix === '.mjs' || suffix === '.cjs') {
      const completed = spawnSync('node', ['--check', pathCheck.target], { encoding: 'utf8', timeout: 10000 });
      return {
        ok: completed.status === 0,
        status: completed.status === 0 ? 'pass' : 'warn',
        kind: 'node',
        path: relPath,
        stdout: String(completed.stdout || '').slice(-2000),
        stderr: String(completed.stderr || '').slice(-2000),
      };
    }
    if (suffix === '.py') {
      const completed = spawnSync('python3', ['-m', 'py_compile', pathCheck.target], { encoding: 'utf8', timeout: 10000 });
      return {
        ok: completed.status === 0,
        status: completed.status === 0 ? 'pass' : 'warn',
        kind: 'python',
        path: relPath,
        stdout: String(completed.stdout || '').slice(-2000),
        stderr: String(completed.stderr || '').slice(-2000),
      };
    }
    return { ok: true, status: 'skipped', kind: suffix || 'text', path: relPath, detail: 'No syntax checker registered for this file type.' };
  } catch (error) {
    return { ok: false, status: 'warn', path: relPath, error: String(error.message || error) };
  }
}

function localToolingSnapshot(rootPath = repoRoot, activeFile = '') {
  const root = path.resolve(rootPath || repoRoot);
  const packagePath = path.join(root, 'package.json');
  const desktopPackagePath = path.join(root, 'desktop-ide', 'package.json');
  const cursorMcp = path.join(root, '.cursor', 'mcp.json');
  const vscodeDir = path.join(root, 'vscode-extension');
  const desktopDir = path.join(root, 'desktop-ide');
  const readJson = filePath => {
    try {
      return JSON.parse(fs.readFileSync(filePath, 'utf8'));
    } catch (_error) {
      return {};
    }
  };
  const rootPackage = readJson(packagePath);
  const desktopPackage = readJson(desktopPackagePath);
  const scripts = {
    root: Object.keys(rootPackage.scripts || {}),
    desktop: Object.keys(desktopPackage.scripts || {}),
  };
  const env = [
    commandVersion('python3', ['--version']),
    commandVersion('node', ['--version']),
    commandVersion('npm', ['--version']),
    commandVersion('git', ['--version']),
  ];
  const mcpConfigured = fs.existsSync(cursorMcp);
  return {
    ok: true,
    beast_object_type: 'beast_desktop_local_tooling_snapshot',
    version: DESKTOP_IDE_VERSION,
    source: 'electron_main_local',
    repoRoot: root,
    activeFile,
    syntax: syntaxCheckFile(root, activeFile),
    linting: {
      scripts,
      has_root_lint: scripts.root.some(item => item.includes('lint')),
      has_desktop_smoke: scripts.desktop.includes('smoke'),
      has_launch_smoke: scripts.desktop.includes('smoke:launch'),
      recommendation: scripts.root.some(item => item.includes('lint'))
        ? 'Use the project lint script through the governed terminal.'
        : 'No root lint script detected; use syntax checks and focused tests until a lint contract is added.',
    },
    mcp: {
      configured: mcpConfigured,
      cursor_config: cursorMcp,
      expected_routes: ['/edgek/mcp/state', '/edgek/mcp/servers', '/edgek/mcp/audit', '/edgek/mcp/executions', '/edgek/mcp/approvals'],
      status: mcpConfigured ? 'configured' : 'no local .cursor/mcp.json',
    },
    plugins: {
      vscode_extension_present: fs.existsSync(vscodeDir),
      desktop_ide_present: fs.existsSync(desktopDir),
      expected_routes: ['/edgek/plugins', '/edgek/plugins/manifest/prepare', '/edgek/plugins/manifest/validate', '/edgek/plugins/install'],
      status: fs.existsSync(vscodeDir) || fs.existsSync(desktopDir) ? 'local surfaces present' : 'no local plugin surfaces detected',
    },
    environments: env,
    read_only: true,
  };
}

function localSystemSnapshot(rootPath = repoRoot) {
  const root = path.resolve(rootPath || activeWorkspaceRoot || repoRoot);
  const python = resolveBeastPython();
  const code = [
    'import json, sys',
    'from pathlib import Path',
    'from app.kernel.workspaces import system_inspector',
    'root = Path(sys.argv[1]).resolve()',
    'snap = system_inspector.system_snapshot(root, port_limit=120, process_limit=80)',
    'snap["catalog"] = system_inspector.catalog_report(root)',
    'print(json.dumps(snap, default=str))',
  ].join('; ');
  const completed = spawnSync(python, ['-c', code, repoRoot], {
    cwd: repoRoot,
    env: { ...process.env, BEAST_ACTIVE_WORKSPACE: root, BEAST_WORKSPACE: root },
    encoding: 'utf8',
    timeout: 12000,
  });
  if (completed.error) {
    return { ok: false, source: 'electron_main_local', error: String(completed.error.message || completed.error) };
  }
  if (completed.status !== 0) {
    return {
      ok: false,
      source: 'electron_main_local',
      error: (completed.stderr || completed.stdout || `python exited ${completed.status}`).trim(),
    };
  }
  try {
    return { ...JSON.parse(completed.stdout || '{}'), source: 'electron_main_local' };
  } catch (error) {
    return { ok: false, source: 'electron_main_local', error: String(error.message || error), raw: completed.stdout };
  }
}

function resolveBeastPython() {
  if (resolvedBeastPython) return resolvedBeastPython;
  const candidates = [
    process.env.BEAST_PYTHON,
    path.join(repoRoot, 'venv', 'bin', 'python'),
    path.join(repoRoot, '.venv', 'bin', 'python'),
    'python3',
    'python',
  ].filter(Boolean);
  for (const candidate of candidates) {
    const completed = spawnSync(candidate, ['-c', 'import fastapi, uvicorn, cryptography, yaml'], {
      cwd: repoRoot,
      encoding: 'utf8',
      timeout: 5000,
    });
    if (!completed.error && completed.status === 0) {
      resolvedBeastPython = candidate;
      return resolvedBeastPython;
    }
  }
  resolvedBeastPython = process.env.BEAST_PYTHON || 'python3';
  return resolvedBeastPython;
}

function getJson(url, timeoutMs = 2500) {
  return new Promise((resolve, reject) => {
    const request = http.get(url, { timeout: timeoutMs }, response => {
      let body = '';
      response.setEncoding('utf8');
      response.on('data', chunk => { body += chunk; });
      response.on('end', () => {
        if (response.statusCode >= 400) {
          reject(new Error(`${url} -> ${response.statusCode}`));
          return;
        }
        try {
          resolve(JSON.parse(body || '{}'));
        } catch (error) {
          reject(error);
        }
      });
    });
    request.on('timeout', () => {
      request.destroy(new Error(`timeout: ${url}`));
    });
    request.on('error', reject);
  });
}

function gatewayRequest(payload = {}) {
  return new Promise(resolve => {
    let target;
    try {
      const base = new URL(gatewayUrl);
      target = new URL(payload.path || payload.url || '/', base);
      if (target.origin !== base.origin || !['127.0.0.1', '::1', 'localhost'].includes(target.hostname)) {
        resolve({ ok: false, status: 0, error: 'gateway request escaped the active loopback origin' });
        return;
      }
    } catch (error) {
      resolve({ ok: false, status: 0, error: String(error.message || error) });
      return;
    }
    const method = String(payload.method || 'GET').toUpperCase();
    const encoded = payload.body == null ? null : Buffer.from(JSON.stringify(payload.body));
    if (encoded && encoded.length > 4 * 1024 * 1024) {
      resolve({ ok: false, status: 413, error: 'gateway IPC request body exceeds 4 MiB' });
      return;
    }
    const forbidden = new Set(['host', 'connection', 'content-length', 'transfer-encoding']);
    const headers = Object.fromEntries(Object.entries(payload.headers || {}).filter(([name]) => !forbidden.has(String(name).toLowerCase())).map(([name, value]) => [String(name), String(value)]));
    if (encoded) {
      headers['Content-Type'] = headers['Content-Type'] || 'application/json';
      headers['Content-Length'] = String(encoded.length);
    }
    // SourcePlan lifecycle and verification can legitimately need more than a
    // UI probe. Keep the cap bounded, but do not turn a normal review into a
    // guaranteed five-second failure under a busy local gateway.
    const timeoutMs = Math.max(250, Math.min(Number(payload.timeoutMs || 6000), 120000));
    const request = http.request(target, { method, headers, timeout: timeoutMs }, response => {
      const chunks = []; let total = 0;
      response.on('data', chunk => {
        total += chunk.length;
        if (total > 8 * 1024 * 1024) request.destroy(new Error('gateway response exceeds 8 MiB'));
        else chunks.push(chunk);
      });
      response.on('end', () => {
        const text = Buffer.concat(chunks).toString('utf8');
        let data = text;
        try { if ((response.headers['content-type'] || '').includes('application/json')) data = JSON.parse(text || 'null'); } catch (_) {}
        const ok = response.statusCode >= 200 && response.statusCode < 300;
        resolve({ ok, status: response.statusCode || 0, data, error: ok ? '' : (data?.detail || `${response.statusCode} gateway request failed`) });
      });
    });
    request.on('timeout', () => request.destroy(new Error(`gateway request timeout after ${timeoutMs} ms`)));
    request.on('error', error => resolve({ ok: false, status: 0, error: String(error.message || error) }));
    if (encoded) request.write(encoded);
    request.end();
  });
}

// Renderer pages are loaded from file://, so browser EventSource requests to
// the loopback gateway can be rejected by CORS before the agent sees them.
// Keep streaming on the same trusted Electron IPC boundary as ordinary gateway
// requests.  This also gives the renderer an explicit cancellation path.
class GatewayEventStreamHost {
  constructor() { this.sessions = new Map(); this.sequence = 0; }
  start(payload = {}, sender) {
    let target;
    try {
      const base = new URL(gatewayUrl);
      target = new URL(payload.path || payload.url || '/', base);
      if (target.origin !== base.origin || !['127.0.0.1', '::1', 'localhost'].includes(target.hostname)) throw new Error('gateway stream escaped the active loopback origin');
    } catch (error) { throw new Error(String(error.message || error)); }
    if (String(payload.method || 'GET').toUpperCase() !== 'GET') throw new Error('gateway event streams only support GET requests');
    const id = `gateway-stream-${Date.now()}-${++this.sequence}`;
    const headers = { Accept: 'text/event-stream', 'Cache-Control': 'no-cache' };
    for (const [name, value] of Object.entries(payload.headers || {})) {
      if (!['host', 'connection', 'content-length', 'transfer-encoding'].includes(String(name).toLowerCase())) headers[String(name)] = String(value);
    }
    const emit = message => { if (sender && !sender.isDestroyed()) sender.send('beast:gateway-stream-message', { id, ...message }); };
    const request = http.request(target, { method: 'GET', headers, timeout: Math.max(1000, Math.min(Number(payload.timeoutMs || 3700000), 3700000)) });
    const session = { id, request, response: null, closed: false, buffer: '', event: 'message', data: [] };
    const close = (reason = '') => { if (session.closed) return; session.closed = true; this.sessions.delete(id); try { session.request.destroy(); } catch (_) {} if (reason) emit({ type: 'closed', reason }); };
    this.sessions.set(id, session);
    const flush = () => {
      if (!session.data.length) { session.event = 'message'; return; }
      emit({ type: 'event', event: session.event || 'message', data: session.data.join('\n') });
      session.event = 'message'; session.data = [];
    };
    request.on('response', response => {
      session.response = response;
      if (response.statusCode < 200 || response.statusCode >= 300) { emit({ type: 'error', error: `gateway stream returned ${response.statusCode}` }); close(); return; }
      emit({ type: 'open', status: response.statusCode });
      response.setEncoding('utf8');
      response.on('data', chunk => {
        session.buffer += chunk;
        let newline;
        while ((newline = session.buffer.indexOf('\n')) >= 0) {
          const line = session.buffer.slice(0, newline).replace(/\r$/, ''); session.buffer = session.buffer.slice(newline + 1);
          if (!line) { flush(); continue; }
          if (line.startsWith(':')) continue;
          const colon = line.indexOf(':'); const field = colon < 0 ? line : line.slice(0, colon); const value = (colon < 0 ? '' : line.slice(colon + 1)).replace(/^ /, '');
          if (field === 'event') session.event = value || 'message'; else if (field === 'data') session.data.push(value);
        }
      });
      response.on('end', () => { flush(); if (!session.closed) { emit({ type: 'end' }); close(); } });
      response.on('error', error => { if (!session.closed) { emit({ type: 'error', error: String(error.message || error) }); close(); } });
    });
    request.on('timeout', () => { if (!session.closed) { emit({ type: 'error', error: 'gateway event stream timed out' }); close(); } });
    request.on('error', error => { if (!session.closed) { emit({ type: 'error', error: String(error.message || error) }); close(); } });
    request.end();
    return { ok: true, id };
  }
  stop(id) { const session = this.sessions.get(String(id || '')); if (!session) return { ok: true, stopped: false }; session.closed = true; this.sessions.delete(session.id); try { session.request.destroy(); } catch (_) {} return { ok: true, stopped: true }; }
  stopAll() { for (const id of [...this.sessions.keys()]) this.stop(id); }
}
const gatewayEventStreamHost = new GatewayEventStreamHost();

async function gatewayHealth(baseUrl = gatewayUrl, rootTimeoutMs = 1800) {
  if (localIdeMode) {
    return {
      ok: false,
      url: gatewayUrl,
      local_mode: true,
      error: localIdeReason,
      capabilities: {
        ok: true,
        mode: 'desktop_local_fallback',
        checks: {
          local_files: { ok: true, mode: 'desktop_ipc' },
          local_editor: { ok: true, mode: 'monaco' },
          sourceplan_gateway: { ok: false, mode: 'deferred_until_gateway_ready' },
        },
      },
    };
  }
  try {
    const payload = await getJson(`${baseUrl}/edgek/root-info`, rootTimeoutMs);
    const capabilities = await gatewayCapabilityHealth(baseUrl, payload);
    return { ok: true, url: baseUrl, payload, capabilities };
  } catch (error) {
    const tcp = await gatewayTcpListening(baseUrl);
    return {
      ok: false,
      url: baseUrl,
      error: String(error.message || error),
      starting: Boolean(gatewayProcess && !gatewayProcess.killed),
      tcp_listening: tcp,
      started_at: gatewayStartedAt,
    };
  }
}

function gatewayTcpListening(urlValue, timeoutMs = 700) {
  return new Promise(resolve => {
    let parsed;
    try {
      parsed = new URL(urlValue);
    } catch (_error) {
      resolve(false);
      return;
    }
    const socket = net.createConnection({
      host: parsed.hostname,
      port: Number(parsed.port || 80),
      timeout: timeoutMs,
    });
    socket.once('connect', () => {
      socket.destroy();
      resolve(true);
    });
    socket.once('timeout', () => {
      socket.destroy();
      resolve(false);
    });
    socket.once('error', () => resolve(false));
  });
}

async function gatewayCapabilityHealth(baseUrl = gatewayUrl, rootPayload = null) {
  try {
    const contract = await getJson(`${baseUrl}/edgek/control-plane/desktop-compatibility`, 4500);
    const valid = contract?.contract === 'beast-desktop-enterprise-v1' && contract?.status === 'ready' && Object.values(contract?.checks || {}).every(Boolean);
    return { ok: valid, mode: 'side_effect_free_route_attestation', contract, checks: contract?.checks || {}, root_declared: Boolean(rootPayload?.endpoints) };
  } catch (error) {
    return { ok: false, mode: 'missing_enterprise_desktop_contract', error: String(error.message || error), checks: {}, root_declared: Boolean(rootPayload?.endpoints) };
  }
}

function portIsFree(port) {
  return new Promise(resolve => {
    const server = net.createServer();
    server.once('error', () => resolve(false));
    server.once('listening', () => {
      server.close(() => resolve(true));
    });
    server.listen(port, '127.0.0.1');
  });
}

async function chooseGatewayPort(preferred = 8101) {
  for (let port = preferred; port <= preferred + 20; port += 1) {
    if (await portIsFree(port)) return port;
  }
  return preferred;
}

async function findCompatibleGateway(preferred = 8101) {
  // A listener alone is not a gateway. Keep this probe bounded so an abandoned
  // Guardian-owned socket cannot hold desktop startup hostage for a minute.
  const ports = Array.from({ length: 6 }, (_item, index) => preferred + index);
  for (const port of ports) {
    const candidateUrl = `http://127.0.0.1:${port}`;
    if (!(await gatewayTcpListening(candidateUrl, 250))) continue;
    const ready = await gatewayHealth(candidateUrl, 900);
    if (ready.ok && ready.capabilities?.ok) {
      return { url: candidateUrl, health: ready };
    }
  }
  return null;
}

function waitForGatewayExit(processRef) {
  return new Promise(resolve => {
    processRef.once('exit', code => resolve(code));
  });
}

async function stopManagedGateway(processRef, timeoutMs = 4000) {
  if (!processRef || processRef.exitCode !== null) return true;
  const exited = waitForGatewayExit(processRef);
  processRef.kill('SIGTERM');
  const stopped = await Promise.race([
    exited.then(() => true),
    new Promise(resolve => setTimeout(() => resolve(false), timeoutMs)),
  ]);
  if (stopped) return true;
  appendLog('managed gateway did not stop after SIGTERM; escalating shutdown');
  processRef.kill('SIGKILL');
  return Promise.race([
    exited.then(() => true),
    new Promise(resolve => setTimeout(() => resolve(false), 1500)),
  ]);
}

function spawnGatewayProcess(port) {
  const python = resolveBeastPython();
  const beast = path.join(repoRoot, 'bin', 'beast');
  const args = [beast, 'gateway', '--host', '127.0.0.1', '--port', String(port)];
  // Socket Guardian owns its listener and, on this installation, does not
  // expose the BEAST HTTP desktop contract.  The desktop must therefore run
  // its managed API as a direct sibling on a free port; inheriting guardian
  // socket mode here would make restart re-create the original conflict.
  lastGatewayCommand = `${python} ${args.map(item => `"${item}"`).join(' ')}`;
  gatewayStartedAt = Date.now();
  appendLog(`desktop repo root: ${repoRoot}`);
  appendLog(`active workspace: ${activeWorkspaceRoot || repoRoot}`);
  // The command parser reads BEAST_SOCKET_MODE from its environment.  Strip a
  // Guardian setting inherited from the shell: it belongs to the externally
  // managed listener, while this child is deliberately the direct HTTP API
  // sibling selected above.
  const childEnv = {
    ...process.env,
    PYTHONUNBUFFERED: '1',
    BEAST_DESKTOP_MANAGED: '1',
    BEAST_ACTIVE_WORKSPACE: activeWorkspaceRoot || repoRoot,
    BEAST_WORKSPACE: activeWorkspaceRoot || repoRoot,
  };
  delete childEnv.BEAST_SOCKET_MODE;
  appendLog(`starting direct desktop gateway: ${lastGatewayCommand}`);
  const processRef = spawn(python, args, {
    cwd: repoRoot,
    env: childEnv,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  processRef.stdout.on('data', chunk => appendLog(chunk.toString()));
  processRef.stderr.on('data', chunk => appendLog(chunk.toString()));
  processRef.on('exit', code => {
    appendLog(`gateway exited with code ${code}`);
    if (gatewayProcess === processRef) {
      gatewayProcess = null;
    }
  });
  return processRef;
}

async function ensureGateway() {
  if (gatewayStartupPromise) {
    appendLog('gateway startup already in progress; joining existing attempt');
    return gatewayStartupPromise;
  }
  gatewayStartupPromise = ensureGatewayInner().finally(() => {
    gatewayStartupPromise = null;
  });
  return gatewayStartupPromise;
}

async function ensureGatewayInner() {
  if (localIdeMode) {
    return enterLocalIdeMode(localIdeReason);
  }
  const health = await gatewayHealth();
  if (health.ok && health.capabilities?.ok) {
    appendLog(`attached to existing BEAST gateway at ${gatewayUrl}`);
    return health;
  }
  if (gatewayProcess && !gatewayProcess.killed && health.tcp_listening) {
    appendLog(`gateway process is listening at ${gatewayUrl}; waiting for HTTP routes instead of spawning another gateway`);
  }
  if (!health.ok && health.tcp_listening) {
    appendLog(`listener at ${gatewayUrl} did not answer the BEAST HTTP contract; preserving it and selecting a separate desktop gateway port`);
  }
  if (health.ok && !health.capabilities?.ok) {
    appendLog(`existing gateway at ${gatewayUrl} is missing desktop IDE routes; starting current BEAST on a free port`);
  }
  const url = new URL(gatewayUrl);
  const requestedPort = Number(url.port || 8101);
  const compatibleGateway = await findCompatibleGateway(requestedPort);
  if (compatibleGateway) {
    gatewayUrl = compatibleGateway.url;
    appendLog(`attached to compatible BEAST gateway at ${gatewayUrl}`);
    for (const windowRef of appWindows) if (!windowRef.isDestroyed()) windowRef.webContents.send('beast:refresh');
    return compatibleGateway.health;
  }
  const firstPort = health.ok || health.tcp_listening ? requestedPort + 1 : requestedPort;
  const maxAutomaticAttempts = 3;
  let attempts = 0;
  for (let port = firstPort; port <= firstPort + 20 && attempts < maxAutomaticAttempts; port += 1) {
    const candidateUrl = `http://127.0.0.1:${port}`;
    if (!gatewayProcess || gatewayProcess.killed || gatewayUrl !== candidateUrl) {
      const free = await portIsFree(port);
      if (!free) {
        appendLog(`port ${port} is already in use; trying next port`);
        continue;
      }
      attempts += 1;
      gatewayUrl = candidateUrl;
      gatewayProcess = spawnGatewayProcess(port);
    }
    const exited = waitForGatewayExit(gatewayProcess);
    let sawTcpListening = false;
    for (let attempt = 0; attempt < 60; attempt += 1) {
      const race = await Promise.race([
        new Promise(resolve => setTimeout(() => resolve({ type: 'tick' }), 1000)),
        exited.then(code => ({ type: 'exit', code })),
      ]);
      if (race.type === 'exit') {
        appendLog(`gateway start failed on port ${port}; trying next port`);
        gatewayProcess = null;
        break;
      }
      const ready = await gatewayHealth(candidateUrl);
      if (ready.ok && ready.capabilities?.ok) {
        appendLog(`BEAST desktop gateway ready at ${gatewayUrl}`);
        for (const windowRef of appWindows) if (!windowRef.isDestroyed()) windowRef.webContents.send('beast:refresh');
        return ready;
      }
      sawTcpListening = sawTcpListening || Boolean(ready.tcp_listening);
      if (attempt > 0 && attempt % 15 === 0) {
        appendLog(`gateway warmup on port ${port}: tcp=${ready.tcp_listening ? 'listening' : 'waiting'} http=${ready.ok ? 'ok' : 'waiting'} ${ready.error || ''}`);
      }
    }
    if (gatewayProcess) {
      if (sawTcpListening) {
        appendLog(`gateway is listening on port ${port} but failed the desktop route contract; replacing it`);
        gatewayProcess.kill('SIGTERM');
        gatewayProcess = null;
        continue;
      }
      appendLog(`gateway did not listen on port ${port}; trying next port`);
      gatewayProcess.kill('SIGTERM');
      gatewayProcess = null;
    }
  }
  return enterLocalIdeMode('managed BEAST gateway did not become ready quickly; local file/editor mode is active');
}

function createMenu() {
  const template = [
    {
      label: 'BEAST',
      submenu: [
        { label: 'Start or Attach Gateway', click: () => ensureGateway() },
        { label: 'Open Gateway in Browser', click: () => shell.openExternal(gatewayUrl) },
        { type: 'separator' },
        { role: 'quit' },
      ],
    },
    {
      label: 'Workspace',
      submenu: [
        {
          label: 'Choose Workspace',
          accelerator: 'CmdOrCtrl+O',
          click: async () => {
            const targetWindow = BrowserWindow.getFocusedWindow() || mainWindow;
            const result = await dialog.showOpenDialog(targetWindow, { properties: ['openDirectory'] });
            if (!result.canceled && result.filePaths[0]) {
              const folders=setWorkspaceRoots([result.filePaths[0]],result.filePaths[0]);
              targetWindow.webContents.send('beast:workspace-selected', { root:activeWorkspaceRoot, folders });
            }
          },
        },
        { label: 'Refresh IDE Snapshot', accelerator: 'CmdOrCtrl+R', click: () => (BrowserWindow.getFocusedWindow() || mainWindow)?.webContents.send('beast:refresh') },
      ],
    },
    {
      label: 'View',
      submenu: [
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { role: 'resetZoom' },
        { type: 'separator' },
        { role: 'reload' },
        { role: 'toggleDevTools' },
        { role: 'togglefullscreen' },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

async function createWindow(options = {}) {
  const initialWorkspace = options.initialWorkspace ? path.resolve(options.initialWorkspace) : '';
  if (initialWorkspace) setWorkspaceRoots([initialWorkspace],initialWorkspace);
  const savedWindowState = readWindowState();
  const windowRef = new BrowserWindow({
    ...DEFAULT_WINDOW_BOUNDS,
    width: savedWindowState.width,
    height: savedWindowState.height,
    ...(Number.isFinite(savedWindowState.x) ? { x: savedWindowState.x } : {}),
    ...(Number.isFinite(savedWindowState.y) ? { y: savedWindowState.y } : {}),
    title: 'BEAST Desktop IDE',
    backgroundColor: '#050607',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  mainWindow = windowRef;
  appWindows.add(windowRef);
  windowRef.on('focus', () => { mainWindow = windowRef; });
  windowRef.on('resize', () => scheduleWindowStatePersist(windowRef));
  windowRef.on('move', () => scheduleWindowStatePersist(windowRef));
  windowRef.on('maximize', () => scheduleWindowStatePersist(windowRef));
  windowRef.on('unmaximize', () => scheduleWindowStatePersist(windowRef));
  windowRef.once('ready-to-show', () => { if (savedWindowState.maximized) windowRef.maximize(); });
  windowRef.on('close', () => { clearTimeout(windowStateWriteTimer); persistWindowState(windowRef); });
  windowRef.on('closed', () => {
    appWindows.delete(windowRef);
    if (mainWindow === windowRef) mainWindow = [...appWindows].find(item => !item.isDestroyed()) || null;
  });
  try {
    await windowRef.webContents.session.clearCache();
  } catch (error) {
    appendLog(`renderer cache clear failed: ${error.message || error}`);
  }
  windowRef.webContents.once('did-finish-load', () => {
    appendLog(`renderer loaded: ${path.join(__dirname, 'renderer', 'index.html')} · ${DESKTOP_IDE_VERSION}`);
    windowRef.webContents.send('beast:desktop-version', {
      version: DESKTOP_IDE_VERSION,
      rendererPath: path.join(__dirname, 'renderer', 'index.html'),
      repoRoot: activeWorkspaceRoot || repoRoot,
      beastRepoRoot: repoRoot,
      windowId: windowRef.id,
    });
    if (initialWorkspace) {
      windowRef.webContents.send('beast:workspace-selected', { root:activeWorkspaceRoot, folders:workspaceFolders() });
    }
  });
  await windowRef.loadFile(path.join(__dirname, 'renderer', 'index.html'));
  createMenu();
  ensureGateway();
}

ipcMain.handle('beast:status', async event => {
  let health = await gatewayHealth();
  if (!health.ok || !health.capabilities?.ok) {
    // Keep a managed compatible port (for example 8102 when Socket Guardian
    // owns 8101). Resetting to the registry port here made every transient
    // probe re-enter the Guardian conflict even after desktop had found a
    // healthy BEAST gateway.
    ensureGateway();
    health = { ...health, ok: false, starting: true, url: gatewayUrl };
  }
  const windowRef = BrowserWindow.fromWebContents(event.sender);
  return {
    gatewayUrl: health.url || gatewayUrl,
    repoRoot: activeWorkspaceRoot || repoRoot,
    workspaceFolders: workspaceFolders(),
    beastRepoRoot: repoRoot,
    health,
    processPid: gatewayProcess?.pid || null,
    lastGatewayCommand,
    gatewayLog,
    desktopVersion: DESKTOP_IDE_VERSION,
    rendererPath: path.join(__dirname, 'renderer', 'index.html'),
    windowId: windowRef?.id || null,
    windowCount: appWindows.size,
  };
});

ipcMain.handle('beast:gateway-request', async (_event, payload) => gatewayRequest(payload || {}));
ipcMain.handle('beast:gateway-stream-start', async (event, payload) => gatewayEventStreamHost.start(payload || {}, event.sender));
ipcMain.handle('beast:gateway-stream-stop', async (_event, id) => gatewayEventStreamHost.stop(id));

function normalizedZoomLevel(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? Math.max(-3, Math.min(5, Math.round(numeric))) : 0;
}

ipcMain.handle('beast:zoom-get', async event => {
  const windowRef = BrowserWindow.fromWebContents(event.sender) || mainWindow;
  return { level: windowRef?.webContents.getZoomLevel?.() ?? 0, factor: windowRef?.webContents.getZoomFactor?.() ?? 1 };
});
ipcMain.handle('beast:zoom-set', async (event, requestedLevel) => {
  const windowRef = BrowserWindow.fromWebContents(event.sender) || mainWindow;
  if (!windowRef || windowRef.isDestroyed()) throw new Error('No BEAST desktop window is available for zoom.');
  const level = normalizedZoomLevel(requestedLevel); windowRef.webContents.setZoomLevel(level);
  return { level, factor: windowRef.webContents.getZoomFactor() };
});
ipcMain.handle('beast:zoom-reset', async event => {
  const windowRef = BrowserWindow.fromWebContents(event.sender) || mainWindow;
  if (!windowRef || windowRef.isDestroyed()) throw new Error('No BEAST desktop window is available for zoom.');
  windowRef.webContents.setZoomLevel(0); return { level: 0, factor: windowRef.webContents.getZoomFactor() };
});

ipcMain.handle('beast:choose-workspace', async event => {
  const windowRef = BrowserWindow.fromWebContents(event.sender) || mainWindow;
  const result = await dialog.showOpenDialog(windowRef, { properties: ['openDirectory'] });
  if (result.canceled || !result.filePaths[0]) return '';
  const folders=setWorkspaceRoots([result.filePaths[0]],result.filePaths[0]);
  return {root:activeWorkspaceRoot,folders};
});
ipcMain.handle('beast:workspace-folders', async () => ({root:activeWorkspaceRoot,folders:workspaceFolders()}));
ipcMain.handle('beast:workspace-folder-add', async event => { const windowRef=BrowserWindow.fromWebContents(event.sender)||mainWindow;const result=await dialog.showOpenDialog(windowRef,{properties:['openDirectory']});if(result.canceled||!result.filePaths[0])return {root:activeWorkspaceRoot,folders:workspaceFolders()};const folders=setWorkspaceRoots([...activeWorkspaceRoots,result.filePaths[0]],activeWorkspaceRoot);return {root:activeWorkspaceRoot,folders}; });
ipcMain.handle('beast:workspace-folder-remove', async (_event,id) => { const folder=workspaceFolders().find(item=>item.id===String(id||''));if(!folder||folder.primary)return {ok:false,error:'The primary workspace folder cannot be removed.'};const folders=setWorkspaceRoots(activeWorkspaceRoots.filter(item=>path.resolve(item)!==folder.path),activeWorkspaceRoot);return {ok:true,root:activeWorkspaceRoot,folders}; });
ipcMain.handle('beast:execution-target-get', async () => ({ok:true,target:executionTargetSummary()}));
ipcMain.handle('beast:execution-target-set', async (_event,payload) => setActiveExecutionTarget(payload || {}));
ipcMain.handle('beast:execution-target-list', async (_event,payload) => listExecutionTargets(registeredWorkspaceRoot(payload || {})));

ipcMain.handle('beast:restart-gateway', async () => {
  localIdeMode = false;
  localIdeReason = '';
  gatewayStartupPromise = null;
  if (gatewayProcess) {
    const previousGateway = gatewayProcess;
    gatewayProcess = null;
    const stopped = await stopManagedGateway(previousGateway);
    if (!stopped) {
      throw new Error('Managed BEAST gateway did not stop; restart was not attempted to avoid attaching to a stale process.');
    }
  }
  return ensureGateway();
});

ipcMain.handle('beast:open-gateway', async () => {
  await shell.openExternal(gatewayUrl);
  return { ok: true, gatewayUrl };
});

ipcMain.handle('beast:list-files', async (_event, rootPath, limit) => {
  if(!rootPath||path.resolve(rootPath)===activeWorkspaceRoot)return multiRootFiles(Math.max(1, Math.min(Number(limit || 400), 2000)));
  return workspaceFileCandidates(rootPath, Math.max(1, Math.min(Number(limit || 400), 2000)));
});

ipcMain.handle('beast:read-file', async (_event, rootPath, relPath, maxChars) => {
  const ref=parseWorkspaceReference(relPath);if(!ref.folder)return {ok:false,error:'Unknown workspace folder reference.',path:relPath};return readWorkspaceFile(ref.folder.path,ref.relative, Math.max(1, Math.min(Number(maxChars || 200000), 1000000)));
});
ipcMain.handle('beast:workspace-target-list-files', async (_event, payload) => workspaceTargetListFiles(registeredWorkspaceRoot(payload || {}), payload || {}));
ipcMain.handle('beast:workspace-target-read-file', async (_event, payload) => workspaceTargetReadFile(registeredWorkspaceRoot(payload || {}), payload || {}));
ipcMain.handle('beast:workspace-target-write-file', async (_event, payload) => workspaceTargetWriteFile(registeredWorkspaceRoot(payload || {}), payload || {}));

function registeredWorkspaceRoot(payload={}) { const folder=workspaceFolders().find(item=>item.id===String(payload?.rootId||''));return folder?.path||activeWorkspaceRoot||repoRoot; }
ipcMain.handle('beast:workspace-search', async (_event, payload) => textWorkspaceSearch(registeredWorkspaceRoot(payload),payload || {}));
ipcMain.handle('beast:workspace-replace', async (_event, payload) => workspaceReplacePreview(registeredWorkspaceRoot(payload),payload || {}));
ipcMain.handle('beast:workspace-git-status', async (_event,payload) => workspaceGitStatus(registeredWorkspaceRoot(payload)));
ipcMain.handle('beast:workspace-git-repositories', async () => ({ok:true,repositories:await Promise.all(workspaceFolders().map(async folder=>{const status=await workspaceGitStatus(folder.path);return {folder,status:{ok:status.ok,branch:status.branch||'',branchName:status.branchName||'',counts:status.counts||{staged:0,unstaged:0,conflicts:0},changes:status.changes||[],error:status.error||''}};}))}));
ipcMain.handle('beast:workspace-git-action', async (_event, payload) => workspaceGitAction(registeredWorkspaceRoot(payload),payload?.action,payload?.path));
ipcMain.handle('beast:workspace-git-diff', async (_event, payload) => workspaceGitDiff(registeredWorkspaceRoot(payload),payload || {}));
ipcMain.handle('beast:workspace-git-commit', async (_event, payload) => workspaceGitCommit(registeredWorkspaceRoot(payload),payload || {}));
ipcMain.handle('beast:workspace-git-branch', async (_event, payload) => workspaceGitBranch(registeredWorkspaceRoot(payload),payload || {}));
ipcMain.handle('beast:workspace-git-hunks', async (_event, payload) => workspaceGitHunks(registeredWorkspaceRoot(payload),payload || {}));
ipcMain.handle('beast:workspace-git-hunk-action', async (_event, payload) => workspaceGitHunkAction(registeredWorkspaceRoot(payload),payload || {}));
ipcMain.handle('beast:workspace-git-conflict', async (_event, payload) => workspaceGitConflict(registeredWorkspaceRoot(payload),payload || {}));
ipcMain.handle('beast:workspace-git-resolve', async (_event, payload) => workspaceGitResolve(registeredWorkspaceRoot(payload),payload || {}));
ipcMain.handle('beast:workspace-git-history', async (_event, payload) => workspaceGitHistory(registeredWorkspaceRoot(payload),payload || {}));
ipcMain.handle('beast:workspace-git-remotes', async (_event,payload) => workspaceGitRemotes(registeredWorkspaceRoot(payload)));
ipcMain.handle('beast:workspace-git-operation', async (_event, payload) => workspaceGitOperation(registeredWorkspaceRoot(payload),payload || {}));
ipcMain.handle('beast:workspace-tasks', async (_event,payload) => workspaceTasks(registeredWorkspaceRoot(payload)));
ipcMain.handle('beast:workspace-task-run', async (_event, payload) => runWorkspaceTask(registeredWorkspaceRoot(payload),payload));
ipcMain.handle('beast:workspace-settings', async (_event,payload) => workspaceSettings(registeredWorkspaceRoot(payload)));
ipcMain.handle('beast:workspace-settings-save', async (_event,payload) => writeWorkspaceSettings(registeredWorkspaceRoot(payload),payload?.settings));
ipcMain.handle('beast:workspace-tests', async (_event,payload) => workspaceTestsForTarget(registeredWorkspaceRoot(payload),payload||{}));
ipcMain.handle('beast:workspace-test-run', async (_event,payload) => runWorkspaceTest(registeredWorkspaceRoot(payload),payload));
ipcMain.handle('beast:workspace-task-list', async () => ({ok:true,sessions:workspaceTaskHost.list()}));
ipcMain.handle('beast:workspace-task-start', async (event,payload) => ({ok:true,session:workspaceTaskHost.start(registeredWorkspaceRoot(payload),typeof payload==='string'?payload:payload?.id,event.sender)}));
ipcMain.handle('beast:workspace-task-stop', async (_event,id) => workspaceTaskHost.stop(id));

ipcMain.handle('beast:file-operation', async (_event, rootPath, operation) => {
  return mutateWorkspaceFile(rootPath || activeWorkspaceRoot || repoRoot, operation || {});
});

ipcMain.handle('beast:open-workspace-window', async (_event, workspace) => {
  const target = path.resolve(workspace || activeWorkspaceRoot || repoRoot);
  if (!fs.existsSync(target)) return { ok: false, error: 'workspace path does not exist', workspace: target };
  await createWindow({ initialWorkspace: target });
  return { ok: true, workspace: target };
});

ipcMain.handle('beast:release-readiness', async (_event, rootPath) => {
  return localReleaseReadiness(rootPath || activeWorkspaceRoot || repoRoot);
});

ipcMain.handle('beast:tooling-snapshot', async (_event, rootPath, activeFile) => {
  return localToolingSnapshot(rootPath || activeWorkspaceRoot || repoRoot, activeFile || '');
});

ipcMain.handle('beast:system-snapshot', async (_event, rootPath) => {
  return localSystemSnapshot(rootPath || activeWorkspaceRoot || repoRoot);
});

ipcMain.handle('beast:ide-compatibility', async (_event, rootPath) => {
  return ideCompatibilityHost.discover(rootPath || activeWorkspaceRoot || repoRoot);
});

ipcMain.handle('beast:ide-capability-install', async (_event, options) => {
  return ideCompatibilityHost.install(options || {});
});

ipcMain.handle('beast:ide-protocol-start', async (event, options) => {
  return ideCompatibilityHost.start({ ...(options || {}), root:options?.root || activeWorkspaceRoot || repoRoot, target:options?.target || activeExecutionTarget }, event.sender);
});

ipcMain.handle('beast:ide-protocol-request', async (_event, payload) => {
  return ideCompatibilityHost.request(payload || {});
});

ipcMain.handle('beast:ide-protocol-notify', async (_event, payload) => {
  return ideCompatibilityHost.notify(payload || {});
});

ipcMain.handle('beast:ide-protocol-stop', async (_event, sessionId) => {
  return ideCompatibilityHost.stop(String(sessionId || ''));
});

ipcMain.handle('beast:notebook-execute', async (_event, payload) => {
  return executeNotebookCell(activeWorkspaceRoot || repoRoot, payload || {});
});

ipcMain.handle('beast:notebook-kernel-start', async (event, rootPath) => {
  return notebookKernelHost.start(rootPath || activeWorkspaceRoot || repoRoot,event.sender);
});

ipcMain.handle('beast:notebook-kernel-request', async (_event, payload) => {
  return notebookKernelHost.request(payload || {});
});

ipcMain.handle('beast:notebook-kernel-stop', async () => notebookKernelHost.stop());

ipcMain.handle('beast:remote-probe', async (_event, payload) => {
  return probeRemoteWorkspace(payload || {});
});

ipcMain.handle('beast:remote-list-files', async (_event, payload) => {
  return listRemoteWorkspaceFiles(payload || {});
});
ipcMain.handle('beast:remote-search', async (_event, payload) => searchRemoteWorkspace(payload || {}));
ipcMain.handle('beast:remote-reconnect', async () => reconnectRemoteWorkspace());
ipcMain.handle('beast:remote-read-file', async (_event, payload) => readRemoteWorkspaceFile(payload || {}));
ipcMain.handle('beast:remote-write-file', async (_event, payload) => writeRemoteWorkspaceFile(payload || {}));
ipcMain.handle('beast:remote-terminal-run', async (_event, payload) => runRemoteTerminal(payload || {}));
ipcMain.handle('beast:dev-container-inspect', async (_event,payload) => inspectDevContainers(registeredWorkspaceRoot(payload)));
ipcMain.handle('beast:dev-container-start', async (_event,payload) => startDevContainer(registeredWorkspaceRoot(payload)));
ipcMain.handle('beast:dev-container-stop', async (_event,payload) => stopDevContainer(registeredWorkspaceRoot(payload),payload?.id));
ipcMain.handle('beast:dev-container-attach', async (_event,payload) => attachDevContainer(registeredWorkspaceRoot(payload),payload?.id));
ipcMain.handle('beast:dev-container-rebuild', async (_event,payload) => rebuildDevContainer(registeredWorkspaceRoot(payload)));
ipcMain.handle('beast:dev-container-logs', async (_event,payload) => devContainerLogs(registeredWorkspaceRoot(payload),payload?.id));
ipcMain.handle('beast:dev-container-terminal-run', async (_event,payload) => runDevContainerTerminal(registeredWorkspaceRoot(payload),payload || {}));
ipcMain.handle('beast:remote-terminal-list', async () => ({ok:true,terminals:remoteTerminalHost.list()}));
ipcMain.handle('beast:remote-terminal-start', async (event,payload) => ({ok:true,terminal:remoteTerminalHost.start(payload || {},event.sender)}));
ipcMain.handle('beast:remote-terminal-send', async (_event,payload) => remoteTerminalHost.send(payload?.id,payload?.input));
ipcMain.handle('beast:remote-terminal-stop', async (_event,id) => remoteTerminalHost.stop(id));
ipcMain.handle('beast:terminal-session-list', async () => ({ok:true,terminals:localTerminalHost.list()}));
ipcMain.handle('beast:terminal-session-start', async (event,payload) => ({ok:true,terminal:localTerminalHost.start(registeredWorkspaceRoot(payload),payload||{},event.sender)}));
ipcMain.handle('beast:terminal-session-send', async (_event,payload) => localTerminalHost.send(payload?.id,payload?.input));
ipcMain.handle('beast:terminal-session-stop', async (_event,id) => localTerminalHost.stop(id));

ipcMain.handle('beast:remote-forward-list', async () => ({ ok:true, forwards:sshForwardHost.list() }));

ipcMain.handle('beast:remote-forward-start', async (event, payload) => {
  return { ok:true, forward:sshForwardHost.start(payload || {},event.sender) };
});

ipcMain.handle('beast:remote-forward-stop', async (_event, id) => sshForwardHost.stop(id));

ipcMain.handle('beast:extension-host-discover', async (event, rootPath) => {
  return beastExtensionHost.discover(rootPath || activeWorkspaceRoot || repoRoot,event.sender,activeExecutionTarget);
});

ipcMain.handle('beast:extension-host-grant', async (event, payload) => {
  return beastExtensionHost.grant(activeWorkspaceRoot || repoRoot,payload?.id,payload?.capabilities,event.sender);
});
ipcMain.handle('beast:extension-host-enable', async (event,payload) => beastExtensionHost.setEnabled(activeWorkspaceRoot||repoRoot,payload?.id,Boolean(payload?.enabled),event.sender));
ipcMain.handle('beast:extension-host-install', async event => beastExtensionHost.installWorkspaceExtension(activeWorkspaceRoot||repoRoot,event.sender));
ipcMain.handle('beast:extension-host-uninstall', async (event,payload) => beastExtensionHost.uninstallWorkspaceExtension(activeWorkspaceRoot||repoRoot,payload?.id,event.sender));
ipcMain.handle('beast:extension-host-execute', async (event, payload) => beastExtensionHost.execute(activeWorkspaceRoot || repoRoot,payload?.id,payload?.command,event.sender,payload?.target || activeExecutionTarget));

ipcMain.handle('beast:extension-host-stop', async () => beastExtensionHost.stop());

app.whenReady().then(() => { restoreWorkspaceFolders(); return createWindow(); });
app.on('window-all-closed', () => {
  if (gatewayProcess) gatewayProcess.kill('SIGTERM');
  ideCompatibilityHost.stopAll();
  notebookKernelHost.stop();
  sshForwardHost.stopAll();
  remoteTerminalHost.stopAll();
  workspaceTaskHost.stopAll();
  localTerminalHost.stopAll();
  beastExtensionHost.stop();
  if (process.platform !== 'darwin') app.quit();
});
app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
