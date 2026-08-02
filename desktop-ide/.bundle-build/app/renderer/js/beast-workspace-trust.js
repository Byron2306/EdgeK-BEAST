(() => {
  const MUTATION_SELECTORS = [
    '[data-ai-action="send"]','[data-ai-action="worktree-agent"]','[data-ai-action="sourceplan"]',
    '[data-terminal-action="execute"]','[data-terminal-action="chat-start"]',
    '[data-runtime-action^="notebook-"]','[data-runtime-action^="extension-"]',
    '[data-compat-install-kind]','[data-mission-action="start"]'
  ].join(',');

  let snapshot = { mode: 'restricted', restricted: true, restrictions: [] };
  let disposer = null;

  function ensureBanner() {
    let banner = document.getElementById('beastWorkspaceTrustBar');
    if (banner) return banner;
    banner = document.createElement('section');
    banner.id = 'beastWorkspaceTrustBar';
    banner.className = 'beast-workspace-trust-bar restricted';
    banner.setAttribute('role', 'status');
    banner.setAttribute('aria-live', 'polite');
    banner.innerHTML = `<span class="trust-mark">◆</span><div><b data-workspace-trust-label>RESTRICTED MODE</b><small data-workspace-trust-detail>Executable workspace features are disabled until explicitly trusted.</small></div><button type="button" data-workspace-trust-action="toggle">Trust Workspace</button>`;
    const shell = document.querySelector('.beast-shell') || document.body;
    shell.prepend(banner);
    banner.addEventListener('click', async event => {
      const action = event.target.closest('[data-workspace-trust-action]')?.dataset.workspaceTrustAction;
      if (action !== 'toggle') return;
      const next = snapshot.restricted ? 'trusted' : 'restricted';
      const reason = next === 'trusted' ? 'Explicit operator trust decision from BEAST workbench.' : 'Operator returned workspace to restricted mode.';
      try {
        const value = await window.beastDesktop?.setWorkspaceTrust?.({ mode: next, reason });
        if (value) apply(value);
      } catch (error) {
        banner.querySelector('[data-workspace-trust-detail]').textContent = String(error.message || error);
      }
    });
    return banner;
  }

  function patchStore(value) {
    try {
      const trust = BeastStore.get().trust || {};
      BeastStore.patch('trust', { ...trust, workspaceTrust: value, boundary: { ...(trust.boundary || {}), mode: value.restricted ? 'Restricted' : 'Trusted' } });
    } catch (_) {}
  }

  function gateDom() {
    document.documentElement.dataset.workspaceTrust = snapshot.mode;
    document.querySelectorAll(MUTATION_SELECTORS).forEach(button => {
      if (snapshot.restricted) {
        button.dataset.trustDisabled = 'true';
        button.disabled = true;
        button.title = 'Disabled by BEAST Workspace Trust restricted mode.';
      } else if (button.dataset.trustDisabled === 'true') {
        delete button.dataset.trustDisabled;
        button.disabled = false;
        if (button.title === 'Disabled by BEAST Workspace Trust restricted mode.') button.removeAttribute('title');
      }
    });
  }

  function apply(value = {}) {
    snapshot = { ...snapshot, ...value, restricted: value.mode !== 'trusted' };
    const banner = ensureBanner();
    banner.classList.toggle('restricted', snapshot.restricted);
    banner.classList.toggle('trusted', !snapshot.restricted);
    banner.querySelector('[data-workspace-trust-label]').textContent = snapshot.restricted ? 'RESTRICTED MODE' : 'WORKSPACE TRUSTED';
    banner.querySelector('[data-workspace-trust-detail]').textContent = snapshot.restricted
      ? 'Agents, terminals, tasks, debugging, notebooks, executable extensions, workspace settings, hooks, and source mutation are disabled.'
      : 'Executable workspace features are enabled and remain governed by normal BEAST policy.';
    banner.querySelector('[data-workspace-trust-action]').textContent = snapshot.restricted ? 'Trust Workspace' : 'Restrict Workspace';
    patchStore(snapshot);
    gateDom();
    window.dispatchEvent(new CustomEvent('beast-workspace-trust-changed', { detail: snapshot }));
  }

  async function refresh() {
    try {
      const value = await window.beastDesktop?.workspaceTrust?.({});
      if (value) apply(value);
    } catch (_) { apply(snapshot); }
  }

  const observer = new MutationObserver(() => gateDom());
  function start() {
    ensureBanner();
    observer.observe(document.body, { childList: true, subtree: true });
    refresh();
    disposer = window.beastDesktop?.onWorkspaceTrustChanged?.(apply) || null;
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true }); else start();

  window.BeastWorkspaceTrust = Object.freeze({ refresh, apply, get: () => ({ ...snapshot }), isRestricted: () => snapshot.restricted });
  window.addEventListener('beforeunload', () => { observer.disconnect(); if (typeof disposer === 'function') disposer(); }, { once: true });
})();
