(function () {
  'use strict';

  const routeCodes = {
    studio:'SYS_OVERVIEW',workspace:'CODE_WORKBENCH',compatibility:'IDE_PROTOCOL',
    source:'TASK_PIPELINE',mission:'MISSION_CTRL',models:'MODEL_ROUTER',
    'compute-fabric':'COMPUTE_FABRIC','live-fabric':'EVIDENCE_STREAM',
    'compute-control':'RESOURCE_CTRL',agents:'SWARM_MATRIX',review:'REVIEW_GATE',
    trust:'TRUST_KERNEL',memory:'MEMORY_LATTICE',evidence:'EVIDENCE_VAULT',
    'grand-closure':'CLOSURE_CHAIN',crystallization:'CRYSTAL_REACTOR',
    map:'SEMANTIC_MAP',terminal:'TERMINAL_MUX',testing:'TEST_EXPLORER',
    tooling:'SCHEMA_FORGE',doctor:'SYSTEM_DOCTOR',reality:'REALITY_MATRIX',
    providers:'CACHE_ROUTER',system:'RUNTIME_PREC',atlas:'SYSTEMS_ATLAS',
    worktrees:'WORKTREE_MISSIONS',deploy:'RELEASE_FORGE',chronicle:'EVENT_CHRONICLE',
    economy:'TOKEN_ECONOMY',commons:'COMMONS_FORGE',settings:'IDE_CONTROLS'
  };

  function ensureCarrier() {
    const dock = document.querySelector('.beast-command');
    if (!dock || dock.querySelector('.beast-hacker-carrier')) return;
    const carrier = document.createElement('div');
    carrier.className = 'beast-hacker-carrier';
    carrier.setAttribute('aria-hidden', 'true');
    carrier.innerHTML = '<span>RX::LIVE // ENCRYPTED_CARRIER // 0xBEA57</span>';
    dock.prepend(carrier);
  }

  function addressRoute(route) {
    const head = document.querySelector('#beastPageOutlet .beast-page-head');
    if (!head) return;
    const code = routeCodes[route] || String(route || 'UNKNOWN').toUpperCase();
    const address = `[ root@beast :: ${code} ] // ACCESS_GRANTED // LIVE`;
    head.dataset.hackerTitle = address;
    let label = head.querySelector('.beast-hacker-address');
    if (!label) {
      label = document.createElement('div');
      label.className = 'beast-hacker-address';
      label.setAttribute('aria-hidden', 'true');
      head.prepend(label);
    }
    label.textContent = address;
  }

  function pulseRoute(route) {
    document.body.dataset.hackerRoute = route || 'studio';
    addressRoute(route);
    const carrier = document.querySelector('.beast-hacker-carrier span');
    if (carrier) {
      const code = routeCodes[route] || 'SYSTEM';
      carrier.textContent = `RX::${code} // ENCRYPTED_CARRIER // 0xBEA57`;
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    ensureCarrier();
    pulseRoute(document.body.dataset.beastPage || 'studio');
  }, { once:true });
  document.addEventListener('beast:route-complete', event => {
    ensureCarrier();
    pulseRoute(event.detail?.page || 'studio');
  });
})();
