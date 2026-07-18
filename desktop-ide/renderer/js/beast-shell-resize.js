(() => {
  const storageKey = 'beast.shell.layout.v1';
  const defaults = Object.freeze({ sidebar: 258, rail: 320 });
  let shell = null;

  function stored() {
    try { const value = JSON.parse(localStorage.getItem(storageKey) || '{}'); return value && typeof value === 'object' ? value : {}; } catch (_) { return {}; }
  }
  function numeric(value, fallback) { const parsed = Number(value); return Number.isFinite(parsed) ? parsed : fallback; }
  function widths() {
    const styles = getComputedStyle(shell);
    return { sidebar: numeric(parseFloat(styles.getPropertyValue('--beast-sidebar-w')), defaults.sidebar), rail: numeric(parseFloat(styles.getPropertyValue('--beast-rail-w')), defaults.rail) };
  }
  function bounds(region) {
    const current = widths(); const centerMinimum = 460;
    if (region === 'sidebar') return [190, Math.max(190, Math.min(480, window.innerWidth - current.rail - centerMinimum))];
    return [240, Math.max(240, Math.min(540, window.innerWidth - current.sidebar - centerMinimum))];
  }
  function set(region, value, persist = true) {
    const [minimum, maximum] = bounds(region); const width = Math.max(minimum, Math.min(maximum, Math.round(numeric(value, defaults[region]))));
    shell.style.setProperty(region === 'sidebar' ? '--beast-sidebar-w' : '--beast-rail-w', `${width}px`);
    if (persist) { try { localStorage.setItem(storageKey, JSON.stringify(widths())); } catch (_) {} }
    return width;
  }
  function reset() { set('sidebar', defaults.sidebar, false); set('rail', defaults.rail, false); try { localStorage.removeItem(storageKey); } catch (_) {} }
  function bindResizer(node) {
    const region = node.dataset.shellResizer;
    node.addEventListener('pointerdown', event => {
      if (window.innerWidth <= 1100) return;
      event.preventDefault(); const pointerId = event.pointerId; const shellRect = shell.getBoundingClientRect();
      node.setPointerCapture?.(pointerId); document.body.classList.add('beast-shell-resizing');
      const move = moveEvent => { if (moveEvent.pointerId !== pointerId) return; set(region, region === 'sidebar' ? moveEvent.clientX - shellRect.left - 10 : shellRect.right - moveEvent.clientX - 10, false); };
      const finish = finishEvent => { if (finishEvent.pointerId !== pointerId) return; node.removeEventListener('pointermove', move); node.removeEventListener('pointerup', finish); node.removeEventListener('pointercancel', finish); document.body.classList.remove('beast-shell-resizing'); try { localStorage.setItem(storageKey, JSON.stringify(widths())); } catch (_) {} };
      node.addEventListener('pointermove', move); node.addEventListener('pointerup', finish); node.addEventListener('pointercancel', finish);
    });
    node.addEventListener('dblclick', reset);
    node.addEventListener('keydown', event => {
      if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
      event.preventDefault(); const direction = event.key === 'ArrowLeft' ? -1 : event.key === 'ArrowRight' ? 1 : 0;
      const current = widths()[region]; const [minimum, maximum] = bounds(region);
      set(region, event.key === 'Home' ? minimum : event.key === 'End' ? maximum : current + (region === 'sidebar' ? direction : -direction) * 20);
    });
  }
  function bind() {
    shell = document.querySelector('.beast-shell'); if (!shell) return;
    const previous = stored(); set('sidebar', previous.sidebar ?? defaults.sidebar, false); set('rail', previous.rail ?? defaults.rail, false);
    document.querySelectorAll('[data-shell-resizer]').forEach(bindResizer);
    window.addEventListener('resize', () => { const current = widths(); set('sidebar', current.sidebar, false); set('rail', current.rail, false); }, { passive:true });
    window.BeastShellLayout = { reset, widths: () => ({ ...widths() }) };
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind, { once:true }); else bind();
})();
