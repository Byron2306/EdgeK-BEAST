'use strict';

const { app, BrowserWindow, Menu, dialog, ipcMain, shell, screen } = require('electron');
const { IdeCompatibilityHost } = require('./ide-compatibility-host');
const { loadBuildIdentity } = require('./main/build-identity');
const { resolveRepoRoot, runtimeResourcePath: resolveRuntimeResourcePath, pythonToolRoot: resolvePythonToolRoot } = require('./main/runtime-paths');
const { createWindowStateStore } = require('./main/window-state');
const { NotebookKernelHost } = require('./main/notebook-kernel-host');
const { createWorkspacePathTools } = require('./main/workspace-paths');
const { createBoundedProcess } = require('./main/process-host');
const { createWorkspaceFileHost } = require('./main/workspace-file-host');
const { createEditorDocumentHost } = require('./main/editor-document-host');
const { createGitHost } = require('./main/git-host');
const { createTaskTestHost } = require('./main/task-test-host');
const { createNotebookExecutionHost } = require('./main/notebook-execution-host');
const { createExecutionTargetHost } = require('./main/execution-target-host');
const { createBeastExtensionHost } = require('./main/extension-host');
const { createWorkspaceStateHost } = require('./main/workspace-state-host');
const { createDesktopDiagnosticsHost } = require('./main/desktop-diagnostics-host');
const { createGatewayHost, serviceRegistryGateway } = require('./main/gateway-host');
const { createWindowHost } = require('./main/window-host');
const { registerIpcHandlers } = require('./main/ipc-registry');
const { registerApplicationLifecycle } = require('./main/application-lifecycle');
const { createWorkspaceTrustHost } = require('./main/workspace-trust-host');

if (process.platform === 'linux' && process.env.BEAST_ELECTRON_SANDBOX !== '1') {
  app.commandLine.appendSwitch('no-sandbox');
  app.commandLine.appendSwitch('disable-gpu-sandbox');
  app.commandLine.appendSwitch('disable-dev-shm-usage');
  app.commandLine.appendSwitch('disable-gpu-compositing');
  app.commandLine.appendSwitch('disable-zero-copy');
  app.commandLine.appendSwitch('disable-accelerated-2d-canvas');
  app.commandLine.appendSwitch('disable-accelerated-video-decode');
  app.commandLine.appendSwitch('disable-accelerated-video-encode');
  app.commandLine.appendSwitch('disable-frame-rate-limit');
  app.commandLine.appendSwitch('in-process-gpu');
  if (process.env.BEAST_ELECTRON_DISABLE_GPU !== '0') {
    app.disableHardwareAcceleration();
    app.commandLine.appendSwitch('disable-gpu');
    app.commandLine.appendSwitch('use-gl', 'swiftshader');
    app.commandLine.appendSwitch('enable-unsafe-swiftshader');
    app.commandLine.appendSwitch('disable-features', 'UseSkiaRenderer,VizDisplayCompositor,CanvasOopRasterization,Accelerated2dCanvas,VaapiVideoDecoder,RawDraw');
  }
}

const BUILD_IDENTITY = loadBuildIdentity(__dirname);
const DESKTOP_IDE_VERSION = BUILD_IDENTITY.desktop_runtime_build;
const repoRoot = resolveRepoRoot({ baseDirectory: __dirname });
const runtimeResourcePath = (...parts) => resolveRuntimeResourcePath(__dirname, process.resourcesPath, ...parts);
const pythonToolRoot = () => resolvePythonToolRoot(__dirname, process.resourcesPath);
const ideCompatibilityHost = new IdeCompatibilityHost(repoRoot);
const notebookKernelHost = new NotebookKernelHost({ repoRoot, runtimeResourcePath, pythonToolRoot });

const { safeWorkspacePath, taskCwd } = createWorkspacePathTools({ repoRoot });
const boundedProcess = createBoundedProcess({ repoRoot });
const workspaceFileHost = createWorkspaceFileHost({ repoRoot, safeWorkspacePath });
const editorDocumentHost = createEditorDocumentHost({ app, repoRoot, safeWorkspacePath, getActiveWorkspaceRoot: () => workspaceStateHost?.getActiveWorkspaceRoot?.() || repoRoot });
const gitHost = createGitHost({ repoRoot, boundedProcess, safeWorkspacePath });

