(() => {
  'use strict';

  const IDENTITY = window.BEAST_BUILD_IDENTITY || {};
  const RELEASE = Object.freeze({
    version:IDENTITY.product_version || '3.1.0-rc4',
    build:IDENTITY.release_id || 'BEAST-IDE-3.1.0-RC4',
    label:String(IDENTITY.product_version || '3.1.0-rc4').split('-').pop().toUpperCase(),
    codename:IDENTITY.codename || 'BLACKGLASS'
  });
  const glyphs = '01<>[]{}λΣΔΞ::BEAST//ROOT#@$_+-=|';
  const cardCanvases = new Set();
  let initialized = false;
  let running = false;
  let raf = 0;
  let observer = null;
  let resizeObserver = null;
  let resizeRaf = 0;
  let resizeTimer = 0;
  let lastFrame = 0;
  let tier = 'low';
  let motion = 'full';
  let atmosphereMode = 'matrix-grid';
  let workload = 'idle';
  let bg = null;
  let front = null;
  let pulse = null;
  let commandExpanded = false;

  const $ = id => document.getElementById(id);
  const dprLimit = () => workload === 'interactive' ? 1 : tier === 'low' ? 1 : tier === 'medium' ? 1.25 : 1.4;
  const config = () => workload === 'interactive'
      ? { fps:12, bgStep:72, front:false, frontStep:160, trail:5 }
    : tier === 'low'
      ? { fps:8, bgStep:72, front:false, frontStep:160, trail:5 }
      : tier === 'medium'
      ? { fps:8, bgStep:72, front:false, frontStep:160, trail:5 }
        : { fps:8, bgStep:72, front:false, frontStep:160, trail:5 };

  function releaseIdentity() {
    document.documentElement.dataset.beastRelease = RELEASE.version;
    document.body.dataset.beastPhase = 'release';
    document.body.dataset.beastVisualOwner = 'rc4';
    document.title = `BEAST IDE ${RELEASE.version.toUpperCase()} — ${RELEASE.codename}`;
    document.querySelector('meta[name="beast-version"]')?.setAttribute('content', RELEASE.version);
    document.querySelector('meta[name="beast-build"]')?.setAttribute('content', RELEASE.build);
    document.querySelectorAll('[data-beast-build]').forEach(node => { node.textContent = RELEASE.version.toUpperCase(); });
    const phase = document.querySelector('.phase-pill');
    if (phase) phase.textContent = RELEASE.label;
    const status = document.querySelector('.beast-sidebar-foot > div:last-child');
    if (status) status.textContent = '● VISUAL STABILIZATION ONLINE';
    const input = $('beastCommandInput');
    if (input) input.placeholder = 'Ask or command BEAST IDE RC4…';
  }

  function fontState() {
    const root = document.documentElement;
    root.dataset.beastFonts = 'loading';
    if (!document.fonts?.load) { root.dataset.beastFonts = 'fallback'; return; }
    const faces = ['700 16px "Orbitron"','700 16px "Oxanium"','700 16px "Rajdhani"','600 16px "Chakra Petch"','400 16px "Share Tech Mono"'];
    Promise.allSettled(faces.map(face => document.fonts.load(face))).then(results => {
      const loaded = results.filter(item => item.status === 'fulfilled' && item.value?.length).length;
      root.dataset.beastFonts = loaded >= 4 ? 'ready' : loaded ? 'partial' : 'fallback';
      dispatchEvent(new CustomEvent('beast:fonts-ready',{detail:{loaded,total:faces.length}}));
    }).catch(() => { root.dataset.beastFonts = 'fallback'; });
  }

  function fitCanvas(canvas, fullWindow = false) {
    if (!canvas) return null;
    const rect = fullWindow ? { width:innerWidth, height:innerHeight } : canvas.getBoundingClientRect();
    const dpr = Math.min(devicePixelRatio || 1, dprLimit());
    const width = Math.max(1, Math.round(rect.width));
    const height = Math.max(1, Math.round(rect.height));
    const pixelWidth = Math.max(1, Math.round(width * dpr));
    const pixelHeight = Math.max(1, Math.round(height * dpr));
    if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
      canvas.width = pixelWidth; canvas.height = pixelHeight;
      canvas.style.width = `${width}px`; canvas.style.height = `${height}px`;
    }
    const ctx = canvas.getContext('2d',{alpha:true});
    ctx.setTransform(dpr,0,0,dpr,0,0);
    return { ctx, width, height, dpr };
  }

  function makeRain(canvas, frontLayer = false) {
    if (!canvas) return null;
    let surface = null;
    let columns = [];
    function resize() {
      surface = fitCanvas(canvas,true);
      if (!surface) return;
      const cfg = config();
      const step = frontLayer ? cfg.frontStep : cfg.bgStep;
      columns = Array.from({length:Math.ceil(surface.width/step)},(_,index) => ({
        x:index*step+Math.random()*7,
        y:-Math.random()*surface.height,
        speed:(frontLayer?.30:.52)+Math.random()*(frontLayer?.50:.92),
        trail:Math.max(5,cfg.trail-(frontLayer?4:0))+Math.floor(Math.random()*5),
        alpha:(frontLayer?.08:.22)+Math.random()*(frontLayer?.10:.28),
        phase:Math.random()*glyphs.length
      }));
    }
    function draw(now) {
      if (!surface) resize();
      if (!surface) return;
      const {ctx,width,height}=surface;
      if (atmosphereMode === 'quiet') { ctx.clearRect(0,0,width,height); return; }
      ctx.globalCompositeOperation='source-over';
      ctx.fillStyle=frontLayer?'rgba(0,2,1,.15)':'rgba(0,2,1,.072)';
      ctx.fillRect(0,0,width,height);
      const tick=Math.floor(now/(frontLayer?150:120));
      for(let i=0;i<columns.length;i++){
        const col=columns[i];
        for(let j=0;j<col.trail;j++){
          const fall=1-j/col.trail;
          const alpha=col.alpha*fall*fall;
          ctx.shadowColor='rgba(151,255,99,.92)';
          ctx.shadowBlur=j===0?9:j<3?3:0;
          ctx.fillStyle=j===0?`rgba(228,255,217,${Math.min(.78,alpha*2.1)})`:`rgba(120,255,62,${alpha*.72})`;
          // Keep the hacker rain visual without painting literal code glyphs
          // into translucent panels where they read as stale UI data.
          ctx.fillRect(col.x,col.y-j*18,frontLayer?1:1.5,Math.max(5,18*fall));
        }
        ctx.shadowBlur=0;
        col.y+=col.speed*3.1;
        if(col.y-col.trail*18>height){col.y=-Math.random()*260;col.speed=(frontLayer?.30:.52)+Math.random()*(frontLayer?.50:.92);}
      }
    }
    resize();
    // A previous visual owner may have painted this bitmap at the same
    // dimensions. Clear it explicitly so stale glyphs cannot survive handoff.
    surface?.ctx.clearRect(0,0,surface.width,surface.height);
    return {resize,draw,clear(){surface?.ctx.clearRect(0,0,surface.width,surface.height)}};
  }

  function makeHeaderPulse() {
    const canvas = $('beastHeaderPulse');
    if (!canvas) return null;
    function draw(now) {
      const surface=fitCanvas(canvas,false); if(!surface)return;
      const {ctx,width,height}=surface; ctx.clearRect(0,0,width,height);
      const base=height*.55,t=now/1000;
      ctx.strokeStyle='rgba(120,255,62,.82)';ctx.lineWidth=1.3;ctx.shadowColor='rgba(120,255,62,.9)';ctx.shadowBlur=7;ctx.beginPath();
      for(let x=0;x<=width;x+=2){const phase=(x/Math.max(1,width)*6+t*.58)%1;let y=base+Math.sin(x*.06+t)*1.8;if(phase>.43&&phase<.455)y-=height*.20;else if(phase>=.455&&phase<.48)y+=height*.32;else if(phase>=.48&&phase<.515)y-=height*.12;x?ctx.lineTo(x,y):ctx.moveTo(x,y);}ctx.stroke();ctx.shadowBlur=0;
    }
    return {draw};
  }

  function heartbeat(canvas, now, seed=0) {
    const surface=fitCanvas(canvas,false); if(!surface)return;
    const {ctx,width,height}=surface;ctx.clearRect(0,0,width,height);const t=now/1000;
    ctx.strokeStyle='rgba(120,255,62,.74)';ctx.lineWidth=1.15;ctx.shadowColor='rgba(120,255,62,.78)';ctx.shadowBlur=5;ctx.beginPath();
    const base=height*.58;for(let x=0;x<=width;x+=2){const phase=(x/Math.max(width,1)*5+t*.5+seed)%1;let y=base+Math.sin(x*.05+t+seed)*1.5;if(phase>.46&&phase<.475)y-=height*.23;else if(phase>=.475&&phase<.50)y+=height*.35;else if(phase>=.50&&phase<.53)y-=height*.12;x?ctx.lineTo(x,y):ctx.moveTo(x,y);}ctx.stroke();ctx.shadowBlur=0;
  }

  function scan(root=document) {
    const outlet=$('beastPageOutlet');
    if(outlet){const roots=[...outlet.children].filter(node=>node.classList?.contains('beast-page'));roots.slice(0,-1).forEach(node=>node.remove());}
  }

  function draw(now) {
    if(!running)return;
    const interval=1000/config().fps;
    if(now-lastFrame>=interval){
      lastFrame=now;
      pulse?.draw(now);
    }
    raf=requestAnimationFrame(draw);
  }

  function rebuildRain() {
    bg?.clear?.();front?.clear?.();
    for(const id of ['beastMatrix','beastMatrixFront']){
      const canvas=$(id);const ctx=canvas?.getContext?.('2d');
      if(canvas&&ctx)ctx.clearRect(0,0,canvas.width,canvas.height);
    }
    // Keep one low-cost rain layer behind the shell. Panel-level raster
    // overlays are disabled in the final compatibility layer because they
    // duplicate data and produce the ghosting seen during route changes.
    bg=null;
    front=null;
  }

  function start() {
    if(running||document.hidden||motion==='reduced'||matchMedia('(prefers-reduced-motion: reduce)').matches)return;
    running=true;pulse=makeHeaderPulse();lastFrame=0;raf=requestAnimationFrame(draw);
  }

  function stop() {
    running=false;cancelAnimationFrame(raf);raf=0;bg?.clear?.();front?.clear?.();
    for(const id of ['beastMatrix','beastMatrixFront']){
      const canvas=$(id);const ctx=canvas?.getContext?.('2d');
      if(canvas&&ctx)ctx.clearRect(0,0,canvas.width,canvas.height);
    }
  }

  function restart() { stop(); start(); }
  function setTier(next='medium') { tier=next==='low'?'low':'medium';document.body.dataset.performanceTier=tier;if(running)restart(); }
  function setWorkload(next='idle') { const normalized=next==='interactive'?'interactive':'idle';if(workload===normalized)return;workload=normalized;document.body.dataset.beastWorkload=workload;if(running)restart(); }
  function setAtmosphere(next='matrix-grid') { atmosphereMode=['matrix-grid','matrix','grid','quiet'].includes(next)?next:'matrix-grid';document.body.dataset.beastAtmosphere=atmosphereMode;if(running&&atmosphereMode!=='quiet')restart();else if(atmosphereMode==='quiet'){bg?.clear?.();front?.clear?.();} }
  function setMotion(next='full') { motion=next==='reduced'?'reduced':'full';document.documentElement.dataset.motion=motion;motion==='reduced'?stop():start(); }

  function bindCommandDock() {
    const dock=document.querySelector('.beast-command');if(!dock)return;
    let toggle=$('beastCommandToggle');
    if(!toggle){toggle=document.createElement('button');toggle.id='beastCommandToggle';toggle.className='beast-command-toggle';toggle.type='button';toggle.setAttribute('aria-label','Expand command shortcuts');toggle.textContent='⌃';document.querySelector('.beast-command-tabs')?.appendChild(toggle);}
    commandExpanded=localStorage.getItem('beast.rc4.commandExpanded')==='true';
    const apply=()=>{dock.dataset.mode=commandExpanded?'expanded':'compact';document.body.dataset.commandDock=commandExpanded?'expanded':'compact';toggle.textContent=commandExpanded?'⌄':'⌃';toggle.setAttribute('aria-expanded',String(commandExpanded));toggle.setAttribute('aria-label',commandExpanded?'Collapse command shortcuts':'Expand command shortcuts');};
    toggle.addEventListener('click',()=>{commandExpanded=!commandExpanded;localStorage.setItem('beast.rc4.commandExpanded',String(commandExpanded));apply();});apply();
  }

  function init() {
    if(initialized)return;initialized=true;
    releaseIdentity();fontState();bindCommandDock();
    atmosphereMode='quiet';motion='reduced';tier=document.body.dataset.performanceTier||'low';
    document.body.dataset.beastAtmosphere='quiet';
    document.documentElement.dataset.motion='reduced';
    resizeObserver=new ResizeObserver(entries=>{cancelAnimationFrame(resizeRaf);resizeRaf=requestAnimationFrame(()=>{resizeRaf=0;for(const entry of entries){if(entry.target instanceof HTMLCanvasElement)fitCanvas(entry.target,false);}});});
    const outlet=$('beastPageOutlet');
    observer=new MutationObserver(records=>{for(const record of records)for(const node of record.addedNodes)if(node.nodeType===1)scan(node);});observer.observe(outlet||document.body,{childList:true,subtree:Boolean(outlet)});
    addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{bg?.resize?.();front?.resize?.();pulse?.draw(performance.now());},100);},{passive:true});
    document.addEventListener('visibilitychange',()=>document.hidden?stop():start());
    document.addEventListener('beast:route-complete',event=>{scan(event.detail?.root||document);releaseIdentity();});
    document.addEventListener('beast:settings-applied',event=>{const s=event.detail||{};if(s.atmosphere)setAtmosphere(s.atmosphere);if(s.motion)setMotion(s.motion);});
    scan(document);start();
  }

  function update(root=document){scan(root);releaseIdentity();}
  function destroy(){stop();cancelAnimationFrame(resizeRaf);resizeRaf=0;observer?.disconnect();observer=null;resizeObserver?.disconnect();resizeObserver=null;cardCanvases.clear();initialized=false;}

  window.BeastVisualRuntime={init,update,destroy,start,stop,restart,setTier,setWorkload,setAtmosphere,setMotion,get state(){return{running,tier,motion,atmosphereMode,workload,cardCanvases:cardCanvases.size};}};
})();
