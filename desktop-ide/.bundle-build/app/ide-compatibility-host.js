const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

function runtimeResource(...parts) {
  const resource = process.resourcesPath ? path.join(process.resourcesPath,...parts) : '';
  if (resource && fs.existsSync(resource)) return resource;
  const unpacked = process.resourcesPath ? path.join(process.resourcesPath,'app.asar.unpacked',...parts) : '';
  return unpacked && fs.existsSync(unpacked) ? unpacked : path.join(__dirname,...parts);
}

const PYTHON_TOOL_ROOT = (() => {
  const packaged = process.resourcesPath ? path.join(process.resourcesPath,'python-tools') : '';
  return packaged && fs.existsSync(packaged) ? packaged : path.join(__dirname,'.beast-python-tools');
})();
const MANAGED_TOOL_ROOT = path.join(os.homedir(),'.local','share','beast-ide','tools');
const MANAGED_BIN_ROOT = path.join(MANAGED_TOOL_ROOT,'bin');
const managedToolEnv = () => ({ ...process.env, GOBIN:MANAGED_BIN_ROOT, PATH:[MANAGED_BIN_ROOT,process.env.PATH].filter(Boolean).join(path.delimiter) });
function pythonToolEnv() {
  return { ...process.env, PYTHONPATH:[PYTHON_TOOL_ROOT,process.env.PYTHONPATH].filter(Boolean).join(path.delimiter) };
}

const LANGUAGE_SERVERS = [
  { id:'typescript', label:'TypeScript / JavaScript', languages:['typescript','javascript','typescriptreact','javascriptreact'], command:'typescript-language-server', args:['--stdio'] },
  { id:'pyright', label:'Python (Pyright)', languages:['python'], command:'pyright-langserver', args:['--stdio'] },
  { id:'pylsp', label:'Python (pylsp)', languages:['python'], command:'python3', args:['-m','pylsp'], probe:['-c','import pylsp'], env:'python-tools' },
  { id:'rust', label:'Rust Analyzer', languages:['rust'], command:'rust-analyzer', args:[], install:{ mode:'system', package:'rust-analyzer', label:'Install Rust Analyzer' } },
  { id:'go', label:'Go (gopls)', languages:['go'], command:'gopls', args:['serve'], install:{ mode:'go', module:'golang.org/x/tools/gopls@latest', label:'Install gopls' } },
  { id:'clangd', label:'C / C++ (clangd)', languages:['c','cpp'], command:'clangd', commands:['clangd','clangd-19','clangd-18','clangd-17'], args:[], install:{ mode:'system', package:'clangd', label:'Install clangd' } },
  { id:'bash', label:'Shell (bash-language-server)', languages:['shell'], command:'bash-language-server', args:['start'] },
  { id:'json', label:'JSON Language Server', languages:['json'], command:'vscode-json-language-server', args:['--stdio'] },
  { id:'html', label:'HTML Language Server', languages:['html'], command:'vscode-html-language-server', args:['--stdio'] },
  { id:'css', label:'CSS Language Server', languages:['css','scss','less'], command:'vscode-css-language-server', args:['--stdio'] },
];

const DEBUG_ADAPTERS = [
  // debugpy exposes DAP on a loopback socket rather than stdio. The relay
  // keeps the renderer/main contract consistently Content-Length JSON-RPC.
  { id:'debugpy', label:'Python debugpy', command:'python3', args:[runtimeResource('scripts','debugpy-dap-relay.py')], probe:['-c','import debugpy'], env:'python-tools', requiresLoopback:true },
  { id:'lldb', label:'LLDB DAP', command:'lldb-dap', commands:['lldb-dap','lldb-dap-19','lldb-dap-18','lldb-dap-17'], args:[], install:{ mode:'system', package:'lldb', label:'Install LLDB DAP' } },
  { id:'delve', label:'Go Delve DAP', command:'dlv', args:['dap'], transport:'delve-socket', requiresLoopback:true, install:{ mode:'go', module:'github.com/go-delve/delve/cmd/dlv@latest', label:'Install Delve' } },
];

