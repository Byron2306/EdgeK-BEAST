(() => {
  'use strict';
  const key='beast.v2.page-session';
  let sessions={}; let active=''; let bound=false;
  try{sessions=JSON.parse(sessionStorage.getItem(key)||'{}')||{}}catch(_){sessions={}}
  const viewport=()=>document.querySelector('.beast-viewport');
  function descriptor(element){
    if(!element||element===document.body)return '';
    if(element.id)return `#${CSS.escape(element.id)}`;
    const attrs=['data-editor-tab','data-file-path','data-model-id','data-agent-id','data-map-node','data-crystal-candidate','data-nav'];
    for(const attr of attrs){const value=element.getAttribute?.(attr);if(value)return `[${attr}="${CSS.escape(value)}"]`}
    return '';
  }
  function capture(page=active){
    if(!page)return; const v=viewport();
    sessions[page]={scrollTop:v?.scrollTop||0,focus:descriptor(document.activeElement),at:Date.now()};
    sessionStorage.setItem(key,JSON.stringify(sessions));
  }
  async function restore(page){
    active=page; const saved=sessions[page]; if(!saved)return;
    await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
    const v=viewport(); if(v)v.scrollTop=Math.max(0,Number(saved.scrollTop)||0);
    if(saved.focus){const el=document.querySelector(saved.focus);if(el&&typeof el.focus==='function')el.focus({preventScroll:true})}
  }
  function init(){
    if(bound)return;bound=true;
    document.addEventListener('beast:route-start',event=>{capture(active);active=event.detail.page;document.getElementById('beastPageOutlet')?.setAttribute('data-transitioning','true')});
    document.addEventListener('beast:route-complete',event=>{document.getElementById('beastPageOutlet')?.removeAttribute('data-transitioning');restore(event.detail.page)});
    window.addEventListener('beforeunload',()=>capture(active));
  }
  window.BeastPageSession={init,capture,restore,get active(){return active}};
})();
