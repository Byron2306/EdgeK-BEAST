(() => {
  'use strict';

  const STEP_ORDER = ['lease','arda','capability','policy','postcondition','receipt'];
  const ROUTE_STATES = {
    workspace:'coding', agents:'coding', source:'verifying', testing:'verifying', review:'verifying',
    trust:'guarding', evidence:'verifying', 'grand-closure':'sealing', crystallization:'sealing',
    'live-fabric':'observing', 'compute-fabric':'routing', models:'routing', providers:'routing',
    terminal:'working', deploy:'guarding', doctor:'observing', system:'observing'
  };
  const MASCOT_FRAME_STATES = { coding:'working', working:'working', verifying:'working', observing:'working', routing:'working', guarding:'alert', refusal:'alert', pressure:'alert', sealing:'finished', rollback:'finished', complete:'finished', idle:'idle' };
  let proofTimer = 0;
  let lastState = null;

  const text = value => String(value ?? '').trim();
  const normalize = value => text(value).toLowerCase();
  const truthy = value => value === true || ['true','pass','passed','ok','valid','validated','verified','active','allowed','authorized','consumed','sealed','complete','completed'].includes(normalize(value));
  const falsey = value => value === false || ['false','fail','failed','invalid','refused','denied','blocked','error','revoked'].includes(normalize(value));

  function setDensity(mode, persist=true) {
    const allowed = ['comfortable','compact','focus'];
    const next = allowed.includes(mode) ? mode : 'comfortable';
    const shell = document.querySelector('.beast-shell');
    if (!shell) return;
    shell.dataset.density = next;
    document.body.dataset.density = next;
    const select = document.getElementById('beastDensityMode');
    if (select && select.value !== next) select.value = next;
    if (persist) localStorage.setItem('beast.phaseD.density', next);
    document.dispatchEvent(new CustomEvent('beast:layout-density', { detail:{ density:next } }));
  }

  function setOperationalMascot(state, detail='') {
    const next = state || 'idle';
    const mascot = document.getElementById('beastMascot');
    if (mascot) {
      mascot.dataset.operationalState = next;
      mascot.title = `BEAST · ${next}${detail ? ` · ${detail}` : ''}`;
    }
    document.body.dataset.beastOperationalState = next;
    window.setTimeout(() => window.BeastMascot?.setState?.(MASCOT_FRAME_STATES[next] || 'idle'), 0);
  }

  function proofValue(source, keys) {
    for (const key of keys) {
      const path = key.split('.');
      let value = source;
      for (const part of path) value = value && typeof value === 'object' ? value[part] : undefined;
      if (value !== undefined && value !== null && value !== '') return value;
    }
    return undefined;
  }

  function deriveProof(state={}) {
    const op = state.proofChain || state.activeProof || state.operationProof || state.governance?.activeProof || {};
    const lifecycle = state.sourcePlan?.lifecycle || {};
    const trust = state.trust || {};
    const receipt = state.evidence?.latestReceipt || state.evidence?.pack?.receipt || op.receipt;
    const source = { ...op,
      lease: proofValue(op,['lease','process_lease','processLease']) ?? proofValue(state,['processLease.status','chronicle.processLease.status']),
      arda: proofValue(op,['arda','arda_result','ardaResult']) ?? proofValue(state,['arda.status','trust.arda']),
      capability: proofValue(op,['capability','capability_lease','capabilityLease']) ?? proofValue(lifecycle,['capability.status','action_contract.capability']),
      policy: proofValue(op,['policy','policy_result','policyResult']) ?? trust.status,
      postcondition: proofValue(op,['postcondition','postcondition_result','postconditionResult']) ?? proofValue(lifecycle,['postcondition.status','verification.status']),
      receipt: receipt ? 'sealed' : proofValue(op,['receipt_status','receiptStatus'])
    };
    const active = Boolean(op.active || op.operation_id || op.operationId || lifecycle.applying || normalize(state.sourcePlan?.status).includes('apply'));
    const refused = Boolean(op.refused || op.denied || falsey(source.arda) || falsey(source.capability) || falsey(source.policy));
    const complete = Boolean(op.complete || op.completed || truthy(source.postcondition) && truthy(source.receipt));
    return { source, active, refused, complete, label:text(op.label || op.operation || op.operation_id || op.operationId || '') };
  }

  function statusOf(value, active=false) {
    if (truthy(value)) return ['pass', text(value).toUpperCase() || 'PASS'];
    if (falsey(value)) return ['fail', text(value).toUpperCase() || 'FAIL'];
    if (active && (value === undefined || value === null || value === '')) return ['pending','PENDING'];
    if (normalize(value).includes('pending') || normalize(value).includes('checking') || normalize(value).includes('running')) return ['pending',text(value).toUpperCase()];
    return ['unknown', value === undefined || value === null || value === '' ? '—' : text(value).toUpperCase()];
  }

  function renderProof(state={}) {
    const bar = document.getElementById('beastProofBar');
    if (!bar) return;
    const proof = deriveProof(state);
    let passed=0, failed=0, pending=0;
    STEP_ORDER.forEach(step => {
      const node = bar.querySelector(`[data-proof-step="${step}"]`);
      if (!node) return;
      const [status,label] = statusOf(proof.source[step], proof.active);
      node.dataset.status = status;
      node.querySelector('em').textContent = label;
      if (status === 'pass') passed += 1;
      if (status === 'fail') failed += 1;
      if (status === 'pending') pending += 1;
    });
    const summary = document.getElementById('beastProofSummary');
    if (proof.refused || failed) {
      bar.dataset.state='refused'; summary.textContent=`REFUSED · ${failed} boundary${failed===1?'':'ies'} held · NO EFFECT`;
      setOperationalMascot('refusal', proof.label || 'authority refused');
    } else if (proof.complete) {
      bar.dataset.state='complete'; summary.textContent=`CLOSED · ${passed}/6 checks proven · receipt sealed`;
      setOperationalMascot('complete', proof.label || 'proof closed');
    } else if (proof.active || pending) {
      bar.dataset.state='active'; summary.textContent=`ACTIVE · ${passed}/6 checks complete${proof.label ? ` · ${proof.label}` : ''}`;
    } else {
      bar.dataset.state='idle'; summary.textContent='IDLE · no consequential action active';
    }
  }

  function operationMascot(detail={}) {
    const tone=normalize(detail.tone); const message=normalize(detail.message);
    if (tone === 'error' || /refus|denied|blocked|fail/.test(message)) return setOperationalMascot('refusal', detail.message);
    if (/rollback|revert|restor/.test(message)) return setOperationalMascot('rollback', detail.message);
    if (/seal|capsule|receipt/.test(message)) return setOperationalMascot('sealing', detail.message);
    if (/verif|test|audit|check/.test(message)) return setOperationalMascot('verifying', detail.message);
    if (/cache hit|prefix|reuse/.test(message)) return setOperationalMascot('routing', detail.message);
    if (/deploy|policy|trust|arda|capability/.test(message)) return setOperationalMascot('guarding', detail.message);
    setOperationalMascot(tone === 'ok' ? 'complete' : 'working', detail.message);
    clearTimeout(proofTimer);
    proofTimer=window.setTimeout(()=>setOperationalMascot(ROUTE_STATES[window.BeastStore?.get?.().route] || 'idle'),2600);
  }

  function bind() {
    const density=document.getElementById('beastDensityMode');
    const saved=localStorage.getItem('beast.phaseD.density') || (window.innerHeight < 800 ? 'compact' : 'comfortable');
    setDensity(saved,false);
    density?.addEventListener('change',event=>setDensity(event.target.value));
    document.addEventListener('keydown',event=>{
      if (event.ctrlKey && event.shiftKey && event.code === 'Period') {
        event.preventDefault(); const modes=['comfortable','compact','focus']; const current=document.querySelector('.beast-shell')?.dataset.density || 'comfortable'; setDensity(modes[(modes.indexOf(current)+1)%modes.length]);
      }
    });
    document.addEventListener('beast:route-start',event=>{
      const route=event.detail?.page || 'studio';
      window.setTimeout(()=>setOperationalMascot(ROUTE_STATES[route] || 'idle',route),0);
    });
    document.addEventListener('beast:operation',event=>operationMascot(event.detail || {}));
    document.addEventListener('beast:proof-update',event=>renderProof({ ...(window.BeastStore?.get?.() || {}), proofChain:event.detail || {} }));
    window.addEventListener('unhandledrejection',()=>setOperationalMascot('refusal','unhandled operation failure'));
    const store=window.BeastStore;
    if (store?.subscribe) store.subscribe(state=>{ lastState=state; renderProof(state); });
    lastState=store?.get?.() || {};
    renderProof(lastState);
    setOperationalMascot(ROUTE_STATES[lastState.route] || 'idle', lastState.route || 'studio');
  }

  window.BeastPhaseD = Object.freeze({ setDensity, setOperationalMascot, renderProof, updateProof:detail=>document.dispatchEvent(new CustomEvent('beast:proof-update',{detail})) });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',bind,{once:true}); else bind();
})();
