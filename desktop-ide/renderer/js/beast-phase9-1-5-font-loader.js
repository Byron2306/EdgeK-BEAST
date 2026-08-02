(() => {
  "use strict";
  const root = document.documentElement;
  root.dataset.beastFonts = "loading";
  const families = [
    '700 16px "Orbitron"',
    '700 16px "Oxanium"',
    '700 16px "Rajdhani"',
    '600 16px "Chakra Petch"',
    '400 16px "Share Tech Mono"'
  ];
  if (!document.fonts || !document.fonts.load) {
    root.dataset.beastFonts = "fallback";
    return;
  }
  Promise.allSettled(families.map(face => document.fonts.load(face))).then(results => {
    const loaded = results.filter(r => r.status === "fulfilled" && r.value && r.value.length).length;
    root.dataset.beastFonts = loaded >= 4 ? "ready" : (loaded ? "partial" : "fallback");
    window.dispatchEvent(new CustomEvent("beast:fonts-ready", { detail: { loaded, total: families.length } }));
  }).catch(() => { root.dataset.beastFonts = "fallback"; });
})();
