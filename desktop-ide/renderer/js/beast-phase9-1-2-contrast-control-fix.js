(() => {
  function init() {
    document.body.dataset.beastContrastFix = '9.1.2';
    const phase = document.querySelector('.phase-pill');
    if (phase) phase.textContent = 'PHASE 9.1.2';
    const sideVersion = document.querySelector('.beast-sidebar-foot > div:first-child');
    if (sideVersion) sideVersion.textContent = 'BEAST CORE SHELL v2.9.1.2';
    const status = document.querySelector('.beast-sidebar-foot > div:last-child');
    if (status) status.textContent = '● SILVER + CONTROL CONTRAST ONLINE';
    const input = document.getElementById('beastCommandInput');
    if (input) input.placeholder = 'Ask or command BEAST Phase 9.1.2…';
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once:true });
  else init();
  window.BeastPhase912ContrastFix = { init };
})();
