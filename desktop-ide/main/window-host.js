'use strict';

const path = require('path');
const { DEFAULT_WINDOW_BOUNDS } = require('./window-state');

function createWindowHost({ BrowserWindow, Menu, dialog, shell, desktopRoot, buildIdentity, desktopVersion, workspaceStateHost, gatewayHost, beastRepoRoot }) {
  let windowStateStore = null;
  let mainWindow = null;
  const appWindows = new Set();
  const appendLog = gatewayHost.appendLog;
  let deferredGatewayTimer = 0;

  function setWindowStateStore(store) { windowStateStore = store; }
  function readWindowState() { return windowStateStore?.read() || { ...DEFAULT_WINDOW_BOUNDS, maximized:false }; }
  function persistWindowState(windowRef) { return windowStateStore?.persist(windowRef); }
  function scheduleWindowStatePersist(windowRef) { return windowStateStore?.schedule(windowRef); }
  function setOwnedZoom(windowRef, requestedLevel) {
    if (!windowRef || windowRef.isDestroyed()) return;
    const level = Math.max(-3, Math.min(5, Math.round(Number(requestedLevel) || 0)));
    windowRef.__beastZoomLevel = level;
    windowRef.webContents.setZoomLevel(level);
    scheduleWindowStatePersist(windowRef);
  }

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
          { label: 'Refresh IDE Snapshot', click: () => (BrowserWindow.getFocusedWindow() || mainWindow)?.webContents.send('beast:refresh') },
        ],
      },
      {
        label: 'View',
        submenu: [
          { label:'Zoom In', accelerator:'CmdOrCtrl+Plus', click:()=>{const target=BrowserWindow.getFocusedWindow()||mainWindow;setOwnedZoom(target,(target?.__beastZoomLevel ?? target?.webContents.getZoomLevel() ?? 0)+1);} },
          { label:'Zoom Out', accelerator:'CmdOrCtrl+-', click:()=>{const target=BrowserWindow.getFocusedWindow()||mainWindow;setOwnedZoom(target,(target?.__beastZoomLevel ?? target?.webContents.getZoomLevel() ?? 0)-1);} },
          { label:'Reset Zoom', accelerator:'CmdOrCtrl+0', click:()=>setOwnedZoom(BrowserWindow.getFocusedWindow()||mainWindow,0) },
          { type: 'separator' },
          { label:'Reload', accelerator:'CmdOrCtrl+R', click:()=>{const target=BrowserWindow.getFocusedWindow()||mainWindow;if(target){target.__beastZoomLevel=target.webContents.getZoomLevel();persistWindowState(target);target.reload();}} },
          { label:'Hard Reload', accelerator:'CmdOrCtrl+Shift+R', click:async()=>{const target=BrowserWindow.getFocusedWindow()||mainWindow;if(target){target.__beastZoomLevel=target.webContents.getZoomLevel();persistWindowState(target);await target.webContents.session.clearCache();target.webContents.reloadIgnoringCache();}} },
          { role: 'toggleDevTools' },
          { role: 'togglefullscreen' },
        ],
      },
    ];
    Menu.setApplicationMenu(Menu.buildFromTemplate(template));
  }

  function scheduleDeferredGatewayEnsure() {
    clearTimeout(deferredGatewayTimer);
    deferredGatewayTimer = setTimeout(() => {
      deferredGatewayTimer = 0;
      gatewayHost.ensureGateway().catch(error => {
        appendLog(`deferred gateway attach failed: ${String(error.message || error)}`);
      });
    }, 1200);
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
    windowRef.__beastZoomLevel = Number.isFinite(Number(savedWindowState.zoomLevel))
      ? Math.max(-3, Math.min(5, Math.round(Number(savedWindowState.zoomLevel))))
      : 0;
    windowRef.webContents.setZoomLevel(windowRef.__beastZoomLevel);
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
    windowRef.webContents.on('console-message', (_event, level, message, line, sourceId) => {
      appendLog(`renderer console[${level}] ${sourceId || 'renderer'}:${line || 0} ${message}`);
    });
    windowRef.webContents.on('did-fail-load', (_event, errorCode, errorDescription, validatedURL) => {
      appendLog(`renderer load failed ${errorCode}: ${errorDescription} · ${validatedURL || 'unknown-url'}`);
    });
    windowRef.webContents.on('render-process-gone', (_event, details) => {
      appendLog(`renderer process gone: ${details?.reason || 'unknown'} · exit ${details?.exitCode ?? 'n/a'}`);
    });
    // Capture native Ctrl+/- and View-menu zoom, not only renderer IPC controls.
    windowRef.webContents.on('zoom-changed', () => {
      setImmediate(() => {
        if (windowRef.isDestroyed()) return;
        windowRef.__beastZoomLevel = Math.max(-3, Math.min(5, Math.round(windowRef.webContents.getZoomLevel())));
        // Native menu and Ctrl +/- changes do not pass through renderer IPC.
        // Mirror them into the renderer preference so the guardian cannot
        // restore the previous level a few seconds later.
        windowRef.webContents.executeJavaScript(`localStorage.setItem('beast.desktop.zoom-level.v2', '${windowRef.__beastZoomLevel}')`).catch(() => {});
        scheduleWindowStatePersist(windowRef);
      });
    });
    windowRef.webContents.on('before-input-event', (event, input) => {
      if (!(input.control || input.meta) || input.type !== 'keyDown') return;
      const key = String(input.key || '');
      if (!['+','=','-','0'].includes(key)) return;
      event.preventDefault();
      const current = Number.isFinite(windowRef.__beastZoomLevel) ? windowRef.__beastZoomLevel : windowRef.webContents.getZoomLevel();
      setOwnedZoom(windowRef, key === '0' ? 0 : current + (key === '-' ? -1 : 1));
    });
    // Chromium keys zoom preferences by full file URL, including SPA fragments.
    // Reapply the window-owned level after hash navigation so every IDE route
    // renders at the same scale instead of inheriting historical per-page zoom.
    windowRef.webContents.on('did-navigate-in-page', () => {
      const level = Number(windowRef.__beastZoomLevel);
      if (!Number.isFinite(level)) return;
      setImmediate(() => {
        if (!windowRef.isDestroyed()) windowRef.webContents.setZoomLevel(level);
      });
    });
    windowRef.on('unresponsive', () => appendLog('renderer window became unresponsive'));
    windowRef.webContents.on('did-finish-load', () => {
      setOwnedZoom(windowRef, windowRef.__beastZoomLevel);
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
    scheduleDeferredGatewayEnsure();
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
