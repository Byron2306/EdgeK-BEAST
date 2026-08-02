(() => {
  let observer = null;
  let timer = 0;
  let lastDeepAudit = 0;
  const idle = window.requestIdleCallback || (fn => setTimeout(() => fn({ timeRemaining: () => 0 }), 120));

  function duplicateIds() {
    const counts = new Map();
    document.querySelectorAll('[id]').forEach(node => counts.set(node.id, (counts.get(node.id) || 0) + 1));
    return [...counts.entries()].filter(([, count]) => count > 1);
  }

  function scrollOwners() {
    if (Date.now() - lastDeepAudit < 8000) return [];
    lastDeepAudit = Date.now();
    return [...document.querySelectorAll('*')].filter(node => {
      const style = getComputedStyle(node);
      const scrollable = /(auto|scroll)/.test(style.overflowY);
      return scrollable && node.scrollHeight > node.clientHeight + 2;
    });
  }

  function audit() {
    const outlet = document.getElementById('beastPageOutlet');
    const shell = document.querySelector('.beast-shell');
    const duplicates = duplicateIds();
    const owners = scrollOwners();
    const horizontalOverflow = document.documentElement.scrollWidth > document.documentElement.clientWidth + 2;
    const viewport = `${window.innerWidth}×${window.innerHeight}@${window.devicePixelRatio || 1}`;
    const current = BeastStore.get()?.diagnostics || {};

    const next = {
      duplicateIds: duplicates.length,
      outletChildren: outlet?.children.length || 0,
      horizontalOverflow,
      nestedScrollOwners: owners.length ? owners.filter(node => !node.classList.contains('beast-viewport') && !node.classList.contains('beast-rail') && !node.classList.contains('beast-nav') && !node.classList.contains('beast-file-list') && !node.classList.contains('monaco-scrollable-element') && !node.classList.contains('sourceplan-operation-list') && !node.classList.contains('sourceplan-check-list') && !node.classList.contains('model-registry-list') && !node.classList.contains('agent-session-list') && !node.classList.contains('agent-handoff-list')).length : (current.nestedScrollOwners || 0),
      viewport,
      activeEditors: document.querySelectorAll('.monaco-editor').length - document.querySelectorAll('.monaco-diff-editor .monaco-editor').length,
      activeDiffEditors: document.querySelectorAll('.monaco-diff-editor').length
    };
    if (Object.keys(next).some(key => current[key] !== next[key])) BeastStore.patch('diagnostics', next);

    if (shell) {
      shell.dataset.density = window.innerWidth < 1450 ? 'compact' : 'normal';
      shell.dataset.short = window.innerHeight < 820 ? 'true' : 'false';
    }

    if (duplicates.length || horizontalOverflow || (outlet?.children.length || 0) > 1) {
      console.warn('[BEAST Layout Guard]', { duplicates, horizontalOverflow, outletChildren: outlet?.children.length || 0, scrollOwners: owners });
    }
  }

  function schedule() {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => idle(audit), 120);
  }

  function init() {
    observer = new ResizeObserver(schedule);
    observer.observe(document.documentElement);
    const outlet = document.getElementById('beastPageOutlet');
    if (outlet) observer.observe(outlet);
    window.addEventListener('resize', schedule, { passive: true });
    document.addEventListener('beast:route-complete', schedule);
    schedule();
  }

  window.BeastLayoutGuard = { init, audit };
})();
