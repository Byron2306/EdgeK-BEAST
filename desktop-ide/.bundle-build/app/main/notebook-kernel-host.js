'use strict';

const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn } = require('child_process');

class NotebookKernelHost {
  constructor({ repoRoot, runtimeResourcePath, pythonToolRoot }) {
    this.repoRoot = repoRoot;
    this.runtimeResourcePath = runtimeResourcePath;
    this.pythonToolRoot = pythonToolRoot;
    this.session = null;
    this.sequence = 0;
  }
  summary() { const s=this.session; return { status:s?.status || 'stopped', pid:s?.process?.pid || null, root:s?.root || '', kernel:'beast-python' }; }
  emit(message) { const sender=this.session?.sender; if (sender && !sender.isDestroyed()) sender.send('beast:notebook-kernel-message',message); }
  start(root, sender) {
    const workspace=path.resolve(root || this.repoRoot);
    if (this.session?.status === 'running' && this.session.root === workspace) return this.summary();
    this.stop();
    const tools=this.pythonToolRoot(); const ipythonDir=path.join(os.tmpdir(),'beast-ide-ipython');
    try { fs.mkdirSync(ipythonDir,{recursive:true}); } catch (_) {}
    const processRef=spawn('python3',[this.runtimeResourcePath('scripts','notebook-kernel-relay.py')],{cwd:workspace,env:{...process.env,PYTHONPATH:[tools,process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),JUPYTER_PATH:path.join(tools,'share','jupyter'),IPYTHONDIR:ipythonDir,BEAST_ACTIVE_WORKSPACE:workspace,BEAST_JUPYTER_KERNEL:'beast-python'},stdio:['pipe','pipe','pipe'],shell:false,windowsHide:true});
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

module.exports = { NotebookKernelHost };
