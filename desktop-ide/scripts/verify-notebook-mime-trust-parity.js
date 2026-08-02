#!/usr/bin/env node
'use strict';

const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { createNotebookExecutionHost } = require('../main/notebook-execution-host');
const { normalizeNotebookOutputs, summarizeMimeOutputs } = require('../main/notebook-output-contract');

const repoRoot = path.resolve(__dirname, '..', '..');
const renderer = fs.readFileSync(path.join(repoRoot, 'desktop-ide', 'renderer', 'js', 'pages', 'beast-workspace-page.js'), 'utf8');
const editorCortex = fs.readFileSync(path.join(repoRoot, 'desktop-ide', 'renderer', 'js', 'beast-editor-cortex.js'), 'utf8');
const trustGate = fs.readFileSync(path.join(repoRoot, 'desktop-ide', 'renderer', 'js', 'beast-workspace-trust.js'), 'utf8');

async function main() {
  const richOutputs = normalizeNotebookOutputs([
    { output_type:'display_data', data:{ 'text/html':'<b onclick="x()">safe-ish</b><script>bad()</script>', 'text/plain':'safe-ish' }, metadata:{ isolated:false } },
    { output_type:'display_data', data:{ 'image/png':'iVBORw0KGgo=', 'image/svg+xml':'<svg><circle r="4"/></svg>' } },
    { output_type:'execute_result', execution_count:7, data:{ 'application/json':{ answer:42 }, 'text/plain':'{"answer":42}' } },
    { output_type:'error', ename:'ValueError', evalue:'nope', traceback:['line 1','ValueError: nope'] },
  ]);
  const summary = summarizeMimeOutputs(richOutputs);
  assert.equal(richOutputs[0].output_type, 'display_data');
  assert.equal(richOutputs[0].primary_mime, 'text/html');
  assert.equal(richOutputs[1].primary_mime, 'image/png');
  assert.equal(richOutputs[2].execution_count, 7);
  assert.equal(summary.hasRichOutput, true);
  assert(summary.mimeTypes.includes('text/html'));
  assert(summary.mimeTypes.includes('application/json'));

  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'beast-notebook-'));
  const host = createNotebookExecutionHost({
    repoRoot,
    getActiveWorkspaceRoot: () => tmp,
    boundedProcess: async () => ({ ok:true, returncode:0, stdout:'hello notebook\n', stderr:'' }),
  });
  const result = await host.executeNotebookCell(tmp, { code:'print("hello notebook")' });
  assert.equal(result.ok, true);
  assert.equal(result.outputs[0].output_type, 'stream');
  assert.equal(result.outputs[0].data['text/plain'], 'hello notebook\n');
  assert.equal(result.output_mime_summary.hasRichOutput, false);

  assert(renderer.includes('function notebookMimeBundle'));
  assert(renderer.includes('sanitizeNotebookHtml'));
  assert(renderer.includes('HTML output rendered as text until this workspace is trusted'));
  assert(renderer.includes('SVG output held in restricted render mode'));
  assert(renderer.includes('data-notebook-output-mime'));
  assert(renderer.includes('beast-notebook-trust'));
  assert(renderer.includes('data-notebook-runtime-summary'));
  assert(renderer.includes('Trusted MIME'));
  assert(renderer.includes('restricted execution gate'));
  assert(editorCortex.includes('BEAST_WORKSPACE_RESTRICTED'));
  assert(trustGate.includes('[data-notebook-action="run-cell"]'));
  assert(trustGate.includes('[data-notebook-action="run-all"]'));

  const report = { ok:true, checks:15, mimeTypes:summary.mimeTypes, renderer:'trust-aware-rich-mime', execution:'normalized-mime-bundles' };
  fs.mkdirSync(path.join(repoRoot, 'build'), { recursive:true });
  fs.writeFileSync(path.join(repoRoot, 'build', 'NOTEBOOK_MIME_TRUST_PARITY.json'), `${JSON.stringify(report, null, 2)}\n`);
  console.log(JSON.stringify(report, null, 2));
}

main().catch(error => {
  console.error(error);
  process.exit(1);
});
