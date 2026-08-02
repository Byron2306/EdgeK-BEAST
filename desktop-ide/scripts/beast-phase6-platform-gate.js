#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { spawnSync } = require('child_process');

function arg(name, fallback = null) {
  const i = process.argv.indexOf(name);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}
function has(name) { return process.argv.includes(name); }
function run(command, args, options = {}) {
  const started = Date.now();
  const result = spawnSync(command, args, {
    cwd: options.cwd,
    encoding: 'utf8',
    timeout: options.timeout || 180000,
    shell: false,
    env: { ...process.env, ...(options.env || {}) },
  });
  return {
    ok: result.status === 0,
    command: [command, ...args].join(' '),
    returncode: result.status,
    signal: result.signal || null,
    duration_ms: Date.now() - started,
    stdout_tail: String(result.stdout || '').slice(-4000),
    stderr_tail: String(result.stderr || '').slice(-4000),
    error: result.error ? String(result.error.message || result.error) : null,
  };
}
function digest(value) {
  return `sha256:${crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex')}`;
}
function check(name, passed, detail = {}) { return { name, passed: Boolean(passed), ...detail }; }
function readJson(file) { return JSON.parse(fs.readFileSync(file, 'utf8')); }
function isSandboxGated(result) {
  const errorText = String(result?.error || '');
  const stderr = String(result?.stderr_tail || '');
  const stdout = String(result?.stdout_tail || '');
  return /EPERM/i.test(errorText) && !stderr.trim() && !stdout.trim();
}

const desktop = path.resolve(arg('--desktop', path.resolve(__dirname, '..')));
const output = path.resolve(arg('--json', path.join(desktop, 'phase6_7_platform_receipt.json')));
const target = arg('--target', 'local');
const expectedPlatform = arg('--expect-platform', process.platform);
const runLive = has('--live');
const runPackage = has('--package');
const checks = [];

checks.push(check('platform_matches', process.platform === expectedPlatform, { observed: process.platform, expected: expectedPlatform }));
checks.push(check('supported_platform', ['linux', 'win32', 'darwin'].includes(process.platform), { observed: process.platform }));
checks.push(check('supported_target', ['local', 'ssh', 'container'].includes(target), { target }));

const required = [
  'package.json', 'main.js', 'preload.js', 'main/ipc-registry.js',
  'main/workspace-file-host.js', 'main/workspace-state-host.js',
  'renderer/index.html', 'renderer/js/beast-release-app.js',
  'scripts/smoke-desktop-ide.js', 'scripts/verify-execution-target-parity.js',
];
for (const rel of required) checks.push(check(`file:${rel}`, fs.existsSync(path.join(desktop, rel)), { path: path.join(desktop, rel) }));

let pkg = {};
try { pkg = readJson(path.join(desktop, 'package.json')); } catch (error) { checks.push(check('package_json_parse', false, { error: String(error) })); }
if (Object.keys(pkg).length) {
  checks.push(check('package_json_parse', true, { name: pkg.name, version: pkg.version }));
  checks.push(check('electron_dependency_declared', Boolean(pkg.devDependencies?.electron || pkg.dependencies?.electron)));
  checks.push(check('monaco_dependency_declared', Boolean(pkg.dependencies?.['monaco-editor'])));
}

const jsFiles = [];
for (const root of ['main.js', 'preload.js', 'main', 'renderer/js', 'scripts']) {
  const start = path.join(desktop, root);
  if (!fs.existsSync(start)) continue;
  const stat = fs.statSync(start);
  if (stat.isFile()) jsFiles.push(start);
  else {
    const stack = [start];
    while (stack.length) {
      const current = stack.pop();
      for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
        const full = path.join(current, entry.name);
        if (entry.isDirectory()) stack.push(full);
        else if (entry.isFile() && entry.name.endsWith('.js')) jsFiles.push(full);
      }
    }
  }
}
let syntaxFailures = [];
for (const file of jsFiles) {
  const result = run(process.execPath, ['--check', file], { timeout: 20000 });
  if (!result.ok) syntaxFailures.push({ file, ...result });
}
checks.push(check('javascript_syntax', syntaxFailures.length === 0, { checked: jsFiles.length, failures: syntaxFailures.slice(0, 10) }));

