'use strict';

function createBrowserWindowOptions({ bounds = {}, preloadPath }) {
  const { rendererWebPreferences } = require('./security-policy');
  return {
    ...bounds,
    title: 'BEAST Desktop IDE',
    backgroundColor: '#050607',
    webPreferences: rendererWebPreferences(preloadPath),
  };
}

module.exports = {
  createBrowserWindowOptions,
};
