(() => {
  function escapeHtml(value) { return String(value ?? '').replace(/[&<>"']/g, char => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' })[char]); }
  function formatSize(value) {
    const size = Number(value); if (!Number.isFinite(size) || size <= 0) return '';
    if (size < 1024) return `${size} B`; if (size < 1024 ** 2) return `${(size / 1024).toFixed(1)} KB`; return `${(size / 1024 ** 2).toFixed(1)} MB`;
  }
  function iconFor(path, type) {
    if (type === 'directory') return BeastAssets.icon('project');
    const ext = String(path).split('.').pop().toLowerCase();
    return ['js','jsx','ts','tsx','py','html','css','sh','go','rs'].includes(ext) ? BeastAssets.icon('terminal') : BeastAssets.icon('files');
  }
  function fileName(path) { return String(path || '').split('/').pop() || path; }

  function buildTree(files) {
    const root = { name: '', path: '', type: 'directory', children: new Map() };
    for (const file of files) {
      const parts = file.path.split('/').filter(Boolean);
      let cursor = root;
      parts.forEach((part, index) => {
        const path = parts.slice(0, index + 1).join('/');
        if (!cursor.children.has(part)) cursor.children.set(part, { name: part, path, type: index === parts.length - 1 ? file.type : 'directory', size: index === parts.length - 1 ? file.size : '', children: new Map() });
        cursor = cursor.children.get(part);
      });
    }
    return root;
  }

  function renderTreeNode(node, fragment, depth, state, query) {
    const entries = [...node.children.values()].sort((a, b) => (a.type === b.type ? a.name.localeCompare(b.name) : a.type === 'directory' ? -1 : 1));
    for (const item of entries) {
      const hasMatch = !query || item.path.toLowerCase().includes(query) || [...item.children.values()].some(child => child.path.toLowerCase().includes(query));
      if (!hasMatch) continue;
      const row = document.createElement('button'); row.type = 'button'; row.className = `beast-file-row ${item.type === 'directory' ? 'folder' : ''}`;
      row.style.setProperty('--tree-depth', depth);
      if (item.type === 'directory') row.dataset.folderPath = item.path; else row.dataset.filePath = item.path;
      if (state.editor.activePath === item.path) row.classList.add('active');
      const collapsed = state.editor.collapsedFolders.includes(item.path);
      row.innerHTML = `<span class="beast-tree-caret">${item.type === 'directory' ? (collapsed ? '›' : '⌄') : ''}</span><img src="${iconFor(item.path, item.type)}" alt=""><span class="beast-file-copy"><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.type === 'directory' ? item.path : fileName(item.path))}</small></span><em>${formatSize(item.size)}</em>`;
      fragment.append(row);
      if (item.type === 'directory' && !collapsed) renderTreeNode(item, fragment, depth + 1, state, query);
    }
  }

  function template() {
    const root = document.createElement('div');
    root.className = 'beast-page beast-workspace-page phase2-workspace';
    root.innerHTML = `
      <header class="beast-page-head">
        <div><h2>Editor Cortex</h2><div class="sub">MULTI-TAB MONACO // PERSISTENT BUFFERS // GOVERNED MUTATIONS</div></div>
        <div class="beast-page-actions"><button class="beast-button secondary" data-workspace-action="choose">Choose Folder</button><button class="beast-button" data-workspace-action="refresh">Refresh Index</button></div>
      </header>
      <section class="beast-workspace-toolbar beast-card wide cortex-toolbar">
        <div class="cortex-root"><span class="tiny">WORKSPACE ROOT</span><strong data-workspace-root>No workspace selected</strong></div>
        <div class="beast-workspace-state"><span class="beast-pill" data-workspace-count>0 files</span><span class="beast-pill" data-model-count>0 models</span><span class="beast-pill" data-workspace-dirty>clean</span></div>
      </section>
      <div class="cortex-layout">
        <aside class="beast-card cortex-explorer">
          <div class="cortex-tabbar"><button data-explorer-tab="files" class="active">Files</button><button data-explorer-tab="outline">Outline</button><button data-explorer-tab="recent">Recent</button></div>
          <div class="cortex-explorer-tools">
            <input class="beast-filter" data-file-filter placeholder="Filter workspace…" autocomplete="off">
            <button title="New file" data-file-op="new-file">＋</button><button title="New folder" data-file-op="new-folder">⌑</button><button title="Toggle tree/flat" data-file-op="toggle-mode">≋</button>
          </div>
          <div class="beast-file-list" data-explorer-body role="listbox" aria-label="Workspace explorer"></div>
          <footer class="cortex-explorer-foot"><span data-explorer-status>idle</span><div><button data-file-op="rename">REN</button><button data-file-op="delete">DEL</button></div></footer>
        </aside>
        <section class="beast-card cortex-editor wide">
          <div class="cortex-editor-top">
            <div class="cortex-tabs" data-editor-tabs></div>
            <div class="cortex-editor-tools"><button data-editor-action="split">Split</button><button data-editor-action="revert">Revert</button><button class="hot" data-editor-action="draft">Draft SourcePlan</button></div>
          </div>
          <div class="cortex-editor-stage" data-editor-stage>
            <div class="cortex-editor-pane" data-editor-host></div>
            <textarea class="beast-editor-fallback hidden" data-editor-fallback spellcheck="false" aria-label="BEAST editor"></textarea>
            <div class="cortex-editor-pane hidden" data-editor-split-host></div>
            <textarea class="beast-editor-fallback hidden" data-editor-split-fallback spellcheck="false" aria-label="BEAST split editor"></textarea>
            <div class="cortex-empty" data-editor-empty><img src="${BeastAssets.icon('terminal')}" alt=""><strong>Editor Cortex standing by</strong><span>Select a file or restore a recent buffer.</span></div>
          </div>
          <footer class="cortex-statusbar"><span data-editor-status>No active buffer.</span><span data-editor-position>Ln 1, Col 1</span><span data-layout-status></span></footer>
        </section>
      </div>`;
    return root;
  }

  async function renderer({ signal }) {
    const root = template();
    const explorer = root.querySelector('[data-explorer-body]');
    const filter = root.querySelector('[data-file-filter]');
    const editorHost = root.querySelector('[data-editor-host]');
    const fallback = root.querySelector('[data-editor-fallback]');
    const splitHost = root.querySelector('[data-editor-split-host]');
    const splitFallback = root.querySelector('[data-editor-split-fallback]');
    let disposed = false;
    let lastExplorerKey = '';
    let lastTabsKey = '';

    function renderTabs(state) {
      const key = `${state.editor.openTabs.join('|')}::${state.editor.activePath}::${state.editor.dirtyPaths.join('|')}`;
      if (key === lastTabsKey) return; lastTabsKey = key;
      const host = root.querySelector('[data-editor-tabs]');
      const fragment = document.createDocumentFragment();
      state.editor.openTabs.forEach(path => {
        const tab = document.createElement('button'); tab.type = 'button'; tab.className = 'cortex-tab'; tab.dataset.editorTab = path;
        if (path === state.editor.activePath) tab.classList.add('active');
        if (state.editor.dirtyPaths.includes(path)) tab.classList.add('dirty');
        tab.innerHTML = `<img src="${iconFor(path, 'file')}" alt=""><span>${escapeHtml(fileName(path))}</span><i data-close-tab="${escapeHtml(path)}">×</i>`;
        fragment.append(tab);
      });
      host.replaceChildren(fragment);
    }

    function renderExplorer(state) {
      const query = filter.value.trim().toLowerCase();
      const key = `${state.editor.explorerTab}|${state.editor.explorerMode}|${state.workspace.files.map(file => file.path).join('|')}|${state.editor.collapsedFolders.join('|')}|${state.editor.activePath}|${state.editor.outline.map(row => `${row.name}:${row.line}`).join('|')}|${state.editor.recentFiles.join('|')}|${query}`;
      if (key === lastExplorerKey) return; lastExplorerKey = key;
      const fragment = document.createDocumentFragment();
      if (state.editor.explorerTab === 'outline') {
        if (!state.editor.outline.length) explorer.innerHTML = '<div class="cortex-empty-list">No symbols detected in the active buffer.</div>';
        else {
          state.editor.outline.forEach(symbol => {
            const row = document.createElement('button'); row.className = 'beast-file-row symbol'; row.dataset.gotoLine = symbol.line;
            row.innerHTML = `<span class="beast-tree-caret">${symbol.kind === 'type' ? '◆' : 'ƒ'}</span><span class="beast-file-copy"><strong>${escapeHtml(symbol.name)}</strong><small>line ${symbol.line}</small></span><em>${escapeHtml(symbol.kind)}</em>`;
            fragment.append(row);
          }); explorer.replaceChildren(fragment);
        }
      } else if (state.editor.explorerTab === 'recent') {
        if (!state.editor.recentFiles.length) explorer.innerHTML = '<div class="cortex-empty-list">No recent files yet.</div>';
        else {
          state.editor.recentFiles.forEach(path => {
            const row = document.createElement('button'); row.className = 'beast-file-row'; row.dataset.filePath = path;
            row.innerHTML = `<span class="beast-tree-caret">↺</span><img src="${iconFor(path, 'file')}" alt=""><span class="beast-file-copy"><strong>${escapeHtml(fileName(path))}</strong><small>${escapeHtml(path)}</small></span>`;
            fragment.append(row);
          }); explorer.replaceChildren(fragment);
        }
      } else if (state.editor.explorerMode === 'flat') {
        state.workspace.files.filter(item => !query || item.path.toLowerCase().includes(query)).slice(0, 1400).forEach(item => {
          const row = document.createElement('button'); row.className = 'beast-file-row'; row.dataset.filePath = item.path;
          if (item.path === state.editor.activePath) row.classList.add('active');
          row.innerHTML = `<span class="beast-tree-caret"></span><img src="${iconFor(item.path, item.type)}" alt=""><span class="beast-file-copy"><strong>${escapeHtml(item.name || fileName(item.path))}</strong><small>${escapeHtml(item.path)}</small></span><em>${formatSize(item.size)}</em>`;
          fragment.append(row);
        }); explorer.replaceChildren(fragment);
      } else {
        renderTreeNode(buildTree(state.workspace.files), fragment, 0, state, query); explorer.replaceChildren(fragment);
      }
    }

    function patch(state) {
      if (disposed) return;
      root.querySelector('[data-workspace-root]').textContent = state.workspace.root || 'No workspace selected';
      root.querySelector('[data-workspace-count]').textContent = state.workspace.loading ? 'indexing…' : `${state.workspace.files.length} files`;
      root.querySelector('[data-model-count]').textContent = `${state.editor.modelCount} models`;
      const dirty = root.querySelector('[data-workspace-dirty]'); dirty.textContent = state.editor.dirtyPaths.length ? `● ${state.editor.dirtyPaths.length} staged` : 'clean'; dirty.classList.toggle('warn', Boolean(state.editor.dirtyPaths.length));
      root.querySelector('[data-explorer-status]').textContent = state.workspace.error || (state.workspace.loading ? 'indexing' : `${state.editor.explorerMode} mode`);
      root.querySelector('[data-editor-status]').textContent = state.workspace.error || (state.editor.activePath ? `${state.workspace.language} · ${state.workspace.dirty ? 'SourcePlan required before write' : 'clean buffer'} · ${state.editor.owner}` : 'No active buffer.');
      root.querySelector('[data-editor-position]').textContent = `Ln ${state.editor.cursor.line}, Col ${state.editor.cursor.column}`;
      root.querySelector('[data-layout-status]').textContent = `${state.diagnostics.viewport || ''} · ${state.diagnostics.horizontalOverflow ? 'overflow!' : 'stable'}`;
      root.querySelector('[data-editor-empty]').classList.toggle('hidden', Boolean(state.editor.activePath));
      root.querySelectorAll('[data-explorer-tab]').forEach(button => button.classList.toggle('active', button.dataset.explorerTab === state.editor.explorerTab));
      root.querySelector('[data-editor-action="split"]').classList.toggle('active', state.editor.split);
      renderTabs(state); renderExplorer(state);
    }

    const unsubscribe = BeastStore.subscribe(patch);
    queueMicrotask(() => BeastEditorCortex.mount({ host: editorHost, fallback, splitHost, splitFallback }));

    root.addEventListener('click', async event => {
      const close = event.target.closest('[data-close-tab]');
      if (close) { event.stopPropagation(); BeastEditorCortex.closeTab(close.dataset.closeTab); return; }
      const tab = event.target.closest('[data-editor-tab]'); if (tab) { BeastEditorCortex.activate(tab.dataset.editorTab); return; }
      const file = event.target.closest('[data-file-path]'); if (file) { await BeastEditorCortex.openFile(file.dataset.filePath, { signal }); BeastMascot.setState('working'); setTimeout(() => BeastMascot.setState('idle'), 650); return; }
      const folder = event.target.closest('[data-folder-path]'); if (folder) { BeastEditorCortex.toggleFolder(folder.dataset.folderPath); return; }
      const symbol = event.target.closest('[data-goto-line]'); if (symbol) { BeastEditorCortex.gotoLine(Number(symbol.dataset.gotoLine)); return; }
      const explorerTab = event.target.closest('[data-explorer-tab]'); if (explorerTab) { BeastEditorCortex.setExplorerTab(explorerTab.dataset.explorerTab); return; }
      const action = event.target.closest('[data-workspace-action]')?.dataset.workspaceAction;
      if (action === 'choose') { try { await BeastDesktopBridge.chooseWorkspace(); await BeastDesktopBridge.listFiles({ signal }); await BeastEditorCortex.restoreTabs(); } catch (error) { BeastStore.patch('workspace', { error: String(error.message || error) }); } return; }
      if (action === 'refresh') { await BeastDesktopBridge.listFiles({ signal }); return; }
      const editorAction = event.target.closest('[data-editor-action]')?.dataset.editorAction;
      if (editorAction === 'split') { BeastEditorCortex.toggleSplit(); return; }
      if (editorAction === 'revert') { BeastEditorCortex.revertActive(); return; }
      if (editorAction === 'draft') {
        try { await BeastEditorCortex.draftSourcePlan(); BeastFX.trigger('success', event.target, { size: 240 }); await BeastRouter.navigate('source'); }
        catch (error) { BeastStore.patch('sourcePlan', { status: 'error', message: String(error.message || error), error: String(error.message || error) }); BeastFX.trigger('warning', event.target, { size: 220 }); }
        return;
      }
      const op = event.target.closest('[data-file-op]')?.dataset.fileOp;
      if (!op) return;
      if (op === 'toggle-mode') { BeastEditorCortex.setExplorerMode(BeastStore.get().editor.explorerMode === 'tree' ? 'flat' : 'tree'); return; }
      const activePath = BeastStore.get().editor.activePath;
      let operation = null;
      if (op === 'new-file' || op === 'new-folder') {
        const suggested = op === 'new-folder' ? 'src/new_module' : 'src/new_file.py';
        const path = window.prompt(op === 'new-folder' ? 'New folder path' : 'New file path', suggested); if (!path) return;
        operation = { op: op === 'new-folder' ? 'create_folder' : 'create_file', path, content: '' };
      }
      if (op === 'rename') { if (!activePath) return; const target = window.prompt('Rename active file to', activePath); if (!target || target === activePath) return; operation = { op: 'rename', path: activePath, target }; }
      if (op === 'delete') { if (!activePath) return; operation = { op: 'delete_file', path: activePath }; }
      if (!operation) return;
      try {
        const receipt = await BeastDesktopBridge.classifyFileOperation(operation, { signal });
        if (receipt.decision === 'block') throw new Error('Safety Governor blocked this operation.');
        if (!window.confirm(`${operation.op}: ${operation.path}${operation.target ? ` → ${operation.target}` : ''}\n\nSafety decision: ${receipt.decision || 'allow'}`)) return;
        const result = await BeastDesktopBridge.fileOperation(operation, { signal });
        if (!result?.ok) throw new Error(result?.error || 'File operation failed.');
        if (op === 'delete') BeastEditorCortex.closeTab(activePath);
        await BeastDesktopBridge.listFiles({ signal });
        if (op === 'new-file') await BeastEditorCortex.openFile(result.path || operation.path, { signal });
        if (op === 'rename') { BeastEditorCortex.closeTab(activePath); await BeastEditorCortex.openFile(result.target || operation.target, { signal }); }
        BeastStore.addLedger(`Governed file operation complete: ${operation.op}`);
      } catch (error) { BeastStore.patch('workspace', { error: String(error.message || error) }); }
    });

    filter.addEventListener('input', () => { lastExplorerKey = ''; patch(BeastStore.get()); });
    if (!BeastStore.get().workspace.indexedAt && BeastStore.get().workspace.root) queueMicrotask(() => BeastDesktopBridge.listFiles({ signal }));

    return { node: root, dispose() { disposed = true; unsubscribe(); BeastEditorCortex.unmount(); } };
  }

  window.BeastWorkspacePage = { renderer };
})();