function executable(command) {
  const localSuffixes = process.platform === 'win32' ? ['.cmd','.exe',''] : [''];
  for (const suffix of localSuffixes) {
    const managed = path.join(MANAGED_BIN_ROOT,`${command}${suffix}`);
    try { fs.accessSync(managed,fs.constants.X_OK); return managed; } catch (_) {}
    const local = path.join(__dirname,'node_modules','.bin',`${command}${suffix}`);
    if (fs.existsSync(local)) return local;
  }
  const pathValue = process.env.PATH || '';
  const suffixes = process.platform === 'win32' ? String(process.env.PATHEXT || '.EXE;.CMD;.BAT').split(';') : [''];
  for (const folder of pathValue.split(path.delimiter).filter(Boolean)) {
    for (const suffix of suffixes) {
      const candidate = path.join(folder, process.platform === 'win32' ? `${command}${suffix}` : command);
      try { fs.accessSync(candidate, fs.constants.X_OK); return candidate; } catch (_) {}
    }
  }
  return '';
}

function loopbackAvailable() {
  const python=executable('python3');
  if (!python) return { ok:false, detail:'python3 is unavailable for the local-loopback probe' };
  const result=spawnSync(python,['-c','import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); s.close()'],{encoding:'utf8',timeout:4000});
  if (result.status===0) return { ok:true, detail:'' };
  const reason=String(result.stderr || result.stdout || 'loopback bind probe failed').trim().split('\n').at(-1);
  return { ok:false, detail:`local loopback is unavailable (${reason})` };
}

function probe(entry) {
  const resolved = (entry.commands || [entry.command]).map(executable).find(Boolean) || '';
  if (!resolved) return { ...entry, available:false, resolved:'', detail:`${entry.command} is not installed` };
  if (entry.probe) {
    const result = spawnSync(resolved, entry.probe, { encoding:'utf8', timeout:4000, env:entry.env === 'python-tools' ? pythonToolEnv() : process.env });
    if (result.status !== 0) return { ...entry, available:false, resolved, detail:String(result.stderr || 'probe failed').trim() };
  }
  if (entry.requiresLoopback) {
    const loopback=loopbackAvailable();
    if (!loopback.ok) return { ...entry, available:true, resolved, detail:`ready · ${resolved} · loopback verification deferred (${loopback.detail})`, loopbackDeferred:true };
  }
  return { ...entry, available:true, resolved, detail:`ready · ${resolved}` };
}

function runInstaller(command,args,options={}) {
  return new Promise(resolve => {
    let stdout='';let stderr='';let settled=false;let timer=null;
    const finish=result=>{if(settled)return;settled=true;clearTimeout(timer);resolve(result);};
    let child;
    try { child=spawn(command,args,{cwd:options.cwd || __dirname,env:options.env || process.env,stdio:['ignore','pipe','pipe'],shell:false,windowsHide:true}); }
    catch(error){finish({ok:false,code:null,stdout:'',stderr:String(error.message||error)});return;}
    child.stdout.on('data',chunk=>{stdout=`${stdout}${String(chunk)}`.slice(-24000);});
    child.stderr.on('data',chunk=>{stderr=`${stderr}${String(chunk)}`.slice(-24000);});
    child.on('error',error=>finish({ok:false,code:null,stdout,stderr:`${stderr}\n${String(error.message||error)}`.trim()}));
    child.on('exit',code=>finish({ok:code===0,code,stdout,stderr}));
    timer=setTimeout(()=>{try{child.kill('SIGTERM');}catch(_){}finish({ok:false,code:null,stdout,stderr:`${stderr}\nInstaller timed out.`.trim()});},Math.max(30000,Math.min(Number(options.timeoutMs||600000),900000)));
  });
}

function commandCapability(id, label, command, args=['--version']) {
  const resolved = executable(command);
  if (!resolved) return { id, label, command, available:false, detail:`${command} is not installed` };
  const result = spawnSync(resolved, args, { encoding:'utf8', timeout:4000 });
  const detail = String(result.stdout || result.stderr || 'available').trim().split('\n')[0];
  return { id, label, command, resolved, available:result.status === 0, detail };
}

function pythonModuleCapability(id, label, args, detailModule) {
  const resolved = executable('python3');
  if (!resolved) return { id, label, command:'python3', available:false, detail:'python3 is not installed' };
  const result = spawnSync(resolved, args, { encoding:'utf8', timeout:6000, env:pythonToolEnv() });
  const detail = String(result.stdout || result.stderr || 'available').trim().split('\n')[0];
  return { id, label, command:'python3', resolved, available:result.status === 0, detail:detail || detailModule || 'ready' };
}

