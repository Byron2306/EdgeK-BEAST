(() => {
  const bridge = window.BeastUtilityOrchestrationBridge;
  if (!bridge) throw new Error('BEAST utility bridge must load before restored route support.');

  function ensureFabricState() {
    if (typeof bridge.ensureState === 'function') bridge.ensureState();
    const defaults = {
      platform:{loading:false,error:'',diagnosticsError:'',updatedAt:0},
      control:{loading:false,error:'',errors:{},updatedAt:0},
      liveFabric:{events:[],bpf:{},xdp:{},transport:{}},
      computeFabric:{selectedRoute:'',routes:{},decisionTrace:[]},
      reality:{},
      grandClosure:{gates:{}},
      commons:{loading:false,error:'',nodes:[],health:{}},
      sensorium:{authority:'',episodes:{open_missions:{},closed_count:0},recent_events:[]},
      testing:{loading:false,error:'',rows:[]},
    };
    if (typeof BeastStore.transaction === 'function') {
      BeastStore.transaction(next => {
        for (const [key, value] of Object.entries(defaults)) next[key] ||= value;
      });
      return;
    }
    const state = BeastStore.get() || {};
    for (const [key, value] of Object.entries(defaults)) {
      if (typeof BeastStore.patch === 'function') BeastStore.patch(key, state[key] || value);
      else state[key] ||= value;
    }
  }

  function useActiveGateway() {
    const gateway = BeastStore.get().connection.gatewayUrl;
    if (gateway) BeastRuntime.setGatewayUrl(gateway);
  }

  async function refreshPlatform() {
    ensureFabricState();
    useActiveGateway();
    BeastStore.patch('platform', { loading: true, error: '' });
    try {
      const params = new URLSearchParams({
        session_id: 'default',
        limit: '8',
        route_limit: '10',
        event_limit: '8',
        process_limit: '30',
        port_limit: '40',
      });
      const root = BeastStore.get().workspace.root;
      if (root) params.set('root_path', root);
      const [platformResult, evidenceResult] = await Promise.allSettled([
        BeastRuntime.request(`/edgek/platform/snapshot?${params}`, {
          timeoutMs: 7000, attempts: 1, cacheTtl: 0,
        }),
        BeastRuntime.request('/edgek/ide/phase-evidence', {
          timeoutMs: 7000, attempts: 1, cacheTtl: 0,
        }),
      ]);
      if (evidenceResult.status === 'rejected') throw evidenceResult.reason;
      const snapshot = platformResult.status === 'fulfilled' ? platformResult.value : {};
      const evidence = evidenceResult.value || {};
      const snapshots = snapshot?.snapshots || {};
      BeastStore.patch('platform', {
        ...snapshot,
        evidenceSource: evidence.source || 'unreported',
        diagnosticsError: platformResult.status === 'rejected' ? String(platformResult.reason?.message || platformResult.reason) : '',
        loading: false,
        error: '',
        updatedAt: Date.now(),
      });
      for (const [key, camel, snake] of [
        ['computeFabric', 'computeFabric', 'compute_fabric'],
        ['liveFabric', 'liveFabric', 'live_fabric'],
        ['reality', 'reality', 'reality'],
        ['grandClosure', 'grandClosure', 'grand_closure'],
      ]) {
        const projection = evidence[camel] || evidence[snake] || snapshot?.[camel] || snapshot?.[snake] || snapshots[camel] || snapshots[snake];
        if (projection && typeof projection === 'object') BeastStore.patch(key, projection);
      }
      for (const key of ['sensorium', 'providers', 'economy']) {
        if (evidence[key] && typeof evidence[key] === 'object') BeastStore.patch(key, evidence[key]);
      }
      const system = snapshots.system || snapshot?.system;
      if (evidence.system && typeof evidence.system === 'object') BeastStore.patch('system', evidence.system);
      if (system && typeof system === 'object') BeastStore.patch('system', system);
      return snapshot;
    } catch (error) {
      BeastStore.patch('platform', {
        loading: false,
        error: String(error.message || error),
        updatedAt: Date.now(),
      });
      throw error;
    }
  }

  async function refreshControl() {
    ensureFabricState();
    useActiveGateway();
    BeastStore.patch('control', { loading: true, error: '' });
    const contracts = {
      interception: '/edgek/interception/transparent/state',
      reuse: '/edgek/crystal-reuse',
      services: '/edgek/control-plane/services',
      cgroup: '/edgek/control-plane/cgroup-delegation',
      reboot: '/edgek/control-plane/reboot-continuity',
      host: '/edgek/host-enforcement/state',
    };
    const names = Object.keys(contracts);
    const results = await Promise.allSettled(names.map(name => BeastRuntime.request(contracts[name], {
      timeoutMs: 4500,
      attempts: 1,
      cacheTtl: 0,
    })));
    const payload = { loading: false, error: '', errors: {}, updatedAt: Date.now() };
    const response = {};
    results.forEach((result, index) => {
      const name = names[index];
      if (result.status === 'fulfilled') {
        payload[name] = result.value;
        response[name] = result.value;
      } else {
        const message = String(result.reason?.message || result.reason || 'Unavailable');
        payload.errors[name] = message;
        response[name] = {};
      }
    });
    const failures = Object.keys(payload.errors).length;
    if (failures) payload.error = `${failures} control-plane contract${failures === 1 ? '' : 's'} unavailable`;
    BeastStore.patch('control', payload);
    return { ...response, errors: payload.errors };
  }

  ensureFabricState();
  bridge.ensureFabricState = ensureFabricState;
  bridge.refreshPlatform = refreshPlatform;
  bridge.refreshControl = refreshControl;
})();
