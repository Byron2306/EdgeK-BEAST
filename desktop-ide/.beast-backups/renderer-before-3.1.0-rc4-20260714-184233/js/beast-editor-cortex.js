(() => {
  const models = new Map();
  const buffers = new Map();
  const originals = new Map();
  const languages = new Map();
  let monacoPromise = null;
  let editor = null;
  let splitEditor = null;
  let diffEditor = null;
  let editorDisposables = [];
  let diffModels = [];
  let mounted = false;
  let suppress = false;
  let activeHosts = null;
  const storagePrefix = 'beast.phase2.editor';

  function rootKey() { return BeastStore.get().workspace.root || 'workspace'; }
  function stateKey() { return `${storagePrefix}:state:${rootKey()}`; }
  function bufferKey(path) { return `${storagePrefix}:buffer:${rootKey()}:${path}`; }

  function ensureTheme(api) {
    if (api.editor._beastPhase2Theme) return;
    api.editor.defineTheme('beast-phase2', {
      base: 'vs-dark', inherit: true,
      rules: [
        { token: '', foreground: 'dce6df', background: '020403' },
        { token: 'comment', foreground: '69786f', fontStyle: 'italic' },
        { token: 'keyword', foreground: 'a3ff5a', fontStyle: 'bold' },
        { token: 'string', foreground: 'b9db93' },
        { token: 'number', foreground: 'ffbd32' },
        { token: 'type', foreground: '77ff3d' },
        { token: 'delimiter', foreground: '9aada1' }
      ],
      colors: {
        'editor.background': '#020403', 'editor.foreground': '#dce6df',
        'editorLineNumber.foreground': '#405047', 'editorLineNumber.activeForeground': '#a3ff5a',
        'editorCursor.foreground': '#a3ff5a', 'editor.selectionBackground': '#183923',
        'editor.inactiveSelectionBackground': '#102519', 'editor.lineHighlightBackground': '#07100b',
        'editorGutter.background': '#020403', 'minimap.background': '#020403',
        'editorIndentGuide.background1': '#122119', 'editorIndentGuide.activeBackground1': '#37663f',
        'diffEditor.insertedTextBackground': '#174d2466', 'diffEditor.removedTextBackground': '#5b1d1d66',
        'diffEditor.insertedLineBackground': '#0d2b1566', 'diffEditor.removedLineBackground': '#30101066',
        'editorOverviewRuler.addedForeground': '#77ff3d', 'editorOverviewRuler.deletedForeground': '#ff4938'
      }
    });
    api.editor._beastPhase2Theme = true;
  }

  function ensureMonaco() {
    if (monacoPromise) return monacoPromise;
    monacoPromise = new Promise(resolve => {
      if (!window.require) { resolve(null); return; }
      try {
        window.require.config({ paths: { vs: '../node_modules/monaco-editor/min/vs' } });
        window.require(['vs/editor/editor.main'], () => {
          if (!window.monaco) { resolve(null); return; }
          ensureTheme(window.monaco);
          resolve(window.monaco);
        }, () => resolve(null));
      } catch (_) { resolve(null); }
    });
    return monacoPromise;
  }

  function editorState() { return BeastStore.get().editor; }
  function activePath() { return editorState().activePath || BeastStore.get().workspace.selectedPath || ''; }

  function persist() {
    const state = editorState();
    const payload = {
      openTabs: state.openTabs.slice(0, 12), activePath: state.activePath,
      recentFiles: state.recentFiles.slice(0, 30), split: state.split,
      explorerMode: state.explorerMode, explorerTab: state.explorerTab,
      collapsedFolders: state.collapsedFolders.slice(0, 300), dirtyPaths: state.dirtyPaths.slice(0, 12)
    };
    try { localStorage.setItem(stateKey(), JSON.stringify(payload)); } catch (_) {}
    for (const path of state.dirtyPaths) {
      try { localStorage.setItem(bufferKey(path), buffers.get(path) ?? ''); } catch (_) {}
    }
  }

  function restoreMetadata() {
    let payload = {};
    try { payload = JSON.parse(localStorage.getItem(stateKey()) || '{}'); } catch (_) {}
    BeastStore.patch('editor', {
      openTabs: Array.isArray(payload.openTabs) ? payload.openTabs.filter(Boolean).slice(0, 12) : [],
      activePath: payload.activePath || '', recentFiles: Array.isArray(payload.recentFiles) ? payload.recentFiles.filter(Boolean).slice(0, 30) : [],
      split: Boolean(payload.split), explorerMode: payload.explorerMode === 'flat' ? 'flat' : 'tree',
      explorerTab: ['files','outline','recent'].includes(payload.explorerTab) ? payload.explorerTab : 'files',
      collapsedFolders: Array.isArray(payload.collapsedFolders) ? payload.collapsedFolders : [],
      dirtyPaths: Array.isArray(payload.dirtyPaths) ? payload.dirtyPaths.filter(Boolean).slice(0, 12) : []
    });
    return BeastStore.get().editor;
  }

  async function restoreTabs() {
    const meta = restoreMetadata();
    const files = [...new Set([meta.activePath, ...meta.openTabs].filter(Boolean))].slice(0, 8);
    for (const path of files) {
      try { await openFile(path, { activate: false, silent: true, restore: true }); } catch (_) {}
    }
    const target = meta.activePath && buffers.has(meta.activePath) ? meta.activePath : files.find(path => buffers.has(path));
    if (target) activate(target);
  }

  function uriFor(path) {
    if (!window.monaco) return null;
    return monaco.Uri.parse(`file:///${encodeURIComponent(path).replace(/%2F/g, '/')}`);
  }

  function ensureModel(path) {
    if (!window.monaco || !path) return null;
    if (models.has(path)) return models.get(path);
    const model = monaco.editor.createModel(buffers.get(path) || '', languages.get(path) || BeastDesktopBridge.inferLanguage(path), uriFor(path));
    models.set(path, model);
    BeastStore.patch('editor', { modelCount: models.size });
    return model;
  }

  function symbolsFor(text, language) {
    const rows = [];
    const lines = String(text || '').split('\n');
    const patterns = language === 'python'
      ? [/^\s*(?:async\s+)?def\s+([\w_]+)/, /^\s*class\s+([\w_]+)/]
      : [/^\s*(?:export\s+)?(?:async\s+)?function\s+([\w$]+)/, /^\s*(?:export\s+)?class\s+([\w$]+)/, /^\s*(?:const|let|var)\s+([\w$]+)\s*=\s*(?:async\s*)?\(/, /^\s*(?:interface|type)\s+([\w$]+)/];
    lines.forEach((line, index) => {
      for (const pattern of patterns) {
        const match = line.match(pattern);
        if (match) { rows.push({ name: match[1], line: index + 1, kind: /class|interface|type/.test(line) ? 'type' : 'function' }); break; }
      }
    });
    return rows.slice(0, 120);
  }

  function syncActiveStore(path) {
    const text = buffers.get(path) ?? '';
    const original = originals.get(path) ?? '';
    const language = languages.get(path) || BeastDesktopBridge.inferLanguage(path);
    const dirty = text !== original;
    const state = BeastStore.get().editor;
    const dirtyPaths = dirty ? [...new Set([...state.dirtyPaths, path])] : state.dirtyPaths.filter(item => item !== path);
    BeastStore.transaction(next => {
      next.workspace.selectedPath = path;
      next.workspace.currentText = text;
      next.workspace.originalText = original;
      next.workspace.language = language;
      next.workspace.dirty = dirty;
      next.workspace.error = '';
      next.editor.activePath = path;
      next.editor.dirtyPaths = dirtyPaths;
      next.editor.outline = symbolsFor(text, language);
      next.editor.modelCount = models.size;
    });
    if (dirty) {
      try { localStorage.setItem(bufferKey(path), text); } catch (_) {}
    } else {
      try { localStorage.removeItem(bufferKey(path)); } catch (_) {}
    }
    persist();
  }

  function bindEditor(instance, pane = 'primary') {
    editorDisposables.push(instance.onDidChangeModelContent(() => {
      if (suppress) return;
      const path = activePath();
      if (!path) return;
      const value = instance.getValue();
      buffers.set(path, value);
      if (pane === 'primary' && splitEditor && splitEditor.getModel() !== instance.getModel()) splitEditor.setModel(instance.getModel());
      syncActiveStore(path);
    }));
    editorDisposables.push(instance.onDidChangeCursorPosition(event => {
      if (pane !== 'primary') return;
      BeastStore.patch('editor', { cursor: { line: event.position.lineNumber, column: event.position.column } });
    }));
  }

  async function mount({ host, fallback, splitHost, splitFallback }) {
    unmount();
    activeHosts = { host, fallback, splitHost, splitFallback };
    mounted = true;
    const api = await ensureMonaco();
    if (!mounted || !host?.isConnected) return;
    if (!api) {
      fallback?.classList.remove('hidden');
      host?.classList.add('hidden');
      splitFallback?.classList.toggle('hidden', !editorState().split);
      if (fallback) fallback.value = buffers.get(activePath()) || '';
      fallback?.addEventListener('input', fallbackInput);
      splitFallback?.addEventListener('input', fallbackInput);
      BeastStore.patch('editor', { owner: 'fallback', modelCount: 0 });
      return;
    }
    fallback?.classList.add('hidden');
    host?.classList.remove('hidden');
    editor = api.editor.create(host, {
      theme: 'beast-phase2', automaticLayout: true, minimap: { enabled: true, side: 'right' },
      fontSize: 13, fontFamily: 'JetBrains Mono, Cascadia Code, SFMono-Regular, Consolas, monospace',
      lineNumbers: 'on', scrollBeyondLastLine: false, wordWrap: 'off', glyphMargin: true,
      renderWhitespace: 'selection', smoothScrolling: true, padding: { top: 10, bottom: 12 },
      cursorBlinking: 'phase', bracketPairColorization: { enabled: true }, guides: { bracketPairs: true, indentation: true }
    });
    splitEditor = api.editor.create(splitHost, {
      theme: 'beast-phase2', automaticLayout: true, minimap: { enabled: false },
      fontSize: 13, fontFamily: 'JetBrains Mono, Cascadia Code, SFMono-Regular, Consolas, monospace',
      lineNumbers: 'on', scrollBeyondLastLine: false, wordWrap: 'off', glyphMargin: false,
      smoothScrolling: true, padding: { top: 10, bottom: 12 }
    });
    bindEditor(editor, 'primary');
    bindEditor(splitEditor, 'split');
    updateMountedModel();
    applySplit();
    BeastStore.patch('editor', { owner: 'monaco', modelCount: models.size });
  }

  function fallbackInput(event) {
    const path = activePath();
    if (!path) return;
    buffers.set(path, event.target.value);
    if (activeHosts?.fallback && activeHosts.fallback !== event.target) activeHosts.fallback.value = event.target.value;
    if (activeHosts?.splitFallback && activeHosts.splitFallback !== event.target) activeHosts.splitFallback.value = event.target.value;
    syncActiveStore(path);
  }

  function updateMountedModel() {
    const path = activePath();
    suppress = true;
    if (path) {
      const model = ensureModel(path);
      editor?.setModel(model);
      splitEditor?.setModel(model);
      if (activeHosts?.fallback) activeHosts.fallback.value = buffers.get(path) || '';
      if (activeHosts?.splitFallback) activeHosts.splitFallback.value = buffers.get(path) || '';
    } else {
      editor?.setModel(null); splitEditor?.setModel(null);
      if (activeHosts?.fallback) activeHosts.fallback.value = '';
      if (activeHosts?.splitFallback) activeHosts.splitFallback.value = '';
    }
    suppress = false;
  }

  function applySplit() {
    const split = editorState().split;
    activeHosts?.splitHost?.classList.toggle('hidden', !split);
    activeHosts?.splitFallback?.classList.toggle('hidden', !split || Boolean(window.monaco));
    activeHosts?.host?.parentElement?.classList.toggle('split-active', split);
    editor?.layout(); splitEditor?.layout();
  }

  function unmount() {
    mounted = false;
    editorDisposables.forEach(disposable => { try { disposable.dispose(); } catch (_) {} });
    editorDisposables = [];
    editor?.dispose(); splitEditor?.dispose();
    editor = null; splitEditor = null;
    if (activeHosts?.fallback) activeHosts.fallback.removeEventListener('input', fallbackInput);
    if (activeHosts?.splitFallback) activeHosts.splitFallback.removeEventListener('input', fallbackInput);
    activeHosts = null;
    BeastStore.patch('editor', { owner: 'unmounted' });
  }

  async function openFile(path, options = {}) {
    if (!path) return null;
    let loaded;
    try { loaded = await BeastDesktopBridge.loadFile(path, options); }
    catch (error) { BeastStore.patch('workspace', { error: String(error.message || error) }); return null; }
    if (!loaded) return null;
    const persisted = options.restore ? localStorage.getItem(bufferKey(path)) : null;
    originals.set(path, loaded.text);
    buffers.set(path, persisted !== null ? persisted : loaded.text);
    languages.set(path, BeastDesktopBridge.inferLanguage(path));
    if (models.has(path)) {
      const model = models.get(path);
      if (model.getValue() !== buffers.get(path)) { suppress = true; model.setValue(buffers.get(path)); suppress = false; }
    }
    BeastStore.transaction(next => {
      if (!next.editor.openTabs.includes(path)) next.editor.openTabs.push(path);
      next.editor.openTabs = next.editor.openTabs.slice(-12);
      next.editor.recentFiles = [path, ...next.editor.recentFiles.filter(item => item !== path)].slice(0, 30);
    });
    if (options.activate !== false) activate(path);
    if (!options.silent) BeastStore.addLedger(`Editor opened ${path}`);
    return loaded;
  }

  function activate(path) {
    if (!path || !buffers.has(path)) return;
    const state = editorState();
    if (!state.openTabs.includes(path)) BeastStore.patch('editor', { openTabs: [...state.openTabs, path].slice(-12) });
    syncActiveStore(path);
    updateMountedModel();
    editor?.focus();
  }

  function closeTab(path) {
    const state = editorState();
    const tabs = state.openTabs.filter(item => item !== path);
    if (state.dirtyPaths.includes(path) && !window.confirm(`Close ${path.split('/').pop()} with staged changes? The persisted buffer will remain recoverable.`)) return false;
    const wasActive = state.activePath === path;
    BeastStore.patch('editor', { openTabs: tabs });
    if (wasActive) {
      const nextPath = tabs.at(-1) || '';
      if (nextPath) activate(nextPath);
      else {
        BeastStore.transaction(next => {
          next.editor.activePath = '';
          next.workspace.selectedPath = '';
          next.workspace.currentText = '';
          next.workspace.originalText = '';
          next.workspace.dirty = false;
          next.editor.outline = [];
        });
        updateMountedModel();
      }
    }
    persist();
    return true;
  }

  function revertActive() {
    const path = activePath();
    if (!path) return;
    const original = originals.get(path) || '';
    buffers.set(path, original);
    const model = models.get(path);
    if (model) { suppress = true; model.setValue(original); suppress = false; }
    syncActiveStore(path);
    updateMountedModel();
    BeastStore.addLedger(`Reverted ${path}`);
  }

  function toggleSplit() {
    BeastStore.patch('editor', { split: !editorState().split });
    applySplit(); persist();
  }

  function setExplorerTab(tab) { BeastStore.patch('editor', { explorerTab: tab }); persist(); }
  function setExplorerMode(mode) { BeastStore.patch('editor', { explorerMode: mode === 'flat' ? 'flat' : 'tree' }); persist(); }
  function toggleFolder(path) {
    const collapsed = new Set(editorState().collapsedFolders);
    collapsed.has(path) ? collapsed.delete(path) : collapsed.add(path);
    BeastStore.patch('editor', { collapsedFolders: [...collapsed] }); persist();
  }

  function gotoLine(line) {
    if (!editor) return;
    editor.revealLineInCenter(line);
    editor.setPosition({ lineNumber: line, column: 1 }); editor.focus();
  }

  function getActive() {
    const path = activePath();
    return { path, text: buffers.get(path) || '', original: originals.get(path) || '', language: languages.get(path) || BeastDesktopBridge.inferLanguage(path), dirty: buffers.get(path) !== originals.get(path) };
  }

  async function draftSourcePlan() {
    const active = getActive();
    if (!active.path) throw new Error('Select a file before drafting SourcePlan.');
    if (!active.dirty) throw new Error('No editor changes to compile.');
    BeastStore.patch('sourcePlan', { status: 'drafting', message: 'Compiling governed editor draft…', error: '', originalText: active.original, proposedText: active.text });
    const result = await BeastDesktopBridge.draftSourcePlan({ path: active.path, originalText: active.original, newText: active.text });
    if (result?.ok === false) throw new Error(result.error || 'SourcePlan draft failed.');
    const plan = structuredClone(result.plan || result);
    const operations = plan.operations || (Array.isArray(plan.selected_operations) && typeof plan.selected_operations[0] === 'object' ? plan.selected_operations : null) || result.preview?.operations || [];
    if (!Array.isArray(plan.operations) || !plan.operations.length) plan.operations = operations;
    const ids = operations.map((op, index) => typeof op === 'string' ? op : (op.operation_id || op.id || `op-${index + 1}`));
    BeastStore.patch('sourcePlan', {
      status: result.local ? 'local-draft' : 'draft', message: result.local ? 'Local diff compiled. Gateway verification is still required.' : `Draft ready: ${plan.plan_id || 'draft'}`,
      plan, lifecycle: null, selectedOperationIds: ids, previewText: result.preview_text || BeastDesktopBridge.localDiff(active.original, active.text),
      originalText: active.original, proposedText: active.text, activeOperationId: ids[0] || '', stale: Boolean(result.stale_context), error: '', updatedAt: Date.now()
    });
    BeastStore.addLedger(`SourcePlan drafted for ${active.path}`);
    return plan;
  }

  async function refreshLifecycle() {
    const plan = BeastStore.get().sourcePlan.plan;
    if (!plan) throw new Error('No SourcePlan draft.');
    const lifecycle = await BeastDesktopBridge.sourcePlanLifecycle(plan);
    BeastStore.patch('sourcePlan', { lifecycle, status: lifecycle?.can_apply ? 'ready' : BeastStore.get().sourcePlan.status, message: lifecycle?.can_apply ? 'Verification complete. Plan is ready to apply.' : BeastStore.get().sourcePlan.message, updatedAt: Date.now() });
    BeastStore.addLedger(`SourcePlan lifecycle refreshed: ${plan.plan_id || 'draft'}`);
    return lifecycle;
  }

  async function verifyPlan() {
    const state = BeastStore.get().sourcePlan;
    BeastStore.patch('sourcePlan', { verifying: true, error: '', message: 'Running SourcePlan verification…' });
    try {
      const result = await BeastDesktopBridge.verifySourcePlan(state.plan);
      const lifecycle = await BeastDesktopBridge.sourcePlanLifecycle(state.plan);
      BeastStore.patch('sourcePlan', { verifying: false, lifecycle, status: lifecycle?.can_apply ? 'ready' : 'verified', message: `Verified ${state.plan?.plan_id || 'SourcePlan'} · ${result?.selected_count ?? state.selectedOperationIds.length} operations`, updatedAt: Date.now() });
      BeastStore.addLedger(`SourcePlan verified: ${state.plan?.plan_id || 'draft'}`);
      return result;
    } catch (error) {
      BeastStore.patch('sourcePlan', { verifying: false, status: 'error', error: String(error.message || error), message: String(error.message || error) });
      throw error;
    }
  }

  async function applyPlan() {
    const state = BeastStore.get().sourcePlan;
    if (!state.plan) throw new Error('No SourcePlan draft.');
    if (!window.confirm(`Apply SourcePlan ${state.plan.plan_id || 'draft'}? BEAST will verify, write rollback data, and close evidence.`)) return null;
    BeastStore.patch('sourcePlan', { applying: true, error: '', message: 'Applying through governed write path…' });
    try {
      const result = await BeastDesktopBridge.applySourcePlan(state.plan);
      BeastStore.patch('sourcePlan', { applying: false, status: 'applied', message: `Applied ${state.plan.plan_id || 'SourcePlan'}`, lastApply: result, updatedAt: Date.now() });
      const path = activePath();
      if (path) {
        const reloaded = await BeastDesktopBridge.loadFile(path);
        if (reloaded) {
          originals.set(path, reloaded.text); buffers.set(path, reloaded.text);
          const model = models.get(path); if (model) { suppress = true; model.setValue(reloaded.text); suppress = false; }
          syncActiveStore(path);
        }
      }
      BeastStore.addLedger(`SourcePlan applied: ${state.plan.plan_id || 'draft'}`);
      return result;
    } catch (error) {
      BeastStore.patch('sourcePlan', { applying: false, status: 'error', error: String(error.message || error), message: String(error.message || error) });
      throw error;
    }
  }

  function clearPlan() {
    BeastStore.set('sourcePlan', { status: 'idle', message: 'No editor draft yet.', plan: null, lifecycle: null, selectedOperationIds: [], previewText: '', originalText: '', proposedText: '', activeOperationId: '', stale: false, error: '', verifying: false, applying: false, lastApply: null, updatedAt: Date.now() });
  }

  function toggleOperation(id) {
    const state = BeastStore.get().sourcePlan;
    const selected = new Set(state.selectedOperationIds);
    selected.has(id) ? selected.delete(id) : selected.add(id);
    const plan = structuredClone(state.plan || {});
    if (Array.isArray(plan.operations)) plan.operations = plan.operations.map((op, index) => ({ ...op, selected: selected.has(op.operation_id || op.id || `op-${index + 1}`) }));
    plan.selected_operations = [...selected];
    BeastStore.patch('sourcePlan', { plan, selectedOperationIds: [...selected], activeOperationId: id, lifecycle: null, status: state.status === 'ready' ? 'draft' : state.status, message: 'Operation selection changed. Refresh lifecycle before applying.' });
  }

  async function mountDiff(host, fallback) {
    const state = BeastStore.get().sourcePlan;
    const api = await ensureMonaco();
    if (!host?.isConnected) return () => {};
    if (!api) {
      fallback.classList.remove('hidden'); host.classList.add('hidden'); fallback.textContent = state.previewText || 'No diff preview.';
      return () => {};
    }
    fallback.classList.add('hidden'); host.classList.remove('hidden');
    diffEditor?.dispose(); diffModels.forEach(model => model.dispose()); diffModels = [];
    const sideBySide = host.clientWidth >= 760;
    diffEditor = api.editor.createDiffEditor(host, {
      theme: 'beast-phase2', automaticLayout: true, renderSideBySide: sideBySide,
      useInlineViewWhenSpaceIsLimited: true, enableSplitViewResizing: true,
      readOnly: true, originalEditable: false, minimap: { enabled: false },
      scrollBeyondLastLine: false, wordWrap: 'on', renderOverviewRuler: false
    });
    const original = api.editor.createModel(state.originalText || '', BeastDesktopBridge.inferLanguage(activePath()), api.Uri.parse(`inmemory://sourceplan/original/${Date.now()}`));
    const modified = api.editor.createModel(state.proposedText || '', BeastDesktopBridge.inferLanguage(activePath()), api.Uri.parse(`inmemory://sourceplan/proposed/${Date.now()}`));
    diffModels = [original, modified]; diffEditor.setModel({ original, modified });
    let lastSideBySide = sideBySide;
    const resizeObserver = new ResizeObserver(entries => {
      const width = entries[0]?.contentRect?.width || host.clientWidth;
      const nextSideBySide = width >= 760;
      if (nextSideBySide !== lastSideBySide) {
        lastSideBySide = nextSideBySide;
        diffEditor?.updateOptions({ renderSideBySide: nextSideBySide });
      }
      diffEditor?.layout();
    });
    resizeObserver.observe(host);
    BeastStore.patch('diagnostics', { activeDiffEditors: 1 });
    return () => { resizeObserver.disconnect(); diffEditor?.dispose(); diffEditor = null; diffModels.forEach(model => model.dispose()); diffModels = []; BeastStore.patch('diagnostics', { activeDiffEditors: 0 }); };
  }

  function destroyAll() {
    unmount();
    diffEditor?.dispose(); diffModels.forEach(model => model.dispose());
    models.forEach(model => model.dispose()); models.clear(); buffers.clear(); originals.clear(); languages.clear();
  }

  window.BeastEditorCortex = {
    ensureMonaco, mount, unmount, openFile, activate, closeTab, revertActive, toggleSplit,
    setExplorerTab, setExplorerMode, toggleFolder, gotoLine, getActive, restoreTabs,
    draftSourcePlan, refreshLifecycle, verifyPlan, applyPlan, clearPlan, toggleOperation, mountDiff,
    persist, destroyAll, localDiff: BeastDesktopBridge.localDiff
  };
})();
