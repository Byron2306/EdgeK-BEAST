const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('beastDesktop', {
  status: () => ipcRenderer.invoke('beast:status'),
  listFiles: (workspace, limit) => ipcRenderer.invoke('beast:list-files', workspace, limit),
  readFile: (workspace, path, maxChars) => ipcRenderer.invoke('beast:read-file', workspace, path, maxChars),
  fileOperation: (workspace, operation) => ipcRenderer.invoke('beast:file-operation', workspace, operation),
  openWorkspaceWindow: workspace => ipcRenderer.invoke('beast:open-workspace-window', workspace),
  releaseReadiness: workspace => ipcRenderer.invoke('beast:release-readiness', workspace),
  toolingSnapshot: (workspace, activeFile) => ipcRenderer.invoke('beast:tooling-snapshot', workspace, activeFile),
  chooseWorkspace: () => ipcRenderer.invoke('beast:choose-workspace'),
  restartGateway: () => ipcRenderer.invoke('beast:restart-gateway'),
  openGateway: () => ipcRenderer.invoke('beast:open-gateway'),
  onGatewayLog: callback => ipcRenderer.on('beast:gateway-log', (_event, log) => callback(log)),
  onDesktopVersion: callback => ipcRenderer.on('beast:desktop-version', (_event, info) => callback(info)),
  onWorkspaceSelected: callback => ipcRenderer.on('beast:workspace-selected', (_event, workspace) => callback(workspace)),
  onRefresh: callback => ipcRenderer.on('beast:refresh', () => callback()),
});
