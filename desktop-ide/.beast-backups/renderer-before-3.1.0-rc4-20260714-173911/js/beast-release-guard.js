(() => {
  'use strict';
  const RELEASE = Object.freeze({
    product: 'BEAST IDE', version: '3.1.0-rc3', build: 'BEAST-IDE-3.1.0-RC3', codename: 'BLACKGLASS',
    released: '2026-07-14', routes: ["studio", "workspace", "source", "mission", "models", "agents", "review", "trust", "memory", "evidence", "crystallization", "map", "terminal", "tooling", "doctor", "providers", "system", "worktrees", "deploy", "chronicle", "economy", "settings"], schema: 1
  });
  const faults = [];
  const bounded = value => String(value ?? '').slice(0, 4000);
  function record(kind, payload) {
    faults.push({ time: new Date().toISOString(), kind, message: bounded(payload?.message || payload), stack: bounded(payload?.stack || '') });
    if (faults.length > 100) faults.shift();
  }
  function singleton(selector) { return document.querySelectorAll(selector).length; }
  function diagnostics() {
    return {
      release: RELEASE,
      generatedAt: new Date().toISOString(),
      route: window.BeastRouter?.active || document.body?.dataset?.beastPage || 'unknown',
      connection: window.BeastStore?.get?.()?.connection || null,
      viewport: { width: innerWidth, height: innerHeight, dpr: devicePixelRatio },
      performanceTier: document.body?.dataset?.performanceTier || 'unknown',
      ownership: {
        pageOutlets: singleton('#beastPageOutlet'), contextRails: singleton('#beastContextRail'),
        mascots: singleton('#beastMascot'), matrixBack: singleton('#beastMatrix'), matrixFront: singleton('#beastMatrixFront'),
        activePageRoots: document.querySelectorAll('#beastPageOutlet > .beast-page').length
      },
      faults: faults.slice()
    };
  }
  function downloadDiagnostics() {
    const blob = new Blob([JSON.stringify(diagnostics(), null, 2)], {type:'application/json'});
    const link = document.createElement('a'); link.href = URL.createObjectURL(blob);
    link.download = `BEAST_DIAGNOSTICS_${new Date().toISOString().replace(/[:.]/g,'-')}.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  }
  function stamp() {
    document.documentElement.dataset.beastVersion = RELEASE.version;
    document.body.dataset.beastRelease = RELEASE.build;
    document.body.dataset.beastPhase = 'release';
    document.querySelectorAll('[data-beast-build]').forEach(node => node.textContent = RELEASE.version.toUpperCase());
    const phase = document.querySelector('.phase-pill'); if (phase) phase.textContent = 'RC3';
  }
  function inspectOwnership() {
    const report = diagnostics().ownership;
    const bad = report.pageOutlets !== 1 || report.contextRails !== 1 || report.mascots !== 1 || report.matrixBack !== 1 || report.matrixFront !== 1 || report.activePageRoots > 1;
    document.body.dataset.releaseOwnership = bad ? 'fault' : 'clean';
    if (bad) record('ownership', JSON.stringify(report));
    return report;
  }
  addEventListener('error', event => record('error', event.error || event.message));
  addEventListener('unhandledrejection', event => record('unhandledrejection', event.reason));
  addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === 'd') { event.preventDefault(); downloadDiagnostics(); }
  });
  document.addEventListener('beast:route-complete', inspectOwnership);
  document.addEventListener('DOMContentLoaded', () => { stamp(); inspectOwnership(); });
  window.BEAST_RELEASE = Object.freeze({ ...RELEASE, diagnostics, downloadDiagnostics, inspectOwnership });
})();
