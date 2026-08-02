'use strict';

function rendererWebPreferences(preload) {
  return {
    preload,
    contextIsolation: true,
    nodeIntegration: false,
  };
}

function assertRendererWebPreferences(webPreferences = {}) {
  return Boolean(webPreferences.contextIsolation === true && webPreferences.nodeIntegration === false && webPreferences.preload);
}

module.exports = {
  assertRendererWebPreferences,
  rendererWebPreferences,
};
