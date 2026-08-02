'use strict';

const path = require('path');
const { spawn } = require('child_process');

function forwardPort(value) { const port=Number(value); return Number.isInteger(port) && port >= 1 && port <= 65535 ? port : 0; }
function forwardTarget(value) { const target=String(value || '127.0.0.1').trim().toLowerCase(); return ['127.0.0.1','localhost'].includes(target) ? target : ''; }

class SshForwardHost {
  constructor({ repoRoot, remoteTarget }) { this.repoRoot=repoRoot;this.remoteTarget=remoteTarget;this.sessions=new Map();this.sequence=0; }
  summary(session) { return { id:session.id, status:session.status, pid:session.process?.pid || null, host:session.host, direction:session.direction, localPort:session.localPort, remotePort:session.remotePort, targetHost:session.targetHost, url:session.direction==='local' ? `http://127.0.0.1:${session.localPort}` : `http://127.0.0.1:${session.remotePort}`, visibility:'loopback-only', verification:'strict-known-host' }; }
  emit(session, message) { if (session.sender && !session.sender.isDestroyed()) session.sender.send('beast:remote-forward-message',{forward:this.summary(session),...message}); }
  list() { return [...this.sessions.values()].map(session=>this.summary(session)); }
  start(payload={}, sender) {
    const host=this.remoteTarget(payload.host); const direction=payload.direction==='reverse' ? 'reverse' : 'local';
    const localPort=forwardPort(payload.localPort); const remotePort=forwardPort(payload.remotePort); const targetHost=forwardTarget(payload.targetHost);
    if (!host || !localPort || !remotePort || !targetHost) throw new Error('Forwarding requires a verified SSH host, loopback target, and ports from 1 to 65535.');
    const existing=[...this.sessions.values()].find(session=>session.host===host&&session.direction===direction&&session.localPort===localPort&&session.remotePort===remotePort&&session.targetHost===targetHost&&session.status==='running');
    if (existing) { existing.sender=sender; return this.summary(existing); }
    const id=`forward-${Date.now()}-${++this.sequence}`;
    const spec=direction==='local' ? `127.0.0.1:${localPort}:${targetHost}:${remotePort}` : `127.0.0.1:${remotePort}:${targetHost}:${localPort}`;
    const flag=direction==='local' ? '-L' : '-R';
    const processRef=spawn('ssh',['-o','BatchMode=yes','-o','ConnectTimeout=7','-o','ServerAliveInterval=20','-o','ServerAliveCountMax=2','-o','StrictHostKeyChecking=yes','-o','ExitOnForwardFailure=yes','-N',flag,spec,host],{cwd:this.repoRoot,stdio:['ignore','pipe','pipe'],shell:false,windowsHide:true});
    const session={id,process:processRef,sender,host,direction,localPort,remotePort,targetHost,status:'starting',stderr:''};this.sessions.set(id,session);
    processRef.stderr.on('data',chunk=>{session.stderr=`${session.stderr}${String(chunk)}`.slice(-4000);this.emit(session,{type:'stderr',text:String(chunk).slice(-1000)});});
    processRef.on('error',error=>{session.status='error';this.emit(session,{type:'error',error:String(error.message||error)});});
    processRef.on('exit',(code,signal)=>{if(this.sessions.get(id)===session)this.sessions.delete(id);if(session.status!=='stopped'){session.status='error';this.emit(session,{type:'exit',code,signal,error:session.stderr||`SSH forward exited ${code ?? signal}`});}});
    session.status='running'; this.emit(session,{type:'started'}); return this.summary(session);
  }
  stop(id) { const session=this.sessions.get(String(id||''));if(!session)return {ok:true,status:'stopped'};this.sessions.delete(session.id);session.status='stopped';if(!session.process.killed)session.process.kill('SIGTERM');this.emit(session,{type:'stopped'});return {ok:true,...this.summary(session)}; }
  stopAll() { return this.list().map(session=>this.stop(session.id)); }
}

