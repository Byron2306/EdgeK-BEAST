(() => {
  'use strict';
  let interval=0; let debounce=0; let observer=null; let running=false;
  function inspect(){
    if(!running||document.hidden)return;
    const outlet=document.getElementById('beastPageOutlet');
    const children=outlet?[...outlet.children]:[];
    if(children.length>1){children.slice(0,-1).forEach(node=>node.remove());BeastStore.addLedger(`Watchdog removed ${children.length-1} stale page root(s)`)}
    const ids=[...document.querySelectorAll('[id]')].map(el=>el.id); const duplicates=ids.filter((id,i)=>ids.indexOf(id)!==i);
    const viewport=document.querySelector('.beast-viewport');
    const runtime=window.BeastRuntime?.diagnostics?.()||{};
    const next={
      duplicateIds:new Set(duplicates).size,outletChildren:outlet?.children.length||0,
      horizontalOverflow:document.documentElement.scrollWidth>document.documentElement.clientWidth+2,
      viewport:`${innerWidth}×${innerHeight}@${Math.round(devicePixelRatio*100)}%`,
      activeEditors:document.querySelectorAll('.monaco-editor:not(.diff-editor .monaco-editor)').length,
      activeDiffEditors:document.querySelectorAll('.monaco-diff-editor').length,
      runtimeMode:runtime.mode||'offline',inFlight:runtime.inFlight||0
    };
    const current=BeastStore.get().diagnostics||{};
    if(Object.keys(next).some(key=>current[key]!==next[key]))BeastStore.patch('diagnostics',next);
    if(viewport && viewport.scrollWidth>viewport.clientWidth+4) document.body.dataset.viewportOverflow='true'; else delete document.body.dataset.viewportOverflow;
  }
  function init(){if(running)return;running=true;observer=new MutationObserver(()=>{clearTimeout(debounce);debounce=setTimeout(inspect,80)});observer.observe(document.body,{subtree:true,childList:true});interval=setInterval(inspect,1600);inspect()}
  function destroy(){running=false;observer?.disconnect();observer=null;clearTimeout(debounce);clearInterval(interval);debounce=0;interval=0}
  window.BeastRuntimeWatchdog={init,destroy,inspect};
})();
