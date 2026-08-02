(() => {
  // v2 discards legacy widths that could collapse the navigation into an icon sliver.
  const storageKey = 'beast.shell.layout.v3';
  const defaults = Object.freeze({ sidebar: 244, rail: 280, command: 98 });
  let shell = null;

  function stored() {
    try { const value = JSON.parse(localStorage.getItem(storageKey) || '{}'); return value && typeof value === 'object' ? value : {}; } catch (_) { return {}; }
  }
  function numeric(value, fallback) { const parsed = Number(value); return Number.isFinite(parsed) ? parsed : fallback; }
  function widths() {
    const styles = getComputedStyle(shell);
    return {
      sidebar: numeric(parseFloat(styles.getPropertyValue('--beast-sidebar-w')), defaults.sidebar),
      rail: numeric(parseFloat(styles.getPropertyValue('--beast-rail-w')), defaults.rail),
      command: numeric(parseFloat(styles.getPropertyValue('--beast-command-h')), defaults.command),
    };
  }
  function bounds(region) {
    const current = widths(); const centerMinimum = 600;
    if (region === 'sidebar') return [220, Math.max(220, Math.min(360, window.innerWidth - current.rail - centerMinimum))];
    if (region === 'rail') return [250, Math.max(250, Math.min(380, window.innerWidth - current.sidebar - centerMinimum))];
    return [98, Math.max(98, Math.min(220, window.innerHeight - 220))];
  }
  function set(region, value, persist = true) {
    const [minimum, maximum] = bounds(region); const width = Math.max(minimum, Math.min(maximum, Math.round(numeric(value, defaults[region]))));
    const variable = region === 'sidebar' ? '--beast-sidebar-w' : region === 'rail' ? '--beast-rail-w' : '--beast-command-h';
    shell.style.setProperty(variable, `${width}px`);
    if (persist) { try { localStorage.setItem(storageKey, JSON.stringify(widths())); } catch (_) {} }
    return width;
  }
  function reset() {
    set('sidebar', defaults.sidebar, false);
    set('rail', defaults.rail, false);
    set('command', defaults.command, false);
    try { localStorage.removeItem(storageKey); } catch (_) {}
  }
  function bindResizer(node) {
    const region = node.dataset.shellResizer;
    node.addEventListener('pointerdown', event => {
      if (window.innerWidth <= 1100) return;
      event.preventDefault(); const pointerId = event.pointerId; const shellRect = shell.getBoundingClientRect();
      node.setPointerCapture?.(pointerId); document.body.classList.add('beast-shell-resizing');
      const move = moveEvent => {
        if (moveEvent.pointerId !== pointerId) return;
        if (region === 'sidebar') {
          set(region, moveEvent.clientX - shellRect.left - 10, false);
          return;
        }
        if (region === 'rail') {
          set(region, shellRect.right - moveEvent.clientX - 10, false);
          return;
        }
        set(region, shellRect.bottom - moveEvent.clientY - 10, false);
      };
      const finish = finishEvent => { if (finishEvent.pointerId !== pointerId) return; node.removeEventListener('pointermove', move); node.removeEventListener('pointerup', finish); node.removeEventListener('pointercancel', finish); document.body.classList.remove('beast-shell-resizing'); try { localStorage.setItem(storageKey, JSON.stringify(widths())); } catch (_) {} };
      node.addEventListener('pointermove', move); node.addEventListener('pointerup', finish); node.addEventListener('pointercancel', finish);
    });
    node.addEventListener('dblclick', reset);
    node.addEventListener('keydown', event => {
      if (!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End'].includes(event.key)) return;
      event.preventDefault(); const direction = event.key === 'ArrowLeft' || event.key === 'ArrowUp' ? -1 : event.key === 'ArrowRight' || event.key === 'ArrowDown' ? 1 : 0;
      const current = widths()[region]; const [minimum, maximum] = bounds(region);
      const delta = region === 'rail' ? -direction : direction;
      set(region, event.key === 'Home' ? minimum : event.key === 'End' ? maximum : current + delta * 20);
    });
  }
  function bind() {
    shell = document.querySelector('.beast-shell'); if (!shell) return;
    const previous = stored();
    set('sidebar', previous.sidebar ?? defaults.sidebar, false);
    set('rail', previous.rail ?? defaults.rail, false);
    set('command', previous.command ?? defaults.command, false);
    document.querySelectorAll('[data-shell-resizer]').forEach(bindResizer);
    window.addEventListener('resize', () => {
      const current = widths();
      set('sidebar', current.sidebar, false);
      set('rail', current.rail, false);
      set('command', current.command, false);
    }, { passive:true });
    window.BeastShellLayout = { reset, widths: () => ({ ...widths() }) };
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind, { once:true }); else bind();
})();
