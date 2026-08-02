'use strict';

const path = require('path');

function createDesktopWindowHost({
  BrowserWindow,
  desktopRoot,
  createBrowserWindowOptions,
  defaultWindowBounds,
  readWindowState,
  persistWindowState,
  scheduleWindowStatePersist,
  setWorkspaceRoots,
  workspaceFolders,
  appendLog,
  buildIdentity,
  desktopVersion,
  repoRoot,
  getActiveWorkspaceRoot,
  setMainWindow,
  getMainWindow,
  appWindows,
  installMenu,
  ensureGateway,
}) {
  async function createWindow(options = {}) {
    const initialWorkspace = options.initialWorkspace ? path.resolve(options.initialWorkspace) : '';
    if (initialWorkspace) setWorkspaceRoots([initialWorkspace], initialWorkspace);
    const savedWindowState = readWindowState();
    const rendererPath = path.join(desktopRoot, 'renderer', 'index.html');
    const windowRef = new BrowserWindow(createBrowserWindowOptions({
      bounds: {
        ...defaultWindowBounds,
        width: savedWindowState.width,
        height: savedWindowState.height,
        ...(Number.isFinite(savedWindowState.x) ? { x: savedWindowState.x } : {}),
        ...(Number.isFinite(savedWindowState.y) ? { y: savedWindowState.y } : {}),
      },
      preloadPath: path.join(desktopRoot, 'preload.js'),
    }));
    setMainWindow(windowRef);
    appWindows.add(windowRef);
    windowRef.on('focus', () => setMainWindow(windowRef));
    windowRef.on('resize', () => scheduleWindowStatePersist(windowRef));
    windowRef.on('move', () => scheduleWindowStatePersist(windowRef));
    windowRef.on('maximize', () => scheduleWindowStatePersist(windowRef));
    windowRef.on('unmaximize', () => scheduleWindowStatePersist(windowRef));
    windowRef.once('ready-to-show', () => { if (savedWindowState.maximized) windowRef.maximize(); });
    windowRef.on('close', () => persistWindowState(windowRef));
    windowRef.on('closed', () => {
      appWindows.delete(windowRef);
      if (getMainWindow() === windowRef) setMainWindow([...appWindows].find(item => !item.isDestroyed()) || null);
    });
    try {
      await windowRef.webContents.session.clearCache();
    } catch (error) {
      appendLog(`renderer cache clear failed: ${error.message || error}`);
    }
    windowRef.webContents.once('did-finish-load', () => {
      appendLog(`renderer loaded: ${rendererPath} · ${desktopVersion}`);
      windowRef.webContents.send('beast:desktop-version', {
        version: desktopVersion,
        buildIdentity,
        rendererPath,
        repoRoot: getActiveWorkspaceRoot() || repoRoot,
        beastRepoRoot: repoRoot,
        windowId: windowRef.id,
      });
      if (initialWorkspace) {
        windowRef.webContents.send('beast:workspace-selected', { root:getActiveWorkspaceRoot(), folders:workspaceFolders() });
      }
    });
    await windowRef.loadFile(rendererPath);
    installMenu();
    ensureGateway();
  }

  return { createWindow };
}

module.exports = {
  createDesktopWindowHost,
};
