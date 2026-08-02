#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const repoRoot = path.resolve(__dirname, '..', '..');
const reportPath = path.join(repoRoot, 'build', 'EXECUTION_TARGET_PARITY.json');
const artifactPath = path.join(repoRoot, 'build', 'EXECUTION_TARGET_GOVERNED_CONTRACT.json');
const allowedSkipped = new Set([
  'SSH target live handshake',
  'container target live handshake',
  'Dev Container Compose lifecycle live acceptance',
]);

function main() {
  const result = spawnSync(process.execPath, [path.join(__dirname, 'verify-execution-target-parity.js')], {
    cwd: repoRoot,
    encoding: 'utf8',
    timeout: 180000,
    maxBuffer: 1024 * 1024,
  });
  let report = null;
  try {
    report = JSON.parse(fs.readFileSync(reportPath, 'utf8'));
  } catch (_) {
    report = null;
  }
  const rows = Array.isArray(report?.rows) ? report.rows : [];
  const failedRows = rows.filter(row => row.status === 'failed');
  const skippedRows = rows.filter(row => row.status === 'skipped');
  const unexpectedSkips = skippedRows.filter(row => !allowedSkipped.has(String(row.name || '')));
  const ok =
    result.status === 0 &&
    Boolean(report?.ok) &&
    failedRows.length === 0 &&
    skippedRows.length === allowedSkipped.size &&
    unexpectedSkips.length === 0;
  const contract = {
    ok,
    date: '2026-07-31',
    checks: rows.filter(row => row.status === 'passed').length,
    verifier: 'desktop-ide/scripts/verify-execution-target-parity.js',
    allowedSkipped: [...allowedSkipped],
    skipped: skippedRows.map(row => row.name),
    failed: failedRows.map(row => row.name),
    artifact: 'build/EXECUTION_TARGET_PARITY.json',
  };
  fs.mkdirSync(path.dirname(artifactPath), { recursive: true });
  fs.writeFileSync(artifactPath, `${JSON.stringify(contract, null, 2)}\n`, 'utf8');
  console.log(JSON.stringify(contract, null, 2));
  process.exit(ok ? 0 : 1);
}

main();
