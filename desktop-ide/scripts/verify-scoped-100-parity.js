#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const repoRoot = path.resolve(__dirname, '..', '..');

function safeReadJson(file) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (_) {
    return null;
  }
}

function run(script, artifact) {
  const file = path.join(__dirname, script);
  const result = spawnSync(process.execPath, [file], {
    cwd: repoRoot,
    encoding: 'utf8',
    timeout: 120000,
    maxBuffer: 1024 * 1024,
  });
  const parsed = safeReadJson(path.join(repoRoot, artifact));
  return {
    ok: result.status === 0 && Boolean(parsed?.ok),
    status: result.status,
    stdout: String(result.stdout || ''),
    stderr: String(result.stderr || ''),
    parsed,
  };
}

function main() {
  const notebook = run(
    'verify-notebook-mime-trust-parity.js',
    'build/NOTEBOOK_MIME_TRUST_PARITY.json',
  );
  const extension = run(
    'verify-real-vscode-extension-host.js',
    'build/REAL_VSCODE_EXTENSION_HOST_PARITY.json',
  );
  const gateway = run(
    'verify-gateway-stability-contract.js',
    'build/GATEWAY_STABILITY_CONTRACT.json',
  );
  const ideServices = run(
    'verify-ide-services-parity.js',
    'build/IDE_SERVICES_PARITY.json',
  );
  const executionTarget = run(
    'verify-execution-target-governed-contract.js',
    'build/EXECUTION_TARGET_GOVERNED_CONTRACT.json',
  );
  const remoteExtension = run(
    'verify-remote-extension-runtime-contract.js',
    'build/REMOTE_EXTENSION_RUNTIME_CONTRACT.json',
  );
  const languageNavigation = run(
    'verify-language-navigation-contract.js',
    'build/LANGUAGE_NAVIGATION_CONTRACT.json',
  );
  const debugLifecycle = run(
    'verify-debug-lifecycle-contract.js',
    'build/DEBUG_LIFECYCLE_CONTRACT.json',
  );
  const notebookRuntime = run(
    'verify-notebook-runtime-contract.js',
    'build/NOTEBOOK_RUNTIME_CONTRACT.json',
  );
  const notebookWidgetState = run(
    'verify-notebook-widget-state-contract.js',
    'build/NOTEBOOK_WIDGET_STATE_CONTRACT.json',
  );
  const dapGoverned = run(
    'verify-dap-governed-contract.js',
    'build/DAP_GOVERNED_CONTRACT.json',
  );
  const testExplorer = run(
    'verify-test-explorer-contract.js',
    'build/TEST_EXPLORER_CONTRACT.json',
  );
  const areas = [
    {
      id: 'notebook_mime_trust_runtime_contract',
      label: 'Notebook MIME/trust/runtime contract',
      percent: notebook.ok ? 100 : 0,
      verifier: 'desktop-ide/scripts/verify-notebook-mime-trust-parity.js',
      checks: Number(notebook.parsed?.checks || 0),
      status: notebook.ok ? 'passed' : 'failed',
      artifact: 'build/NOTEBOOK_MIME_TRUST_PARITY.json',
    },
    {
      id: 'vscode_extension_package_runtime_contract',
      label: 'VS Code extension package/runtime contract',
      percent: extension.ok ? 100 : 0,
      verifier: 'desktop-ide/scripts/verify-real-vscode-extension-host.js',
      checks: Number(extension.parsed?.checks || 0),
      status: extension.ok ? 'passed' : 'failed',
      artifact: 'build/REAL_VSCODE_EXTENSION_HOST_PARITY.json',
    },
    {
      id: 'gateway_stability_contract',
      label: 'Gateway stability contract',
      percent: gateway.ok ? 100 : 0,
      verifier: 'desktop-ide/scripts/verify-gateway-stability-contract.js',
      checks: Number(gateway.parsed?.checks || 0),
      status: gateway.ok ? 'passed' : 'failed',
      artifact: 'build/GATEWAY_STABILITY_CONTRACT.json',
    },
    {
      id: 'ide_services_spine_contract',
      label: 'IDE services spine contract',
      percent: ideServices.ok ? 100 : 0,
      verifier: 'desktop-ide/scripts/verify-ide-services-parity.js',
      checks: Number(ideServices.parsed?.checks || 0),
      status: ideServices.ok ? 'passed' : 'failed',
      artifact: 'build/IDE_SERVICES_PARITY.json',
    },
    {
      id: 'execution_target_governed_contract',
      label: 'Execution target governed contract',
      percent: executionTarget.ok ? 100 : 0,
      verifier: 'desktop-ide/scripts/verify-execution-target-governed-contract.js',
      checks: Number(executionTarget.parsed?.checks || 0),
      status: executionTarget.ok ? 'passed' : 'failed',
      artifact: 'build/EXECUTION_TARGET_GOVERNED_CONTRACT.json',
    },
    {
      id: 'remote_extension_runtime_contract',
      label: 'Remote extension runtime contract',
      percent: remoteExtension.ok ? 100 : 0,
      verifier: 'desktop-ide/scripts/verify-remote-extension-runtime-contract.js',
      checks: Number(remoteExtension.parsed?.checks || 0),
      status: remoteExtension.ok ? 'passed' : 'failed',
      artifact: 'build/REMOTE_EXTENSION_RUNTIME_CONTRACT.json',
    },
    {
      id: 'language_navigation_contract',
      label: 'Language/navigation contract',
      percent: languageNavigation.ok ? 100 : 0,
      verifier: 'desktop-ide/scripts/verify-language-navigation-contract.js',
      checks: Number(languageNavigation.parsed?.checks || 0),
      status: languageNavigation.ok ? 'passed' : 'failed',
      artifact: 'build/LANGUAGE_NAVIGATION_CONTRACT.json',
    },
    {
      id: 'debug_lifecycle_contract',
      label: 'Debug lifecycle contract',
      percent: debugLifecycle.ok ? 100 : 0,
      verifier: 'desktop-ide/scripts/verify-debug-lifecycle-contract.js',
      checks: Number(debugLifecycle.parsed?.checks || 0),
      status: debugLifecycle.ok ? 'passed' : 'failed',
      artifact: 'build/DEBUG_LIFECYCLE_CONTRACT.json',
    },
    {
      id: 'notebook_runtime_contract',
      label: 'Notebook runtime contract',
      percent: notebookRuntime.ok ? 100 : 0,
      verifier: 'desktop-ide/scripts/verify-notebook-runtime-contract.js',
      checks: Number(notebookRuntime.parsed?.checks || 0),
      status: notebookRuntime.ok ? 'passed' : 'failed',
      artifact: 'build/NOTEBOOK_RUNTIME_CONTRACT.json',
    },
    {
      id: 'notebook_widget_state_contract',
      label: 'Notebook widget/state contract',
      percent: notebookWidgetState.ok ? 100 : 0,
      verifier: 'desktop-ide/scripts/verify-notebook-widget-state-contract.js',
      checks: Number(notebookWidgetState.parsed?.checks || 0),
      status: notebookWidgetState.ok ? 'passed' : 'failed',
      artifact: 'build/NOTEBOOK_WIDGET_STATE_CONTRACT.json',
    },
    {
      id: 'dap_governed_contract',
      label: 'DAP governed contract',
      percent: dapGoverned.ok ? 100 : 0,
      verifier: 'desktop-ide/scripts/verify-dap-governed-contract.js',
      checks: Number(dapGoverned.parsed?.checks || 0),
      status: dapGoverned.ok ? 'passed' : 'failed',
      artifact: 'build/DAP_GOVERNED_CONTRACT.json',
    },
    {
      id: 'test_explorer_contract',
      label: 'Test explorer contract',
      percent: testExplorer.ok ? 100 : 0,
      verifier: 'desktop-ide/scripts/verify-test-explorer-contract.js',
      checks: Number(testExplorer.parsed?.checks || 0),
      status: testExplorer.ok ? 'passed' : 'failed',
      artifact: 'build/TEST_EXPLORER_CONTRACT.json',
    },
  ];
  const ok = areas.every(area => area.percent === 100);
  const report = {
    ok,
    date: '2026-07-31',
    scoped_100_areas: areas,
  };
  fs.mkdirSync(path.join(repoRoot, 'build'), { recursive: true });
  fs.writeFileSync(path.join(repoRoot, 'build', 'SCOPED_100_PARITY.json'), `${JSON.stringify(report, null, 2)}\n`, 'utf8');
  console.log(JSON.stringify(report, null, 2));
  process.exit(ok ? 0 : 1);
}

main();
