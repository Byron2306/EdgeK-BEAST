'use strict';

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

function createBeastExtensionHost({
  repoRoot,
  runtimeResourcePath,
  boundedProcess,
  getMainWindow,
  executionTargetHost,
  BrowserWindow,
  dialog,
}) {
  if (!repoRoot || typeof runtimeResourcePath !== 'function' || typeof boundedProcess !== 'function' || !executionTargetHost) {
    throw new Error('createBeastExtensionHost requires repository, runtime, process, and target dependencies');
  }
  const { remotePath, remoteSshArgs, remoteTarget, shellQuote, containerId, executionTargetSummary } = executionTargetHost;

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
    summary() { const s=this.session;return {status:s?.status || 'stopped',pid:s?.process?.pid || null,root:s?.root || '',target:s?.target || {kind:'local'},runtime:s?.runtime || null,mode:s?.target?.kind==='local'?'declarative-manifests':'remote-declarative-manifests',extensions:s?.extensions || []}; }
    emit(message) { const sender=this.session?.sender;if(sender&&!sender.isDestroyed())sender.send('beast:extension-host-message',message); }
    workspaceRoot(root,target={kind:'local'}) {
      if (target.kind==='ssh') return remotePath(target.remoteRoot || '~');
      if (target.kind==='container') return remotePath(target.workspaceFolder || '/workspace');
      return path.resolve(root || repoRoot);
    }
    roots(root,target={kind:'local'}) {
      const workspace=this.workspaceRoot(root,target);
      if (target.kind==='local') return [{path:path.join(workspace,'.beast','extensions'),origin:'workspace'},{path:runtimeResourcePath('extensions'),origin:'bundled'}];
      // The host runs inside the selected target, so these are target-local
      // paths—not desktop paths accidentally serialized into a remote process.
      return [{path:path.posix.join(workspace,'.beast','extensions'),origin:'workspace'}];
    }
    async runtimePreflight(target={kind:'local'}) {
      if(target.kind==='ssh') { const host=remoteTarget(target.host);const workspace=remotePath(target.remoteRoot||'~');if(!host||!workspace)throw new Error('SSH extension target is missing a verified host or workspace path.');const result=await boundedProcess('ssh',remoteSshArgs(host,`test -d ${shellQuote(workspace)} && command -v node && node --version`),{timeoutMs:12000,outputLimit:32000});if(!result.ok)throw new Error(`SSH extension runtime requires Node.js in ${workspace}: ${String(result.stderr||result.error||'node was not found').trim().slice(0,500)}`);return {kind:'ssh',node:String(result.stdout||'').trim().split(/\s+/).pop(),workspace}; }
      if(target.kind==='container') { const id=containerId(target.containerId||target.name);if(!id)throw new Error('Container extension target has no valid container id.');const result=await boundedProcess('docker',['exec','-i',id,'node','--version'],{timeoutMs:12000,outputLimit:32000});if(!result.ok)throw new Error(`Container extension runtime requires Node.js: ${String(result.stderr||result.error||'node was not found').trim().slice(0,500)}`);return {kind:'container',node:String(result.stdout||'').trim(),containerId:id}; }
      return {kind:'local',node:process.version};
    }
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
      const runtime=await this.runtimePreflight(selected);const launch=this.launch(workspace,selected);const processRef=spawn(launch.command,launch.args,{cwd:launch.cwd,env:{...process.env,ELECTRON_RUN_AS_NODE:'1',BEAST_ACTIVE_WORKSPACE:workspace},stdio:['pipe','pipe','pipe'],shell:false,windowsHide:true});
      const session={process:processRef,sender,root:workspace,target:selected,runtime,status:'starting',buffer:'',stderr:'',pending:new Map(),extensions:[],readyResolve:null,readyReject:null};this.session=session;
      const rejectAll=error=>{for(const pending of session.pending.values()){clearTimeout(pending.timer);pending.reject(error);}session.pending.clear();session.readyReject?.(error);session.readyReject=null;};
      processRef.stdout.on('data',chunk=>{session.buffer+=String(chunk);let cut;while((cut=session.buffer.indexOf('\n'))>=0){const line=session.buffer.slice(0,cut);session.buffer=session.buffer.slice(cut+1);if(!line.trim())continue;try{const message=JSON.parse(line);if(message.id!=null&&session.pending.has(message.id)){const pending=session.pending.get(message.id);session.pending.delete(message.id);clearTimeout(pending.timer);message.ok===false?pending.reject(new Error(message.error||'extension host request failed')):pending.resolve(message);}else if(message.type==='ready'){session.status='running';session.readyResolve?.(this.summary());session.readyResolve=null;session.readyReject=null;this.emit(message);}else this.emit(message);}catch(error){this.emit({type:'error',error:`Malformed extension host message: ${error.message}`});}}});
      processRef.stderr.on('data',chunk=>{const text=String(chunk);session.stderr=`${session.stderr}${text}`.slice(-12000);this.emit({type:'stderr',text:text.slice(-4000)});});
      processRef.on('error',error=>{session.status='error';rejectAll(error);this.emit({type:'error',error:String(error.message||error)});});
      processRef.on('exit',(code,signal)=>{const diagnostic=String(session.stderr||'').trim().slice(-1000);const error=new Error(`extension host exited ${code ?? signal}${diagnostic?`: ${diagnostic}`:''}`);if(this.session===session){session.status='error';this.emit({type:'exit',code,signal,error:error.message});this.session=null;}rejectAll(error);});
      return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{session.readyReject=null;this.stop();reject(new Error('Extension host startup timed out.'));},10000);session.readyResolve=value=>{clearTimeout(timer);resolve(value);};session.readyReject=error=>{clearTimeout(timer);reject(error);};});
    }
    request(operation,payload={}) { const session=this.session;if(!session?.process?.stdin?.writable)throw new Error('Extension host is not running');const id=++this.sequence;session.process.stdin.write(`${JSON.stringify({id,operation,...payload})}\n`);return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{session.pending.delete(id);reject(new Error(`Extension host ${operation} timed out.`));},12000);session.pending.set(id,{resolve,reject,timer});}); }
    async discover(root,sender,target={kind:'local'}) { const workspace=path.resolve(root || repoRoot);await this.start(workspace,sender,target);const selected=this.session.target;const result=await this.request('discover',{roots:this.roots(workspace,selected)});const grants=readExtensionGrants(workspace);const disabled=readDisabledExtensions(workspace);this.session.extensions=(result.extensions || []).map(extension=>{const granted=(Array.isArray(grants[extension.id])?grants[extension.id]:[]).filter(capability=>extension.capabilities.includes(capability));return {...extension,disabled:disabled.has(extension.id),granted,needsApproval:extension.capabilities.filter(capability=>!granted.includes(capability))};});return this.summary(); }
    async grant(root,id,capabilities,sender) { const workspace=path.resolve(root || repoRoot);const summary=await this.discover(workspace,sender);const extension=summary.extensions.find(item=>item.id===String(id||''));if(!extension)throw new Error('Extension manifest is not available in this workspace.');const requested=[...new Set((Array.isArray(capabilities)?capabilities:[]).map(String))];if(requested.some(capability=>!EXTENSION_CAPABILITIES.has(capability)||!extension.capabilities.includes(capability)))throw new Error('Requested extension grant is not declared by this manifest.');const grants=readExtensionGrants(workspace);grants[extension.id]=requested;writeExtensionGrants(workspace,grants);return this.discover(workspace,sender); }
    async setEnabled(root,id,enabled,sender) { const workspace=path.resolve(root||repoRoot);const summary=await this.discover(workspace,sender);if(!summary.extensions.some(item=>item.id===String(id||'')))throw new Error('Extension is not available in this workspace.');const disabled=readDisabledExtensions(workspace);enabled?disabled.delete(String(id)):disabled.add(String(id));writeDisabledExtensions(workspace,disabled);return this.discover(workspace,sender); }
    async installWorkspaceExtension(root,sender) { const workspace=path.resolve(root||repoRoot);const windowRef=BrowserWindow.fromWebContents(sender)||getMainWindow();const choice=await dialog.showOpenDialog(windowRef,{title:'Install BEAST workspace extension',properties:['openDirectory']});if(choice.canceled||!choice.filePaths[0])return this.discover(workspace,sender);const source=extensionPackage(choice.filePaths[0]);if(!source)throw new Error('Choose an extension folder with a valid beast-extension.json and a bounded main entrypoint.');const destination=path.join(workspaceExtensionRoot(workspace),source.id);if(fs.existsSync(destination)){const confirm=await dialog.showMessageBox(windowRef,{type:'warning',buttons:['Replace','Cancel'],defaultId:1,cancelId:1,message:`Replace workspace extension “${source.id}”?`,detail:'The existing managed workspace copy will be removed before the selected manifest and entrypoint are installed.'});if(confirm.response!==0)return this.discover(workspace,sender);fs.rmSync(destination,{recursive:true,force:true});}fs.mkdirSync(destination,{recursive:true,mode:0o700});fs.copyFileSync(source.manifest,path.join(destination,'beast-extension.json'));const target=path.join(destination,source.main);fs.mkdirSync(path.dirname(target),{recursive:true,mode:0o700});fs.copyFileSync(source.entry,target);const disabled=readDisabledExtensions(workspace);disabled.delete(source.id);writeDisabledExtensions(workspace,disabled);return this.discover(workspace,sender); }
    async uninstallWorkspaceExtension(root,id,sender) { const workspace=path.resolve(root||repoRoot);const safeId=String(id||'');if(!/^[a-z0-9][a-z0-9._-]{1,95}$/.test(safeId))throw new Error('Extension identifier is invalid.');const folder=path.join(workspaceExtensionRoot(workspace),safeId);const source=extensionPackage(folder);if(!source||source.id!==safeId)throw new Error('Only installed workspace extensions can be removed.');const windowRef=BrowserWindow.fromWebContents(sender)||getMainWindow();const confirm=await dialog.showMessageBox(windowRef,{type:'warning',buttons:['Remove','Cancel'],defaultId:1,cancelId:1,message:`Remove workspace extension “${safeId}”?`,detail:'This removes only BEAST’s managed copy in .beast/extensions.'});if(confirm.response!==0)return this.discover(workspace,sender);fs.rmSync(folder,{recursive:true,force:true});const grants=readExtensionGrants(workspace);delete grants[safeId];writeExtensionGrants(workspace,grants);const disabled=readDisabledExtensions(workspace);disabled.delete(safeId);writeDisabledExtensions(workspace,disabled);return this.discover(workspace,sender); }
    async execute(root,id,command,sender,target={kind:'local'}) { const workspace=path.resolve(root || repoRoot);const summary=await this.discover(workspace,sender,target);const extension=summary.extensions.find(item=>item.id===String(id||''));if(!extension)throw new Error('Extension is not available in this workspace.');if(extension.disabled)throw new Error('Extension is disabled for this workspace.');if(!extension.contributes?.commands?.some(item=>item.id===String(command||'')))throw new Error('Extension command is not declared by this manifest.');const selected=this.session.target;const result=await this.request('execute',{extensionId:extension.id,command:String(command||''),roots:this.roots(workspace,selected),workspaceRoot:this.workspaceRoot(workspace,selected),granted:extension.granted||[]});const routes=new Set(['workspace','mission','compatibility','source','review','evidence','crystallization','terminal','testing']);const actions=(result.actions||[]).filter(action=>action&&typeof action==='object').map(action=>{if(action.kind==='navigate'&&!routes.has(action.payload?.route))throw new Error('Extension requested an unsupported navigation target.');if(!['navigate','notice','command'].includes(action.kind))throw new Error('Extension requested an unsupported mediated action.');return action;});return {ok:true,extension:extension.id,target:selected,granted:result.granted||[],actions}; }
    stop() { const session=this.session;if(!session)return {ok:true,status:'stopped'};this.session=null;session.status='stopped';for(const pending of session.pending.values()){clearTimeout(pending.timer);pending.reject(new Error('Extension host stopped'));}session.pending.clear();if(!session.process.killed)session.process.kill('SIGTERM');return {ok:true,status:'stopped'}; }
    async deployWorkspaceExtensions(root,sender,target={kind:'local'}) {
      const workspace=path.resolve(root||repoRoot);const selected=executionTargetSummary(target);
      if(selected.kind==='local') return {...await this.discover(workspace,sender,selected),deployed:[],message:'Local workspace extensions are already active.'};
      const localRoot=workspaceExtensionRoot(workspace);const sources=fs.existsSync(localRoot)?fs.readdirSync(localRoot,{withFileTypes:true}).filter(item=>item.isDirectory()).map(item=>extensionPackage(path.join(localRoot,item.name))).filter(Boolean):[];
      const targetRoot=this.workspaceRoot(workspace,selected);const deployFile=async(relative,content)=>{const destination=path.posix.join(targetRoot,'.beast','extensions',relative);const parent=path.posix.dirname(destination);const encoded=Buffer.from(content).toString('base64');const command=`mkdir -p ${shellQuote(parent)} && tmp=$(mktemp ${shellQuote(`${parent}/.beast-extension.XXXXXX`)}) && printf %s ${shellQuote(encoded)} | base64 -d > "$tmp" && mv -f "$tmp" ${shellQuote(destination)}`;return selected.kind==='ssh'?boundedProcess('ssh',remoteSshArgs(remoteTarget(selected.host),command),{timeoutMs:20000,outputLimit:32000}):boundedProcess('docker',['exec','-i',containerId(selected.containerId||selected.name),'sh','-lc',command],{timeoutMs:20000,outputLimit:32000});};
      const deployed=[];for(const source of sources){const manifest=fs.readFileSync(source.manifest);const entry=fs.readFileSync(source.entry);for(const [relative,content] of [[`${source.id}/beast-extension.json`,manifest],[`${source.id}/${source.main}`,entry]]){const result=await deployFile(relative,content);if(!result.ok)throw new Error(`Extension deployment failed for ${source.id}: ${String(result.stderr||result.error||'target command failed').slice(0,500)}`);}deployed.push({id:source.id,files:2,bytes:manifest.length+entry.length});}
      const summary=await this.discover(workspace,sender,selected);return {...summary,deployed,target:selected,message:deployed.length?`Deployed ${deployed.length} workspace extension(s) to ${selected.label||selected.kind}.`:'No managed workspace extensions to deploy.'};
    }
  }
  BeastExtensionHost.prototype.grantForTarget=async function(root,id,capabilities,sender,target={kind:'local'}) { const workspace=path.resolve(root||repoRoot);const summary=await this.discover(workspace,sender,target);const extension=summary.extensions.find(item=>item.id===String(id||''));if(!extension)throw new Error('Extension manifest is not available on the active execution target. Deploy the workspace extension to that target first.');const requested=[...new Set((Array.isArray(capabilities)?capabilities:[]).map(String))];if(requested.some(capability=>!EXTENSION_CAPABILITIES.has(capability)||!extension.capabilities.includes(capability)))throw new Error('Requested extension grant is not declared by this manifest.');const grants=readExtensionGrants(workspace);grants[extension.id]=requested;writeExtensionGrants(workspace,grants);return this.discover(workspace,sender,target); };
  return new BeastExtensionHost();
}

module.exports = { createBeastExtensionHost };
