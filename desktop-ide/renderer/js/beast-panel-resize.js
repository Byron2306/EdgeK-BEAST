(() => {
  'use strict';

  const storageKey = 'beast.workbench.panel-sizes.v4';

  function reset() { try { localStorage.removeItem(storageKey); } catch (_) {} }

  function bind() {
    // Panel handles are intentionally disabled until they are implemented as
    // absolutely positioned overlays. Injecting controls into a CSS grid makes
    // them participate in layout and can collapse authored tracks.
    try {
      // Remove layouts written by the experimental grid-child implementation.
      localStorage.removeItem('beast.workbench.panel-sizes.v2');
      localStorage.removeItem('beast.workbench.panel-sizes.v3');
    } catch (_) {}
    window.BeastWorkbenchPanels = { reset, scan() {} };
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind, { once: true });
  } else {
    bind();
  }
})();
