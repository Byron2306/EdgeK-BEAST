'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const repositoryRoot = path.resolve(__dirname, '..');
const renderer = path.join(repositoryRoot, 'renderer/js');
const clientSource = fs.readFileSync(
  path.join(renderer, 'ai/agent-client.js'), 'utf8');

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

// Extract a single production listener body by event name. Listeners in the
// live streaming block are indented by six spaces and terminated with "});".
function extractListener(eventName) {
  const marker =
    `eventSource.addEventListener('${eventName}', event => {`;
  const start = clientSource.indexOf(marker);

  assert.ok(start >= 0, `Listener not found: ${eventName}`);

  const next = clientSource.indexOf(
    '\n      eventSource.addEventListener(', start + marker.length);
  const end = next < 0 ? clientSource.length : next;
  const body = clientSource.slice(start, end);
  const closing = body.lastIndexOf('});');

  assert.ok(closing >= 0, `Listener boundary missing: ${eventName}`);

  return body.slice(0, closing + 3);
}

function harness(listenerSource) {
  const state = {
    integrations: {
      capabilities: [],
      lifecycleEvents: []
    },
    aiCoding: {
      activeRunId: '',
      activeRunSequence: 0,
      contextFiles: [],
      error: '',
      messages: [{
        id: 'assistant-1',
        role: 'assistant',
        content: '',
        streaming: false,
        activity: '',
        progress: [],
        turns: []
      }],
      mode: 'agent',
      sourcePlanReady: false,
      streaming: false,
      trace: []
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

  const listeners = new Map();
  const traces = [];

  const eventSource = {
    addEventListener(type, fn) {
      listeners.set(type, fn);
    }
  };

  const runtime = {
    streamState: {
      stream: eventSource,
      runId: 'run-003b',
      sequence: 0
    },
    api: {
      appendTurn() {},
      persist() {},
      patch(partial) {
        if (partial && typeof partial === 'object') {
          Object.assign(state, partial);
        }
      },
      updateProgress() {},
      updateAssistant() {},
      eventPayload(event) {
        const parsed = JSON.parse(event.data || '{}');
        const payload = parsed && typeof parsed.payload === 'object'
          ? parsed.payload
          : parsed;
        const sequence = Number(event.lastEventId || 0);
        if (Number.isFinite(sequence) && sequence > runtime.streamState.sequence) {
          runtime.streamState.sequence = sequence;
          state.aiCoding.activeRunSequence = sequence;
        }
        return payload;
      },
      armWatchdog() {},
      clearWatchdog() {},
      normalizeContextFiles: value => value,
      handlePermissionRequest() {},
      fail() {}
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
    console,
    runtime,
    eventSource,
    traces,
    assistantId: 'assistant-1',
    appendTurn: runtime.api.appendTurn,
    appendTrace(type, message) {
      traces.push({ type, message });
    },
    eventPayload(event) {
      if (runtime.api.eventPayload) {
        return runtime.api.eventPayload(event);
      }
      const sequence = Number(event.lastEventId);
      if (Number.isSafeInteger(sequence) && sequence > 0) {
        runtime.streamState.sequence = sequence;
      }
      try {
        const parsed = JSON.parse(event.data || '{}');
        return parsed && typeof parsed.payload === 'object'
          ? parsed.payload
          : parsed;
      } catch (_) {
        return {};
      }
    },
    updateProgress: runtime.api.updateProgress,
    armWatchdog: runtime.api.armWatchdog,
    clearWatchdog: runtime.api.clearWatchdog,
    handlePermissionRequest: runtime.api.handlePermissionRequest,
    normalizeContextFiles: runtime.api.normalizeContextFiles,
    fail: runtime.api.fail,
    updateAssistant: runtime.api.updateAssistant,
    patch: runtime.api.patch,
    persist: runtime.api.persist,
    mergeAssistantPlanState() {},
    mergeAssistantRoute() {},
    stageSourcePlan() {
      return { ready: true, operations: [{ path: 'a.py', operation: 'edit' }] };
    },
    proposalSummary() {
      return 'Changes ready for review';
    }
  };

  vm.createContext(context);
  vm.runInContext(
    fs.readFileSync(
      path.join(renderer, 'beast-integration-map.js'),
      'utf8'
    ),
    context
  );
  vm.runInContext(listenerSource, context);
  for (const extra of [
    extraToolListener,
    extraStageListener,
    extraValidationListener,
    extraSourcePlanListener,
    extraInterceptionListener
  ]) {
    vm.runInContext(extra, context);
  }

  const dispatch = (
    sequence,
    payload,
    override = {},
    eventName = 'agent_run_integration'
  ) => {
    const event = {
      lastEventId: String(sequence),
      data: JSON.stringify({ payload }),
      ...override
    };

    const handler = listeners.get(eventName);
    assert.ok(handler, `listener not registered: ${eventName}`);
    handler(event);
  };

  return {
    state,
    runtime,
    traces,
    dispatch,
    eventSource,
    get cursorCalls() {
      return traces.filter(
        item => item.type === 'integration'
          && !String(item.message).startsWith('Rejected')
      ).length;
    }
  };
}

// Test data - SSE events matching the doc requirements
const validIntegration = {
  capability: 'vector_rag',
  status: 'fired',
  stage: 'execution',
  operation: 'advisory_retrieval',
  effect_committed: false,
  run_id: 'run-003b'
};

const validIntegrationCompression = {
  capability: 'compression.longcodezip',
  status: 'fired',
  stage: 'execution',
  operation: 'compression',
  effect_committed: false,
  run_id: 'run-003b'
};

const validIntegrationKV = {
  capability: 'kv_transport',
  status: 'fired',
  stage: 'execution',
  operation: 'prefix_reuse_lookup',
  effect_committed: false,
  run_id: 'run-003b',
  artifacts: { provenance: 'synthetic_fixture' }
};

const validIntegrationSwarm = {
  capability: 'swarm_specialist',
  status: 'fired',
  stage: 'specialist_dispatch',
  operation: 'specialist_dispatch',
  effect_committed: false,
  run_id: 'run-003b'
};

const validIntegrationInterception = {
  capability: 'stream_interception',
  status: 'fired',
  stage: 'interception',
  operation: 'stream_observation',
  upstream_cancel_requested: false,
  run_id: 'run-003b',
  tokens_emitted: 150,
  savings: { saved_tokens: 25 }
};

const validToolCall = {
  type: 'tool_call',
  phase: 'tool',
  tool: 'BEAST governed tool',
  text: 'Using repository tool',
  status: 'active',
  authority: 'read-only/governed'
};

const validVerification = {
  status: 'passed',
  repair: false
};

const validSourcePlan = {
  plan_id: 'candidate-promotion-engine-001',
  status: 'draft',
  operations: [
    { path: 'app/kernel/agents/promotion_engine.py', operation: 'edit' }
  ],
  requires_operator_translation: false
};

const validRunDone = {
  status: 'complete'
};

const validRunStage = {
  text: 'typed_planner_v1 · inspect_plan_dispatch',
  status: 'active'
};

const validRunInterception = {
  stop_reason: 'stream_observed',
  tokens_emitted: 200,
  savings: { saved_tokens: 40 }
};

const listenerSource = extractListeners()[0];
const extraToolListener = extractListener('agent_run_tool');
const extraStageListener = extractListener('agent_run_stage');
const extraValidationListener = extractListener('agent_run_validation');
const extraSourcePlanListener = extractListener('agent_run_sourceplan');
const extraInterceptionListener = extractListener('agent_run_interception');

let passedTests = 0;
let failedTests = 0;

function runTest(name, fn) {
  try {
    fn();
    passedTests++;
    console.log(`  PASS: ${name}`);
  } catch (e) {
    failedTests++;
    console.log(`  FAIL: ${name} - ${e.message}`);
  }
}

console.log('=== IDE Acceptance Test: Advanced Runtime ===\n');

// 1. fresh: valid SSE receipt is accepted
runTest('fresh: valid SSE receipt is accepted', () => {
  const h = harness(listenerSource);
  h.dispatch(10, validIntegration);
  assert.equal(h.state.integrations.lifecycleEvents.length, 1);
  assert.equal(h.runtime.streamState.sequence, 10);
  assert.equal(h.cursorCalls, 1);
});

// 2. fresh: duplicate replay is rejected
runTest('fresh: duplicate replay is rejected', () => {
  const h = harness(listenerSource);
  h.dispatch(10, validIntegration);
  h.dispatch(10, validIntegration);
  assert.equal(h.state.integrations.lifecycleEvents.length, 1);
  assert.equal(h.cursorCalls, 1);
});

// 3. fresh: invalid sequence is rejected
runTest('fresh: invalid sequence is rejected', () => {
  const h = harness(listenerSource);
  h.dispatch(0, validIntegration);
  h.dispatch(-1, validIntegration);
  h.dispatch('not-a-number', validIntegration);
  assert.equal(h.state.integrations.lifecycleEvents.length, 0);
  assert.equal(h.cursorCalls, 0);
});

// 4. fresh: malformed JSON is rejected
runTest('fresh: malformed JSON is rejected', () => {
  const h = harness(listenerSource);
  h.dispatch(12, validIntegration, { data: '{invalid-json' });
  assert.equal(h.state.integrations.lifecycleEvents.length, 0);
  assert.equal(h.runtime.streamState.sequence, 0);
  assert.equal(h.cursorCalls, 0);
  assert.ok(h.traces.some(
    item => item.message.includes('malformed SSE JSON')
  ));
});

// 5. fresh: run mismatch is rejected
runTest('fresh: run mismatch is rejected', () => {
  const h = harness(listenerSource);
  h.dispatch(13, {
    ...validIntegration,
    run_id: 'another-run'
  });
  assert.equal(h.state.integrations.lifecycleEvents.length, 0);
  assert.equal(h.cursorCalls, 0);
});

// 4. fresh: stale EventSource cannot write
runTest('fresh: stale EventSource cannot write', () => {
  const h = harness(listenerSource);
  h.runtime.streamState.stream = {};
  h.dispatch(14, validIntegration);
  assert.equal(h.state.integrations.lifecycleEvents.length, 0);
  assert.equal(h.cursorCalls, 0);
});

// 5. fresh: absent run identity is rejected
runTest('fresh: absent run identity is rejected', () => {
  const h = harness(listenerSource);
  h.runtime.streamState.runId = '';
  h.dispatch(15, validIntegration);
  assert.equal(h.state.integrations.lifecycleEvents.length, 0);
  assert.equal(h.cursorCalls, 0);
});

// 6. fresh: producer commit remains unverified
runTest('fresh: producer commit remains unverified', () => {
  const h = harness(listenerSource);
  h.dispatch(16, {
    ...validIntegration,
    effect_committed: true
  });
  const receipt = h.state.integrations.lifecycleEvents[0];
  assert.equal(receipt.effectCommitted, true);
  assert.equal(receipt.durabilityVerified, false);
});

// 8b. fresh: integration with compression
runTest('fresh: integration with compression', () => {
  const h = harness(listenerSource);
  h.dispatch(17, validIntegrationCompression);
  assert.equal(h.state.integrations.lifecycleEvents.length, 1);
  // Check for compression-related events
  const compressionEvents = h.state.integrations.lifecycleEvents.filter(
    e => e.operation && e.operation.includes('compression')
  );
  assert.ok(compressionEvents.length > 0, ' compression events should be present');
});

// 9. fresh: integration with KV
runTest('fresh: integration with KV', () => {
  const h = harness(listenerSource);
  h.dispatch(18, validIntegrationKV);
  assert.equal(h.state.integrations.lifecycleEvents.length, 1);
  // Check for KV provenance
  const kvEvent = h.state.integrations.lifecycleEvents[0];
  assert.ok(kvEvent.artifacts && kvEvent.artifacts.provenance, 'KV provenance should be present');
  assert.equal(kvEvent.artifacts.provenance, 'synthetic_fixture', 'KV provenance should be synthetic_fixture');
});

// 10. fresh: integration with swarm
runTest('fresh: integration with swarm', () => {
  const h = harness(listenerSource);
  h.dispatch(19, validIntegrationSwarm);
  assert.equal(h.state.integrations.lifecycleEvents.length, 1);
  // Check for swarm dispatch
  const swarmEvent = h.state.integrations.lifecycleEvents[0];
  assert.ok(swarmEvent.operation && swarmEvent.operation.includes('dispatch'), 'swarm dispatch operation should be present');
});

// 11. fresh: integration with interception
runTest('fresh: integration with interception', () => {
  const h = harness(listenerSource);
  h.dispatch(20, validRunInterception, {}, 'agent_run_interception');
  const interception = h.traces.find(item => item.type === 'interception');
  assert.ok(interception, 'interception trace should be present');
  assert.match(interception.message, /40 saved/);
});

// 12. tool call with Effect TS
runTest('tool call with Effect TS', () => {
  const h = harness(listenerSource);
  h.dispatch(21, {
    ...validToolCall,
    text: 'Using Effect TS repository tool'
  }, {}, 'agent_run_tool');
  const toolEvent = h.traces.find(item => item.type === 'tool');
  assert.ok(toolEvent, 'tool trace should be recorded');
  assert.ok(
    toolEvent.message.includes('Effect TS')
      || toolEvent.message.includes('repository tool'),
    'tool event should mention Effect TS or repository tool'
  );
});

// 13. verification passed
runTest('verification passed', () => {
  const h = harness(listenerSource);
  h.dispatch(22, {
    status: 'passed',
    check_count: 2
  }, {}, 'agent_run_validation');
  const verificationEvent = h.traces.find(
    item => item.type === 'validation'
  );
  assert.ok(verificationEvent, 'validation trace should be recorded');
  assert.ok(
    verificationEvent.message.startsWith('passed'),
    'verification trace should start with passed'
  );
});

// 14. sourcePlanReady and staged proposal
runTest('sourcePlanReady and staged proposal', () => {
  const h = harness(listenerSource);
  h.dispatch(23, {
    plan: validSourcePlan,
    operation_count: validSourcePlan.operations.length
  }, {}, 'agent_run_sourceplan');
  const sourcePlanEvent = h.traces.find(
    item => item.type === 'sourceplan'
  );
  assert.ok(sourcePlanEvent, 'sourceplan trace should be recorded');
  assert.equal(h.state.status, 'ready-to-review');
});

// 15. final status ready-to-review
runTest('final status ready-to-review', () => {
  const h = harness(listenerSource);
  h.dispatch(24, {
    plan: validSourcePlan,
    operation_count: validSourcePlan.operations.length
  }, {}, 'agent_run_sourceplan');
  assert.equal(h.state.aiCoding.mode, 'agent', 'mode should be agent');
  assert.equal(h.state.status, 'ready-to-review', 'status should be ready-to-review');
});

// 16. typed planner trace
runTest('typed planner trace', () => {
  const h = harness(listenerSource);
  h.dispatch(25, {
    ...validRunStage
  }, {}, 'agent_run_stage');
  const stageTraces = h.traces.filter(t => t.type === 'stage');
  assert.ok(stageTraces.length > 0, 'should have stage traces');
  assert.ok(
    stageTraces[0].message.includes('typed planner v1'),
    'stage trace should identify the typed planner'
  );
});

// 17. integration turns for compression, KV, and swarm
runTest('integration turns for compression, KV, and swarm', () => {
  const h = harness(listenerSource);
  h.dispatch(26, validIntegrationCompression);
  h.dispatch(27, validIntegrationKV);
  h.dispatch(28, validIntegrationSwarm);
  assert.ok(h.state.integrations.lifecycleEvents.length >= 3, 'should have at least 3 integration events');
  // Check each type has events
  const compressionEvents = h.state.integrations.lifecycleEvents.filter(
    e => e.operation && e.operation.includes('compression')
  );
  const kvEvents = h.state.integrations.lifecycleEvents.filter(
    e => e.artifacts && e.artifacts.provenance
  );
  const swarmEvents = h.state.integrations.lifecycleEvents.filter(
    e => e.operation && e.operation.includes('dispatch')
  );
  assert.ok(compressionEvents.length > 0, 'compression events should be present');
  assert.ok(kvEvents.length > 0, 'KV events should be present');
  assert.ok(swarmEvents.length > 0, 'swarm dispatch events should be present');
});

// 18. stream interception turn with saved-token detail
runTest('stream interception turn with saved-token detail', () => {
  const h = harness(listenerSource);
  h.dispatch(29, validRunInterception, {}, 'agent_run_interception');
  const interception = h.traces.find(item => item.type === 'interception');
  assert.ok(interception, 'interception trace should be present');
  assert.match(interception.message, /40 saved/);
});

// 19. review status ready-to-review
runTest('review status ready-to-review', () => {
  const h = harness(listenerSource);
  h.dispatch(30, {
    plan: validSourcePlan,
    operation_count: validSourcePlan.operations.length
  }, {}, 'agent_run_sourceplan');
  h.dispatch(31, validRunStage, {}, 'agent_run_stage');
  // Check that state reflects ready-to-review
  assert.equal(
    h.state.status,
    'ready-to-review',
    'review status should be ready-to-review'
  );
});

console.log(`\n=== Results: ${passedTests} passed, ${failedTests} failed ===`);
if (failedTests === 0) {
  console.log('ALL IDE ACCEPTANCE TESTS PASSED');
} else {
  console.log('SOME IDE ACCEPTANCE TESTS FAILED');
  process.exitCode = 1;
}
