'use strict';
exports.run = async (_api, command) => {
  const routes = { 'beast.openCrystallization': 'crystallization', 'beast.openEvidence': 'evidence' };
  if (routes[command]) api.emit('navigate', { route: routes[command] });
  else vscode.window.showWarningMessage(`BEAST Crystal Lab does not handle ${command || 'this command'}.`);
};
