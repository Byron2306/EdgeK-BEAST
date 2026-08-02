
(() => {
  const iconMap = {
    workspace:'workspace', mission:'mission', agents:'agents', review:'review', trust:'trust',
    memory:'memory', models:'models', evidence:'evidence', crystallization:'crystallization',
    map:'map', source:'source', worktrees:'worktrees', terminal:'terminal',
    providers:'providers', tooling:'tooling', system:'system', doctor:'doctor',
    settings:'settings', studio:'studio', deploy:'deploy', chronicle:'chronicle', economy:'economy', overview:'overview', database:'database'
  };
  const effectMap = {
    scan:'scan-line-sweep', streak:'energy-streak', grid:'holographic-grid', ring:'scan-ring',
    matrix:'matrix-stream', burst:'digital-burst', explosion:'data-explosion',
    flare:'center-flare', radar:'radar-sweep', slash:'diagonal-slash',
    success:'success-pulse', warning:'warning-flare'
  };
  window.BeastAssets = Object.freeze({
    icon(name) { return `assets/icons/${iconMap[name] || name}.png`; },
    effect(name) { return `assets/effects/${effectMap[name] || name}.png`; },
    cursor(name, size=48) { return `assets/cursors/${name}-${size}.png`; },
    frame(name) { return `assets/frames/${name}.png`; },
    mascot(state='idle', frame=0) { return `assets/mascot/${state}/frame_${String(frame).padStart(2,'0')}.png`; },
    sound(name) { return `assets/sounds/beast_${name}.wav`; }
  });
})();
