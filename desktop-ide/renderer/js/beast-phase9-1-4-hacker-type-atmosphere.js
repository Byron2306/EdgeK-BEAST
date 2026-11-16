(() => {
  const glyphs = '01<>[]{}λΣΔΞ::BEAST//ROOT#@$_+-=|';
  let loopTimer = 0, resizeHandler = null, running = false;

  function makeRain(canvas, cfg) {
    if (!canvas) return null;
    const ctx = canvas.getContext('2d', { alpha:true });
    let w = 0, h = 0, dpr = 1, cols = [];

    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, 1.25);
      w = window.innerWidth; h = window.innerHeight;
      canvas.width = Math.floor(w * dpr); canvas.height = Math.floor(h * dpr);
      canvas.style.width = `${w}px`; canvas.style.height = `${h}px`;
      ctx.setTransform(dpr,0,0,dpr,0,0);
      cols = Array.from({ length:Math.ceil(w / cfg.step) }, (_, i) => ({
        x:i * cfg.step + Math.random() * 8,
        y:-Math.random() * h,
        speed:cfg.speedMin + Math.random() * (cfg.speedMax - cfg.speedMin),
        trail:cfg.trailMin + Math.floor(Math.random() * (cfg.trailMax - cfg.trailMin + 1)),
        alpha:cfg.alphaMin + Math.random() * (cfg.alphaMax - cfg.alphaMin),
        phase:Math.random() * glyphs.length
      }));
    }

    function draw() {
      ctx.globalCompositeOperation = 'source-over';
      ctx.fillStyle = `rgba(0,2,1,${cfg.fade})`;
      ctx.fillRect(0,0,w,h);
      ctx.font = `700 ${cfg.fontSize}px "DejaVu Sans Mono","Liberation Mono",monospace`;
      const tick = Math.floor(performance.now() / cfg.tick);
      cols.forEach((col,index) => {
        for (let j=0; j<col.trail; j++) {
          const fall = 1 - j / col.trail;
          const alpha = col.alpha * fall * fall;
          const ch = glyphs[(index + j + tick + Math.floor(col.phase)) % glyphs.length];
          if (j === 0) {
            ctx.shadowColor = 'rgba(151,255,99,.98)';
            ctx.shadowBlur = cfg.headGlow;
            ctx.fillStyle = `rgba(226,255,215,${Math.min(.98,alpha * 2.7)})`;
          } else {
            ctx.shadowBlur = j < 3 ? 4 : 0;
            ctx.shadowColor = 'rgba(119,255,61,.55)';
            ctx.fillStyle = `rgba(119,255,61,${alpha})`;
          }
          ctx.fillText(ch,col.x,col.y - j * (cfg.fontSize + cfg.gap));
        }
        ctx.shadowBlur = 0;
        col.y += col.speed * cfg.velocity;
        if (col.y - col.trail * (cfg.fontSize + cfg.gap) > h) {
          col.y = -Math.random() * 260;
          col.speed = cfg.speedMin + Math.random() * (cfg.speedMax - cfg.speedMin);
        }
      });
    }
    resize();
    return { resize, draw };
  }

  function stop() {
    running = false;
    clearTimeout(loopTimer);
    if (resizeHandler) window.removeEventListener('resize',resizeHandler);
    resizeHandler = null;
  }

  function start() {
    if (running || document.body.dataset.beastAtmosphere !== 'matrix-grid' || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    running = true;
    const bg = makeRain(document.getElementById('beastMatrix'), {
      step:31,fontSize:12,speedMin:.45,speedMax:1.05,alphaMin:.13,alphaMax:.34,
      trailMin:6,trailMax:12,fade:.11,headGlow:7,gap:5,velocity:2.8,tick:160
    });
    const front = makeRain(document.getElementById('beastMatrixFront'), {
      step:82,fontSize:11,speedMin:.3,speedMax:.72,alphaMin:.06,alphaMax:.17,
      trailMin:4,trailMax:8,fade:.15,headGlow:5,gap:5,velocity:2.5,tick:180
    });
    function draw() {
      if (!running) return;
      if (!document.hidden) {
        bg?.draw();
        front?.draw();
      }
      loopTimer = setTimeout(draw, document.hidden ? 500 : 80);
    }
    resizeHandler = () => { bg?.resize(); front?.resize(); };
    window.addEventListener('resize',resizeHandler,{ passive:true });
    draw();
  }

  function ensureGrid() {
    let grid = document.getElementById('beastGridFront');
    if (!grid) {
      grid = document.createElement('div');
      grid.id = 'beastGridFront';
      grid.setAttribute('aria-hidden','true');
      document.body.appendChild(grid);
    }
  }

  function updateVersion() {
    document.body.dataset.beastType = 'industrial-hacker';
    const phase = document.querySelector('.phase-pill');
    if (phase) phase.textContent = 'PHASE 9.1.5';
    const version = document.querySelector('.beast-sidebar-foot > div:first-child');
    if (version) version.textContent = 'BEAST CORE SHELL v2.9.1.5';
    const status = document.querySelector('.beast-sidebar-foot > div:last-child');
    if (status) status.textContent = '● UNIQUE HACKER TYPE ONLINE';
    const input = document.getElementById('beastCommandInput');
    if (input) input.placeholder = 'Ask or command BEAST Phase 9.1.5…';
    document.title = 'BEAST Phase 9.1.5 — Unique Hacker Type';
  }

  function init() {
    try { window.BeastAtmosphere?.stop?.(); } catch (_) {}
    ensureGrid();
    updateVersion();
    window.BeastAtmosphere = { start, stop };
    if (document.body.dataset.beastAtmosphere === 'matrix-grid') start();
    document.dispatchEvent(new CustomEvent('beast:settings-applied'));
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();

  window.BeastPhase914 = { init, start, stop, ensureGrid };
})();
