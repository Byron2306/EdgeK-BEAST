const fs = require('fs');
const path = require('path');
const { app, BrowserWindow } = require('electron');
const root = '/home/byron/GitHub/EdgeK-BEAST';
const output = path.join(root, '.beast/validation-2026-10-10/electron-live.json');
const consoleErrors = [];
const deadline = setTimeout(() => { fs.writeFileSync(output, JSON.stringify({ passed:false, error:'Desktop startup timed out', consoleErrors },null,2)); app.exit(1); },90000);
let checked = false;
app.on('browser-window-created', (_event, window) => {
  window.webContents.on('console-message', (_event, level, message) => { if (level >= 3) consoleErrors.push(message); });
  window.webContents.on('did-finish-load', async () => {
    if (checked) return;
    checked = true;
    await new Promise(resolve => setTimeout(resolve,10000));
    try {
      const state = await window.webContents.executeJavaScript(`({ title:document.title, readyState:document.readyState, page:document.body.dataset.beastPage, outlets:document.querySelectorAll('#beastPageOutlet').length, rendererLoaded:Boolean(window.BeastRouter), bridgeLoaded:Boolean(window.beastDesktop || window.beast || window.BeastDesktop), contentLength:document.body.innerText.length })`);
      const passed = state.readyState === 'complete' && state.outlets === 1 && state.rendererLoaded && state.contentLength > 200 && consoleErrors.length === 0;
      fs.writeFileSync(output,JSON.stringify({passed,source:'actual desktop main.js',state,consoleErrors},null,2));
      console.log(JSON.stringify({passed,state,consoleErrors}));
      clearTimeout(deadline);
      app.removeAllListeners('window-all-closed');
      for (const windowRef of BrowserWindow.getAllWindows()) if (!windowRef.isDestroyed()) windowRef.destroy();
      app.exit(passed ? 0 : 1);
    } catch (error) {
      fs.writeFileSync(output,JSON.stringify({passed:false,error:String(error),consoleErrors},null,2));
      clearTimeout(deadline);
      app.exit(1);
    }
  });
});
require(path.join(root,'desktop-ide/main.js'));
