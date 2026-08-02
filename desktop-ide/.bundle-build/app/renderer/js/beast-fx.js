(() => {
  'use strict';
  function trigger(name,target=document.body,options={}){
    const layer=document.getElementById('beastFxLayer');if(!layer)return;
    const rect=target.getBoundingClientRect?.()||{left:innerWidth/2,top:innerHeight/2,width:0,height:0};
    const image=document.createElement('img');image.className='beast-fx-instance';image.src=BeastAssets.effect(name);
    image.style.left=`${options.x??rect.left+rect.width/2}px`;image.style.top=`${options.y??rect.top+rect.height/2}px`;image.style.width=`${options.size||320}px`;
    layer.appendChild(image);setTimeout(()=>image.remove(),900);
  }
  function matrix(){window.BeastVisualRuntime?.start?.();}
  function logoFlicker(){document.querySelector('.beast-ascii')?.setAttribute('data-flicker','true');}
  window.BeastFX={trigger,matrix,logoFlicker,stop(){window.BeastVisualRuntime?.stop?.();}};
})();
