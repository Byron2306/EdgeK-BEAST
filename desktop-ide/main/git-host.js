'use strict';

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

function createGitHost({ repoRoot, boundedProcess, safeWorkspacePath }) {
  if (!repoRoot || typeof boundedProcess !== 'function' || typeof safeWorkspacePath !== 'function') {
    throw new Error('createGitHost requires repoRoot, boundedProcess, and safeWorkspacePath');
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

  return {
    parseGitPorcelain,
    gitReceipt,
    parseGitPatchHunks,
    workspaceGitStatus,
    gitTextAt,
    workspaceGitDiff,
    workspaceGitHunks,
    workspaceGitHunkAction,
    gitConflictStage,
    workspaceGitConflict,
    workspaceGitResolve,
    workspaceGitAction,
    workspaceGitCommit,
    workspaceGitBranch,
    safeGitRevision,
    safeGitRemote,
    workspaceGitHistory,
    workspaceGitRemotes,
    workspaceGitOperation,
  };
}

module.exports = { createGitHost };
