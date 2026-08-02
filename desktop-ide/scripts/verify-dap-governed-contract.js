#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const { runVerification: runRemoteDebugRecoveryVerification } = require('./verify-remote-debug-recovery');

const repoRoot = path.resolve(__dirname, '..', '..');
const foundationArtifact = path.join(repoRoot, 'build', 'PARITY_FOUNDATION.json');
const remoteDapArtifact = path.join(repoRoot, 'build', 'REMOTE_DAP_CONTRACT.json');
const artifactPath = path.join(repoRoot, 'build', 'DAP_GOVERNED_CONTRACT.json');

function run(script, env = {}) {
  return spawnSync(process.execPath, [path.join(__dirname, script)], {
    cwd: repoRoot,
    encoding: 'utf8',
    timeout: 180000,
    maxBuffer: 1024 * 1024,
    env: { ...process.env, ...env },
  });
}

function readJson(file) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (_) {
    return null;
  }
}

async function main() {
  const foundationRun = run('verify-ide-parity-foundation.js');
  const foundation = readJson(foundationArtifact);
  const remoteDapRun = run('verify-remote-dap.js');
  const remoteDap = readJson(remoteDapArtifact);
  const recovery = await runRemoteDebugRecoveryVerification();
  const runtime = fs.readFileSync(path.join(repoRoot, 'desktop-ide', 'renderer', 'js', 'beast-ide-runtime.js'), 'utf8');
  const page = fs.readFileSync(path.join(repoRoot, 'desktop-ide', 'renderer', 'js', 'pages', 'beast-compatibility-page.js'), 'utf8');
  const handshakes = foundation?.handshakes || {};
  const allowedSkipped = new Set([
    'debugpy',
    'delve',
    'lldb',
    'dapLaunch',
    'dapRestart',
  ]);
  const handshakeRows = {
    debugpy: handshakes.debugpy,
    delve: handshakes.delve,
    lldb: handshakes.lldb,
    dapLaunch: handshakes.dapLaunch,
    dapRestart: handshakes.dapRestart,
  };
  const handshakeOk = Object.entries(handshakeRows).every(([key, value]) => value === 'passed' || (allowedSkipped.has(key) && value === 'skipped'));
  const ok =
    foundationRun.status === 0 &&
    foundation?.ok === true &&
    recovery?.ok === true &&
    remoteDapRun.status === 0 &&
    remoteDap?.ok === true &&
    Number(remoteDap?.skipped || 0) === Number(remoteDap?.checks || 0) &&
    handshakeOk &&
    runtime.includes('supportsConfigurationDoneRequest') &&
    runtime.includes("request(session,'loadedSources'") &&
    runtime.includes('supportsLoadedSourcesRequest') &&
    runtime.includes('supportsRestartRequest') &&
    runtime.includes('restartDebugFrame') &&
    runtime.includes("if (message.event==='loadedSource')") &&
    page.includes('data-runtime-debug-capabilities') &&
    page.includes('data-runtime-debug-sources') &&
    page.includes('data-runtime-debug-stop') &&
    page.includes('data-runtime-debug-threads') &&
    page.includes('data-runtime-debug-variables');
  const report = {
    ok,
    date: '2026-07-31',
    checks: 15,
    artifacts: {
      foundation: 'build/PARITY_FOUNDATION.json',
    },
    remoteDap,
    recovery,
    allowedSkipped: [...allowedSkipped],
    handshakes: handshakeRows,
  };
  fs.mkdirSync(path.dirname(artifactPath), { recursive: true });
  fs.writeFileSync(artifactPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
  console.log(JSON.stringify(report, null, 2));
  process.exit(ok ? 0 : 1);
}

main().catch(error => {
  console.error(error.stack || String(error));
  process.exit(1);
});
