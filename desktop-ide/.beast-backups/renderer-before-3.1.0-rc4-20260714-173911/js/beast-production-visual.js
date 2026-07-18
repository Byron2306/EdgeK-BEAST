/* ===== SOURCE: beast-phase9-visual-system.js ===== */
(() => {
  let observer=null, headerRaf=0, worldRafs=new Map(), resizeObserver=null;
  const canvases=new Set();
  const dpr=()=>Math.min(window.devicePixelRatio||1,2);
  function size(canvas){const r=canvas.getBoundingClientRect(),q=dpr();const w=Math.max(1,Math.round(r.width*q)),h=Math.max(1,Math.round(r.height*q));if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}const ctx=canvas.getContext('2d');ctx.setTransform(q,0,0,q,0,0);return{ctx,w:r.width,h:r.height};}
  function heartbeat(canvas, seed=0){
    const {ctx,w,h}=size(canvas);ctx.clearRect(0,0,w,h);const t=performance.now()/1000;ctx.strokeStyle='rgba(119,255,61,.72)';ctx.lineWidth=1.35;ctx.shadowColor='rgba(119,255,61,.85)';ctx.shadowBlur=6;ctx.beginPath();
    const base=h*.56;for(let x=0;x<=w;x+=2){const phase=(x/w*6+t*.55+seed)%1;let y=base+Math.sin(x*.055+t*1.1+seed)*2; if(phase>.43&&phase<.455)y-=h*.18; else if(phase>=.455&&phase<.48)y+=h*.31; else if(phase>=.48&&phase<.515)y-=h*.11; ctx.lineTo(x,y);}ctx.stroke();
    ctx.shadowBlur=0;ctx.fillStyle='rgba(119,255,61,.85)';ctx.beginPath();ctx.arc(w-6,base+Math.sin(w*.055+t*1.1+seed)*2,2.2,0,Math.PI*2);ctx.fill();
  }
  function headerPulse(){const c=document.getElementById('beastHeaderPulse');if(!c)return;heartbeat(c,3.7);headerRaf=requestAnimationFrame(headerPulse);}
  function world(canvas){
    const {ctx,w,h}=size(canvas);ctx.clearRect(0,0,w,h);const t=performance.now()/1000;
    const nodes=[[.18,.32],[.46,.31],[.68,.40],[.56,.70],[.84,.66]];
    ctx.strokeStyle='rgba(119,255,61,.19)';ctx.lineWidth=1;
    for(let i=0;i<nodes.length-1;i++){const a=nodes[i],b=nodes[i+1];ctx.beginPath();ctx.moveTo(a[0]*w,a[1]*h);ctx.quadraticCurveTo((a[0]+b[0])*.5*w,(Math.min(a[1],b[1])-.14)*h,b[0]*w,b[1]*h);ctx.stroke();}
    nodes.forEach((n,i)=>{const x=n[0]*w,y=n[1]*h,r=4+Math.sin(t*2+i)*1.4;ctx.fillStyle='rgba(164,255,117,.95)';ctx.shadowColor='#77ff3d';ctx.shadowBlur=12;ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fill();ctx.shadowBlur=0;ctx.strokeStyle='rgba(119,255,61,.34)';ctx.beginPath();ctx.arc(x,y,12+(t*8+i*4)%18,0,Math.PI*2);ctx.stroke();});
    const sweep=(t*.10)%1;const gx=sweep*w;const grd=ctx.createLinearGradient(gx-80,0,gx+80,0);grd.addColorStop(0,'transparent');grd.addColorStop(.5,'rgba(119,255,61,.14)');grd.addColorStop(1,'transparent');ctx.fillStyle=grd;ctx.fillRect(gx-80,0,160,h);
  }
  function worldLoop(canvas){if(!document.contains(canvas)){worldRafs.delete(canvas);return;}world(canvas);worldRafs.set(canvas,requestAnimationFrame(()=>worldLoop(canvas)));}
  function addHeartbeat(card,index=0){if(card.dataset.phase9Heartbeat)return;card.dataset.phase9Heartbeat='1';const c=document.createElement('canvas');c.className='beast-viz-canvas beast-viz-heartbeat';c.setAttribute('aria-hidden','true');card.appendChild(c);canvases.add(c);const loop=()=>{if(!document.contains(c))return;heartbeat(c,index*.9);requestAnimationFrame(loop)};requestAnimationFrame(loop);}
  function addWorld(card){if(card.dataset.phase9World)return;card.dataset.phase9World='1';const host=document.createElement('div');host.className='beast-viz-world';const c=document.createElement('canvas');c.className='beast-viz-canvas';host.appendChild(c);card.appendChild(host);canvases.add(c);worldLoop(c);}
  function enhance(root=document){
    const page=document.body.dataset.beastPage||'';
    root.querySelectorAll?.('.beast-card').forEach((card,index)=>{
      const title=(card.querySelector('h3')?.textContent||'').toLowerCase();
      if(/core health|system health|performance|analytics|runtime readiness|compute economy/.test(title)) addHeartbeat(card,index);
      if(/system topology|global node|network intelligence|mission map/.test(title) && !card.closest('.beast-map-page')) addWorld(card);
    });
    const studioTopology=root.querySelector?.('[data-studio-systems]')?.closest('.beast-card');if(studioTopology)addWorld(studioTopology);
    document.querySelectorAll('.beast-page-head').forEach(h=>h.dataset.phase9Header='1');
  }
  function init(){
    document.body.dataset.beastPhase='9';
    const viewport=document.querySelector('.beast-viewport');if(viewport&&!document.getElementById('beastPageScan')){const scan=document.createElement('div');scan.id='beastPageScan';scan.setAttribute('aria-hidden','true');viewport.prepend(scan);}
    cancelAnimationFrame(headerRaf);headerPulse();
    enhance(document);
    observer=new MutationObserver(records=>{for(const r of records){for(const n of r.addedNodes){if(n.nodeType===1)enhance(n);}}});observer.observe(document.body,{childList:true,subtree:true});
    resizeObserver=new ResizeObserver(()=>canvases.forEach(c=>{if(c.isConnected)size(c)}));document.querySelectorAll('.beast-viewport,.beast-rail,.beast-header').forEach(el=>resizeObserver.observe(el));
  }
  function update(){enhance(document);}
  function destroy(){observer?.disconnect();resizeObserver?.disconnect();cancelAnimationFrame(headerRaf);worldRafs.forEach(id=>cancelAnimationFrame(id));worldRafs.clear();}
  window.BeastPhase9Visuals={init,update,destroy};
})();


