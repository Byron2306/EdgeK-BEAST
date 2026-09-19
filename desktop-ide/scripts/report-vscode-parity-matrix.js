#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');

const repo = path.resolve(__dirname, '..', '..');
const scopedPath = path.join(repo, 'build', 'SCOPED_100_PARITY.json');
const outputPath = path.join(repo, 'build', 'VSCODE_PARITY_MATRIX.json');

const capabilities = [
  ['extension_runtime', 'VS Code extension package/runtime contract', 'vscode_extension_package_runtime_contract'],
  ['language_navigation', 'Language/navigation contract', 'language_navigation_contract'],
  ['tasks_services', 'IDE services spine contract', 'ide_services_spine_contract'],
  ['debug_dap', 'DAP governed contract', 'dap_governed_contract'],
  ['testing', 'Test Explorer contract', 'test_explorer_contract'],
  ['notebooks', 'Notebook runtime contract', 'notebook_runtime_contract'],
  ['notebook_trust_mime', 'Notebook MIME/trust/runtime contract', 'notebook_mime_trust_runtime_contract'],
  ['notebook_widget_state', 'Notebook widget/state contract', 'notebook_widget_state_contract'],
  ['remote_execution', 'Execution target governed contract', 'execution_target_governed_contract'],
  ['remote_extensions', 'Remote extension runtime contract', 'remote_extension_runtime_contract'],
  ['gateway', 'Gateway stability contract', 'gateway_stability_contract'],
];

function main() {
  let scoped = null;
  try { scoped = JSON.parse(fs.readFileSync(scopedPath, 'utf8')); } catch (_) {}
  const byId = new Map((scoped?.scoped_100_areas || []).map(row => [row.id, row]));
  const rows = capabilities.map(([id, label, sourceId]) => {
    const source = byId.get(sourceId);
    return {
      id,
      label,
      status: source?.status === 'passed' ? 'verified' : source ? 'failed' : 'unverified',
      checks: Number(source?.checks || 0),
      verifier: source?.verifier || '',
      artifact: source?.artifact || '',
      source_scope: sourceId,
    };
  });
  rows.push(
    { id: 'marketplace_ecosystem_breadth', label: 'Marketplace/ecosystem breadth', status: 'partial', reason: 'No exhaustive VS Code Marketplace corpus proof.' },
    { id: 'complete_vscode_api_surface', label: 'Complete VS Code API surface', status: 'partial', reason: 'Compatibility host implements a bounded API surface; exhaustive API proof is absent.' },
    { id: 'ui_ux', label: 'VS Code UI/UX parity', status: 'not-applicable', reason: 'BEAST intentionally retains its own governed operator surface.' },
    { id: 'coding_agent_governance', label: 'BEAST governed coding-agent workflow', status: 'beast_extension', reason: 'BEAST-specific capability above the VS Code baseline.' },
  );
  const measured = rows.filter(row => ['verified','failed','unverified','partial'].includes(row.status));
  const verified = measured.filter(row => row.status === 'verified').length;
  const report = {
    beast_object_type: 'beast_vscode_parity_matrix',
    version: '1.0',
    generated_from: 'build/SCOPED_100_PARITY.json',
    scoped_source_present: Boolean(scoped),
    warning: 'This matrix does not claim universal VS Code parity.',
    summary: { measured_capabilities: measured.length, verified, partial: measured.filter(r => r.status === 'partial').length, failed: measured.filter(r => r.status === 'failed').length, unverified: measured.filter(r => r.status === 'unverified').length },
    capabilities: rows,
  };
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, JSON.stringify(report, null, 2) + '\n', 'utf8');
  console.log(JSON.stringify(report, null, 2));
  process.exit(report.summary.failed ? 1 : 0);
}
main();
