(() => {
  let revision = 0;
  let frame = 0;
  let controller = null;
  let disposeActive = null;

  async function request(page, renderer, options = {}) {
    const myRevision = ++revision;
    controller?.abort('superseded');
    controller = new AbortController();
    cancelAnimationFrame(frame);
    await new Promise(resolve => { frame = requestAnimationFrame(resolve); });
    if (myRevision !== revision) return;

    const outlet = document.getElementById('beastPageOutlet');
    if (!outlet) throw new Error('Missing #beastPageOutlet');
    outlet.setAttribute('aria-busy', 'true');

    try {
      const result = await renderer({ page, signal: controller.signal, revision: myRevision, options });
      if (myRevision !== revision || controller.signal.aborted) {
        result?.dispose?.();
        return;
      }

      disposeActive?.();
      disposeActive = null;

      if (typeof result === 'string') outlet.innerHTML = result;
      else if (result instanceof Node) outlet.replaceChildren(result);
      else if (result?.node instanceof Node) {
        outlet.replaceChildren(result.node);
        disposeActive = typeof result.dispose === 'function' ? result.dispose : null;
      } else {
        outlet.replaceChildren();
      }

      outlet.dataset.renderRevision = String(myRevision);
      outlet.dataset.renderPage = page;
    } finally {
      if (myRevision === revision) outlet.removeAttribute('aria-busy');
    }
  }

  function cancel() {
    revision += 1;
    controller?.abort('cancelled');
    cancelAnimationFrame(frame);
    disposeActive?.();
    disposeActive = null;
  }

  window.BeastRenderScheduler = { request, cancel, get revision() { return revision; } };
})();
