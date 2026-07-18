(() => {
  'use strict';
  const KEY = 'beast.phase11.preferences';
  const defaults = { textScale:'normal', contrast:'normal', motion:'full', atmosphere:'matrix-grid', adaptive:true };
  const pages = ['studio','workspace','source','mission','models','agents','review','trust','memory','evidence','crystallization','map','terminal','tooling','doctor','providers','system','worktrees','deploy','chronicle','economy','settings'];
  let settings = {...defaults};
  let initialized = false;
  let observer = null;
  let resizeTimer = 0;
  let perfRAF = 0;
  let perfSamples = [];
  let longTasks = 0;
  let atmosphere = null;

  const $ = id => document.getElementById(id);
  const announce = message => { const live=$('beastA11yLive'); if(live){ live.textContent=''; requestAnimationFrame(()=>live.textContent=message); } };
  const read = () => { try { return {...defaults,...JSON.parse(localStorage.getItem(KEY)||'{}')}; } catch(_) { return {...defaults}; } };
  const write = () => localStorage.setItem(KEY,JSON.stringify(settings));

  function performanceConfig(tier='high') {
    if (tier === 'low') return {fps:18,bgStep:42,front:false,frontStep:92,dpr:1,trail:8};
    if (tier === 'medium') return {fps:24,bgStep:29,front:true,frontStep:78,dpr:1.35,trail:11};
    return {fps:30,bgStep:21,front:true,frontStep:58,dpr:1.7,trail:15};
  }

  function createAtmosphere() {
    try { window.BeastAtmosphere?.stop?.(); } catch(_) {}
    const glyphs='01<>[]{}λΣΔΞ::BEAST//ROOT#@$_+-=|';
    let running=false,raf=0,last=0,controllers=[],resizeHandler=null;
    function make(canvas,cfg,front=false){
      if(!canvas)return null; const ctx=canvas.getContext('2d',{alpha:true}); let w=0,h=0,dpr=1,cols=[];
      function resize(){
        const quality=performanceConfig(document.body.dataset.performanceTier||'high');
        dpr=Math.min(devicePixelRatio||1,quality.dpr); w=innerWidth;h=innerHeight;
        canvas.width=Math.max(1,Math.floor(w*dpr));canvas.height=Math.max(1,Math.floor(h*dpr));canvas.style.width=w+'px';canvas.style.height=h+'px';ctx.setTransform(dpr,0,0,dpr,0,0);
        const step=front?quality.frontStep:quality.bgStep;
        cols=Array.from({length:Math.ceil(w/step)},(_,i)=>({x:i*step+Math.random()*7,y:-Math.random()*h,speed:(front?.35:.55)+Math.random()*(front?.55:.9),trail:Math.max(5,quality.trail-(front?4:0))+Math.floor(Math.random()*5),alpha:(front?.10:.20)+Math.random()*(front?.12:.25),phase:Math.random()*glyphs.length}));
      }
      function draw(now){
        const mode=document.body.dataset.beastAtmosphere||'matrix-grid';
        if(mode==='quiet'||mode==='grid'){ctx.clearRect(0,0,w,h);return;}
        ctx.fillStyle=front?'rgba(0,2,1,.13)':'rgba(0,2,1,.075)';ctx.fillRect(0,0,w,h);ctx.font=`700 ${front?12:13}px "Share Tech Mono","JetBrains Mono",ui-monospace,monospace`;
        const tick=Math.floor(now/(front?155:125));
        for(let i=0;i<cols.length;i++){const col=cols[i];for(let j=0;j<col.trail;j++){const fall=1-j/col.trail,a=col.alpha*fall*fall,ch=glyphs[(i+j+tick+Math.floor(col.phase))%glyphs.length];ctx.shadowColor='rgba(151,255,99,.9)';ctx.shadowBlur=j===0?8:0;ctx.fillStyle=j===0?`rgba(225,255,214,${Math.min(.94,a*2.5)})`:`rgba(119,255,61,${a})`;ctx.fillText(ch,col.x,col.y-j*18);}ctx.shadowBlur=0;col.y+=col.speed*3.1;if(col.y-col.trail*18>h){col.y=-Math.random()*250;}}
      }
      resize();return{resize,draw};
    }
    function loop(now){
      if(!running)return; const tier=document.body.dataset.performanceTier||'high',cfg=performanceConfig(tier),interval=1000/cfg.fps;
      if(now-last>=interval){last=now;controllers.forEach(c=>c?.draw(now));}
      raf=requestAnimationFrame(loop);
    }
    function start(){
      if(running||document.hidden||document.documentElement.dataset.motion==='reduced'||matchMedia('(prefers-reduced-motion: reduce)').matches)return;
      running=true;const cfg=performanceConfig(document.body.dataset.performanceTier||'high');controllers=[make($('beastMatrix'),cfg,false),cfg.front?make($('beastMatrixFront'),cfg,true):null];resizeHandler=()=>controllers.forEach(c=>c?.resize());addEventListener('resize',resizeHandler,{passive:true});raf=requestAnimationFrame(loop);
    }
    function stop(){running=false;cancelAnimationFrame(raf);if(resizeHandler)removeEventListener('resize',resizeHandler);resizeHandler=null;controllers=[];}
    function restart(){stop();start();}
    return {start,stop,restart,get running(){return running;}};
  }

  function setTier(tier,reason='adaptive') {
    const normalized=['high','medium','low'].includes(tier)?tier:'medium';
    if(document.body.dataset.performanceTier===normalized)return;
    document.body.dataset.performanceTier=normalized;
    $('beastPerformanceTier') && ($('beastPerformanceTier').textContent=`${normalized.toUpperCase()} · ${reason}`);
    if(settings.adaptive) atmosphere?.restart?.();
    document.dispatchEvent(new CustomEvent('beast:performance-tier',{detail:{tier:normalized,reason}}));
  }

  function initialTier(){
    const cores=navigator.hardwareConcurrency||4, memory=navigator.deviceMemory||4, dpr=devicePixelRatio||1;
    if(cores<=4||memory<=4||dpr>2.25)return'medium';
    return'high';
  }

  function monitorPerformance(){
    perfSamples=[];let previous=performance.now(),started=previous;
    function sample(now){
      const delta=now-previous;previous=now;if(delta<250)perfSamples.push(delta);
      if(now-started<4200){perfRAF=requestAnimationFrame(sample);return;}
      const avg=perfSamples.length?perfSamples.reduce((a,b)=>a+b,0)/perfSamples.length:33;
      const fps=Math.round(1000/avg);let tier=fps<38?'low':fps<53?'medium':'high';
      if(longTasks>=3&&tier==='high')tier='medium';
      if(settings.adaptive)setTier(tier,`${fps} fps`);else setTier(initialTier(),'manual effects');
    }
    perfRAF=requestAnimationFrame(sample);
    if('PerformanceObserver'in window){try{new PerformanceObserver(list=>{longTasks+=list.getEntries().length;}).observe({entryTypes:['longtask']});}catch(_){}}
  }

  function applySettings({persist=true,announceChange=false}={}){
    const root=document.documentElement,body=document.body;
    root.dataset.textScale=settings.textScale;root.dataset.contrast=settings.contrast;root.dataset.motion=settings.motion;
    body.dataset.beastAtmosphere=settings.atmosphere;body.dataset.adaptiveEffects=String(settings.adaptive);
    if(settings.motion==='reduced')atmosphere?.stop?.();else atmosphere?.start?.();
    if(persist)write();
    syncControls();
    document.dispatchEvent(new CustomEvent('beast:settings-applied',{detail:{...settings}}));
    if(announceChange)announce('BEAST display preferences applied');
  }

  function syncControls(){
    const map={beastTextScale:'textScale',beastContrastMode:'contrast',beastMotionMode:'motion',beastAtmosphereMode:'atmosphere'};
    for(const [id,key]of Object.entries(map)){const el=$(id);if(el)el.value=settings[key];}
    const adaptive=$('beastAdaptiveEffects');if(adaptive)adaptive.checked=settings.adaptive;
    const readout=$('beastViewportReadout');if(readout)readout.textContent=`${innerWidth} × ${innerHeight} · ${Math.round(devicePixelRatio*100)}% DPR`;
  }

  function openPanel(open=true){
    const panel=$('beastAccessPanel'),toggle=$('beastAccessToggle');if(!panel||!toggle)return;
    panel.hidden=!open;toggle.setAttribute('aria-expanded',String(open));
    if(open){panel.querySelector('select,input,button')?.focus();announce('Display and motion controls opened');}else{toggle.focus();announce('Display and motion controls closed');}
  }

  function accessibleName(node){
    const text=(node.textContent||'').trim().replace(/\s+/g,' ');if(text)return text;
    return node.getAttribute('title')||node.dataset.nav||node.dataset.beastRoute||node.dataset.commandChip||node.querySelector('img')?.getAttribute('alt')||'BEAST action';
  }

  function repairA11y(root=document){
    root.querySelectorAll?.('button').forEach(button=>{if(!button.hasAttribute('type'))button.type='button';const text=(button.textContent||'').trim();if(!button.getAttribute('aria-label')&&!text)button.setAttribute('aria-label',accessibleName(button));});
    root.querySelectorAll?.('button img,.beast-nav img,.beast-page-actions img').forEach(img=>{if(img.closest('button'))img.alt='';});
    root.querySelectorAll?.('canvas').forEach(canvas=>canvas.setAttribute('aria-hidden','true'));
    root.querySelectorAll?.('.beast-page').forEach((page,index)=>{page.setAttribute('role','region');const h=page.querySelector('.beast-page-head h2,h1,h2');if(h){if(!h.id)h.id=`beastPageHeading-${Date.now()}-${index}`;page.setAttribute('aria-labelledby',h.id);$('beastMainViewport')?.setAttribute('aria-labelledby',h.id);}});
    const active=window.BeastRouter?.active||document.body.dataset.beastPage;
    document.querySelectorAll('[data-beast-route]').forEach(btn=>{const current=btn.dataset.beastRoute===active;btn.toggleAttribute('aria-current',current);if(current)btn.setAttribute('aria-current','page');});
    root.querySelectorAll?.('[class*="selected"],.selected').forEach(node=>{if(node.matches('button,[role="button"]'))node.setAttribute('aria-pressed','true');});
  }

  function routeStep(direction){const active=window.BeastRouter?.active||'studio',i=Math.max(0,pages.indexOf(active)),next=pages[(i+direction+pages.length)%pages.length];window.BeastRouter?.navigate?.(next);announce(`${next} page`);}
  function cycleRegions(){const regions=[$('beastMainViewport'),document.querySelector('.beast-sidebar'),document.querySelector('.beast-rail'),document.querySelector('.beast-command')].filter(el=>el&&getComputedStyle(el).display!=='none');const current=regions.indexOf(document.activeElement.closest?.('.beast-viewport,.beast-sidebar,.beast-rail,.beast-command'));const target=regions[(current+1)%regions.length];target.tabIndex=target.tabIndex<0?0:target.tabIndex;target.focus();announce(target.getAttribute('aria-label')||'BEAST region');}

  function bind(){
    $('beastAccessToggle')?.addEventListener('click',()=>openPanel($('beastAccessPanel')?.hidden));
    $('beastAccessClose')?.addEventListener('click',()=>openPanel(false));
    const handlers={beastTextScale:['textScale'],beastContrastMode:['contrast'],beastMotionMode:['motion'],beastAtmosphereMode:['atmosphere']};
    for(const[id,[key]]of Object.entries(handlers))$(id)?.addEventListener('change',e=>{settings[key]=e.target.value;applySettings({announceChange:true});});
    $('beastAdaptiveEffects')?.addEventListener('change',e=>{settings.adaptive=e.target.checked;applySettings({announceChange:true});monitorPerformance();});
    document.addEventListener('keydown',event=>{
      const mod=event.ctrlKey||event.metaKey;
      if(mod&&event.key.toLowerCase()==='k'){event.preventDefault();$('beastCommandInput')?.focus();announce('Command input focused');}
      if(mod&&event.shiftKey&&event.key.toLowerCase()==='l'){event.preventDefault();openPanel($('beastAccessPanel')?.hidden);}
      if(event.key==='F6'){event.preventDefault();cycleRegions();}
      if(event.altKey&&event.key==='ArrowRight'){event.preventDefault();routeStep(1);}
      if(event.altKey&&event.key==='ArrowLeft'){event.preventDefault();routeStep(-1);}
      if(event.key==='Escape'&&!$('beastAccessPanel')?.hidden)openPanel(false);
    });
    document.addEventListener('beast:route-start',()=>{$('beastPageOutlet')?.setAttribute('aria-busy','true');});
    document.addEventListener('beast:route-complete',event=>{const outlet=$('beastPageOutlet');outlet?.setAttribute('aria-busy','false');repairA11y(outlet||document);const page=event.detail?.page||window.BeastRouter?.active;announce(`${page} workspace loaded`);requestAnimationFrame(()=>$('beastMainViewport')?.focus({preventScroll:true}));});
    document.addEventListener('visibilitychange',()=>{if(document.hidden)atmosphere?.stop?.();else if(settings.motion!=='reduced')atmosphere?.start?.();});
    addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{syncControls();document.body.dataset.viewport=innerWidth<760?'compact':innerWidth<1180?'narrow':innerWidth<1540?'medium':'wide';},120);},{passive:true});
  }

  function init(){
    if(initialized)return;initialized=true;settings=read();
    document.body.dataset.beastPhase='release';document.body.dataset.viewport=innerWidth<760?'compact':innerWidth<1180?'narrow':innerWidth<1540?'medium':'wide';
    atmosphere=createAtmosphere();window.BeastAtmosphere=atmosphere;setTier(initialTier(),'hardware profile');
    bind();applySettings({persist:false});repairA11y(document);observer=new MutationObserver(records=>{for(const record of records)for(const node of record.addedNodes)if(node.nodeType===1)repairA11y(node);});observer.observe(document.body,{childList:true,subtree:true});monitorPerformance();
    const phase=document.querySelector('.phase-pill');if(phase)phase.textContent='RC3';
    announce('BEAST-IDE-3.1.0-RC3 accessibility and performance layer online');
  }
  function destroy(){observer?.disconnect();observer=null;cancelAnimationFrame(perfRAF);atmosphere?.stop?.();initialized=false;}
  window.BeastAccessibility={init,destroy,applySettings,repairA11y,setTier,get settings(){return{...settings};}};
})();
