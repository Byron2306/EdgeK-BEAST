(() => {
  let observer = null;
  let scheduled = 0;

  function enforceAtmosphere() {
    const body = document.body;
    body.dataset.beastGlass = '9.1.3';
    const mode = body.dataset.beastAtmosphere;
    if (!mode || mode === 'quiet') body.dataset.beastAtmosphere = 'matrix-grid';
    window.BeastAtmosphere?.start?.();
  }

  function refreshVersion() {
    const phase = document.querySelector('.phase-pill');
    if (phase) phase.textContent = 'PHASE 9.1.3';
    const version = document.querySelector('.beast-sidebar-foot > div:first-child');
    if (version) version.textContent = 'BEAST CORE SHELL v2.9.1.3';
    const status = document.querySelector('.beast-sidebar-foot > div:last-child');
    if (status) status.textContent = '● GLASS ATMOSPHERE + LARGE BRAND ONLINE';
    const input = document.getElementById('beastCommandInput');
    if (input) input.placeholder = 'Ask or command BEAST Phase 9.1.3…';
  }

  function markGlassPanels() {
    const outlet = document.getElementById('beastPageOutlet');
    if (!outlet) return;
    const selector = [
      '.beast-card','.beast-rail-card','[class$="-panel"]','[class*="-panel "]',
      '[class$="-card"]','[class*="-card "]','[class$="-stage"]','[class*="-stage "]',
      '[class$="-inspector"]','[class*="-inspector "]','[class$="-detail"]','[class*="-detail "]',
      '[class$="-hero"]','[class*="-hero "]','[class$="-screen"]','[class*="-screen "]'
    ].join(',');
    outlet.querySelectorAll(selector).forEach(node => node.classList.add('beast-glass-panel'));
  }

  function repair() {
    scheduled = 0;
    enforceAtmosphere();
    refreshVersion();
    markGlassPanels();
  }

  function schedule() {
    if (scheduled) return;
    scheduled = requestAnimationFrame(repair);
  }

  function init() {
    repair();
    observer?.disconnect();
    observer = new MutationObserver(schedule);
    observer.observe(document.body, { childList:true, subtree:true });
    document.addEventListener('beast:route-complete', schedule);
    document.addEventListener('beast:settings-applied', schedule);
  }

  function destroy() {
    observer?.disconnect(); observer = null;
    if (scheduled) cancelAnimationFrame(scheduled);
    scheduled = 0;
    document.removeEventListener('beast:route-complete', schedule);
    document.removeEventListener('beast:settings-applied', schedule);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once:true });
  else init();

  window.BeastPhase913GlassAtmosphere = { init, repair, destroy };
})();
