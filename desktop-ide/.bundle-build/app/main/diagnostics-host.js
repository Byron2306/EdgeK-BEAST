'use strict';

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

function createDesktopScriptRunner({ desktopRoot }) {
  return function runDesktopScript(scriptName) {
    const scriptPath = path.join(desktopRoot, 'scripts', scriptName);
    if (!fs.existsSync(scriptPath)) {
      return { ran: false, ok: false, error: `${scriptName} missing`, script: scriptPath };
    }
    try {
      const completed = spawnSync('node', [scriptPath], {
        cwd: desktopRoot,
        encoding: 'utf8',
        timeout: 30000,
      });
      return {
        ran: true,
        ok: completed.status === 0,
        returncode: completed.status,
        stdout: String(completed.stdout || '').slice(-4000),
        stderr: String(completed.stderr || '').slice(-4000),
        script: scriptPath,
      };
    } catch (error) {
      return { ran: true, ok: false, error: String(error.message || error), script: scriptPath };
    }
  };
}

module.exports = {
  createDesktopScriptRunner,
};
