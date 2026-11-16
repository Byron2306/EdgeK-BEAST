(() => {
  let observer = null;
  let scheduled = 0;

  function keepOne(parent, selector) {
    if (!parent) return;
    const nodes = [...parent.querySelectorAll(`:scope > ${selector}`)];
    nodes.slice(1).forEach(node => node.remove());
  }

  function repairHeaderOwnership() {
    const header = document.querySelector('.beast-header.beast-header-premium');
    if (!header) return;
    ['.beast-header-brandmark','.beast-header-emblem','.beast-header-terminal','.beast-title-row','.beast-header-state']
      .forEach(selector => keepOne(header, selector));
  }

  function repairPageOwnership() {
    const outlet = document.getElementById('beastPageOutlet');
    if (!outlet) return;
    const pageRoots = [...outlet.children].filter(node => node.classList?.contains('beast-page'));
    if (pageRoots.length > 1) {
      const current = pageRoots.at(-1);
      pageRoots.slice(0,-1).forEach(node => {
        node.classList.add('beast-stale-page');
        node.setAttribute('aria-hidden','true');
        node.remove();
      });
      current.classList.remove('beast-stale-page');
      current.removeAttribute('aria-hidden');
    }
    const current = outlet.querySelector(':scope > .beast-page');
    if (current) keepOne(current, '.beast-page-head');
  }

  function repair() {
    scheduled = 0;
    repairHeaderOwnership();
    repairPageOwnership();
    document.body.dataset.beastOverlayFix = '9.1.1';
  }

  function schedule() {
    if (scheduled) return;
    scheduled = requestAnimationFrame(repair);
  }

  function init() {
    repair();
    observer?.disconnect();
    observer = new MutationObserver(schedule);
    observer.observe(document.body,{childList:true,subtree:true});
    document.addEventListener('beast:route-complete',schedule);
  }

  function destroy() {
    observer?.disconnect(); observer = null;
    if (scheduled) cancelAnimationFrame(scheduled);
    scheduled = 0;
    document.removeEventListener('beast:route-complete',schedule);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
  window.BeastPhase911OverlayFix = {init,repair,destroy};
})();