function shellQuote(value) {
  return `'${String(value ?? '').replace(/'/g, `'\\''`)}'`;
}

function safeRemoteHost(value) {
  const host=String(value || '').trim();
  return /^[A-Za-z0-9][A-Za-z0-9@._:-]{0,252}$/.test(host) ? host : '';
}

function safeRemotePath(value, fallback='~') {
  const target=String(value || fallback).trim();
  if (!/^[~\/@A-Za-z0-9._+\-]+$/.test(target) || target.split('/').includes('..')) return '';
  return target;
}

function safeContainerId(value) {
  const id=String(value || '').trim();
  return /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(id) ? id : '';
}

function normalizeExecutionTarget(target={}, fallbackRoot='') {
  const kind=['ssh','container'].includes(target?.kind) ? target.kind : 'local';
  if (kind==='ssh') {
    const host=safeRemoteHost(target.host);
    const remoteRoot=safeRemotePath(target.remoteRoot || target.path || target.root || fallbackRoot,'~');
    if (!host || !remoteRoot) throw new Error('SSH protocol target requires a verified host and safe remote root.');
    return {kind,host,remoteRoot,transport:'ssh-stdio'};
  }
  if (kind==='container') {
    const containerId=safeContainerId(target.containerId || target.id || target.name);
    const workspaceFolder=safeRemotePath(target.workspaceFolder || target.path || fallbackRoot,'/workspace');
    if (!containerId || !workspaceFolder) throw new Error('Container protocol target requires a container id/name and safe workspace folder.');
    return {kind,containerId,workspaceFolder,transport:'docker-exec-stdio'};
  }
  return {kind:'local',transport:'local-stdio'};
}

function remoteEntryArgs(entry) {
  if (entry.id==='debugpy') return ['-m','debugpy.adapter'];
  if (entry.id==='delve') return ['dap'];
  return entry.args || [];
}

function targetCommand(entry, root, target) {
  if (target.kind==='ssh') {
    const args=[entry.command,...remoteEntryArgs(entry)].map(shellQuote).join(' ');
    return {
      command:'ssh',
      args:['-o','BatchMode=yes','-o','ConnectTimeout=7','-o','ServerAliveInterval=20','-o','ServerAliveCountMax=2','-o','StrictHostKeyChecking=yes',target.host,`cd ${shellQuote(target.remoteRoot)} && exec ${args}`],
      cwd:root,
      env:process.env,
    };
  }
  if (target.kind==='container') {
    return {
      command:'docker',
      args:['exec','-i','-w',target.workspaceFolder,target.containerId,entry.command,...remoteEntryArgs(entry)],
      cwd:root,
      env:process.env,
    };
  }
  const executablePath=entry.resolved || entry.command;
  const bundledNodeServer=executablePath.startsWith(path.join(__dirname,'node_modules','.bin')) && process.platform !== 'win32';
  const delveSocket=entry.transport==='delve-socket';
  const relay=runtimeResource('scripts','stdio-protocol-relay.py');
  return {
    command:bundledNodeServer || delveSocket ? 'python3' : executablePath,
    args:bundledNodeServer ? [relay,executablePath,...(entry.args || [])] : delveSocket ? [runtimeResource('scripts','delve-dap-relay.py'),executablePath] : (entry.args || []),
    cwd:root,
    env:{ ...(entry.env === 'python-tools' ? pythonToolEnv() : process.env), BEAST_ACTIVE_WORKSPACE:root },
  };
}

class FramedProtocolSession {
  constructor({ id, kind, entry, root, sender, target }) {
    this.id = id;
    this.kind = kind;
    this.entry = entry;
    this.root = root;
    this.sender = sender;
    this.target = normalizeExecutionTarget(target || {}, root);
    this.buffer = Buffer.alloc(0);
    this.sequence = 0;
    this.pending = new Map();
    this.process = null;
    this.status = 'starting';
  }

  start() {
    const command=targetCommand(this.entry,this.root,this.target);
    this.process = spawn(command.command, command.args, {
      cwd:command.cwd,
      env:command.env,
      stdio:['pipe','pipe','pipe'],
      shell:false,
    });
    this.process.stdout.on('data', chunk => this.consume(chunk));
    this.process.stderr.on('data', chunk => this.emit({ type:'stderr', text:String(chunk).slice(-4000) }));
    this.process.on('error', error => { this.status='error'; this.emit({ type:'error', error:String(error.message || error) }); this.rejectAll(error); });
    this.process.on('exit', (code, signal) => { this.status='stopped'; this.emit({ type:'exit', code, signal }); this.rejectAll(new Error(`protocol process exited ${code ?? signal}`)); });
    this.status = 'running';
    this.emit({ type:'started', pid:this.process.pid, command:this.entry.command, target:this.target, transport:this.target.transport });
    return this.summary();
  }

  emit(message) {
    if (!this.sender?.isDestroyed?.()) this.sender.send('beast:ide-protocol-message', { sessionId:this.id, kind:this.kind, ...message });
  }

  consume(chunk) {
    this.buffer = Buffer.concat([this.buffer, chunk]);
    while (this.buffer.length) {
      const headerEnd = this.buffer.indexOf('\r\n\r\n');
      if (headerEnd < 0) return;
      const header = this.buffer.subarray(0, headerEnd).toString('ascii');
      const match = header.match(/Content-Length:\s*(\d+)/i);
      if (!match) { this.buffer = this.buffer.subarray(headerEnd + 4); continue; }
      const length = Number(match[1]);
      const bodyStart = headerEnd + 4;
      if (this.buffer.length < bodyStart + length) return;
      const body = this.buffer.subarray(bodyStart, bodyStart + length).toString('utf8');
      this.buffer = this.buffer.subarray(bodyStart + length);
      try { this.handle(JSON.parse(body)); } catch (error) { this.emit({ type:'error', error:`Malformed protocol payload: ${error.message}` }); }
    }
  }

  handle(message) {
    if (this.kind === 'dap' && message?.type === 'response' && this.pending.has(message.request_seq)) {
      const pending = this.pending.get(message.request_seq);
      this.pending.delete(message.request_seq);
      clearTimeout(pending.timer);
      if (message.success === false) pending.reject(new Error(message.message || message.body?.error?.format || `DAP ${message.command || 'request'} failed`));
      else pending.resolve(message.body || {});
      return;
    }
    if (message.id != null && this.pending.has(message.id)) {
      const pending = this.pending.get(message.id);
      this.pending.delete(message.id);
      clearTimeout(pending.timer);
      if (message.error) pending.reject(new Error(message.error.message || JSON.stringify(message.error)));
      else pending.resolve(message.result);
      return;
    }
    this.emit({ type:'message', message });
  }

  write(message) {
    if (!this.process?.stdin?.writable) throw new Error('protocol session is not writable');
    const body = Buffer.from(JSON.stringify(message), 'utf8');
    this.process.stdin.write(Buffer.concat([Buffer.from(`Content-Length: ${body.length}\r\n\r\n`, 'ascii'), body]));
  }

  notify(method, params={}) {
    if (this.kind === 'dap') { this.write({ seq:++this.sequence, type:'request', command:method, arguments:params }); return; }
    this.write({ jsonrpc:'2.0', method, params });
  }

  request(method, params={}, timeoutMs=10000) {
    const id = ++this.sequence;
    this.write(this.kind === 'dap' ? { seq:id, type:'request', command:method, arguments:params } : { jsonrpc:'2.0', id, method, params });
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(new Error(`${method} timed out`)); }, Math.max(500, Math.min(Number(timeoutMs || 10000), 30000)));
      this.pending.set(id, { resolve, reject, timer });
    });
  }

  rejectAll(error) { for (const item of this.pending.values()) { clearTimeout(item.timer); item.reject(error); } this.pending.clear(); }
  stop() { if (this.process && !this.process.killed) this.process.kill('SIGTERM'); this.status='stopped'; return this.summary(); }
  summary() { return { id:this.id, kind:this.kind, adapter:this.entry.id, label:this.entry.label, status:this.status, pid:this.process?.pid || null, root:this.root, target:this.target, transport:this.target.transport }; }
}

class IdeCompatibilityHost {
  constructor(repoRoot) { this.repoRoot=path.resolve(repoRoot); this.sessions=new Map(); this.nextId=0; }

  discover(workspaceRoot=this.repoRoot) {
    const root = path.resolve(workspaceRoot || this.repoRoot);
    const languages = LANGUAGE_SERVERS.map(probe);
    const debug = DEBUG_ADAPTERS.map(probe);
    const notebooks = [
      pythonModuleCapability('jupyter','Jupyter notebooks',['-c','import jupyter_core, jupyter_client; print(f"jupyter_core {jupyter_core.__version__} · jupyter_client {jupyter_client.__version__}")'],'Jupyter'),
      pythonModuleCapability('ipykernel','Python kernel',['-c','import ipykernel; print(ipykernel.__version__)'],'ipykernel'),
      commandCapability('beast-python','BEAST Python cell runner','python3',['--version']),
    ];
    const ssh=commandCapability('ssh','Remote SSH','ssh',['-V']);
    const remote = [ssh,{...ssh,id:'ssh-forwarding',label:'SSH forwarding + reverse tunnels',detail:ssh.available?'strict host key · loopback-only -L/-R':'ssh is not installed'},commandCapability('docker','Dev containers','docker',['--version'])];
    const code = commandCapability('code','VS Code extension host','code',['--version']);
    const companion = fs.existsSync(path.join(this.repoRoot,'vscode-extension','package.json'));
    const desktopRuntime=fs.existsSync(path.join(__dirname,'scripts','beast-extension-host.js'));
    const available = [...languages,...debug,...notebooks,...remote].filter(item => item.available).length;
    const total = languages.length + debug.length + notebooks.length + remote.length;
    return {
      ok:true, source:'electron_main_protocol_probe', root, updatedAt:Date.now(),
      summary:{ available, total, coverage:total ? Math.round(available / total * 100) : 0 },
      extensionHost:{ ...code, companion, desktopRuntime, detail:desktopRuntime?'isolated declarative runtime · explicit workspace grants':code.detail, status:desktopRuntime ? 'desktop-runtime-ready' : (companion ? (code.available ? 'companion-ready' : 'companion-source-present') : 'missing') },
      languages, debug, notebooks, remote, sessions:[...this.sessions.values()].map(item => item.summary()),
    };
  }

  async install(options={}) {
    const kind=options.kind === 'dap' ? 'dap' : 'lsp';
    const source=kind === 'dap' ? DEBUG_ADAPTERS : LANGUAGE_SERVERS;
    const entry=source.find(item=>item.id===String(options.id||''));
    if(!entry?.install)throw new Error('This capability does not expose an allowlisted installer.');
    try{fs.mkdirSync(MANAGED_BIN_ROOT,{recursive:true});}catch(error){throw new Error(`Could not create the managed tool directory: ${error.message}`);}
    let command='';let args=[];let env=process.env;let authority='managed-user';
    if(entry.install.mode==='go'){
      command=executable('go');args=['install',entry.install.module];env=managedToolEnv();
      if(!command)throw new Error('Go is required before this managed tool can be installed.');
    }else if(entry.install.mode==='system'){
      authority='elevated-system';
      if(process.platform!=='linux')return {ok:false,requiresManual:true,kind,id:entry.id,command:`Install ${entry.install.package} with your operating system package manager.`,detail:'Automatic system package installation is currently available on Linux.'};
      command=executable('pkexec');args=[executable('apt-get')||'/usr/bin/apt-get','install','-y',entry.install.package];
      if(!command)return {ok:false,requiresManual:true,kind,id:entry.id,command:`sudo apt-get install -y ${entry.install.package}`,detail:'Copy this command into a trusted terminal, then probe capabilities again.'};
    }
    const startedAt=Date.now();const result=await runInstaller(command,args,{env,timeoutMs:900000});const verified=probe(entry);
    return {ok:Boolean(result.ok&&verified.available),kind,id:entry.id,label:entry.label,authority,startedAt,finishedAt:Date.now(),available:verified.available,resolved:verified.resolved||'',command:entry.install.mode==='go'?`go install ${entry.install.module}`:`apt-get install -y ${entry.install.package}`,stdout:result.stdout,stderr:result.stderr,detail:verified.available?'Installed and verified.':String(result.stderr||verified.detail||'Installation did not complete.').trim().slice(-4000)};
  }

  start(options={}, sender) {
    const kind = options.kind === 'dap' ? 'dap' : 'lsp';
    const root = path.resolve(options.root || this.repoRoot);
    const workspaceRoots=[root,...(Array.isArray(options.roots)?options.roots:[])].map(item=>path.resolve(String(item||root))).filter((item,index,all)=>all.indexOf(item)===index&&fs.existsSync(item)&&fs.statSync(item).isDirectory()).slice(0,12);
    if (root !== this.repoRoot && !root.startsWith(`${this.repoRoot}${path.sep}`) && !fs.existsSync(root)) throw new Error('workspace root does not exist');
    const target=normalizeExecutionTarget(options.target || {}, root);
    const catalog = target.kind === 'local' ? (kind === 'lsp' ? LANGUAGE_SERVERS : DEBUG_ADAPTERS).map(probe) : (kind === 'lsp' ? LANGUAGE_SERVERS : DEBUG_ADAPTERS).map(entry=>({...entry,available:true,resolved:entry.command,detail:`delegated over ${target.transport}`}));
    const entry = catalog.find(item => item.id === options.adapter || (kind === 'lsp' && item.languages.includes(options.language))) || null;
    if (!entry?.available) throw new Error(`${options.adapter || options.language || kind} adapter is not installed`);
    const existing = [...this.sessions.values()].find(item => item.kind === kind && item.entry.id === entry.id && item.root === root && item.status === 'running' && JSON.stringify(item.target)===JSON.stringify(target));
    if (existing) return existing.summary();
    const id = `${kind}-${Date.now()}-${++this.nextId}`;
    const session = new FramedProtocolSession({ id, kind, entry, root, sender, target });
    this.sessions.set(id, session);
    const summary = session.start();
    if (kind === 'lsp') {
      const initializationOptions=entry.id==='typescript' ? { tsserver:{ path:path.join(__dirname,'node_modules','typescript','lib','tsserver.js') } } : {};
      const rootUri=target.kind==='ssh'?`file://${target.remoteRoot}`:target.kind==='container'?`file://${target.workspaceFolder}`:`file://${root}`;
      session.request('initialize', { processId:process.pid, rootUri, capabilities:{ textDocument:{ synchronization:{ dynamicRegistration:false }, completion:{ completionItem:{ snippetSupport:true } }, hover:{}, definition:{}, references:{}, rename:{ prepareSupport:true }, codeAction:{}, formatting:{}, documentSymbol:{}, semanticTokens:{ requests:{ full:true }, tokenTypes:['namespace','type','class','enum','interface','struct','typeParameter','parameter','variable','property','enumMember','event','function','method','macro','keyword','modifier','comment','string','number','regexp','operator','decorator'], tokenModifiers:['declaration','definition','readonly','static','deprecated','abstract','async','modification','documentation','defaultLibrary'], formats:['relative'], multilineTokenSupport:true, overlappingTokenSupport:false }, publishDiagnostics:{} }, workspace:{ workspaceFolders:true, symbol:{ dynamicRegistration:false, symbolKind:{ valueSet:[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26] } } } }, workspaceFolders:workspaceRoots.map(folder=>({uri:target.kind==='local'?`file://${folder}`:rootUri,name:path.basename(folder)})), initializationOptions }, 12000)
        .then(result => { session.notify('initialized',{}); session.emit({ type:'ready', capabilities:result?.capabilities || {} }); })
        .catch(error => session.emit({ type:'error', error:`initialize failed: ${error.message}` }));
    } else {
      // DAP is intentionally initialized here, in the main process. The
      // renderer can request only allowlisted adapter sessions and structured
      // protocol messages; it never receives a process handle.
      session.request('initialize', {
        clientID:'beast-ide', clientName:'BEAST IDE', adapterID:entry.id,
        pathFormat:'path', linesStartAt1:true, columnsStartAt1:true,
        supportsVariableType:true, supportsVariablePaging:true,
        supportsRunInTerminalRequest:false,
      }, 12000)
        .then(result => session.emit({ type:'ready', capabilities:result || {} }))
        .catch(error => session.emit({ type:'error', error:`DAP initialize failed: ${error.message}` }));
    }
    return summary;
  }

  request({ sessionId, method, params, timeoutMs }) { const session=this.sessions.get(sessionId); if (!session) throw new Error('protocol session not found'); return session.request(method,params,timeoutMs); }
  notify({ sessionId, method, params }) { const session=this.sessions.get(sessionId); if (!session) throw new Error('protocol session not found'); session.notify(method,params); return {ok:true}; }
  stop(sessionId) { const session=this.sessions.get(sessionId); if (!session) return {ok:true,status:'missing'}; const result=session.stop(); this.sessions.delete(sessionId); return result; }
  stopAll() { for (const session of this.sessions.values()) session.stop(); this.sessions.clear(); }
}

module.exports = { IdeCompatibilityHost, LANGUAGE_SERVERS, DEBUG_ADAPTERS };
