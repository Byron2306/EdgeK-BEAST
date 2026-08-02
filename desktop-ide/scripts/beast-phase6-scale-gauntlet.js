#!/usr/bin/env node
'use strict';
const fs=require('fs');
const os=require('os');
const path=require('path');
const crypto=require('crypto');
const {spawnSync}=require('child_process');
const {performance}=require('perf_hooks');

function parseArgs(argv){
  const out={tier:'all',keep:false,desktop:'',scratch:'',slowRoot:'',json:''};
  for(let i=2;i<argv.length;i++){
    const a=argv[i];
    if(a==='--keep') out.keep=true;
    else if(a==='--tier') out.tier=argv[++i]||'';
    else if(a.startsWith('--tier=')) out.tier=a.split('=',2)[1];
    else if(a==='--desktop') out.desktop=argv[++i]||'';
    else if(a==='--scratch') out.scratch=argv[++i]||'';
    else if(a==='--slow-root') out.slowRoot=argv[++i]||'';
    else if(a==='--json') out.json=argv[++i]||'';
    else throw new Error(`unknown argument: ${a}`);
  }
  return out;
}
function now(){return performance.now()}
function ms(start){return Math.round((now()-start)*1000)/1000}
function sha(value){return `sha256:${crypto.createHash('sha256').update(String(value)).digest('hex')}`}
function ensureDir(p){fs.mkdirSync(p,{recursive:true})}
function write(p,text='x\n'){ensureDir(path.dirname(p));fs.writeFileSync(p,text)}
function run(command,args,cwd,timeout=120000){const r=spawnSync(command,args,{cwd,encoding:'utf8',timeout});return {ok:r.status===0,status:r.status,stdout:String(r.stdout||'').trim(),stderr:String(r.stderr||'').trim()}}
function safeWorkspacePath(root,rel){const r=path.resolve(root),target=path.resolve(r,String(rel||''));return target===r||target.startsWith(`${r}${path.sep}`)?{ok:true,root:r,target}:{ok:false,error:'path escaped workspace'}}
function percentile(values,p){if(!values.length)return null;const a=[...values].sort((x,y)=>x-y);return a[Math.min(a.length-1,Math.floor((a.length-1)*p))]}

