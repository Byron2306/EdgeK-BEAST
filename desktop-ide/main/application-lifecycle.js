'use strict';

function registerApplicationLifecycle({
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
}) {
  app.whenReady().then(() => {
    const windowStateStore = createWindowStateStore({ app, screen, appendLog:gatewayHost.appendLog });
    windowHost.setWindowStateStore(windowStateStore);
    workspaceStateHost.restoreWorkspaceFolders();
    return windowHost.createWindow();
  });

  app.on('window-all-closed', () => {
    gatewayHost.shutdown();
    ideCompatibilityHost.stopAll();
    notebookKernelHost.stop();
    windowHost.disposeWindowState();
    executionTargetHost.sshForwardHost.stopAll();
    executionTargetHost.remoteTerminalHost.stopAll();
    taskTestHost.workspaceTaskHost.stopAll();
    executionTargetHost.localTerminalHost.stopAll();
    beastExtensionHost.stop();
    if (process.platform !== 'darwin') app.quit();
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) windowHost.createWindow();
  });
}

module.exports = { registerApplicationLifecycle };