class RemoteTerminalHost {
  constructor({ repoRoot, remoteTarget, remotePath, getLastRemoteWorkspace }) { this.repoRoot=repoRoot;this.remoteTarget=remoteTarget;this.remotePath=remotePath;this.getLastRemoteWorkspace=getLastRemoteWorkspace;this.sessions=new Map();this.sequence=0; }
  summary(session) { return { id:session.id,status:session.status,pid:session.process?.pid || null,host:session.host,cwd:session.cwd,shell:session.shell,transport:'ssh-tty',verification:'strict-known-host',startedAt:session.startedAt }; }
  emit(session,message) { if(session.sender&&!session.sender.isDestroyed()) session.sender.send('beast:remote-terminal-message',{terminal:this.summary(session),...message}); }
  list() { return [...this.sessions.values()].map(session=>this.summary(session)); }
  start(payload={},sender) {
    const last=this.getLastRemoteWorkspace?.();const host=this.remoteTarget(payload.host || last?.host); const cwd=this.remotePath(payload.path || last?.path || '~'); const shell=['bash','sh','zsh','fish'].includes(String(payload.shell||'bash')) ? String(payload.shell||'bash') : '';
    if(!host||!cwd||!shell) throw new Error('Remote terminal requires a verified host, safe workspace path, and supported shell.');
    const existing=[...this.sessions.values()].find(session=>session.host===host&&session.cwd===cwd&&session.shell===shell&&session.status==='running');if(existing){existing.sender=sender;this.emit(existing,{type:'attached',text:existing.output||''});return this.summary(existing);}
    const id=`remote-terminal-${Date.now()}-${++this.sequence}`;const command=`cd ${cwd} && exec ${shell} -i`;const processRef=spawn('ssh',['-tt','-o','BatchMode=yes','-o','ConnectTimeout=7','-o','ServerAliveInterval=20','-o','ServerAliveCountMax=2','-o','StrictHostKeyChecking=yes',host,command],{cwd:this.repoRoot,stdio:['pipe','pipe','pipe'],shell:false,windowsHide:true});
    const session={id,process:processRef,sender,host,cwd,shell,status:'starting',output:'',stderr:'',startedAt:Date.now()};this.sessions.set(id,session);const append=(text,stream)=>{const value=String(text||'');session.output=`${session.output}${value}`.slice(-256000);if(stream==='stderr')session.stderr=`${session.stderr}${value}`.slice(-12000);this.emit(session,{type:'output',stream,text:value});};
    processRef.stdout.on('data',chunk=>append(chunk,'stdout'));processRef.stderr.on('data',chunk=>append(chunk,'stderr'));processRef.on('error',error=>{session.status='error';this.emit(session,{type:'error',error:String(error.message||error)});});processRef.on('exit',(code,signal)=>{if(this.sessions.get(id)===session)this.sessions.delete(id);if(session.status!=='stopped'){session.status='error';this.emit(session,{type:'exit',code,signal,error:session.stderr||`Remote terminal exited ${code ?? signal}`});}});session.status='running';this.emit(session,{type:'started',text:`Connected to ${host} · ${cwd}\n`});return this.summary(session);
  }
  send(id,input) { const session=this.sessions.get(String(id||''));const text=String(input??'');if(!session||session.status!=='running'||!session.process.stdin?.writable)throw new Error('Remote terminal session is not running.');if(!text||Buffer.byteLength(text,'utf8')>64*1024)throw new Error('Remote terminal input must be between 1 byte and 64 KiB.');session.process.stdin.write(text.endsWith('\n')?text:`${text}\n`);return {ok:true,...this.summary(session),bytes:Buffer.byteLength(text,'utf8')}; }
  stop(id) { const session=this.sessions.get(String(id||''));if(!session)return {ok:true,status:'stopped'};this.sessions.delete(session.id);session.status='stopped';try{if(session.process.stdin?.writable)session.process.stdin.write('exit\n');}catch(_){}if(!session.process.killed)session.process.kill('SIGTERM');this.emit(session,{type:'stopped'});return {ok:true,...this.summary(session)}; }
  stopAll() { return this.list().map(session=>this.stop(session.id)); }
}

