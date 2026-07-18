'use strict';

// Runs only inside the BEAST extension VM. The supported vscode shim is
// mediated: it can navigate through known BEAST commands and show notices,
// but it never receives Node, process, network, or direct write authority.
exports.run = async (_api, command) => {
  if (command === 'beast.openMission') await vscode.commands.executeCommand('beast.openMission');
  else if (command === 'beast.openCompatibility') await vscode.commands.executeCommand('beast.openCompatibility');
  else vscode.window.showWarningMessage(`BEAST Companion does not handle ${command || 'this command'}.`);
};
