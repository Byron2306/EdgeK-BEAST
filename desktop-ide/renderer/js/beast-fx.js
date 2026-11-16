
(() => {
  let matrixRAF=0;
  const captureMode=new URLSearchParams(location.search).get('capture')==='1';
  function trigger(name,target=document.body,options={}){
    const layer=document.getElementById('beastFxLayer');
    if(!layer)return;
    const r=target.getBoundingClientRect?.() || {left:innerWidth/2,top:innerHeight/2,width:0,height:0};
    const img=document.createElement('img');
    img.className='beast-fx-instance';
    img.src=BeastAssets.effect(name);
    img.style.left=`${options.x ?? r.left+r.width/2}px`;
    img.style.top=`${options.y ?? r.top+r.height/2}px`;
    img.style.width=`${options.size || 320}px`;
    layer.appendChild(img);
    setTimeout(()=>img.remove(),900);
  }
  function matrix(){
    if (window.BeastAtmosphere?.start) { window.BeastAtmosphere.start(); return; }
  }
  function logoFlicker(){
    const el=document.querySelector('.beast-ascii');
    if(!el)return;
    setInterval(()=>{
      if(Math.random()>.7){el.style.clipPath=`inset(${Math.random()*45}% 0 ${Math.random()*35}% 0)`;setTimeout(()=>el.style.clipPath='',45+Math.random()*70);}
    },1100);
  }
  window.BeastFX={trigger,matrix,logoFlicker,stop(){cancelAnimationFrame(matrixRAF);}};
})();
