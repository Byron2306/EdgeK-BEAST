// BEAST Pair Programmer renderer module: approval-cards.js
(() => {
  const registry = window.BeastAICodingModules = window.BeastAICodingModules || {};
  registry.createApprovalCards = runtime => {
  const api = runtime.api;

  function renderSafeValue(value) {
    if (value == null) return '';
    if (typeof value === 'string') return value;
    try { return JSON.stringify(value, null, 2); } catch { return String(value); }
  }

  function requestOperatorDecision({ payload, capabilities, durableCard }) {
    return new Promise(resolve => {
      const prior = document.querySelector('[data-beast-approval-dialog]');
      if (prior) prior.remove();
      const esc = window.BeastOperationsConsole?.esc || (value => String(value ?? ''));
      const card = durableCard?.cards?.[0] || durableCard?.items?.[0] || durableCard || {};
      const safeArgs = card.safe_arguments || card.argument_view || payload.safe_arguments || {};
      const files = card.affected_files || payload.paths || capabilities.flatMap(item => item.paths || []);
      const dialog = document.createElement('section');
      dialog.className = 'phase5-approval-dialog';
      dialog.dataset.beastApprovalDialog = 'true';
      dialog.setAttribute('role','alertdialog');
      dialog.setAttribute('aria-modal','true');
      dialog.innerHTML = `<form>
        <header><div><b>${esc(card.summary || 'Governed tool approval')}</b><small>${esc(card.tool_id || capabilities.map(item => item.label || item.id).join(', ') || 'capability request')}</small></div><span class="beast-pill ${String(card.risk_class || '').toLowerCase()}">${esc(card.risk_class || 'UNCLASSIFIED')}</span></header>
        <section class="phase5-approval-grid">
          <div><span>Run / step</span><b>${esc(card.run_id || runtime.streamState.runId || 'current')} · ${esc(card.step_id || 'unspecified')}</b></div>
          <div><span>Permission mode</span><b>${esc(card.permission_mode || BeastStore.get().aiCoding.mode || 'guided')}</b></div>
          <div><span>Target</span><b>${esc(card.target || card.execution_target || 'governed runtime')}</b></div>
          <div><span>Expiry</span><b>${esc(card.approval?.expires_at || card.expires_at || 'one use')}</b></div>
        </section>
        <details open><summary>Safe arguments</summary><pre>${esc(renderSafeValue(safeArgs) || 'No safe argument view supplied.')}</pre></details>
        <details><summary>Affected resources</summary><pre>${esc((files || []).join('\n') || card.command || card.url || 'No affected resources declared.')}</pre></details>
        <p>${esc((card.expected_side_effects || []).join(' · ') || 'Source writes remain behind the SourcePlan promotion boundary.')}</p>
        <footer><button type="button" data-approval-action="reject">Reject</button><button type="button" data-approval-action="replan">Request replan</button><button type="submit">Approve once</button></footer>
      </form>`;
      document.body.append(dialog);
      const close = decision => { dialog.remove(); resolve(decision); };
      dialog.querySelector('[data-approval-action="reject"]').addEventListener('click', () => close('reject'));
      dialog.querySelector('[data-approval-action="replan"]').addEventListener('click', () => close('replan'));
      dialog.querySelector('form').addEventListener('submit', event => { event.preventDefault(); close('approve'); });
      requestAnimationFrame(() => dialog.querySelector('[data-approval-action="reject"]')?.focus());
    });
  }

  async function persistResolution({ payload, capabilities, paths, approved }) {
    const runId = String(runtime.streamState.runId || BeastStore.get().aiCoding.activeRunId || '');
    if (runId && payload.request_id) {
      return BeastRuntime.request(`/edgek/agent-runs/${encodeURIComponent(runId)}/approvals/${encodeURIComponent(payload.request_id)}`, {
        method:'POST', timeoutMs:10000,
        body:{
          root_path:runtime.root(), approved:Boolean(approved), scope:'once',
          capabilities:capabilities.map(item => item.id), paths
        }
      });
    }
    if (!approved) return { ok:true, legacy:true, approved:false };
    return BeastRuntime.request('/edgek/ide/agent-sessions/capabilities/grant', {
      method:'POST', timeoutMs:10000,
      body:{
        root_path:runtime.root(), session_id:payload.session_id, request_id:payload.request_id,
        capabilities:capabilities.map(item => item.id), paths
      }
    });
  }

  async function handlePermissionRequest({ event, assistantId, eventSource }) {
    if (runtime.streamState.stream !== eventSource) return false;
    api.armWatchdog(assistantId, eventSource);
    const payload = api.eventPayload(event);
    const capabilities = Array.isArray(payload.capabilities) ? payload.capabilities : [];
    let durableCard = null;
    const runId = String(runtime.streamState.runId || BeastStore.get().aiCoding.activeRunId || '');
    if (runId && window.BeastOperationsConsole) {
      durableCard = await BeastOperationsConsole.loadSurface('tool-approvals', runId, { limit:50 }).catch(() => null);
    }
    const decision = await requestOperatorDecision({ payload, capabilities, durableCard });
    const approved = decision === 'approve';
    const paths = capabilities.flatMap(item => Array.isArray(item.paths) ? item.paths : []);
    if (decision === 'replan') {
      api.appendTrace('permission', 'Operator requested replanning instead of granting authority.');
      api.appendTurn(assistantId, { type:'permission_request', kind:'permission', text:'Replan requested by operator', state:'failed', authority:'no authority granted' });
      return false;
    }
    try {
      await persistResolution({ payload, capabilities, paths, approved });
      if (!approved) {
        api.appendTrace('permission', 'Agent capability request declined and recorded against the durable run');
        api.appendTurn(assistantId, { type:'permission_request', kind:'permission', text:'Capability request declined', state:'failed', authority:'operator declined' });
        return false;
      }
      api.appendTrace('permission', `Approved ${capabilities.length} governed capability request(s); the resolution is bound to this durable run.`);
      api.appendTurn(assistantId, { type:'permission_request', kind:'permission', text:`Approved ${capabilities.length} governed capability request(s)`, state:'done', authority:'operator approved once' });
      return true;
    } catch (error) {
      api.appendTrace('permission', `Capability decision could not be saved: ${String(error.message || error)}`);
      return false;
    }
  }

    return { handlePermissionRequest };
  };
})();
