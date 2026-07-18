(() => {
  const actionIcons = {
    refresh:'diagnostics', test:'diagnostics', policy:'policies', stage:'target-lock', create:'agent',
    pause:'policies', resume:'agents', cancel:'alerts', verify:'trust', policies:'policies', access:'trust',
    export:'files', compact:'memory', promote:'crystallization', fit:'target-lock', commit:'crystallization',
    seal:'trust', proof:'evidence', open:'files', sync:'network', scan:'diagnostics', run:'terminal',
    approve:'trust', reject:'alerts', apply:'trust', draft:'source', save:'files', clear:'terminal',
    benchmark:'compute', install:'plugins', update:'plugins', restart:'system', repair:'doctor'
  };

  const textRules = [
    [/refresh|scan|diagnostic|doctor/i,'diagnostics'],[/assign|create agent|agent/i,'agent'],[/model|route/i,'models'],
    [/policy|guard/i,'policies'],[/verify|integrity|trust|approve/i,'trust'],[/memory|compact|recall/i,'memory'],
    [/export|file|open|save/i,'files'],[/crystal|commit|promote/i,'crystallization'],[/map|fit|target/i,'target-lock'],
    [/cancel|warning|risk|block|reject/i,'alerts'],[/sync|network|handoff/i,'network'],[/tool|plugin|install|update/i,'tools'],
    [/run|execute|terminal|clear/i,'terminal'],[/benchmark|compute/i,'compute'],[/repair|restart/i,'doctor']
  ];

  /*
   * These controls have their own grid contract. Auto-prepending an image shifts
   * columns, breaks alignment, or can become a 512px natural-size image before
   * page CSS catches up. They either already own an explicit icon slot or are
   * intentionally text-only compact controls.
   */
  const skipSelector = [
    '.beast-chip',
    '.beast-command-tabs button',
    '.cortex-tabbar button',
    '.cortex-editor-tools button',
    '.cortex-explorer-tools button',
    '.cortex-tab',
    '.beast-file-row',
    '.review-gate',
    '.memory-recall-row',
    '.memory-layer-row',
    '.map-node',
    '.route-map-node',
    '.agent-orbit-node',
    '.model-registry-row',
    '.agent-session-row',
    '.crystal-candidate-row',
    '.evidence-file-row',
    '[data-close-tab]'
  ].join(',');

  function keyForButton(button) {
    const data = [
      button.dataset.modelAction,
      button.dataset.agentAction,
      button.dataset.trustAction,
      button.dataset.memoryAction,
      button.dataset.mapAction,
      button.dataset.crystalAction,
      button.dataset.reviewAction,
      button.dataset.evidenceAction,
      button.dataset.editorAction,
      button.dataset.sourceplanAction,
      button.dataset.terminalAction,
      button.dataset.toolingAction,
      button.dataset.doctorAction
    ].find(Boolean);
    if (data && actionIcons[data]) return actionIcons[data];
    const text = (button.textContent || '').trim();
    return textRules.find(([rx]) => rx.test(text))?.[1] || '';
  }

  function sizeForButton(button) {
    if (button.matches('.terminal-icon-button,.beast-icon-button')) return 28;
    if (button.matches('.beast-button,.rail-action,.model-stage-button,.agent-control-row button')) return 20;
    if (button.closest('.beast-page-actions,.beast-panel-head')) return 18;
    return 16;
  }

  function lockImageSize(img, size) {
    const px = `${size}px`;
    img.width = size;
    img.height = size;
    img.style.setProperty('width', px, 'important');
    img.style.setProperty('height', px, 'important');
    img.style.setProperty('max-width', px, 'important');
    img.style.setProperty('max-height', px, 'important');
    img.style.setProperty('min-width', px, 'important');
    img.style.setProperty('min-height', px, 'important');
    img.style.setProperty('object-fit', 'contain', 'important');
    img.style.setProperty('flex', `0 0 ${px}`, 'important');
  }

  function add(button) {
    if (!(button instanceof HTMLElement)) return;
    if (button.matches(skipSelector)) return;
    if (button.querySelector(':scope > img')) return;
    const key = keyForButton(button);
    if (!key) return;

    const size = sizeForButton(button);
    const img = document.createElement('img');
    img.src = BeastAssets.icon(key);
    img.alt = '';
    img.decoding = 'async';
    img.loading = 'lazy';
    img.setAttribute('aria-hidden', 'true');
    img.dataset.beastAutoIcon = key;
    img.className = `beast-auto-icon beast-auto-icon--${size}`;
    lockImageSize(img, size);
    button.prepend(img);
  }

  function scan(root = document) {
    if (!(root instanceof Document || root instanceof Element)) return;
    root.querySelectorAll('button').forEach(add);
  }

  function fallback(img) {
    if (!(img instanceof HTMLImageElement) || img.dataset.fallbackApplied === 'true') return;
    img.dataset.fallbackApplied = 'true';
    img.src = BeastAssets.icon('diagnostics');
    img.classList.add('beast-icon-fallback');

    /* Only constrain genuinely unstyled fallback images. Existing explicit page
       icons keep their page-owned dimensions. */
    const box = img.getBoundingClientRect();
    if (!box.width || !box.height || box.width > 96 || box.height > 96) {
      lockImageSize(img, 20);
    }
  }

  function audit(root = document) {
    const rows = [];
    root.querySelectorAll('img').forEach(img => {
      const box = img.getBoundingClientRect();
      const visible = box.width > 0 && box.height > 0 && getComputedStyle(img).display !== 'none';
      if (!visible) return;
      if (box.width > 128 || box.height > 128) {
        rows.push({
          src: img.getAttribute('src') || '',
          className: String(img.className || ''),
          width: Math.round(box.width),
          height: Math.round(box.height),
          parent: String(img.parentElement?.className || '')
        });
      }
    });
    return rows;
  }

  document.addEventListener('error', event => {
    if (event.target instanceof HTMLImageElement) fallback(event.target);
  }, true);

  const observer = new MutationObserver(records => records.forEach(record => record.addedNodes.forEach(node => {
    if (node.nodeType !== 1) return;
    if (node.matches?.('button')) add(node);
    scan(node);
  })));

  window.addEventListener('DOMContentLoaded', () => {
    scan();
    observer.observe(document.body, { childList: true, subtree: true });
  });

  window.BeastIconCoverage = { scan, fallback, audit };
})();
