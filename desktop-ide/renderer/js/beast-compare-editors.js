(() => {
  const state = {
    open: false,
    mode: 'buffer-disk',
    left: null,
    right: null,
    targetPath: '',
    renderSideBySide: true,
    changeIndex: 0,
    changeLines: [],
    disposeDiff: null,
  };

  const clone = value => JSON.parse(JSON.stringify(value));
  const fileName = path => String(path || '').split('/').filter(Boolean).at(-1) || 'Untitled';

  function active() {
    return window.BeastEditorCortex?.getActive?.() || { path: '', text: '', original: '', dirty: false, language: 'plaintext' };
  }

  function otherOpenDocument(path) {
    const layout = window.BeastEditorGroups?.snapshot?.();
    if (!layout) return '';
    const tabs = Object.values(layout.groups || {}).flatMap(group => group.tabs || []);
    return [...new Set(tabs)].find(item => item && item !== path) || '';
  }

  function changedLines(leftText, rightText) {
    const left = String(leftText || '').split('\n');
    const right = String(rightText || '').split('\n');
    const lines = [];
    const count = Math.max(left.length, right.length);
    for (let i = 0; i < count; i += 1) {
      if (left[i] !== right[i]) lines.push(i + 1);
    }
    return lines;
  }

  function snapshot() {
    return clone({
      open: state.open,
      mode: state.mode,
      left: state.left,
      right: state.right,
      targetPath: state.targetPath,
      renderSideBySide: state.renderSideBySide,
      changeIndex: state.changeIndex,
      changeCount: state.changeLines.length,
      currentChangeLine: state.changeLines[state.changeIndex] || 0,
    });
  }

  function notify() {
    document.dispatchEvent(new CustomEvent('beast:compare-state', { detail: snapshot() }));
  }

  async function render() {
    const panel = document.querySelector('[data-compare-workbench]');
    const host = document.querySelector('[data-compare-host]');
    const fallback = document.querySelector('[data-compare-fallback]');
    if (!panel || !host || !fallback) return;
    panel.classList.toggle('hidden', !state.open);
    document.querySelector('.cortex-editor')?.classList.toggle('compare-active', state.open);
    if (!state.open) {
      state.disposeDiff?.();
      state.disposeDiff = null;
      return;
    }
    const title = document.querySelector('[data-compare-title]');
    const meta = document.querySelector('[data-compare-meta]');
    if (title) title.textContent = `${state.left?.label || 'Left'} ↔ ${state.right?.label || 'Right'}`;
    if (meta) meta.textContent = `${state.mode.replaceAll('-', ' ').toUpperCase()} · ${state.changeLines.length} change${state.changeLines.length === 1 ? '' : 's'}`;
    state.disposeDiff?.();
    state.disposeDiff = await window.BeastEditorCortex.mountContentDiff(host, fallback, {
      identity: `phase6.4/${state.mode}/${Date.now()}`,
      path: state.targetPath || state.right?.path || state.left?.path || '',
      originalText: state.left?.text || '',
      modifiedText: state.right?.text || '',
      previewText: state.right?.text || '',
      renderSideBySide: state.renderSideBySide,
      changeLines: state.changeLines,
    });
    updateControls();
  }

  function updateControls() {
    const count = state.changeLines.length;
    const label = document.querySelector('[data-compare-position]');
    if (label) label.textContent = count ? `${state.changeIndex + 1} / ${count}` : 'No changes';
    document.querySelector('[data-compare-action="accept-left"]')?.toggleAttribute('disabled', !state.targetPath);
    document.querySelector('[data-compare-action="accept-right"]')?.toggleAttribute('disabled', !state.targetPath);
    const view = document.querySelector('[data-compare-action="toggle-view"]');
    if (view) view.textContent = state.renderSideBySide ? 'Inline' : 'Side by side';
  }

  async function openTexts({ mode = 'custom', left, right, targetPath = '' }) {
    if (!left || !right) throw new Error('Both comparison sides are required.');
    state.open = true;
    state.mode = mode;
    state.left = { label: left.label || fileName(left.path), path: left.path || '', text: String(left.text || ''), readOnly: left.readOnly !== false };
    state.right = { label: right.label || fileName(right.path), path: right.path || '', text: String(right.text || ''), readOnly: right.readOnly !== false };
    state.targetPath = targetPath || '';
    state.changeLines = changedLines(state.left.text, state.right.text);
    state.changeIndex = 0;
    await render();
    if (state.changeLines.length) window.BeastEditorCortex?.revealDiffLine?.(state.changeLines[0]);
    notify();
    return snapshot();
  }

  async function openBufferVsDisk(path = '') {
    const doc = active();
    const target = path || doc.path;
    if (!target) throw new Error('Open an editor before comparing with disk.');
    const loaded = target === doc.path ? { text: doc.original } : await window.BeastDesktopBridge.loadFile(target, { activate: false });
    return openTexts({
      mode: 'buffer-disk',
      targetPath: target,
      left: { label: `${fileName(target)} · Disk`, path: target, text: loaded?.text || '' },
      right: { label: `${fileName(target)} · Buffer`, path: target, text: target === doc.path ? doc.text : loaded?.text || '' },
    });
  }

  async function openEditorComparison(leftPath = '', rightPath = '') {
    const doc = active();
    const right = rightPath || doc.path;
    const left = leftPath || otherOpenDocument(right);
    if (!left || !right) throw new Error('Open at least two editor tabs to compare files.');
    const [leftFile, rightFile] = await Promise.all([
      left === doc.path ? Promise.resolve({ text: doc.text }) : window.BeastDesktopBridge.loadFile(left, { activate: false }),
      right === doc.path ? Promise.resolve({ text: doc.text }) : window.BeastDesktopBridge.loadFile(right, { activate: false }),
    ]);
    return openTexts({
      mode: 'file-file',
      targetPath: right,
      left: { label: fileName(left), path: left, text: leftFile?.text || '' },
      right: { label: fileName(right), path: right, text: rightFile?.text || '' },
    });
  }

  async function openSourcePlan() {
    const plan = window.BeastStore?.get?.().sourcePlan || {};
    const path = active().path;
    if (!plan.originalText && !plan.proposedText) throw new Error('No SourcePlan comparison is ready.');
    return openTexts({
      mode: 'sourceplan',
      targetPath: path,
      left: { label: `${fileName(path)} · Original`, path, text: plan.originalText || '' },
      right: { label: `${fileName(path)} · Proposed`, path, text: plan.proposedText || '' },
    });
  }

  function navigate(direction = 1) {
    if (!state.changeLines.length) return 0;
    state.changeIndex = (state.changeIndex + direction + state.changeLines.length) % state.changeLines.length;
    const line = state.changeLines[state.changeIndex];
    window.BeastEditorCortex?.revealDiffLine?.(line);
    updateControls();
    notify();
    return line;
  }

  async function accept(side) {
    if (!state.targetPath) throw new Error('This comparison has no writable target buffer.');
    const chosen = side === 'left' ? state.left : state.right;
    if (!chosen) throw new Error('Comparison side is unavailable.');
    await window.BeastEditorCortex?.replaceBuffer?.(state.targetPath, chosen.text, { source: `compare:${side}` });
    window.BeastStore?.addLedger?.(`Compare editor accepted ${side} side for ${state.targetPath}`);
    await openBufferVsDisk(state.targetPath);
    return snapshot();
  }

  async function toggleView() {
    state.renderSideBySide = !state.renderSideBySide;
    await render();
    notify();
  }

  function close() {
    state.disposeDiff?.();
    state.disposeDiff = null;
    state.open = false;
    state.left = null;
    state.right = null;
    state.targetPath = '';
    state.changeLines = [];
    state.changeIndex = 0;
    render();
    notify();
  }

  document.addEventListener('click', async event => {
    const action = event.target.closest('[data-compare-action]')?.dataset.compareAction;
    if (!action) return;
    try {
      if (action === 'disk') await openBufferVsDisk();
      else if (action === 'file') await openEditorComparison();
      else if (action === 'sourceplan') await openSourcePlan();
      else if (action === 'next') navigate(1);
      else if (action === 'previous') navigate(-1);
      else if (action === 'toggle-view') await toggleView();
      else if (action === 'accept-left') await accept('left');
      else if (action === 'accept-right') await accept('right');
      else if (action === 'close') close();
    } catch (error) {
      window.BeastStore?.patch?.('workspace', { error: String(error.message || error) });
    }
  });

  window.BeastCompareEditors = {
    snapshot,
    openTexts,
    openBufferVsDisk,
    openEditorComparison,
    openSourcePlan,
    navigate,
    accept,
    toggleView,
    close,
  };
})();
