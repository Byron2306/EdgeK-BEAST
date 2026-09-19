#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const repo = path.resolve(__dirname, '..', '..');
const desktop = path.join(repo, 'desktop-ide');

const contracts = [
  ['ide_services', 'scripts/verify-ide-services-parity.js', 'build/IDE_SERVICES_PARITY.json', true],
  ['execution_targets', 'scripts/verify-execution-target-governed-contract.js', 'build/EXECUTION_TARGET_GOVERNED_CONTRACT.json', false],
  ['language_navigation', 'scripts/verify-language-navigation-contract.js', 'build/LANGUAGE_NAVIGATION_CONTRACT.json', false],
  ['debug_lifecycle', 'scripts/verify-debug-lifecycle-contract.js', 'build/DEBUG_LIFECYCLE_CONTRACT.json', false],
  ['test_explorer', 'scripts/verify-test-explorer-contract.js', 'build/TEST_EXPLORER_CONTRACT.json', true],
];

function readJson(file) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch (_) { return null; }
}

function run([id, script, artifact, required]) {
  const result = spawnSync(process.execPath, [path.join(desktop, script)], {
    cwd: repo, encoding: 'utf8', timeout: 120000, maxBuffer: 1024 * 1024,
  });
  const parsed = readJson(path.join(repo, artifact));
  return {
    id, script, artifact, required,
    exit_code: result.status,
    reported_ok: parsed?.ok === true,
    checks: Number(parsed?.checks || 0),
    failed: Array.isArray(parsed?.failed) ? parsed.failed : [],
    skipped: Array.isArray(parsed?.skipped) ? parsed.skipped : [],
    environment_limited: result.status !== 0 && !required,
  };
}

const results = contracts.map(run);
const requiredFailures = results.filter(item => item.required && !item.reported_ok);
const report = {
  beast_object_type: 'beast_termux_vscode_parity_report',
  version: '1.0',
  platform: process.platform,
  arch: process.arch,
  scope: 'headless_contracts_only',
  ok: requiredFailures.length === 0,
  warning: 'A passing Termux profile is not full VS Code/Electron parity. Optional desktop, remote-target and language-adapter gaps remain visible below.',
  required_failures: requiredFailures.map(item => item.id),
  contracts: results,
};
fs.mkdirSync(path.join(repo, 'build'), { recursive: true });
fs.writeFileSync(path.join(repo, 'build', 'TERMUX_VSCODE_PARITY.json'), JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify(report, null, 2));
process.exit(report.ok ? 0 : 1);
