const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const jsRoot = path.join(__dirname, '..', 'renderer', 'js');
function load(file, context) {
  vm.runInContext(fs.readFileSync(path.join(jsRoot, file), 'utf8'), context, { filename: file });
}

test('restored evidence pages receive the phase projection from the live gateway contract', async () => {
  const state = { connection: { gatewayUrl: 'http://127.0.0.1:8101' }, workspace: { root: '/workspace' }, platform: {}, computeFabric: {}, liveFabric: {}, reality: {}, grandClosure: {}, system: {} };
  const phase = {
    source: 'repository_evidence',
    computeFabric: { selectedRoute: 'prefix_replay', routes: { prefix_replay: { eligible: true } } },
    liveFabric: { bpf: { ready: true, live: null } },
    reality: { bpf: { installed: true, live: null } },
    grandClosure: { gates: { G9: { validated: true, merkle_root: 'sha256:proof' } } },
  };
  const requested = [];
  const context = vm.createContext({
    window: { BeastUtilityOrchestrationBridge: { ensureState() {} } }, URLSearchParams,
    BeastStore: { get: () => state, patch: (key, value) => Object.assign(state[key] ||= {}, value) },
    BeastRuntime: {
      setGatewayUrl() {},
      async request(url) {
        requested.push(url);
        if (url.startsWith('/edgek/platform/snapshot')) return { status: 'healthy', snapshots: { system: { status: 'healthy' } } };
        if (url === '/edgek/ide/phase-evidence') return phase;
        throw Error(`Unexpected route ${url}`);
      },
    },
  });
  load('beast-restored-route-bridge.js', context);
  await context.window.BeastUtilityOrchestrationBridge.refreshPlatform();
  assert.equal(state.computeFabric.selectedRoute, 'prefix_replay');
  assert.equal(state.liveFabric.bpf.ready, true);
  assert.equal(state.reality.bpf.installed, true);
  assert.equal(state.grandClosure.gates.G9.merkle_root, 'sha256:proof');
  assert.ok(requested.includes('/edgek/ide/phase-evidence'));
});

test('memory refresh accepts nullable and path-only truth stores without invented records', async () => {
  const state = { workspace: { root: '/workspace' }, memory: { security: {} } };
  const context = vm.createContext({
    window: {}, URLSearchParams, Date,
    BeastStore: { get: () => state, patch: (key, value) => Object.assign(state[key] ||= {}, value), addLedger() {} },
    BeastDesktopBridge: {
      demoMode: false,
      async fetchJson(url) {
        if (url.startsWith('/edgek/memory/stack')) return {
          layers: { L0: { name: 'Meta Rules', scope: 'Governance', status: 'active' } },
          truth_stores: ['policies/default.yaml', null], retrieval_views: ['workspace graph'],
        };
        return {};
      },
    },
  });
  load('beast-trust-memory-bridge.js', context);
  const result = await context.window.BeastTrustMemoryBridge.refreshMemory();
  assert.equal(result.error, '');
  assert.equal(result.truthStores.length, 1);
  assert.equal(result.truthStores[0].label, 'policies/default.yaml');
  assert.equal(result.layers[0].records, 0);
  assert.equal(result.recallResults.length, 0);
});

test('failed route render can be retried from the same navigation item', async () => {
  let attempts = 0;
  const context = vm.createContext({
    window: { BeastRenderScheduler: { async request() { if (++attempts === 1) throw Error('render failed'); } } },
    document: { body: { dataset: {} }, querySelectorAll: () => [], dispatchEvent() {} },
    CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
  });
  load('beast-router.js', context);
  context.window.BeastRouter.register('mission', () => {});
  await assert.rejects(context.window.BeastRouter.navigate('mission'), /render failed/);
  await context.window.BeastRouter.navigate('mission');
  assert.equal(attempts, 2);
  assert.equal(context.window.BeastRouter.active, 'mission');
});

test('renderer without desktop preload reaches the configured local gateway', async () => {
  const requested = [];
  const context = vm.createContext({
    window: { setTimeout, clearTimeout },
    location: { search: '' },
    localStorage: { getItem: () => null },
    structuredClone, URL, URLSearchParams, AbortController,
    fetch: async url => {
      requested.push(String(url));
      if (String(url) !== 'http://127.0.0.1:8101/health') throw Error('Wrong gateway');
      return { ok: true, json: async () => ({ status: 'healthy' }) };
    },
  });
  load('beast-store.js', context);
  context.BeastStore = context.window.BeastStore;
  load('beast-desktop-bridge.js', context);
  const health = await context.window.BeastDesktopBridge.fetchJson('/health');
  assert.equal(health.status, 'healthy');
  assert.deepEqual(requested, ['http://127.0.0.1:8101/health']);
});
