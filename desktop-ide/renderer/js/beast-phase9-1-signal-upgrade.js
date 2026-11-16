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
