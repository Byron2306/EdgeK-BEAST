#!/usr/bin/env node
'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const { EventEmitter } = require('events');

const repoRoot = path.resolve(__dirname, '..', '..');
const renderer = fs.readFileSync(path.join(repoRoot, 'desktop-ide', 'renderer', 'js', 'pages', 'beast-workspace-page.js'), 'utf8');
const runtime = fs.readFileSync(path.join(repoRoot, 'desktop-ide', 'renderer', 'js', 'beast-ide-runtime.js'), 'utf8');
const editorCortex = fs.readFileSync(path.join(repoRoot, 'desktop-ide', 'renderer', 'js', 'beast-editor-cortex.js'), 'utf8');
const { normalizeNotebookOutputs, summarizeMimeOutputs } = require('../main/notebook-output-contract');

function loadNotebookKernelHostWithFakeSpawn(spawnFactory) {
  const childProcess = require('child_process');
  const originalSpawn = childProcess.spawn;
  const modulePath = require.resolve('../main/notebook-kernel-host');
  delete require.cache[modulePath];
  childProcess.spawn = spawnFactory;
  try {
    return require('../main/notebook-kernel-host').NotebookKernelHost;
  } finally {
    childProcess.spawn = originalSpawn;
    delete require.cache[modulePath];
  }
}

function createFakeKernelProcess() {
  const proc = new EventEmitter();
  proc.stdout = new EventEmitter();
  proc.stderr = new EventEmitter();
  proc.pid = 424242;
  proc.killed = false;
  proc.stdin = {
    writable: true,
    write(chunk) {
      const payload = JSON.parse(String(chunk || '').trim());
      if (payload.operation === 'shutdown') {
        setTimeout(() => {
          proc.killed = true;
          proc.emit('exit', 0, 'SIGTERM');
        }, 0);
        return true;
      }
      if (payload.operation === 'execute') {
        setTimeout(() => {
          proc.stdout.emit('data', `${JSON.stringify({
            id: payload.id,
            ok: true,
            execution_count: 9,
            outputs: [
              {
                output_type: 'display_data',
                data: {
                  'application/vnd.jupyter.widget-view+json': { model_id: 'widget-1', version_major: 2 },
                  'text/plain': 'widget payload',
                },
                metadata: {},
              },
              {
                output_type: 'display_data',
                data: {
                  'text/html': '<b>trusted html</b>',
                  'text/plain': 'trusted html',
                },
                metadata: {},
              },
            ],
          })}\n`);
        }, 0);
        return true;
      }
      return true;
    },
  };
  proc.kill = function kill(signal = 'SIGTERM') {
    this.killed = true;
    this.signal = signal;
    setTimeout(() => this.emit('exit', 0, signal), 0);
    return true;
  };
  setTimeout(() => {
    proc.stdout.emit('data', `${JSON.stringify({ type: 'ready', pid: proc.pid, kernel: 'beast-python' })}\n`);
  }, 0);
  return proc;
}

async function main() {
  const NotebookKernelHost = loadNotebookKernelHostWithFakeSpawn(() => createFakeKernelProcess());
  const senderMessages = [];
  const sender = {
    isDestroyed: () => false,
    send: (_channel, message) => senderMessages.push(message),
  };
  const host = new NotebookKernelHost({
    repoRoot,
    runtimeResourcePath: (...parts) => path.join(repoRoot, 'desktop-ide', ...parts),
    pythonToolRoot: () => path.join(repoRoot, 'desktop-ide', 'dist', 'linux-unpacked', 'resources', 'python-tools'),
  });

  const summary = host.start(repoRoot, sender);
  assert.equal(summary.kernel, 'beast-python');

  await new Promise(resolve => setTimeout(resolve, 10));
  const ready = senderMessages.find(message => message.type === 'ready');
  assert(ready && ready.kernel === 'beast-python');

  const executed = await host.request({
    operation: 'execute',
    code: 'print("runtime contract")',
    timeout: 30,
  });
  assert.equal(executed.execution_count, 9);
  assert.equal(executed.receipt.id.startsWith('NBK-'), true);
  assert.equal(executed.output_mime_summary.trustSensitive, true);
  assert(executed.output_mime_summary.mimeTypes.includes('application/vnd.jupyter.widget-view+json'));
  assert(executed.output_mime_summary.mimeTypes.includes('text/html'));

  const normalized = normalizeNotebookOutputs(executed.outputs);
  const summaryMime = summarizeMimeOutputs(normalized);
  assert.equal(summaryMime.trustSensitive, true);
  assert(summaryMime.trustedMimeTypes.includes('application/vnd.jupyter.widget-view+json'));
  assert(summaryMime.trustedMimeTypes.includes('text/html'));

  const stopped = host.stop();
  assert.equal(stopped.ok, true);

  assert(editorCortex.includes('function parseNotebook(text)'));
  assert(editorCortex.includes('function serializeNotebook(document)'));
  assert(editorCortex.includes('async function runNotebookCell'));
  assert(editorCortex.includes('async function runAllNotebookCells'));
  assert(editorCortex.includes("runtime: 'persistent-jupyter-kernel'"));
  assert(editorCortex.includes("runtime: 'trust-gated-notebook'"));
  assert(editorCortex.includes('receipt_id: result.receipt?.id ||'));

  assert(runtime.includes("patchRuntime('notebook',{status:'kernel-ready'"));
  assert(runtime.includes("patchRuntime('notebook',{status:'running',error:''})"));
  assert(runtime.includes('lastMimeSummary:result.output_mime_summary||{}'));
  assert(runtime.includes("if (message.type==='stderr')"));
  assert(runtime.includes("if (message.type==='exit') { notebookKernel=null;"));

  assert(renderer.includes('application/vnd.jupyter.widget-view+json'));
  assert(renderer.includes('Widget state recorded; rich widget runtime is not embedded in this shell.'));
  assert(renderer.includes('Structured visualization bundle captured; interactive runtime is not embedded in this shell.'));
  assert(renderer.includes('Rich MIME bundles are rendered in trusted review mode.'));
  assert(renderer.includes('data-notebook-runtime-summary'));
  assert(renderer.includes('Execution ${escapeHtml(cell.metadata.beast.receipt_id)}'));

  const report = {
    ok: true,
    date: '2026-07-31',
    checks: 20,
    kernel: {
      ready: true,
      executionCount: executed.execution_count,
      receipt: executed.receipt.id,
      trustSensitive: executed.output_mime_summary.trustSensitive,
    },
    mimeTypes: summaryMime.mimeTypes,
    trustedMimeTypes: summaryMime.trustedMimeTypes,
  };
  fs.mkdirSync(path.join(repoRoot, 'build'), { recursive: true });
  fs.writeFileSync(
    path.join(repoRoot, 'build', 'NOTEBOOK_RUNTIME_CONTRACT.json'),
    `${JSON.stringify(report, null, 2)}\n`,
    'utf8',
  );
  console.log(JSON.stringify(report, null, 2));
}

main().catch(error => {
  console.error(error.stack || String(error));
  process.exit(1);
});