/* ===== SOURCE: beast-phase9-1-signal-upgrade.js ===== */
(() => {
  function init(){
    document.body.dataset.beastVisual='9.1';
    const current=document.body.dataset.beastAtmosphere;
    if(!current || current==='quiet') document.body.dataset.beastAtmosphere='matrix-grid';
    const phase=document.querySelector('.phase-pill');if(phase)phase.textContent='PHASE 9.1.1';
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
  window.BeastPhase91Signal={init};
})();


/* ===== SOURCE: beast-phase9-1-1-overlay-fix.js ===== */
(() => {
  let observer = null;
  let scheduled = 0;

  function keepOne(parent, selector) {
    if (!parent) return;
    const nodes = [...parent.querySelectorAll(`:scope > ${selector}`)];
    nodes.slice(1).forEach(node => node.remove());
  }

  function repairHeaderOwnership() {
    const header = document.querySelector('.beast-header.beast-header-premium');
    if (!header) return;
    ['.beast-header-brandmark','.beast-header-emblem','.beast-header-terminal','.beast-title-row','.beast-header-state']
      .forEach(selector => keepOne(header, selector));
  }

  function repairPageOwnership() {
    const outlet = document.getElementById('beastPageOutlet');
    if (!outlet) return;
    const pageRoots = [...outlet.children].filter(node => node.classList?.contains('beast-page'));
    if (pageRoots.length > 1) {
      const current = pageRoots.at(-1);
      pageRoots.slice(0,-1).forEach(node => {
        node.classList.add('beast-stale-page');
        node.setAttribute('aria-hidden','true');
        node.remove();
      });
      current.classList.remove('beast-stale-page');
      current.removeAttribute('aria-hidden');
    }
    const current = outlet.querySelector(':scope > .beast-page');
    if (current) keepOne(current, '.beast-page-head');
  }

  function repair() {
    scheduled = 0;
    repairHeaderOwnership();
    repairPageOwnership();
    document.body.dataset.beastOverlayFix = '9.1.1';
  }

  function schedule() {
    if (scheduled) return;
    scheduled = requestAnimationFrame(repair);
  }

  function init() {
    repair();
    observer?.disconnect();
    observer = new MutationObserver(schedule);
    observer.observe(document.body,{childList:true,subtree:true});
    document.addEventListener('beast:route-complete',schedule);
  }

  function destroy() {
    observer?.disconnect(); observer = null;
    if (scheduled) cancelAnimationFrame(scheduled);
    scheduled = 0;
    document.removeEventListener('beast:route-complete',schedule);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
  window.BeastPhase911OverlayFix = {init,repair,destroy};
})();


/* ===== SOURCE: beast-phase9-1-2-contrast-control-fix.js ===== */
(() => {
  function init() {
    document.body.dataset.beastContrastFix = '9.1.2';
    const phase = document.querySelector('.phase-pill');
    if (phase) phase.textContent = 'PHASE 9.1.2';
    const sideVersion = document.querySelector('.beast-sidebar-foot > div:first-child');
    if (sideVersion) sideVersion.textContent = 'BEAST CORE SHELL v2.9.1.2';
    const status = document.querySelector('.beast-sidebar-foot > div:last-child');
    if (status) status.textContent = '● SILVER + CONTROL CONTRAST ONLINE';
    const input = document.getElementById('beastCommandInput');
    if (input) input.placeholder = 'Ask or command BEAST Phase 9.1.2…';
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once:true });
  else init();
  window.BeastPhase912ContrastFix = { init };
})();


/* ===== SOURCE: beast-phase9-1-3-glass-atmosphere-brand.js ===== */
(() => {
  let observer = null;
  let scheduled = 0;

  function enforceAtmosphere() {
    const body = document.body;
    body.dataset.beastGlass = '9.1.3';
    const mode = body.dataset.beastAtmosphere;
    if (!mode || mode === 'quiet') body.dataset.beastAtmosphere = 'matrix-grid';
    window.BeastAtmosphere?.start?.();
  }

  function refreshVersion() {
    const phase = document.querySelector('.phase-pill');
    if (phase) phase.textContent = 'PHASE 9.1.3';
    const version = document.querySelector('.beast-sidebar-foot > div:first-child');
    if (version) version.textContent = 'BEAST CORE SHELL v2.9.1.3';
    const status = document.querySelector('.beast-sidebar-foot > div:last-child');
    if (status) status.textContent = '● GLASS ATMOSPHERE + LARGE BRAND ONLINE';
    const input = document.getElementById('beastCommandInput');
    if (input) input.placeholder = 'Ask or command BEAST Phase 9.1.3…';
  }

  function markGlassPanels() {
    const outlet = document.getElementById('beastPageOutlet');
    if (!outlet) return;
    const selector = [
      '.beast-card','.beast-rail-card','[class$="-panel"]','[class*="-panel "]',
      '[class$="-card"]','[class*="-card "]','[class$="-stage"]','[class*="-stage "]',
      '[class$="-inspector"]','[class*="-inspector "]','[class$="-detail"]','[class*="-detail "]',
      '[class$="-hero"]','[class*="-hero "]','[class$="-screen"]','[class*="-screen "]'
    ].join(',');
    outlet.querySelectorAll(selector).forEach(node => node.classList.add('beast-glass-panel'));
  }

  function repair() {
    scheduled = 0;
    enforceAtmosphere();
    refreshVersion();
    markGlassPanels();
  }

  function schedule() {
    if (scheduled) return;
    scheduled = requestAnimationFrame(repair);
  }

  function init() {
    repair();
    observer?.disconnect();
    observer = new MutationObserver(schedule);
    observer.observe(document.body, { childList:true, subtree:true });
    document.addEventListener('beast:route-complete', schedule);
    document.addEventListener('beast:settings-applied', schedule);
  }

  function destroy() {
    observer?.disconnect(); observer = null;
    if (scheduled) cancelAnimationFrame(scheduled);
    scheduled = 0;
    document.removeEventListener('beast:route-complete', schedule);
    document.removeEventListener('beast:settings-applied', schedule);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once:true });
  else init();

  window.BeastPhase913GlassAtmosphere = { init, repair, destroy };
})();


