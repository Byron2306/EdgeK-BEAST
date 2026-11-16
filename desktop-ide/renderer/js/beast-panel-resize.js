(() => {
  'use strict';

  const storageKey = 'beast.workbench.panel-sizes.v4';
  const configurations = [
    { selector: '.cortex-layout', key: 'workspaceExplorer', label: 'Resize workspace Explorer', side: 'left', fallback: 268, minimum: 180, maximum: 480 },
    { selector: '.sourceplan-main-grid', key: 'sourcePlanSidebar', label: 'Resize SourcePlan sidebar', side: 'right', fallback: 300, minimum: 240, maximum: 560 }
  ];

  function stored() {
    try {
      const value = JSON.parse(localStorage.getItem(storageKey) || '{}');
      return value && typeof value === 'object' ? value : {};
    } catch (_) {
      return {};
    }
  }

  function persist(sizes) {
    try { localStorage.setItem(storageKey, JSON.stringify(sizes)); } catch (_) {}
  }

  function reset() {
    try { localStorage.removeItem(storageKey); } catch (_) {}
    scan();
  }

  function sizeBounds(grid, config) {
    return [config.minimum, Math.max(config.minimum, Math.min(config.maximum, grid.clientWidth - 340))];
  }

  function attach(grid, config) {
    if (grid.dataset.panelResizeBound) return;
    grid.dataset.panelResizeBound = config.key;
    grid.classList.add('beast-user-resizable');

    const sizes = stored();
    const [minimum, maximum] = sizeBounds(grid, config);
    const original = config.side === 'left'
      ? grid.firstElementChild?.getBoundingClientRect().width
      : grid.lastElementChild?.getBoundingClientRect().width;
    let width = Math.round(Number(sizes[config.key]) || original || config.fallback);
    const handle = document.createElement('button');
    handle.type = 'button';
    handle.className = `beast-panel-resizer ${config.side}`;
    handle.dataset.panelResizer = config.key;
    handle.setAttribute('data-panel-resizer', config.key);
    handle.setAttribute('role', 'separator');
    handle.setAttribute('aria-orientation', 'vertical');
    handle.setAttribute('aria-label', config.label);
    handle.tabIndex = 0;
    grid.append(handle);

    const apply = (value, save = true) => {
      const [min, max] = sizeBounds(grid, config);
      width = Math.max(min, Math.min(max, Math.round(Number(value) || config.fallback)));
      if (config.side === 'left') {
        grid.style.gridTemplateColumns = `${width}px minmax(0,1fr)`;
        handle.style.left = `${width}px`;
      } else {
        grid.style.gridTemplateColumns = `minmax(0,1fr) ${width}px`;
        handle.style.right = `${width}px`;
      }
      handle.setAttribute('aria-valuemin', String(min));
      handle.setAttribute('aria-valuemax', String(max));
      handle.setAttribute('aria-valuenow', String(width));
      if (save) persist({ ...stored(), [config.key]: width });
    };

    apply(width, false);
    const resizeObserver = new ResizeObserver(() => apply(width, false));
    resizeObserver.observe(grid);
    handle.addEventListener('pointerdown', event => {
      if (window.innerWidth <= 1100) return;
      event.preventDefault();
      const gridRect = grid.getBoundingClientRect();
      const pointerId = event.pointerId;
      const move = moveEvent => {
        if (moveEvent.pointerId !== pointerId) return;
        const next = config.side === 'left'
          ? moveEvent.clientX - gridRect.left
          : gridRect.right - moveEvent.clientX;
        apply(next, false);
      };
      const finish = finishEvent => {
        if (finishEvent?.pointerId !== undefined && finishEvent.pointerId !== pointerId) return;
        window.removeEventListener('pointermove', move);
        window.removeEventListener('pointerup', finish);
        window.removeEventListener('pointercancel', finish);
        persist({ ...stored(), [config.key]: width });
      };
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', finish, { once: true });
      window.addEventListener('pointercancel', finish, { once: true });
    });
    handle.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const direction = event.key === 'ArrowLeft' ? -1 : 1;
      apply(event.key === 'Home' ? minimum : event.key === 'End' ? maximum : width + direction * 16);
    });
  }

  function scan(root = document) {
    for (const config of configurations) {
      root.querySelectorAll(config.selector).forEach(grid => attach(grid, config));
    }
  }

  function bind() {
    scan();
    const outlet = document.getElementById('beastPageOutlet');
    if (outlet) {
      const observer = new MutationObserver(() => scan(outlet));
      observer.observe(outlet, { childList: true, subtree: true });
    }
    window.addEventListener('resize', () => scan(), { passive: true });
    window.BeastWorkbenchPanels = { reset, scan };
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind, { once: true });
  } else {
    bind();
  }
})();
