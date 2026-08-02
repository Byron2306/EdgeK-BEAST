'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');

const SCHEMA = 'beast.desktop-profile.v2';
const MAX_BYTES = 1024 * 1024;
const PROFILE_KEYS = ['settings','keybindings','layout','extensionSet','uiDensity','modelRoute','trustDefaults'];
const SCOPES = new Set(['user','workspace','folder','language','target']);

function object(value){ return value && typeof value === 'object' && !Array.isArray(value) ? value : {}; }
function clone(value){ return JSON.parse(JSON.stringify(value)); }
function stable(value){ if(Array.isArray(value))return value.map(stable);if(value&&typeof value==='object'){return Object.keys(value).sort().reduce((o,k)=>(o[k]=stable(value[k]),o),{});}return value; }
function digest(value){ return `sha256:${crypto.createHash('sha256').update(JSON.stringify(stable(value))).digest('hex')}`; }
function safeWrite(file, value){ const encoded=`${JSON.stringify(value,null,2)}\n`;if(Buffer.byteLength(encoded)>MAX_BYTES)throw new Error('Settings/profile payload exceeds 1 MiB.');fs.mkdirSync(path.dirname(file),{recursive:true});const tmp=`${file}.${process.pid}.tmp`;fs.writeFileSync(tmp,encoded,{encoding:'utf8',mode:0o600});fs.renameSync(tmp,file); }
function read(file, fallback={}){ try{return JSON.parse(fs.readFileSync(file,'utf8'));}catch(error){if(error.code==='ENOENT')return clone(fallback);throw error;} }
function contained(root,target){const rel=path.relative(path.resolve(root),path.resolve(target));return rel===''||(!rel.startsWith('..')&&!path.isAbsolute(rel));}

function migrate(input){
  const raw=object(input); const from=String(raw.schema||raw.version||'beast.desktop-profile.v1');
  if(from===SCHEMA)return {profile:{...raw,schema:SCHEMA,version:2},migrated:false,from};
  if(from==='beast.desktop-profile.v1'||from==='1'||from==='v1'){
    const profile={schema:SCHEMA,version:2,name:String(raw.name||'Imported profile'),createdAt:raw.createdAt||Date.now(),updatedAt:Date.now(),settings:object(raw.settings),keybindings:object(raw.keybindings),layout:object(raw.layout),extensionSet:Array.isArray(raw.extensionSet)?raw.extensionSet:[],uiDensity:raw.uiDensity||raw.density||'comfortable',modelRoute:object(raw.modelRoute||raw.model),trustDefaults:object(raw.trustDefaults||raw.trust),metadata:{...object(raw.metadata),migratedFrom:from}};
    return {profile,migrated:true,from};
  }
  throw new Error(`Unsupported profile schema: ${from}`);
}

function validateProfile(input){const {profile,migrated,from}=migrate(input);for(const key of PROFILE_KEYS)if(!(key in profile))throw new Error(`Profile is missing ${key}.`);if(!Array.isArray(profile.extensionSet))throw new Error('extensionSet must be an array.');return {profile:{...profile,digest:digest({...profile,digest:undefined})},migrated,from};}

function createSettingsProfileHost({configRoot=path.join(os.homedir(),'.config','edgek-beast'), workspaceRoot=()=>process.cwd()}={}){
  const userFile=path.join(configRoot,'desktop-settings.v2.json');
  const scopeFile=(scope,payload={})=>{
    if(!SCOPES.has(scope))throw new Error(`Unsupported settings scope: ${scope}`);
    const root=path.resolve(payload.root||workspaceRoot());
    if(scope==='user')return userFile;
    if(scope==='workspace')return path.join(root,'.beast','settings.workspace.json');
    if(scope==='folder')return path.join(path.resolve(payload.folderRoot||root),'.beast','settings.folder.json');
    if(scope==='language')return path.join(root,'.beast','settings.languages.json');
    return path.join(root,'.beast','settings.targets.json');
  };
  function getScope(payload={}){const scope=String(payload.scope||'user');const file=scopeFile(scope,payload);const doc=object(read(file,{schema:'beast.settings-scope.v1',scope,values:{}}));let values=object(doc.values);if(scope==='language')values=object(values[String(payload.language||'plaintext')]);if(scope==='target')values=object(values[String(payload.target||'local')]);return {ok:true,scope,values,source:file,digest:digest(values)};}
  function setScope(payload={}){const scope=String(payload.scope||'user');const file=scopeFile(scope,payload);const current=object(read(file,{schema:'beast.settings-scope.v1',scope,values:{}}));const nextValues=object(payload.values);if(scope==='language'){current.values=object(current.values);current.values[String(payload.language||'plaintext')]=nextValues;}else if(scope==='target'){current.values=object(current.values);current.values[String(payload.target||'local')]=nextValues;}else current.values=nextValues;const next={...current,schema:'beast.settings-scope.v1',scope,updatedAt:Date.now()};safeWrite(file,next);return {...getScope(payload),receipt:{id:`SET-${digest(next).slice(7,23).toUpperCase()}`,digest:digest(next)}};}
  function effective(payload={}){const layers=['user','workspace','folder','language','target'].map(scope=>getScope({...payload,scope}));const values=layers.reduce((acc,row)=>Object.assign(acc,row.values),{});return {ok:true,values,layers,digest:digest(values)};}
  function projectFile(payload={}){const root=path.resolve(payload.root||workspaceRoot());return path.join(root,'.beast','profile.json');}
  function exportProfile(payload={}){const root=path.resolve(payload.root||workspaceRoot());const profile={schema:SCHEMA,version:2,name:String(payload.name||path.basename(root)||'BEAST profile'),createdAt:Date.now(),updatedAt:Date.now(),settings:effective(payload).values,keybindings:object(payload.keybindings),layout:object(payload.layout),extensionSet:Array.isArray(payload.extensionSet)?payload.extensionSet:[],uiDensity:String(payload.uiDensity||'comfortable'),modelRoute:object(payload.modelRoute),trustDefaults:object(payload.trustDefaults),metadata:{projectRoot:root,product:'BEAST IDE'}};const checked=validateProfile(profile).profile;const file=path.resolve(payload.file||projectFile(payload));if(payload.file&&!contained(root,file)&&!payload.allowExternal)throw new Error('External profile export requires explicit allowExternal.');safeWrite(file,checked);return {ok:true,file,profile:checked,digest:checked.digest};}
  function importProfile(payload={}){const root=path.resolve(payload.root||workspaceRoot());const file=path.resolve(payload.file||projectFile(payload));if(!contained(root,file)&&!payload.allowExternal)throw new Error('External profile import requires explicit allowExternal.');const checked=validateProfile(read(file));if(payload.apply!==false){setScope({...payload,scope:'workspace',values:checked.profile.settings});}return {ok:true,file,profile:checked.profile,migrated:checked.migrated,from:checked.from,applied:payload.apply!==false};}
  function saveProjectProfile(payload={}){return exportProfile({...payload,file:projectFile(payload)});}
  function loadProjectProfile(payload={}){const file=projectFile(payload);if(!fs.existsSync(file))return {ok:true,exists:false,file,profile:null};return {...importProfile({...payload,file,apply:false}),exists:true};}
  return {getScope,setScope,effective,exportProfile,importProfile,saveProjectProfile,loadProjectProfile,migrate,validateProfile,SCHEMA};
}
module.exports={createSettingsProfileHost,migrate,validateProfile,SCHEMA};
