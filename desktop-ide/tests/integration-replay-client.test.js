'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const vm = require('node:vm');
const { test } = require('node:test');

const repositoryRoot = path.resolve(__dirname, '../..');
const renderer = path.join(repositoryRoot, 'desktop-ide/renderer/js');

function durableLegacyReplay() {
  const workspace = fs.mkdtempSync(
    path.join(os.tmpdir(), 'beast-integration-replay-')
  );
  const python = path.join(repositoryRoot, '.venv/bin/python');
  const program = `
import json
import sys
from pathlib import Path

from app.kernel.agents.run_engine import AgentRunEngine

root = Path(sys.argv[1])
engine = AgentRunEngine(root)
run_id = "integration-client-replay"
engine.create_run(
    session_id="integration-client-session",
    objective="Prove durable integration replay",
    run_id=run_id,
)
for status in ("fired", "skipped", "failed"):
    engine.emit(
        run_id,
        f"agent.integration.{status}",
        {
            "run_id": run_id,
            "session_id": "integration-client-session",
            "capability": "vector_rag",
            "status": status,
            "stage": "execution",
            "operation": "advisory_retrieval",
            "mode": "advisory_retrieval",
            "reason": f"client_replay_{status}",
            "effect_committed": False,
        },
    )

# Reopen the SQLite-backed store and use the production legacy SSE serializer.
reopened = AgentRunEngine(root)
events = [
    event for event in reopened.store.events(run_id)
    if event["event_type"].startswith("agent.integration.")
]
assert len(events) == 3
assert all(not event["legacy_type"] for event in events)
print(json.dumps({
    "run_id": run_id,
    "frames": [reopened.sse_event(event, projection="legacy") for event in events],
}))
`;

  try {
    const result = spawnSync(python, ['-c', program, workspace], {
      cwd: repositoryRoot,
      encoding: 'utf8',
      timeout: 30000
    });

    assert.equal(
      result.status,
      0,
      `Durable backend fixture failed: ${result.stderr || result.stdout}`
    );

    const lines = result.stdout.trim().split('\n');
    return JSON.parse(lines.at(-1));
  } finally {
    fs.rmSync(workspace, { recursive: true, force: true });
  }
}

function parseSseFrame(frame) {
  let lastEventId = '';
  let name = 'message';
  const data = [];

  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith('id:')) lastEventId = line.slice(3).trim();
    if (line.startsWith('event:')) name = line.slice(6).trim();
    if (line.startsWith('data:')) data.push(line.slice(5).trimStart());
  }

  assert.equal(name, 'agent_run_integration');
  assert.match(lastEventId, /^[1-9]\d*$/);
  assert.equal(data.length, 1);
  return { lastEventId, data: data.join('\n') };
}

function clientHarness() {
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
  const eventSource = {
    addEventListener(type, listener) {
      listeners.set(type, listener);
    },
    close() {}
  };

  const runtime = {
    streamState: {
      stream: null,
      runId: '',
      sequence: 0,
      lastCursorPersistAt: 0
    },
    constants: {
      MAX_CONTEXT_FILES: 20,
      RELIABLE_LOCAL_CODER: '',
      RELIABLE_LOCAL_PROFILE: {},
      RELIABLE_PLANNER_PROFILE: {}
    },
    root: () => '/offline-workspace',
    gatewayUrl: () => 'http://beast.offline',
    now: () => 2000,
    stateKey: 'integration-replay-test',
    api: {}
  };

  let persisted = 0;
  let requestedUrl = '';
  const patch = update => Object.assign(state.aiCoding, update);

  const context = {
    BeastStore: store,
    BeastMascot: { setState() {} },
    BeastRuntime: {
      async request() {
        return {
          ok: true,
          run: {
            run_id: runtime.streamState.runId,
            mode: 'agent',
            state: 'executing_tool'
          }
        };
      }
    },
    URLSearchParams,
    console
  };
  context.window = context;
  vm.createContext(context);

  for (const module of [
    'beast-integration-map.js',
    'ai/agent-events.js'
  ]) {
    vm.runInContext(fs.readFileSync(path.join(renderer, module), 'utf8'), context);
  }

  const events = context.BeastAICodingModules.createAgentEvents(runtime);
  const updateAssistant = (id, update) => {
    const message = state.aiCoding.messages.find(item => item.id === id);
    if (message) Object.assign(message, update);
  };
  const addMessage = (role, content, extra = {}) => {
    const id = `message-${state.aiCoding.messages.length + 1}`;
    state.aiCoding.messages.push({ id, role, content, ...extra });
    return id;
  };

  Object.assign(runtime.api, {
    eventPayload: events.eventPayload,
    appendTrace: events.appendTrace,
    addMessage,
    updateAssistant,
    updateProgress() {},
    appendTurn() {},
    patch,
    persist() {
      persisted++;
    },
    armWatchdog() {},
    clearWatchdog() {},
    normalizeContextFiles: value => value,
    handlePermissionRequest() {},
    fail() {}
  });
  runtime.openRunStream = async url => {
    requestedUrl = url;
    return eventSource;
  };

  vm.runInContext(
    fs.readFileSync(path.join(renderer, 'ai/agent-client.js'), 'utf8'),
    context
  );
  const client = context.BeastAICodingModules.createAgentClient(runtime);

  return {
    state,
    runtime,
    client,
    eventSource,
    dispatch(frame) {
      const listener = listeners.get('agent_run_integration');
      assert.equal(typeof listener, 'function');
      listener(parseSseFrame(frame));
    },
    get requestedUrl() {
      return requestedUrl;
    },
    get persisted() {
      return persisted;
    }
  };
}

