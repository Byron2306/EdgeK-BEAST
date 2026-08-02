'use strict';

const fs = require('fs');
const path = require('path');
const { createSettingsProfileHost } = require('./settings-profile-host');
const { createPhaseEvidenceHost } = require('./phase-evidence-host');

function registerIpcHandlers({
  ipcMain,
  BrowserWindow,
  dialog,
  shell,
  repoRoot,
  desktopRoot,
  desktopVersion,
  workspaceStateHost,
  windowHost,
  gatewayHost,
  diagnosticsHost,
  workspaceFileHost,
  editorDocumentHost,
  gitHost,
  taskTestHost,
  executionTargetHost,
  notebookExecutionHost,
  notebookKernelHost,
  ideCompatibilityHost,
  beastExtensionHost,
  workspaceTrustHost,
}) {
  const { workspaceFileCandidates, enumerateWorkspaceTree, readWorkspaceFile, textWorkspaceSearch, workspaceReplacePreview, mutateWorkspaceFile, undoWorkspaceFile, startWatch, stopWatch } = workspaceFileHost;
  const { workspaceGitStatus, workspaceGitDiff, workspaceGitHunks, workspaceGitHunkAction, workspaceGitConflict, workspaceGitResolve, workspaceGitAction, workspaceGitCommit, workspaceGitBranch, workspaceGitHistory, workspaceGitRemotes, workspaceGitOperation } = gitHost;
  const { workspaceTasks, workspaceSettings, writeWorkspaceSettings, workspaceTestsForTarget, runWorkspaceTest, runWorkspaceTask, workspaceTaskHost } = taskTestHost;
  const { executionTargetSummary, setActiveExecutionTarget, listExecutionTargets, workspaceTargetListFiles, workspaceTargetReadFile, workspaceTargetWriteFile, probeRemoteWorkspace, listRemoteWorkspaceFiles, searchRemoteWorkspace, reconnectRemoteWorkspace, remoteWorkspaceHealth, readRemoteWorkspaceFile, writeRemoteWorkspaceFile, runRemoteTerminal, inspectDevContainers, startDevContainer, stopDevContainer, restartDevContainer, attachDevContainer, rebuildDevContainer, devContainerLogs, runDevContainerTerminal, sshForwardHost, remoteTerminalHost, localTerminalHost } = executionTargetHost;
  const { executeNotebookCell } = notebookExecutionHost;
  const gatewayEventStreamHost = gatewayHost.gatewayEventStreamHost;
  const gatewayRequest = gatewayHost.gatewayRequest;
  const workspaceFolders = workspaceStateHost.workspaceFolders;
  const setWorkspaceRoots = workspaceStateHost.setWorkspaceRoots;
  const parseWorkspaceReference = workspaceStateHost.parseWorkspaceReference;
  const multiRootFiles = workspaceStateHost.multiRootFiles;
  const registeredWorkspaceRoot = workspaceStateHost.registeredWorkspaceRoot;

  const rawHandle = ipcMain.handle.bind(ipcMain);
  const handle = (channel, listener) => rawHandle(channel, async (event, ...args) => {
    workspaceTrustHost.assertAllowed(channel, args);
    return listener(event, ...args);
  });

  handle('beast:workspace-trust-get', async (_event, payload) => workspaceTrustHost.snapshot(payload?.workspaceRoot));
  handle('beast:workspace-trust-set', async (_event, payload) => workspaceTrustHost.setMode(payload || {}));
  const settingsProfileHost = createSettingsProfileHost({ workspaceRoot: () => workspaceStateHost.getActiveWorkspaceRoot() || repoRoot });
  const phaseEvidenceHost = createPhaseEvidenceHost({ workspaceRoot: () => workspaceStateHost.getActiveWorkspaceRoot(), repoRoot });
  const reorderWorkspaceFolders = workspaceStateHost.reorderWorkspaceFolders;
  const renameWorkspaceFolder = workspaceStateHost.renameWorkspaceFolder;
  const exportWorkspaceFile = workspaceStateHost.exportWorkspaceFile;
  const importWorkspaceFile = workspaceStateHost.importWorkspaceFile;

  handle('beast:settings-scope-get', async (_event,payload) => settingsProfileHost.getScope(payload || {}));
  handle('beast:settings-scope-set', async (_event,payload) => settingsProfileHost.setScope(payload || {}));
  handle('beast:settings-effective', async (_event,payload) => settingsProfileHost.effective(payload || {}));
  handle('beast:profile-export', async (_event,payload) => settingsProfileHost.exportProfile(payload || {}));
  handle('beast:profile-import', async (_event,payload) => settingsProfileHost.importProfile(payload || {}));
  handle('beast:project-profile-save', async (_event,payload) => settingsProfileHost.saveProjectProfile(payload || {}));
  handle('beast:project-profile-load', async (_event,payload) => settingsProfileHost.loadProjectProfile(payload || {}));

  handle('beast:status', async event => {
    const health = await gatewayHost.recoverStatusHealth();
    const windowRef = BrowserWindow.fromWebContents(event.sender);
    const runtimeStack = await gatewayHost.runtimeStackHealth(health.url || gatewayHost.getGatewayUrl());
    const snapshot = gatewayHost.getSnapshot();
    return {
      gatewayUrl: health.url || gatewayHost.getGatewayUrl(),
      repoRoot: workspaceStateHost.getActiveWorkspaceRoot() || repoRoot,
      workspaceFolders: workspaceFolders(),
      beastRepoRoot: repoRoot,
      health,
      runtimeStack,
      processPid: snapshot.processPid,
      lastGatewayCommand: snapshot.lastGatewayCommand,
      gatewayLog: snapshot.log,
      desktopVersion,
      rendererPath: path.join(desktopRoot, 'renderer', 'index.html'),
      windowId: windowRef?.id || null,
      windowCount: windowHost.getWindowCount(),
    };
  });

  handle('beast:editor-document-create', async (_event, payload) => editorDocumentHost.create(payload || {}));
  handle('beast:editor-document-get', async (_event, id, options) => editorDocumentHost.get(id, options || {}));
  handle('beast:editor-document-list', async () => ({ ok: true, documents: editorDocumentHost.list() }));
  handle('beast:editor-document-update', async (_event, id, payload) => editorDocumentHost.update(id, payload || {}));
  handle('beast:editor-document-refresh', async (_event, id) => editorDocumentHost.refresh(id));
  handle('beast:editor-document-save', async (_event, id, payload) => editorDocumentHost.save(id, payload || {}));
  handle('beast:editor-document-binary-preview', async (_event, id, payload) => editorDocumentHost.binaryPreview(id, payload || {}));
  handle('beast:editor-document-open-external', async (_event, id) => {
    const target = editorDocumentHost.externalOpenTarget(id);
    const error = await shell.openPath(target);
    if (error) throw new Error(error);
    return { ok: true, target };
  });

  handle('beast:gateway-request', async (_event, payload) => gatewayRequest(payload || {}));
  handle('beast:gateway-stream-start', async (event, payload) => gatewayEventStreamHost.start(payload || {}, event.sender));
  handle('beast:gateway-stream-stop', async (_event, id) => gatewayEventStreamHost.stop(id));
  handle('beast:phase-evidence', async () => phaseEvidenceHost.snapshot());

function normalizedZoomLevel(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? Math.max(-3, Math.min(5, Math.round(numeric))) : 0;
}

handle('beast:zoom-get', async event => {
  const windowRef = BrowserWindow.fromWebContents(event.sender) || windowHost.getMainWindow();
  return { level: windowRef?.webContents.getZoomLevel?.() ?? 0, factor: windowRef?.webContents.getZoomFactor?.() ?? 1 };
});
handle('beast:zoom-set', async (event, requestedLevel) => {
  const windowRef = BrowserWindow.fromWebContents(event.sender) || windowHost.getMainWindow();
  if (!windowRef || windowRef.isDestroyed()) throw new Error('No BEAST desktop window is available for zoom.');
  const level = normalizedZoomLevel(requestedLevel); windowRef.webContents.setZoomLevel(level);
  return { level, factor: windowRef.webContents.getZoomFactor() };
});
handle('beast:zoom-reset', async event => {
  const windowRef = BrowserWindow.fromWebContents(event.sender) || windowHost.getMainWindow();
  if (!windowRef || windowRef.isDestroyed()) throw new Error('No BEAST desktop window is available for zoom.');
  windowRef.webContents.setZoomLevel(0); return { level: 0, factor: windowRef.webContents.getZoomFactor() };
});

handle('beast:choose-workspace', async event => {
  const windowRef = BrowserWindow.fromWebContents(event.sender) || windowHost.getMainWindow();
  const result = await dialog.showOpenDialog(windowRef, { properties: ['openDirectory'] });
  if (result.canceled || !result.filePaths[0]) return '';
  const folders=setWorkspaceRoots([result.filePaths[0]],result.filePaths[0]);
  return {root:workspaceStateHost.getActiveWorkspaceRoot(),folders};
});
handle('beast:workspace-folders', async () => ({root:workspaceStateHost.getActiveWorkspaceRoot(),folders:workspaceFolders()}));
handle('beast:workspace-folder-add', async event => { const windowRef=BrowserWindow.fromWebContents(event.sender)||windowHost.getMainWindow();const result=await dialog.showOpenDialog(windowRef,{properties:['openDirectory']});if(result.canceled||!result.filePaths[0])return {root:workspaceStateHost.getActiveWorkspaceRoot(),folders:workspaceFolders()};const folders=setWorkspaceRoots([...workspaceStateHost.getActiveWorkspaceRoots(),result.filePaths[0]],workspaceStateHost.getActiveWorkspaceRoot());return {root:workspaceStateHost.getActiveWorkspaceRoot(),folders}; });
handle('beast:workspace-folder-remove', async (_event,id) => { const folder=workspaceFolders().find(item=>item.id===String(id||''));if(!folder||folder.primary)return {ok:false,error:'The primary workspace folder cannot be removed.'};const folders=setWorkspaceRoots(workspaceStateHost.getActiveWorkspaceRoots().filter(item=>path.resolve(item)!==folder.path),workspaceStateHost.getActiveWorkspaceRoot());return {ok:true,root:workspaceStateHost.getActiveWorkspaceRoot(),folders}; });
handle('beast:workspace-folder-reorder', async (_event,ids) => ({ok:true,folders:reorderWorkspaceFolders(ids)}));
handle('beast:workspace-folder-rename', async (_event,payload) => renameWorkspaceFolder(payload?.id,payload?.name));
handle('beast:workspace-file-export', async (_event,targetPath) => exportWorkspaceFile(targetPath));
handle('beast:workspace-file-import', async (_event,sourcePath) => importWorkspaceFile(sourcePath));
handle('beast:workspace-tree-page', async (_event,payload) => enumerateWorkspaceTree(registeredWorkspaceRoot(payload),payload||{}));
handle('beast:workspace-operation-undo', async (_event,payload) => undoWorkspaceFile(registeredWorkspaceRoot(payload),payload?.undoId||''));
handle('beast:workspace-watch-start', async (event,payload) => startWatch(registeredWorkspaceRoot(payload),event.sender,payload||{}));
handle('beast:workspace-watch-stop', async (_event,id) => stopWatch(id));
handle('beast:execution-target-get', async () => ({ok:true,target:executionTargetSummary()}));
handle('beast:execution-target-set', async (_event,payload) => setActiveExecutionTarget(payload || {}));
handle('beast:execution-target-list', async (_event,payload) => listExecutionTargets(registeredWorkspaceRoot(payload || {})));


handle('beast:restart-gateway', async () => gatewayHost.restartGateway());

handle('beast:reset-runtime-stack', async () => gatewayHost.resetRuntimeStack());

handle('beast:open-gateway', async () => {
  await shell.openExternal(gatewayHost.getGatewayUrl());
  return { ok: true, gatewayUrl:gatewayHost.getGatewayUrl() };
});

handle('beast:list-files', async (_event, rootPath, limit) => {
  if(!rootPath||path.resolve(rootPath)===workspaceStateHost.getActiveWorkspaceRoot())return multiRootFiles(Math.max(1, Math.min(Number(limit || 400), 2000)));
  return workspaceFileCandidates(rootPath, Math.max(1, Math.min(Number(limit || 400), 2000)));
});

handle('beast:read-file', async (_event, rootPath, relPath, maxChars) => {
  const ref=parseWorkspaceReference(relPath);if(!ref.folder)return {ok:false,error:'Unknown workspace folder reference.',path:relPath};return readWorkspaceFile(ref.folder.path,ref.relative, Math.max(1, Math.min(Number(maxChars || 200000), 1000000)));
});
handle('beast:workspace-target-list-files', async (_event, payload) => workspaceTargetListFiles(registeredWorkspaceRoot(payload || {}), payload || {}));
handle('beast:workspace-target-read-file', async (_event, payload) => workspaceTargetReadFile(registeredWorkspaceRoot(payload || {}), payload || {}));
handle('beast:workspace-target-write-file', async (_event, payload) => workspaceTargetWriteFile(registeredWorkspaceRoot(payload || {}), payload || {}));

handle('beast:workspace-search', async (_event, payload) => textWorkspaceSearch(registeredWorkspaceRoot(payload),payload || {}));
handle('beast:workspace-replace', async (_event, payload) => workspaceReplacePreview(registeredWorkspaceRoot(payload),payload || {}));
handle('beast:workspace-git-status', async (_event,payload) => workspaceGitStatus(registeredWorkspaceRoot(payload)));
handle('beast:workspace-git-repositories', async () => ({ok:true,repositories:await Promise.all(workspaceFolders().map(async folder=>{const status=await workspaceGitStatus(folder.path);return {folder,status:{ok:status.ok,branch:status.branch||'',branchName:status.branchName||'',counts:status.counts||{staged:0,unstaged:0,conflicts:0},changes:status.changes||[],error:status.error||''}};}))}));
handle('beast:workspace-git-action', async (_event, payload) => workspaceGitAction(registeredWorkspaceRoot(payload),payload?.action,payload?.path));
handle('beast:workspace-git-diff', async (_event, payload) => workspaceGitDiff(registeredWorkspaceRoot(payload),payload || {}));
handle('beast:workspace-git-commit', async (_event, payload) => workspaceGitCommit(registeredWorkspaceRoot(payload),payload || {}));
handle('beast:workspace-git-branch', async (_event, payload) => workspaceGitBranch(registeredWorkspaceRoot(payload),payload || {}));
handle('beast:workspace-git-hunks', async (_event, payload) => workspaceGitHunks(registeredWorkspaceRoot(payload),payload || {}));
handle('beast:workspace-git-hunk-action', async (_event, payload) => workspaceGitHunkAction(registeredWorkspaceRoot(payload),payload || {}));
handle('beast:workspace-git-conflict', async (_event, payload) => workspaceGitConflict(registeredWorkspaceRoot(payload),payload || {}));
handle('beast:workspace-git-resolve', async (_event, payload) => workspaceGitResolve(registeredWorkspaceRoot(payload),payload || {}));
handle('beast:workspace-git-history', async (_event, payload) => workspaceGitHistory(registeredWorkspaceRoot(payload),payload || {}));
handle('beast:workspace-git-remotes', async (_event,payload) => workspaceGitRemotes(registeredWorkspaceRoot(payload)));
handle('beast:workspace-git-operation', async (_event, payload) => workspaceGitOperation(registeredWorkspaceRoot(payload),payload || {}));
handle('beast:workspace-tasks', async (_event,payload) => workspaceTasks(registeredWorkspaceRoot(payload)));
handle('beast:workspace-task-run', async (_event, payload) => runWorkspaceTask(registeredWorkspaceRoot(payload),payload));
handle('beast:workspace-settings', async (_event,payload) => workspaceSettings(registeredWorkspaceRoot(payload)));
handle('beast:workspace-settings-save', async (_event,payload) => writeWorkspaceSettings(registeredWorkspaceRoot(payload),payload?.settings));
handle('beast:workspace-tests', async (_event,payload) => workspaceTestsForTarget(registeredWorkspaceRoot(payload),payload||{}));
handle('beast:workspace-test-run', async (_event,payload) => runWorkspaceTest(registeredWorkspaceRoot(payload),payload));
handle('beast:workspace-task-list', async () => ({ok:true,sessions:workspaceTaskHost.list()}));
handle('beast:workspace-task-start', async (event,payload) => ({ok:true,session:workspaceTaskHost.start(registeredWorkspaceRoot(payload),typeof payload==='string'?payload:payload?.id,event.sender)}));
handle('beast:workspace-task-stop', async (_event,id) => workspaceTaskHost.stop(id));

handle('beast:file-operation', async (_event, rootPath, operation) => {
  return mutateWorkspaceFile(rootPath || workspaceStateHost.getActiveWorkspaceRoot() || repoRoot, operation || {});
});

handle('beast:open-workspace-window', async (_event, workspace) => {
  const target = path.resolve(workspace || workspaceStateHost.getActiveWorkspaceRoot() || repoRoot);
  if (!fs.existsSync(target)) return { ok: false, error: 'workspace path does not exist', workspace: target };
  await windowHost.createWindow({ initialWorkspace: target });
  return { ok: true, workspace: target };
});

handle('beast:release-readiness', async (_event, rootPath) => {
  return diagnosticsHost.localReleaseReadiness(rootPath || workspaceStateHost.getActiveWorkspaceRoot() || repoRoot);
});

handle('beast:tooling-snapshot', async (_event, rootPath, activeFile) => {
  return diagnosticsHost.localToolingSnapshot(rootPath || workspaceStateHost.getActiveWorkspaceRoot() || repoRoot, activeFile || '');
});

handle('beast:system-snapshot', async (_event, rootPath) => {
  return diagnosticsHost.localSystemSnapshot(rootPath || workspaceStateHost.getActiveWorkspaceRoot() || repoRoot);
});

handle('beast:ide-compatibility', async (_event, rootPath) => {
  return ideCompatibilityHost.discover(rootPath || workspaceStateHost.getActiveWorkspaceRoot() || repoRoot);
});

handle('beast:ide-capability-install', async (_event, options) => {
  return ideCompatibilityHost.install(options || {});
});

handle('beast:ide-protocol-start', async (event, options) => {
  return ideCompatibilityHost.start({ ...(options || {}), root:options?.root || workspaceStateHost.getActiveWorkspaceRoot() || repoRoot, target:options?.target || executionTargetHost.getActiveExecutionTarget() }, event.sender);
});

handle('beast:ide-protocol-request', async (_event, payload) => {
  return ideCompatibilityHost.request(payload || {});
});

handle('beast:ide-protocol-notify', async (_event, payload) => {
  return ideCompatibilityHost.notify(payload || {});
});

handle('beast:ide-protocol-stop', async (_event, sessionId) => {
  return ideCompatibilityHost.stop(String(sessionId || ''));
});

handle('beast:notebook-execute', async (_event, payload) => {
  return executeNotebookCell(workspaceStateHost.getActiveWorkspaceRoot() || repoRoot, payload || {});
});

handle('beast:notebook-kernel-start', async (event, rootPath) => {
  return notebookKernelHost.start(rootPath || workspaceStateHost.getActiveWorkspaceRoot() || repoRoot,event.sender);
});

handle('beast:notebook-kernel-request', async (_event, payload) => {
  return notebookKernelHost.request(payload || {});
});

handle('beast:notebook-kernel-stop', async () => notebookKernelHost.stop());

handle('beast:remote-probe', async (_event, payload) => {
  return probeRemoteWorkspace(payload || {});
});

handle('beast:remote-list-files', async (_event, payload) => {
  return listRemoteWorkspaceFiles(payload || {});
});
handle('beast:remote-search', async (_event, payload) => searchRemoteWorkspace(payload || {}));
handle('beast:remote-reconnect', async () => reconnectRemoteWorkspace());
handle('beast:remote-health', async (_event,payload) => remoteWorkspaceHealth(payload || {}));
handle('beast:remote-read-file', async (_event, payload) => readRemoteWorkspaceFile(payload || {}));
handle('beast:remote-write-file', async (_event, payload) => writeRemoteWorkspaceFile(payload || {}));
handle('beast:remote-terminal-run', async (_event, payload) => runRemoteTerminal(payload || {}));
handle('beast:dev-container-inspect', async (_event,payload) => inspectDevContainers(registeredWorkspaceRoot(payload)));
handle('beast:dev-container-start', async (_event,payload) => startDevContainer(registeredWorkspaceRoot(payload)));
handle('beast:dev-container-stop', async (_event,payload) => stopDevContainer(registeredWorkspaceRoot(payload),payload?.id));
handle('beast:dev-container-restart', async (_event,payload) => restartDevContainer(registeredWorkspaceRoot(payload),payload?.id));
handle('beast:dev-container-attach', async (_event,payload) => attachDevContainer(registeredWorkspaceRoot(payload),payload?.id));
handle('beast:dev-container-rebuild', async (_event,payload) => rebuildDevContainer(registeredWorkspaceRoot(payload)));
handle('beast:dev-container-logs', async (_event,payload) => devContainerLogs(registeredWorkspaceRoot(payload),payload?.id));
handle('beast:dev-container-terminal-run', async (_event,payload) => runDevContainerTerminal(registeredWorkspaceRoot(payload),payload || {}));
handle('beast:dev-container-open-port', async (_event,payload) => { const port=Number(payload?.port);if(!Number.isInteger(port)||port<1||port>65535)return {ok:false,error:'Container port must be between 1 and 65535.'};const url=`http://127.0.0.1:${port}`;await shell.openExternal(url);return {ok:true,url,port}; });
handle('beast:remote-terminal-list', async () => ({ok:true,terminals:remoteTerminalHost.list()}));
handle('beast:remote-terminal-start', async (event,payload) => ({ok:true,terminal:remoteTerminalHost.start(payload || {},event.sender)}));
handle('beast:remote-terminal-send', async (_event,payload) => remoteTerminalHost.send(payload?.id,payload?.input));
handle('beast:remote-terminal-stop', async (_event,id) => remoteTerminalHost.stop(id));
handle('beast:terminal-session-list', async () => ({ok:true,terminals:localTerminalHost.list()}));
handle('beast:terminal-session-start', async (event,payload) => ({ok:true,terminal:localTerminalHost.start(registeredWorkspaceRoot(payload),payload||{},event.sender)}));
handle('beast:terminal-session-send', async (_event,payload) => localTerminalHost.send(payload?.id,payload?.input));
handle('beast:terminal-session-stop', async (_event,id) => localTerminalHost.stop(id));

handle('beast:remote-forward-list', async () => ({ ok:true, forwards:sshForwardHost.list() }));

handle('beast:remote-forward-start', async (event, payload) => {
  return { ok:true, forward:sshForwardHost.start(payload || {},event.sender) };
});

handle('beast:remote-forward-stop', async (_event, id) => sshForwardHost.stop(id));

handle('beast:extension-host-discover', async (event, rootPath) => {
  return beastExtensionHost.discover(rootPath || workspaceStateHost.getActiveWorkspaceRoot() || repoRoot,event.sender,executionTargetHost.getActiveExecutionTarget());
});

handle('beast:extension-host-grant', async (event, payload) => {
  return beastExtensionHost.grantForTarget(workspaceStateHost.getActiveWorkspaceRoot() || repoRoot,payload?.id,payload?.capabilities,event.sender,payload?.target || executionTargetHost.getActiveExecutionTarget());
});
handle('beast:extension-host-enable', async (event,payload) => beastExtensionHost.setEnabled(workspaceStateHost.getActiveWorkspaceRoot()||repoRoot,payload?.id,Boolean(payload?.enabled),event.sender));
handle('beast:extension-host-install', async event => beastExtensionHost.installWorkspaceExtension(workspaceStateHost.getActiveWorkspaceRoot()||repoRoot,event.sender));
handle('beast:extension-host-deploy', async (event,payload) => beastExtensionHost.deployWorkspaceExtensions(workspaceStateHost.getActiveWorkspaceRoot()||repoRoot,event.sender,payload?.target || executionTargetHost.getActiveExecutionTarget()));
handle('beast:extension-host-uninstall', async (event,payload) => beastExtensionHost.uninstallWorkspaceExtension(workspaceStateHost.getActiveWorkspaceRoot()||repoRoot,payload?.id,event.sender));
handle('beast:extension-host-execute', async (event, payload) => beastExtensionHost.execute(workspaceStateHost.getActiveWorkspaceRoot() || repoRoot,payload?.id,payload?.command,event.sender,payload?.target || executionTargetHost.getActiveExecutionTarget()));

handle('beast:extension-host-stop', async () => beastExtensionHost.stop());
}

module.exports = { registerIpcHandlers };