const smokePath = path.join(desktop, 'scripts', 'smoke-desktop-ide.js');
if (fs.existsSync(smokePath)) {
  const smoke = run(process.execPath, [smokePath], { cwd: desktop, timeout: 180000 });
  checks.push(check('desktop_renderer_smoke', smoke.ok, { detail: smoke }));
}
const parityPath = path.join(desktop, 'scripts', 'verify-parity-foundation-static.js');
if (fs.existsSync(parityPath)) {
  const parity = run(process.execPath, [parityPath], { cwd: desktop, timeout: 180000 });
  const missingParentBackend = !parity.ok && /ENOENT:.*app[\\/]routes[\\/]ide\.py/.test(`${parity.stderr_tail} ${parity.stdout_tail}`);
  const sandboxGated = !parity.ok && isSandboxGated(parity);
  if (missingParentBackend) {
    checks.push({ name: 'parity_foundation', passed: null, status: 'environment_gated', reason: 'desktop-only archive lacks parent repository app/routes/ide.py', detail: parity });
  } else if (sandboxGated) {
    checks.push({ name: 'parity_foundation', passed: null, status: 'environment_gated', reason: 'process sandbox blocked parity subprocess launch; rerun on the host desktop shell', detail: parity });
  } else {
    checks.push(check('parity_foundation', parity.ok, { detail: parity }));
  }
}
const targetsPath = path.join(desktop, 'scripts', 'verify-execution-target-parity.js');
if (fs.existsSync(targetsPath)) {
  const targets = run(process.execPath, [targetsPath], { cwd: desktop, timeout: 180000 });
  checks.push(check('execution_target_contract', targets.ok, { detail: targets }));
}

const platformContracts = {
  linux: ['linux'],
  win32: ['win'],
  darwin: ['mac'],
};
checks.push(check('builder_target_declared', Boolean(pkg.build?.[platformContracts[process.platform]?.[0]] || pkg.build), {
  platform: process.platform,
  build_keys: Object.keys(pkg.build || {}),
}));

if (runLive) {
  const launch = path.join(desktop, 'scripts', 'launch-smoke-desktop-ide.js');
  if (fs.existsSync(launch)) {
    const live = run(process.execPath, [launch], { cwd: desktop, timeout: 180000 });
    checks.push(check('live_electron_launch', live.ok, { detail: live }));
  } else checks.push(check('live_electron_launch', false, { error: 'launch smoke script missing' }));
} else {
  checks.push({ name: 'live_electron_launch', passed: null, status: 'environment_gated', reason: 'rerun with --live on an interactive or CI desktop host' });
}

if (runPackage) {
  const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm';
  const packaged = run(npm, ['run', 'package:dir'], { cwd: desktop, timeout: 900000 });
  checks.push(check('platform_package_directory', packaged.ok, { detail: packaged }));
} else {
  checks.push({ name: 'platform_package_directory', passed: null, status: 'environment_gated', reason: 'rerun with --package on the native platform' });
}

const journeyPath = arg('--journey', null);
let journey = null;
if (journeyPath) {
  try {
    journey = readJson(path.resolve(journeyPath));
    const requiredJourneys = ['edit', 'navigation', 'search', 'save', 'restore', 'trust'];
    const missing = requiredJourneys.filter(key => journey.journeys?.[key] !== 'pass');
    checks.push(check('operator_journey_attestation', missing.length === 0, { missing, journey_path: path.resolve(journeyPath) }));
  } catch (error) {
    checks.push(check('operator_journey_attestation', false, { error: String(error) }));
  }
} else {
  checks.push({ name: 'operator_journey_attestation', passed: null, status: 'environment_gated', reason: 'supply --journey <receipt.json>' });
}

const hard = checks.filter(item => item.passed !== null);
const passed = hard.filter(item => item.passed).length;
const failed = hard.filter(item => !item.passed).length;
const gated = checks.filter(item => item.passed === null).length;
const receipt = {
  beast_object_type: 'beast_phase6_7_platform_exit_receipt',
  schema: 'beast.ide.phase6.platform-exit.v1',
  created_at: new Date().toISOString(),
  platform: process.platform,
  arch: process.arch,
  target,
  node: process.version,
  desktop,
  mode: { live: runLive, package: runPackage },
  status: failed ? 'fail' : (gated ? 'partial' : 'pass'),
  validated: failed === 0 && gated === 0,
  summary: { checks: checks.length, passed, failed, environment_gated: gated },
  checks,
  journey,
};
receipt.receipt_digest = digest(receipt);
fs.mkdirSync(path.dirname(output), { recursive: true });
fs.writeFileSync(output, JSON.stringify(receipt, null, 2) + '\n');
console.log(JSON.stringify({ receipt: output, status: receipt.status, validated: receipt.validated, summary: receipt.summary, receipt_digest: receipt.receipt_digest }, null, 2));
process.exit(failed ? 1 : 0);
