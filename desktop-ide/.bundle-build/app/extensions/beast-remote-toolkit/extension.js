'use strict';
exports.run = async (_api, command) => {
  if (command === 'beast.openCompatibility') api.emit('navigate', { route: 'compatibility' });
  else if (command === 'beast.openTerminal') api.emit('navigate', { route: 'terminal' });
  else vscode.window.showWarningMessage(`BEAST Remote Toolkit does not handle ${command || 'this command'}.`);
};
