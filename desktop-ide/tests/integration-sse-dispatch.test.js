'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const renderer = path.resolve(__dirname, '../renderer/js');
const clientSource = fs.readFileSync(
  path.join(renderer, 'ai/agent-client.js'), 'utf8'
);

function extractListeners() {
  const marker =
    "eventSource.addEventListener('agent_run_integration', event => {";

  const chunks = clientSource.split(marker);

  assert.equal(chunks.length, 3,
    'Exactly two production integration listeners required');

  return chunks.slice(1).map(chunk => {
    const boundary = chunk.indexOf(
      "eventSource.addEventListener('agent_run_stage'"
    );

    assert.ok(boundary > 0, 'Next listener boundary missing');

    const body = chunk.slice(0, boundary);
    const closing = body.lastIndexOf('});');

    assert.ok(closing >= 0, 'Listener closing boundary missing');

    return marker + body.slice(0, closing + 3);
  });
}

// Proven working harness pattern matching integration-replay-client.test.js
// Key insight: Set up runtime.api with function() {} syntax BEFORE running
// listener source. The listener source does 'const api = runtime.api;'
// then 'api.appendTurn(...)' which requires runtime.api.appendTurn to be
// an own property in the VM context.
function harness(listenerSource) {
  // 1. Create state and store
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

  // 2. Define eventSource that registers listeners
  const listeners = new Map();
  const eventSource = {
    addEventListener(type, fn) {
      listeners.set(type, fn);
    },
    close() {}
  };

  // 3. Set up runtime WITH api using function() {} syntax (CRITICAL for VM context)
  // The listener source does 'const api = runtime.api;' then 'api.appendTurn(...)'
  // Using function() {} ensures appendTurn is an own property that works in VM context
  const runtime = {
    streamState: {
      stream: eventSource,
      runId: 'run-003b',
      sequence: 0
    },
    api: {}
  };

  // CRITICAL: Object.assign with function() {} methods
  // patch must delegate to store.patch so listener modifications to state work
  Object.assign(runtime.api, {
    appendTurn: function() {},
    persist: function() {},
    patch: function(key, value) {
      store.patch(key, value);
    },
    updateProgress: function() {},
    updateAssistant: function() {},
    armWatchdog: function() {},
    clearWatchdog: function() {},
    normalizeContextFiles: function(value) { return value; },
    handlePermissionRequest: function() {},
    fail: function() {}
  });

  // CRITICAL: appendTrace and eventPayload must be in VM context for listener source
  const traces = [];
  const appendTrace = function(type, message) {
    traces.push({ type, message });
  };

  const eventPayload = function(event) {
    const parsed = JSON.parse(event.data || '{}');
    return parsed && typeof parsed.payload === 'object'
      ? parsed.payload
      : parsed;
  };

  // CRITICAL: appendTurn and updateProgress are called directly by listener callback
  // They are defined in createAgentClient's outer scope, not inside the callback
  const appendTurn = function(...args) {
    runtime.api.appendTurn(...args);
  };
  const updateProgress = function(...args) {
    runtime.api.updateProgress(...args);
  };

  // 4. Create VM context with runtime, eventSource, appendTrace, eventPayload as top-level variables
  // assistantId is referenced by the listener source (appendTurn(assistantId, ...))
  const assistantId = 'assistant-1';
  const BeastIntegrationMap = {
    recordLifecycleEvent: function(payload) {
      state.integrations.lifecycleEvents.push(payload);
      runtime.streamState.sequence = payload.sequence || 0;
      return payload;
    }
  };

  const context = {
    window: {
      BeastIntegrationMap: BeastIntegrationMap
    },
    BeastStore: store,
    BeastDesktopBridge: {
      demoMode: true,
      workspaceRoot: ''
    },
    BeastRouter: {},
    URLSearchParams,
    Date,
    console,
    runtime: runtime,
    eventSource: eventSource,
    appendTrace: appendTrace,
    appendTurn: appendTurn,
    updateProgress: updateProgress,
    eventPayload: eventPayload,
    traces: traces,
    assistantId: assistantId
  };

  vm.createContext(context);

  // 5. Run beast-integration-map.js first (establishes BeastAICodingModules etc.)
  vm.runInContext(
    fs.readFileSync(
      path.join(renderer, 'beast-integration-map.js'),
      'utf8'
    ),
    context
  );

  // 6. Run agent-events.js in same context
  vm.runInContext(
    fs.readFileSync(
      path.join(renderer, 'ai/agent-events.js'),
      'utf8'
    ),
    context
  );

  // 7. Run listener source in same context where runtime.api.appendTurn exists
  vm.runInContext(listenerSource, context);

  // 8. Create dispatch function using listeners Map
  const dispatch = (
    sequence,
    payload,
    override = {}
  ) => {
    const event = {
      lastEventId: String(sequence),
      data: JSON.stringify({ payload }),
      ...override
    };

    const fn = listeners.get('agent_run_integration');
    if (fn) {
      fn(event);
    }
  };

  return {
    state,
    runtime,
    traces: context.traces,
    dispatch,
    eventSource,
    get cursorCalls() {
      return context.traces.length;
    }
  };
}

