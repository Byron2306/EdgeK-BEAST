(() => {
  const WORK_ROUTES = new Set(['workspace','terminal','testing','compatibility','source','worktrees']);
  const $ = id => document.getElementById(id);
  const text = (value, fallback='UNRESOLVED') => String(value ?? '').trim() || fallback;
  function classify(node, value) {
    node.classList.remove('good','warn','bad');
    const v=String(value||'').toLowerCase();
    node.classList.add(/active|ready|healthy|verified|low|connected|pass|trusted/.test(v)?'good':/fail|error|blocked|critical|denied/.test(v)?'bad':'warn');
  }
  function updateRibbon(state) {
    const mission=$('beastRibbonMission'), workspace=$('beastRibbonWorkspace'), trust=$('beastRibbonTrust'), lease=$('beastRibbonLease'), route=$('beastRibbonRoute'), pressure=$('beastRibbonPressure');
    if(!mission)return;
    mission.textContent=text(state.mission?.id || state.mission?.title || state.mission?.status,'UNASSIGNED');
    workspace.textContent=text((state.workspace?.root||'').split('/').filter(Boolean).pop(),'NO ROOT');
    trust.textContent=text(state.trust?.status,'CHECKING'); classify(trust,trust.textContent);
    const leaseValue=state.runtime?.processLease?.status || state.system?.processLease?.status || state.chronicle?.processLease?.status || (state.connection?.status==='connected'?'ACTIVE':'UNBOUND');
    lease.textContent=text(leaseValue,'UNBOUND'); classify(lease,lease.textContent);
    route.textContent=text(state.models?.active || state.aiCoding?.provider || state.models?.provider,'UNRESOLVED'); classify(route,route.textContent);
    const pressureValue=state.system?.pressure?.status || state.system?.psi?.status || state.economy?.pressure || 'UNKNOWN';
    pressure.textContent=text(pressureValue,'UNKNOWN'); classify(pressure,pressure.textContent);
  }
  function setMode(route){document.body.classList.toggle('beast-work-mode',WORK_ROUTES.has(route));}
  function ensureActiveGroupOpen(route){
    const active=document.querySelector(`[data-beast-route="${CSS.escape(route)}"]`);
    const group=active?.closest('.beast-nav-group'); if(!group)return;
    const toggle=group.querySelector('.beast-nav-group-toggle'), items=group.querySelector('.beast-nav-group-items');
    if(items?.hidden){items.hidden=false;toggle?.setAttribute('aria-expanded','true');const b=toggle?.querySelector('b');if(b)b.textContent='−';}
  }
  function init(){
    document.querySelectorAll('.beast-nav-group-toggle').forEach(toggle=>toggle.addEventListener('click',()=>{const items=toggle.parentElement.querySelector('.beast-nav-group-items');const open=toggle.getAttribute('aria-expanded')==='true';toggle.setAttribute('aria-expanded',String(!open));items.hidden=open;const b=toggle.querySelector('b');if(b)b.textContent=open?'+':'−';}));
    document.querySelectorAll('[data-ribbon-route]').forEach(button=>button.addEventListener('click',()=>window.BeastRouter?.navigate(button.dataset.ribbonRoute)));
    const shell=document.querySelector('.beast-shell'), railToggle=$('beastRailToggle');
    const saved=localStorage.getItem('beast.phaseA.railCollapsed')==='true'; shell?.classList.toggle('beast-rail-collapsed',saved); railToggle?.setAttribute('aria-expanded',String(!saved));
    railToggle?.addEventListener('click',()=>{const collapsed=shell.classList.toggle('beast-rail-collapsed');localStorage.setItem('beast.phaseA.railCollapsed',String(collapsed));railToggle.setAttribute('aria-expanded',String(!collapsed));railToggle.setAttribute('aria-label',collapsed?'Expand context rail':'Collapse context rail');});
    document.addEventListener('beast:route-start',event=>{const route=event.detail?.page||'studio';setMode(route);ensureActiveGroupOpen(route)});
    const store=window.BeastStore;if(store?.subscribe)store.subscribe(state=>updateRibbon(state));
    const initial=store?.get?.();if(initial){updateRibbon(initial);setMode(initial.route);ensureActiveGroupOpen(initial.route)}
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
