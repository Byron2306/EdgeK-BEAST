'use strict';

function registerApplicationLifecycle({ app, BrowserWindow, onReady, onWindowAllClosed, createWindow }) {
  app.whenReady().then(onReady);
  app.on('window-all-closed', onWindowAllClosed);
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
}

module.exports = {
  registerApplicationLifecycle,
};
