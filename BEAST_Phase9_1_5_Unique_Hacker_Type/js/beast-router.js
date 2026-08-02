
(() => {
  const routes = new Map();
  let active = '';
  function register(page, renderer) { routes.set(page, renderer); }
  async function navigate(page, options={}) {
    if (!routes.has(page)) page = 'mission';
    if (active === page && !options.force) return;
    active = page;
    document.body.dataset.beastPage = page;
    document.querySelectorAll('[data-beast-route]').forEach(el => el.classList.toggle('active', el.dataset.beastRoute === page));
    document.dispatchEvent(new CustomEvent('beast:route-start', {detail:{page}}));
    await window.BeastRenderScheduler.request(page, routes.get(page), options);
    document.dispatchEvent(new CustomEvent('beast:route-complete', {detail:{page}}));
  }
  window.BeastRouter = {register,navigate,get active(){return active;}};
})();
