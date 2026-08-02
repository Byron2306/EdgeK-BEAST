#!/usr/bin/env node
'use strict';

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const electronBinary = require('electron');
const desktopRoot = path.resolve(__dirname, '..');
const cliArgs = process.argv.slice(2);

function isTruthy(value) {
  return ['1', 'true', 'yes', 'on'].includes(String(value || '').toLowerCase());
}

function shouldDisableSandbox() {
  if (process.env.BEAST_ELECTRON_SANDBOX === '1') return false;
  if (process.env.BEAST_ELECTRON_NO_SANDBOX === '0') return false;
  if (process.platform !== 'linux') return isTruthy(process.env.BEAST_ELECTRON_NO_SANDBOX);
  return true;
}

function fsMarker(filePath) {
  try {
    return require('fs').existsSync(filePath);
  } catch (_) {
    return false;
  }
}

const env = { ...process.env };
delete env.ELECTRON_RUN_AS_NODE;
if (shouldDisableSandbox()) env.ELECTRON_DISABLE_SANDBOX = '1';

const flags = [];
if (shouldDisableSandbox()) {
  flags.push('--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu-sandbox', '--disable-dev-shm-usage');
}

const requestedEntry = cliArgs[0] ? path.resolve(desktopRoot, cliArgs[0]) : '';
const entryScript = requestedEntry && requestedEntry.endsWith('.js') && fs.existsSync(requestedEntry)
  ? requestedEntry
  : desktopRoot;
const passthroughArgs = entryScript === requestedEntry ? cliArgs.slice(1) : cliArgs;

const child = spawn(electronBinary, [...flags, entryScript, ...passthroughArgs], {
  cwd: desktopRoot,
  env,
  stdio: 'inherit',
  windowsHide: false,
});

child.on('exit', (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});

child.on('error', error => {
  console.error(`[beast-desktop-ide] Failed to launch Electron: ${error.message}`);
  process.exit(1);
});