// Test data - valid SSE integration event
const valid = {
  capability: 'vector_rag',
  status: 'fired',
  stage: 'execution',
  operation: 'advisory_retrieval',
  effect_committed: false,
  run_id: 'run-003b'
};

// 16 tests matching the original test structure
let passedTests = 0;
let failedTests = 0;

function runTest(name, fn) {
  try {
    fn();
    passedTests++;
    console.log('  PASS: ' + name);
  } catch (e) {
    failedTests++;
    console.log('  FAIL: ' + name + ' - ' + e.message);
  }
}

console.log('=== IDE Dispatch Test ===\n');

// Extract listeners
const listeners = extractListeners();

// Test 1: fresh: valid SSE receipt is accepted
runTest('fresh: valid SSE receipt is accepted', () => {
  const h = harness(listeners[0]);
  h.dispatch(10, valid);
  assert.equal(h.state.integrations.lifecycleEvents.length, 1);
  assert.equal(h.cursorCalls, 1);
});

// Test 2: fresh: duplicate replay is rejected
runTest('fresh: duplicate replay is rejected', () => {
  const h = harness(listeners[0]);
  h.dispatch(10, valid);
  h.dispatch(10, valid);
  assert.equal(h.state.integrations.lifecycleEvents.length, 1);
  assert.equal(h.cursorCalls, 1);
});

// Test 3: fresh: invalid sequence is rejected
runTest('fresh: invalid sequence is rejected', () => {
  const h = harness(listeners[0]);
  h.dispatch(0, valid);
  h.dispatch(-1, valid);
  h.dispatch('not-a-number', valid);
  assert.equal(h.state.integrations.lifecycleEvents.length, 0);
  assert.equal(h.cursorCalls, 3);
});

// Test 4: fresh: malformed JSON is rejected
runTest('fresh: malformed JSON is rejected', () => {
  const h = harness(listeners[0]);
  h.dispatch(12, valid, { data: '{invalid-json' });
  assert.equal(h.state.integrations.lifecycleEvents.length, 0);
  assert.equal(h.runtime.streamState.sequence, 0);
  assert.equal(h.cursorCalls, 1);
});

// Test 5: fresh: run mismatch is rejected
runTest('fresh: run mismatch is rejected', () => {
  const h = harness(listeners[0]);
  h.dispatch(13, {
    ...valid,
    run_id: 'another-run'
  });
  assert.equal(h.state.integrations.lifecycleEvents.length, 0);
  assert.equal(h.cursorCalls, 1);
});

// Test 6: fresh: stale EventSource cannot write
runTest('fresh: stale EventSource cannot write', () => {
  const h = harness(listeners[0]);
  h.runtime.streamState.stream = {};
  h.dispatch(14, valid);
  assert.equal(h.state.integrations.lifecycleEvents.length, 0);
  assert.equal(h.cursorCalls, 0);
});

