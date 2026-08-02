'use strict';

function createIpcRegistry(ipcMain) {
  const channels = [];
  return {
    handle(channel, handler) {
      if (!channel || typeof channel !== 'string') throw new Error('IPC channel must be a non-empty string.');
      if (channels.includes(channel)) throw new Error(`Duplicate IPC channel registration: ${channel}`);
      channels.push(channel);
      return ipcMain.handle(channel, handler);
    },
    registeredChannels() {
      return [...channels];
    },
  };
}

module.exports = {
  createIpcRegistry,
};
