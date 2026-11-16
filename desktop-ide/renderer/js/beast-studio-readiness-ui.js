(() => {
  const page = window.BeastStudioPage;
  if (!page || typeof page.renderer !== 'function') throw new Error('Studio page must load before its readiness display.');

  const renderStudio = page.renderer;
  page.renderer = async (...args) => {
    const rendered = await renderStudio(...args);
    const node = rendered?.node;
    if (!node) return rendered;

    let disposed = false;
    function update(state) {
      if (disposed) return;
      const studio = state.studio || {};
      const systems = studio.systems || [];
      const host = node.querySelector('[data-studio-systems]');
      const rows = host?.querySelectorAll('button') || [];
      systems.forEach((system, index) => {
        const row = rows[index];
        if (!row) return;
        const detail = row.querySelector('small');
        const status = row.querySelector('i');
        if (detail) detail.textContent = system.detail || system.status || 'No status reported';
        if (status) {
          status.dataset.readinessStatus = system.status || 'unknown';
          status.classList.toggle('online', Boolean(system.ready));
        }
        row.dataset.readinessStatus = system.status || 'unknown';
      });

      const health = node.querySelector('[data-studio-health]');
      if (health) {
        let note = health.querySelector('.p8-readiness-note');
        if (!note) {
          note = document.createElement('small');
          note.className = 'p8-readiness-note';
          health.append(note);
        }
        const readiness = studio.readiness || { ready:systems.filter(system => system.ready).length, total:systems.length };
        const pending = systems.filter(system => ['checking','not_checked','stale'].includes(system.status)).length;
        note.textContent = studio.loading
          ? `Refreshing live checks · ${readiness.ready}/${readiness.total} ready`
          : `${readiness.ready}/${readiness.total} ready · ${systems.length - readiness.ready - pending} blocked · ${pending} unchecked`;
      }
    }

    const unsubscribe = BeastStore.subscribe(update);
    const refreshOnClick = event => {
      if (!event.target.closest('[data-p8-action="studio-refresh"]')) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      void BeastUtilityOrchestrationBridge.refreshStudio({ force:true });
    };
    node.addEventListener('click', refreshOnClick, true);

    return {
      ...rendered,
      dispose() {
        disposed = true;
        unsubscribe();
        node.removeEventListener('click', refreshOnClick, true);
        rendered.dispose?.();
      }
    };
  };
})();
