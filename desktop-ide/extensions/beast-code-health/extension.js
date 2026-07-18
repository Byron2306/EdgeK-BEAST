'use strict';
exports.run = async (_api, command) => {
  const routes = { 'beast.openTesting': 'testing', 'beast.openSourcePlan': 'source', 'beast.openReview': 'review' };
  if (routes[command]) api.emit('navigate', { route: routes[command] });
  else vscode.window.showWarningMessage(`BEAST Code Health does not handle ${command || 'this command'}.`);
};
