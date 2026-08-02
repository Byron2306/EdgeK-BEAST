#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const repoRoot = path.resolve(__dirname, '..', '..');
const servicesArtifact = path.join(repoRoot, 'build', 'IDE_SERVICES_PARITY.json');
const ecosystemArtifact = path.join(repoRoot, 'build', 'ECOSYSTEM_TEST_ADAPTERS.json');
const artifactPath = path.join(repoRoot, 'build', 'TEST_EXPLORER_CONTRACT.json');

function run(script) {
  return spawnSync(process.execPath, [path.join(__dirname, script)], {
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

function main() {
  const servicesRun = run('verify-ide-services-parity.js');
  const ecosystemRun = run('verify-ecosystem-test-adapters.js');
  const services = readJson(servicesArtifact);
  let ecosystem = readJson(ecosystemArtifact);
  if (!ecosystem) {
    try {
      ecosystem = JSON.parse(String(ecosystemRun.stdout || '{}'));
    } catch (_) {
      ecosystem = null;
    }
  }
  const page = fs.readFileSync(path.join(repoRoot, 'desktop-ide', 'renderer', 'js', 'pages', 'beast-testing-page.js'), 'utf8');
  const terminalPage = fs.readFileSync(path.join(repoRoot, 'desktop-ide', 'renderer', 'js', 'pages', 'beast-terminal-page.js'), 'utf8');
  const taskHost = fs.readFileSync(path.join(repoRoot, 'desktop-ide', 'main', 'task-test-host.js'), 'utf8');
  const tests = services?.snapshot?.services?.tests || {};
  const debug = services?.snapshot?.services?.debug || {};
  const recent = tests.recent || [];
  const ok =
    servicesRun.status === 0 &&
    services?.ok === true &&
    Boolean(ecosystem?.ok) === true &&
    Number(ecosystem?.tests || 0) >= 8 &&
    Number(ecosystem?.nodes || 0) >= 7 &&
    Array.isArray(ecosystem?.frameworks) &&
    ecosystem.frameworks.includes('pytest') &&
    ecosystem.frameworks.includes('go') &&
    ecosystem.frameworks.includes('cargo') &&
    ecosystem.frameworks.includes('maven') &&
    ecosystem.frameworks.includes('gradle') &&
    ecosystem.frameworks.includes('dotnet') &&
    ecosystem.frameworks.includes('playwright') &&
    ecosystem.frameworks.includes('cypress') &&
    tests.ok === true &&
    Number(tests.testCount || 0) >= 2 &&
    Number(tests.fileCount || 0) >= 2 &&
    Number(tests.nodeCount || 0) >= 2 &&
    Array.isArray(tests.frameworks) &&
    tests.frameworks.includes('node:test') &&
    Number(tests.historyCount || 0) >= 1 &&
    Array.isArray(recent) &&
    recent.some(row => Number(row.retryCount || 0) >= 0) &&
    debug.status === 'ready' &&
    Array.isArray(debug.adapters) &&
    debug.adapters.length >= 2 &&
    Array.isArray(debug.profiles) &&
    debug.profiles.some(profile => profile.id === 'launch:Debug sample Python') &&
    page.includes('data-test-flaky') &&
    page.includes('data-test-history') &&
    page.includes('data-test-task-history') &&
    page.includes('data-test-action="retry"') &&
    page.includes("Focused debug currently supports pytest.") &&
    page.includes('startDebug({adapter:\'debugpy\'') &&
    terminalPage.includes('test-file-debug') &&
    taskHost.includes('retryOnFailure') &&
    taskHost.includes('flaky=attempts.length>1&&!attempts[0].ok&&Boolean(result.ok)');

  const report = {
    ok,
    date: '2026-07-31',
    checks: 24,
    artifacts: {
      services: 'build/IDE_SERVICES_PARITY.json',
      ecosystem: 'build/ECOSYSTEM_TEST_ADAPTERS.json',
    },
    ecosystem,
    tests: {
      testCount: tests.testCount || 0,
      fileCount: tests.fileCount || 0,
      nodeCount: tests.nodeCount || 0,
      frameworks: tests.frameworks || [],
      historyCount: tests.historyCount || 0,
    },
  };
  fs.mkdirSync(path.dirname(artifactPath), { recursive: true });
  fs.writeFileSync(artifactPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
  console.log(JSON.stringify(report, null, 2));
  process.exit(ok ? 0 : 1);
}

main();
