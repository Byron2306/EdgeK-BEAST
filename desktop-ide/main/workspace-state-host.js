'use strict';

const fs = require('fs');
const path = require('path');

function createWorkspaceStateHost({ app, repoRoot, workspaceFileCandidates, appendLog = () => {}, initialWorkspaceRoot = '' }) {
  let activeWorkspaceRoot = path.resolve(initialWorkspaceRoot || process.env.BEAST_ACTIVE_WORKSPACE || process.env.BEAST_WORKSPACE || repoRoot);
  let activeWorkspaceRoots = [activeWorkspaceRoot];

  function workspaceFoldersStatePath() {
    return path.join(app.getPath('userData'), 'beast-desktop-workspace-folders.json');
  }

  function normalizeWorkspaceRoots(roots, primary = activeWorkspaceRoot) {
    const unique = [path.resolve(primary || repoRoot), ...(Array.isArray(roots) ? roots : [])]
      .filter(item => {
        try { return fs.existsSync(path.resolve(item)) && fs.statSync(path.resolve(item)).isDirectory(); }
        catch (_) { return false; }
      })
      .filter((item, index, all) => all.indexOf(item) === index)
      .slice(0, 12);
    const used = new Map();
    return unique.map((rootPath, index) => {
      const base = path.basename(rootPath).replace(/[^A-Za-z0-9._-]/g, '-') || `folder-${index + 1}`;
      const count = (used.get(base) || 0) + 1;
      used.set(base, count);
      return { id: count === 1 ? base : `${base}-${count}`, name: base, path: rootPath, primary: index === 0 };
    });
  }

  function workspaceFolders() {
    return normalizeWorkspaceRoots(activeWorkspaceRoots, activeWorkspaceRoot);
  }

  function persistWorkspaceFolders() {
    try {
      const folders = workspaceFolders();
      fs.mkdirSync(path.dirname(workspaceFoldersStatePath()), { recursive: true });
      fs.writeFileSync(workspaceFoldersStatePath(), JSON.stringify({ primary: activeWorkspaceRoot, roots: folders.map(item => item.path) }));
    } catch (error) {
      appendLog(`workspace folder persistence failed: ${error.message || error}`);
    }
  }

  function restoreWorkspaceFolders() {
    try {
      const saved = JSON.parse(fs.readFileSync(workspaceFoldersStatePath(), 'utf8'));
      if (Array.isArray(saved?.roots) && saved.roots.length) setWorkspaceRoots(saved.roots, saved.primary || saved.roots[0], false);
    } catch (_) {}
    return workspaceFolders();
  }

  function setWorkspaceRoots(roots, primary = '', persist = true) {
    const first = primary ? path.resolve(primary) : path.resolve((roots || [])[0] || activeWorkspaceRoot || repoRoot);
    activeWorkspaceRoot = first;
    activeWorkspaceRoots = normalizeWorkspaceRoots(roots, first).map(item => item.path);
    if (persist) persistWorkspaceFolders();
    return workspaceFolders();
  }

  function parseWorkspaceReference(reference) {
    const value = String(reference || '');
    const match = value.match(/^@([^/]+)\/(.+)$/);
    if (!match) return { folder: workspaceFolders()[0], relative: value };
    const folder = workspaceFolders().find(item => item.id === match[1]);
    return { folder, relative: match[2] };
  }

  function multiRootFiles(limit = 2000) {
    const folders = workspaceFolders();
    const perRoot = Math.max(1, Math.ceil(limit / Math.max(1, folders.length)));
    return folders.flatMap(folder => workspaceFileCandidates(folder.path, perRoot).map(item => ({
      ...item,
      path: folders.length === 1 ? item.path : `@${folder.id}/${item.path}`,
      relativePath: item.path,
      rootId: folder.id,
      rootName: folder.name,
      rootPath: folder.path,
    }))).slice(0, limit);
  }

  function reorderWorkspaceFolders(orderedIds = []) {
    const current = workspaceFolders();
    const byId = new Map(current.map(item => [item.id, item]));
    const ordered = [];
    for (const id of Array.isArray(orderedIds) ? orderedIds : []) {
      const folder = byId.get(String(id));
      if (folder && !ordered.includes(folder)) ordered.push(folder);
    }
    for (const folder of current) if (!ordered.includes(folder)) ordered.push(folder);
    const primary = current.find(item => item.primary) || ordered[0];
    const roots = [primary, ...ordered.filter(item => item !== primary)].map(item => item.path);
    return setWorkspaceRoots(roots, primary.path);
  }

  function renameWorkspaceFolder(id, name) {
    const folders = workspaceFolders();
    const folder = folders.find(item => item.id === String(id || ''));
    const label = String(name || '').trim().slice(0, 80);
    if (!folder) return { ok:false, error:'Unknown workspace folder.' };
    if (!label) return { ok:false, error:'Workspace folder name is required.' };
    const aliasesPath = path.join(app.getPath('userData'), 'beast-desktop-workspace-aliases.json');
    let aliases={}; try { aliases=JSON.parse(fs.readFileSync(aliasesPath,'utf8')); } catch (_) {}
    aliases[folder.path]=label;
    fs.mkdirSync(path.dirname(aliasesPath), {recursive:true});
    fs.writeFileSync(aliasesPath, JSON.stringify(aliases, null, 2));
    return { ok:true, id:folder.id, path:folder.path, name:label };
  }

  function workspaceFileSnapshot() {
    const aliasesPath = path.join(app.getPath('userData'), 'beast-desktop-workspace-aliases.json');
    let aliases={}; try { aliases=JSON.parse(fs.readFileSync(aliasesPath,'utf8')); } catch (_) {}
    return workspaceFolders().map(item => ({...item, name: aliases[item.path] || item.name}));
  }

  function exportWorkspaceFile(targetPath='') {
    const destination=path.resolve(String(targetPath||''));
    if(!destination.endsWith('.code-workspace')) return {ok:false,error:'Workspace files must use .code-workspace.'};
    const payload={folders:workspaceFileSnapshot().map(folder=>({path:folder.path,name:folder.name})),settings:{'beast.primaryFolder':workspaceStateHostPrimary()}};
    fs.mkdirSync(path.dirname(destination),{recursive:true});
    const tmp=`${destination}.tmp-${process.pid}`;fs.writeFileSync(tmp,JSON.stringify(payload,null,2));fs.renameSync(tmp,destination);
    return {ok:true,path:destination,folders:payload.folders.length};
  }

  function workspaceStateHostPrimary(){ return activeWorkspaceRoot; }

  function importWorkspaceFile(sourcePath='') {
    const source=path.resolve(String(sourcePath||''));
    if(!source.endsWith('.code-workspace')) return {ok:false,error:'Workspace files must use .code-workspace.'};
    let payload;try{payload=JSON.parse(fs.readFileSync(source,'utf8'));}catch(error){return {ok:false,error:String(error.message||error)}}
    const roots=(Array.isArray(payload?.folders)?payload.folders:[]).map(item=>path.resolve(path.dirname(source),String(item?.path||''))).filter(Boolean);
    if(!roots.length)return {ok:false,error:'Workspace file contains no valid folders.'};
    const folders=setWorkspaceRoots(roots,roots[0]);
    return {ok:true,path:source,folders};
  }

  function registeredWorkspaceRoot(payload = {}) {
    const folder = workspaceFolders().find(item => item.id === String(payload?.rootId || ''));
    return folder?.path || activeWorkspaceRoot || repoRoot;
  }

  return {
    getActiveWorkspaceRoot: () => activeWorkspaceRoot,
    getActiveWorkspaceRoots: () => [...activeWorkspaceRoots],
    workspaceFoldersStatePath,
    normalizeWorkspaceRoots,
    workspaceFolders: workspaceFileSnapshot,
    persistWorkspaceFolders,
    restoreWorkspaceFolders,
    setWorkspaceRoots,
    parseWorkspaceReference,
    multiRootFiles,
    registeredWorkspaceRoot,
    reorderWorkspaceFolders,
    renameWorkspaceFolder,
    exportWorkspaceFile,
    importWorkspaceFile,
  };
}

module.exports = { createWorkspaceStateHost };
