'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const source = fs.readFileSync(
  path.resolve(__dirname, '../renderer/js/ai/agent-events.js'),
  'utf8'
);

function harness() {
  const runtime = {
    streamState: {
      sequence: 5,
      lastCursorPersistAt: 0
    }
  };

  const patches = [];
  let persists = 0;

  const api = {
    persist() {
      persists++;
    }
  };

  const context = {
    runtime,
    api,
    patch(value) {
      patches.push(value);
    },
    now() {
      return 2000;
    },
    JSON,
    Number
  };

  const match = source.match(
    /function eventPayload\(event\) \{[\s\S]*?\n  \}/
  );

  assert.ok(match, 'Production eventPayload helper missing');

  vm.createContext(context);

  vm.runInContext(
    `${match[0]}\nthis.eventPayload = eventPayload;`,
    context
  );

  return {
    runtime,
    patches,
    api,
    eventPayload: context.eventPayload,
    get persists() {
      return persists;
    }
  };
}

test('malformed JSON cannot advance cursor', () => {
  const h = harness();

  assert.throws(() => h.eventPayload({
    lastEventId: '20',
    data: '{malformed'
  }), SyntaxError);

  assert.equal(h.runtime.streamState.sequence, 5);
  assert.equal(h.patches.length, 0);
  assert.equal(h.persists, 0);
});

test('valid payload advances cursor', () => {
  const h = harness();

  const payload = h.eventPayload({
    lastEventId: '20',
    data: JSON.stringify({
      payload: { status: 'fired' }
    })
  });

  assert.equal(payload.status, 'fired');
  assert.equal(h.runtime.streamState.sequence, 20);
  assert.equal(h.patches.length, 1);
  assert.equal(h.patches[0].activeRunSequence, 20);
  assert.equal(h.persists, 1);
});

test('older sequence cannot regress cursor', () => {
  const h = harness();

  h.eventPayload({
    lastEventId: '3',
    data: '{}'
  });

  assert.equal(h.runtime.streamState.sequence, 5);
  assert.equal(h.patches.length, 0);
  assert.equal(h.persists, 0);
});

test('missing sequence does not mutate cursor', () => {
  const h = harness();

  h.eventPayload({
    data: '{}'
  });

  assert.equal(h.runtime.streamState.sequence, 5);
  assert.equal(h.patches.length, 0);
  assert.equal(h.persists, 0);
});
