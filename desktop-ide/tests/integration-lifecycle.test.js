'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const renderer = path.resolve(__dirname, '../renderer/js');

function harness() {
  const state = {
    integrations: {
      capabilities: [],
      lifecycleEvents: []
    }
  };

  const store = {
    get: () => state,
    transaction(fn) {
      fn(state);
    },
    patch(key, value) {
      Object.assign(state[key], value);
    },
    set(key, value) {
      state[key] = value;
    },
    subscribe() {
      return () => {};
    }
  };

  const context = {
    window: {},
    BeastStore: store,
    BeastDesktopBridge: {
      demoMode: true,
      workspaceRoot: ''
    },
    BeastRouter: {},
    URLSearchParams,
    Date,
    console
  };

  vm.createContext(context);

  const source = fs.readFileSync(
    path.join(renderer, 'beast-integration-map.js'),
    'utf8'
  );

  vm.runInContext(source, context);

  return {
    state,
    api: context.window.BeastIntegrationMap
  };
}

test('eligibility never implies committed effect', () => {
  const { api } = harness();

  const receipt = api.recordLifecycleEvent({
    capability: 'crystal_bus',
    status: 'fired',
    stage: 'eligibility',
    operation: 'transfer_preflight',
    effect_committed: false,
    run_id: 'run-1',
    sequence: 10
  });

  assert.equal(receipt.status, 'fired');
  assert.equal(receipt.stage, 'eligibility');
  assert.equal(receipt.effectCommitted, false);
  assert.equal(receipt.durabilityVerified, false);
});

test('producer commit assertion is not independent verification', () => {
  const { api } = harness();

  const receipt = api.recordLifecycleEvent({
    capability: 'memory_hull.seal',
    status: 'fired',
    stage: 'postflight',
    operation: 'residue_seal',
    effect_committed: true,
    run_id: 'run-1',
    sequence: 11
  });

  assert.equal(receipt.effectCommitted, true);
  assert.equal(receipt.durabilityVerified, false);
});

test('durable SSE replay does not duplicate receipts', () => {
  const { api, state } = harness();

  const event = {
    capability: 'vector_rag',
    status: 'fired',
    stage: 'execution',
    operation: 'advisory_retrieval',
    run_id: 'run-1',
    sequence: 42
  };

  assert.ok(api.recordLifecycleEvent(event));
  assert.equal(api.recordLifecycleEvent(event), null);
  assert.equal(state.integrations.lifecycleEvents.length, 1);
});

test('different durable sequences remain distinct', () => {
  const { api, state } = harness();

  for (const sequence of [42, 43]) {
    api.recordLifecycleEvent({
      capability: 'vector_rag',
      status: 'fired',
      run_id: 'run-1',
      sequence
    });
  }

  assert.equal(state.integrations.lifecycleEvents.length, 2);
});

test('identical sequences from different runs remain distinct', () => {
  const { api, state } = harness();

  for (const run_id of ['run-1', 'run-2']) {
    api.recordLifecycleEvent({
      capability: 'vector_rag',
      status: 'fired',
      run_id,
      sequence: 42
    });
  }

  assert.equal(state.integrations.lifecycleEvents.length, 2);
});

test('lifecycle storage remains bounded', () => {
  const { api, state } = harness();

  for (let sequence = 1; sequence <= 150; sequence++) {
    api.recordLifecycleEvent({
      capability: 'vector_rag',
      status: 'fired',
      run_id: 'run-1',
      sequence
    });
  }

  assert.equal(state.integrations.lifecycleEvents.length, 100);
  assert.equal(state.integrations.lifecycleEvents[0].sequence, 51);
});

test('invalid capabilities are not recorded', () => {
  const { api, state } = harness();

  assert.equal(api.recordLifecycleEvent({ status: 'fired' }), null);
  assert.equal(state.integrations.lifecycleEvents.length, 0);
});

test('replay outside the 100-receipt display buffer is rejected', () => {
  const { api, state } = harness();

  for (let sequence = 1; sequence <= 150; sequence++) {
    api.recordLifecycleEvent({
      capability: 'vector_rag',
      status: 'fired',
      run_id: 'run-eviction',
      sequence
    });
  }

  assert.equal(state.integrations.lifecycleEvents.length, 100);

  const replay = api.recordLifecycleEvent({
    capability: 'vector_rag',
    status: 'fired',
    run_id: 'run-eviction',
    sequence: 20
  });

  assert.equal(replay, null);
  assert.equal(state.integrations.lifecycleEvents.length, 100);
});

test('replay beyond the retained identity horizon is rejected', () => {
  const { api, state } = harness();

  for (let sequence = 1; sequence <= 4200; sequence++) {
    api.recordLifecycleEvent({
      capability: 'vector_rag',
      status: 'fired',
      run_id: 'run-long',
      sequence
    });
  }

  const before = state.integrations.lifecycleEvents.length;

  const replay = api.recordLifecycleEvent({
    capability: 'vector_rag',
    status: 'fired',
    run_id: 'run-long',
    sequence: 1
  });

  assert.equal(replay, null);
  assert.equal(state.integrations.lifecycleEvents.length, before);
});

test('out-of-order events inside the replay window remain valid', () => {
  const { api, state } = harness();

  for (const sequence of [100, 102, 101]) {
    const receipt = api.recordLifecycleEvent({
      capability: 'vector_rag',
      status: 'fired',
      run_id: 'run-reordered',
      sequence
    });

    assert.ok(receipt);
  }

  assert.equal(state.integrations.lifecycleEvents.length, 3);
});

test('clear resets display history and replay identity', () => {
  const { api, state } = harness();

  const event = {
    capability: 'crystal_bus',
    status: 'fired',
    stage: 'eligibility',
    effect_committed: false,
    run_id: 'run-reset',
    sequence: 7
  };

  assert.ok(api.recordLifecycleEvent(event));
  assert.equal(api.recordLifecycleEvent(event), null);

  api.clear();

  assert.equal(state.integrations.lifecycleEvents.length, 0);
  assert.ok(api.recordLifecycleEvent(event));
  assert.equal(state.integrations.lifecycleEvents.length, 1);
});

test('same sequence in separate runs remains independent', () => {
  const { api, state } = harness();

  for (const run_id of ['run-alpha', 'run-beta']) {
    assert.ok(api.recordLifecycleEvent({
      capability: 'memory_hull.recall',
      status: 'fired',
      run_id,
      sequence: 25
    }));
  }

  assert.equal(state.integrations.lifecycleEvents.length, 2);
});
