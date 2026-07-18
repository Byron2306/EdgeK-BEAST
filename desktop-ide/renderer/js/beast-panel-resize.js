(() => {
  const storageKey = 'beast.workbench.panel-sizes.v1';
  const excluded = '.cortex-explorer,.cortex-editor,.cortex-ai-panel,.beast-command,.beast-sidebar,.beast-rail';
  let observer = null;
  let scanTimer = 0;
  let active = null;

  function read() { try { const value = JSON.parse(localStorage.getItem(storageKey) || '{}'); return value && typeof value === 'object' ? value : {}; } catch (_) { return {}; } }
  function write(value) { try { localStorage.setItem(storageKey, JSON.stringify(value)); } catch (_) {} }
  function routeKey(page, index) {
    const route = window.BeastStore?.get?.().route || page.className.split(/\s+/).find(name => name.endsWith('-page')) || 'workbench';
    return `${route}:${page.className.split(/\s+/).find(name => name.endsWith('-page')) || 'page'}:${index}`;
  }
  function qualifies(card) {
    if (card.matches(excluded) || card.closest('.beast-workspace-page')) return false;
    const rect = card.getBoundingClientRect();
    return rect.width >= 250 && rect.height >= 150 && getComputedStyle(card).display !== 'none';
  }
  function attach(card, key, saved) {
    if (card.dataset.beastPanelResizeBound === 'true') return;
    card.dataset.beastPanelResizeBound = 'true'; card.dataset.beastPanelResizeKey = key; card.classList.add('beast-user-resizable');
    const prior = saved[key];
    if (prior?.width) card.style.width = `${prior.width}px`;
    if (prior?.height) card.style.height = `${prior.height}px`;
    const persist = () => {
      if (active?.card !== card) return;
      const rect = card.getBoundingClientRect(); const values = read(); values[key] = { width:Math.round(rect.width), height:Math.round(rect.height) }; write(values);
    };
    card.addEventListener('pointerdown', event => {
      const rect = card.getBoundingClientRect(); const dragging = event.clientX >= rect.right - 28 && event.clientY >= rect.bottom - 28;
      if (dragging) { active = { card, persist }; document.body.classList.add('beast-panel-resizing'); }
    });
    card.addEventListener('dblclick', event => {
      const rect = card.getBoundingClientRect();
      if (event.clientX < rect.right - 28 || event.clientY < rect.bottom - 28) return;
      card.style.removeProperty('width'); card.style.removeProperty('height'); const values = read(); delete values[key]; write(values);
    });
  }
  function scan() {
    const outlet = document.getElementById('beastPageOutlet'); const page = outlet?.querySelector('.beast-page');
    if (!page || window.innerWidth <= 900) return;
    const saved = read(); let index = 0;
    page.querySelectorAll('.beast-card').forEach(card => { if (!qualifies(card)) return; attach(card, routeKey(page, index++), saved); });
  }
  function scheduleScan() { clearTimeout(scanTimer); scanTimer = setTimeout(scan, 60); }
  function bind() {
    const outlet = document.getElementById('beastPageOutlet'); if (!outlet) return;
    observer = new MutationObserver(scheduleScan); observer.observe(outlet, { childList:true, subtree:true });
    const finish = () => { if (active) active.persist(); active = null; document.body.classList.remove('beast-panel-resizing'); };
    window.addEventListener('pointerup', finish); window.addEventListener('pointercancel', finish);
    window.addEventListener('resize', scheduleScan, { passive:true }); scheduleScan();
    window.BeastWorkbenchPanels = { reset() { document.querySelectorAll('.beast-user-resizable').forEach(card => { card.style.removeProperty('width'); card.style.removeProperty('height'); }); try { localStorage.removeItem(storageKey); } catch (_) {} }, scan };
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind, { once:true }); else bind();
})();
