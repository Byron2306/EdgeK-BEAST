(function () {
  'use strict';

  let canonicalLevel = null;
  let applying = false;
  const storageKey = 'beast.desktop.zoom-level.v2';

  function readStoredLevel() {
    try {
      const value = Number(localStorage.getItem(storageKey));
      return Number.isFinite(value) ? Math.max(-3, Math.min(5, Math.round(value))) : null;
    } catch (_) { return null; }
  }

  function writeStoredLevel(level) {
    try { localStorage.setItem(storageKey, String(level)); } catch (_) {}
  }

  async function readCanonicalLevel() {
    const stored = readStoredLevel();
    // The renderer preference is authoritative. Electron's current zoom can
    // still be the default during reload, which used to erase the preference
    // before the reapply pass ran.
    if (Number.isFinite(stored)) {
      canonicalLevel = stored;
      return;
    }
    if (!window.beastDesktop?.getZoom) return;
    try {
      const result = await window.beastDesktop.getZoom();
      canonicalLevel = Number(result?.level);
      if (!Number.isFinite(canonicalLevel)) canonicalLevel = 0;
      writeStoredLevel(canonicalLevel);
    } catch (_) {}
  }

  async function reapplyCanonicalZoom() {
    if (applying || !window.beastDesktop?.setZoom) return;
    applying = true;
    try {
      if (!Number.isFinite(canonicalLevel)) await readCanonicalLevel();
      if (Number.isFinite(canonicalLevel)) {
        const result = await window.beastDesktop.setZoom(canonicalLevel);
        canonicalLevel = Number(result?.level);
        if (Number.isFinite(canonicalLevel)) writeStoredLevel(canonicalLevel);
      }
    } catch (_) {
      canonicalLevel = 0;
    } finally {
      applying = false;
    }
  }

  async function restore() {
    await readCanonicalLevel();
    await reapplyCanonicalZoom();
  }

  // Restore before a route renders and once again after its DOM settles. The
  // double pass prevents route-specific initialization from overwriting the
  // user's persisted desktop scale.
  document.addEventListener('beast:route-start', restore);
  document.addEventListener('beast:route-complete', () => {
    requestAnimationFrame(() => requestAnimationFrame(restore));
  });
  window.addEventListener('hashchange', restore);
  window.addEventListener('pageshow', restore);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) restore();
  });
  window.addEventListener('focus', restore);
  window.addEventListener('storage', event => {
    if (event.key === storageKey) {
      canonicalLevel = null;
      restore();
    }
  });
  restore();
})();
