'use strict';

function installApplicationMenu({
  BrowserWindow,
  Menu,
  dialog,
  shell,
  ensureGateway,
  getGatewayUrl,
  getMainWindow,
  chooseWorkspace,
}) {
  const template = [
    {
      label: 'BEAST',
      submenu: [
        { label: 'Start or Attach Gateway', click: () => ensureGateway() },
        { label: 'Open Gateway in Browser', click: () => shell.openExternal(getGatewayUrl()) },
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
            const targetWindow = BrowserWindow.getFocusedWindow() || getMainWindow();
            const result = await dialog.showOpenDialog(targetWindow, { properties: ['openDirectory'] });
            if (!result.canceled && result.filePaths[0]) {
              const folders = chooseWorkspace(result.filePaths[0]);
              targetWindow.webContents.send('beast:workspace-selected', folders);
            }
          },
        },
        {
          label: 'Refresh IDE Snapshot',
          accelerator: 'CmdOrCtrl+R',
          click: () => (BrowserWindow.getFocusedWindow() || getMainWindow())?.webContents.send('beast:refresh'),
        },
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

module.exports = {
  installApplicationMenu,
};
