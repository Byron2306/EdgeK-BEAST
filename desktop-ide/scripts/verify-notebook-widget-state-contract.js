#!/usr/bin/env node
'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const { normalizeNotebookOutputs, summarizeMimeOutputs } = require('../main/notebook-output-contract');

const repoRoot = path.resolve(__dirname, '..', '..');
const renderer = fs.readFileSync(path.join(repoRoot, 'desktop-ide', 'renderer', 'js', 'pages', 'beast-workspace-page.js'), 'utf8');
const editorCortex = fs.readFileSync(path.join(repoRoot, 'desktop-ide', 'renderer', 'js', 'beast-editor-cortex.js'), 'utf8');

function main() {
  const outputs = normalizeNotebookOutputs([
    {
      output_type: 'display_data',
      data: {
        'application/vnd.jupyter.widget-view+json': {
          model_id: 'widget-model-7',
          version_major: 2,
          version_minor: 0,
        },
        'text/plain': 'Widget[IntSlider(value=7)]',
      },
      metadata: {
        beast: {
          trust_state: 'trusted',
          output_mime_summary: {
            outputCount: 1,
            mimeTypes: ['application/vnd.jupyter.widget-view+json', 'text/plain'],
          },
        },
      },
    },
    {
      output_type: 'display_data',
      data: {
        'application/vnd.plotly.v1+json': {
          data: [{ type: 'bar', x: ['A', 'B'], y: [1, 2] }],
          layout: { title: 'Plotly state' },
        },
        'text/plain': 'Plotly bundle',
      },
    },
    {
      output_type: 'display_data',
      data: {
        'application/vnd.vega.v5+json': {
          data: { values: [{ x: 1, y: 2 }] },
          mark: 'point',
        },
        'text/plain': 'Vega bundle',
      },
    },
    {
      output_type: 'display_data',
      data: {
        'application/vnd.vegalite.v5+json': {
          data: { values: [{ x: 1, y: 2 }] },
          mark: 'line',
        },
        'text/plain': 'Vega-Lite bundle',
      },
    },
  ]);

  const summary = summarizeMimeOutputs(outputs);
  assert.equal(summary.trustSensitive, true);
  assert(summary.mimeTypes.includes('application/vnd.jupyter.widget-view+json'));
  assert(summary.mimeTypes.includes('application/vnd.plotly.v1+json'));
  assert(summary.mimeTypes.includes('application/vnd.vega.v5+json'));
  assert(summary.mimeTypes.includes('application/vnd.vegalite.v5+json'));
  assert(summary.trustedMimeTypes.includes('application/vnd.jupyter.widget-view+json'));
  assert(summary.trustedMimeTypes.includes('application/vnd.plotly.v1+json'));
  assert(summary.trustedMimeTypes.includes('application/vnd.vega.v5+json'));
  assert(summary.trustedMimeTypes.includes('application/vnd.vegalite.v5+json'));

  assert(renderer.includes("application/vnd.jupyter.widget-view+json"));
  assert(renderer.includes("application/vnd.plotly.v1+json"));
  assert(renderer.includes("application/vnd.vega.v5+json"));
  assert(renderer.includes("application/vnd.vegalite.v5+json"));
  assert(renderer.includes('Widget state recorded; rich widget runtime is not embedded in this shell.'));
  assert(renderer.includes('Widget output held until this workspace is trusted.'));
  assert(renderer.includes('Structured visualization bundle captured; interactive runtime is not embedded in this shell.'));
  assert(renderer.includes('Visualization bundle rendered as structured text until this workspace is trusted.'));
  assert(renderer.includes('data-notebook-output-trust'));
  assert(renderer.includes('data-notebook-output-mime'));
  assert(renderer.includes('trust-sensitive'));

  assert(editorCortex.includes('beast_output_summary'));
  assert(editorCortex.includes('output_mime_summary'));
  assert(editorCortex.includes("runtime: 'persistent-jupyter-kernel'"));
  assert(editorCortex.includes("runtime: 'trust-gated-notebook'"));

  const report = {
    ok: true,
    date: '2026-07-31',
    checks: 16,
    mimeTypes: summary.mimeTypes,
    trustedMimeTypes: summary.trustedMimeTypes,
    trustSensitive: summary.trustSensitive,
    widgetPrimary: outputs[0].primary_mime,
  };
  fs.mkdirSync(path.join(repoRoot, 'build'), { recursive: true });
  fs.writeFileSync(
    path.join(repoRoot, 'build', 'NOTEBOOK_WIDGET_STATE_CONTRACT.json'),
    `${JSON.stringify(report, null, 2)}\n`,
    'utf8',
  );
  console.log(JSON.stringify(report, null, 2));
}

main();