test('durable canonical integration events reach the instantiated IDE reconnect listener and cursor', async () => {
  const fixture = durableLegacyReplay();
  const h = clientHarness();

  const connected = await h.client.reconnectActiveRun(fixture.run_id, 0);
  assert.equal(connected.ok, true);
  assert.match(h.requestedUrl, /[?&]projection=legacy(?:&|$)/);
  assert.match(h.requestedUrl, /[?&]follow=true(?:&|$)/);
  assert.match(h.requestedUrl, /[?&]after=0(?:&|$)/);
  assert.equal(h.runtime.streamState.stream, h.eventSource);

  for (const frame of fixture.frames) h.dispatch(frame);

  const receipts = h.state.integrations.lifecycleEvents;
  assert.equal(receipts.length, 3);
  assert.deepEqual(
    Array.from(receipts, receipt => receipt.status),
    ['fired', 'skipped', 'failed']
  );
  assert.ok(receipts.every(receipt =>
    receipt.capability === 'vector_rag' &&
    receipt.runId === fixture.run_id &&
    receipt.durabilityVerified === false
  ));

  const finalSequence = Number(parseSseFrame(fixture.frames.at(-1)).lastEventId);
  assert.equal(h.runtime.streamState.sequence, finalSequence);
  assert.equal(h.state.aiCoding.activeRunSequence, finalSequence);
  assert.ok(h.persisted > 0, 'accepted replay must persist the reconnect cursor');

  // The actual listener and real eventPayload helper jointly reject a duplicate
  // without advancing or persisting the cursor a second time.
  const persistedBeforeDuplicate = h.persisted;
  h.dispatch(fixture.frames.at(-1));
  assert.equal(h.state.integrations.lifecycleEvents.length, 3);
  assert.equal(h.runtime.streamState.sequence, finalSequence);
  assert.equal(h.persisted, persistedBeforeDuplicate);

  // A same-stream frame claiming another run is refused before cursor mutation.
  const wrongRun = parseSseFrame(fixture.frames.at(-1));
  const envelope = JSON.parse(wrongRun.data);
  envelope.payload.run_id = 'another-run';
  const wrongRunFrame = `id: ${finalSequence + 1}\n` +
    'event: agent_run_integration\n' +
    `data: ${JSON.stringify(envelope)}\n\n`;
  h.dispatch(wrongRunFrame);
  assert.equal(h.state.integrations.lifecycleEvents.length, 3);
  assert.equal(h.runtime.streamState.sequence, finalSequence);
  assert.equal(h.persisted, persistedBeforeDuplicate);

  // Malformed JSON cannot advance the cursor, even with a newer SSE identity.
  const malformedFrame = `id: ${finalSequence + 2}\n` +
    'event: agent_run_integration\n' +
    'data: {malformed\n\n';
  h.dispatch(malformedFrame);
  assert.equal(h.state.integrations.lifecycleEvents.length, 3);
  assert.equal(h.runtime.streamState.sequence, finalSequence);
  assert.equal(h.persisted, persistedBeforeDuplicate);
});
