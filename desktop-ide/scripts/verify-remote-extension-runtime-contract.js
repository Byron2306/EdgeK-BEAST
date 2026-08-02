#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const { verifyRemoteExtensionRouting, verifyRemoteContinuity, verifyContainerContinuity, verifyRemoteSoakMatrix } = require('./verify-remote-extension-parity');

const repoRoot = path.resolve(__dirname, '..', '..');
const artifactPath = path.join(repoRoot, 'build', 'REMOTE_EXTENSION_RUNTIME_CONTRACT.json');

async function main() {
  const results = await Promise.all([
    verifyRemoteExtensionRouting(),
    verifyRemoteContinuity(),
    verifyContainerContinuity(),
    verifyRemoteSoakMatrix(),
  ]);
  const ok = results.every(result => result.ok);
  const report = {
    ok,
    date: '2026-07-31',
    checks: results.reduce((sum, result) => sum + Number(result.checks || 0), 0),
    failed: results.flatMap(result => result.failed || []),
    parts: {
      routing: results[0],
      sshContinuity: results[1],
      containerContinuity: results[2],
      soakMatrix: results[3],
    },
  };
  fs.mkdirSync(path.dirname(artifactPath), { recursive: true });
  fs.writeFileSync(artifactPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
  console.log(JSON.stringify({ ok: report.ok, checks: report.checks, failed: report.failed }, null, 2));
  process.exit(ok ? 0 : 1);
}

main().catch(error => {
  console.error(error.stack || String(error));
  process.exit(1);
});
