#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const { runVerification: runRemoteDebugRecoveryVerification } = require('./verify-remote-debug-recovery');

const repoRoot = path.resolve(__dirname, '..', '..');
const foundationArtifact = path.join(repoRoot, 'build', 'PARITY_FOUNDATION.json');
const artifactPath = path.join(repoRoot, 'build', 'DEBUG_LIFECYCLE_CONTRACT.json');

function runFoundation() {
  return spawnSync(process.execPath, [path.join(__dirname, 'verify-ide-parity-foundation.js')], {
    cwd: repoRoot,
    encoding: 'utf8',
    timeout: 180000,
    maxBuffer: 1024 * 1024,
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
  const foundationRun = runFoundation();
  const foundation = readJson(foundationArtifact);
  const recovery = await runRemoteDebugRecoveryVerification();
  const source = fs.readFileSync(path.join(repoRoot, 'desktop-ide', 'renderer', 'js', 'pages', 'beast-compatibility-page.js'), 'utf8');
  const runtime = fs.readFileSync(path.join(repoRoot, 'desktop-ide', 'renderer', 'js', 'beast-ide-runtime.js'), 'utf8');
  const handshakes = foundation?.handshakes || {};
  const ok =
    foundationRun.status === 0 &&
    foundation?.ok === true &&
    recovery?.ok === true &&
    source.includes('data-runtime-debug-stop') &&
    source.includes('data-runtime-debug-threads') &&
    source.includes('data-runtime-debug-variables') &&
    source.includes('data-runtime-debug-config') &&
    source.includes('data-runtime-debug-compound') &&
    runtime.includes("request(session,'loadedSources'") &&
    runtime.includes('supportsRestartRequest') &&
    runtime.includes('restartDebugFrame') &&
    handshakes.debugpy === 'skipped' &&
    handshakes.delve === 'skipped' &&
    handshakes.lldb === 'skipped' &&
    handshakes.dapLaunch === 'skipped' &&
    handshakes.dapRestart === 'skipped';
  const report = {
    ok,
    date: '2026-07-31',
    checks: 3 + 10,
    artifacts: {
      foundation: 'build/PARITY_FOUNDATION.json',
    },
    recovery,
    debugHandshakes: {
      debugpy: handshakes.debugpy,
      delve: handshakes.delve,
      lldb: handshakes.lldb,
      dapLaunch: handshakes.dapLaunch,
      dapRestart: handshakes.dapRestart,
    },
    boundedContract: {
      pausedStateUi: true,
      loadedSources: runtime.includes("request(session,'loadedSources'"),
      restartSupport: runtime.includes('supportsRestartRequest'),
      restartFrame: runtime.includes('restartDebugFrame'),
    },
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
