(() => {
  let observer=null, headerRaf=0, worldRafs=new Map(), resizeObserver=null;
  const canvases=new Set();
  const dpr=()=>Math.min(window.devicePixelRatio||1,2);
  function size(canvas){const r=canvas.getBoundingClientRect(),q=dpr();const w=Math.max(1,Math.round(r.width*q)),h=Math.max(1,Math.round(r.height*q));if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}const ctx=canvas.getContext('2d');ctx.setTransform(q,0,0,q,0,0);return{ctx,w:r.width,h:r.height};}
  function heartbeat(canvas, seed=0){
    const {ctx,w,h}=size(canvas);ctx.clearRect(0,0,w,h);const t=performance.now()/1000;ctx.strokeStyle='rgba(119,255,61,.72)';ctx.lineWidth=1.35;ctx.shadowColor='rgba(119,255,61,.85)';ctx.shadowBlur=6;ctx.beginPath();
    const base=h*.56;for(let x=0;x<=w;x+=2){const phase=(x/w*6+t*.55+seed)%1;let y=base+Math.sin(x*.055+t*1.1+seed)*2; if(phase>.43&&phase<.455)y-=h*.18; else if(phase>=.455&&phase<.48)y+=h*.31; else if(phase>=.48&&phase<.515)y-=h*.11; ctx.lineTo(x,y);}ctx.stroke();
    ctx.shadowBlur=0;ctx.fillStyle='rgba(119,255,61,.85)';ctx.beginPath();ctx.arc(w-6,base+Math.sin(w*.055+t*1.1+seed)*2,2.2,0,Math.PI*2);ctx.fill();
  }
  function headerPulse(){const c=document.getElementById('beastHeaderPulse');if(!c)return;heartbeat(c,3.7);headerRaf=requestAnimationFrame(headerPulse);}
  function world(canvas){
    const {ctx,w,h}=size(canvas);ctx.clearRect(0,0,w,h);const t=performance.now()/1000;
    const nodes=[[.18,.32],[.46,.31],[.68,.40],[.56,.70],[.84,.66]];
    ctx.strokeStyle='rgba(119,255,61,.19)';ctx.lineWidth=1;
    for(let i=0;i<nodes.length-1;i++){const a=nodes[i],b=nodes[i+1];ctx.beginPath();ctx.moveTo(a[0]*w,a[1]*h);ctx.quadraticCurveTo((a[0]+b[0])*.5*w,(Math.min(a[1],b[1])-.14)*h,b[0]*w,b[1]*h);ctx.stroke();}
    nodes.forEach((n,i)=>{const x=n[0]*w,y=n[1]*h,r=4+Math.sin(t*2+i)*1.4;ctx.fillStyle='rgba(164,255,117,.95)';ctx.shadowColor='#77ff3d';ctx.shadowBlur=12;ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fill();ctx.shadowBlur=0;ctx.strokeStyle='rgba(119,255,61,.34)';ctx.beginPath();ctx.arc(x,y,12+(t*8+i*4)%18,0,Math.PI*2);ctx.stroke();});
    const sweep=(t*.10)%1;const gx=sweep*w;const grd=ctx.createLinearGradient(gx-80,0,gx+80,0);grd.addColorStop(0,'transparent');grd.addColorStop(.5,'rgba(119,255,61,.14)');grd.addColorStop(1,'transparent');ctx.fillStyle=grd;ctx.fillRect(gx-80,0,160,h);
  }
  function worldLoop(canvas){if(!document.contains(canvas)){worldRafs.delete(canvas);return;}world(canvas);worldRafs.set(canvas,requestAnimationFrame(()=>worldLoop(canvas)));}
  function addHeartbeat(card,index=0){if(card.dataset.phase9Heartbeat)return;card.dataset.phase9Heartbeat='1';const c=document.createElement('canvas');c.className='beast-viz-canvas beast-viz-heartbeat';c.setAttribute('aria-hidden','true');card.appendChild(c);canvases.add(c);const loop=()=>{if(!document.contains(c))return;heartbeat(c,index*.9);requestAnimationFrame(loop)};requestAnimationFrame(loop);}
  function addWorld(card){if(card.dataset.phase9World)return;card.dataset.phase9World='1';const host=document.createElement('div');host.className='beast-viz-world';const c=document.createElement('canvas');c.className='beast-viz-canvas';host.appendChild(c);card.appendChild(host);canvases.add(c);worldLoop(c);}
  function enhance(root=document){
    const page=document.body.dataset.beastPage||'';
    root.querySelectorAll?.('.beast-card').forEach((card,index)=>{
      const title=(card.querySelector('h3')?.textContent||'').toLowerCase();
      if(/core health|system health|performance|analytics|runtime readiness|compute economy/.test(title)) addHeartbeat(card,index);
      if(/system topology|global node|network intelligence|mission map/.test(title) && !card.closest('.beast-map-page')) addWorld(card);
    });
    const studioTopology=root.querySelector?.('[data-studio-systems]')?.closest('.beast-card');if(studioTopology)addWorld(studioTopology);
    document.querySelectorAll('.beast-page-head').forEach(h=>h.dataset.phase9Header='1');
  }
  function init(){
    document.body.dataset.beastPhase='9';
    const viewport=document.querySelector('.beast-viewport');if(viewport&&!document.getElementById('beastPageScan')){const scan=document.createElement('div');scan.id='beastPageScan';scan.setAttribute('aria-hidden','true');viewport.prepend(scan);}
    cancelAnimationFrame(headerRaf);headerPulse();
    enhance(document);
    observer=new MutationObserver(records=>{for(const r of records){for(const n of r.addedNodes){if(n.nodeType===1)enhance(n);}}});observer.observe(document.body,{childList:true,subtree:true});
    resizeObserver=new ResizeObserver(()=>canvases.forEach(c=>{if(c.isConnected)size(c)}));document.querySelectorAll('.beast-viewport,.beast-rail,.beast-header').forEach(el=>resizeObserver.observe(el));
  }
  function update(){enhance(document);}
  function destroy(){observer?.disconnect();resizeObserver?.disconnect();cancelAnimationFrame(headerRaf);worldRafs.forEach(id=>cancelAnimationFrame(id));worldRafs.clear();}
  window.BeastPhase9Visuals={init,update,destroy};
})();
