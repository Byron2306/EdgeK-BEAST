(() => {
  const models = new Map();
  const buffers = new Map();
  const originals = new Map();
  const languages = new Map();
  const notebooks = new Map();
  let monacoPromise = null;
  let editor = null;
  let splitEditor = null;
  let diffEditor = null;
  let diffGeneration = 0;
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
  function isNotebookPath(path) { return /\.ipynb$/i.test(String(path || '')); }
  function notebookCell(raw = {}, index = 0) {
    const source = Array.isArray(raw.source) ? raw.source.join('') : String(raw.source || '');
    return { id: String(raw.id || `beast-cell-${Date.now().toString(36)}-${index}`), cell_type: raw.cell_type === 'markdown' ? 'markdown' : 'code', metadata: raw.metadata || {}, source, outputs: Array.isArray(raw.outputs) ? raw.outputs : [], execution_count: raw.execution_count ?? null };
  }
  function parseNotebook(text) {
    try {
      const raw = JSON.parse(String(text || ''));
      if (!raw || !Array.isArray(raw.cells)) throw new Error('Missing cells array');
      return { raw, cells: raw.cells.map(notebookCell), parseError: '' };
    } catch (error) {
      return { raw: { nbformat: 4, nbformat_minor: 5, metadata: {} }, cells: [notebookCell({ cell_type: 'code', source: '' }, 0)], parseError: `Notebook JSON could not be parsed: ${String(error.message || error)}` };
    }
  }
  function serializeNotebook(document) {
    const raw = { ...(document?.raw || {}), nbformat: Number(document?.raw?.nbformat || 4), nbformat_minor: Number(document?.raw?.nbformat_minor || 5) };
    raw.cells = (document?.cells || []).map(cell => ({ id: cell.id, cell_type: cell.cell_type, metadata: cell.metadata || {}, source: cell.source || '', ...(cell.cell_type === 'code' ? { execution_count: cell.execution_count ?? null, outputs: cell.outputs || [] } : {}) }));
    return `${JSON.stringify(raw, null, 2)}\n`;
  }
  function notebookFor(path = activePath()) { return isNotebookPath(path) ? notebooks.get(path) || null : null; }
  function syncNotebook(path) {
    const document = notebookFor(path); if (!document) return null;
    const text = serializeNotebook(document); buffers.set(path, text);
    const model = models.get(path);
    if (model && model.getValue() !== text) { suppress = true; model.setValue(text); suppress = false; }
    if (path === activePath()) syncActiveStore(path); else persist();
    return document;
  }
  function mutateNotebook(path, mutation) {
    const document = notebookFor(path); if (!document) throw new Error('Open a notebook before editing it.');
    mutation(document); syncNotebook(path); return document;
  }

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
      window.BeastEditorDocumentModel?.scheduleUpdate?.(path, value);
      window.BeastTabLifecycle?.markEdited?.(path);
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
    window.BeastIDECompatibility?.bindMonaco?.(api);
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
    window.BeastEditorSafety?.apply?.(activePath(), [editor, splitEditor]);
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
    window.BeastEditorSafety?.apply?.(path, [editor, splitEditor]);
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
    try {
      const canonical = await window.BeastEditorDocumentModel?.open?.(path, { language: BeastDesktopBridge.inferLanguage(path) });
      if (canonical?.binary) loaded = { ...loaded, text: '', binary: true, readOnly: true };
      if (canonical?.large_file_mode) loaded = { ...loaded, largeFileMode: true };
    } catch (error) { console.warn('[BEAST 6.1] canonical document registration failed', error); }
    const persisted = options.restore ? localStorage.getItem(bufferKey(path)) : null;
    originals.set(path, loaded.text);
    buffers.set(path, persisted !== null ? persisted : loaded.text);
    languages.set(path, BeastDesktopBridge.inferLanguage(path));
    if (isNotebookPath(path)) notebooks.set(path, parseNotebook(buffers.get(path)));
    if (models.has(path)) {
      const model = models.get(path);
      if (model.getValue() !== buffers.get(path)) { suppress = true; model.setValue(buffers.get(path)); suppress = false; }
    }
    BeastStore.transaction(next => {
      if (!next.editor.openTabs.includes(path)) next.editor.openTabs.push(path);
      next.editor.openTabs = next.editor.openTabs.slice(-12);
      window.BeastEditorGroups?.openDocument?.(path, { groupId: options.groupId || window.BeastEditorGroups.snapshot().activeGroupId, preview: options.preview !== false, pinned: Boolean(options.pinned) });
      next.editor.recentFiles = [path, ...next.editor.recentFiles.filter(item => item !== path)].slice(0, 30);
    });
    if (options.activate !== false) activate(path);
    if (!options.silent) BeastStore.addLedger(`Editor opened ${path}`);
    return loaded;
  }

  function activate(path, groupId = '') {
    if (!path || !buffers.has(path)) return;
    try { window.BeastEditorGroups?.activateDocument?.(path, groupId || window.BeastEditorGroups.snapshot().activeGroupId); } catch (_) {}
    const state = editorState();
    if (!state.openTabs.includes(path)) BeastStore.patch('editor', { openTabs: [...state.openTabs, path].slice(-12) });
    syncActiveStore(path);
    updateMountedModel();
    editor?.focus();
  }

  async function closeTab(path, options = {}) {
    const state = editorState();
    const wasActive = state.activePath === path;
    const result = await window.BeastTabLifecycle?.requestClose?.(path, options) || { closed: false };
    if (!result.closed) return false;
    const tabs = window.BeastEditorGroups?.snapshot?.();
    const allTabs = [...new Set(Object.values(tabs?.groups || {}).flatMap(group => group.tabs))];
    BeastStore.patch('editor', { openTabs: allTabs });
    if (wasActive) {
      const activeGroup = tabs?.groups?.[tabs.activeGroupId];
      const nextPath = activeGroup?.activeDocumentId || allTabs.at(-1) || '';
      if (nextPath) activate(nextPath, activeGroup?.groupId || '');
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
    notebooks.delete(path);
    return true;
  }

  function revertPath(path) {
    if (!path) return;
    const original = originals.get(path) || '';
    buffers.set(path, original);
    if (isNotebookPath(path)) notebooks.set(path, parseNotebook(original));
    const model = models.get(path);
    if (model) { suppress = true; model.setValue(original); suppress = false; }
    syncActiveStore(path);
    updateMountedModel();
    BeastStore.addLedger(`Reverted ${path}`);
  }

  function revertActive() { return revertPath(activePath()); }

  async function reopenClosedEditor() { return window.BeastTabLifecycle?.reopenClosed?.(); }
  function pinActive() { const path = activePath(); return path ? window.BeastTabLifecycle?.pin?.(path) : null; }
  function unpinActive() { const path = activePath(); return path ? window.BeastTabLifecycle?.unpin?.(path) : null; }

  async function saveActive() {
    const path=activePath();const remote=BeastDesktopBridge.parseRemoteRef?.(path);const target=BeastStore.get().workspace.executionTarget || {kind:'local'};
    if(!remote && target.kind==='local')throw new Error('Local files remain SourcePlan-governed. Use Draft SourcePlan to save local edits.');
    const text=buffers.get(path) || '';const result=remote?await BeastDesktopBridge.saveRemoteFile(path,text,originals.get(path)||''):await BeastDesktopBridge.saveTargetFile(path,text,originals.get(path)||'');originals.set(path,text);syncActiveStore(path);persist();BeastStore.addLedger(`${remote?'Remote':'Target'} editor save: ${result.receipt?.id || path}`);return result;
  }

  function getNotebook(path = activePath()) {
    const document = notebookFor(path);
    return document ? structuredClone({ cells: document.cells, parseError: document.parseError, metadata: document.raw?.metadata || {}, nbformat: document.raw?.nbformat || 4 }) : null;
  }
  function isNotebook(path = activePath()) { return Boolean(notebookFor(path)); }
  function setNotebookCellSource(cellId, source, path = activePath()) {
    return mutateNotebook(path, document => { const cell = document.cells.find(item => item.id === cellId); if (!cell) throw new Error('Notebook cell no longer exists.'); cell.source = String(source ?? ''); });
  }
  function addNotebookCell(type = 'code', afterId = '', path = activePath()) {
    return mutateNotebook(path, document => {
      const cell = notebookCell({ cell_type: type === 'markdown' ? 'markdown' : 'code', source: '' }, document.cells.length);
      const index = document.cells.findIndex(item => item.id === afterId);
      document.cells.splice(index < 0 ? document.cells.length : index + 1, 0, cell);
    });
  }
  function deleteNotebookCell(cellId, path = activePath()) {
    return mutateNotebook(path, document => {
      if (document.cells.length <= 1) throw new Error('A notebook needs at least one cell.');
      document.cells = document.cells.filter(item => item.id !== cellId);
    });
  }
  function moveNotebookCell(cellId, direction, path = activePath()) {
    return mutateNotebook(path, document => {
      const index = document.cells.findIndex(item => item.id === cellId); const target = index + (direction === 'up' ? -1 : 1);
      if (index < 0 || target < 0 || target >= document.cells.length) return;
      [document.cells[index], document.cells[target]] = [document.cells[target], document.cells[index]];
    });
  }
  async function runNotebookCell(cellId, path = activePath()) {
    const document = notebookFor(path); const cell = document?.cells.find(item => item.id === cellId);
    if (!cell) throw new Error('Notebook cell no longer exists.');
    if (cell.cell_type !== 'code') throw new Error('Only code cells can run.');
    const result = await BeastIDERuntime.runPythonCell(cell.source);
    mutateNotebook(path, draft => {
      const target = draft.cells.find(item => item.id === cellId); if (!target) return;
      target.outputs = Array.isArray(result.outputs) ? result.outputs : [];
      target.execution_count = result.execution_count ?? target.execution_count;
    });
    return result;
  }
  async function runAllNotebookCells(path = activePath()) {
    const document = notebookFor(path); if (!document) throw new Error('Open a notebook before running it.');
    const results = [];
    for (const cell of [...document.cells]) { if (cell.cell_type === 'code' && cell.source.trim()) results.push(await runNotebookCell(cell.id, path)); }
    return results;
  }

  function toggleSplit(orientation = 'horizontal') {
    const groups = window.BeastEditorGroups;
    if (groups) {
      const layout = groups.snapshot();
      if (Object.keys(layout.groups).length === 1) groups.splitGroup(layout.activeGroupId, orientation);
      else {
        const ids = Object.keys(layout.groups);
        const secondary = ids.find(id => id !== layout.activeGroupId);
        if (secondary) groups.mergeGroup(secondary, layout.activeGroupId);
      }
      BeastStore.patch('editor', { split: Object.keys(groups.snapshot().groups).length > 1 });
    } else BeastStore.patch('editor', { split: !editorState().split });
    applySplit(); persist();
  }

  function splitGroup(orientation = 'horizontal') {
    const layout = window.BeastEditorGroups?.snapshot?.();
    if (!layout) return null;
    const created = window.BeastEditorGroups.splitGroup(layout.activeGroupId, orientation);
    BeastStore.patch('editor', { split: true, activeGroupId: created.groupId });
    applySplit(); persist(); return created;
  }

  function closeActiveGroup() {
    const groups = window.BeastEditorGroups; const layout = groups?.snapshot?.();
    if (!layout || Object.keys(layout.groups).length <= 1) return false;
    const source = layout.groups[layout.activeGroupId];
    const targetId = Object.keys(layout.groups).find(id => id !== source.groupId);
    groups.closeGroup(source.groupId, { moveTabsTo: targetId });
    BeastStore.patch('editor', { split: Object.keys(groups.snapshot().groups).length > 1 });
    applySplit(); persist(); return true;
  }

  function moveActiveToNextGroup() {
    const groups = window.BeastEditorGroups; const layout = groups?.snapshot?.(); const path = activePath();
    if (!layout || !path || Object.keys(layout.groups).length < 2) return false;
    const ids = Object.keys(layout.groups); const from = layout.activeGroupId; const to = ids[(ids.indexOf(from) + 1) % ids.length];
    groups.moveDocument(path, from, to, { preview: false }); groups.setActiveGroup(to); activate(path, to); return true;
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

  function getSelection() {
    const path = activePath();
    if (!path) return { path: '', text: '', range: null };
    if (editor) {
      const range = editor.getSelection();
      const model = editor.getModel();
      return {
        path,
        text: range && model ? model.getValueInRange(range) : '',
        range: range ? {
          startLineNumber: range.startLineNumber,
          startColumn: range.startColumn,
          endLineNumber: range.endLineNumber,
          endColumn: range.endColumn
        } : null
      };
    }
    const input = activeHosts?.fallback;
    if (!input) return { path, text: '', range: null };
    return {
      path,
      text: input.value.slice(input.selectionStart || 0, input.selectionEnd || 0),
      range: { startOffset: input.selectionStart || 0, endOffset: input.selectionEnd || 0 }
    };
  }

  async function draftSourcePlan() {
    const active = getActive();
    if (!active.path) throw new Error('Select a file before drafting SourcePlan.');
    if (BeastDesktopBridge.parseRemoteRef?.(active.path)) throw new Error('Remote files use the explicit Remote Save action; SourcePlan drafting currently applies to the local workspace only.');
    if (!active.dirty) throw new Error('No editor changes to compile.');
    BeastStore.patch('sourcePlan', { status: 'drafting', message: 'Compiling governed editor draft…', error: '', originalText: active.original, proposedText: active.text });
    const result = await BeastDesktopBridge.draftSourcePlan({ path: active.path, originalText: active.original, newText: active.text });
    if (result?.ok === false) throw new Error(result.error || 'SourcePlan draft failed.');
    const plan = structuredClone(result.plan || result);
    const operations = plan.operations || (Array.isArray(plan.selected_operations) && typeof plan.selected_operations[0] === 'object' ? plan.selected_operations : null) || result.preview?.operations || [];
    if (!Array.isArray(plan.operations) || !plan.operations.length) plan.operations = operations;
    const ids = operations.map((op, index) => typeof op === 'string' ? op : (op.operation_id || op.id || `op-${index + 1}`));
    BeastStore.patch('sourcePlan', {
      status: result.local ? 'local-preview' : 'draft', message: result.local ? `Local diff preview only. Gateway verification is required before this becomes a SourcePlan.${result.gatewayError ? ` ${result.gatewayError}` : ''}` : `Draft ready: ${plan.plan_id || 'draft'}`,
      plan, lifecycle: null, selectedOperationIds: ids, previewText: result.preview_text || BeastDesktopBridge.localDiff(active.original, active.text),
      originalText: active.original, proposedText: active.text, activeOperationId: ids[0] || '', stale: Boolean(result.stale_context), error: result.local ? String(result.error || '') : '', updatedAt: Date.now()
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
      if (!result || result.ok === false) throw new Error(result?.error || 'Gateway did not confirm SourcePlan verification.');
      const lifecycle = await BeastDesktopBridge.sourcePlanLifecycle(state.plan, { verification: result });
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
    // The SourcePlan Apply button is the explicit operator approval surface.
    // Browser confirm() is unavailable in some Electron/portal environments
    // and previously made acceptance appear to do nothing.
    BeastStore.patch('sourcePlan', { applying: true, error: '', message: 'Applying through governed write path…' });
    try {
      const result = await BeastDesktopBridge.applySourcePlan(state.plan, { approval_source: 'sourceplan_apply_button' });
      if (!result || result.ok === false || result.applied === false) throw new Error(result?.error || 'Gateway did not confirm SourcePlan apply.');
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
      document.dispatchEvent(new CustomEvent('beast:agent-sourceplan-applied', { detail:{ plan:state.plan, result } }));
      return result;
    } catch (error) {
      BeastStore.patch('sourcePlan', { applying: false, status: 'error', error: String(error.message || error), message: String(error.message || error) });
      throw error;
    }
  }

  async function rollbackLatestPlan() {
    if (!window.confirm('Rollback the latest BEAST SourcePlan apply? This restores the captured pre-apply files and removes files created by that apply.')) return null;
    BeastStore.patch('sourcePlan', { applying:true, error:'', message:'Restoring the latest governed rollback snapshot…' });
    try {
      const result = await BeastDesktopBridge.rollbackLatestSourcePlan();
      if (!result || result.ok === false) throw new Error(result?.error || 'Gateway did not confirm SourcePlan rollback.');
      const path = activePath();
      if (path) {
        const reloaded = await BeastDesktopBridge.loadFile(path);
        if (reloaded) {
          originals.set(path, reloaded.text); buffers.set(path, reloaded.text);
          const model = models.get(path); if (model) { suppress = true; model.setValue(reloaded.text); suppress = false; }
          syncActiveStore(path);
        }
      }
      BeastStore.patch('sourcePlan', { applying:false, status:'rolled-back', message:`Rollback restored ${(result.restored || []).length} file(s) and removed ${(result.deleted || []).length} created file(s).`, lastApply:null, updatedAt:Date.now() });
      BeastStore.addLedger('SourcePlan rollback completed');
      return result;
    } catch (error) {
      BeastStore.patch('sourcePlan', { applying:false, status:'error', error:String(error.message || error), message:String(error.message || error) });
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

  async function mountContentDiff(host, fallback, content={}) {
    const api = await ensureMonaco();
    if (!host?.isConnected) return () => {};
    if (!api) {
      fallback.classList.remove('hidden'); host.classList.add('hidden'); fallback.textContent = content.previewText || content.patch || 'No diff preview.';
      return () => {};
    }
    fallback.classList.add('hidden'); host.classList.remove('hidden');
    const generation=++diffGeneration;diffEditor?.dispose(); diffModels.forEach(model => model.dispose()); diffModels = [];
    const sideBySide = host.clientWidth >= 760;
    let instance;
    try { instance=api.editor.createDiffEditor(host, {
      theme: 'beast-phase2', automaticLayout: true, renderSideBySide: content.renderSideBySide === false ? false : sideBySide,
      useInlineViewWhenSpaceIsLimited: true, enableSplitViewResizing: true,
      readOnly: true, originalEditable: false, minimap: { enabled: false },
      renderSideBySide: content.renderSideBySide !== false,
      scrollBeyondLastLine: false, wordWrap: 'on', renderOverviewRuler: false
    }); } catch (error) { if(generation!==diffGeneration)return()=>{};fallback.classList.remove('hidden');host.classList.add('hidden');fallback.textContent=`Diff editor unavailable: ${String(error.message||error)}`;return()=>{}; }
    if(generation!==diffGeneration||!host.isConnected){instance.dispose();return()=>{};}diffEditor=instance;
    const identity=String(content.identity||'diff').replace(/[^A-Za-z0-9._/-]/g,'-');const language=BeastDesktopBridge.inferLanguage(content.path||activePath());
    const original = api.editor.createModel(content.originalText || '', language, api.Uri.parse(`inmemory://${identity}/original/${Date.now()}`));
    const modified = api.editor.createModel(content.modifiedText || '', language, api.Uri.parse(`inmemory://${identity}/modified/${Date.now()}`));
    diffModels = [original, modified]; instance.setModel({ original, modified });
    const beforeLines=String(content.originalText||'').split('\n');const afterLines=String(content.modifiedText||'').split('\n');let firstChangedLine=1;const compared=Math.max(beforeLines.length,afterLines.length);for(let index=0;index<compared;index+=1){if(beforeLines[index]!==afterLines[index]){firstChangedLine=index+1;break;}}
    requestAnimationFrame(()=>{if(generation!==diffGeneration||diffEditor!==instance)return;instance.getOriginalEditor().revealLineInCenter(firstChangedLine);instance.getModifiedEditor().revealLineInCenter(firstChangedLine);});
    let lastSideBySide = sideBySide;
    const resizeObserver = new ResizeObserver(entries => {
      const width = entries[0]?.contentRect?.width || host.clientWidth;
      const nextSideBySide = width >= 760;
      if (generation!==diffGeneration||diffEditor!==instance) return;
      if (nextSideBySide !== lastSideBySide) {
        lastSideBySide = nextSideBySide;
        instance.updateOptions({ renderSideBySide: nextSideBySide });
      }
      instance.layout();
    });
    resizeObserver.observe(host);
    BeastStore.patch('diagnostics', { activeDiffEditors: 1 });
    return () => { resizeObserver.disconnect(); if(generation!==diffGeneration)return;diffGeneration+=1;instance.dispose(); if(diffEditor===instance)diffEditor=null; diffModels.forEach(model => model.dispose()); diffModels = []; BeastStore.patch('diagnostics', { activeDiffEditors: 0 }); };
  }


  function revealDiffLine(line) {
    const target = Math.max(1, Number(line || 1));
    if (!diffEditor) return false;
    diffEditor.getOriginalEditor().revealLineInCenter(target);
    diffEditor.getModifiedEditor().revealLineInCenter(target);
    diffEditor.getModifiedEditor().setPosition({ lineNumber: target, column: 1 });
    return true;
  }

  async function replaceBuffer(path, text, options = {}) {
    const target = String(path || activePath());
    if (!target || !buffers.has(target)) throw new Error('Target editor buffer is not open.');
    const canonical = await window.BeastEditorDocumentModel?.get?.(target).catch?.(() => null);
    if (canonical?.binary || canonical?.read_only) throw new Error('Target document is read-only.');
    const value = String(text ?? '');
    buffers.set(target, value);
    const model = models.get(target);
    if (model && model.getValue() !== value) { suppress = true; model.setValue(value); suppress = false; }
    window.BeastEditorDocumentModel?.scheduleUpdate?.(target, value);
    window.BeastTabLifecycle?.markEdited?.(target);
    if (target === activePath()) { syncActiveStore(target); updateMountedModel(); }
    else persist();
    BeastStore.addLedger(`Editor buffer replaced from ${options.source || 'comparison'}`);
    return getActive();
  }

  async function mountDiff(host, fallback) {
    const state = BeastStore.get().sourcePlan;
    return mountContentDiff(host,fallback,{identity:'sourceplan',path:activePath(),originalText:state.originalText,modifiedText:state.proposedText,previewText:state.previewText});
  }


  function modelFor(path) { return path && buffers.has(path) ? ensureModel(path) : null; }
  function documentSnapshot(path) {
    const target = String(path || '');
    if (!target || !buffers.has(target)) return null;
    return { path: target, text: buffers.get(target) || '', original: originals.get(target) || '', language: languages.get(target) || BeastDesktopBridge.inferLanguage(target), dirty: buffers.get(target) !== originals.get(target) };
  }
  function commitModelValue(path, value, options = {}) {
    const target = String(path || '');
    if (!target || !buffers.has(target)) return false;
    const text = String(value ?? '');
    buffers.set(target, text);
    window.BeastEditorDocumentModel?.scheduleUpdate?.(target, text);
    window.BeastTabLifecycle?.markEdited?.(target);
    if (target === activePath()) syncActiveStore(target);
    else persist();
    return true;
  }
  function setCursorPosition(position = {}) {
    BeastStore.patch('editor', { cursor: { line: Math.max(1, Number(position.lineNumber || position.line || 1)), column: Math.max(1, Number(position.column || 1)) } });
  }

  function destroyAll() {
    unmount();
    diffGeneration+=1;diffEditor?.dispose(); diffEditor=null;diffModels.forEach(model => model.dispose());diffModels=[];
    models.forEach(model => model.dispose()); models.clear(); buffers.clear(); originals.clear(); languages.clear(); notebooks.clear();
  }

  window.BeastEditorCortex = {
    ensureMonaco, mount, unmount, openFile, activate, closeTab, revertActive, revertPath, reopenClosedEditor, pinActive, unpinActive, toggleSplit, splitGroup, closeActiveGroup, moveActiveToNextGroup,
    setExplorerTab, setExplorerMode, toggleFolder, gotoLine, getActive, getSelection, saveActive, restoreTabs,
    isNotebook, getNotebook, setNotebookCellSource, addNotebookCell, deleteNotebookCell, moveNotebookCell, runNotebookCell, runAllNotebookCells,
    draftSourcePlan, refreshLifecycle, verifyPlan, applyPlan, rollbackLatestPlan, clearPlan, toggleOperation, mountDiff, mountContentDiff, revealDiffLine, replaceBuffer,
    persist, modelFor, documentSnapshot, commitModelValue, setCursorPosition, destroyAll, localDiff: BeastDesktopBridge.localDiff
  };
})();