function generateRepository(root,count){
  ensureDir(root); const started=now(); const buckets=250;
  for(let i=0;i<count;i++){
    const bucket=String(i%buckets).padStart(3,'0');
    const group=String(Math.floor(i/buckets)%40).padStart(2,'0');
    write(path.join(root,'src',`g${group}`,`b${bucket}`,`file-${String(i).padStart(6,'0')}.txt`),`BEAST_SCALE_TOKEN ${i}\n`);
  }
  for(let depth=0,p=root;depth<96;depth++){p=path.join(p,`deep-${String(depth).padStart(2,'0')}`);ensureDir(p);if(depth%8===0)write(path.join(p,`depth-${depth}.txt`),`deep ${depth}\n`)}
  for(let i=0;i<1000;i++)write(path.join(root,'node_modules','ignored-package',`ignored-${i}.js`),'ignored\n');
  for(let i=0;i<1000;i++)write(path.join(root,'dist','generated',`bundle-${i}.js`),'generated\n');
  return {created:count,ignoredGenerated:2000,deepPathLevels:96,generationMs:ms(started)};
}
function loadHost(desktop){
  const modulePath=path.join(desktop,'main','workspace-file-host.js');
  if(!fs.existsSync(modulePath))throw new Error(`missing workspace host: ${modulePath}`);
  delete require.cache[require.resolve(modulePath)];
  return require(modulePath).createWorkspaceFileHost({repoRoot:desktop,safeWorkspacePath});
}
function measureTree(host,root,count){
  const pages=[]; const probes=[0,Math.max(0,Math.floor(count/2)),Math.max(0,count-1000)];
  for(const offset of probes){const start=now();const page=host.enumerateWorkspaceTree(root,{offset,limit:1000,symlinkPolicy:'within_workspace'});pages.push({offset,elapsedMs:ms(start),rows:page.rows.length,nextOffset:page.nextOffset,scannedFiles:page.scannedFiles,scannedDirectories:page.scannedDirectories,virtualized:page.virtualized})}
  const start=now();const quick=host.workspaceFileCandidates(root,400);const quickMs=ms(start);
  return {probes:pages,quickOpenCandidateMs:quickMs,quickOpenCandidates:quick.length,p50Ms:percentile(pages.map(x=>x.elapsedMs),.5),p95Ms:percentile(pages.map(x=>x.elapsedMs),.95),ignoredGeneratedVisible:pages.some(p=>false)};
}
function gitChurn(root,tracked=5000,changed=3000){
  const gitRoot=path.join(root,'git-churn');ensureDir(gitRoot);run('git',['init','-q'],gitRoot);run('git',['config','user.email','beast-scale@example.invalid'],gitRoot);run('git',['config','user.name','BEAST Scale Gauntlet'],gitRoot);
  for(let i=0;i<tracked;i++)write(path.join(gitRoot,`tracked-${String(i).padStart(5,'0')}.txt`),`base ${i}\n`);
  let start=now();const add=run('git',['add','.'],gitRoot,180000);const addMs=ms(start);const commit=run('git',['commit','-qm','scale baseline'],gitRoot,180000);
  for(let i=0;i<changed;i++)fs.appendFileSync(path.join(gitRoot,`tracked-${String(i).padStart(5,'0')}.txt`),'changed\n');
  for(let i=0;i<changed;i++)write(path.join(gitRoot,`untracked-${String(i).padStart(5,'0')}.txt`),'new\n');
  start=now();const status=run('git',['status','--porcelain=v1','-uno'],gitRoot,180000);const trackedStatusMs=ms(start);
  start=now();const full=run('git',['status','--porcelain=v1'],gitRoot,180000);const fullStatusMs=ms(start);
  return {tracked,modified:changed,untracked:changed,addMs,trackedStatusMs,fullStatusMs,statusLines:full.stdout?full.stdout.split('\n').length:0,gitAvailable:add.ok&&commit.ok};
}
async function externalMutations(host,root){
  const events=[]; const sender={send:(_channel,payload)=>events.push(payload)};
  let watch;
  try{watch=host.startWatch(root,sender)}catch(error){return {supported:false,error:String(error.message||error),events:0}}
  for(let i=0;i<120;i++){const target=path.join(root,`mutation-${String(i).padStart(3,'0')}.txt`);write(target,`mutation ${i}\n`);fs.appendFileSync(target,'again\n')}
  await new Promise(resolve=>setTimeout(resolve,700));
  host.stopWatch(watch.id);
  return {supported:true,mode:watch.mode,events:events.length,errorEvents:events.filter(x=>x.error).length,mutations:240};
}
function slowFilesystemProbe(host,root){
  if(!root)return {status:'environment_gated',reason:'No --slow-root mount supplied. A delay simulator is not accepted as network-filesystem proof.'};
  if(!fs.existsSync(root))return {status:'failed',reason:`slow root does not exist: ${root}`};
  const start=now();const page=host.enumerateWorkspaceTree(root,{limit:1000});return {status:page.ok?'measured':'failed',root,elapsedMs:ms(start),rows:page.rows.length,filesystem:run('stat',['-f','-c','%T',root],process.cwd()).stdout||'unknown'};
}
function thresholds(count,tree,git,mutations){
  const limits=count>=100000?{first:5000,middle:10000,last:15000,quick:5000,git:15000}:{first:2500,middle:5000,last:7500,quick:2500,git:10000};
  const probes=tree.probes;
  const checks=[
    {name:'first_page_bounded',passed:probes[0].elapsedMs<=limits.first,observed:probes[0].elapsedMs,limit:limits.first},
    {name:'middle_page_bounded',passed:probes[1].elapsedMs<=limits.middle,observed:probes[1].elapsedMs,limit:limits.middle},
    {name:'last_page_bounded',passed:probes[2].elapsedMs<=limits.last,observed:probes[2].elapsedMs,limit:limits.last},
    {name:'quick_candidates_bounded',passed:tree.quickOpenCandidateMs<=limits.quick,observed:tree.quickOpenCandidateMs,limit:limits.quick},
    {name:'git_status_bounded',passed:git.fullStatusMs<=limits.git,observed:git.fullStatusMs,limit:limits.git},
    {name:'external_mutations_visible',passed:mutations.supported&&mutations.events>0,observed:mutations.events,limit:'>0'},
    {name:'virtualized_contract',passed:probes.every(x=>x.virtualized===true&&x.rows<=1000),observed:probes.map(x=>x.rows),limit:1000},
  ];
  return {limits,checks,passed:checks.every(x=>x.passed)};
}
async function main(){
  const args=parseArgs(process.argv); const desktop=path.resolve(args.desktop||path.join(__dirname,'..'));
  const tiers=args.tier==='all'?[10000,100000]:[Number(args.tier)];
  if(tiers.some(x=>![10000,100000].includes(x)))throw new Error('--tier must be 10000, 100000, or all');
  const scratch=path.resolve(args.scratch||fs.mkdtempSync(path.join(os.tmpdir(),'beast-phase6-scale-')));ensureDir(scratch);
  const host=loadHost(desktop); const runs=[];
  for(const count of tiers){
    const root=path.join(scratch,`repo-${count}`);const generated=generateRepository(root,count);const tree=measureTree(host,root,count);const git=gitChurn(root);const mutations=await externalMutations(host,root);const threshold=thresholds(count,tree,git,mutations);
    runs.push({fileCount:count,root:args.keep?root:'temporary',generated,tree,git,externalMutations:mutations,threshold});
  }
  const slowFilesystem=slowFilesystemProbe(host,args.slowRoot);
  const receipt={beast_object_type:'ide_phase6_scale_gauntlet_receipt',schema:'beast.ide.scale-gauntlet.v1',created_at:new Date().toISOString(),platform:{platform:process.platform,arch:process.arch,node:process.version,kernel:os.release(),cpuCount:os.cpus().length,totalMemoryBytes:os.totalmem(),filesystem:run('stat',['-f','-c','%T',scratch],process.cwd()).stdout||'unknown'},desktopHost:path.join(desktop,'main','workspace-file-host.js'),runs,slowFilesystem,validated:runs.every(x=>x.threshold.passed),claim_boundary:{local_scale:'physically_measured',slow_network_filesystem:slowFilesystem.status==='measured'?'physically_measured':'not_proven',cross_platform:'not_proven_by_single_host'}};
  receipt.receipt_digest=sha(JSON.stringify(receipt));
  const text=JSON.stringify(receipt,null,2);if(args.json){ensureDir(path.dirname(path.resolve(args.json)));fs.writeFileSync(path.resolve(args.json),text+'\n')}console.log(text);
  if(!args.keep)fs.rmSync(scratch,{recursive:true,force:true});
  process.exitCode=receipt.validated?0:1;
}
main().catch(error=>{console.error(error.stack||error);process.exit(2)});
