#!/usr/bin/env node
'use strict';

// Extensions execute inside a VM with an intentionally small, serializable
// vscode-compatible surface. This host owns filesystem mediation and never
// exposes require, process, sockets, or arbitrary child-process access.
const fs=require('fs');
const path=require('path');
const vm=require('vm');

const CAPABILITIES=new Set(['workspace.read','workspace.write','language.client','terminal.execute','network.loopback']);
const ID=/^[a-z0-9][a-z0-9._-]{1,95}$/;
let buffer='';

function send(value) { process.stdout.write(`${JSON.stringify(value)}\n`); }
function readJson(file) { try { return JSON.parse(fs.readFileSync(file,'utf8')); } catch (_) { return null; } }
function manifestAt(file, origin) {
  const raw=readJson(file); if (!raw || !ID.test(String(raw.id || ''))) return null;
  const requested=[...new Set((Array.isArray(raw.capabilities)?raw.capabilities:[]).map(String).filter(capability=>CAPABILITIES.has(capability)))];
  const commands=(Array.isArray(raw.contributes?.commands)?raw.contributes.commands:[]).map(item=>({id:String(item?.id || ''),title:String(item?.title || '')})).filter(item=>/^beast\.[a-z0-9._-]+$/i.test(item.id)&&item.title).slice(0,80);
  const main=typeof raw.main==='string'&&/^[A-Za-z0-9._/-]{1,180}$/.test(raw.main)&&!raw.main.split('/').includes('..')?raw.main:'';
  return {id:raw.id,name:String(raw.name || raw.id).slice(0,120),version:String(raw.version || '0.0.0').slice(0,40),description:String(raw.description || '').slice(0,500),capabilities:requested,contributes:{commands},origin,manifest:file,main,root:path.dirname(file)};
}
function discover(roots) {
  const extensions=[]; const seen=new Set();
  for (const item of Array.isArray(roots)?roots:[]) {
    const root=path.resolve(String(item?.path || '')); const origin=String(item?.origin || 'workspace');
    let entries=[]; try { entries=fs.readdirSync(root,{withFileTypes:true}); } catch (_) { continue; }
    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      const extension=manifestAt(path.join(root,entry.name,'beast-extension.json'),origin);
      if (extension && !seen.has(extension.id)) { seen.add(extension.id); extensions.push(extension); }
    }
  }
  return extensions.sort((a,b)=>a.name.localeCompare(b.name));
}
async function execute(message={}) {
  const extension=discover(message.roots).find(item=>item.id===String(message.extensionId||''));if(!extension?.main)throw new Error('Extension does not declare an executable sandbox entrypoint.');
  const command=String(message.command||'');if(!extension.contributes.commands.some(item=>item.id===command))throw new Error('Extension command is not declared in its manifest.');
  const sourcePath=path.resolve(extension.root,extension.main);if(!sourcePath.startsWith(`${extension.root}${path.sep}`)||!fs.statSync(sourcePath).isFile())throw new Error('Extension entrypoint is invalid.');
  const source=fs.readFileSync(sourcePath,'utf8');if(Buffer.byteLength(source,'utf8')>65536)throw new Error('Extension entrypoint exceeds the 64 KiB sandbox limit.');
  const workspaceRoot=path.resolve(String(message.workspaceRoot||''));if(!workspaceRoot||!fs.existsSync(workspaceRoot)||!fs.statSync(workspaceRoot).isDirectory())throw new Error('Extension workspace root is invalid.');
  const grants=new Set((Array.isArray(message.granted)?message.granted:[]).map(String).filter(capability=>extension.capabilities.includes(capability)&&CAPABILITIES.has(capability)));
  const actions=[];const emit=(kind,payload={})=>{if(!['navigate','notice','command'].includes(String(kind)))throw new Error('Unsupported mediated extension action.');actions.push({kind:String(kind),payload});};const requireCapability=capability=>{if(!grants.has(capability))throw new Error(`Extension capability is not granted: ${capability}`);};const workspacePath=value=>{const raw=typeof value==='string'?value:value?.fsPath||value?.path||'';const target=path.resolve(workspaceRoot,String(raw||''));if(target===workspaceRoot||!target.startsWith(`${workspaceRoot}${path.sep}`))throw new Error('Extension path escaped its workspace.');return target;};const uri=value=>Object.freeze({scheme:'file',fsPath:String(value),path:String(value),toString:()=>`file://${String(value)}`});const toUri=target=>uri(target);const globMatcher=pattern=>{const raw=String(pattern||'**/*');let expression='';for(let index=0;index<raw.length;index+=1){const char=raw[index];if(char==='*'&&raw[index+1]==='*'){if(raw[index+2]==='/'){expression+='(?:.*/)?';index+=2;}else{expression+='.*';index+=1;}}else if(char==='*')expression+='[^/]*';else if(char==='?')expression+='[^/]';else expression+=/[.+^${}()|[\]\\]/.test(char)?`\\${char}`:char;}return new RegExp(`^${expression}$`);};const findFiles=(include='**/*',exclude='',maxResults=100)=>{requireCapability('workspace.read');const matcher=globMatcher(include);const ignored=String(exclude||'').trim();const rows=[];const skip=new Set(['.git','.beast','node_modules','.venv','venv','dist','build','__pycache__']);const walk=folder=>{if(rows.length>=Math.max(1,Math.min(Number(maxResults)||100,500)))return;for(const entry of fs.readdirSync(folder,{withFileTypes:true}).sort((a,b)=>a.name.localeCompare(b.name))){if(skip.has(entry.name))continue;const full=path.join(folder,entry.name);const rel=path.relative(workspaceRoot,full).split(path.sep).join('/');if(entry.isDirectory())walk(full);else if(entry.isFile()&&matcher.test(rel)&&(!ignored||!rel.includes(ignored.replaceAll('*',''))))rows.push(toUri(full));if(rows.length>=Math.max(1,Math.min(Number(maxResults)||100,500)))return;}};walk(workspaceRoot);return rows;};const systemCommands={"beast.openMission":()=>emit('navigate',{route:'mission'}),"beast.openCompatibility":()=>emit('navigate',{route:'compatibility'}),"beast.openWorkspace":()=>emit('navigate',{route:'workspace'}),"beast.openTerminal":()=>emit('navigate',{route:'terminal'})};const vscode=Object.freeze({Uri:Object.freeze({file:value=>uri(workspacePath(value))}),commands:Object.freeze({executeCommand:(id,...args)=>{const handler=systemCommands[String(id)];if(handler)return handler(...args);emit('command',{id:String(id),args});}}),window:Object.freeze({showInformationMessage:message=>emit('notice',{severity:'info',message:String(message)}),showWarningMessage:message=>emit('notice',{severity:'warning',message:String(message)}),showErrorMessage:message=>emit('notice',{severity:'error',message:String(message)})}),workspace:Object.freeze({workspaceFolders:grants.has('workspace.read')?Object.freeze([{uri:uri(workspaceRoot),name:path.basename(workspaceRoot),index:0}]):Object.freeze([]),getConfiguration:()=>Object.freeze({get:(_key,fallback)=>fallback}),asRelativePath:value=>path.relative(workspaceRoot,workspacePath(value)).split(path.sep).join('/'),findFiles,fs:Object.freeze({readFile:async value=>{requireCapability('workspace.read');const target=workspacePath(value);const stat=fs.statSync(target);if(!stat.isFile()||stat.size>1024*1024)throw new Error('Extension read is limited to workspace files up to 1 MiB.');return Uint8Array.from(fs.readFileSync(target));}})}),env:Object.freeze({appName:'BEAST IDE',language:'en'})});const api=Object.freeze({emit,vscode,capabilities:Object.freeze([...grants])});const context=vm.createContext(Object.freeze({module:{exports:{}},exports:{},api,vscode,Uint8Array}));
  new vm.Script(`'use strict';\n${source}`,{filename:sourcePath}).runInContext(context,{timeout:500});const exported=context.module.exports.run?context.module.exports:context.exports; if(typeof exported.run!=='function')throw new Error('Extension entrypoint must export run(api, command).');
  await Promise.race([Promise.resolve(exported.run(api,command)),new Promise((_,reject)=>setTimeout(()=>reject(new Error('Extension command timed out.')),1500))]);return {extensionId:extension.id,granted:[...grants],actions};
}
async function handle(message={}) {
  if (message.operation==='discover') return {extensions:discover(message.roots)};
  if (message.operation==='ping') return {host:'beast-declarative-extension-host',capabilities:[...CAPABILITIES]};
  if (message.operation==='execute') return execute(message);
  throw new Error('Unsupported extension host operation.');
}

send({type:'ready',host:'beast-declarative-extension-host',capabilities:[...CAPABILITIES]});
process.stdin.on('data',chunk=>{buffer+=String(chunk);let cut;while((cut=buffer.indexOf('\n'))>=0){const line=buffer.slice(0,cut);buffer=buffer.slice(cut+1);if(!line.trim())continue;let request={};try{request=JSON.parse(line);Promise.resolve(handle(request)).then(result=>send({id:request.id,ok:true,...result})).catch(error=>send({id:request.id,ok:false,error:String(error.message||error)}));}catch(error){send({id:request.id,ok:false,error:String(error.message||error)});}}});
process.stdin.on('end',()=>process.exit(0));