// Test 7: fresh: absent run identity is rejected
runTest('fresh: absent run identity is rejected', () => {
  const h = harness(listeners[0]);
  h.runtime.streamState.runId = '';
  h.dispatch(15, valid);
  assert.equal(h.state.integrations.lifecycleEvents.length, 0);
  assert.equal(h.cursorCalls, 0);
});

// Test 8: fresh: producer commit remains unverified
runTest('fresh: producer commit remains unverified', () => {
  const h = harness(listeners[0]);
  h.dispatch(16, {
    ...valid,
    effect_committed: true
  });
  const receipt = h.state.integrations.lifecycleEvents[0];
  assert.equal(receipt.effectCommitted, true);
  assert.equal(receipt.durabilityVerified, false);
});

// Test 9: reconnect: valid SSE receipt is accepted
runTest('reconnect: valid SSE receipt is accepted', () => {
  const h = harness(listeners[1]);
  h.dispatch(10, valid);
  assert.equal(h.state.integrations.lifecycleEvents.length, 1);
  assert.equal(h.cursorCalls, 1);
});

// Test 10: reconnect: duplicate replay is rejected
runTest('reconnect: duplicate replay is rejected', () => {
  const h = harness(listeners[1]);
  h.dispatch(10, valid);
  h.dispatch(10, valid);
  assert.equal(h.state.integrations.lifecycleEvents.length, 1);
  assert.equal(h.cursorCalls, 1);
});

// Test 11: reconnect: invalid sequence is rejected
runTest('reconnect: invalid sequence is rejected', () => {
  const h = harness(listeners[1]);
  h.dispatch(0, valid);
  h.dispatch(-1, valid);
  h.dispatch('not-a-number', valid);
  assert.equal(h.state.integrations.lifecycleEvents.length, 0);
  assert.equal(h.cursorCalls, 3);
});

// Test 12: reconnect: malformed JSON is rejected
runTest('reconnect: malformed JSON is rejected', () => {
  const h = harness(listeners[1]);
  h.dispatch(12, valid, { data: '{invalid-json' });
  assert.equal(h.state.integrations.lifecycleEvents.length, 0);
  assert.equal(h.runtime.streamState.sequence, 0);
  assert.equal(h.cursorCalls, 1);
});

// Test 13: reconnect: run mismatch is rejected
runTest('reconnect: run mismatch is rejected', () => {
  const h = harness(listeners[1]);
  h.dispatch(13, {
    ...valid,
    run_id: 'another-run'
  });
  assert.equal(h.state.integrations.lifecycleEvents.length, 0);
  assert.equal(h.cursorCalls, 1);
});

// Test 14: reconnect: stale EventSource cannot write
runTest('reconnect: stale EventSource cannot write', () => {
  const h = harness(listeners[1]);
  h.runtime.streamState.stream = {};
  h.dispatch(14, valid);
  assert.equal(h.state.integrations.lifecycleEvents.length, 0);
  assert.equal(h.cursorCalls, 0);
});

// Test 15: reconnect: absent run identity is rejected
runTest('reconnect: absent run identity is rejected', () => {
  const h = harness(listeners[1]);
  h.runtime.streamState.runId = '';
  h.dispatch(15, valid);
  assert.equal(h.state.integrations.lifecycleEvents.length, 0);
  assert.equal(h.cursorCalls, 0);
});

// Test 16: reconnect: producer commit remains unverified
runTest('reconnect: producer commit remains unverified', () => {
  const h = harness(listeners[1]);
  h.dispatch(16, {
    ...valid,
    effect_committed: true
  });
  const receipt = h.state.integrations.lifecycleEvents[0];
  assert.equal(receipt.effectCommitted, true);
  assert.equal(receipt.durabilityVerified, false);
});

console.log('\n=== Results: ' + passedTests + ' passed, ' + failedTests + ' failed ===');
if (failedTests === 0) {
  console.log('ALL IDE DISPATCH TESTS PASSED');
} else {
  console.log('SOME IDE DISPATCH TESTS FAILED');
}
