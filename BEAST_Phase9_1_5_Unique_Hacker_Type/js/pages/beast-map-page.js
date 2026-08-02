(() => {
  const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const clamp=value=>Math.max(0,Math.min(100,Number(value)||0));
  const iconFor=node=>node.type==='agent'?'agents':node.type==='store'?'evidence':node.type==='external'?'network':node.type==='entry'?'target-lock':node.type==='risk'?'alerts':'project';

  function template(){
    const root=document.createElement('div');
    root.className='beast-page beast-map-page';
    root.innerHTML=`
      <header class="beast-page-head">
        <div><h2>Mission Map</h2><div class="sub">STABLE GRAPH CANVAS // DEPENDENCY TOPOLOGY // IMPACT TRACE // ORPHAN HUNT</div></div>
        <div class="beast-page-actions">
          <button class="beast-button secondary" data-map-action="refresh"><img src="${BeastAssets.icon('network')}" alt="">Refresh Graph</button>
          <button class="beast-button hot" data-map-action="fit"><img src="${BeastAssets.icon('target-lock')}" alt="">Fit Topology</button>
        </div>
      </header>
      <section class="map-summary-grid">
        <article class="beast-card map-summary-card"><img src="${BeastAssets.icon('map')}" alt=""><div><h3>Map Health</h3><strong data-map-health>0%</strong><span>topology integrity</span></div></article>
        <article class="beast-card map-summary-card"><img src="${BeastAssets.icon('project')}" alt=""><div><h3>Graph Nodes</h3><strong data-map-nodes>0</strong><span>active mission entities</span></div></article>
        <article class="beast-card map-summary-card"><img src="${BeastAssets.icon('network')}" alt=""><div><h3>Dependency Links</h3><strong data-map-edges>0</strong><span>verified relationships</span></div></article>
        <article class="beast-card map-summary-card"><img src="${BeastAssets.icon('alerts')}" alt=""><div><h3>Orphaned Nodes</h3><strong data-map-orphans>0</strong><span>requiring attention</span></div></article>
      </section>
      <div class="map-main-grid">
        <section class="beast-card wide map-canvas-panel beast-hacker-flicker">
          <header class="beast-panel-head"><div><h3>Code Graph Constellation</h3><span data-map-status>Awaiting topology</span></div><span class="beast-pill live">CANVAS OWNER: 1</span></header>
          <div class="map-toolbar">
            <input class="map-search" data-map-query placeholder="Filter nodes, files, symbols…">
            <div class="map-filter-row" data-map-filters>
              <button class="active" data-map-filter="all">All</button><button data-map-filter="entry">Core</button><button data-map-filter="parser">Code</button><button data-map-filter="agent">Agents</button><button data-map-filter="store">Stores</button><button data-map-filter="external">External</button><button data-map-filter="risk">Risks</button>
            </div>
            <div class="map-zoom-row"><button data-map-action="zoom-out">−</button><button data-map-zoom-label>100%</button><button data-map-action="zoom-in">+</button></div>
          </div>
          <div class="map-stage beast-target" data-map-stage>
            <div class="beast-data-noise"></div>
            <div class="map-world" data-map-world>
              <canvas class="map-edge-canvas" data-map-canvas></canvas>
              <div class="map-node-layer" data-map-node-layer></div>
            </div>
          </div>
        </section>
        <section class="beast-card map-inspector-panel" data-map-inspector></section>
      </div>
      <div class="map-lower-grid">
        <section class="beast-card map-health-panel"><header class="beast-panel-head"><div><h3>Map Health</h3><span>Coverage · freshness · consistency</span></div></header><div class="map-health-orbit" data-map-health-orbit><span data-map-health-orbit-value>0%</span></div><div class="beast-rail-facts"><div><span>Coverage</span><b data-map-coverage>0%</b></div><div><span>Freshness</span><b data-map-freshness>0%</b></div><div><span>Consistency</span><b data-map-consistency>0%</b></div><div><span>Orphans</span><b data-map-orphan-fact>0</b></div></div></section>
        <section class="beast-card map-legend-panel"><header class="beast-panel-head"><div><h3>Topology Legend</h3><span>Node and relation semantics</span></div></header><div class="map-legend-grid"><span><i style="--tone:#77ff3d"></i>Core / entry</span><span><i style="--tone:#52e7ff"></i>Parser / code</span><span><i style="--tone:#9a70ff"></i>Agent</span><span><i style="--tone:#ffbd32"></i>Store / evidence</span><span><i style="--tone:#61ffd5"></i>External dependency</span><span><i style="--tone:#ff4938"></i>Risk / orphan</span></div><p>The graph canvas uses one HTML node layer and one Canvas connection layer. It does not reconstruct the page when a node is selected.</p></section>
        <section class="beast-card map-impact-panel"><header class="beast-panel-head"><div><h3>Impact Trace</h3><span data-impact-count>0 related paths</span></div><button class="beast-button secondary" data-map-action="focus-selected"><img src="${BeastAssets.icon('context')}" alt="">Focus</button></header><div class="map-impact-list" data-map-impact></div></section>
      </div>`;
    return root;
  }

  function renderer({signal}){
    const root=template();
    let disposed=false,raf=0,drawRAF=0,lastNodesKey='',lastInspectorKey='';
    const stage=root.querySelector('[data-map-stage]');
    const world=root.querySelector('[data-map-world]');
    const canvas=root.querySelector('[data-map-canvas]');
    const ctx=canvas.getContext('2d');

    function filtered(state){
      const query=state.map.query.trim().toLowerCase();
      return state.map.nodes.filter(node=>(state.map.filter==='all'||node.type===state.map.filter)&&(!query||`${node.label} ${node.path} ${node.type} ${node.language}`.toLowerCase().includes(query)));
    }

    function renderNodes(state){
      const visible=filtered(state);const key=JSON.stringify([visible.map(n=>[n.id,n.x,n.y,n.type]),state.map.selectedId]);
      if(key===lastNodesKey)return;lastNodesKey=key;
      root.querySelector('[data-map-node-layer]').innerHTML=visible.map((node,index)=>`<button class="map-node ${esc(node.type)} ${node.id===state.map.selectedId?'selected':''}" style="--x:${node.x}%;--y:${node.y}%;--delay:${index*-.18}s" data-map-node="${esc(node.id)}"><img src="${BeastAssets.icon(iconFor(node))}" alt=""><span><b>${esc(node.label)}</b><small>${esc(node.type)}</small></span><i></i></button>`).join('')||'<div class="map-empty">No nodes match the active graph filter.</div>';
      queueDraw();
    }

    function renderInspector(state){
      const node=state.map.nodes.find(item=>item.id===state.map.selectedId)||state.map.nodes[0];
      const related=node?state.map.edges.filter(edge=>edge.source===node.id||edge.target===node.id):[];
      const key=JSON.stringify([node,related]);if(key===lastInspectorKey)return;lastInspectorKey=key;
      root.querySelector('[data-map-inspector]').innerHTML=node?`<header class="beast-panel-head"><div><h3>Selected Node</h3><span>${esc(node.type)} · ${esc(node.language)}</span></div><span class="beast-pill live">FRESH ${clamp(node.freshness)}%</span></header><div class="map-node-hero"><img src="${BeastAssets.icon(iconFor(node))}" alt=""><div><strong>${esc(node.label)}</strong><span>${esc(node.path)}</span></div></div><p class="map-description">${esc(node.description)}</p><div class="beast-rail-facts"><div><span>Type</span><b>${esc(node.type)}</b></div><div><span>Language</span><b>${esc(node.language)}</b></div><div><span>Coverage</span><b>${clamp(node.coverage)}%</b></div><div><span>Freshness</span><b>${clamp(node.freshness)}%</b></div><div><span>Links</span><b>${related.length}</b></div><div><span>State</span><b>${node.type==='risk'?'Review':'Verified'}</b></div></div><header class="beast-panel-head"><div><h3>Dependencies</h3><span>${related.length} direct links</span></div></header><div class="map-dependency-list">${related.slice(0,8).map(edge=>{const other=state.map.nodes.find(item=>item.id===(edge.source===node.id?edge.target:edge.source));return other?`<button class="map-dependency-row" data-map-node="${esc(other.id)}"><img src="${BeastAssets.icon(iconFor(other))}" alt=""><span><b>${esc(other.label)}</b><span>${esc(edge.type)}</span></span><em>${edge.source===node.id?'OUT':'IN'}</em></button>`:''}).join('')||'<div class="cortex-empty-list">No direct dependencies.</div>'}</div>`:'<h3>Selected Node</h3><p>Select a graph node to inspect its mission impact.</p>';
      root.querySelector('[data-map-impact]').innerHTML=related.slice(0,7).map(edge=>{const other=state.map.nodes.find(item=>item.id===(edge.source===node?.id?edge.target:edge.source));return `<article><b>${esc(other?.label||'Unknown node')}</b><span>${esc(edge.type)} · ${edge.source===node?.id?'downstream':'upstream'}</span></article>`}).join('')||'<div class="cortex-empty-list">No impact paths selected.</div>';
      root.querySelector('[data-impact-count]').textContent=`${related.length} related paths`;
    }

    function patch(state){
      if(disposed)return;const map=state.map;
      root.querySelector('[data-map-health]').textContent=`${clamp(map.health)}%`;root.querySelector('[data-map-nodes]').textContent=map.nodes.length;root.querySelector('[data-map-edges]').textContent=map.edges.length;root.querySelector('[data-map-orphans]').textContent=map.orphaned;
      root.querySelector('[data-map-status]').textContent=map.loading?'Scanning repository topology…':map.error?`Resilient local map · ${map.error}`:`${map.nodes.length} nodes · ${map.edges.length} links · updated ${map.updatedAt?new Date(map.updatedAt).toLocaleTimeString():'pending'}`;
      root.querySelector('[data-map-world]').style.setProperty('--map-zoom',map.zoom);root.querySelector('[data-map-zoom-label]').textContent=`${Math.round(map.zoom*100)}%`;
      root.querySelector('[data-map-health-orbit]').style.setProperty('--health',clamp(map.health));root.querySelector('[data-map-health-orbit-value]').textContent=`${clamp(map.health)}%`;root.querySelector('[data-map-coverage]').textContent=`${clamp(map.coverage)}%`;root.querySelector('[data-map-freshness]').textContent=`${clamp(map.freshness)}%`;root.querySelector('[data-map-consistency]').textContent=`${clamp(map.consistency)}%`;root.querySelector('[data-map-orphan-fact]').textContent=map.orphaned;
      root.querySelectorAll('[data-map-filter]').forEach(button=>button.classList.toggle('active',button.dataset.mapFilter===map.filter));
      const query=root.querySelector('[data-map-query]');if(document.activeElement!==query)query.value=map.query;
      renderNodes(state);renderInspector(state);queueDraw();
    }

    function queueDraw(){cancelAnimationFrame(drawRAF);drawRAF=requestAnimationFrame(()=>draw(performance.now()));}
    function draw(time){
      if(disposed)return;const state=BeastStore.get();const visible=new Set(filtered(state).map(node=>node.id));const rect=stage.getBoundingClientRect();const dpr=Math.min(devicePixelRatio||1,2);canvas.width=Math.max(1,Math.round(rect.width*dpr));canvas.height=Math.max(1,Math.round(rect.height*dpr));canvas.style.width=`${rect.width}px`;canvas.style.height=`${rect.height}px`;ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,rect.width,rect.height);
      const buttons=new Map([...root.querySelectorAll('[data-map-node]')].filter(el=>el.classList.contains('map-node')).map(el=>[el.dataset.mapNode,el]));const stageRect=stage.getBoundingClientRect();
      state.map.edges.forEach((edge,index)=>{if(!visible.has(edge.source)||!visible.has(edge.target))return;const a=buttons.get(edge.source),b=buttons.get(edge.target);if(!a||!b)return;const ar=a.getBoundingClientRect(),br=b.getBoundingClientRect();const x1=(ar.left+ar.width/2-stageRect.left)/state.map.zoom,y1=(ar.top+ar.height/2-stageRect.top)/state.map.zoom,x2=(br.left+br.width/2-stageRect.left)/state.map.zoom,y2=(br.top+br.height/2-stageRect.top)/state.map.zoom;const dx=Math.abs(x2-x1)*.45;const tones={green:'119,255,61',cyan:'82,231,255',violet:'154,112,255',amber:'255,189,50',red:'255,73,56'};const rgb=tones[edge.tone]||tones.green;ctx.beginPath();ctx.moveTo(x1,y1);ctx.bezierCurveTo(x1+Math.sign(x2-x1)*dx,y1,x2-Math.sign(x2-x1)*dx,y2,x2,y2);const selectedEdge=edge.source===state.map.selectedId||edge.target===state.map.selectedId;ctx.strokeStyle=`rgba(${rgb},${selectedEdge ? .68 : .22})`;ctx.lineWidth=selectedEdge?1.8:1;ctx.setLineDash(edge.type==='handoff'?[5,4]:[2,4]);ctx.lineDashOffset=-(time/42+index*3);ctx.stroke();});
      if(new URLSearchParams(location.search).get('capture')!=='1') raf=requestAnimationFrame(draw);
    }

    const observer=new ResizeObserver(queueDraw);observer.observe(stage);
    const unsubscribe=BeastStore.subscribe(patch);
    root.addEventListener('input',event=>{if(event.target.matches('[data-map-query]'))BeastMapCrystalBridge.setMapQuery(event.target.value)});
    root.addEventListener('click',async event=>{
      const node=event.target.closest('[data-map-node]');if(node){BeastMapCrystalBridge.selectMapNode(node.dataset.mapNode);BeastFX.trigger('ring',node,{size:180});return;}
      const filter=event.target.closest('[data-map-filter]');if(filter){BeastMapCrystalBridge.setMapFilter(filter.dataset.mapFilter);return;}
      const action=event.target.closest('[data-map-action]')?.dataset.mapAction;if(!action)return;
      try{
        if(action==='refresh'){await BeastMapCrystalBridge.refreshMap({signal});BeastFX.trigger('burst',event.target,{size:250})}
        if(action==='fit'){BeastMapCrystalBridge.setMapZoom(1);BeastFX.trigger('grid',stage,{size:520})}
        if(action==='zoom-in')BeastMapCrystalBridge.setMapZoom(BeastStore.get().map.zoom+.1);
        if(action==='zoom-out')BeastMapCrystalBridge.setMapZoom(BeastStore.get().map.zoom-.1);
        if(action==='focus-selected'){BeastMapCrystalBridge.setMapFilter('all');BeastMapCrystalBridge.setMapQuery('');BeastMapCrystalBridge.setMapZoom(1.18);BeastFX.trigger('radar',stage,{size:420})}
      }catch(error){BeastStore.patch('map',{loading:false,error:String(error.message||error)});BeastFX.trigger('warning',event.target,{size:240})}
    });
    if(!BeastStore.get().map.updatedAt)queueMicrotask(()=>BeastMapCrystalBridge.refreshMap({signal}).catch(()=>{}));
    return{node:root,dispose(){disposed=true;unsubscribe();observer.disconnect();cancelAnimationFrame(raf);cancelAnimationFrame(drawRAF)}};
  }
  window.BeastMapPage={renderer};
})();