/* ===== SOURCE: beast-phase9-1-4-hacker-type-atmosphere.js ===== */
(() => {
  const glyphs = '01<>[]{}λΣΔΞ::BEAST//ROOT#@$_+-=|';
  let bgRAF = 0, frontRAF = 0, resizeHandler = null, running = false;

  function makeRain(canvas, cfg) {
    if (!canvas) return null;
    const ctx = canvas.getContext('2d', { alpha:true });
    let w = 0, h = 0, dpr = 1, cols = [];

    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
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
    cancelAnimationFrame(bgRAF); cancelAnimationFrame(frontRAF);
    if (resizeHandler) window.removeEventListener('resize',resizeHandler);
    resizeHandler = null;
  }

  function start() {
    if (running || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    running = true;
    const bg = makeRain(document.getElementById('beastMatrix'), {
      step:19,fontSize:13,speedMin:.55,speedMax:1.45,alphaMin:.20,alphaMax:.48,
      trailMin:9,trailMax:20,fade:.075,headGlow:11,gap:5,velocity:3.45,tick:125
    });
    const front = makeRain(document.getElementById('beastMatrixFront'), {
      step:44,fontSize:12,speedMin:.34,speedMax:.84,alphaMin:.12,alphaMax:.28,
      trailMin:5,trailMax:12,fade:.12,headGlow:8,gap:5,velocity:3.1,tick:150
    });
    function bgLoop(){ if(!running) return; bg?.draw(); bgRAF=requestAnimationFrame(bgLoop); }
    function frontLoop(){ if(!running) return; front?.draw(); frontRAF=requestAnimationFrame(frontLoop); }
    resizeHandler = () => { bg?.resize(); front?.resize(); };
    window.addEventListener('resize',resizeHandler,{ passive:true });
    bgLoop(); frontLoop();
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
    if (!document.body.dataset.beastAtmosphere || document.body.dataset.beastAtmosphere === 'quiet') {
      document.body.dataset.beastAtmosphere = 'matrix-grid';
    }
    const phase = document.querySelector('.phase-pill');
    if (phase) phase.textContent = 'PHASE 9.1.4';
    const version = document.querySelector('.beast-sidebar-foot > div:first-child');
    if (version) version.textContent = 'BEAST CORE SHELL v2.9.1.4';
    const status = document.querySelector('.beast-sidebar-foot > div:last-child');
    if (status) status.textContent = '● HACKER TYPE + VISIBLE ATMOSPHERE ONLINE';
    const input = document.getElementById('beastCommandInput');
    if (input) input.placeholder = 'Ask or command BEAST Phase 9.1.4…';
    document.title = 'BEAST Phase 9.1.4 — Hacker Type + Visible Atmosphere';
  }

  function init() {
    try { window.BeastAtmosphere?.stop?.(); } catch (_) {}
    ensureGrid();
    updateVersion();
    window.BeastAtmosphere = { start, stop };
    start();
    document.dispatchEvent(new CustomEvent('beast:settings-applied'));
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();

  window.BeastPhase914 = { init, start, stop, ensureGrid };
})();


/* ===== SOURCE: beast-phase9-1-5-font-loader.js ===== */
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

