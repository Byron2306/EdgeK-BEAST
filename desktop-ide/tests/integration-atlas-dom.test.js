'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const source = fs.readFileSync(
  path.resolve(__dirname, '../renderer/js/pages/beast-atlas-page.js'),
  'utf8'
);

function element() {
  const children = new Map();

  return {
    innerHTML: '',
    textContent: '',
    className: '',
    hidden: false,
    disabled: false,
    dataset: {},
    attributes: {},

    classList: {
      toggle() {}
    },

    setAttribute(name, value) {
      this.attributes[name] = value;
    },

    append(child) {
      this.appended = child;
    },

    querySelector(selector) {
      if (!children.has(selector)) {
        children.set(selector, element());
      }

      return children.get(selector);
    },

    querySelectorAll() {
      return [];
    },

    addEventListener() {}
  };
}

function harness(initialReceipts = []) {
  const state = {
    integrations: {
      selectedId: '',
      capabilities: [],
      lifecycleEvents: initialReceipts,
      summary: {},
      status: 'loaded',
      loading: false,
      error: ''
    }
  };

  let subscriber = null;
  let unsubscribed = false;

  const store = {
    get() {
      return state;
    },

    subscribe(fn) {
      subscriber = fn;

      return () => {
        unsubscribed = true;
        subscriber = null;
      };
    }
  };

  const context = {
    window: {},
    document: {
      createElement() {
        return element();
      }
    },
    BeastStore: store,
    BeastIntegrationMap: {
      refresh() {
        return Promise.resolve();
      }
    },
    BeastRouter: {
      navigate() {
        return Promise.resolve();
      }
    },
    console
  };

  vm.createContext(context);
  vm.runInContext(source, context);

  const page = context.window.BeastAtlasPage.renderer();

  function update(receipts) {
    state.integrations.lifecycleEvents = receipts;

    if (subscriber) {
      subscriber(state);
    }
  }

  function html() {
    return page.node
      .querySelector('[data-atlas-lifecycle-events]')
      .innerHTML;
  }

  return {
    page,
    state,
    update,
    html,
    get unsubscribed() {
      return unsubscribed;
    }
  };
}

function receipt(sequence, overrides = {}) {
  return {
    capability: `capability_${sequence}`,
    stage: 'execution',
    operation: 'advisory',
    status: 'fired',
    mode: 'governed',
    effectCommitted: false,
    sequence,
    ...overrides
  };
}

test('Atlas exposes lifecycle rendering surface', () => {
  assert.match(source, /data-atlas-lifecycle/);
  assert.match(source, /Agent Integration Lifecycle/);
});

test('empty lifecycle state is rendered', () => {
  const h = harness();

  h.update([]);

  assert.match(
    h.html(),
    /No integration lifecycle receipts observed/
  );
});

test('store update renders lifecycle receipt', () => {
  const h = harness();

  h.update([receipt(1)]);

  assert.match(h.html(), /capability_1/);
  assert.match(h.html(), /execution/);
  assert.match(h.html(), /advisory/);
  assert.match(h.html(), /fired/);
});

test('Atlas displays only latest 30 receipts', () => {
  const h = harness();

  h.update(
    Array.from({ length: 40 }, (_, index) =>
      receipt(index + 1)
    )
  );

  const html = h.html();

  assert.doesNotMatch(html, /capability_1</);
  assert.doesNotMatch(html, /capability_10</);
  assert.match(html, /capability_11</);
  assert.match(html, /capability_40</);
});

test('newest lifecycle receipt appears first', () => {
  const h = harness();

  h.update([
    receipt(1),
    receipt(2),
    receipt(3)
  ]);

  assert.ok(
    h.html().indexOf('capability_3') <
    h.html().indexOf('capability_2')
  );

  assert.ok(
    h.html().indexOf('capability_2') <
    h.html().indexOf('capability_1')
  );
});

test('receipt HTML is escaped', () => {
  const h = harness();

  h.update([
    receipt(1, {
      capability: '<img src=x onerror=alert(1)>',
      stage: '<script>attack()</script>',
      operation: '" onclick="attack()"',
      status: '<b>fired</b>',
      mode: '<svg onload=attack()>'
    })
  ]);

  const html = h.html();

  assert.doesNotMatch(html, /<script>/);
  assert.doesNotMatch(html, /<img/);
  assert.doesNotMatch(html, /<svg/);

  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /&lt;img/);
  assert.match(html, /&lt;svg/);
  assert.match(html, /&quot;/);
});

test('producer commit claim remains explicitly unverified', () => {
  const h = harness();

  h.update([
    receipt(1, {
      effectCommitted: true
    })
  ]);

  assert.match(
    h.html(),
    /COMMIT CLAIMED · NOT INDEPENDENTLY VERIFIED/
  );
});

test('uncommitted receipt cannot claim durability', () => {
  const h = harness();

  h.update([
    receipt(1, {
      effectCommitted: false
    })
  ]);

  assert.match(
    h.html(),
    /NO DURABLE EFFECT PROVEN/
  );

  assert.doesNotMatch(
    h.html(),
    /COMMIT CLAIMED/
  );
});

test('disposed renderer stops responding to store updates', () => {
  const h = harness();

  h.update([receipt(1)]);

  const before = h.html();

  h.page.dispose();

  h.update([receipt(2)]);

  assert.equal(h.html(), before);
  assert.equal(h.unsubscribed, true);
});