class LocalTerminalHost {
  constructor({ repoRoot, taskCwd, getActiveWorkspaceRoot }) { this.repoRoot=repoRoot;this.taskCwd=taskCwd;this.getActiveWorkspaceRoot=getActiveWorkspaceRoot;this.sessions=new Map();this.sequence=0; }
  summary(session) { return {id:session.id,status:session.status,pid:session.process?.pid||null,cwd:session.cwd,shell:session.shell,transport:'local-pty-compatible',verification:'workspace-bounded',startedAt:session.startedAt}; }
  emit(session,message) { if(session.sender&&!session.sender.isDestroyed())session.sender.send('beast:terminal-session-message',{terminal:this.summary(session),...message}); }
  list() { return [...this.sessions.values()].map(session=>this.summary(session)); }
  start(rootPath,payload={},sender) { const root=path.resolve(rootPath||this.getActiveWorkspaceRoot?.()||this.repoRoot);const cwd=this.taskCwd(root,payload.cwd||root);const shell=['bash','sh','zsh','fish'].includes(String(payload.shell||'bash'))?String(payload.shell||'bash'):'';if(!cwd||!shell)throw new Error('Local terminal requires a workspace-bounded cwd and supported shell.');const existing=[...this.sessions.values()].find(session=>session.cwd===cwd&&session.shell===shell&&session.status==='running');if(existing){existing.sender=sender;return this.summary(existing);}const id=`terminal-${Date.now()}-${++this.sequence}`;const processRef=spawn(shell,['-i'],{cwd,env:{...process.env,TERM:process.env.TERM||'xterm-256color'},stdio:['pipe','pipe','pipe'],shell:false,windowsHide:true});const session={id,process:processRef,sender,cwd,shell,status:'starting',output:'',stderr:'',startedAt:Date.now()};this.sessions.set(id,session);const append=(text,stream)=>{const value=String(text||'');session.output=`${session.output}${value}`.slice(-256000);if(stream==='stderr')session.stderr=`${session.stderr}${value}`.slice(-12000);this.emit(session,{type:'output',stream,text:value});};processRef.stdout.on('data',chunk=>append(chunk,'stdout'));processRef.stderr.on('data',chunk=>append(chunk,'stderr'));processRef.on('error',error=>{session.status='error';this.emit(session,{type:'error',error:String(error.message||error)});});processRef.on('exit',(code,signal)=>{if(this.sessions.get(id)===session)this.sessions.delete(id);if(session.status!=='stopped'){session.status='exited';this.emit(session,{type:'exit',code,signal,error:session.stderr||''});}});session.status='running';this.emit(session,{type:'started',text:`BEAST terminal · ${cwd}\n`});return this.summary(session); }
  send(id,input) { const session=this.sessions.get(String(id||''));const text=String(input??'');if(!session||session.status!=='running'||!session.process.stdin?.writable)throw new Error('Local terminal session is not running.');if(!text||Buffer.byteLength(text,'utf8')>64*1024)throw new Error('Terminal input must be between 1 byte and 64 KiB.');session.process.stdin.write(text.endsWith('\n')?text:`${text}\n`);return {ok:true,...this.summary(session),bytes:Buffer.byteLength(text,'utf8')}; }
  stop(id) { const session=this.sessions.get(String(id||''));if(!session)return {ok:true,status:'stopped'};this.sessions.delete(session.id);session.status='stopped';try{if(session.process.stdin?.writable)session.process.stdin.write('exit\n');}catch(_){}if(!session.process.killed)session.process.kill('SIGTERM');this.emit(session,{type:'stopped'});return {ok:true,...this.summary(session)}; }
  stopAll() { return this.list().map(session=>this.stop(session.id)); }
}

module.exports = { SshForwardHost, RemoteTerminalHost, LocalTerminalHost, forwardPort, forwardTarget };
