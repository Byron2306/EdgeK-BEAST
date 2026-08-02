'use strict';

const path = require('path');
const { DEFAULT_WINDOW_BOUNDS } = require('./window-state');

function createWindowHost({ BrowserWindow, Menu, dialog, shell, desktopRoot, buildIdentity, desktopVersion, workspaceStateHost, gatewayHost, beastRepoRoot }) {
  let windowStateStore = null;
  let mainWindow = null;
  const appWindows = new Set();
  const appendLog = gatewayHost.appendLog;

  function setWindowStateStore(store) { windowStateStore = store; }
  function readWindowState() { return windowStateStore?.read() || { ...DEFAULT_WINDOW_BOUNDS, maximized:false }; }
  function persistWindowState(windowRef) { return windowStateStore?.persist(windowRef); }
  function scheduleWindowStatePersist(windowRef) { return windowStateStore?.schedule(windowRef); }

  function createMenu() {
    const template = [
      {
        label: 'BEAST',
        submenu: [
          { label: 'Start or Attach Gateway', click: () => gatewayHost.ensureGateway() },
          { label: 'Open Gateway in Browser', click: () => shell.openExternal(gatewayHost.getGatewayUrl()) },
          { type: 'separator' },
          { role: 'quit' },
        ],
      },
      {
        label: 'Workspace',
        submenu: [
          {
            label: 'Choose Workspace',
            accelerator: 'CmdOrCtrl+O',
            click: async () => {
              const targetWindow = BrowserWindow.getFocusedWindow() || mainWindow;
              const result = await dialog.showOpenDialog(targetWindow, { properties: ['openDirectory'] });
              if (!result.canceled && result.filePaths[0]) {
                const folders = workspaceStateHost.setWorkspaceRoots([result.filePaths[0]], result.filePaths[0]);
                targetWindow.webContents.send('beast:workspace-selected', { root:workspaceStateHost.getActiveWorkspaceRoot(), folders });
              }
            },
          },
          { label: 'Refresh IDE Snapshot', accelerator: 'CmdOrCtrl+R', click: () => (BrowserWindow.getFocusedWindow() || mainWindow)?.webContents.send('beast:refresh') },
        ],
      },
      {
        label: 'View',
        submenu: [
          { role: 'zoomIn' },
          { role: 'zoomOut' },
          { role: 'resetZoom' },
          { type: 'separator' },
          { role: 'reload' },
          { role: 'toggleDevTools' },
          { role: 'togglefullscreen' },
        ],
      },
    ];
    Menu.setApplicationMenu(Menu.buildFromTemplate(template));
  }

  async function createWindow(options = {}) {
    const initialWorkspace = options.initialWorkspace ? path.resolve(options.initialWorkspace) : '';
    if (initialWorkspace) workspaceStateHost.setWorkspaceRoots([initialWorkspace], initialWorkspace);
    const savedWindowState = readWindowState();
    const windowRef = new BrowserWindow({
      ...DEFAULT_WINDOW_BOUNDS,
      width: savedWindowState.width,
      height: savedWindowState.height,
      ...(Number.isFinite(savedWindowState.x) ? { x: savedWindowState.x } : {}),
      ...(Number.isFinite(savedWindowState.y) ? { y: savedWindowState.y } : {}),
      title: 'BEAST Desktop IDE',
      backgroundColor: '#050607',
      webPreferences: {
        preload: path.join(desktopRoot, 'preload.js'),
        contextIsolation: true,
        nodeIntegration: false,
      },
    });
    mainWindow = windowRef;
    appWindows.add(windowRef);
    windowRef.on('focus', () => { mainWindow = windowRef; });
    windowRef.on('resize', () => scheduleWindowStatePersist(windowRef));
    windowRef.on('move', () => scheduleWindowStatePersist(windowRef));
    windowRef.on('maximize', () => scheduleWindowStatePersist(windowRef));
    windowRef.on('unmaximize', () => scheduleWindowStatePersist(windowRef));
    windowRef.once('ready-to-show', () => { if (savedWindowState.maximized) windowRef.maximize(); });
    windowRef.on('close', () => persistWindowState(windowRef));
    windowRef.on('closed', () => {
      appWindows.delete(windowRef);
      if (mainWindow === windowRef) mainWindow = [...appWindows].find(item => !item.isDestroyed()) || null;
    });
    try { await windowRef.webContents.session.clearCache(); }
    catch (error) { appendLog(`renderer cache clear failed: ${error.message || error}`); }
    windowRef.webContents.once('did-finish-load', () => {
      const rendererPath = path.join(desktopRoot, 'renderer', 'index.html');
      appendLog(`renderer loaded: ${rendererPath} · ${desktopVersion}`);
      windowRef.webContents.send('beast:desktop-version', {
        version: desktopVersion,
        buildIdentity,
        rendererPath,
        repoRoot: workspaceStateHost.getActiveWorkspaceRoot(),
        beastRepoRoot,
        windowId: windowRef.id,
      });
      if (initialWorkspace) {
        windowRef.webContents.send('beast:workspace-selected', { root:workspaceStateHost.getActiveWorkspaceRoot(), folders:workspaceStateHost.workspaceFolders() });
      }
    });
    await windowRef.loadFile(path.join(desktopRoot, 'renderer', 'index.html'));
    createMenu();
    gatewayHost.ensureGateway();
    return windowRef;
  }

  return {
    createWindow,
    createMenu,
    setWindowStateStore,
    getWindowStateStore: () => windowStateStore,
    getMainWindow: () => mainWindow,
    getAppWindows: () => appWindows,
    getWindowCount: () => appWindows.size,
    disposeWindowState: () => windowStateStore?.dispose(),
  };
}

module.exports = { createWindowHost };
