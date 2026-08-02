'use strict';

const { spawn } = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

function createTaskTestHost({ repoRoot, workspaceFileCandidates, safeWorkspacePath, taskCwd, getTargetHost }) {
  if (!repoRoot || typeof workspaceFileCandidates !== 'function' || typeof safeWorkspacePath !== 'function' || typeof taskCwd !== 'function' || typeof getTargetHost !== 'function') {
    throw new Error('createTaskTestHost requires workspace, path, and execution-target dependencies');
  }
  const executionTargetSummary = (...args) => getTargetHost().executionTargetSummary(...args);
  const runOnExecutionTarget = (...args) => getTargetHost().runOnExecutionTarget(...args);
  const remotePath = (...args) => getTargetHost().remotePath(...args);
  const shellQuote = (...args) => getTargetHost().shellQuote(...args);
  const targetRelativePath = (...args) => getTargetHost().targetRelativePath(...args);

  function parseJsonc(text) {
    const source=String(text || '');let clean='';let quote='';let escaped=false;
    for(let index=0;index<source.length;index+=1){const char=source[index];const next=source[index+1];if(quote){clean+=char;if(escaped)escaped=false;else if(char==='\\')escaped=true;else if(char===quote)quote='';continue;}if(char==='"'||char==="'"){quote=char;clean+=char;continue;}if(char==='/'&&next==='/'){while(index<source.length&&source[index]!=='\n')index+=1;clean+='\n';continue;}if(char==='/'&&next==='*'){index+=2;while(index<source.length&&(source[index]!=='*'||source[index+1]!=='/'))index+=1;index+=1;continue;}clean+=char;}
    let normalized='';quote='';escaped=false;
    for(let index=0;index<clean.length;index+=1){const char=clean[index];if(quote){normalized+=char;if(escaped)escaped=false;else if(char==='\\')escaped=true;else if(char===quote)quote='';continue;}if(char==='"'||char==="'"){quote=char;normalized+=char;continue;}if(char===','){let cursor=index+1;while(/\s/.test(clean[cursor]||''))cursor+=1;if(clean[cursor]===']'||clean[cursor]==='}')continue;}normalized+=char;}
    return JSON.parse(normalized);
  }

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
    const root=path.resolve(rootPath||repoRoot);const id=typeof payload==='string'?payload:payload?.id;const file=typeof payload==='object'?String(payload?.file||''):'';const node=typeof payload==='object'?String(payload?.node||''):'';const selectedTarget=typeof payload==='object'?payload?.target:null;const catalog=await workspaceTestsForTarget(root,payload||{});const test=catalog.tests.find(item=>item.id===String(id||''));if(!test)return {ok:false,error:'Test target is not declared by this workspace or execution target.'};const selected= file && (!selectedTarget||selectedTarget.kind==='local') ? safeWorkspacePath(root,file) : null;if(selected&&(!selected.ok||(!fs.existsSync(selected.target)||!fs.statSync(selected.target).isFile())))return {ok:false,error:'Selected test file is outside this workspace or no longer exists.'};const selectedNode=node?catalog.nodes.find(item=>item.id===node):null;if(node&&!selectedNode)return {ok:false,error:'Selected test node is outside this workspace or no longer exists.'};if((selected||selectedNode)&&test.id!=='python:pytest')return {ok:false,error:'Focused file and test-node runs currently support the pytest target.'};if(selected&&selectedNode&&selectedNode.path!==file)return {ok:false,error:'Selected test node does not belong to the selected test file.'};let result;if(test.id.startsWith('npm:'))result=await runOnExecutionTarget(selectedTarget,root,'npm',['run',test.id.slice(4)],{timeoutMs:600000,outputLimit:768000});else if(test.id==='python:pytest')result=await runOnExecutionTarget(selectedTarget,root,'python3',['-m','pytest',...(selectedNode?[selectedNode.id]:selected?[file]:[])],{timeoutMs:600000,outputLimit:768000});else result=await runOnExecutionTarget(selectedTarget,root,'python3',['manage.py','test'],{timeoutMs:600000,outputLimit:768000});const target=selectedNode?.id||file;const executionTarget=executionTargetSummary(selectedTarget||getTargetHost().getActiveExecutionTarget());const digest=crypto.createHash('sha256').update(`${root}\n${test.id}\n${target}\n${executionTarget.kind}\n${result.stdout}\n${result.stderr}\n${result.returncode}`).digest('hex');return {...result,test,file:target,node:selectedNode?.id||'',executionTarget,receipt:{id:`TEST-${digest.slice(0,16).toUpperCase()}`,digest:`sha256:${digest}`,evidence:'operator-initiated',mode:`${test.framework}:${executionTarget.kind}`}};
  }
  async function runWorkspaceTask(rootPath,payload) {
    const root=path.resolve(rootPath || repoRoot);const taskId=String(typeof payload==='string'?payload:payload?.id||'');const selectedTarget=typeof payload==='object'?payload?.target:null;if(!/^[A-Za-z0-9:_./-]{1,120}$/.test(taskId))return {ok:false,error:'Unsupported task identifier.'};const listed=workspaceTasks(root).tasks;const task=listed.find(item=>item.id===taskId)||listed.find(item=>item.kind==='npm'&&item.script===taskId);if(!task)return {ok:false,error:'Task is not declared in package.json or .vscode/tasks.json.'};const cwd=taskCwd(root,task.cwd);if(!cwd)return {ok:false,error:'Task working directory escaped the active workspace.'};const env={...process.env,...taskEnvironment(task.env)};let result;if(task.kind==='npm')result=await runOnExecutionTarget(selectedTarget,root,'npm',['run',task.script],{cwd,env,timeoutMs:60000,outputLimit:512000});else result=await runOnExecutionTarget(selectedTarget,root,task.command,task.args,{cwd,env,timeoutMs:60000,outputLimit:512000,shell:task.kind==='shell'});const executionTarget=executionTargetSummary(selectedTarget||getTargetHost().getActiveExecutionTarget());const digest=crypto.createHash('sha256').update(`${root}\n${task.id}\n${task.kind}\n${task.command}\n${task.args.join('\u0000')}\n${executionTarget.kind}\n${result.stdout}\n${result.stderr}\n${result.returncode}`).digest('hex');return {...result,executionTarget,task:{id:task.id,label:task.label,source:task.source,kind:task.kind},receipt:{id:`TASK-${digest.slice(0,16).toUpperCase()}`,digest:`sha256:${digest}`,evidence:'operator-initiated',mode:`${task.source}:${executionTarget.kind}`}};
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

  return {
    parseJsonc,
    taskEnvironment,
    taskFingerprint,
    safeTaskRegexSource,
    normalizeTaskMatcher,
    normalizeTaskMatchers,
    workspaceTasks,
    workspaceSettings,
    writeWorkspaceSettings,
    pytestTestNodes,
    workspaceTests,
    workspaceTestsForTarget,
    runWorkspaceTest,
    runWorkspaceTask,
    taskProblemPath,
    taskProblemFromLine,
    WorkspaceTaskHost,
    workspaceTaskHost,
  };
}

module.exports = { createTaskTestHost };
