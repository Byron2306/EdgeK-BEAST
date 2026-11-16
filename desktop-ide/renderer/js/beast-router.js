
(() => {
  const routes = new Map();
  let active = '';
  function register(page, renderer) { routes.set(page, renderer); }
  async function navigate(page, options={}) {
    if (!routes.has(page)) page = 'mission';
    if (active === page && !options.force) return;
    const previous = active;
    active = page;
    document.body.dataset.beastPage = page;
    document.querySelectorAll('[data-beast-route]').forEach(el => el.classList.toggle('active', el.dataset.beastRoute === page));
    document.dispatchEvent(new CustomEvent('beast:route-start', {detail:{page}}));
    try {
      await window.BeastRenderScheduler.request(page, routes.get(page), options);
    } catch (error) {
      if (active === page) {
        active = previous;
        if (previous) {
          document.body.dataset.beastPage = previous;
          document.querySelectorAll('[data-beast-route]').forEach(el => el.classList.toggle('active', el.dataset.beastRoute === previous));
          document.dispatchEvent(new CustomEvent('beast:route-start', {detail:{page:previous}}));
        } else {
          delete document.body.dataset.beastPage;
          document.querySelectorAll('[data-beast-route]').forEach(el => el.classList.remove('active'));
        }
      }
      document.dispatchEvent(new CustomEvent('beast:route-failed', {detail:{page,error:String(error.message || error)}}));
      throw error;
    }
    document.dispatchEvent(new CustomEvent('beast:route-complete', {detail:{page}}));
  }
  window.BeastRouter = {register,navigate,get active(){return active;}};
})();
