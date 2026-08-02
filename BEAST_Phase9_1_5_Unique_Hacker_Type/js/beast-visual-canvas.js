(() => {
  const active = new Set();
  const reduceMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

  function fitCanvas(canvas) {
    const rect = canvas.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const width = Math.max(1, Math.round(rect.width));
    const height = Math.max(1, Math.round(rect.height));
    if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
    }
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx, width, height };
  }

  function glowLine(ctx, points, alpha = .36, width = 1.2, dash = []) {
    ctx.save();
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.setLineDash(dash);
    ctx.strokeStyle = `rgba(119,255,61,${alpha})`;
    ctx.lineWidth = width;
    ctx.shadowColor = 'rgba(119,255,61,.42)';
    ctx.shadowBlur = 8;
    ctx.beginPath();
    points.forEach(([x,y], index) => index ? ctx.lineTo(x,y) : ctx.moveTo(x,y));
    ctx.stroke();
    ctx.restore();
  }

  function pulse(ctx, path, t, tone = 'green') {
    if (path.length < 2) return;
    const segments = [];
    let total = 0;
    for (let i=1;i<path.length;i++) {
      const dx=path[i][0]-path[i-1][0], dy=path[i][1]-path[i-1][1];
      const len=Math.hypot(dx,dy); segments.push({a:path[i-1],b:path[i],len,start:total}); total+=len;
    }
    let distance = (t % 1) * total;
    const seg = segments.find(s => distance <= s.start+s.len) || segments[segments.length-1];
    const p = Math.max(0,Math.min(1,(distance-seg.start)/Math.max(1,seg.len)));
    const x=seg.a[0]+(seg.b[0]-seg.a[0])*p, y=seg.a[1]+(seg.b[1]-seg.a[1])*p;
    const color = tone === 'amber' ? '255,189,50' : '119,255,61';
    ctx.save();
    ctx.fillStyle=`rgba(${color},.96)`;ctx.shadowColor=`rgba(${color},.95)`;ctx.shadowBlur=15;
    ctx.beginPath();ctx.arc(x,y,3.2,0,Math.PI*2);ctx.fill();ctx.restore();
  }

  function relativeCenter(container, element) {
    const a=container.getBoundingClientRect(), b=element.getBoundingClientRect();
    return [b.left-a.left+b.width/2,b.top-a.top+b.height/2];
  }

  function mount(canvas, mode) {
    if (!canvas || canvas.dataset.visualMounted === 'true') return () => {};
    canvas.dataset.visualMounted='true';
    const host=canvas.parentElement;
    let raf=0, disposed=false, last=performance.now();
    const observer=new ResizeObserver(() => fitCanvas(canvas)); observer.observe(host);

    function routeFrame(now) {
      if (disposed) return;
      const {ctx,width:w,height:h}=fitCanvas(canvas);ctx.clearRect(0,0,w,h);
      const nodes=[...host.querySelectorAll('.route-map-node')];
      if (nodes.length >= 5) {
        const pts=nodes.map(n=>relativeCenter(host,n));
        const paths=[
          [pts[0],pts[1],pts[2]],
          [pts[1],[pts[1][0]+(pts[3][0]-pts[1][0])*.48,pts[3][1]],pts[3]],
          [pts[1],[pts[1][0]+(pts[4][0]-pts[1][0])*.48,pts[4][1]],pts[4]]
        ];
        paths.forEach((p,i)=>{glowLine(ctx,p,i? .24:.43,i?1:1.4,i?[5,6]:[]);pulse(ctx,p,(now/4200+i*.29)%1,i===2?'amber':'green');});
      }
      if (!reduceMotion()) raf=requestAnimationFrame(routeFrame);
    }

    function orbitFrame(now) {
      if (disposed) return;
      const {ctx,width:w,height:h}=fitCanvas(canvas);ctx.clearRect(0,0,w,h);
      const core=host.querySelector('.agent-core-node');
      const nodes=[...host.querySelectorAll('.agent-orbit-node')];
      const center=core?relativeCenter(host,core):[w/2,h/2];
      ctx.save();
      [Math.min(w,h)*.25,Math.min(w,h)*.39].forEach((r,index)=>{
        ctx.strokeStyle=`rgba(119,255,61,${index?.09:.17})`;ctx.lineWidth=1;ctx.setLineDash(index?[3,7]:[1,5]);ctx.beginPath();ctx.arc(center[0],center[1],r,0,Math.PI*2);ctx.stroke();
      });ctx.restore();
      nodes.forEach((node,index)=>{
        const p=relativeCenter(host,node);const mid=[center[0]+(p[0]-center[0])*.52,center[1]+(p[1]-center[1])*.52];
        const path=[center,mid,p];glowLine(ctx,path,.18,1,[3,6]);pulse(ctx,path,(now/5200+index/nodes.length)%1);
      });
      if (!reduceMotion()) raf=requestAnimationFrame(orbitFrame);
    }

    function memoryFrame(now) {
      if (disposed) return;
      const {ctx,width:w,height:h}=fitCanvas(canvas);ctx.clearRect(0,0,w,h);
      const nodes=[...host.querySelectorAll('.memory-star')];
      if (nodes.length) {
        const pts=nodes.map(n=>relativeCenter(host,n));
        const core=pts[0];
        const links=[];
        for(let i=1;i<pts.length;i++) links.push([core,pts[i]]);
        for(let i=1;i<pts.length-1;i++) if(i%2) links.push([pts[i],pts[i+1]]);
        links.forEach((p,index)=>{glowLine(ctx,p,.17+(index%3)*.035,1,[3,7]);pulse(ctx,p,(now/6100+index*.17)%1);});
        ctx.save();ctx.strokeStyle='rgba(119,255,61,.11)';ctx.lineWidth=1;
        for(let r=45;r<Math.min(w,h)*.42;r+=42){ctx.beginPath();ctx.arc(core[0],core[1],r,0,Math.PI*2);ctx.stroke();}
        ctx.restore();
      }
      if (!reduceMotion()) raf=requestAnimationFrame(memoryFrame);
    }

    const frame = mode==='route'?routeFrame:mode==='orbit'?orbitFrame:memoryFrame;
    frame(last);
    const disposer=()=>{disposed=true;cancelAnimationFrame(raf);observer.disconnect();canvas.dataset.visualMounted='false';active.delete(disposer);};
    active.add(disposer);return disposer;
  }

  function auto(root=document) {
    const disposers=[];
    root.querySelectorAll('[data-premium-canvas]').forEach(canvas=>disposers.push(mount(canvas,canvas.dataset.premiumCanvas)));
    return () => disposers.forEach(fn=>fn());
  }

  window.BeastVisualCanvas={mount,auto,disposeAll(){[...active].forEach(fn=>fn());}};
})();