let gatewayHost = null;
let windowHost = null;
let executionTargetHost = null;

const workspaceStateHost = createWorkspaceStateHost({
  app,
  repoRoot,
  workspaceFileCandidates: workspaceFileHost.workspaceFileCandidates,
  appendLog: line => gatewayHost?.appendLog(line),
});

const workspaceTrustHost = createWorkspaceTrustHost({
  app,
  getActiveWorkspaceRoot: workspaceStateHost.getActiveWorkspaceRoot,
});

const taskTestHost = createTaskTestHost({
  repoRoot,
  workspaceFileCandidates: workspaceFileHost.workspaceFileCandidates,
  safeWorkspacePath,
  taskCwd,
  getTargetHost: () => executionTargetHost,
});

executionTargetHost = createExecutionTargetHost({
  repoRoot,
  boundedProcess,
  gitReceipt: gitHost.gitReceipt,
  readWorkspaceFile: workspaceFileHost.readWorkspaceFile,
  safeWorkspacePath,
  taskCwd,
  workspaceFileCandidates: workspaceFileHost.workspaceFileCandidates,
  getActiveWorkspaceRoot: workspaceStateHost.getActiveWorkspaceRoot,
});

const notebookExecutionHost = createNotebookExecutionHost({
  repoRoot,
  boundedProcess,
  getActiveWorkspaceRoot: workspaceStateHost.getActiveWorkspaceRoot,
});

const diagnosticsHost = createDesktopDiagnosticsHost({
  repoRoot,
  desktopRoot: __dirname,
  buildIdentity: BUILD_IDENTITY,
  desktopVersion: DESKTOP_IDE_VERSION,
  safeWorkspacePath,
  getActiveWorkspaceRoot: workspaceStateHost.getActiveWorkspaceRoot,
  getGatewaySnapshot: () => gatewayHost?.getSnapshot() || { url:serviceRegistryGateway(repoRoot), localMode:false, processPid:null },
});

const gatewayOverrideAllowed = process.env.BEAST_ALLOW_GATEWAY_OVERRIDE === '1';
const configuredGatewayUrl = serviceRegistryGateway(repoRoot);
const initialGatewayUrl = gatewayOverrideAllowed && process.env.BEAST_DESKTOP_GATEWAY
  ? process.env.BEAST_DESKTOP_GATEWAY
  : configuredGatewayUrl;

gatewayHost = createGatewayHost({
  repoRoot,
  initialGatewayUrl,
  resolveBeastPython: diagnosticsHost.resolveBeastPython,
  getActiveWorkspaceRoot: workspaceStateHost.getActiveWorkspaceRoot,
  getAppWindows: () => windowHost?.getAppWindows() || [],
});

windowHost = createWindowHost({
  BrowserWindow,
  Menu,
  dialog,
  shell,
  desktopRoot: __dirname,
  buildIdentity: BUILD_IDENTITY,
  desktopVersion: DESKTOP_IDE_VERSION,
  workspaceStateHost,
  gatewayHost,
  beastRepoRoot: repoRoot,
});

const beastExtensionHost = createBeastExtensionHost({
  repoRoot,
  runtimeResourcePath,
  boundedProcess,
  getMainWindow: windowHost.getMainWindow,
  executionTargetHost,
  BrowserWindow,
  dialog,
});

registerIpcHandlers({
  ipcMain,
  BrowserWindow,
  dialog,
  shell,
  repoRoot,
  desktopRoot: __dirname,
  desktopVersion: DESKTOP_IDE_VERSION,
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
});

workspaceTrustHost.setBroadcaster(snapshot => {
  for (const windowRef of windowHost.getAppWindows()) {
    if (!windowRef.isDestroyed()) windowRef.webContents.send('beast:workspace-trust-changed', snapshot);
  }
});

registerApplicationLifecycle({
  app,
  BrowserWindow,
  screen,
  createWindowStateStore,
  windowHost,
  workspaceStateHost,
  gatewayHost,
  ideCompatibilityHost,
  notebookKernelHost,
  executionTargetHost,
  taskTestHost,
  beastExtensionHost,
});
