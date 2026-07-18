(() => {
  'use strict';
  const KEY='beast.rc4.preferences';
  const defaults={textScale:'normal',contrast:'normal',motion:'full',atmosphere:'matrix-grid',adaptive:true};
  const pages=['studio','workspace','source','mission','models','agents','review','trust','memory','evidence','crystallization','map','terminal','tooling','doctor','providers','system','worktrees','deploy','chronicle','economy','settings'];
  let settings={...defaults};let initialized=false;let observer=null;let resizeTimer=0;let perfRAF=0;let performanceObserver=null;
  const $=id=>document.getElementById(id);
  const announce=message=>{const live=$('beastA11yLive');if(!live)return;live.textContent='';requestAnimationFrame(()=>{live.textContent=message;});};
  const read=()=>{try{return{...defaults,...JSON.parse(localStorage.getItem(KEY)||'{}')};}catch(_){return{...defaults};}};
  const write=()=>{try{localStorage.setItem(KEY,JSON.stringify(settings));}catch(_){}};

  function setTier(next,reason='adaptive'){
    const tier=['high','medium','low'].includes(next)?next:'medium';
    document.body.dataset.performanceTier=tier;
    $('beastPerformanceTier') && ($('beastPerformanceTier').textContent=`${tier.toUpperCase()} · ${reason}`);
    window.BeastVisualRuntime?.setTier?.(tier);
    document.dispatchEvent(new CustomEvent('beast:performance-tier',{detail:{tier,reason}}));
  }
  function initialTier(){const cores=navigator.hardwareConcurrency||4,memory=navigator.deviceMemory||4,dpr=devicePixelRatio||1;if(cores<=4||memory<=4||dpr>2.25)return'medium';return'high';}
  function monitorPerformance(){
    cancelAnimationFrame(perfRAF);performanceObserver?.disconnect?.();
    let samples=[],previous=performance.now(),started=previous,longTasks=0;
    function sample(now){const delta=now-previous;previous=now;if(delta<250)samples.push(delta);if(now-started<4200){perfRAF=requestAnimationFrame(sample);return;}const avg=samples.length?samples.reduce((a,b)=>a+b,0)/samples.length:33;const fps=Math.round(1000/avg);let tier=fps<38?'low':fps<53?'medium':'high';if(longTasks>=3&&tier==='high')tier='medium';if(settings.adaptive)setTier(tier,`${fps} fps`);else setTier(initialTier(),'manual effects');}
    perfRAF=requestAnimationFrame(sample);
    if('PerformanceObserver'in window){try{performanceObserver=new PerformanceObserver(list=>{longTasks+=list.getEntries().length;});performanceObserver.observe({entryTypes:['longtask']});}catch(_){performanceObserver=null;}}
  }

  function syncControls(){
    const map={beastTextScale:'textScale',beastContrastMode:'contrast',beastMotionMode:'motion',beastAtmosphereMode:'atmosphere'};
    for(const[id,key]of Object.entries(map)){const el=$(id);if(el)el.value=settings[key];}
    const adaptive=$('beastAdaptiveEffects');if(adaptive)adaptive.checked=settings.adaptive;
    const readout=$('beastViewportReadout');if(readout)readout.textContent=`${innerWidth} × ${innerHeight} · ${Math.round(devicePixelRatio*100)}% DPR`;
  }
  function applySettings({persist=true,announceChange=false}={}){
    const root=document.documentElement,body=document.body;
    root.dataset.textScale=settings.textScale;root.dataset.contrast=settings.contrast;root.dataset.motion=settings.motion;
    body.dataset.beastAtmosphere=settings.atmosphere;body.dataset.adaptiveEffects=String(settings.adaptive);
    window.BeastVisualRuntime?.setAtmosphere?.(settings.atmosphere);
    window.BeastVisualRuntime?.setMotion?.(settings.motion);
    if(persist)write();syncControls();
    document.dispatchEvent(new CustomEvent('beast:settings-applied',{detail:{...settings}}));
    if(announceChange)announce('BEAST display preferences applied');
  }

  function openPanel(open=true){const panel=$('beastAccessPanel'),toggle=$('beastAccessToggle');if(!panel||!toggle)return;panel.hidden=!open;toggle.setAttribute('aria-expanded',String(open));if(open){panel.querySelector('select,input,button')?.focus();announce('Display and motion controls opened');}else{toggle.focus();announce('Display and motion controls closed');}}
  function accessibleName(node){const text=(node.textContent||'').trim().replace(/\s+/g,' ');return text||node.getAttribute('title')||node.dataset.nav||node.dataset.beastRoute||node.dataset.commandChip||node.querySelector('img')?.getAttribute('alt')||'BEAST action';}
  function repairA11y(root=document){
    root.querySelectorAll?.('button').forEach(button=>{if(!button.hasAttribute('type'))button.type='button';if(!button.getAttribute('aria-label')&&!(button.textContent||'').trim())button.setAttribute('aria-label',accessibleName(button));});
    root.querySelectorAll?.('button img,.beast-nav img,.beast-page-actions img').forEach(img=>{if(img.closest('button'))img.alt='';});
    root.querySelectorAll?.('canvas').forEach(canvas=>canvas.setAttribute('aria-hidden','true'));
    root.querySelectorAll?.('.beast-page').forEach((page,index)=>{page.setAttribute('role','region');const heading=page.querySelector('.beast-page-head h2,h1,h2');if(heading){if(!heading.id)heading.id=`beastPageHeading-${Date.now()}-${index}`;page.setAttribute('aria-labelledby',heading.id);$('beastMainViewport')?.setAttribute('aria-labelledby',heading.id);}});
    const active=window.BeastRouter?.active||document.body.dataset.beastPage;document.querySelectorAll('[data-beast-route]').forEach(btn=>{const current=btn.dataset.beastRoute===active;if(current)btn.setAttribute('aria-current','page');else btn.removeAttribute('aria-current');});
  }
  function routeStep(direction){const active=window.BeastRouter?.active||'studio',i=Math.max(0,pages.indexOf(active)),next=pages[(i+direction+pages.length)%pages.length];window.BeastRouter?.navigate?.(next);announce(`${next} page`);}
  function cycleRegions(){const regions=[$('beastMainViewport'),document.querySelector('.beast-sidebar'),document.querySelector('.beast-rail'),document.querySelector('.beast-command')].filter(el=>el&&getComputedStyle(el).display!=='none');const current=regions.indexOf(document.activeElement.closest?.('.beast-viewport,.beast-sidebar,.beast-rail,.beast-command'));const target=regions[(current+1)%regions.length];if(!target)return;target.tabIndex=target.tabIndex<0?0:target.tabIndex;target.focus();announce(target.getAttribute('aria-label')||'BEAST region');}

  function bind(){
    $('beastAccessToggle')?.addEventListener('click',()=>openPanel($('beastAccessPanel')?.hidden));$('beastAccessClose')?.addEventListener('click',()=>openPanel(false));
    const handlers={beastTextScale:'textScale',beastContrastMode:'contrast',beastMotionMode:'motion',beastAtmosphereMode:'atmosphere'};
    for(const[id,key]of Object.entries(handlers))$(id)?.addEventListener('change',event=>{settings[key]=event.target.value;applySettings({announceChange:true});});
    $('beastAdaptiveEffects')?.addEventListener('change',event=>{settings.adaptive=event.target.checked;applySettings({announceChange:true});monitorPerformance();});
    document.addEventListener('keydown',event=>{const mod=event.ctrlKey||event.metaKey;if(mod&&event.key.toLowerCase()==='k'){event.preventDefault();$('beastCommandInput')?.focus();announce('Command input focused');}if(mod&&event.shiftKey&&event.key.toLowerCase()==='l'){event.preventDefault();openPanel($('beastAccessPanel')?.hidden);}if(event.key==='F6'){event.preventDefault();cycleRegions();}if(event.altKey&&event.key==='ArrowRight'){event.preventDefault();routeStep(1);}if(event.altKey&&event.key==='ArrowLeft'){event.preventDefault();routeStep(-1);}if(event.key==='Escape'&&!$('beastAccessPanel')?.hidden)openPanel(false);});
    document.addEventListener('beast:route-start',()=>{$('beastPageOutlet')?.setAttribute('aria-busy','true');});
    document.addEventListener('beast:route-complete',event=>{const outlet=$('beastPageOutlet');outlet?.setAttribute('aria-busy','false');repairA11y(outlet||document);const page=event.detail?.page||window.BeastRouter?.active;announce(`${page} workspace loaded`);requestAnimationFrame(()=>$('beastMainViewport')?.focus({preventScroll:true}));});
    addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{syncControls();document.body.dataset.viewport=innerWidth<760?'compact':innerWidth<1180?'narrow':innerWidth<1540?'medium':'wide';},120);},{passive:true});
  }
  function init(){if(initialized)return;initialized=true;settings=read();document.body.dataset.viewport=innerWidth<760?'compact':innerWidth<1180?'narrow':innerWidth<1540?'medium':'wide';setTier(initialTier(),'hardware profile');bind();applySettings({persist:false});repairA11y(document);observer=new MutationObserver(records=>{for(const record of records)for(const node of record.addedNodes)if(node.nodeType===1)repairA11y(node);});observer.observe(document.body,{childList:true,subtree:true});monitorPerformance();announce('BEAST IDE RC4 accessibility and performance layer online');}
  function destroy(){observer?.disconnect();observer=null;cancelAnimationFrame(perfRAF);performanceObserver?.disconnect?.();performanceObserver=null;initialized=false;}
  window.BeastAccessibility={init,destroy,applySettings,repairA11y,setTier,get settings(){return{...settings};}};
})();
