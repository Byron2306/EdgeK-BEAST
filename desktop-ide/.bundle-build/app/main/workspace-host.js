const fs = require('fs');
const path = require('path');

function workspaceFoldersStatePath(app) {
  return path.join(app.getPath('userData'), 'beast-desktop-workspace-folders.json');
}

function normalizeWorkspaceRoots(roots, primary = '', fallbackRoot) {
  const validRoots = (Array.isArray(roots) ? roots : [roots]).map(item => path.resolve(String(item || '').trim())).filter(Boolean);
  if (!validRoots.length) validRoots.push(path.resolve(fallbackRoot));
  const primaryRoot = path.resolve(primary || validRoots[0]);
  if (!validRoots.includes(primaryRoot)) validRoots.unshift(primaryRoot);
  const unique = [...new Set(validRoots)];
  return unique.map((rootPath, index) => ({
    id: path.basename(rootPath).toLowerCase().replace(/[^a-z0-9]/g, '') + (index > 0 ? String(index + 1) : ''),
    name: path.basename(rootPath),
    path: rootPath,
    primary: rootPath === primaryRoot,
  }));
}

function createWorkspaceHost({ app, dialog, repoRoot, appendLog, getMainWindow, getAppWindows, ipcRegistry, BrowserWindow }) {
  let activeWorkspaceRoot = path.resolve(process.env.BEAST_ACTIVE_WORKSPACE || process.env.BEAST_WORKSPACE || repoRoot);
  let activeWorkspaceRoots = [activeWorkspaceRoot];

  function workspaceFolders() {
    return normalizeWorkspaceRoots(activeWorkspaceRoots, activeWorkspaceRoot, repoRoot);
  }

  function persistWorkspaceFolders() {
    try {
      const folders = workspaceFolders();
      fs.mkdirSync(path.dirname(workspaceFoldersStatePath(app)), { recursive: true });
      fs.writeFileSync(workspaceFoldersStatePath(app), JSON.stringify({ primary: activeWorkspaceRoot, roots: folders.map(item => item.path) }));
    } catch (error) {
      appendLog(`workspace folder persistence failed: ${error.message || error}`);
    }
  }

  function setWorkspaceRoots(roots, primary = '', persist = true) {
    const first = primary ? path.resolve(primary) : path.resolve((roots || [])[0] || activeWorkspaceRoot || repoRoot);
    activeWorkspaceRoot = first;
    activeWorkspaceRoots = normalizeWorkspaceRoots(roots, first, repoRoot).map(item => item.path);
    if (persist) persistWorkspaceFolders();

    for (const windowRef of getAppWindows()) {
        if (!windowRef.isDestroyed()) windowRef.webContents.send('beast:workspace-changed', { root: activeWorkspaceRoot, folders: workspaceFolders() });
    }

    return workspaceFolders();
  }

  function restoreWorkspaceFolders() {
    try {
      const saved = JSON.parse(fs.readFileSync(workspaceFoldersStatePath(app), 'utf8'));
      if (Array.isArray(saved?.roots) && saved.roots.length) {
        setWorkspaceRoots(saved.roots, saved.primary || saved.roots[0], false);
      }
    } catch (_) {
      // ignore
    }
  }
  
  function getActiveWorkspaceRoot() {
      return activeWorkspaceRoot;
  }

  function parseWorkspaceReference(reference) {
    const value = String(reference || '');
    const match = value.match(/^@([^/]+)\/(.+)$/);
    if (!match) {
      return { folder: workspaceFolders()[0], relative: value };
    }
    const folder = workspaceFolders().find(item => item.id === match[1]);
    return { folder, relative: match[2] };
  }

  function multiRootFiles(limit = 2000, workspaceFileCandidates) {
    const folders = workspaceFolders();
    const perRoot = Math.max(1, Math.ceil(limit / Math.max(1, folders.length)));
    return folders.flatMap(folder => workspaceFileCandidates(folder.path, perRoot).map(item => ({ ...item, path: folders.length === 1 ? item.path : `@${folder.id}/${item.path}`, relativePath: item.path, rootId: folder.id, rootName: folder.name, rootPath: folder.path }))).slice(0, limit);
  }
  
  function registeredWorkspaceRoot(payload = {}) {
    const folder = workspaceFolders().find(item => item.id === String(payload?.rootId || ''));
    return folder?.path || activeWorkspaceRoot || repoRoot;
  }
  
  ipcRegistry.handle('beast:choose-workspace', async (event) => {
      const windowRef = BrowserWindow.fromWebContents(event.sender) || getMainWindow();
      const result = await dialog.showOpenDialog(windowRef, { properties: ['openDirectory'] });
      if (result.canceled || !result.filePaths[0]) return { root: activeWorkspaceRoot, folders: workspaceFolders() };
      const folders = setWorkspaceRoots([result.filePaths[0]], result.filePaths[0]);
      return { root: activeWorkspaceRoot, folders };
  });

  ipcRegistry.handle('beast:workspace-folders', async () => ({ root: activeWorkspaceRoot, folders: workspaceFolders() }));

  ipcRegistry.handle('beast:workspace-folder-add', async (event) => {
      const windowRef = BrowserWindow.fromWebContents(event.sender) || getMainWindow();
      const result = await dialog.showOpenDialog(windowRef, { properties: ['openDirectory'] });
      if (result.canceled || !result.filePaths[0]) return { root: activeWorkspaceRoot, folders: workspaceFolders() };
      const folders = setWorkspaceRoots([...activeWorkspaceRoots, result.filePaths[0]], activeWorkspaceRoot);
      return { root: activeWorkspaceRoot, folders };
  });

  ipcRegistry.handle('beast:workspace-folder-remove', async (_event, id) => {
      const folder = workspaceFolders().find(item => item.id === String(id || ''));
      if (!folder || folder.primary) return { ok: false, error: 'The primary workspace folder cannot be removed.' };
      const folders = setWorkspaceRoots(activeWorkspaceRoots.filter(item => path.resolve(item) !== folder.path), activeWorkspaceRoot);
      return { ok: true, root: activeWorkspaceRoot, folders };
  });
  
  return {
    restoreWorkspaceFolders,
    setWorkspaceRoots,
    workspaceFolders,
    getActiveWorkspaceRoot,
    parseWorkspaceReference,
    multiRootFiles,
    registeredWorkspaceRoot,
  }
}

module.exports = { createWorkspaceHost, workspaceFoldersStatePath, normalizeWorkspaceRoots };
