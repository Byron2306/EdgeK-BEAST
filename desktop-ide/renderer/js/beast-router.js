(() => {
  const routes=new Map();let active='',navigating='';
  function register(page,renderer){routes.set(page,renderer)}
  async function navigate(page,options={}){
    const aliases={'platform atlas':'atlas','system plane':'system','provider plane':'providers','compute economy':'economy','swarm lanes':'agents','memory atlas':'memory','chronicle ledger':'chronicle'};
    page=aliases[String(page||'').trim().toLowerCase()]||page;
    if(!routes.has(page))page='studio';if(active===page&&!options.force)return true;if(navigating===page&&!options.force)return false;
    const previous=active;navigating=page;document.body.dataset.beastPage=page;
    document.querySelectorAll('[data-beast-route]').forEach(el=>el.classList.toggle('active',el.dataset.beastRoute===page));
    document.dispatchEvent(new CustomEvent('beast:route-start',{detail:{page,previous}}));
    const committed=await BeastRenderScheduler.request(page,routes.get(page),options);
    navigating='';
    if(committed){active=page;try{history.replaceState(null,'',`${location.pathname}${location.search}#${page}`)}catch(_){}document.dispatchEvent(new CustomEvent('beast:route-complete',{detail:{page,previous}}));return true}
    document.body.dataset.beastPage=previous||'studio';document.querySelectorAll('[data-beast-route]').forEach(el=>el.classList.toggle('active',el.dataset.beastRoute===(previous||'studio')));return false;
  }
  window.BeastRouter={register,navigate,get active(){return active},get navigating(){return navigating}};
})();
