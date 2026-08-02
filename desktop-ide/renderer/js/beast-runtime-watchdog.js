(() => {
  'use strict';
  let interval=0,debounce=0,observer=null,running=false,lastHeavy=0;
  const idle=window.requestIdleCallback||((fn)=>setTimeout(()=>fn({timeRemaining:()=>0}),120));
  function inspect(){
    if(!running||document.hidden)return;
    const store=window.BeastStore;
    const outlet=document.getElementById('beastPageOutlet');
    const children=outlet?[...outlet.children].filter(node=>node.nodeType===1):[];
    if(children.length>1){children.slice(0,-1).forEach(node=>node.remove());store?.addLedger?.(`Watchdog removed ${children.length-1} stale page root(s)`);}
    const now=Date.now();
    const runHeavy=now-lastHeavy>10000;
    if(runHeavy)lastHeavy=now;
    const duplicates=runHeavy?duplicateIds():[];
    const viewport=document.querySelector('.beast-viewport');
    const runtime=window.BeastRuntime?.diagnostics?.()||{};
    const next={
      duplicateIds:runHeavy?duplicates.length:(store?.get?.().diagnostics?.duplicateIds||0),
      outletChildren:outlet?.children.length||0,
      horizontalOverflow:document.documentElement.scrollWidth>document.documentElement.clientWidth+2,
      viewport:`${innerWidth}×${innerHeight}@${Math.round((devicePixelRatio||1)*100)}%`,
      activeEditors:runHeavy?document.querySelectorAll('.monaco-editor:not(.diff-editor .monaco-editor)').length:(store?.get?.().diagnostics?.activeEditors||0),
      activeDiffEditors:runHeavy?document.querySelectorAll('.monaco-diff-editor').length:(store?.get?.().diagnostics?.activeDiffEditors||0),
      runtimeMode:runtime.mode||'offline',
      inFlight:runtime.inFlight||0,
      visualOwner:document.body.dataset.beastVisualOwner||'pending'
    };
    if(store?.get&&store?.patch){const current=store.get().diagnostics||{};if(Object.keys(next).some(key=>current[key]!==next[key]))store.patch('diagnostics',next);}
    if(viewport&&viewport.scrollWidth>viewport.clientWidth+4)document.body.dataset.viewportOverflow='true';else delete document.body.dataset.viewportOverflow;
  }
  function duplicateIds(){const seen=new Set(),duplicates=new Set();document.querySelectorAll('[id]').forEach(el=>{if(seen.has(el.id))duplicates.add(el.id);else seen.add(el.id)});return [...duplicates];}
  function schedule(delay=220){clearTimeout(debounce);debounce=setTimeout(()=>idle(inspect),delay);}
  function init(){if(running)return;running=true;const outlet=document.getElementById('beastPageOutlet');observer=new MutationObserver(()=>schedule(260));observer.observe(outlet||document.body,{childList:true,subtree:false});document.addEventListener('beast:route-complete',()=>schedule(40));interval=setInterval(inspect,12000);schedule(0);}
  function destroy(){running=false;observer?.disconnect();observer=null;clearTimeout(debounce);clearInterval(interval);debounce=0;interval=0;}
  window.BeastRuntimeWatchdog={init,destroy,inspect};
})();
