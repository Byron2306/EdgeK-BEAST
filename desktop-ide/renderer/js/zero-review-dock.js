(() => {
  'use strict';
  const asset = new URL('zero-review-board.css', document.currentScript.src);
  const BOARD = '/edgek/zero/review-board';
  const CREATE = '/edgek/zero/reviews';
  const suffix = root => root ? '?' + new URLSearchParams({workspace: root}) : '';
  const bridge = () => window.BeastDesktopBridge;
  function mount() {
    if (document.getElementById('beast-zero-review-host')) return;
    const host = document.createElement('div');
    host.id = 'beast-zero-review-host';
    const shadow = host.attachShadow({mode: 'open'});
    shadow.innerHTML = `<div class="zrb-dock"><section class="zrb-panel" id="zero-review-panel" hidden></section>
      <button type="button" class="zrb-toggle" aria-expanded="false" aria-controls="zero-review-panel">Zero Review</button></div>`;
    const styles = document.createElement('link');
    styles.rel = 'stylesheet';
    styles.href = asset.href;
    shadow.prepend(styles);
    const panel = shadow.querySelector('.zrb-panel');
    const toggle = shadow.querySelector('button');
    const options = {timeoutMs: 5500, cacheTtl: 0, attempts: 1};
    async function gateway(path, overrides = {}) {
      const runtime = window.BeastRuntime;
      if (runtime?.hasDesktop?.('gatewayRequest')) {
        const result = await runtime.desktopCall('gatewayRequest', [{
          path, method: overrides.method || 'GET', body: overrides.body, timeoutMs: overrides.timeoutMs || options.timeoutMs,
        }], {required: true});
        if (!result?.ok) throw Object.assign(new Error(typeof result?.error === 'string' ? result.error :
          'Desktop gateway rejected this review request.'), {status: result?.status || 0});
        return result.data;
      }
      return bridge().fetchJson(path, {...options, ...overrides});
    }
    const view = BeastZeroReviewBoard.mount(panel, {
      initialActive: false,
      connectedLabel: 'Desktop gateway connected · shared with BEAST Zero',
      expectedWorkspace: () => bridge()?.workspaceRoot || '',
      rpc: async (op, value, expected) => {
        const b = bridge();
        if (!b || b.demoMode) throw new Error('Start the local Desktop gateway to use Zero Review.');
        const optionsFor = root => {
          if (!root) throw new Error('Open the configured review workspace in Desktop first.');
          return suffix(root);
        };
        if (op === 'list') return gateway(BOARD + optionsFor(value));
        if (op === 'detail') return gateway(BOARD + '/' + encodeURIComponent(value) + optionsFor(expected));
        const current = b.workspaceRoot;
        await gateway(BOARD + optionsFor(current));
        if (current !== b.workspaceRoot) throw Object.assign(new Error('The Desktop workspace changed.'), {status: 409});
        return gateway(CREATE, {method: 'POST', timeoutMs: 7500, dedupe: false,
          body: {...value, origin: 'desktop_panel'}});
      },
    });
    toggle.addEventListener('click', () => {
      panel.hidden = !panel.hidden;
      toggle.setAttribute('aria-expanded', String(!panel.hidden));
      view.setActive(!panel.hidden);
    });
    document.body.append(host);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, {once: true});
  else mount();
})();
