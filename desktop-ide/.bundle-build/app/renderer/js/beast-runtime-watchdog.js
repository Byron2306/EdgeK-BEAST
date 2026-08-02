(() => {
  'use strict';
  let interval=0,debounce=0,observer=null,running=false;
  function inspect(){
    if(!running||document.hidden)return;
    const store=window.BeastStore;
    const outlet=document.getElementById('beastPageOutlet');
    const children=outlet?[...outlet.children].filter(node=>node.nodeType===1):[];
    if(children.length>1){children.slice(0,-1).forEach(node=>node.remove());store?.addLedger?.(`Watchdog removed ${children.length-1} stale page root(s)`);}
    const ids=[...document.querySelectorAll('[id]')].map(el=>el.id);
    const duplicates=[...new Set(ids.filter((id,index)=>ids.indexOf(id)!==index))];
    const viewport=document.querySelector('.beast-viewport');
    const runtime=window.BeastRuntime?.diagnostics?.()||{};
    const next={
      duplicateIds:duplicates.length,
      outletChildren:outlet?.children.length||0,
      horizontalOverflow:document.documentElement.scrollWidth>document.documentElement.clientWidth+2,
      viewport:`${innerWidth}×${innerHeight}@${Math.round((devicePixelRatio||1)*100)}%`,
      activeEditors:document.querySelectorAll('.monaco-editor:not(.diff-editor .monaco-editor)').length,
      activeDiffEditors:document.querySelectorAll('.monaco-diff-editor').length,
      runtimeMode:runtime.mode||'offline',
      inFlight:runtime.inFlight||0,
      visualOwner:document.body.dataset.beastVisualOwner||'pending'
    };
    if(store?.get&&store?.patch){const current=store.get().diagnostics||{};if(Object.keys(next).some(key=>current[key]!==next[key]))store.patch('diagnostics',next);}
    if(viewport&&viewport.scrollWidth>viewport.clientWidth+4)document.body.dataset.viewportOverflow='true';else delete document.body.dataset.viewportOverflow;
  }
  function init(){if(running)return;running=true;observer=new MutationObserver(()=>{clearTimeout(debounce);debounce=setTimeout(inspect,100);});observer.observe(document.body,{subtree:true,childList:true});interval=setInterval(inspect,1800);setTimeout(inspect,0);}
  function destroy(){running=false;observer?.disconnect();observer=null;clearTimeout(debounce);clearInterval(interval);debounce=0;interval=0;}
  window.BeastRuntimeWatchdog={init,destroy,inspect};
})();
