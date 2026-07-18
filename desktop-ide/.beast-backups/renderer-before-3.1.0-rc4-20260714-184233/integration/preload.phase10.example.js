// Phase 10 secure preload contract example. Merge channels into your existing preload; do not replace working handlers blindly.
const { contextBridge, ipcRenderer } = require('electron');
const invoke = (channel, ...args) => ipcRenderer.invoke(channel, ...args);
const subscribe = (channel, callback) => {
  const handler = (_event, payload) => callback(payload);
  ipcRenderer.on(channel, handler);
  return () => ipcRenderer.removeListener(channel, handler);
};
contextBridge.exposeInMainWorld('beastDesktop', {
  status: () => invoke('beast:status'),
  chooseWorkspace: () => invoke('beast:choose-workspace'),
  listFiles: (root, limit) => invoke('beast:list-files', { root, limit }),
  readFile: (root, path, maxChars) => invoke('beast:read-file', { root, path, maxChars }),
  fileOperation: (root, operation, options) => invoke('beast:file-operation', { root, operation, options }),
  toolingSnapshot: (root, activeFile) => invoke('beast:tooling-snapshot', { root, activeFile }),
  systemSnapshot: root => invoke('beast:system-snapshot', { root }),
  releaseReadiness: root => invoke('beast:release-readiness', { root }),
  restartGateway: () => invoke('beast:restart-gateway'),
  openWorkspaceWindow: path => invoke('beast:open-workspace-window', { path }),
  openGateway: () => invoke('beast:open-gateway'),
  gatewayRequest: request => invoke('beast:gateway-request', request),
  onWorkspaceSelected: callback => subscribe('beast:workspace-selected', callback),
  onRefresh: callback => subscribe('beast:refresh', callback),
  onGatewayLog: callback => subscribe('beast:gateway-log', callback),
  onDesktopVersion: callback => subscribe('beast:desktop-version', callback)
});
