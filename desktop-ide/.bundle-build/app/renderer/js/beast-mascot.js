(() => {
  const configs = {
    idle:     { count: 10, sequence: [0,1,2,1,0,0,3,4,0,0], frameMs: 145 },
    working:  { count: 10, sequence: [0,1,2,3,4,5,6,7,8,9], frameMs: 105 },
    alert:    { count: 10, sequence: [0,1,2,3,4,5,6,7,8,9], frameMs: 125 },
    finished: { count: 10, sequence: [0,1,2,3,4,5,6,7,8,9], frameMs: 135 }
  };
  let state = 'idle';
  let sequenceIndex = 0;
  let timer = 0;
  let visible = true;

  function image() { return document.getElementById('beastMascotFrame'); }
  function shell() { return document.getElementById('beastMascot'); }

  function draw() {
    const node = image();
    if (!node) return;
    const config = configs[state];
    const frame = config.sequence[sequenceIndex % config.sequence.length];
    node.src = BeastAssets.mascot(state, frame);
    node.alt = `BEAST mascot ${state}`;
    shell()?.setAttribute('data-state', state);
  }

  function tick() {
    if (!visible) return;
    sequenceIndex = (sequenceIndex + 1) % configs[state].sequence.length;
    draw();
  }

  function loop() {
    clearInterval(timer);
    timer = window.setInterval(tick, configs[state].frameMs);
  }

  function setState(next) {
    if (!configs[next]) next = 'idle';
    if (next === state) return;
    state = next;
    sequenceIndex = 0;
    draw();
    loop();
    document.dispatchEvent(new CustomEvent('beast:mascot-state', { detail: { state } }));
  }

  function init() {
    document.addEventListener('visibilitychange', () => {
      visible = !document.hidden;
      if (visible) { draw(); loop(); } else clearInterval(timer);
    });
    draw();
    loop();
  }

  window.BeastMascot = { init, setState, get state() { return state; } };
})();
