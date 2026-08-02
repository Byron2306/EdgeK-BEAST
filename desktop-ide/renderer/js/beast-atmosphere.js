(() => {
  let bgRAF=0, frontRAF=0, running=false, resizeHandler=null;
  const glyphs='01<>[]{}λΣΔΞ::BEAST//ROOT#@';

  function controller(canvas,{step,fontSize,speedMin,speedMax,alphaMin,alphaMax,trailMin,trailMax,fade,brightHeads=false}) {
    if(!canvas) return null;
    const ctx=canvas.getContext('2d');
    let width=0,height=0,dpr=1,columns=[];
    function resize(){
      dpr=Math.min(devicePixelRatio||1,2); width=innerWidth; height=innerHeight;
      canvas.width=Math.floor(width*dpr); canvas.height=Math.floor(height*dpr);
      canvas.style.width=width+'px'; canvas.style.height=height+'px';
      ctx.setTransform(dpr,0,0,dpr,0,0);
      columns=Array.from({length:Math.ceil(width/step)},(_,i)=>({
        x:i*step+Math.random()*5, y:-Math.random()*height,
        speed:speedMin+Math.random()*(speedMax-speedMin),
        trail:trailMin+Math.floor(Math.random()*(trailMax-trailMin+1)),
        alpha:alphaMin+Math.random()*(alphaMax-alphaMin), phase:Math.random()*glyphs.length
      }));
    }
    function draw(){
      ctx.fillStyle=`rgba(0,2,1,${fade})`; ctx.fillRect(0,0,width,height);
      ctx.font=`700 ${fontSize}px ui-monospace,SFMono-Regular,Consolas,monospace`;
      const tick=Math.floor(performance.now()/150);
      columns.forEach((col,index)=>{
        for(let j=0;j<col.trail;j++){
          const fall=1-j/col.trail;
          const a=col.alpha*fall*fall;
          const ch=glyphs[(index+j+tick+Math.floor(col.phase))%glyphs.length];
          if(brightHeads&&j===0){
            ctx.shadowColor='rgba(151,255,99,.95)';ctx.shadowBlur=9;ctx.fillStyle=`rgba(220,255,205,${Math.min(.92,a*2.5)})`;
          } else {ctx.shadowBlur=0;ctx.fillStyle=`rgba(119,255,61,${a})`;}
          ctx.fillText(ch,col.x,col.y-j*(fontSize+5));
        }
        ctx.shadowBlur=0; col.y+=col.speed*3.25;
        if(col.y-col.trail*(fontSize+5)>height){col.y=-Math.random()*220;col.speed=speedMin+Math.random()*(speedMax-speedMin);}
      });
    }
    resize(); return {resize,draw};
  }

  function start(){
    if(running) return; running=true;
    if(matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const bg=controller(document.getElementById('beastMatrix'),{step:21,fontSize:13,speedMin:.48,speedMax:1.25,alphaMin:.16,alphaMax:.38,trailMin:7,trailMax:16,fade:.095,brightHeads:true});
    const front=controller(document.getElementById('beastMatrixFront'),{step:58,fontSize:12,speedMin:.30,speedMax:.72,alphaMin:.055,alphaMax:.14,trailMin:4,trailMax:9,fade:.16,brightHeads:true});
    function bgLoop(){bg?.draw();bgRAF=requestAnimationFrame(bgLoop)}
    function frontLoop(){front?.draw();frontRAF=requestAnimationFrame(frontLoop)}
    resizeHandler=()=>{bg?.resize();front?.resize()}; addEventListener('resize',resizeHandler,{passive:true});
    bgLoop(); frontLoop();
  }
  function stop(){running=false;cancelAnimationFrame(bgRAF);cancelAnimationFrame(frontRAF);if(resizeHandler)removeEventListener('resize',resizeHandler);}
  window.BeastAtmosphere={start,stop};
})();
