'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

function viewHarness() {
  const patches = [];
  const traces = [];
  const context = {
    window: {},
    console,
  };
  vm.createContext(context);
  vm.runInContext(
    fs.readFileSync(path.join(__dirname, '../renderer/js/ai/budget-view.js'), 'utf8'),
    context,
  );
  const view = context.window.BeastAICodingModules.createBudgetView({
    api: {
      patch(value) { patches.push(value); },
      appendTrace(kind, detail) { traces.push({ kind, detail }); },
      persist() {},
    },
    constants: {},
  });
  return { view, patches, traces };
}

test('desktop coder shows natural formation and lattice admission evidence', () => {
  const h = viewHarness();
  h.view.applyCrystal({
    lifecycle: 'formed',
    crystal_id: 'coding-crystal:real',
    heldout_successes: 3,
    heldout_attempts: 3,
    lattice_admitted: true,
  });

  assert.equal(h.patches[0].crystal.status, 'formed');
  assert.equal(h.patches[0].crystal.crystalId, 'coding-crystal:real');
  assert.equal(h.patches[0].crystal.latticeAdmitted, true);
  assert.match(h.traces[0].detail, /3\/3 held-outs · lattice admitted/);
});

test('desktop coder distinguishes zero-inference reuse and credited reduction', () => {
  const h = viewHarness();
  h.view.applyCrystal({ lifecycle: 'reused', crystal_id: 'coding-crystal:real' });
  h.view.applyCrystal({ lifecycle: 'credited', crystal_id: 'coding-crystal:real' });

  assert.equal(h.patches[0].crystal.reused, true);
  assert.equal(h.patches[1].crystal.status, 'credited');
  assert.match(h.traces[1].detail, /reduction credited/);
});
