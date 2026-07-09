let gatewayUrl = 'http://127.0.0.1:8000';
let workspaceRoot = '';
let currentFile = '';
let currentPage = 'mission';
let originalText = '';
let currentSnapshot = null;
let currentSourcePlan = null;
let currentSourcePlanLifecycle = null;
let currentAgentSession = null;
let currentWorktreeTask = null;
let ideEventStream = null;
let agentRunStream = null;
let lastCommandSafety = null;
let desktopLocalMode = false;
let monacoReady = null;
let monacoEditor = null;
let monacoSplitEditor = null;
let monacoDiffEditor = null;
let openFiles = [];
let fileModels = new Map();
let fileOriginals = new Map();
let dirtyFiles = new Set();
let explorerRows = [];
let collapsedFolders = new Set();
let explorerFlatMode = true;
let symbolOutlineRows = [];
let selectedSymbol = null;
let symbolSearchRows = [];
let selectedSymbolSearch = null;
let recentFiles = [];
let pendingRestoreTabs = [];
let pendingRestoreCurrentFile = '';
let restoredWorkspaceRoot = '';
let selectedSourcePlanOpId = '';
let lastApplyResult = null;
let splitEditorVisible = false;
let terminalHistory = [];
let terminalHistoryIndex = -1;
let terminalExecutions = [];
let lastTerminalExecution = null;
let terminalStreamSource = null;
let terminalStreamBuffer = null;
let agentRunStages = [];
let agentRunTools = [];
let pendingAgentPatch = null;
let lastMissionRunbook = null;
let ideActions = [];
let lastGatewayStatus = null;
let lastProviderError = '';
let lastToolingSnapshot = null;
let lastBenchmarkVerdict = null;
let selectedDiffHunks = new Set();
let commandPaletteRecents = [];
let desktopBuildInfo = { version: 'renderer-ux-modal-chips', rendererPath: '' };
let selectedProvider = localStorage.getItem('beast.provider') || 'nvidia_nim';
const DEFAULT_NVIDIA_NIM_MODEL = 'meta/llama-3.1-8b-instruct';
const KNOWN_NVIDIA_NIM_MODELS = [DEFAULT_NVIDIA_NIM_MODEL, 'nvidia/nemotron-3-super-120b-a12b'];
let selectedModel = localStorage.getItem('beast.model') || DEFAULT_NVIDIA_NIM_MODEL;
let snapshotRefreshPromise = null;
let lastSnapshotRefreshAt = 0;
let lastFilesRefreshAt = 0;
let lastManifestRefreshAt = 0;
let lastTimelineRefreshAt = 0;
const AGENT_INLINE_SELECTION_LIMIT = 12000;
const AGENT_PATCH_REPLACEMENT_LIMIT = 12000;
const AGENT_CONTEXT_FILE_CHARS = 30000;
const TERMINAL_HISTORY_KEY = 'beast.desktop.terminal.history';
const TERMINAL_EXECUTIONS_KEY = 'beast.desktop.terminal.executions';
const WORKSPACE_STATE_KEY = 'beast.desktop.workspace.state';
const SNAPSHOT_COOLDOWN_MS = 1800;
const FILES_REFRESH_TTL_MS = 12000;
const MANIFEST_REFRESH_TTL_MS = 20000;
const TIMELINE_REFRESH_TTL_MS = 10000;
const desktopPages = {
  mission:   { label: 'Mission',           tab: 'editor' },
  source:    { label: 'SourcePlan',         tab: 'diff' },
  agents:    { label: 'Agent Sessions',     tab: 'editor' },
  worktrees: { label: 'Worktree Missions',  tab: 'diff' },
  evidence:  { label: 'Evidence Bus',       tab: 'editor' },
  terminal:  { label: 'Governed Terminal',  tab: 'terminal' },
  providers: { label: 'Provider Setup',     tab: 'editor' },
  tooling:   { label: 'Tooling Plane',      tab: 'editor' },
  system:    { label: 'System Plane',        tab: 'editor' },
  doctor:    { label: 'Gateway Doctor',     tab: 'terminal' },
  settings:  { label: 'IDE Controls',       tab: 'editor' },
  studio:    { label: 'BEAST Studio',       tab: 'editor' },
};

const $ = id => document.getElementById(id);

function inferLanguage(path) {
  const ext = String(path || '').split('.').pop().toLowerCase();
  return {
    js: 'javascript',
    jsx: 'javascript',
    ts: 'typescript',
    tsx: 'typescript',
    py: 'python',
    json: 'json',
    md: 'markdown',
    html: 'html',
    css: 'css',
    yml: 'yaml',
    yaml: 'yaml',
    sh: 'shell',
  }[ext] || 'plaintext';
}

function editorUriForPath(path) {
  return monaco.Uri.parse(`file:///${encodeURIComponent(path).replace(/%2F/g, '/')}`);
}

function initMonaco() {
  if (monacoReady) return monacoReady;
  monacoReady = new Promise(resolve => {
    if (!window.require) {
      log('Monaco loader unavailable; using fallback buffer.');
      resolve(false);
      return;
    }
    window.require.config({ paths: { vs: '../node_modules/monaco-editor/min/vs' } });
    window.require(['vs/editor/editor.main'], () => {
      monaco.editor.defineTheme('beast-dark', {
        base: 'vs-dark',
        inherit: true,
        rules: [
          { token: '', foreground: 'd7fbe8', background: '020403' },
          { token: 'comment', foreground: '7a8c8d' },
          { token: 'keyword', foreground: '33f6ff' },
          { token: 'string', foreground: 'a6ff3f' },
          { token: 'number', foreground: 'ffd166' },
        ],
        colors: {
          'editor.background': '#020403',
          'editor.foreground': '#d7fbe8',
          'editorLineNumber.foreground': '#486164',
          'editorCursor.foreground': '#5cff95',
          'editor.selectionBackground': '#1f3a3d',
          'editor.lineHighlightBackground': '#0b1113',
          'editorGutter.background': '#020403',
          'minimap.background': '#020403',
        },
      });
      monacoEditor = monaco.editor.create($('monacoEditor'), {
        value: '',
        language: 'plaintext',
        theme: 'beast-dark',
        automaticLayout: true,
        minimap: { enabled: true },
        fontSize: 13,
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
        lineNumbers: 'on',
        scrollBeyondLastLine: false,
        wordWrap: 'on',
        glyphMargin: true,
      });
      monacoSplitEditor = monaco.editor.create($('monacoSplitEditor'), {
        value: '',
        language: 'plaintext',
        theme: 'beast-dark',
        automaticLayout: true,
        minimap: { enabled: false },
        fontSize: 13,
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
        lineNumbers: 'on',
        scrollBeyondLastLine: false,
        wordWrap: 'on',
        glyphMargin: false,
      });
      monacoDiffEditor = monaco.editor.createDiffEditor($('monacoDiff'), {
        theme: 'beast-dark',
        automaticLayout: true,
        renderSideBySide: true,
        minimap: { enabled: true },
        readOnly: true,
        originalEditable: false,
      });
      monaco.languages.registerHoverProvider('*', {
        provideHover(model, position) {
          const path = currentFile || model.uri.path.replace(/^\//, '');
          const dirty = dirtyFiles.has(path) ? 'dirty buffer: SourcePlan required before write' : 'clean buffer';
          const relatedCount = $('relatedContext').querySelectorAll('.file-item').length;
          return {
            range: new monaco.Range(position.lineNumber, 1, position.lineNumber, 1),
            contents: [
              { value: `**BEAST Code Cortex**` },
              { value: `${path} · ${dirty}` },
              { value: `Related context candidates: ${relatedCount}` },
              { value: `Mutation path: SourcePlan -> policy gate -> verify -> evidence.` },
            ],
          };
        },
      });
      monacoEditor.onDidChangeModelContent(() => {
        if (!currentFile) return;
        const value = monacoEditor.getValue();
        $('editorText').value = value;
        if (value === (fileOriginals.get(currentFile) ?? originalText)) {
          dirtyFiles.delete(currentFile);
          clearPersistedBuffer(currentFile);
        } else {
          dirtyFiles.add(currentFile);
          persistDirtyBuffer(currentFile);
        }
        updateEditorMeta();
        updateOpenTabs();
        renderFileExplorer();
        updateDiagnosticsAndDecorations();
        diffCurrentEdit();
        updateStatusChips();
        renderSourcePlanChecklist();
        renderNextActionInspector();
      });
      monacoEditor.onDidChangeCursorSelection(updateEditorMeta);
      monacoEditor.addAction({
        id: 'beast-sourceplan-from-selection',
        label: 'BEAST: SourcePlan From Selection',
        keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyS],
        run: () => sourcePlanSelectionDraft(),
      });
      monacoEditor.addAction({
        id: 'beast-ask-agent-about-selection',
        label: 'BEAST: Ask Agent About Selection',
        keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyA],
        run: () => askAgentAboutSelection(),
      });
      monacoEditor.addAction({
        id: 'beast-jump-related-context',
        label: 'BEAST: Refresh Related Context',
        keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyR],
        run: () => refreshRelatedContext(),
      });
      resolve(true);
    });
  });
  return monacoReady;
}

function getEditorValue() {
  return monacoEditor ? monacoEditor.getValue() : $('editorText').value;
}

function setEditorValue(value) {
  $('editorText').value = value;
  if (monacoEditor && currentFile) {
    const model = ensureModel(currentFile, value);
    monacoEditor.setModel(model);
    monacoSplitEditor?.setModel(model);
  } else if (monacoEditor) {
    monacoEditor.setValue(value);
  }
}

function workspaceStateKey(root = workspaceRoot) {
  return `${WORKSPACE_STATE_KEY}:${root || 'workspace'}`;
}

function saveWorkspaceState() {
  if (!workspaceRoot) return;
  const state = {
    workspaceRoot,
    currentFile,
    openFiles: openFiles.slice(0, 20),
    recentFiles: recentFiles.slice(0, 40),
    collapsedFolders: Array.from(collapsedFolders),
    explorerFlatMode,
    selectedProvider,
    selectedModel,
    selectedAgentSessionId: currentAgentSession?.session_id || '',
    selectedWorktreeTaskId: currentWorktreeTask?.task_id || '',
    commandPaletteRecents: commandPaletteRecents.slice(0, 20),
    splitEditorVisible,
    currentPage,
    collapsedPanels: Array.from(document.querySelectorAll('[data-panel-body].collapsed')).map(node => node.dataset.panelBody),
  };
  localStorage.setItem(workspaceStateKey(), JSON.stringify(state));
  localStorage.setItem(`${WORKSPACE_STATE_KEY}:last-root`, workspaceRoot);
}

function loadWorkspaceState() {
  const fallbackRoot = localStorage.getItem(`${WORKSPACE_STATE_KEY}:last-root`) || '';
  if (!workspaceRoot && fallbackRoot) workspaceRoot = fallbackRoot;
  if (!workspaceRoot || restoredWorkspaceRoot === workspaceRoot) return;
  let state = {};
  try {
    state = JSON.parse(localStorage.getItem(workspaceStateKey()) || '{}');
  } catch (_error) {
    state = {};
  }
  collapsedFolders = new Set(Array.isArray(state.collapsedFolders) ? state.collapsedFolders : []);
  explorerFlatMode = Boolean(state.explorerFlatMode);
  recentFiles = Array.isArray(state.recentFiles) ? state.recentFiles.filter(Boolean) : [];
  pendingRestoreTabs = Array.isArray(state.openFiles) ? state.openFiles.filter(Boolean).slice(0, 8) : [];
  pendingRestoreCurrentFile = state.currentFile || pendingRestoreTabs[0] || '';
  selectedProvider = state.selectedProvider || localStorage.getItem(providerStorageKey('provider')) || selectedProvider;
  selectedModel = state.selectedModel || localStorage.getItem(providerStorageKey('model')) || selectedModel;
  commandPaletteRecents = Array.isArray(state.commandPaletteRecents) ? state.commandPaletteRecents.filter(Boolean).slice(0, 20) : [];
  if (state.selectedAgentSessionId) currentAgentSession = { session_id: state.selectedAgentSessionId, status: 'restoring' };
  if (state.selectedWorktreeTaskId) currentWorktreeTask = { task_id: state.selectedWorktreeTaskId, status: 'restoring' };
  splitEditorVisible = Boolean(state.splitEditorVisible);
  applyCollapsedPanels(Array.isArray(state.collapsedPanels) ? state.collapsedPanels : []);
  restoredWorkspaceRoot = workspaceRoot;
  syncProviderControls();
  applySplitEditorState();
}

function applyCollapsedPanels(panelIds = []) {
  const collapsed = new Set(panelIds);
  document.querySelectorAll('[data-panel-body]').forEach(body => {
    const shouldCollapse = collapsed.has(body.dataset.panelBody);
    body.classList.toggle('collapsed', shouldCollapse);
    document.querySelector(`[data-collapse-panel="${CSS.escape(body.dataset.panelBody)}"]`)?.classList.toggle('collapsed', shouldCollapse);
  });
}

async function restoreWorkspaceTabs() {
  if (!pendingRestoreTabs.length && !pendingRestoreCurrentFile) return;
  const files = uniqueFiles([pendingRestoreCurrentFile, ...pendingRestoreTabs]).filter(Boolean).slice(0, 8);
  pendingRestoreTabs = [];
  pendingRestoreCurrentFile = '';
  for (const file of files) {
    await openFile(file, { refreshSnapshot: false, silent: true });
  }
  if (files.length) {
    await openFile(files[0], { refreshSnapshot: false, silent: true });
    log(`restored ${files.length} editor tab${files.length === 1 ? '' : 's'} for ${workspaceRoot}`);
  }
}

function rememberRecentFile(path) {
  if (!path) return;
  recentFiles = [path, ...recentFiles.filter(item => item !== path)].slice(0, 40);
  saveWorkspaceState();
}

function applySplitEditorState() {
  const host = $('editorSplitHost');
  const peer = $('monacoSplitEditor');
  if (!host || !peer) return;
  host.classList.toggle('split-active', splitEditorVisible);
  peer.classList.toggle('hidden', !splitEditorVisible);
  const model = monacoEditor?.getModel();
  if (splitEditorVisible && model) monacoSplitEditor?.setModel(model);
  monacoEditor?.layout();
  monacoSplitEditor?.layout();
  saveWorkspaceState();
}

function toggleSplitEditor() {
  splitEditorVisible = !splitEditorVisible;
  applySplitEditorState();
  log(`split editor ${splitEditorVisible ? 'enabled' : 'disabled'}`);
}

function undoEdit() {
  if (!monacoEditor) return;
  monacoEditor.trigger('beast-desktop', 'undo', null);
  updateEditorMeta();
}

function redoEdit() {
  if (!monacoEditor) return;
  monacoEditor.trigger('beast-desktop', 'redo', null);
  updateEditorMeta();
}

function quoteCommandPath(path) {
  return `"${String(path || '').replace(/(["\\$`])/g, '\\$1')}"`;
}

function commandForFileOperation(operation) {
  if (operation.op === 'create_file') return `touch ${quoteCommandPath(operation.path)}`;
  if (operation.op === 'create_folder') return `mkdir -p ${quoteCommandPath(operation.path)}`;
  if (operation.op === 'rename') return `mv ${quoteCommandPath(operation.path)} ${quoteCommandPath(operation.target)}`;
  if (operation.op === 'delete_file') return `rm ${quoteCommandPath(operation.path)}`;
  return `workspace-file-op ${quoteCommandPath(operation.path)}`;
}

async function classifyFileOperation(operation) {
  if (desktopLocalMode) return { decision: 'warn', risk_level: 'local', reasons: [{ detail: 'Gateway offline; local confirmation required.' }] };
  const receipt = await postJson('/edgek/safety-governor/classify-command', {
    root_path: workspaceRoot,
    command: commandForFileOperation(operation),
    mode: currentAgentSession?.mode || 'operator',
    task_id: currentAgentSession?.session_id || currentWorktreeTask?.task_id || '',
    operator_override: 'BEAST Desktop file explorer mutation requires explicit operator confirmation.',
  });
  return receipt;
}

async function runGovernedFileOperation(operation) {
  const receipt = await classifyFileOperation(operation);
  const decision = receipt.decision || 'allow';
  if (decision === 'block') {
    log(`file operation blocked by Safety Governor: ${operation.op} ${operation.path}`);
    renderTerminalDecision(receipt);
    return null;
  }
  const details = `${operation.op}: ${operation.path}${operation.target ? ` -> ${operation.target}` : ''}`;
  if (!window.confirm(`Run file operation?\n${details}\n\nSafety decision: ${decision}`)) return null;
  const result = await window.beastDesktop.fileOperation(workspaceRoot, operation);
  log(`file operation ${result.ok ? 'ok' : 'failed'}: ${details}${result.error ? ` · ${result.error}` : ''}`);
  await refreshFiles();
  renderFileExplorer();
  return result;
}

async function createWorkspaceFile() {
  const parent = currentFile ? currentFile.split('/').slice(0, -1).join('/') : '';
  const rel = window.prompt('New file or folder path', parent ? `${parent}/new_file.py` : 'new_file.py');
  if (!rel) return;
  const folder = rel.endsWith('/');
  const result = await runGovernedFileOperation({ op: folder ? 'create_folder' : 'create_file', path: folder ? rel.replace(/\/+$/, '') : rel, content: '' });
  if (result?.ok && !folder) await openFile(result.path || rel);
}

async function renameWorkspaceFile() {
  if (!currentFile) {
    log('rename blocked: no active file.');
    return;
  }
  const target = window.prompt('Rename active file to', currentFile);
  if (!target || target === currentFile) return;
  const result = await runGovernedFileOperation({ op: 'rename', path: currentFile, target });
  if (result?.ok) {
    closeEditorTab(currentFile);
    await openFile(result.target || target);
  }
}

async function deleteWorkspaceFile() {
  if (!currentFile) {
    log('delete blocked: no active file.');
    return;
  }
  const target = currentFile;
  if (!window.confirm(`Delete ${target}? This removes the file locally after Safety Governor classification.`)) return;
  const result = await runGovernedFileOperation({ op: 'delete_file', path: target });
  if (result?.ok) {
    closeEditorTab(target);
    await refreshFiles();
  }
}

function ensureModel(path, value) {
  if (!window.monaco) return null;
  if (fileModels.has(path)) {
    return fileModels.get(path);
  }
  const model = monaco.editor.createModel(value || '', inferLanguage(path), editorUriForPath(path));
  fileModels.set(path, model);
  return model;
}

function log(line) {
  const terminal = $('terminalLog');
  terminal.textContent = `${terminal.textContent}\n${line}`.slice(-20000);
  terminal.scrollTop = terminal.scrollHeight;
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function normalizeFetchError(error, path, timeoutMs) {
  const raw = error?.message || error?.name || String(error || 'request failed');
  if (error?.name === 'AbortError' || /aborted|abort/i.test(String(raw))) {
    return new Error(`${path} timed out after ${Math.round(timeoutMs / 1000)}s while the gateway route was warming`);
  }
  if (/failed to fetch|networkerror|econnrefused/i.test(String(raw))) {
    return new Error(`${path} is not reachable yet (${raw})`);
  }
  return error instanceof Error ? error : new Error(String(raw));
}

async function withGatewayWarmupRetry(label, operation, timeoutMs = 20000) {
  try {
    return await operation(timeoutMs);
  } catch (error) {
    const text = String(error?.message || error);
    const canRetry = lastGatewayStatus?.health?.ok && /timed out|warming|not reachable|failed to fetch/i.test(text);
    if (!canRetry) throw error;
    log(`${label}: gateway route is still warming; retrying once before local fallback.`);
    await sleep(2500);
    try {
      return await operation(timeoutMs + 15000);
    } catch (secondError) {
      throw normalizeFetchError(secondError, label, timeoutMs + 15000);
    }
  }
}

async function getJson(path, timeoutMs = 20000) {
  const url = `${gatewayUrl}${path}`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { headers: { accept: 'application/json' }, signal: controller.signal })
      .finally(() => clearTimeout(timeout));
    if (!response.ok) throw new Error(`${path} -> ${response.status}`);
    return response.json();
  } catch (error) {
    clearTimeout(timeout);
    throw normalizeFetchError(error, path, timeoutMs);
  }
}

async function postJson(path, payload, timeoutMs = 20000) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${gatewayUrl}${path}`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', accept: 'application/json' },
      body: JSON.stringify(payload || {}),
      signal: controller.signal,
    }).finally(() => clearTimeout(timeout));
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `${path} -> ${response.status}`);
    return data;
  } catch (error) {
    clearTimeout(timeout);
    throw normalizeFetchError(error, path, timeoutMs);
  }
}

function rootParam() {
  return workspaceRoot ? `root_path=${encodeURIComponent(workspaceRoot)}` : '';
}

function emptyCard(message, action = '') {
  return `<div class="mini-card muted empty-state">${escapeHtml(message)}${action ? `<br><span>${escapeHtml(action)}</span>` : ''}</div>`;
}

function renderList(target, rows, formatter, emptyMessage = 'No records yet.', emptyAction = '') {
  target.innerHTML = rows && rows.length ? rows.map(formatter).join('') : emptyCard(emptyMessage, emptyAction);
}

function filePathForItem(item) {
  if (typeof item === 'string') return item;
  if (!item || typeof item !== 'object') return '';
  const props = item.properties && typeof item.properties === 'object' ? item.properties : {};
  return String(item.path || item.file || item.relative_path || props.path || props.relative_path || props.file || item.id || '');
}

function buildFileTree(rows) {
  const root = { name: '', path: '', folders: new Map(), files: [] };
  for (const item of rows || []) {
    const rel = filePathForItem(item);
    if (!rel) continue;
    const parts = rel.split('/').filter(Boolean);
    let node = root;
    for (const part of parts.slice(0, -1)) {
      const nextPath = node.path ? `${node.path}/${part}` : part;
      if (!node.folders.has(part)) {
        node.folders.set(part, { name: part, path: nextPath, folders: new Map(), files: [] });
      }
      node = node.folders.get(part);
    }
    node.files.push({ ...item, path: rel, name: parts[parts.length - 1] || rel });
  }
  return root;
}

function countTreeFiles(node) {
  let count = node.files.length;
  node.folders.forEach(folder => { count += countTreeFiles(folder); });
  return count;
}

function setExplorerStatus(message, tone = '') {
  const node = $('fileExplorerStatus');
  if (!node) return;
  node.textContent = message;
  node.className = `explorer-status ${tone}`.trim();
}

function renderTreeNode(node) {
  const folderRows = Array.from(node.folders.values())
    .sort((a, b) => a.name.localeCompare(b.name))
    .map(folder => {
      const collapsed = collapsedFolders.has(folder.path);
      const count = countTreeFiles(folder);
      return [
        '<div class="tree-node">',
        `<button class="tree-folder" data-folder-path="${escapeHtml(folder.path)}" aria-expanded="${collapsed ? 'false' : 'true'}">${collapsed ? '+' : '-'} ${escapeHtml(folder.name)} <span class="folder-count">${count}</span></button>`,
        collapsed ? '' : `<div class="tree-children">${renderTreeNode(folder)}</div>`,
        '</div>',
      ].join('');
    });
  const fileRows = node.files
    .sort((a, b) => a.name.localeCompare(b.name))
    .map(item => {
      const path = item.path;
      const active = path === currentFile ? ' active' : '';
      const dirty = dirtyFiles.has(path) ? ' dirty' : '';
      const source = escapeHtml(item.source || item.properties?.source || '');
      return [
        `<button class="file-item tree-file${active}${dirty}" data-path="${escapeHtml(path)}" title="${escapeHtml(path)}">`,
        escapeHtml(item.name || path),
        source ? `<br><span class="muted">${source}</span>` : '',
        '</button>',
      ].join('');
    });
  return [...folderRows, ...fileRows].join('');
}

function renderFlatFileRows(rows) {
  return rows
    .sort((a, b) => filePathForItem(a).localeCompare(filePathForItem(b)))
    .map(item => {
      const path = filePathForItem(item);
      const active = path === currentFile ? ' active' : '';
      const dirty = dirtyFiles.has(path) ? ' dirty' : '';
      const source = escapeHtml(item.source || item.properties?.source || '');
      return [
        `<button class="file-item tree-file${active}${dirty}" data-path="${escapeHtml(path)}" title="${escapeHtml(path)}">`,
        escapeHtml(path),
        source ? `<br><span class="muted">${source}</span>` : '',
        '</button>',
      ].join('');
    }).join('');
}

function renderFileExplorer() {
  try {
    const needle = $('fileFilter').value.trim().toLowerCase();
    const filtered = explorerRows.filter(item => filePathForItem(item).toLowerCase().includes(needle));
    const tree = buildFileTree(filtered);
    const folderCount = Array.from(tree.folders.values()).length;
    $('toggleExplorerMode').textContent = explorerFlatMode ? 'Tree' : 'Flat';
    $('fileList').innerHTML = explorerFlatMode
      ? renderFlatFileRows(filtered)
      : renderTreeNode(tree);
    if (!$('fileList').innerHTML) {
      $('fileList').innerHTML = emptyCard('No files match this workspace/filter.', 'Try Refresh, Choose Folder, or clear the filter.');
    }
    setExplorerStatus(`${filtered.length}/${explorerRows.length} files · ${folderCount} top folder(s) · ${explorerFlatMode ? 'flat' : 'tree'} view`);
  } catch (error) {
    $('fileList').innerHTML = emptyCard('File explorer render failed.', error.message || String(error));
    setExplorerStatus(`Explorer error: ${error.message || error}`, 'bad');
    log(`file explorer render failed: ${error.stack || error.message || error}`);
  }
}

function updateOpenTabs() {
  $('openTabs').innerHTML = openFiles.length ? openFiles.map(path => {
    const active = path === currentFile ? ' active' : '';
    const dirty = dirtyFiles.has(path) ? ' dirty' : '';
    const label = path.split('/').pop() || path;
    return [
      `<button class="open-tab${active}${dirty}" data-tab-path="${escapeHtml(path)}" title="${escapeHtml(path)}">`,
      `<span>${escapeHtml(label)}</span>`,
      `<span class="close-tab" data-close-tab="${escapeHtml(path)}">x</span>`,
      '</button>',
    ].join('');
  }).join('') : '<div class="mini-card muted">Open a file from the explorer.</div>';
}

function updateMonacoDiff(original, next) {
  if (!monacoDiffEditor || !window.monaco || !currentFile) return;
  const language = inferLanguage(currentFile);
  const originalModel = monaco.editor.createModel(original || '', language);
  const modifiedModel = monaco.editor.createModel(next || '', language);
  const previous = monacoDiffEditor.getModel();
  monacoDiffEditor.setModel({ original: originalModel, modified: modifiedModel });
  if (previous?.original) previous.original.dispose();
  if (previous?.modified) previous.modified.dispose();
}

function changedLineRanges(original, next) {
  const oldLines = String(original || '').split('\n');
  const newLines = String(next || '').split('\n');
  const max = Math.max(oldLines.length, newLines.length);
  const ranges = [];
  for (let index = 0; index < max; index += 1) {
    if (oldLines[index] !== newLines[index]) {
      ranges.push(index + 1);
    }
  }
  return ranges;
}

function updateDiagnosticsAndDecorations() {
  if (!monacoEditor || !window.monaco || !currentFile) return;
  const model = monacoEditor.getModel();
  if (!model) return;
  const value = model.getValue();
  const markers = [];
  const decorations = [];
  const lines = value.split('\n');
  lines.forEach((line, index) => {
    if (/\b(TODO|FIXME|XXX)\b/i.test(line)) {
      markers.push({
        severity: monaco.MarkerSeverity.Warning,
        message: 'BEAST diagnostic: unresolved TODO/FIXME should be considered before SourcePlan apply.',
        startLineNumber: index + 1,
        startColumn: 1,
        endLineNumber: index + 1,
        endColumn: Math.max(2, line.length + 1),
      });
    }
    if (/\b(eval|exec)\s*\(/.test(line)) {
      markers.push({
        severity: monaco.MarkerSeverity.Error,
        message: 'BEAST diagnostic: dynamic execution requires explicit policy and security review.',
        startLineNumber: index + 1,
        startColumn: 1,
        endLineNumber: index + 1,
        endColumn: Math.max(2, line.length + 1),
      });
    }
    if (/\bconsole\.log\s*\(|\bprint\s*\(/.test(line)) {
      markers.push({
        severity: monaco.MarkerSeverity.Info,
        message: 'BEAST diagnostic: debug output should be intentional before SourcePlan apply.',
        startLineNumber: index + 1,
        startColumn: 1,
        endLineNumber: index + 1,
        endColumn: Math.max(2, line.length + 1),
      });
    }
    if (/\bexcept\s*:\s*$/.test(line)) {
      markers.push({
        severity: monaco.MarkerSeverity.Warning,
        message: 'BEAST diagnostic: bare except hides failure evidence.',
        startLineNumber: index + 1,
        startColumn: 1,
        endLineNumber: index + 1,
        endColumn: Math.max(2, line.length + 1),
      });
    }
    if (/\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*['"][^'"]{8,}/i.test(line)) {
      markers.push({
        severity: monaco.MarkerSeverity.Error,
        message: 'BEAST diagnostic: possible hard-coded secret; route through provider secret setup instead.',
        startLineNumber: index + 1,
        startColumn: 1,
        endLineNumber: index + 1,
        endColumn: Math.max(2, line.length + 1),
      });
    }
  });
  if (currentSourcePlanLifecycle?.stale_count > 0) {
    markers.push({
      severity: monaco.MarkerSeverity.Warning,
      message: 'BEAST stale-context warning: reload/rebase this SourcePlan before applying.',
      startLineNumber: 1,
      startColumn: 1,
      endLineNumber: 1,
      endColumn: 2,
    });
  }
  changedLineRanges(fileOriginals.get(currentFile) || originalText, value).forEach(line => {
    decorations.push({
      range: new monaco.Range(line, 1, line, 1),
      options: {
        isWholeLine: true,
        className: 'changed-line',
        glyphMarginClassName: 'changed-glyph',
        hoverMessage: { value: 'Changed staged buffer line. Compile through SourcePlan before writing.' },
      },
    });
  });
  monaco.editor.setModelMarkers(model, 'beast', markers);
  monacoEditor.__beastDecorations = monacoEditor.deltaDecorations(monacoEditor.__beastDecorations || [], decorations);
}

function closeEditorTab(path) {
  const target = path || currentFile;
  if (!target) return;
  if (dirtyFiles.has(target) && !window.confirm(`${target} has unsaved staged edits. Close the tab and discard the buffer?`)) return;
  dirtyFiles.delete(target);
  clearPersistedBuffer(target);
  fileModels.get(target)?.dispose();
  fileModels.delete(target);
  fileOriginals.delete(target);
  openFiles = openFiles.filter(item => item !== target);
  if (currentFile === target) {
    currentFile = openFiles[openFiles.length - 1] || '';
    if (currentFile) {
      const model = fileModels.get(currentFile);
      originalText = fileOriginals.get(currentFile) || '';
      if (model && monacoEditor) monacoEditor.setModel(model);
      $('editorText').value = model ? model.getValue() : '';
      $('activeFile').textContent = currentFile;
    } else {
      originalText = '';
      $('editorText').value = '';
      $('activeFile').textContent = 'No file selected';
      if (monacoEditor) monacoEditor.setModel(null);
    }
  }
  updateOpenTabs();
  renderFileExplorer();
  updateEditorMeta();
  diffCurrentEdit();
  updateStatusChips();
  renderSourcePlanChecklist();
  renderNextActionInspector();
  saveWorkspaceState();
}

function setDesktopPage(page) {
  const nextPage = desktopPages[page] ? page : 'mission';
  currentPage = nextPage;
  // legacy rail buttons (hidden but kept for compat)
  document.querySelectorAll('.rail-button').forEach(item => item.classList.toggle('active', item.dataset.view === nextPage));
  // new OPCB nav items
  document.querySelectorAll('.nav-item[data-desktop-page]').forEach(item => item.classList.toggle('active', item.dataset.desktopPage === nextPage));
  document.querySelectorAll('[data-page-panel]').forEach(item => item.classList.toggle('hidden', item.dataset.pagePanel !== nextPage));
  $('pageEyebrow').textContent = desktopPages[nextPage].label;
  // update cube zone face glow
  const shell = document.querySelector('.app-shell');
  if (shell) {
    shell.dataset.activeFace = desktopPages[nextPage].label;
    shell.dataset.desktopPage = nextPage;
  }
  const tab = desktopPages[nextPage].tab;
  const tabButton = document.querySelector(`[data-editor-tab="${tab}"]`);
  if (tabButton) activateEditorTab(tab);
  if (nextPage === 'evidence') searchEvidenceDrawer('query').catch(error => log(`Evidence refresh failed: ${error.message || error}`));
  if (nextPage === 'providers') refreshProviderSetup().catch(error => log(`Provider refresh failed: ${error.message || error}`));
  if (nextPage === 'tooling') refreshToolingSnapshot().catch(error => log(`Tooling refresh failed: ${error.message || error}`));
  if (nextPage === 'system') refreshSystemSnapshot().catch(error => log(`System refresh failed: ${error.message || error}`));
  if (nextPage === 'agents') renderAgentContextPack();
  if (nextPage === 'settings' && !ideActions.length) refreshActionManifest().catch(error => log(`Action refresh failed: ${error.message || error}`));
  updateStatusChips();
  renderNextActionInspector();
  saveWorkspaceState();
  log(`desktop page: ${page}`);
  // fire page-change event for beast-studio-integrations.js
  document.dispatchEvent(new CustomEvent('beast:page-change', { detail: { page: nextPage } }));
}

function activateEditorTab(tabName) {
  document.querySelectorAll('.tab').forEach(item => item.classList.toggle('active', item.dataset.editorTab === tabName));
  ['editorPane', 'diffPane', 'terminalPane'].forEach(id => $(id).classList.add('hidden'));
  const pane = $(`${tabName}Pane`);
  if (pane) pane.classList.remove('hidden');
}

const panelSplitterState = {
  dragging: false,
  splitId: '',
  startX: 0,
  workspaceWidth: 310,
  mainWidth: 520,
  governanceWidth: 360,
};

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function updateAppColumns(workspaceWidth, mainWidth, governanceWidth) {
  // no-op in BEAST Studio 3-column layout; splitters are hidden
  // sidebar and cube-zone are fixed; main is flexible
}

function onSplitterPointerDown(event) {
  if (!(event.target instanceof HTMLElement)) return;
  const splitter = event.target.closest('.splitter');
  if (!splitter) return;
  event.preventDefault();
  panelSplitterState.dragging = true;
  panelSplitterState.splitId = splitter.dataset.split || '';
  panelSplitterState.startX = event.touches ? event.touches[0].clientX : event.clientX;
  const cols = window.getComputedStyle(document.querySelector('.app-shell')).gridTemplateColumns.split(' ').map(token => parseFloat(token));
  panelSplitterState.workspaceWidth = cols[2];
  panelSplitterState.mainWidth = cols[4];
  panelSplitterState.governanceWidth = cols[6];
  document.body.style.userSelect = 'none';
}

function onSplitterPointerMove(event) {
  if (!panelSplitterState.dragging) return;
  event.preventDefault();
  const currentX = event.touches ? event.touches[0].clientX : event.clientX;
  const delta = currentX - panelSplitterState.startX;
  if (panelSplitterState.splitId === 'activity-workspace') {
    const nextWidth = clamp(panelSplitterState.workspaceWidth + delta, 220, 360);
    updateAppColumns(nextWidth, null, null);
  } else if (panelSplitterState.splitId === 'workspace-main') {
    const nextWorkspace = clamp(panelSplitterState.workspaceWidth + delta, 240, 360);
    const nextMain = clamp(panelSplitterState.mainWidth - delta, 540, 1080);
    updateAppColumns(nextWorkspace, nextMain, null);
  } else if (panelSplitterState.splitId === 'main-governance') {
    const nextMain = clamp(panelSplitterState.mainWidth + delta, 540, 1080);
    const nextGovernance = clamp(panelSplitterState.governanceWidth - delta, 280, 460);
    updateAppColumns(null, nextMain, nextGovernance);
  }
}

function onSplitterPointerUp() {
  if (!panelSplitterState.dragging) return;
  panelSplitterState.dragging = false;
  document.body.style.userSelect = '';
}

function initSplitters() {
  document.querySelectorAll('.splitter').forEach(splitter => {
    splitter.addEventListener('mousedown', onSplitterPointerDown);
    splitter.addEventListener('touchstart', onSplitterPointerDown, { passive: false });
  });
  window.addEventListener('mousemove', onSplitterPointerMove);
  window.addEventListener('touchmove', onSplitterPointerMove, { passive: false });
  window.addEventListener('mouseup', onSplitterPointerUp);
  window.addEventListener('touchend', onSplitterPointerUp);
}

function setStreamState(text, state) {
  const node = $('eventStreamState');
  if (node) { node.textContent = text; node.className = `stream-state ${state || 'warn'}`; }
  const cubeNode = $('cubeZoneLive');
  if (cubeNode) { cubeNode.textContent = state === 'ready' ? '● Live' : '○ ' + text; cubeNode.style.color = state === 'ready' ? 'var(--teal)' : state === 'bad' ? 'var(--danger)' : 'var(--gold)'; }
}

function shouldRefresh(lastAt, ttlMs, force = false) {
  if (force) return true;
  return (Date.now() - Number(lastAt || 0)) > ttlMs;
}

async function refreshStatus() {
  const status = await window.beastDesktop.status();
  lastGatewayStatus = status;
  desktopBuildInfo = {
    version: status.desktopVersion || desktopBuildInfo.version,
    rendererPath: status.rendererPath || desktopBuildInfo.rendererPath,
  };
  renderDesktopBuildId();
  gatewayUrl = status.gatewayUrl || gatewayUrl;
  desktopLocalMode = Boolean(status.health?.local_mode);
  workspaceRoot = workspaceRoot || status.repoRoot;
  loadWorkspaceState();
  $('workspacePath').textContent = workspaceRoot;
  const pill = $('gatewayState');
  if (desktopLocalMode) {
    pill.textContent = 'local IDE mode';
    pill.className = 'status-pill warn';
  } else if (status.health.ok && status.health.capabilities?.ok !== false) {
    pill.textContent = 'gateway online';
    pill.className = 'status-pill';
  } else {
    const logText = (status.gatewayLog || []).join('\n');
    const starting = status.health.starting || status.health.tcp_listening || /starting gateway|trying next port|Initializing/.test(logText);
    pill.textContent = status.health.ok
      ? 'gateway incompatible'
      : status.health.tcp_listening
        ? 'gateway warming'
        : starting ? 'gateway starting' : 'gateway offline';
    pill.className = starting ? 'status-pill warn' : 'status-pill bad';
  }
  if (!lastTerminalExecution) {
    $('terminalLog').textContent = (status.gatewayLog || []).join('\n') || 'BEAST desktop terminal log will appear here.';
  }
  renderGatewayDoctor(status);
  updateStatusChips();
  renderNextActionInspector();
}

function renderDesktopBuildId() {
  const version = desktopBuildInfo.version || 'unknown build';
  const title = desktopBuildInfo.rendererPath || version;
  const brandNode = $('desktopBrandBuildId');
  if (brandNode) {
    brandNode.textContent = version;
    brandNode.title = title;
  }
  const footerNode = $('desktopBuildId');
  if (footerNode) {
    footerNode.textContent = `BEAST Desktop ${version}`;
    footerNode.title = title;
  }
}

window.beastDesktop.onDesktopVersion?.(info => {
  desktopBuildInfo = {
    version: info?.version || desktopBuildInfo.version,
    rendererPath: info?.rendererPath || desktopBuildInfo.rendererPath,
  };
  renderDesktopBuildId();
});

function renderGatewayDoctor(status) {
  const health = status.health || {};
  const capabilities = health.capabilities || {};
  const checks = capabilities.checks || {};
  const ok = Boolean(health.ok && capabilities.ok !== false);
  const state = health.local_mode ? 'local IDE mode' : ok ? 'online' : health.tcp_listening ? 'warming' : health.ok ? 'incompatible' : 'offline';
  const lines = [
    `${state} · ${status.gatewayUrl || gatewayUrl}`,
    explainGatewayState(status),
    `repo: ${status.repoRoot || workspaceRoot || 'unknown'}`,
    `pid: ${status.processPid || 'not owned by desktop'}`,
    `command: ${status.lastGatewayCommand || 'not started by desktop'}`,
    `tcp: ${health.tcp_listening ? 'listening' : 'not listening'}`,
    `root: ${health.ok ? 'ok' : health.error || 'not responding'}`,
    `capability mode: ${capabilities.mode || 'unknown'}`,
    `ide snapshot: ${checks.ide_snapshot?.ok ? 'ok' : checks.ide_snapshot?.error || 'pending'}`,
    `ide events: ${checks.ide_events?.ok ? 'ok' : checks.ide_events?.error || 'pending'}`,
    `mission timeline: ${checks.mission_timeline?.ok ? 'ok' : checks.mission_timeline?.error || 'pending'}`,
    `workspace files: ${checks.workspace_files?.ok ? 'ok' : checks.workspace_files?.error || 'pending'}`,
  ];
  $('gatewayDoctor').textContent = lines.join('\n');
  $('gatewayDoctor').className = ok || health.local_mode ? 'status-box ready' : health.ok ? 'status-box warn' : 'status-box bad';
  $('gatewayDoctorRaw').textContent = JSON.stringify({
    gatewayUrl: status.gatewayUrl,
    repoRoot: status.repoRoot,
    processPid: status.processPid,
    health,
    lastGatewayCommand: status.lastGatewayCommand,
    logTail: (status.gatewayLog || []).slice(-40),
  }, null, 2);
}

function explainGatewayState(status = lastGatewayStatus || {}) {
  const health = status.health || {};
  if (health.local_mode) return 'Local IDE Mode: edit, browse, tab, and diff locally. Restart the gateway for SourcePlan apply, providers, worktrees, and evidence routes.';
  if (health.ok && health.capabilities?.ok !== false) return 'Gateway ready: live BEAST routes are available for SourcePlan, Evidence Bus, agents, providers, and worktrees.';
  if (health.tcp_listening || health.starting) return 'Gateway warming: keep editing locally while route readiness checks complete.';
  if (health.ok && health.capabilities?.ok === false) return 'Gateway answered, but IDE routes are stale. Restart to attach to the current BEAST build.';
  if (health.error) return `Gateway unavailable: ${health.error}. Use Restart Gateway, or continue in Local IDE Mode.`;
  return 'Gateway status unknown. BEAST will prefer local desktop fallbacks until health is confirmed.';
}

function chip(label, state = 'muted') {
  return `<span class="state-chip ${escapeHtml(state)}">${escapeHtml(label)}</span>`;
}

function updateStatusChips() {
  const node = $('statusChipBar');
  if (!node) return;
  const health = lastGatewayStatus?.health || {};
  const crystalCredits = window.beastStudio ? (window.beastStudio.state?.crystalization?.active_credits ?? null) : null;
  const chips = [
    desktopLocalMode ? chip('local', 'warn') : health.ok ? chip('gateway', 'ready') : chip('gateway', health.tcp_listening || health.starting ? 'warn' : 'bad'),
    currentFile ? chip(currentFile.split('/').pop(), 'ready') : chip('no file', 'muted'),
    currentFile && dirtyFiles.has(currentFile) ? chip('dirty', 'warn') : chip('clean', 'muted'),
    currentSourcePlan ? chip('sourceplan', 'ready') : chip('no plan', 'muted'),
    currentSourcePlanLifecycle?.can_apply ? chip('verified', 'ready') : currentSourcePlan ? chip('needs verify', 'warn') : chip('verify pending', 'muted'),
    currentSourcePlanLifecycle?.action_contract?.approval_required ? chip('needs approval', 'warn') : chip('approval ok', currentSourcePlan ? 'ready' : 'muted'),
    (currentSourcePlanLifecycle?.evidence?.match_count || 0) > 0 ? chip('evidence ready', 'ready') : chip('evidence pending', 'muted'),
    crystalCredits != null ? chip(`${crystalCredits} crystals`, crystalCredits > 0 ? 'ready' : 'muted') : null,
  ].filter(Boolean);
  node.innerHTML = chips.join('');
}

function sourcePlanChecklistState() {
  const lifecycle = currentSourcePlanLifecycle || {};
  const contract = lifecycle.action_contract || {};
  const evidenceCount = lifecycle.evidence?.match_count || 0;
  const hasPlan = Boolean(currentSourcePlan);
  const verified = Boolean(lifecycle.can_apply || (lifecycle.verification && lifecycle.verification.ok));
  return [
    { label: 'Draft', ok: hasPlan, warn: currentFile && dirtyFiles.has(currentFile), detail: hasPlan ? 'SourcePlan exists' : dirtyFiles.has(currentFile) ? 'Draft from staged edit' : 'Edit or select code' },
    { label: 'Score', ok: Boolean(lifecycle.scorecard || lifecycle.action_contract), warn: hasPlan && !lifecycle.scorecard, detail: lifecycle.risk ? `risk ${lifecycle.risk}` : 'waiting for lifecycle' },
    { label: 'Verify', ok: verified, warn: hasPlan && !verified, detail: verified ? 'checks passed' : 'run verifier' },
    { label: 'Approve', ok: hasPlan && !contract.approval_required, warn: Boolean(contract.approval_required), detail: contract.approval_required ? 'operator approval needed' : hasPlan ? 'approval clear' : 'not ready' },
    { label: 'Apply', ok: Boolean(lifecycle.can_apply), warn: hasPlan && !lifecycle.can_apply, detail: lifecycle.can_apply ? 'ready through SourcePlan' : 'blocked until verify/approval' },
    { label: 'Evidence', ok: evidenceCount > 0, warn: hasPlan && evidenceCount === 0, detail: evidenceCount ? `${evidenceCount} related receipts` : 'attach receipts' },
    { label: 'Rollback', ok: Boolean(contract.rollback_required || hasPlan), warn: false, detail: hasPlan ? 'snapshot required' : 'not planned' },
  ];
}

function renderSourcePlanChecklist() {
  const node = $('sourcePlanChecklist');
  if (!node) return;
  node.innerHTML = sourcePlanChecklistState().map(item => {
    const state = item.ok ? 'ready' : item.warn ? 'warn' : 'muted';
    return `<div class="check-step ${state}">
      <span>${escapeHtml(item.label)}</span>
      <small>${escapeHtml(item.detail)}</small>
    </div>`;
  }).join('');
}

function nextActionForState() {
  if (!workspaceRoot) return { title: 'Choose a workspace', detail: 'Pick the folder BEAST should operate on. Local file browsing starts there.', action: 'Choose Folder', page: 'mission' };
  if (desktopLocalMode || !(lastGatewayStatus?.health?.ok)) return { title: 'Gateway is not ready', detail: explainGatewayState(lastGatewayStatus), action: 'Open Gateway Doctor', page: 'doctor' };
  if (!currentFile) return { title: 'Select a file', detail: 'Open a file from the explorer. The editor, related context, and SourcePlan controls will bind to it.', action: 'Use file explorer', page: 'mission' };
  if (dirtyFiles.has(currentFile) && !currentSourcePlan) return { title: 'Draft a SourcePlan', detail: 'You have staged editor changes. Compile them into a governed SourcePlan before writing anything.', action: 'SourcePlan Draft', page: 'source', command: 'sourceplan.draft_editor' };
  if (currentSourcePlan && !currentSourcePlanLifecycle) return { title: 'Score the SourcePlan', detail: 'Refresh lifecycle to see risk, operation ledger, policy, evidence, and verify readiness.', action: 'Refresh Lifecycle', page: 'source', command: 'sourceplan.lifecycle' };
  if (currentSourcePlan && !currentSourcePlanLifecycle?.can_apply) return { title: 'Verify and collect evidence', detail: 'Run verification, inspect stale operations, and attach receipts before apply.', action: 'Verify SourcePlan', page: 'source', command: 'sourceplan.verify' };
  if (currentSourcePlanLifecycle?.can_apply) return { title: 'Apply through SourcePlan', detail: 'The plan is ready. Apply only through BEAST so rollback and evidence close correctly.', action: 'Apply SourcePlan', page: 'source', command: 'sourceplan.apply' };
  if (currentPage === 'agents' && !currentAgentSession) return { title: 'Create an agent session', detail: 'Sessions keep mode, budget, tools, files, evidence, provider, and transcript together.', action: 'Create Agent', page: 'agents', command: 'agents.create' };
  if (currentPage === 'providers' && lastProviderError) return { title: 'Provider needs attention', detail: lastProviderError, action: 'Refresh Provider Setup', page: 'providers', command: 'providers.refresh' };
  if (currentPage === 'tooling' && !lastToolingSnapshot) return { title: 'Refresh tooling plane', detail: 'Load MCP, plugin, extension, syntax, lint, and environment readiness before invoking external tools.', action: 'Refresh Tooling', page: 'tooling', command: 'tooling.refresh' };
  if (currentPage === 'worktrees' && !currentWorktreeTask) return { title: 'Create or select a worktree', detail: 'Worktree missions isolate risky edits. Select one to verify, diff, promote, or close.', action: 'Create Worktree', page: 'worktrees', command: 'worktrees.create' };
  return { title: 'Continue the mission', detail: 'Use the command palette for governed actions, or select code/files to narrow the next step.', action: 'Open Commands', page: currentPage || 'mission' };
}

function renderNextActionInspector() {
  const node = $('nextActionInspector');
  if (!node) return;
  const next = nextActionForState();
  const button = next.command
    ? `<button class="ghost-button full" data-ide-action="${escapeHtml(next.command)}">${escapeHtml(next.action)}</button>`
    : `<button class="ghost-button full" data-next-page="${escapeHtml(next.page || 'mission')}">${escapeHtml(next.action)}</button>`;
  node.innerHTML = [
    `<b>${escapeHtml(next.title)}</b>`,
    `<p>${escapeHtml(next.detail)}</p>`,
    button,
  ].join('');
  node.className = `status-box ${desktopLocalMode || next.title.includes('not ready') ? 'warn' : 'ready'}`;
}

async function copyDoctorReport() {
  const text = $('gatewayDoctorRaw').textContent || $('gatewayDoctor').textContent || '';
  try {
    await navigator.clipboard.writeText(text);
    log('Gateway Doctor report copied.');
  } catch (error) {
    log(`Gateway Doctor copy failed: ${error.message || error}`);
  }
}

async function refreshSnapshot(options = {}) {
  const force = Boolean(options.force);
  if (snapshotRefreshPromise) return snapshotRefreshPromise;
  if (!force && !shouldRefresh(lastSnapshotRefreshAt, SNAPSHOT_COOLDOWN_MS)) return currentSnapshot;

  snapshotRefreshPromise = (async () => {
  await refreshStatus();
  loadTerminalState();
  const params = new URLSearchParams();
  if (workspaceRoot) params.set('root_path', workspaceRoot);
  if (currentFile) params.set('active_file', currentFile);
  params.set('objective', currentFile ? `Work on ${currentFile}` : 'BEAST desktop mission');
  try {
    const path = `/edgek/ide/snapshot?${params.toString()}`;
    currentSnapshot = await withGatewayWarmupRetry('IDE snapshot', timeoutMs => getJson(path, timeoutMs), 30000);
  } catch (error) {
    currentSnapshot = {
      phase: 'desktop_route_fallback',
      policy: { mode_route: { decision: 'gateway route missing' }, architecture_decisions: { decision_count: 0 } },
      code_cortex: {},
      evidence_bus: {},
      agent_sessions: { sessions: [] },
      worktrees: { tasks: [] },
    };
    $('policyGate').textContent = 'route missing';
    $('policyDetail').textContent = `${error.message || error}. Files still load from workspace fallback.`;
    log(`IDE snapshot unavailable: ${error.message || error}`);
  }
  $('missionTitle').textContent = currentFile || 'BEAST Mission Workspace';
  const policy = currentSnapshot.policy || {};
  const mode = policy.mode_route || {};
  $('policyGate').textContent = mode.decision || mode.mode || 'governed';
  $('policyDetail').textContent = `ADR ${policy.architecture_decisions?.decision_count || 0} decisions · phase ${currentSnapshot.phase}`;
  // mirror to cube zone
  if ($('cubePolicyGate')) $('cubePolicyGate').textContent = mode.decision || mode.mode || 'governed';
  if ($('cubePolicyDetail')) $('cubePolicyDetail').textContent = `ADR ${policy.architecture_decisions?.decision_count || 0} decisions`;
  if ($('cubeGatewayBadge')) { $('cubeGatewayBadge').textContent = lastGatewayStatus?.health?.ok ? 'online' : 'offline'; $('cubeGatewayBadge').className = `badge ${lastGatewayStatus?.health?.ok ? 'ready' : 'bad'}`; }
  if ($('cubeGatewayDetail')) $('cubeGatewayDetail').textContent = `${gatewayUrl}`;
  renderActiveMissionCard();
  const cortex = currentSnapshot.code_cortex || {};
  const files = cortex.files || cortex.related_files || cortex.matched_files || [];
  renderList($('codeCortex'), files.slice(0, 8), item => `<div class="mini-card">${escapeHtml(item.path || item.file || String(item))}</div>`);
  const evidence = currentSnapshot.evidence_bus || {};
  renderEvidenceReceipts(evidence.recent || evidence.receipts || []);
  const sessions = currentSnapshot.agent_sessions?.sessions || [];
  renderAgentSessions(sessions);
  const worktrees = currentSnapshot.worktrees?.tasks || currentSnapshot.worktrees?.items || [];
  renderWorktreeMissions(worktrees);
  await refreshMissionRoute();
  if (shouldRefresh(lastManifestRefreshAt, MANIFEST_REFRESH_TTL_MS, force)) await refreshActionManifest();
  if (shouldRefresh(lastFilesRefreshAt, FILES_REFRESH_TTL_MS, force)) await refreshFiles();
  if (shouldRefresh(lastTimelineRefreshAt, TIMELINE_REFRESH_TTL_MS, force)) await refreshMissionTimeline();
  startIdeEventStream();
  updateStatusChips();
  renderSourcePlanChecklist();
  renderNextActionInspector();
  lastSnapshotRefreshAt = Date.now();
  // fire integration event for beast-studio-integrations.js
  document.dispatchEvent(new CustomEvent('beast:snapshot-complete', { detail: { snapshot: currentSnapshot } }));
  return currentSnapshot;
  })();

  try {
    return await snapshotRefreshPromise;
  } finally {
    snapshotRefreshPromise = null;
  }
}

function renderActiveMissionCard() {
  const node = $('activeMissionCard');
  if (!node) return;
  const evidence = currentSnapshot?.evidence_bus || {};
  const sessions = currentSnapshot?.agent_sessions?.sessions || [];
  const worktrees = currentSnapshot?.worktrees?.tasks || currentSnapshot?.worktrees?.items || [];
  const title = currentFile || 'BEAST desktop mission';
  const session = currentAgentSession?.session_id ? `session ${currentAgentSession.session_id}` : 'no active session';
  const worktree = currentWorktreeTask?.task_id ? `worktree ${currentWorktreeTask.task_id}` : 'no worktree selected';
  node.innerHTML = [
    `<b>${escapeHtml(title)}</b>`,
    `<span>${escapeHtml(currentSnapshot?.phase || 'local')} · ${escapeHtml($('policyGate').textContent || 'governed')}</span>`,
    `<span>${escapeHtml(session)} · ${escapeHtml(worktree)}</span>`,
    `<small>${sessions.length} session(s) · ${worktrees.length} worktree(s) · ${(evidence.recent || evidence.receipts || []).length} evidence item(s)</small>`,
  ].join('');
}

async function refreshActionManifest() {
  const params = new URLSearchParams();
  if (workspaceRoot) params.set('root_path', workspaceRoot);
  const search = $('commandPaletteSearch')?.value?.trim() || '';
  if (search) params.set('query', search);
  const canUseGateway = !desktopLocalMode && lastGatewayStatus?.health?.ok;
  if (!canUseGateway) {
    ideActions = desktopLocalActionManifest();
    renderCommandPalette();
    lastManifestRefreshAt = Date.now();
    log('Skipping gateway action manifest because gateway is not ready; using local palette.');
    return;
  }
  try {
    const path = `/edgek/ide/actions/manifest?${params.toString()}`;
    const payload = await withGatewayWarmupRetry('Action manifest', timeoutMs => getJson(path, timeoutMs), 25000);
    const merged = new Map();
    for (const action of [...(payload.actions || []), ...desktopLocalActionManifest()]) {
      if (action?.id && !merged.has(action.id)) merged.set(action.id, action);
    }
    ideActions = Array.from(merged.values());
    renderCommandPalette();
    lastManifestRefreshAt = Date.now();
  } catch (error) {
    ideActions = desktopLocalActionManifest();
    renderCommandPalette();
    lastManifestRefreshAt = Date.now();
    log(`Action manifest unavailable; using local palette: ${error.message || error}`);
  }
}

function desktopLocalActionManifest() {
  return [
    { id: 'mission.refresh_snapshot', label: 'Refresh Mission Snapshot', page: 'mission', client_handler: 'refreshSnapshot', risk: 'low', description: 'Reload the local desktop snapshot.', local_fallback: true },
    { id: 'editor.save_sourceplan', label: 'Save Via SourcePlan', page: 'source', client_handler: 'saveViaSourcePlan', risk: 'high', description: 'Save staged editor edits through SourcePlan governance.', sourceplan_required: true, local_fallback: false },
    { id: 'editor.revert_buffer', label: 'Revert Editor Buffer', page: 'source', client_handler: 'revertEditorBuffer', risk: 'medium', description: 'Discard staged editor changes.', local_fallback: true },
    { id: 'editor.reload_file', label: 'Reload Active File', page: 'source', client_handler: 'reloadActiveFileFromDisk', risk: 'medium', description: 'Reload the active file from disk.', local_fallback: true },
    { id: 'sourceplan.draft_editor', label: 'Draft SourcePlan From Editor', page: 'source', client_handler: 'sourcePlanDraft', risk: 'medium', description: 'Build a SourcePlan draft from staged editor changes.', sourceplan_required: true, local_fallback: true },
    { id: 'sourceplan.draft_selection', label: 'Draft SourcePlan From Selection', page: 'source', client_handler: 'sourcePlanSelectionDraft', risk: 'medium', description: 'Build a SourcePlan draft from the current editor selection.', sourceplan_required: true, local_fallback: true },
    { id: 'code.symbol_search', label: 'Search Workspace Symbols', page: 'source', client_handler: 'runSymbolSearch', risk: 'low', description: 'Find workspace symbols and open symbol-sized ranges.', local_fallback: false },
    { id: 'code.intel', label: 'Refresh Code Intelligence', page: 'source', client_handler: 'refreshCodeIntelligence', risk: 'low', description: 'Load diagnostics, symbols, related tests/routes, and stale-context hints.', local_fallback: false },
    { id: 'agents.create', label: 'Create Agent Session', page: 'agents', client_handler: 'createAgentSession', risk: 'low', description: 'Create a persistent agent session.', provider_required: true, local_fallback: true },
    { id: 'worktrees.create', label: 'Create Mission Worktree', page: 'worktrees', client_handler: 'createWorktreeMission', risk: 'medium', description: 'Create an isolated mission worktree.', worktree_recommended: true, local_fallback: false },
    { id: 'evidence.search', label: 'Search Evidence Bus', page: 'evidence', client_handler: 'searchEvidenceDrawer', risk: 'low', description: 'Query evidence receipts.', local_fallback: true },
    { id: 'terminal.classify', label: 'Classify Terminal Command', page: 'terminal', client_handler: 'classifyTerminalCommand', risk: 'low', description: 'Classify a terminal command before execution.', local_fallback: false },
    { id: 'tooling.refresh', label: 'Refresh Tooling Plane', page: 'tooling', client_handler: 'refreshToolingSnapshot', risk: 'low', description: 'Check syntax, lint scripts, MCP, plugins, extensions, and environments.', local_fallback: true },
    { id: 'tooling.syntax', label: 'Syntax Check Active File', page: 'tooling', client_handler: 'runSyntaxToolingCheck', risk: 'low', description: 'Run the local syntax checker for the active file.', local_fallback: true },
    { id: 'tooling.lint', label: 'Show Lint Contract', page: 'tooling', client_handler: 'showLintToolingContract', risk: 'low', description: 'Show available lint scripts and governed terminal guidance.', local_fallback: true },
    { id: 'tooling.mcp', label: 'Inspect MCP', page: 'tooling', client_handler: 'focusMcpTooling', risk: 'low', description: 'Inspect MCP routes, configs, approvals, and schema surfaces.', local_fallback: true },
    { id: 'tooling.plugins', label: 'Inspect Plugins And Extensions', page: 'tooling', client_handler: 'focusPluginTooling', risk: 'low', description: 'Inspect plugin, extension, and installable shell surfaces.', local_fallback: true },
    { id: 'tooling.mcp_ops', label: 'Refresh MCP Operations', page: 'tooling', client_handler: 'refreshMcpOps', risk: 'low', description: 'Load MCP state, servers, schema pins, approvals, audit, and executions.', local_fallback: false },
    { id: 'tooling.plugin_ops', label: 'Refresh Plugin Operations', page: 'tooling', client_handler: 'refreshPluginOps', risk: 'low', description: 'Load plugin inventory and validation/install endpoints.', local_fallback: false },
    { id: 'tooling.grade_benchmark_packet', label: 'Run Benchmark Grading Daemon', page: 'tooling', client_handler: 'runBenchmarkGradingDaemon', risk: 'low', description: 'Trigger the full benchmark grading daemon and load provisional plus structural verdicts.', local_fallback: false },
    { id: 'tooling.environment', label: 'Inspect Environment', page: 'tooling', client_handler: 'focusEnvironmentTooling', risk: 'low', description: 'Inspect Python, Node, npm, git, and local package scripts.', local_fallback: true },
    { id: 'doctor.copy_report', label: 'Copy Doctor Report', page: 'doctor', client_handler: 'copyDoctorReport', risk: 'low', description: 'Copy the current gateway diagnostics.', local_fallback: true },
    { id: 'settings.release_readiness', label: 'Check IDE Readiness', page: 'settings', client_handler: 'checkReleaseReadiness', risk: 'low', description: 'Run desktop readiness checks.', local_fallback: true },
  ];
}

function renderCommandPalette() {
  const inline = $('commandPalette');
  const modal = $('commandPaletteModal');
  const activeSearch = document.activeElement === $('commandPaletteModalSearch')
    ? $('commandPaletteModalSearch')?.value
    : $('commandPaletteSearch')?.value || $('commandPaletteModalSearch')?.value || '';
  const search = String(activeSearch || '').trim().toLowerCase();
  const filteredRows = ideActions.filter(action => {
    if (!search) return true;
    return [action.id, action.label, action.description, action.page, ...(action.tags || [])]
      .join(' ')
      .toLowerCase()
      .includes(search);
  });
  const recentRows = !search
    ? commandPaletteRecents
      .map(id => ideActions.find(action => action.id === id))
      .filter(Boolean)
      .slice(0, 8)
    : [];
  const rows = [...recentRows, ...filteredRows.filter(action => !recentRows.some(recent => recent.id === action.id))].slice(0, 40);
  const html = rows.length ? rows.map(action => {
    const flags = [
      action.risk || 'low',
      action.sourceplan_required ? 'SourcePlan' : '',
      action.approval_required ? 'approval' : '',
      action.provider_required ? 'provider' : '',
      action.worktree_recommended ? 'worktree' : '',
    ].filter(Boolean).join(' · ');
    return `<button class="mini-card full command-card" data-ide-action="${escapeHtml(action.id)}">
      <strong>${escapeHtml(action.label)}</strong>
      <span>${escapeHtml(action.page || 'ide')} · ${escapeHtml(flags)}</span>
      <small>${escapeHtml(action.description || '')}</small>
    </button>`;
  }).join('') : emptyCard('No governed actions match this search.', 'Try sourceplan, verify, worktree, provider, terminal, or evidence.');
  if (inline) inline.innerHTML = html;
  if (modal) modal.innerHTML = html;
}

function openCommandPaletteModal() {
  const overlay = $('commandPaletteOverlay');
  overlay.classList.remove('hidden');
  overlay.setAttribute('aria-hidden', 'false');
  const search = $('commandPaletteModalSearch');
  search.value = $('commandPaletteSearch')?.value || '';
  renderCommandPalette();
  search.focus();
  search.select();
  if (!ideActions.length) refreshActionManifest().catch(error => log(`Action refresh failed: ${error.message || error}`));
}

function closeCommandPaletteModal() {
  const overlay = $('commandPaletteOverlay');
  overlay.classList.add('hidden');
  overlay.setAttribute('aria-hidden', 'true');
}

/*
 * Keep the old inline settings palette useful, but make Ctrl/Cmd+K a proper
 * modal surface so the user does not need to leave their current page.
 */
function syncCommandPaletteSearch(fromModal = false) {
  const source = fromModal ? $('commandPaletteModalSearch') : $('commandPaletteSearch');
  const target = fromModal ? $('commandPaletteSearch') : $('commandPaletteModalSearch');
  if (source && target) target.value = source.value;
  renderCommandPalette();
}

async function planIdeAction(action) {
  if (!action || desktopLocalMode) return null;
  try {
    return await postJson('/edgek/ide/actions/plan', { root_path: workspaceRoot, action_id: action.id });
  } catch (error) {
    if (action.local_fallback) {
      log(`Action plan unavailable for ${action.id}; using local desktop handler.`);
    } else {
      log(`Action plan unavailable for ${action.id}: ${error.message || error}`);
    }
    return null;
  }
}

async function runIdeAction(actionId) {
  const action = ideActions.find(item => item.id === actionId) || desktopLocalActionManifest().find(item => item.id === actionId);
  if (!action) {
    log(`Unknown IDE action: ${actionId}`);
    return;
  }
  rememberIdeAction(action.id);
  if (action.page) setDesktopPage(action.page);
  const plan = await planIdeAction(action);
  if (plan?.evidence_receipt?.receipt_id) log(`action plan evidence: ${plan.evidence_receipt.receipt_id}`);
  const handlers = {
    refreshSnapshot,
    refreshMissionRoute,
    saveViaSourcePlan,
    revertEditorBuffer,
    reloadActiveFileFromDisk,
    runSymbolSearch,
    refreshCodeIntelligence,
    sourcePlanDraft,
    sourcePlanSelectionDraft,
    refreshSourcePlanLifecycle,
    verifySourcePlan,
    applySourcePlan,
    exportMissionRunbook,
    verifyMissionRunbook,
    createHandoffPackage,
    proposeLearning,
    createAgentSession,
    sendAgentPrompt,
    agentOutputToSourcePlan,
    createWorktreeMission,
    testWorktreeMission,
    draftWorktreeSourcePlan,
    closeWorktreeMission,
    refreshProviderSetup,
    smokeNvidiaProvider,
    copyDoctorReport,
    checkReleaseReadiness,
    refreshToolingSnapshot,
    runSyntaxToolingCheck,
    showLintToolingContract,
    focusMcpTooling,
    focusPluginTooling,
    refreshMcpOps,
    refreshPluginOps,
    runBenchmarkGradingDaemon,
    focusEnvironmentTooling,
    refreshSystemSnapshot,
    refreshSystemPorts,
    refreshSystemProcesses,
    refreshSystemEnvironment,
    refreshSystemPackages,
    refreshSystemExtensions,
    refreshSystemCatalog,
    killSystemProcess: () => killSystemProcess(),
    freeSystemPort: () => freeSystemPort(),
    classifyTerminalCommand,
    executeTerminalCommand,
    restartGateway: async () => { await window.beastDesktop.restartGateway(); await refreshSnapshot(); },
    searchEvidenceDrawer: () => searchEvidenceDrawer('query'),
    chooseReceiptsForAction: () => chooseReceiptsForAction('command_palette'),
  };
  const handler = handlers[action.client_handler];
  if (!handler) {
    log(`No desktop handler is wired for ${action.label || action.id}`);
    return;
  }
  log(`IDE action: ${action.label || action.id}`);
  await handler();
}

function rememberIdeAction(actionId) {
  if (!actionId) return;
  commandPaletteRecents = [actionId, ...commandPaletteRecents.filter(item => item !== actionId)].slice(0, 20);
  saveWorkspaceState();
}

function focusCommandPalette() {
  openCommandPaletteModal();
}

async function refreshMissionRoute() {
  const params = new URLSearchParams();
  if (workspaceRoot) params.set('root_path', workspaceRoot);
  if (currentFile) params.set('active_file', currentFile);
  params.set('objective', currentSourcePlan?.objective || (currentFile ? `Work on ${currentFile}` : 'BEAST desktop mission'));
  try {
    const payload = await getJson(`/edgek/ide/mission-route?${params.toString()}`);
    renderList($('missionRouteStrip'), payload.route || [], item => [
      '<div class="mini-card">',
      `<b>${escapeHtml(item.step || '')}. ${escapeHtml(item.face || 'face')}</b> · ${escapeHtml(item.status || 'planned')}`,
      `<br><span class="muted">${escapeHtml((item.tools || []).join(', '))}</span>`,
      '</div>',
    ].join(''));
  } catch (error) {
    $('missionRouteStrip').innerHTML = `<div class="mini-card muted">${escapeHtml(error.message || error)}</div>`;
  }
}

async function refreshMissionTimeline() {
  const params = new URLSearchParams();
  if (workspaceRoot) params.set('root_path', workspaceRoot);
  if (currentFile) params.set('active_file', currentFile);
  params.set('objective', currentFile ? `Work on ${currentFile}` : 'BEAST desktop mission');
  params.set('limit', '40');
  try {
    const payload = await getJson(`/edgek/ide/mission-timeline?${params.toString()}`);
    renderList($('missionTimeline'), payload.entries || [], item => [
      '<div class="mini-card">',
      `<b>${escapeHtml(item.kind || 'event')}</b> · ${escapeHtml(item.status || 'recorded')}`,
      `<br><span>${escapeHtml(item.title || '')}</span>`,
      item.detail ? `<br><span class="muted">${escapeHtml(item.detail)}</span>` : '',
      '</div>',
    ].join(''), 'No mission events yet.', 'Open a file, create a SourcePlan, run an agent, or verify a worktree.');
    lastTimelineRefreshAt = Date.now();
  } catch (error) {
    $('missionTimeline').innerHTML = `<div class="mini-card muted">${escapeHtml(error.message || error)}</div>`;
  }
}

function renderAgentSessions(sessions) {
  const rows = sessions || [];
  renderList($('agentSessions'), rows.slice(0, 10), item => {
    const sessionId = escapeHtml(item.session_id || '');
    const active = currentAgentSession?.session_id === item.session_id ? ' active' : '';
    return [
      `<button class="file-item${active}" data-session-id="${sessionId}">`,
      `<b>${escapeHtml(item.status || 'session')}</b> · ${escapeHtml(item.mode || 'mode')}`,
      `<br><span class="muted">${escapeHtml(item.objective || item.session_id || '')}</span>`,
      '</button>',
    ].join('');
  }, 'No agent sessions yet.', 'Create a session when you want persistent mode, budget, tools, files, and evidence.');
  if (!currentAgentSession && rows.length) {
    currentAgentSession = rows[0];
    renderAgentDetail(currentAgentSession);
  } else if (currentAgentSession?.session_id) {
    const restored = rows.find(item => item.session_id === currentAgentSession.session_id);
    if (restored) {
      currentAgentSession = restored;
      renderAgentDetail(restored);
    }
  }
}

function renderAgentDetail(session) {
  if (!session) {
    $('agentDetail').textContent = 'Select or create an agent session.';
    $('agentDetail').className = 'status-box muted';
    $('agentTurnTimeline').innerHTML = '<div class="mini-card muted">No turns yet.</div>';
    resetAgentRunInspector();
    return;
  }
  const budget = session.budget || {};
  const outputs = Array.isArray(session.outputs) ? session.outputs : [];
  const evidence = Array.isArray(session.evidence) ? session.evidence : [];
  $('agentDetail').textContent = [
    `${session.status || 'session'} · ${session.mode || 'mode'} · ${session.provider || 'provider'}`,
    session.objective || session.session_id || '',
    `files: ${(session.files || []).join(', ') || 'none'}`,
    `tools: ${(session.tools || []).join(', ') || 'none'}`,
    `budget: ${budget.tokens || 0} tokens · ${budget.seconds || 0}s · $${budget.cost_usd || 0}`,
    `outputs: ${outputs.length} · evidence: ${evidence.length}`,
  ].join('\n');
  $('agentDetail').className = session.status === 'cancelled' ? 'status-box bad' : session.status === 'paused' ? 'status-box warn' : 'status-box ready';
  const latestOutput = outputs.length ? outputs[outputs.length - 1] : {};
  if (!$('agentOutputText').value) {
    $('agentOutputText').value = latestOutput.text || latestOutput.summary || latestOutput.content || '';
  }
  renderAgentTimeline(session);
}

function renderAgentTimeline(session) {
  const outputs = Array.isArray(session?.outputs) ? session.outputs : [];
  const rows = outputs.slice(-12).reverse();
  if (!rows.length) {
    $('agentTurnTimeline').innerHTML = '<div class="mini-card muted">No turns yet. Send a request to start the session timeline.</div>';
    return;
  }
  renderList($('agentTurnTimeline'), rows, item => {
    const kind = item.kind || item.type || 'turn';
    const text = item.text || item.summary || item.content || JSON.stringify(item).slice(0, 260);
    const provider = item.provider || selectedProvider;
    const model = item.model || selectedModel;
    return [
      '<div class="mini-card">',
      `<b>${escapeHtml(kind)}</b> · ${escapeHtml(provider)} · ${escapeHtml(model)}`,
      `<br><span class="muted">${escapeHtml(String(text).slice(0, 260))}</span>`,
      '</div>',
    ].join('');
  });
}

function renderTraceChips(targetId, rows, emptyText) {
  const target = $(targetId);
  const items = (rows || []).slice(-16);
  target.innerHTML = items.length
    ? items.map(item => {
      const text = typeof item === 'string' ? item : item.text || item.kind || JSON.stringify(item);
      const warn = /error|fallback|not ready|incomplete|recover/i.test(text) ? ' warn' : '';
      return `<span class="trace-chip${warn}" title="${escapeHtml(text)}">${escapeHtml(String(text).slice(0, 80))}</span>`;
    }).join('')
    : `<span class="trace-chip warn">${escapeHtml(emptyText)}</span>`;
}

function setAgentProviderHealth(text, state = 'muted') {
  const node = $('agentProviderHealth');
  node.textContent = text;
  node.className = `status-box ${state}`;
}

function resetAgentRunInspector() {
  agentRunStages = [];
  agentRunTools = [];
  renderTraceChips('agentStageTrace', agentRunStages, 'waiting');
  renderTraceChips('agentToolTrace', agentRunTools, 'no tools yet');
  setAgentProviderHealth(`${selectedProvider} · ${selectedModel}\nready to stream`, 'muted');
}

function providerRetryOptions(error = '') {
  const networkish = /name or service|econn|timeout|network|dns|getaddrinfo/i.test(String(error));
  return [
    networkish ? 'retry: run Provider Setup smoke check' : 'retry: run stream again',
    'retry: use Local smoke stream',
    'retry: reduce context files/selection',
    selectedProvider !== 'local_ollama' ? 'retry: switch provider to local_ollama' : 'retry: switch provider to nvidia_nim',
  ];
}

function renderProviderRetryOptions(error = '') {
  const lines = providerRetryOptions(error);
  setAgentProviderHealth([`provider failure: ${error || 'unknown'}`, ...lines].join('\n'), 'bad');
  pushAgentStage(`retry options: ${lines.join(' · ')}`);
}

function pushAgentStage(text) {
  if (!text) return;
  agentRunStages.push(String(text));
  renderTraceChips('agentStageTrace', agentRunStages, 'waiting');
}

function pushAgentTool(text) {
  if (!text) return;
  agentRunTools.push(String(text));
  renderTraceChips('agentToolTrace', agentRunTools, 'no tools yet');
}

function relatedContextFiles(limit = 6) {
  return Array.from($('relatedContext').querySelectorAll('[data-path]'))
    .map(node => node.dataset.path)
    .filter(Boolean)
    .filter(path => path !== currentFile)
    .slice(0, limit);
}

function uniqueFiles(files) {
  return Array.from(new Set((files || []).filter(Boolean)));
}

function bufferStorageKey(path = currentFile) {
  return `beast.desktop.buffer:${workspaceRoot || 'workspace'}:${path || ''}`;
}

function persistDirtyBuffer(path = currentFile) {
  if (!path || !fileModels.has(path)) return;
  const value = fileModels.get(path).getValue();
  const original = fileOriginals.get(path) ?? originalText;
  if (value === original) {
    localStorage.removeItem(bufferStorageKey(path));
    return;
  }
  localStorage.setItem(bufferStorageKey(path), JSON.stringify({
    path,
    workspaceRoot,
    value,
    saved_at: Date.now(),
    original_sha256_hint: String(original.length),
  }));
}

function clearPersistedBuffer(path = currentFile) {
  if (path) localStorage.removeItem(bufferStorageKey(path));
}

function restorePersistedBuffer(path, loadedText) {
  const raw = localStorage.getItem(bufferStorageKey(path));
  if (!raw) return loadedText;
  try {
    const payload = JSON.parse(raw);
    const value = String(payload.value || '');
    if (!value || value === loadedText) {
      localStorage.removeItem(bufferStorageKey(path));
      return loadedText;
    }
    if (window.confirm(`${path} has an unsaved BEAST Desktop buffer from ${new Date(payload.saved_at || Date.now()).toLocaleString()}. Restore it?`)) {
      dirtyFiles.add(path);
      log(`restored dirty buffer: ${path}`);
      return value;
    }
  } catch (error) {
    log(`dirty buffer restore failed: ${error.message || error}`);
  }
  return loadedText;
}

function selectionContextSummary(selection) {
  const lines = selection?.selected ? Math.max(1, selection.lineEnd - selection.line + 1) : 0;
  return {
    chars: selection?.selected?.length || 0,
    lines,
    range: `${currentFile || 'editor'}:${selection?.line || 1}-${selection?.lineEnd || 1}`,
  };
}

function buildAgentContextPack(promptText = '') {
  const includeActive = $('agentIncludeActiveFile')?.checked;
  const includeSelection = $('agentIncludeSelection')?.checked;
  const includeRelated = $('agentIncludeRelated')?.checked;
  const selection = editorSelectionInfo();
  const files = [];
  const notes = [];
  let enrichedPrompt = String(promptText || '').trim();

  if (includeActive && currentFile) {
    files.push(currentFile);
    notes.push(`active file: ${currentFile}`);
  }
  if (includeRelated) {
    const related = relatedContextFiles();
    files.push(...related);
    if (related.length) notes.push(`related files: ${related.join(', ')}`);
  }
  if (includeSelection && selection.selected) {
    const summary = selectionContextSummary(selection);
    if (selection.selected.length <= AGENT_INLINE_SELECTION_LIMIT) {
      enrichedPrompt = [
        enrichedPrompt,
        '',
        `Selected code from ${summary.range}:`,
        '```',
        selection.selected,
        '```',
      ].join('\n');
      notes.push(`selection inlined: ${summary.chars} chars · ${summary.lines} lines`);
    } else {
      enrichedPrompt = [
        enrichedPrompt,
        '',
        `Selected range: ${summary.range}`,
        `Selection size: ${summary.chars} chars across ${summary.lines} lines.`,
        'BEAST Desktop did not inline this selection because it exceeds the safe prompt context limit.',
        'Do not infer missing code from a preview or truncation marker. If a replacement is required, ask for a narrower selection or return a scoped SourcePlan/Action IR plan against explicit anchors.',
      ].join('\n');
      notes.push(`large selection referenced, not inlined: ${summary.chars} chars · ${summary.lines} lines`);
    }
  }

  const contextFiles = uniqueFiles(files).slice(0, 12);
  const selectedRange = includeSelection && selection.selected ? selectionContextSummary(selection).range : '';
  enrichedPrompt = [
    enrichedPrompt,
    '',
    'BEAST Desktop edit contract:',
    '- Prefer symbol-scoped patches over whole-file replacement.',
    '- Return BEAST Action IR JSON when you can make an exact edit; otherwise return a short plan and ask for the missing file/range/context.',
    '- Do not guess hidden code. Do not fabricate line ranges. Do not return prose inside a replacement block.',
    selectedRange ? `- Current selection anchor: ${selectedRange}` : '- No explicit selection anchor is available; ask for a narrower selection before proposing a mutation.',
  ].filter(Boolean).join('\n');
  const summary = [
    contextFiles.length ? `${contextFiles.length} file(s)` : 'no files',
    includeSelection && selection.selected ? `${selection.selected.length} selected chars` : 'no selected code',
    selectedProvider,
  ].join(' · ');
  return { prompt: enrichedPrompt || 'Continue this BEAST agent session.', files: contextFiles, notes, summary };
}

function renderAgentContextPack() {
  const pack = buildAgentContextPack($('agentPromptText')?.value || '');
  $('agentContextSummary').textContent = [
    pack.summary,
    ...(pack.notes.length ? pack.notes : ['Use checkboxes to include active file, selected code, or related files.']),
  ].join('\n');
  $('agentContextSummary').className = pack.files.length || pack.notes.length ? 'status-box ready' : 'status-box muted';
  return pack;
}

function appendLocalAgentTurn(kind, text, extra = {}) {
  if (!currentAgentSession) {
    currentAgentSession = {
      session_id: `local-${Date.now()}`,
      status: 'local',
      mode: 'architect',
      provider: selectedProvider,
      model: selectedModel,
      objective: text.slice(0, 120) || 'Local desktop agent session',
      files: currentFile ? [currentFile] : [],
      tools: ['desktop_local_queue'],
      budget: { tokens: 0, seconds: 0, cost_usd: 0 },
      outputs: [],
      evidence: [],
    };
  }
  currentAgentSession.outputs = Array.isArray(currentAgentSession.outputs) ? currentAgentSession.outputs : [];
  currentAgentSession.outputs.push({
    kind,
    text,
    provider: selectedProvider,
    model: selectedModel,
    created_at: new Date().toISOString(),
    ...extra,
  });
  renderAgentDetail(currentAgentSession);
  renderAgentSessions(currentSnapshot?.agent_sessions?.sessions || [currentAgentSession]);
}

function renderWorktreeMissions(worktrees) {
  const rows = worktrees || [];
  renderList($('worktreeMissions'), rows.slice(0, 10), item => {
    const taskId = escapeHtml(item.task_id || '');
    const active = currentWorktreeTask?.task_id === item.task_id ? ' active' : '';
    return [
      `<button class="file-item${active}" data-worktree-id="${taskId}">`,
      `<b>${escapeHtml(item.status || 'worktree')}</b> · ${escapeHtml(item.risk || 'risk')}`,
      `<br><span class="muted">${escapeHtml(item.objective || item.task_id || '')}</span>`,
      '</button>',
    ].join('');
  }, 'No worktree missions yet.', 'Create one for risky, multi-file, dependency, or promotion work.');
  if (!currentWorktreeTask && rows.length) {
    currentWorktreeTask = rows[0];
  } else if (currentWorktreeTask?.task_id) {
    const restored = rows.find(item => item.task_id === currentWorktreeTask.task_id);
    if (restored) currentWorktreeTask = restored;
  }
  saveWorkspaceState();
}

function startIdeEventStream() {
  if (ideEventStream || !workspaceRoot) return;
  if (desktopLocalMode) {
    setStreamState('local IDE mode', 'warn');
    return;
  }
  const params = new URLSearchParams();
  params.set('root_path', workspaceRoot);
  if (currentFile) params.set('active_file', currentFile);
  params.set('objective', currentFile ? `Work on ${currentFile}` : 'BEAST desktop mission');
  params.set('interval', '6');
  ideEventStream = new EventSource(`${gatewayUrl}/edgek/ide/events?${params.toString()}`);
  setStreamState('event stream live', 'ready');
  ideEventStream.addEventListener('agent_session', event => {
    const envelope = JSON.parse(event.data || '{}');
    const payload = envelope.payload || {};
    renderAgentSessions(payload.sessions || []);
    const selected = (payload.sessions || []).find(item => item.session_id === currentAgentSession?.session_id);
    if (selected) {
      currentAgentSession = selected;
      renderAgentDetail(selected);
    }
  });
  ideEventStream.addEventListener('evidence', event => {
    const envelope = JSON.parse(event.data || '{}');
    const payload = envelope.payload || {};
    renderList($('evidenceBus'), payload.recent || payload.receipts || [], item => `<div class="mini-card">${escapeHtml(item.receipt_id || item.artifact_type || item.source || 'evidence')}</div>`);
    if (shouldRefresh(lastTimelineRefreshAt, TIMELINE_REFRESH_TTL_MS)) refreshMissionTimeline();
  });
  ideEventStream.addEventListener('policy', event => {
    const envelope = JSON.parse(event.data || '{}');
    const policy = envelope.payload || {};
    const mode = policy.mode_route || {};
    $('policyGate').textContent = mode.decision || mode.mode || 'governed';
    $('policyDetail').textContent = `ADR ${policy.architecture_decisions?.decision_count || 0} decisions · live`;
  });
  ideEventStream.onerror = () => {
    setStreamState('event stream reconnecting', 'warn');
  };
  ideEventStream.onopen = () => {
    setStreamState('event stream live', 'ready');
  };
}

function resetIdeEventStream() {
  if (ideEventStream) ideEventStream.close();
  ideEventStream = null;
  setStreamState('event stream connecting', 'warn');
}

function resetAgentRunStream() {
  if (agentRunStream) agentRunStream.close();
  agentRunStream = null;
}

async function refreshFiles() {
  if ($('fileList')) $('fileList').innerHTML = `<div class="mini-card muted">Loading workspace files...</div>`;
  setExplorerStatus('Loading workspace files...', 'warn');
  const params = new URLSearchParams();
  if (workspaceRoot) params.set('root_path', workspaceRoot);
  params.set('limit', '2000');
  let payload = {};
  let rows = [];
  const canUseGateway = !desktopLocalMode && lastGatewayStatus?.health?.ok;
  if (canUseGateway) {
    try {
      const path = `/edgek/workspace/files?${params.toString()}`;
      payload = await withGatewayWarmupRetry('Workspace file list', timeoutMs => getJson(path, timeoutMs), 25000);
      rows = payload.files || payload.items || [];
    } catch (error) {
      log(`gateway file list unavailable: ${error.message || error}`);
    }
  } else {
    log('Skipping gateway file list because gateway is not ready; using local workspace fallback.');
  }
  if (!rows.length && window.beastDesktop.listFiles) {
    rows = await window.beastDesktop.listFiles(workspaceRoot, 2000);
    payload = { ...payload, fallback_used: true, fallback_source: 'desktop_local_files' };
  }
  explorerRows = rows;
  renderFileExplorer();
  lastFilesRefreshAt = Date.now();
  if (payload.fallback_used) log(`file list: using ${payload.fallback_source || 'local TUI-style candidates'} because graph/index routes are unavailable.`);
  await restoreWorkspaceTabs();
}

async function openFile(path, options = {}) {
  if (!path || path === '[object Object]') {
    log(`file open blocked: invalid path ${path || '(empty)'}`);
    return;
  }
  currentFile = path;
  currentSourcePlan = null;
  currentSourcePlanLifecycle = null;
  selectedSymbol = null;
  symbolOutlineRows = [];
  const params = new URLSearchParams();
  if (workspaceRoot) params.set('root_path', workspaceRoot);
  params.set('path', path);
  params.set('max_chars', '200000');
  let payload = {};
  try {
    payload = await getJson(`/edgek/workspace/file?${params.toString()}`);
  } catch (error) {
    log(`gateway file open unavailable: ${error.message || error}`);
    payload = window.beastDesktop.readFile
      ? await window.beastDesktop.readFile(workspaceRoot, path, 200000)
      : { ok: false, error: String(error.message || error) };
  }
  if (payload.ok === false) {
    log(`file open failed: ${payload.error || path}`);
    $('activeFile').textContent = `Failed: ${path}`;
    return;
  }
  originalText = String(payload.text || payload.content || payload.preview || '');
  fileOriginals.set(path, originalText);
  if (!openFiles.includes(path)) openFiles.push(path);
  rememberRecentFile(path);
  await initMonaco();
  const editorTextValue = restorePersistedBuffer(path, originalText);
  setEditorValue(editorTextValue);
  if (editorTextValue === originalText) dirtyFiles.delete(path);
  else dirtyFiles.add(path);
  $('activeFile').textContent = path;
  setSourcePlanStatus('No editor draft yet.', 'muted');
  renderSourcePlanChecklist();
  updateEditorMeta();
  updateOpenTabs();
  renderFileExplorer();
  updateStatusChips();
  renderNextActionInspector();
  updateDiagnosticsAndDecorations();
  diffCurrentEdit();
  await refreshSymbolOutline();
  await refreshRelatedContext();
  saveWorkspaceState();
  if (options.refreshSnapshot !== false) await refreshSnapshot();
}

async function reloadActiveFileFromDisk(force = false) {
  if (!currentFile) {
    log('reload blocked: no active file.');
    return;
  }
  if (!force && dirtyFiles.has(currentFile) && !window.confirm(`${currentFile} has unsaved staged edits. Reload from disk and discard them?`)) return;
  const path = currentFile;
  dirtyFiles.delete(path);
  clearPersistedBuffer(path);
  fileModels.get(path)?.dispose();
  fileModels.delete(path);
  await openFile(path);
  log(`reloaded file: ${path}`);
}

function revertEditorBuffer() {
  if (!currentFile) {
    log('revert blocked: no active file.');
    return;
  }
  if (dirtyFiles.has(currentFile) && !window.confirm(`Revert staged edits for ${currentFile}?`)) return;
  const original = fileOriginals.get(currentFile) ?? originalText;
  setEditorValue(original);
  dirtyFiles.delete(currentFile);
  clearPersistedBuffer(currentFile);
  updateEditorMeta();
  updateOpenTabs();
  renderFileExplorer();
  diffCurrentEdit();
  setSourcePlanStatus('Editor buffer reverted to last loaded file content.', 'muted');
  log(`reverted buffer: ${currentFile}`);
}

async function saveViaSourcePlan() {
  if (!currentFile) {
    setSourcePlanStatus('Select a file before saving.', 'warn');
    return;
  }
  if (!dirtyFiles.has(currentFile)) {
    setSourcePlanStatus('No staged editor changes to save.', 'muted');
    return;
  }
  if (desktopLocalMode) {
    diffCurrentEdit();
    document.querySelector('[data-editor-tab="diff"]').click();
    setSourcePlanStatus('Local IDE Mode: Save is queued as a diff preview. Start the gateway to apply through SourcePlan.', 'warn');
    return;
  }
  if (!window.confirm(`Save ${currentFile} through BEAST SourcePlan? This will draft, verify/apply through policy, write rollback, and record evidence.`)) return;
  await sourcePlanDraft();
  if (!currentSourcePlan) return;
  await applySourcePlan(false);
}

function editorSelectionInfo() {
  if (monacoEditor && monacoEditor.getModel()) {
    const selection = monacoEditor.getSelection();
    const model = monacoEditor.getModel();
    const start = model.getOffsetAt(selection.getStartPosition());
    const end = model.getOffsetAt(selection.getEndPosition());
    const selected = model.getValueInRange(selection);
    return {
      start,
      end,
      selected,
      line: selection.startLineNumber,
      col: selection.startColumn,
      lineEnd: selection.endLineNumber,
    };
  }
  const editor = $('editorText');
  const start = editor.selectionStart || 0;
  const end = editor.selectionEnd || 0;
  const before = editor.value.slice(0, start);
  const selected = editor.value.slice(start, end);
  const line = before.split('\n').length;
  const col = before.length - before.lastIndexOf('\n');
  const lineEnd = line + Math.max(0, selected.split('\n').length - 1);
  return { start, end, selected, line, col, lineEnd };
}

function updateEditorMeta() {
  const info = editorSelectionInfo();
  const dirty = getEditorValue() === originalText ? 'clean' : 'dirty';
  const selected = info.end > info.start ? ` · selected ${info.end - info.start} chars · lines ${info.line}-${info.lineEnd}` : '';
  const tabs = openFiles.length ? ` · ${openFiles.length} tab${openFiles.length === 1 ? '' : 's'}` : '';
  $('editorMeta').textContent = `line ${info.line} · col ${info.col} · ${dirty}${selected}${tabs}`;
  if (!$('agentContextSummary').closest('.hidden')) renderAgentContextPack();
}

async function refreshRelatedContext() {
  if (!currentFile) {
    $('relatedContext').innerHTML = '<div class="mini-card muted">Select a file.</div>';
    return;
  }
  const params = new URLSearchParams();
  if (workspaceRoot) params.set('root_path', workspaceRoot);
  params.set('path', currentFile);
  params.set('limit', '24');
  try {
    const payload = await getJson(`/edgek/ide/related-context?${params.toString()}`);
    renderList($('relatedContext'), payload.related || [], item => {
      const path = escapeHtml(item.path || '');
      const kind = escapeHtml(item.relationship_kind || 'related');
      return `<button class="file-item" data-path="${path}"><b>${kind}</b><br><span class="muted">${path}</span></button>`;
    });
  } catch (error) {
    $('relatedContext').innerHTML = `<div class="mini-card muted">${escapeHtml(error.message || error)}</div>`;
  }
}

function selectEditorRange(lineStart, lineEnd, reveal = true) {
  if (!monacoEditor || !monacoEditor.getModel()) return;
  const model = monacoEditor.getModel();
  const start = Math.max(1, Number(lineStart || 1));
  const end = Math.max(start, Number(lineEnd || start));
  const endColumn = model.getLineMaxColumn(Math.min(end, model.getLineCount()));
  const range = new monaco.Range(start, 1, end, endColumn);
  monacoEditor.setSelection(range);
  if (reveal) monacoEditor.revealRangeInCenter(range);
  updateEditorMeta();
}

function editorQueryToken() {
  const selection = editorSelectionInfo();
  if (selection.selected && selection.selected.length <= 120) return selection.selected.trim();
  if (!monacoEditor || !monacoEditor.getModel()) return '';
  const model = monacoEditor.getModel();
  const position = monacoEditor.getPosition();
  const word = model.getWordAtPosition(position);
  return word?.word || '';
}

function renderSymbolOutline(payload = {}) {
  const rows = symbolOutlineRows || [];
  const meta = $('symbolOutlineMeta');
  if (!currentFile) {
    meta.textContent = 'Select a file to map symbols.';
    meta.className = 'status-box muted';
    $('symbolOutline').innerHTML = emptyCard('No active file.', 'Open a source file to see classes/functions.');
    return;
  }
  meta.textContent = [
    `${rows.length} symbol(s) · ${payload.line_count || getEditorValue().split('\n').length} lines`,
    payload.truncated ? 'outline parsed from bounded file text' : 'outline parsed from active file',
    selectedSymbol ? `selected: ${selectedSymbol.name} ${selectedSymbol.line_start}-${selectedSymbol.line_end}` : 'select a symbol for precise agent/context work',
  ].join('\n');
  meta.className = `status-box ${rows.length ? 'ready' : 'warn'}`;
  renderList($('symbolOutline'), rows, item => {
    const active = selectedSymbol && selectedSymbol.name === item.name && selectedSymbol.line_start === item.line_start ? ' active' : '';
    return [
      `<button class="file-item${active}" data-symbol-line="${escapeHtml(item.line_start)}" data-symbol-end="${escapeHtml(item.line_end)}" data-symbol-name="${escapeHtml(item.name)}">`,
      `<b>${escapeHtml(item.kind || 'symbol')}</b> · ${escapeHtml(item.name || 'anonymous')}`,
      `<br><span class="muted">lines ${escapeHtml(item.line_start)}-${escapeHtml(item.line_end)}</span>`,
      '</button>',
    ].join('');
  }, 'No symbols found in this file.', 'Use a smaller selection, related context, or file search.');
}

async function refreshSymbolOutline() {
  if (!currentFile) {
    symbolOutlineRows = [];
    selectedSymbol = null;
    renderSymbolOutline();
    return;
  }
  const params = new URLSearchParams();
  if (workspaceRoot) params.set('root_path', workspaceRoot);
  params.set('path', currentFile);
  params.set('max_symbols', '500');
  try {
    const payload = await getJson(`/edgek/ide/symbol-outline?${params.toString()}`);
    symbolOutlineRows = payload.symbols || [];
    renderSymbolOutline(payload);
  } catch (error) {
    symbolOutlineRows = localSymbolOutline(currentFile, getEditorValue());
    renderSymbolOutline({ line_count: getEditorValue().split('\n').length, truncated: false });
    log(`symbol outline fallback: ${error.message || error}`);
  }
}

function localSymbolOutline(path, text) {
  const rows = [];
  const patterns = [
    ['class', /^\s*class\s+([A-Za-z_][\w]*)/],
    ['function', /^\s*(?:async\s+def|def|function)\s+([A-Za-z_][\w]*)/],
    ['export', /^\s*export\s+(?:async\s+)?(?:function|class|const|let)\s+([A-Za-z_][\w]*)/],
  ];
  const lines = String(text || '').split('\n');
  lines.forEach((line, index) => {
    for (const [kind, pattern] of patterns) {
      const match = line.match(pattern);
      if (match) {
        rows.push({ name: match[1], kind, line_start: index + 1, line_end: index + 1, path });
        break;
      }
    }
  });
  return rows;
}

function selectSymbolFromButton(button) {
  const lineStart = Number(button.dataset.symbolLine || 1);
  const lineEnd = Number(button.dataset.symbolEnd || lineStart);
  selectedSymbol = {
    name: button.dataset.symbolName || 'symbol',
    line_start: lineStart,
    line_end: lineEnd,
    path: currentFile,
  };
  selectEditorRange(lineStart, lineEnd);
  renderSymbolOutline({ line_count: getEditorValue().split('\n').length });
  log(`symbol selected: ${currentFile}:${lineStart}-${lineEnd} ${selectedSymbol.name}`);
}

function askAgentAboutSymbol() {
  if (!currentFile) {
    log('Ask Symbol blocked: no active file.');
    return;
  }
  if (!selectedSymbol) {
    const info = editorSelectionInfo();
    if (!info.selected) {
      log('Ask Symbol blocked: select a Symbol Lens row or editor range first.');
      setAgentPatchStatus('Select a Symbol Lens row or editor range before asking the agent.', 'warn');
      return;
    }
    selectedSymbol = { name: 'selected_range', line_start: info.line, line_end: info.lineEnd, path: currentFile };
  }
  selectEditorRange(selectedSymbol.line_start, selectedSymbol.line_end);
  $('agentIncludeActiveFile').checked = true;
  $('agentIncludeSelection').checked = true;
  $('agentPromptText').value = [
    `Analyze ${currentFile}:${selectedSymbol.line_start}-${selectedSymbol.line_end} (${selectedSymbol.name}).`,
    'Return a SourcePlan-safe, targeted improvement plan first.',
    'If code is needed, return one narrow fenced replacement only for this selected symbol/range.',
    'Do not rewrite the whole file and do not infer context outside the selected range plus attached context files.',
  ].join(' ');
  setDesktopPage('agents');
  renderAgentContextPack();
  setAgentPatchStatus(`Symbol-scoped request prepared for ${selectedSymbol.name}.`, 'ready');
}

function renderSymbolSearchResults(payload = {}, emptyTitle = '') {
  const rows = symbolSearchRows || [];
  renderList($('symbolSearchResults'), rows, item => {
    const active = selectedSymbolSearch && selectedSymbolSearch.path === item.path && selectedSymbolSearch.line_start === item.line_start ? ' active' : '';
    return [
      `<button class="file-item${active}" data-symbol-search-path="${escapeHtml(item.path)}" data-symbol-search-line="${escapeHtml(item.line_start)}" data-symbol-search-end="${escapeHtml(item.line_end)}" data-symbol-search-name="${escapeHtml(item.name)}">`,
      `<b>${escapeHtml(item.name || 'symbol')}</b> · ${escapeHtml(item.kind || 'symbol')}`,
      `<br><span class="muted">${escapeHtml(item.path || '')}:${escapeHtml(item.line_start)}-${escapeHtml(item.line_end)}</span>`,
      item.detail ? `<br><span class="muted">${escapeHtml(item.detail)}</span>` : '',
      '</button>',
    ].join('');
  }, emptyTitle || (payload.query ? 'No matching workspace symbols.' : 'Search for a function, class, route, or file symbol.'), 'Results open directly into Monaco with the symbol range selected.');
}

async function runSymbolSearch() {
  const query = $('symbolSearchQuery').value.trim();
  const params = new URLSearchParams();
  if (workspaceRoot) params.set('root_path', workspaceRoot);
  params.set('query', query);
  params.set('limit', '80');
  try {
    const payload = await getJson(`/edgek/ide/symbol-search?${params.toString()}`, 12000);
    symbolSearchRows = payload.symbols || [];
    selectedSymbolSearch = symbolSearchRows[0] || null;
    renderSymbolSearchResults(payload);
    log(`symbol search: ${payload.match_count || 0} match(es), scanned ${payload.scanned_files || 0} file(s)`);
  } catch (error) {
    symbolSearchRows = [];
    selectedSymbolSearch = null;
    renderSymbolSearchResults({ query });
    log(`symbol search failed: ${error.message || error}`);
  }
}

function selectSymbolSearchResult(button) {
  selectedSymbolSearch = {
    path: button.dataset.symbolSearchPath || '',
    line_start: Number(button.dataset.symbolSearchLine || 1),
    line_end: Number(button.dataset.symbolSearchEnd || button.dataset.symbolSearchLine || 1),
    name: button.dataset.symbolSearchName || 'symbol',
  };
  renderSymbolSearchResults({ query: $('symbolSearchQuery').value.trim() });
}

async function openSelectedSymbolSearchResult() {
  if (!selectedSymbolSearch?.path) {
    log('symbol search open blocked: no result selected.');
    return;
  }
  await openFile(selectedSymbolSearch.path);
  selectEditorRange(selectedSymbolSearch.line_start, selectedSymbolSearch.line_end);
}

async function askAgentAboutSymbolSearchResult() {
  if (!selectedSymbolSearch?.path) {
    log('symbol search ask blocked: no result selected.');
    return;
  }
  await openSelectedSymbolSearchResult();
  selectedSymbol = {
    name: selectedSymbolSearch.name,
    path: selectedSymbolSearch.path,
    line_start: selectedSymbolSearch.line_start,
    line_end: selectedSymbolSearch.line_end,
  };
  askAgentAboutSymbol();
}

async function goToDefinition() {
  const query = editorQueryToken() || $('symbolSearchQuery').value.trim();
  if (!query) {
    log('definition lookup blocked: select or place cursor on a symbol.');
    return;
  }
  $('symbolSearchQuery').value = query;
  await runSymbolSearch();
  await openSelectedSymbolSearchResult();
}

async function findReferences() {
  const query = editorQueryToken() || $('symbolSearchQuery').value.trim();
  if (!query) {
    log('reference lookup blocked: select or place cursor on a symbol.');
    return;
  }
  const params = new URLSearchParams();
  if (workspaceRoot) params.set('root_path', workspaceRoot);
  params.set('query', query);
  params.set('limit', '120');
  const payload = await getJson(`/edgek/ide/text-search?${params.toString()}`);
  symbolSearchRows = (payload.matches || []).map(item => ({
    name: query,
    kind: 'reference',
    path: item.path,
    line_start: item.line,
    line_end: item.line,
    detail: item.preview,
  }));
  selectedSymbolSearch = symbolSearchRows[0] || null;
  renderSymbolSearchResults({ query }, `No references found for ${query}.`);
  log(`references for ${query}: ${symbolSearchRows.length}`);
}

async function relatedTestsRoutes() {
  await refreshCodeIntelligence();
}

async function refreshCodeIntelligence() {
  if (!currentFile && !editorQueryToken()) {
    log('code intelligence blocked: select a file or symbol.');
    return;
  }
  const params = new URLSearchParams();
  if (workspaceRoot) params.set('root_path', workspaceRoot);
  if (currentFile) params.set('path', currentFile);
  params.set('query', editorQueryToken() || (currentFile ? currentFile.split('/').pop().replace(/\.[^.]+$/, '') : ''));
  params.set('limit', '120');
  const payload = await getJson(`/edgek/ide/code-intel?${params.toString()}`);
  const diagnostics = payload.diagnostics || [];
  const related = payload.related || [];
  symbolSearchRows = [
    ...(payload.symbols || []).map(item => ({ ...item, path: currentFile, detail: item.signature || '' })),
    ...related.map(item => ({
      name: payload.query || item.path,
      kind: item.relationship_kind || 'related',
      path: item.path,
      line_start: item.line,
      line_end: item.line,
      detail: item.preview,
    })),
  ];
  selectedSymbolSearch = symbolSearchRows[0] || null;
  renderSymbolSearchResults({ query: payload.query || 'code intelligence' }, 'No code intelligence results.');
  renderList($('relatedContext'), related.slice(0, 24), item => {
    const path = escapeHtml(item.path || '');
    return `<button class="file-item" data-path="${path}"><b>${escapeHtml(item.relationship_kind || 'related')}</b><br><span class="muted">${path}:${escapeHtml(item.line || '')} ${escapeHtml(item.preview || '')}</span></button>`;
  });
  if (diagnostics.length) {
    $('codeCortex').innerHTML = diagnostics.slice(0, 12).map(item => `<div class="mini-card ${item.severity === 'error' ? 'bad' : 'warn'}"><b>${escapeHtml(item.severity)}</b> · line ${escapeHtml(item.line)}<br>${escapeHtml(item.message)}</div>`).join('');
  }
  log(`code intelligence: ${diagnostics.length} diagnostic(s), ${related.length} related item(s)`);
}

function diffCurrentEdit() {
  updateEditorMeta();
  const next = getEditorValue();
  if (!currentFile) {
    $('diffPreview').textContent = 'No file selected.';
    $('diffMeta').textContent = 'No file selected.';
    renderDiffHunkSelector([]);
    return;
  }
  if (next === originalText) {
    $('diffPreview').textContent = 'No changes staged.';
    $('diffMeta').textContent = 'No changes staged.';
    updateMonacoDiff(originalText, next);
    renderDiffHunkSelector([]);
    return;
  }
  $('diffPreview').textContent = [
    `--- a/${currentFile}`,
    `+++ b/${currentFile}`,
    '@@ staged browser edit @@',
    ...simpleLineDiff(originalText, next),
    '',
    'SourcePlan policy: staged editor text is advisory until compiled into explicit operations, approved, verified, and closed with evidence.',
  ].join('\n');
  $('diffMeta').textContent = `${currentFile} · staged buffer diff · SourcePlan required`;
  updateMonacoDiff(originalText, next);
  renderDiffHunkSelector(diffHunks(originalText, next));
}

async function sourcePlanSelectionDraft() {
  if (desktopLocalMode) {
    setSourcePlanStatus('Local IDE Mode: selected edits are visible in Monaco, but SourcePlan compilation needs the BEAST gateway. Use Gateway Doctor Restart when ready.', 'warn');
    diffCurrentEdit();
    document.querySelector('[data-editor-tab="diff"]').click();
    return;
  }
  if (!currentFile) {
    setSourcePlanStatus('Select a file before drafting a selected SourcePlan.', 'warn');
    return;
  }
  const info = editorSelectionInfo();
  if (!info.selected) {
    setSourcePlanStatus('Select code before creating a selected SourcePlan.', 'warn');
    return;
  }
  const replacement = window.prompt('Replacement text for selected range', info.selected);
  if (replacement === null) return;
  const result = await postJson('/edgek/ide/sourceplan/from-selection', {
    root_path: workspaceRoot,
    path: currentFile,
    original_text: originalText,
    selection_text: info.selected,
    replacement_text: replacement,
    objective: `Apply selected governed edit to ${currentFile}:${info.line}-${info.lineEnd}`,
    provider: 'nvidia_nim',
    char_start: info.start,
    char_end: info.end,
    line_start: info.line,
    line_end: info.lineEnd,
  });
  document.querySelector('[data-editor-tab="diff"]').click();
  if (!result.ok) {
    const reason = result.error || 'selection_draft_failed';
    setSourcePlanStatus(`${reason}${result.stale_context ? '\nReload file before drafting.' : ''}`, result.stale_context ? 'bad' : 'warn');
    $('diffPreview').textContent = JSON.stringify(result, null, 2);
    log(`selection SourcePlan failed: ${reason}`);
    return;
  }
  currentSourcePlan = result.plan;
  $('diffPreview').textContent = [
    `# BEAST Selected SourcePlan Draft: ${currentSourcePlan.plan_id}`,
    `# ${currentFile}:${info.line}-${info.lineEnd}`,
    '',
    result.preview_text || 'No diff text returned.',
  ].join('\n');
  setSourcePlanStatus(`Selected draft ready: ${currentSourcePlan.plan_id}\n${currentFile}:${info.line}-${info.lineEnd}`, 'ready');
  log(`selection SourcePlan ready: ${currentSourcePlan.plan_id}`);
  await refreshSourcePlanLifecycle();
}

function simpleLineDiff(oldText, newText) {
  const oldLines = oldText.split('\n');
  const newLines = newText.split('\n');
  const max = Math.max(oldLines.length, newLines.length);
  const lines = [];
  for (let i = 0; i < max; i += 1) {
    if (oldLines[i] === newLines[i]) {
      if (lines.length < 120) lines.push(` ${oldLines[i] || ''}`);
    } else {
      if (oldLines[i] !== undefined) lines.push(`-${oldLines[i]}`);
      if (newLines[i] !== undefined) lines.push(`+${newLines[i]}`);
    }
  }
  return lines.slice(0, 260);
}

function diffHunks(oldText, newText) {
  const oldLines = String(oldText || '').split('\n');
  const newLines = String(newText || '').split('\n');
  const max = Math.max(oldLines.length, newLines.length);
  const hunks = [];
  let current = null;
  for (let index = 0; index < max; index += 1) {
    if (oldLines[index] !== newLines[index]) {
      if (!current) current = { id: `h${hunks.length + 1}`, start: index + 1, end: index + 1, changed: 0 };
      current.end = index + 1;
      current.changed += 1;
    } else if (current) {
      hunks.push(current);
      current = null;
    }
  }
  if (current) hunks.push(current);
  return hunks;
}

function renderDiffHunkSelector(hunks = []) {
  const node = $('diffHunkSelector');
  if (!node) return;
  if (!hunks.length) {
    selectedDiffHunks.clear();
    node.innerHTML = emptyCard('No changed hunks.', 'Edit a file to create governed hunk selections.');
    return;
  }
  if (!selectedDiffHunks.size) hunks.forEach(item => selectedDiffHunks.add(item.id));
  node.innerHTML = hunks.map(item => {
    const selected = selectedDiffHunks.has(item.id);
    return [
      `<button class="file-item${selected ? ' active' : ''}" data-diff-hunk="${escapeHtml(item.id)}" data-hunk-start="${item.start}" data-hunk-end="${item.end}">`,
      `<b>${selected ? 'selected' : 'skipped'}</b> · lines ${item.start}-${item.end}`,
      `<br><span class="muted">${item.changed} changed line(s). Click to toggle and focus this range.</span>`,
      '</button>',
    ].join('');
  }).join('');
}

function toggleDiffHunk(button) {
  const id = button.dataset.diffHunk;
  if (!id) return;
  if (selectedDiffHunks.has(id)) selectedDiffHunks.delete(id);
  else selectedDiffHunks.add(id);
  const start = Number(button.dataset.hunkStart || 1);
  const end = Number(button.dataset.hunkEnd || start);
  if (monacoEditor && window.monaco) {
    monacoEditor.setSelection(new monaco.Range(start, 1, end, 1));
    monacoEditor.revealLineInCenter(start);
  }
  renderDiffHunkSelector(diffHunks(originalText, getEditorValue()));
  log(`diff hunk ${selectedDiffHunks.has(id) ? 'selected' : 'skipped'}: ${id} lines ${start}-${end}`);
}

function syncProviderControls() {
  if ($('providerSelect')) $('providerSelect').value = selectedProvider;
  if ($('providerModel')) $('providerModel').value = selectedModel;
}

function providerStorageKey(kind) {
  return `beast.${workspaceRoot || 'global'}.${kind}`;
}

function saveProviderSetup(provider = selectedProvider, model = selectedModel) {
  selectedProvider = provider || 'nvidia_nim';
  selectedModel = model || DEFAULT_NVIDIA_NIM_MODEL;
  localStorage.setItem('beast.provider', selectedProvider);
  localStorage.setItem('beast.model', selectedModel);
  localStorage.setItem(providerStorageKey('provider'), selectedProvider);
  localStorage.setItem(providerStorageKey('model'), selectedModel);
  syncProviderControls();
  saveWorkspaceState();
}

function providerRecordLabel(item, fallback = '') {
  if (item == null) return fallback;
  if (typeof item === 'string') return item;
  if (typeof item !== 'object') return String(item);
  if (item.value && typeof item.value === 'object') return providerRecordLabel({ key: item.key, ...item.value }, fallback);
  const id = item.provider_id || item.id || item.provider || item.name || item.key || fallback;
  const model = item.default_model || item.model || item.selected_model || '';
  const backend = item.backend || item.route_provider || item.adapter_class || '';
  return [id, model || backend].filter(Boolean).join(' · ');
}

function providerInventoryItems(registry = null) {
  if (!registry || typeof registry !== 'object') return [];
  const candidates = registry.providers || registry.registry || registry.adapters || registry.records || registry.items || [];
  if (Array.isArray(candidates)) return candidates;
  if (candidates && typeof candidates === 'object') {
    return Object.entries(candidates).map(([key, value]) => (
      value && typeof value === 'object' ? { key, ...value } : { key, value }
    ));
  }
  return [];
}

function providerReadinessState(secretRoute = null, smoke = null) {
  const secretReady = secretRoute?.status === 'ready';
  const smokeOk = smoke && (smoke.status === 'ok' || smoke.ok === true);
  if (secretReady && smokeOk) return { label: 'READY · live provider verified', className: 'ready' };
  if (secretReady) return { label: 'READY · smoke not run', className: 'ready' };
  if (secretRoute?.status) return { label: String(secretRoute.status), className: 'warn' };
  return { label: 'unchecked', className: 'warn' };
}

function providerSetupSummary(registry = null, state = null, secretRoute = null, smoke = null, error = '') {
  const configured = state?.providers?.[selectedProvider] || state?.registry?.[selectedProvider] || null;
  const available = providerInventoryItems(registry);
  const availableText = available
    .map((item, index) => providerRecordLabel(item, `provider_${index + 1}`))
    .filter(Boolean)
    .slice(0, 8)
    .join(', ');
  const keyHint = selectedProvider === 'nvidia_nim'
    ? 'expects NVIDIA_API_KEY or NVIDIA_NIM_API_KEY in the gateway environment'
    : 'uses its provider environment configuration';
  const secretStatus = secretRoute?.status
    ? `${secretRoute.status}${secretRoute.missing_env?.length ? ` · missing ${secretRoute.missing_env.join(', ')}` : ''}`
    : 'not checked';
  const smokeStatus = smoke
    ? `${smoke.status || smoke.ok || 'ran'}${smoke.error ? ` · ${smoke.error}` : ''}`
    : 'not run';
  const lines = [
    `${selectedProvider} · ${selectedModel}`,
    secretRoute?.status === 'ready' && smoke && (smoke.status === 'ok' || smoke.ok) ? 'route: READY · live provider verified' : '',
    keyHint,
    configured ? `registry: ${configured.status || configured.state || 'configured'}` : 'registry: pending',
    `secret route: ${secretStatus}`,
    `live smoke: ${smokeStatus}`,
    availableText ? `available: ${availableText}` : 'available: not loaded',
    error ? `error: ${error}` : '',
  ].filter(Boolean);
  return lines.join('\n');
}

function renderProviderSetup(registry = null, state = null, secretRoute = null, smoke = null, error = '') {
  lastProviderError = error || '';
  const configured = state?.providers?.[selectedProvider] || null;
  const readiness = providerReadinessState(secretRoute, smoke);
  const requiredEnv = (secretRoute?.required_env || configured?.env || []).join(', ') || 'none';
  const missingEnv = (secretRoute?.missing_env || []).join(', ') || 'none';
  const available = providerInventoryItems(registry).slice(0, 10);
  const rows = available.map((item, index) => {
    const label = providerRecordLabel(item, `provider_${index + 1}`);
    const active = label.startsWith(selectedProvider) ? ' active' : '';
    return `<div class="mini-card${active}">${escapeHtml(label)}</div>`;
  }).join('');
  $('providerState').innerHTML = [
    `<b>${escapeHtml(selectedProvider)}</b> · ${escapeHtml(selectedModel)}`,
    `<br><span class="muted">${escapeHtml(readiness.label)}</span>`,
    `<br><span class="muted">secret route: ${escapeHtml(secretRoute?.status || 'not checked')} · required: ${escapeHtml(requiredEnv)} · missing: ${escapeHtml(missingEnv)}</span>`,
    smoke ? `<br><span class="muted">live smoke: ${escapeHtml(smoke.status || smoke.ok || 'ran')}</span>` : '<br><span class="muted">live smoke: not run</span>',
    error ? `<br><span class="muted">provider attention: ${escapeHtml(providerErrorHint(error))}</span>` : '',
    rows ? `<div class="provider-inventory">${rows}</div>` : emptyCard('No provider inventory loaded.', 'Refresh when the gateway is online, or keep the selected local/default route.'),
  ].filter(Boolean).join('');
  $('providerState').className = `status-box ${error ? 'bad' : readiness.className}`;
  renderNextActionInspector();
}

function providerErrorHint(error) {
  const text = String(error || '');
  if (!text) return '';
  if (/Name or service not known|ENOTFOUND|EAI_AGAIN|network/i.test(text)) return `${text}. This looks like network/DNS provider reachability, not an IDE failure. Check NVIDIA endpoint access and gateway environment.`;
  if (/NVIDIA_API_KEY|NVIDIA_NIM_API_KEY|missing/i.test(text)) return `${text}. Set NVIDIA_API_KEY or NVIDIA_NIM_API_KEY before starting the gateway.`;
  if (/gateway offline|Failed to fetch|timeout/i.test(text)) return `${text}. Restart Gateway or continue with Local IDE Mode until routes are ready.`;
  return text;
}

async function refreshProviderSetup() {
  syncProviderControls();
  if (desktopLocalMode) {
    renderProviderSetup(null, null, null, null, 'gateway offline; using local desktop defaults for new sessions');
    $('providerRaw').textContent = JSON.stringify({
      selectedProvider,
      selectedModel,
      local_mode: true,
      note: 'Set NVIDIA_API_KEY or NVIDIA_NIM_API_KEY before starting the BEAST gateway for live NIM runs.',
    }, null, 2);
    return;
  }
  try {
    const [registry, state, secretRoute] = await Promise.all([
      getJson('/edgek/providers/registry'),
      getJson('/edgek/providers/state'),
      getJson(`/edgek/providers/secrets/route/${encodeURIComponent(selectedProvider)}`),
    ]);
    renderProviderSetup(registry, state, secretRoute);
    $('providerRaw').textContent = JSON.stringify({ selectedProvider, selectedModel, registry, state, secretRoute }, null, 2);
  } catch (error) {
    renderProviderSetup(null, null, null, null, error.message || String(error));
    $('providerRaw').textContent = JSON.stringify({ selectedProvider, selectedModel, error: error.message || String(error) }, null, 2);
  }
}

async function smokeNvidiaProvider() {
  saveProviderSetup('nvidia_nim', $('providerModel').value.trim() || DEFAULT_NVIDIA_NIM_MODEL);
  if (desktopLocalMode) {
    renderProviderSetup(null, null, null, null, 'gateway offline; live smoke requires gateway');
    log('NIM smoke blocked: gateway offline.');
    return;
  }
  $('providerState').textContent = 'Running explicit NVIDIA NIM smoke test...';
  $('providerState').className = 'status-box warn';
  try {
    const [registry, state, secretRoute, smoke] = await Promise.all([
      getJson('/edgek/providers/registry'),
      getJson('/edgek/providers/state'),
      getJson('/edgek/providers/secrets/route/nvidia_nim'),
      postJson('/edgek/providers/nvidia-nim/live-smoke', {
        confirm_live: true,
        model: selectedModel,
        prompt: 'Output only this token and nothing else: BEAST_NIM_LIVE_OK',
        max_tokens: 32,
        timeout_seconds: 30,
      }),
    ]);
    renderProviderSetup(registry, state, secretRoute, smoke);
    $('providerRaw').textContent = JSON.stringify({ selectedProvider, selectedModel, registry, state, secretRoute, smoke }, null, 2);
    log(`NIM smoke: ${smoke?.status || smoke?.ok || 'complete'}`);
  } catch (error) {
    renderProviderSetup(null, null, null, null, error.message || String(error));
    $('providerRaw').textContent = JSON.stringify({ selectedProvider, selectedModel, smoke_error: error.message || String(error) }, null, 2);
    log(`NIM smoke failed: ${error.message || error}`);
  }
}

function renderToolingSnapshot(snapshot, error = '') {
  lastToolingSnapshot = snapshot || null;
  const syntax = snapshot?.syntax || {};
  const linting = snapshot?.linting || {};
  const mcp = snapshot?.mcp || {};
  const plugins = snapshot?.plugins || {};
  const env = Array.isArray(snapshot?.environments) ? snapshot.environments : [];
  const source = snapshot?.source || (desktopLocalMode ? 'local' : 'gateway');
  const syntaxClass = syntax.ok === false ? 'bad' : syntax.status === 'skipped' || syntax.status === 'idle' ? 'warn' : 'ready';
  $('toolingSummary').textContent = [
    `${snapshot?.status || 'ready'} · ${source}`,
    `syntax: ${syntax.status || 'unknown'}${syntax.path ? ` · ${syntax.path}` : ''}`,
    `lint: ${linting.has_root_lint ? 'root lint script' : 'no root lint script'} · desktop smoke ${linting.has_desktop_smoke ? 'ready' : 'missing'}`,
    `mcp: ${mcp.status || (mcp.configured ? 'configured' : 'unknown')}`,
    `plugins/extensions: ${plugins.status || 'unknown'}`,
  ].join('\n');
  $('toolingSummary').className = `status-box ${error ? 'bad' : syntaxClass}`;
  $('syntaxLintPanel').innerHTML = [
    `<div class="mini-card ${syntaxClass}"><b>Syntax</b><br>${escapeHtml(syntax.status || 'unknown')} · ${escapeHtml(syntax.kind || 'n/a')}<br><span class="muted">${escapeHtml(syntax.stderr || syntax.error || syntax.detail || syntax.path || 'No syntax issues reported.')}</span></div>`,
    `<div class="mini-card"><b>Lint Contract</b><br>${escapeHtml(linting.recommendation || 'No lint contract loaded.')}<br><span class="muted">root scripts: ${escapeHtml((linting.scripts?.root || []).join(', ') || 'none')}</span><br><span class="muted">desktop scripts: ${escapeHtml((linting.scripts?.desktop || []).join(', ') || 'none')}</span></div>`,
  ].join('');
  $('mcpPluginPanel').innerHTML = [
    `<div class="mini-card"><b>MCP</b><br>${escapeHtml(mcp.status || 'unknown')}<br><span class="muted">${escapeHtml(mcp.cursor_config || 'no config path')}</span><br><span class="muted">${escapeHtml((mcp.expected_routes || []).join(' · '))}</span></div>`,
    `<div class="mini-card"><b>Plugins + Extensions</b><br>${escapeHtml(plugins.status || 'unknown')}<br><span class="muted">VS Code extension: ${plugins.vscode_extension_present ? 'present' : 'missing'} · Desktop IDE: ${plugins.desktop_ide_present ? 'present' : 'missing'}</span><br><span class="muted">${escapeHtml((plugins.expected_routes || []).join(' · '))}</span></div>`,
  ].join('');
  $('environmentPanel').innerHTML = env.length
    ? env.map(item => `<div class="mini-card ${item.ok ? 'ready' : 'warn'}"><b>${escapeHtml(item.command)}</b><br>${escapeHtml(item.version || item.error || 'not available')}</div>`).join('')
    : emptyCard('Environment not loaded.', 'Refresh the Tooling Plane to detect Python, Node, npm, and git.');
  $('toolingRaw').textContent = JSON.stringify(snapshot || { error }, null, 2);
  renderNextActionInspector();
}

function renderBenchmarkVerdict(result, error = '') {
  lastBenchmarkVerdict = result || null;
  const node = $('benchmarkVerdictStatus');
  if (!node) return;
  if (!result) {
    node.textContent = error || 'No benchmark verdict loaded.';
    node.className = `status-box ${error ? 'bad' : 'muted'}`;
    return;
  }
  const provisional = result.claim_status || 'unknown';
  const structural = result.structural_claim_status || 'unknown';
  node.textContent = [
    `Provisional: ${provisional}`,
    `Structural: ${structural}`,
    result.verdict_path ? `Provisional verdict: ${result.verdict_path}` : '',
    result.structural_verdict_path ? `Structural verdict: ${result.structural_verdict_path}` : '',
  ].filter(Boolean).join('\n');
  node.className = structural === 'supported' ? 'status-box ready' : provisional === 'supported' ? 'status-box warn' : 'status-box bad';
}

async function refreshToolingSnapshot() {
  let snapshot = null;
  if (!desktopLocalMode) {
    try {
      const params = new URLSearchParams();
      if (workspaceRoot) params.set('root_path', workspaceRoot);
      if (currentFile) params.set('active_file', currentFile);
      snapshot = await getJson(`/edgek/ide/tooling-snapshot?${params.toString()}`);
    } catch (error) {
      log(`Gateway tooling snapshot unavailable; using local desktop checks: ${error.message || error}`);
    }
  }
  if (!snapshot && window.beastDesktop?.toolingSnapshot) {
    snapshot = await window.beastDesktop.toolingSnapshot(workspaceRoot, currentFile);
  }
  renderToolingSnapshot(snapshot || { ok: false, status: 'warn', source: 'unavailable' });
  log(`tooling snapshot: ${snapshot?.source || 'unavailable'}`);
}

async function runSyntaxToolingCheck() {
  await refreshToolingSnapshot();
  const syntax = lastToolingSnapshot?.syntax || {};
  log(`syntax check: ${syntax.status || 'unknown'}${syntax.path ? ` · ${syntax.path}` : ''}`);
}

function showLintToolingContract() {
  if (!lastToolingSnapshot) refreshToolingSnapshot().catch(error => log(`tooling refresh failed: ${error.message || error}`));
  const linting = lastToolingSnapshot?.linting || {};
  $('toolingRaw').textContent = JSON.stringify(linting, null, 2);
  log(linting.has_root_lint ? 'lint contract: root lint script available.' : 'lint contract: no root lint script detected.');
}

function focusMcpTooling() {
  setDesktopPage('tooling');
  $('mcpPluginPanel')?.scrollIntoView({ block: 'nearest' });
  log('tooling focus: MCP routes, approvals, schema pins, and config.');
}

function focusPluginTooling() {
  setDesktopPage('tooling');
  $('mcpPluginPanel')?.scrollIntoView({ block: 'nearest' });
  log('tooling focus: plugins, extensions, and installable surfaces.');
}

function focusEnvironmentTooling() {
  setDesktopPage('tooling');
  $('environmentPanel')?.scrollIntoView({ block: 'nearest' });
  log('tooling focus: local environment versions.');
}

// ---------------------------------------------------------------------------
// System plane: ports, processes (with governed kill), environment, package
// management, extensions. Kill / free-port reuse the terminal approval pattern:
// window.confirm -> approved:true -> governed gateway endpoint + evidence.
// ---------------------------------------------------------------------------
let lastSystemSnapshot = null;

function systemKillSignal() {
  return $('systemKillSignal')?.value || 'TERM';
}

function renderSystemPorts(ports) {
  const rows = Array.isArray(ports) ? ports : [];
  $('systemPortsPanel').innerHTML = rows.length
    ? rows.map(p => {
        const owner = p.pid ? `pid ${escapeHtml(String(p.pid))} · ${escapeHtml(p.process || '')}` : 'owner not attributable';
        const freeBtn = `<button class="ghost-button" data-free-port="${escapeHtml(String(p.port))}">Free</button>`;
        return `<div class="mini-card"><b>${escapeHtml(p.proto)} :${escapeHtml(String(p.port))}</b> <span class="muted">${escapeHtml(p.address || '')}</span><br><span class="muted">${owner}</span> ${freeBtn}</div>`;
      }).join('')
    : emptyCard('No listening ports found.', 'Refresh the System plane.');
}

function renderSystemProcesses(processes) {
  const rows = Array.isArray(processes) ? processes : [];
  $('systemProcessPanel').innerHTML = rows.length
    ? rows.map(p => `<div class="mini-card"><b>${escapeHtml(p.name || 'process')}</b> <span class="muted">pid ${escapeHtml(String(p.pid))} · ${escapeHtml(String(p.rss_mb || 0))} MB · ${escapeHtml(p.user || '')}</span><br><span class="muted">${escapeHtml((p.cmdline || '').slice(0, 120))}</span><br><button class="ghost-button" data-kill-pid="${escapeHtml(String(p.pid))}" data-kill-name="${escapeHtml(p.name || '')}">Kill</button></div>`).join('')
    : emptyCard('No processes matched.', 'Adjust the filter and refresh.');
}

function renderSystemEnvironment(env) {
  const py = env?.python || {};
  const interp = Array.isArray(env?.interpreters) ? env.interpreters : [];
  const cards = [
    `<div class="mini-card ready"><b>Python</b><br>${escapeHtml(py.version || '?')} · ${py.in_virtualenv ? 'venv' : 'system'}<br><span class="muted">${escapeHtml(py.executable || '')}</span></div>`,
    ...interp.filter(i => i.installed).map(i => `<div class="mini-card ${i.ok ? 'ready' : 'warn'}"><b>${escapeHtml(i.command)}</b><br>${escapeHtml(i.version || i.error || '')}</div>`),
  ];
  $('systemEnvPanel').innerHTML = cards.join('') || emptyCard('Environment not loaded.');
}

function renderSystemPackages(pkg) {
  const py = pkg?.python || {};
  const node = pkg?.node || {};
  const manifests = Array.isArray(node.manifests) ? node.manifests : [];
  const suggestions = Array.isArray(pkg?.suggested_commands) ? pkg.suggested_commands : [];
  const cards = [
    `<div class="mini-card"><b>Python</b><br>${escapeHtml(String(py.declared_count || 0))} declared · ${escapeHtml(String(py.installed_distribution_count || 0))} installed<br><span class="muted">${escapeHtml((py.requirement_files || []).join(', ') || 'no requirements files')}${py.has_pyproject ? ' · pyproject.toml' : ''}</span></div>`,
    ...manifests.map(m => `<div class="mini-card ${m.node_modules_installed ? 'ready' : 'warn'}"><b>node: ${escapeHtml(m.location)}</b><br>${escapeHtml(String(m.dependency_count))} deps · ${escapeHtml(m.manager)} · ${m.node_modules_installed ? 'installed' : 'not installed'}<br><span class="muted">scripts: ${escapeHtml((m.scripts || []).join(', ') || 'none')}</span></div>`),
    ...suggestions.map(s => `<div class="mini-card"><b>Suggested</b> <span class="state-chip warn">${escapeHtml(s.risk || 'medium')}</span><br><code>${escapeHtml(s.command)}</code><br><button class="ghost-button" data-run-terminal="${escapeHtml(s.command)}">Run in governed terminal</button></div>`),
  ];
  $('systemPackagePanel').innerHTML = cards.join('') || emptyCard('No package data.');
}

function renderSystemExtensions(ext) {
  const vsix = ext?.vscode_extension || {};
  const mcp = ext?.mcp || {};
  const plugins = ext?.plugins || {};
  const commands = Array.isArray(vsix.commands) ? vsix.commands : [];
  $('systemExtPanel').innerHTML = [
    `<div class="mini-card ${vsix.present ? 'ready' : 'warn'}"><b>VS Code Extension</b><br>${escapeHtml(vsix.display_name || vsix.name || 'none')} v${escapeHtml(vsix.version || '?')}<br><span class="muted">${escapeHtml(String(vsix.command_count || 0))} commands · engine ${escapeHtml(vsix.engine || '?')}</span></div>`,
    `<div class="mini-card"><b>MCP Servers</b><br>${escapeHtml((mcp.servers || []).join(', ') || 'none configured')}<br><span class="muted">${escapeHtml(mcp.config || '')}</span></div>`,
    `<div class="mini-card"><b>Plugins</b><br>${escapeHtml(String(plugins.count || 0))} local plugin(s)<br><span class="muted">${escapeHtml((plugins.names || []).slice(0, 8).join(', ') || 'none')}</span></div>`,
    commands.length ? `<div class="mini-card"><b>Extension Commands</b><br><span class="muted">${escapeHtml(commands.slice(0, 12).map(c => c.command).join(', '))}${commands.length > 12 ? '…' : ''}</span></div>` : '',
  ].join('');
}

function renderSystemSnapshot(snap, error = '') {
  lastSystemSnapshot = snap || null;
  const summary = snap?.summary || {};
  $('systemSummary').textContent = [
    `${snap?.ok ? 'ready' : 'unavailable'} · psutil ${snap?.psutil_available ? 'yes' : 'no'}`,
    `ports: ${summary.listening_ports ?? '?'} · processes: ${summary.processes_total ?? '?'}`,
    `python ${summary.python || '?'}${summary.in_virtualenv ? ' (venv)' : ''} · ${summary.python_dependencies ?? 0} deps`,
    `node manifests: ${summary.node_manifests ?? 0} · vscode cmds: ${summary.vscode_commands ?? 0}`,
  ].join('\n');
  $('systemSummary').className = `status-box ${error ? 'bad' : snap?.ok ? 'ready' : 'warn'}`;
  renderSystemPorts(snap?.ports?.ports);
  renderSystemProcesses(snap?.processes?.processes);
  renderSystemEnvironment(snap?.environment);
  renderSystemPackages(snap?.packages);
  renderSystemExtensions(snap?.extensions);
  $('systemRaw').textContent = JSON.stringify(snap || { error }, null, 2);
  renderNextActionInspector();
}

async function refreshSystemSnapshot() {
  if (desktopLocalMode) {
    $('systemSummary').textContent = 'Local IDE Mode: system plane requires the BEAST gateway.';
    $('systemSummary').className = 'status-box warn';
    return;
  }
  const params = new URLSearchParams();
  if (workspaceRoot) params.set('root_path', workspaceRoot);
  const query = $('systemProcessQuery')?.value?.trim();
  if (query) params.set('process_query', query);
  params.set('process_limit', '40');
  params.set('port_limit', '80');
  try {
    const snap = await getJson(`/edgek/ide/system-snapshot?${params.toString()}`);
    renderSystemSnapshot(snap);
    getJson(`/edgek/ide/catalog?${workspaceRoot ? `root_path=${encodeURIComponent(workspaceRoot)}` : ''}`).then(renderSystemCatalog).catch(() => {});
    log(`system snapshot: ${snap?.summary?.listening_ports ?? 0} ports · ${snap?.summary?.processes_total ?? 0} processes`);
  } catch (error) {
    renderSystemSnapshot({ ok: false }, error.message || String(error));
    log(`system snapshot failed: ${error.message || error}`);
  }
}

async function refreshSystemPorts() {
  setDesktopPage('system');
  try {
    const data = await getJson('/edgek/ide/ports?limit=200');
    renderSystemPorts(data.ports);
    log(`ports: ${data.count} listening`);
  } catch (error) { log(`ports failed: ${error.message || error}`); }
  $('systemPortsPanel')?.scrollIntoView({ block: 'nearest' });
}

async function refreshSystemProcesses() {
  setDesktopPage('system');
  const params = new URLSearchParams();
  const query = $('systemProcessQuery')?.value?.trim();
  if (query) params.set('query', query);
  params.set('limit', '80');
  try {
    const data = await getJson(`/edgek/ide/processes?${params.toString()}`);
    renderSystemProcesses(data.processes);
    log(`processes: ${data.count}/${data.total}`);
  } catch (error) { log(`processes failed: ${error.message || error}`); }
  $('systemProcessPanel')?.scrollIntoView({ block: 'nearest' });
}

async function refreshSystemEnvironment() {
  setDesktopPage('system');
  const params = new URLSearchParams();
  if (workspaceRoot) params.set('root_path', workspaceRoot);
  try { renderSystemEnvironment(await getJson(`/edgek/ide/environment?${params.toString()}`)); } catch (error) { log(`environment failed: ${error.message || error}`); }
  $('systemEnvPanel')?.scrollIntoView({ block: 'nearest' });
}

async function refreshSystemPackages() {
  setDesktopPage('system');
  const params = new URLSearchParams();
  if (workspaceRoot) params.set('root_path', workspaceRoot);
  try { renderSystemPackages(await getJson(`/edgek/ide/packages?${params.toString()}`)); } catch (error) { log(`packages failed: ${error.message || error}`); }
  $('systemPackagePanel')?.scrollIntoView({ block: 'nearest' });
}

async function refreshSystemExtensions() {
  setDesktopPage('system');
  const params = new URLSearchParams();
  if (workspaceRoot) params.set('root_path', workspaceRoot);
  try { renderSystemExtensions(await getJson(`/edgek/ide/extensions?${params.toString()}`)); } catch (error) { log(`extensions failed: ${error.message || error}`); }
  $('systemExtPanel')?.scrollIntoView({ block: 'nearest' });
}

async function killSystemProcess(pid, name = '') {
  if (!pid) { setDesktopPage('system'); log('kill: pick a process from the System plane.'); return; }
  if (desktopLocalMode) { log('kill blocked: gateway unavailable.'); return; }
  const signal = systemKillSignal();
  if (!window.confirm(`Send SIG${signal} to pid ${pid}${name ? ` (${name})` : ''}?\nThis is a governed, evidence-logged action.`)) {
    log(`kill cancelled for pid ${pid}`);
    return;
  }
  try {
    const result = await postJson('/edgek/ide/system/kill', {
      root_path: workspaceRoot || undefined,
      pid: Number(pid),
      signal,
      approved: true,
      operator_override: `Approved from BEAST Desktop IDE System plane (SIG${signal})`,
    });
    if (result.ok) {
      log(`killed pid ${pid}: ${result.status} · receipt ${(result.evidence_receipt || {}).receipt_id || 'n/a'}`);
    } else {
      const reason = result.error || result.reason || 'unknown';
      log(`kill refused for pid ${pid}: ${reason}`);
      window.alert(`Kill not performed: ${reason}${result.protected_reason ? ` (${result.protected_reason})` : ''}`);
    }
  } catch (error) {
    log(`kill failed for pid ${pid}: ${error.message || error}`);
  }
  await refreshSystemProcesses();
}

async function freeSystemPort(port) {
  if (desktopLocalMode) { log('free-port blocked: gateway unavailable.'); return; }
  const value = Number(port || $('systemFreePort')?.value);
  if (!value) { setDesktopPage('system'); log('free-port: enter a port number.'); return; }
  const signal = systemKillSignal();
  if (!window.confirm(`Free port ${value} by sending SIG${signal} to its owner process?\nThis is a governed, evidence-logged action.`)) {
    log(`free-port cancelled for ${value}`);
    return;
  }
  try {
    const result = await postJson('/edgek/ide/ports/free', {
      root_path: workspaceRoot || undefined,
      port: value,
      signal,
      approved: true,
      operator_override: `Approved from BEAST Desktop IDE System plane (free port ${value})`,
    });
    if (result.ok) {
      log(`freed port ${value}: ${result.owner_count} owner(s) terminated.`);
    } else {
      const reason = result.error || (result.results || []).map(r => r.error || r.reason).filter(Boolean).join(', ') || 'unknown';
      log(`free-port ${value} not completed: ${reason}`);
      window.alert(`Free port ${value} not completed: ${reason}`);
    }
  } catch (error) {
    log(`free-port ${value} failed: ${error.message || error}`);
  }
  await refreshSystemPorts();
}

function copySystemReport() {
  const text = $('systemRaw')?.textContent || JSON.stringify(lastSystemSnapshot || {}, null, 2);
  navigator.clipboard.writeText(text).then(() => log('system report copied.')).catch(() => log('copy failed.'));
}

let lastCatalog = null;

function renderSystemCatalog(cat) {
  lastCatalog = cat || null;
  const mcp = Array.isArray(cat?.mcp_servers) ? cat.mcp_servers : [];
  const tools = Array.isArray(cat?.tools) ? cat.tools : [];
  const ext = Array.isArray(cat?.vscode_extensions) ? cat.vscode_extensions : [];
  const mcpCards = mcp.map((s, i) => {
    const runner = s.runner_available ? `<span class="state-chip ready">${escapeHtml(s.runner || '')} ready</span>` : `<span class="state-chip warn">${escapeHtml(s.runner || 'runner')} missing</span>`;
    return `<div class="mini-card"><b>MCP · ${escapeHtml(s.name)}</b> <span class="state-chip ${s.risk_class === 'high' ? 'bad' : s.risk_class === 'low' ? 'ready' : 'warn'}">${escapeHtml(s.risk_class || '')}</span> ${runner}<br><span class="muted">${escapeHtml(s.description || '')}</span><br><code>${escapeHtml(s.command + ' ' + (s.args || []).join(' '))}</code><br><button class="ghost-button" data-copy-mcp="${i}">Copy config</button> <button class="ghost-button" data-register-mcp="${i}">Register with BEAST</button></div>`;
  });
  const toolCards = tools.map(t => `<div class="mini-card ${t.installed ? 'ready' : 'warn'}"><b>Tool · ${escapeHtml(t.name)}</b> ${t.installed ? '<span class="state-chip ready">installed</span>' : '<span class="state-chip warn">missing</span>'}<br><span class="muted">${escapeHtml(t.description || '')}</span><br>${t.installed ? '' : `<code>${escapeHtml(t.install_hint || '')}</code>`}</div>`);
  const extCards = ext.map(e => `<div class="mini-card"><b>Ext · ${escapeHtml(e.name)}</b><br><span class="muted">${escapeHtml(e.description || '')}</span><br><code>${escapeHtml(e.id)}</code></div>`);
  const cards = [...mcpCards, ...toolCards, ...extCards];
  $('systemCatalogPanel').innerHTML = cards.length ? cards.join('') : emptyCard('Catalog unavailable.', 'Refresh the catalog.');
}

async function refreshSystemCatalog() {
  setDesktopPage('system');
  const params = new URLSearchParams();
  if (workspaceRoot) params.set('root_path', workspaceRoot);
  try {
    const cat = await getJson(`/edgek/ide/catalog?${params.toString()}`);
    renderSystemCatalog(cat);
    log(`catalog: ${cat?.summary?.mcp_servers ?? 0} MCP · ${cat?.summary?.tools_installed ?? 0}/${cat?.summary?.tools ?? 0} tools installed`);
  } catch (error) { log(`catalog failed: ${error.message || error}`); }
  $('systemCatalogPanel')?.scrollIntoView({ block: 'nearest' });
}

function copyCatalogMcp(index) {
  const server = (lastCatalog?.mcp_servers || [])[Number(index)];
  if (!server) return;
  const config = JSON.stringify(server.mcp_config || {}, null, 2);
  navigator.clipboard.writeText(config).then(() => log(`copied MCP config for ${server.name}`)).catch(() => log('copy failed.'));
}

async function registerCatalogMcp(index) {
  const server = (lastCatalog?.mcp_servers || [])[Number(index)];
  if (!server || desktopLocalMode) { log('register blocked.'); return; }
  if (!window.confirm(`Register MCP server "${server.name}" (class ${server.server_class}) with the BEAST broker?`)) return;
  try {
    const result = await postJson('/edgek/mcp/servers', {
      name: `catalog-${server.id}`,
      server_class: server.server_class,
      description: server.description,
      metadata: { catalog_id: server.id, command: server.command, args: server.args },
    });
    log(result?.ok === false ? `register failed: ${result.error || 'policy rejected server_class'}` : `registered MCP server: ${server.name}`);
  } catch (error) {
    log(`register failed for ${server.name}: ${error.message || error}`);
  }
}

async function refreshMcpOps() {
  setDesktopPage('tooling');
  if (desktopLocalMode) {
    $('mcpOpsPanel').innerHTML = emptyCard('MCP operations need the gateway.', 'Restart the gateway, then refresh MCP Ops.');
    return;
  }
  try {
    const [state, servers, pins, approvals, audit, executions] = await Promise.all([
      getJson('/edgek/mcp/state'),
      getJson('/edgek/mcp/servers'),
      getJson('/edgek/mcp/schema-pins?limit=50'),
      getJson('/edgek/mcp/approvals?limit=20'),
      getJson('/edgek/mcp/audit?limit=20'),
      getJson('/edgek/mcp/executions?limit=20'),
    ]);
    const approvalRows = (approvals.approvals || []).slice(0, 8).map(item => `<div class="mini-card warn"><b>${escapeHtml(item.request_id || item.id || 'approval')}</b><br>${escapeHtml(item.status || 'pending')} · ${escapeHtml(item.tool || item.server || '')}</div>`).join('');
    $('mcpOpsPanel').innerHTML = [
      `<div class="mini-card ready"><b>MCP Broker</b><br>${escapeHtml(JSON.stringify(state.stats || state, null, 0).slice(0, 180))}</div>`,
      `<div class="mini-card"><b>Servers</b><br>${escapeHtml((servers.servers || []).length)} registered · schema pins ${escapeHtml((pins.schema_pins || []).length)}</div>`,
      approvalRows || emptyCard('No pending approvals.', 'MCP approvals will appear here before execution.'),
    ].join('');
    $('toolingRaw').textContent = JSON.stringify({ state, servers, pins, approvals, audit, executions }, null, 2);
    log(`MCP ops: ${(servers.servers || []).length} server(s), ${(approvals.approvals || []).length} approval(s).`);
  } catch (error) {
    $('mcpOpsPanel').innerHTML = `<div class="mini-card bad">MCP ops failed: ${escapeHtml(error.message || error)}</div>`;
    log(`MCP ops failed: ${error.message || error}`);
  }
}

async function resolveMcpApproval(decision) {
  const requestId = window.prompt(`${decision === 'approve' ? 'Approve' : 'Deny'} MCP request id`);
  if (!requestId) return;
  const reason = window.prompt('Operator reason', `${decision} from BEAST Desktop Tooling Plane`) || '';
  try {
    const result = await postJson(`/edgek/mcp/approvals/${encodeURIComponent(requestId)}/${decision}`, { reason, operator: 'beast_desktop' });
    $('toolingRaw').textContent = JSON.stringify(result, null, 2);
    log(`MCP approval ${decision}: ${requestId}`);
    await refreshMcpOps();
  } catch (error) {
    $('mcpOpsPanel').innerHTML = `<div class="mini-card bad">MCP ${decision} failed: ${escapeHtml(error.message || error)}</div>`;
  }
}

async function refreshPluginOps() {
  setDesktopPage('tooling');
  if (desktopLocalMode) {
    $('pluginOpsPanel').innerHTML = emptyCard('Plugin operations need the gateway.', 'Restart the gateway to validate or install plugin manifests.');
    return;
  }
  try {
    const plugins = await getJson('/edgek/plugins');
    const rows = (plugins.plugins || []).slice(0, 10).map(item => `<div class="mini-card ready"><b>${escapeHtml(item.name || item.id || 'plugin')}</b><br>${escapeHtml(item.risk_class || item.status || 'installed')} · ${escapeHtml((item.tools || []).length)} tool(s)</div>`).join('');
    $('pluginOpsPanel').innerHTML = rows || emptyCard('No installed plugin manifests.', 'Validate a manifest before installing anything.');
    $('toolingRaw').textContent = JSON.stringify(plugins, null, 2);
    log(`plugin ops: ${(plugins.plugins || []).length} plugin(s).`);
  } catch (error) {
    $('pluginOpsPanel').innerHTML = `<div class="mini-card bad">Plugin ops failed: ${escapeHtml(error.message || error)}</div>`;
    log(`Plugin ops failed: ${error.message || error}`);
  }
}

async function validatePluginManifest() {
  const raw = window.prompt('Paste plugin manifest JSON to validate');
  if (!raw) return;
  let manifest;
  try {
    manifest = JSON.parse(raw);
  } catch (error) {
    $('pluginOpsPanel').innerHTML = `<div class="mini-card bad">Invalid JSON: ${escapeHtml(error.message || error)}</div>`;
    return;
  }
  try {
    const result = await postJson('/edgek/plugins/manifest/validate', manifest);
    $('pluginOpsPanel').innerHTML = `<div class="mini-card ${result.valid === false ? 'bad' : 'ready'}"><b>Manifest validation</b><br>${escapeHtml(result.valid === false ? 'failed' : 'passed')} · ${escapeHtml((result.errors || []).join('; ') || 'schema accepted')}</div>`;
    $('toolingRaw').textContent = JSON.stringify(result, null, 2);
  } catch (error) {
    $('pluginOpsPanel').innerHTML = `<div class="mini-card bad">Validation failed: ${escapeHtml(error.message || error)}</div>`;
  }
}

function copyToolingReport() {
  const report = {
    summary: $('toolingSummary')?.textContent || '',
    snapshot: lastToolingSnapshot,
    benchmarkVerdict: lastBenchmarkVerdict,
    raw: $('toolingRaw')?.textContent || '',
    copied_at: new Date().toISOString(),
  };
  navigator.clipboard?.writeText(JSON.stringify(report, null, 2));
  log('tooling report copied.');
}

async function runBenchmarkGradingDaemon() {
  setDesktopPage('tooling');
  const packetDir = workspaceRoot
    ? `${workspaceRoot}/benchmarks/results/full_blind_test_packet`
    : '/home/byron/EdgeK-BEAST/benchmarks/results/full_blind_test_packet';
  try {
    const result = await postJson('/edgek/benchmarks/public-grading-daemon', { packet_dir: packetDir });
    renderBenchmarkVerdict(result);
    $('toolingRaw').textContent = JSON.stringify(result, null, 2);
    log(`benchmark grading daemon: ${result.claim_status || 'unknown'} / structural ${result.structural_claim_status || 'unknown'}`);
  } catch (error) {
    renderBenchmarkVerdict(null, error.message || String(error));
    $('toolingRaw').textContent = JSON.stringify({ error: error.message || String(error), packet_dir: packetDir }, null, 2);
    log(`benchmark grading daemon failed: ${error.message || error}`);
  }
}

function copyBenchmarkVerdict() {
  if (!lastBenchmarkVerdict) {
    log('No benchmark verdict to copy.');
    return;
  }
  navigator.clipboard?.writeText(JSON.stringify(lastBenchmarkVerdict, null, 2));
  log('benchmark verdict copied.');
}

async function createAgentSession() {
  const objective = window.prompt('Agent objective', currentFile ? `Work on ${currentFile}` : 'BEAST desktop agent mission');
  if (!objective) return;
  if (desktopLocalMode) {
    appendLocalAgentTurn('operator_prompt', objective, { local_queued: true });
    $('agentPromptText').value = objective;
    log('agent session queued locally: gateway unavailable.');
    return;
  }
  const result = await postJson('/edgek/ide/agent-sessions/create', {
    root_path: workspaceRoot,
    objective,
    mode: 'architect',
    provider: selectedProvider,
    model: selectedModel,
    files: currentFile ? [currentFile] : [],
    budget: { tokens: 120000, seconds: 3600, cost_usd: 0 },
  });
  currentAgentSession = result.session || null;
  renderAgentDetail(currentAgentSession);
  log(`agent session created: ${currentAgentSession?.session_id || JSON.stringify(result).slice(0, 180)}`);
  await refreshSnapshot();
}

async function createWorktreeMission() {
  const objective = window.prompt('Worktree mission objective', currentFile ? `Safely change ${currentFile}` : 'BEAST isolated desktop mission');
  if (!objective) return;
  const result = await postJson('/edgek/ide/worktree-mission/create', {
    root_path: workspaceRoot,
    objective,
    provider: selectedProvider,
    model: selectedModel,
    mode: 'implementer',
    files: currentFile ? [currentFile] : [],
    risk: 'medium',
  });
  currentWorktreeTask = result.task || null;
  log(`worktree mission: ${currentWorktreeTask?.task_id || JSON.stringify(result).slice(0, 180)}`);
  await refreshSnapshot();
}

function setSourcePlanStatus(text, state) {
  const node = $('sourcePlanStatus');
  node.textContent = text;
  node.className = `status-box ${state || 'muted'}`;
  updateStatusChips();
  renderSourcePlanChecklist();
  renderNextActionInspector();
}

async function refreshSourcePlanLifecycle() {
  if (!currentSourcePlan) {
    currentSourcePlanLifecycle = null;
    $('sourcePlanLifecycle').innerHTML = emptyCard('No SourcePlan lifecycle loaded.', 'Draft from the editor or a selection first.');
    $('sourcePlanOperations').innerHTML = emptyCard('No SourcePlan operations loaded.', 'Operations appear after a draft is compiled.');
    $('sourcePlanActionContract').textContent = 'No contract loaded.';
    $('sourcePlanActionContract').className = 'status-box muted';
    $('sourcePlanOperationLedger').innerHTML = emptyCard('No operation ledger loaded.', 'Lifecycle refresh will show selected, stale, and rollback state.');
    renderSourcePlanChecklist();
    renderNextActionInspector();
    return;
  }
  try {
    const lifecycle = await postJson('/edgek/ide/sourceplan/lifecycle', {
      root_path: workspaceRoot,
      plan: currentSourcePlan,
    });
    currentSourcePlanLifecycle = lifecycle;
    const stages = lifecycle.stages || [];
    renderList($('sourcePlanLifecycle'), stages, item => {
      const state = item.ok ? 'ready' : 'warn';
      return `<div class="status-box ${state}"><b>${escapeHtml(item.stage || 'stage')}</b><br>${escapeHtml(item.detail || '')}</div>`;
    });
    const operations = lifecycle.preview?.operations || [];
    renderList($('sourcePlanOperations'), operations, item => {
      const opId = escapeHtml(item.op_id || '');
      if (!selectedSourcePlanOpId && item.op_id) selectedSourcePlanOpId = String(item.op_id);
      const selectedSet = new Set((currentSourcePlan?.selected_operations || []).map(String));
      const selected = selectedSet.size ? selectedSet.has(item.op_id || '') : item.selected !== false;
      const active = selectedSourcePlanOpId === String(item.op_id || '') ? ' active' : '';
      const selectedLabel = selected ? 'selected' : 'skipped';
      const stale = item.stale_reason ? ` · stale: ${escapeHtml(item.stale_reason)}` : '';
      const path = escapeHtml(item.path || '');
      return [
        `<button class="file-item ${selected ? 'active' : ''}${active}" data-sourceplan-op="${opId}">`,
        `<b>${escapeHtml(selectedLabel)}</b> · ${escapeHtml(item.op || 'op')} · ${path}`,
        `<br><span class="muted">${escapeHtml(item.description || '')}${stale}</span>`,
        '</button>',
      ].join('');
    });
    renderSourcePlanActionContract(lifecycle.action_contract || {});
    renderSourcePlanOperationLedger(lifecycle.operation_ledger || {});
    renderRollbackPreview(lifecycle);
    renderApplyTimeline(lastApplyResult);
    renderSourcePlanChecklist();
    const risk = lifecycle.risk ? ` · risk ${lifecycle.risk}` : '';
    const receipts = lifecycle.evidence?.match_count || 0;
    setSourcePlanStatus(
      `Plan ${lifecycle.plan_id || 'draft'}${risk}\nOps ${lifecycle.operation_count} · selected ${lifecycle.selected_count} · stale ${lifecycle.stale_count}\nEvidence ${receipts} · can apply ${lifecycle.can_apply ? 'yes' : 'no'}`,
      lifecycle.can_apply ? 'ready' : lifecycle.errors?.length ? 'bad' : 'warn',
    );
  } catch (error) {
    $('sourcePlanLifecycle').innerHTML = `<div class="mini-card muted">${escapeHtml(error.message || error)}</div>`;
    renderNextActionInspector();
  }
}

function renderSourcePlanActionContract(contract) {
  if (!contract || !Object.keys(contract).length) {
    $('sourcePlanActionContract').textContent = 'No contract loaded.';
    $('sourcePlanActionContract').className = 'status-box muted';
    return;
  }
  const lines = [
    `${contract.status || 'draft'} · risk ${contract.risk || 'unknown'}`,
    contract.intent || '',
    `approval: ${contract.approval_required ? 'required' : 'not required'} · rollback: ${contract.rollback_required ? 'required' : 'not required'}`,
    `files: ${(contract.files_allowed || []).slice(0, 4).join(', ') || 'none'}`,
    `blocked: ${(contract.blocked_actions || []).slice(0, 4).join(', ')}`,
  ].filter(Boolean);
  $('sourcePlanActionContract').textContent = lines.join('\n');
  $('sourcePlanActionContract').className = contract.approval_required ? 'status-box warn' : 'status-box ready';
}

function renderSourcePlanOperationLedger(ledger) {
  const rows = ledger?.operations || [];
  renderList($('sourcePlanOperationLedger'), rows, item => {
    const state = item.status === 'stale' ? 'bad' : item.selected ? 'ready' : 'muted';
    return [
      `<div class="mini-card ${state}">`,
      `<b>${escapeHtml(item.operation_id || 'op')}</b> · ${escapeHtml(item.status || 'pending')} · ${escapeHtml(item.operation || 'edit')}`,
      `<br><span>${escapeHtml(item.path || '')}</span>`,
      item.stale_reason ? `<br><span class="muted">stale: ${escapeHtml(item.stale_reason)}</span>` : '',
      `<br><span class="muted">before ${escapeHtml(String(item.before_sha256 || '').slice(0, 18))} · after ${escapeHtml(String(item.after_sha256 || '').slice(0, 18))}</span>`,
      `<br><span class="muted">verify ${escapeHtml(item.verification_status || 'pending')} · rollback ${item.rollback_required ? 'required' : 'optional'} · evidence ${escapeHtml(item.evidence_status || 'pending')}</span>`,
      '</div>',
    ].join('');
  });
  if (ledger?.ledger_hash) {
    log(`SourcePlan operation ledger: ${ledger.operation_count || 0} ops · ${ledger.ledger_hash.slice(0, 24)}`);
  }
}

async function chooseReceiptsForAction(action = 'sourceplan.apply') {
  if (desktopLocalMode) {
    $('receiptChooser').innerHTML = '<div class="mini-card muted">Receipt chooser needs the BEAST gateway.</div>';
    return;
  }
  const params = new URLSearchParams();
  if (workspaceRoot) params.set('root_path', workspaceRoot);
  params.set('action', action);
  params.set('limit', '80');
  const key = $('evidenceKey')?.value?.trim() || currentSourcePlan?.plan_id || currentAgentSession?.session_id || currentWorktreeTask?.task_id || '';
  if (key) params.set('key', key);
  const payload = await getJson(`/edgek/ide/receipts/chooser?${params.toString()}`);
  renderReceiptChooser(payload.receipts || []);
  log(`receipt chooser: ${payload.receipt_count || 0} candidate(s) for ${action}`);
  setDesktopPage('evidence');
}

function renderReceiptChooser(receipts) {
  renderList($('receiptChooser'), receipts || [], item => [
    '<div class="mini-card">',
    `<b>${escapeHtml(item.receipt_id || 'receipt')}</b> · ${escapeHtml(item.status || 'recorded')}`,
    `<br><span>${escapeHtml(item.source || '')} · ${escapeHtml(item.artifact_type || '')}</span>`,
    item.summary ? `<br><span class="muted">${escapeHtml(item.summary)}</span>` : '',
    item.resolved_command ? `<br><code>${escapeHtml(item.resolved_command)}</code>` : '',
    '</div>',
  ].join(''));
}

async function exportMissionRunbook() {
  if (desktopLocalMode) {
    log('runbook export blocked: gateway unavailable.');
    return;
  }
  const result = await postJson('/edgek/ide/mission-runbook/export', {
    root_path: workspaceRoot,
    active_file: currentFile,
    objective: currentSourcePlan?.objective || (currentFile ? `Work on ${currentFile}` : 'BEAST desktop mission'),
    plan: currentSourcePlan || {},
  });
  lastMissionRunbook = result;
  const preview = result.markdown_preview || JSON.stringify(result.manifest || result, null, 2);
  $('diffPreview').textContent = preview;
  $('diffMeta').textContent = `Mission runbook ${result.runbook_id || ''}`;
  document.querySelector('[data-editor-tab="diff"]').click();
  log(`mission runbook exported: ${result.paths?.markdown || result.runbook_id}`);
  await refreshMissionTimeline();
  await searchEvidenceDrawer('query');
}

async function copySourceRunbook() {
  const text = lastMissionRunbook?.markdown_preview || $('diffPreview').textContent || '';
  if (!text.trim()) {
    log('runbook copy blocked: no runbook preview available.');
    return;
  }
  await navigator.clipboard.writeText(text);
  log('runbook preview copied.');
}

async function verifyMissionRunbook() {
  if (desktopLocalMode) {
    log('runbook verify blocked: gateway unavailable.');
    return;
  }
  const result = await postJson('/edgek/ide/mission-runbook/verify', {
    root_path: workspaceRoot,
    runbook_id: lastMissionRunbook?.runbook_id || '',
  });
  $('diffPreview').textContent = JSON.stringify(result, null, 2);
  $('diffMeta').textContent = `Runbook verify ${result.runbook_id || ''}`;
  document.querySelector('[data-editor-tab="diff"]').click();
  log(`runbook verify: ${result.status || result.error || 'unknown'}`);
  await searchEvidenceDrawer('query');
}

async function createHandoffPackage() {
  if (desktopLocalMode) {
    log('handoff package blocked: gateway unavailable.');
    return;
  }
  if (!currentSourcePlan) {
    setSourcePlanStatus('Create a SourcePlan before packaging a handoff.', 'warn');
    return;
  }
  const result = await postJson('/edgek/ide/sourceplan/handoff-package', {
    root_path: workspaceRoot,
    plan: currentSourcePlan,
  });
  $('diffPreview').textContent = [
    `# Handoff Package: ${result.handoff_id || 'unknown'}`,
    `# Status: ${result.status || result.error || 'unknown'}`,
    `# Direct apply allowed: ${result.direct_apply_allowed ? 'yes' : 'no'}`,
    '',
    result.patch_preview || JSON.stringify(result, null, 2),
  ].join('\n');
  $('diffMeta').textContent = `Handoff ${result.handoff_id || ''}`;
  document.querySelector('[data-editor-tab="diff"]').click();
  setSourcePlanStatus(`Handoff ${result.status || 'created'}: ${result.handoff_id || ''}\nOps ${(result.operations || []).length} · blocked ${(result.blocked || []).length}`, result.ok ? 'ready' : 'warn');
  log(`handoff package: ${result.handoff_id || result.error}`);
  await searchEvidenceDrawer('query');
}

async function proposeLearning() {
  if (desktopLocalMode) {
    log('learning proposal blocked: gateway unavailable.');
    return;
  }
  const note = window.prompt('Learning proposal note', currentSourcePlan?.objective || 'Promote this governed IDE workflow.');
  if (note === null) return;
  const result = await postJson('/edgek/ide/learning-queue/propose', {
    root_path: workspaceRoot,
    plan: currentSourcePlan || {},
    note,
  });
  $('diffPreview').textContent = JSON.stringify(result, null, 2);
  $('diffMeta').textContent = `Learning proposal ${result.proposal_id || ''}`;
  document.querySelector('[data-editor-tab="diff"]').click();
  log(`learning proposal: ${result.status || 'created'} · score ${result.score ?? 'n/a'}`);
  await searchEvidenceDrawer('query');
}

async function checkReleaseReadiness() {
  let result = null;
  let source = 'gateway';
  if (!desktopLocalMode) {
    try {
      result = await postJson('/edgek/ide/release-readiness/check', {
        root_path: workspaceRoot,
      });
    } catch (error) {
      log(`Gateway readiness route unavailable; running local desktop checks: ${error.message || error}`);
    }
  }
  if (!result && window.beastDesktop?.releaseReadiness) {
    source = 'local';
    result = await window.beastDesktop.releaseReadiness(workspaceRoot);
  }
  if (!result) {
    $('releaseReadiness').textContent = 'Readiness checks unavailable. Restart the desktop app from the current source tree and try again.';
    $('releaseReadiness').className = 'status-box warn';
    return;
  }
  const failed = (result.checks || []).filter(item => !item.passed);
  const smoke = result.smoke || {};
  const launchSmoke = result.launch_smoke || {};
  $('releaseReadiness').textContent = [
    `${result.status || 'unknown'} · ${result.summary?.passed || 0}/${result.summary?.checks || 0} checks passed · ${source}`,
    `smoke: ${smoke.ok ? 'passed' : smoke.ran ? 'failed' : 'not run'}`,
    `launch: ${launchSmoke.ok ? 'passed' : launchSmoke.ran ? 'failed' : 'not run'}`,
    ...failed.slice(0, 6).map(item => `${item.check}: failed`),
  ].join('\n');
  $('releaseReadiness').className = result.ok ? 'status-box ready' : 'status-box warn';
  $('diffPreview').textContent = JSON.stringify(result, null, 2);
  $('diffMeta').textContent = 'Desktop IDE release readiness';
  document.querySelector('[data-editor-tab="diff"]').click();
  log(`release readiness: ${result.status || 'unknown'}`);
  await searchEvidenceDrawer('query');
}

function toggleSourcePlanOperation(opId) {
  if (!currentSourcePlan || !opId) return;
  selectedSourcePlanOpId = opId;
  const operations = Array.isArray(currentSourcePlan.operations) ? currentSourcePlan.operations : [];
  const allIds = operations.map((item, index) => String(item.op_id || `op_${index + 1}`));
  const selected = new Set(Array.isArray(currentSourcePlan.selected_operations)
    ? currentSourcePlan.selected_operations.map(String)
    : operations.filter(item => item.selected !== false).map((item, index) => String(item.op_id || `op_${index + 1}`)));
  if (selected.has(opId)) {
    selected.delete(opId);
  } else if (allIds.includes(opId)) {
    selected.add(opId);
  }
  currentSourcePlan.selected_operations = allIds.filter(id => selected.has(id));
  log(`SourcePlan operation ${selected.has(opId) ? 'selected' : 'skipped'}: ${opId}`);
  refreshSourcePlanLifecycle();
}

function selectedSourcePlanOperation() {
  const operations = Array.isArray(currentSourcePlan?.operations) ? currentSourcePlan.operations : [];
  if (!operations.length) return null;
  return operations.find((item, index) => String(item.op_id || `op_${index + 1}`) === String(selectedSourcePlanOpId)) || operations[0];
}

function editSelectedSourcePlanOperation() {
  const op = selectedSourcePlanOperation();
  if (!op) {
    setSourcePlanStatus('No SourcePlan operation selected to edit.', 'warn');
    return;
  }
  const description = window.prompt('Operation description', op.description || op.op || '');
  if (description === null) return;
  op.description = description;
  const editableKey = ['new', 'new_text', 'content'].find(key => typeof op[key] === 'string');
  if (editableKey && window.confirm(`Edit operation ${editableKey} text?`)) {
    const next = window.prompt(`Operation ${editableKey}`, op[editableKey]);
    if (next !== null) op[editableKey] = next;
  }
  setSourcePlanStatus(`Edited SourcePlan operation ${op.op_id || selectedSourcePlanOpId}. Re-verify before apply.`, 'warn');
  refreshSourcePlanLifecycle();
}

function moveSelectedSourcePlanOperation(direction = 0) {
  const operations = Array.isArray(currentSourcePlan?.operations) ? currentSourcePlan.operations : [];
  if (!operations.length || !selectedSourcePlanOpId) {
    setSourcePlanStatus('Select a SourcePlan operation before reordering.', 'warn');
    return;
  }
  const index = operations.findIndex((item, offset) => String(item.op_id || `op_${offset + 1}`) === String(selectedSourcePlanOpId));
  const nextIndex = index + direction;
  if (index < 0 || nextIndex < 0 || nextIndex >= operations.length) return;
  [operations[index], operations[nextIndex]] = [operations[nextIndex], operations[index]];
  currentSourcePlan.operations = operations;
  setSourcePlanStatus(`Moved operation ${selectedSourcePlanOpId} ${direction < 0 ? 'up' : 'down'}. Re-verify before apply.`, 'warn');
  refreshSourcePlanLifecycle();
}

function renderRollbackPreview(lifecycle = currentSourcePlanLifecycle || {}) {
  const node = $('sourcePlanRollbackPreview');
  if (!node) return;
  const rollback = lifecycle.rollback_preview || lifecycle.rollback || currentSourcePlan?.rollback || currentSourcePlan?.rollback_plan || {};
  const operations = Array.isArray(rollback.operations) ? rollback.operations : [];
  const lines = [
    rollback.status || (operations.length ? 'rollback ready after apply' : 'rollback will be generated on apply'),
    rollback.path ? `snapshot: ${rollback.path}` : '',
    operations.length ? `${operations.length} rollback operation(s)` : '',
    ...(operations.slice(0, 4).map(item => `${item.op || 'restore'} · ${item.path || item.file || ''}`)),
  ].filter(Boolean);
  node.textContent = lines.join('\n') || 'Rollback preview appears after a lifecycle refresh or apply.';
  node.className = operations.length || rollback.path ? 'status-box ready' : 'status-box muted';
}

function renderApplyTimeline(result = lastApplyResult) {
  const node = $('sourcePlanApplyTimeline');
  if (!node) return;
  if (!result) {
    node.innerHTML = emptyCard('No apply result timeline yet.', 'Verify and apply a SourcePlan to see evidence and rollback status here.');
    return;
  }
  const rows = [
    { step: 'verify', ok: result.ok !== false, detail: result.verification || result.status || 'completed' },
    { step: 'apply', ok: result.ok !== false, detail: (result.applied || []).join(', ') || result.error || 'completed' },
    { step: 'rollback', ok: Boolean(result.rollback || result.rollback_snapshot || result.rollback_receipt), detail: result.rollback_snapshot || result.rollback_receipt?.receipt_id || 'created by SourcePlan apply path' },
    { step: 'evidence', ok: Boolean(result.evidence_receipt || result.receipt || result.evidence), detail: result.evidence_receipt?.receipt_id || result.receipt?.receipt_id || 'evidence captured' },
  ];
  renderList(node, rows, item => `<div class="status-box ${item.ok ? 'ready' : 'warn'}"><b>${escapeHtml(item.step)}</b><br>${escapeHtml(item.detail || '')}</div>`);
}

function setSourcePlanOperationSelection(mode = 'all') {
  if (!currentSourcePlan) {
    setSourcePlanStatus('No SourcePlan draft loaded for operation selection.', 'warn');
    return;
  }
  const operations = Array.isArray(currentSourcePlan.operations) ? currentSourcePlan.operations : [];
  const ids = operations.map((item, index) => String(item.op_id || `op_${index + 1}`));
  currentSourcePlan.selected_operations = mode === 'none' ? [] : ids;
  operations.forEach((item, index) => {
    item.selected = mode !== 'none';
    item.op_id = item.op_id || `op_${index + 1}`;
  });
  setSourcePlanStatus(`${mode === 'none' ? 'No' : 'All'} SourcePlan operations selected (${currentSourcePlan.selected_operations.length}/${ids.length}).`, mode === 'none' ? 'warn' : 'ready');
  refreshSourcePlanLifecycle();
}

async function reloadBaseForSourcePlan() {
  if (!currentFile) {
    setSourcePlanStatus('No active file to reload.', 'warn');
    return;
  }
  const hadPlan = Boolean(currentSourcePlan);
  clearSourcePlan();
  await reloadActiveFileFromDisk(true);
  setSourcePlanStatus(hadPlan ? 'Reloaded file and cleared stale SourcePlan. Re-draft from the current buffer.' : 'Reloaded file from disk.', 'warn');
}

async function rebaseSourcePlanAgainstDisk() {
  if (!currentFile) {
    setSourcePlanStatus('No active file to rebase.', 'warn');
    return;
  }
  const staged = getEditorValue();
  const payload = window.beastDesktop.readFile
    ? await window.beastDesktop.readFile(workspaceRoot, currentFile, 1000000)
    : await getJson(`/edgek/workspace/file?${new URLSearchParams({ root_path: workspaceRoot, path: currentFile, max_chars: '1000000' }).toString()}`);
  if (payload.ok === false) {
    setSourcePlanStatus(`Rebase failed: ${payload.error || 'could not read current file'}`, 'bad');
    return;
  }
  const disk = String(payload.text || payload.content || payload.preview || '');
  originalText = disk;
  fileOriginals.set(currentFile, disk);
  setEditorValue(staged);
  if (staged !== disk) {
    dirtyFiles.add(currentFile);
    persistDirtyBuffer(currentFile);
  } else {
    dirtyFiles.delete(currentFile);
    clearPersistedBuffer(currentFile);
  }
  setSourcePlanStatus('Reloaded disk base while preserving staged buffer. Re-drafting SourcePlan against current file.', 'warn');
  await sourcePlanDraft();
}

async function sourcePlanDraft() {
  if (desktopLocalMode) {
    diffCurrentEdit();
    document.querySelector('[data-editor-tab="diff"]').click();
    setSourcePlanStatus('Local IDE Mode: diff preview is ready. Start the gateway to compile this buffer into governed SourcePlan operations.', 'warn');
    log('SourcePlan draft deferred: gateway unavailable; local diff preview remains available.');
    return;
  }
  if (!currentFile) {
    setSourcePlanStatus('Select a file before drafting SourcePlan.', 'warn');
    log('SourcePlan draft blocked: no file selected.');
    return;
  }
  const next = getEditorValue();
  if (next === originalText) {
    setSourcePlanStatus('No editor changes to compile.', 'warn');
    diffCurrentEdit();
    document.querySelector('[data-editor-tab="diff"]').click();
    return;
  }
  diffCurrentEdit();
  document.querySelector('[data-editor-tab="diff"]').click();
  setSourcePlanStatus('Compiling governed editor draft...', 'warn');
  const result = await postJson('/edgek/ide/sourceplan/from-editor', {
    root_path: workspaceRoot,
    path: currentFile,
    original_text: originalText,
    new_text: next,
    objective: `Apply governed desktop editor changes to ${currentFile}`,
    provider: selectedProvider,
    model: selectedModel,
    selected_hunks: diffHunks(originalText, next).filter(item => selectedDiffHunks.has(item.id)),
  });
  if (!result.ok) {
    currentSourcePlan = null;
    const reason = result.error || 'draft_failed';
    const stale = result.stale_context ? ' Stale file: reload before drafting.' : '';
    setSourcePlanStatus(`${reason}.${stale}`, result.stale_context ? 'bad' : 'warn');
    $('diffPreview').textContent = [
      `SourcePlan draft was not created for ${currentFile}.`,
      '',
      `Reason: ${reason}`,
      result.current_hash ? `Current hash: ${result.current_hash}` : '',
      result.editor_base_hash ? `Editor base hash: ${result.editor_base_hash}` : '',
    ].filter(Boolean).join('\n');
    log(`SourcePlan draft failed: ${reason}`);
    return;
  }
  currentSourcePlan = result.plan;
  const planId = currentSourcePlan?.plan_id || 'draft';
  const previewText = result.preview_text || (result.preview?.operations || [])
    .flatMap(item => item.diff_lines || [])
    .join('\n');
  $('diffPreview').textContent = [
    `# BEAST SourcePlan Draft: ${planId}`,
    `# Status: ${currentSourcePlan?.status || 'draft_requires_approval'}`,
    `# Apply path: approval -> verification -> rollback -> evidence closure`,
    '',
    previewText || 'No diff text returned.',
  ].join('\n');
  setSourcePlanStatus(`Draft ready: ${planId}\n${currentFile}\nSelected operations: ${(currentSourcePlan?.selected_operations || []).length}`, 'ready');
  log(`SourcePlan draft ready: ${planId}`);
  await refreshSourcePlanLifecycle();
}

async function selectAgentSession(sessionId) {
  const params = new URLSearchParams();
  if (workspaceRoot) params.set('root_path', workspaceRoot);
  const result = await getJson(`/edgek/ide/agent-sessions/${encodeURIComponent(sessionId)}?${params.toString()}`);
  if (!result.ok) {
    log(`agent session lookup failed: ${result.error || sessionId}`);
    return;
  }
  currentAgentSession = result.session;
  $('agentOutputText').value = '';
  renderAgentDetail(currentAgentSession);
  renderAgentSessions(currentSnapshot?.agent_sessions?.sessions || [currentAgentSession]);
  saveWorkspaceState();
}

async function updateAgentSessionStatus(status) {
  if (!currentAgentSession?.session_id) {
    log('agent session control blocked: no session selected.');
    return;
  }
  const path = status === 'paused'
    ? '/edgek/ide/agent-sessions/pause'
    : status === 'active'
      ? '/edgek/ide/agent-sessions/resume'
      : '/edgek/ide/agent-sessions/cancel';
  const payload = {
    root_path: workspaceRoot,
    session_id: currentAgentSession.session_id,
    reason: status === 'cancelled' ? 'cancelled from BEAST Desktop IDE' : '',
  };
  const result = await postJson(path, payload);
  if (result.ok) {
    currentAgentSession = result.session;
    renderAgentDetail(currentAgentSession);
    log(`agent session ${currentAgentSession.session_id}: ${currentAgentSession.status}`);
  }
  await refreshSnapshot();
}

async function ensureAgentSessionForPrompt(prompt) {
  const pack = buildAgentContextPack(prompt);
  if (currentAgentSession?.session_id && !String(currentAgentSession.session_id).startsWith('local-')) {
    return currentAgentSession;
  }
  if (desktopLocalMode) {
    appendLocalAgentTurn('operator_prompt', pack.prompt, { local_queued: true, context_files: pack.files });
    return currentAgentSession;
  }
  const result = await postJson('/edgek/ide/agent-sessions/create', {
    root_path: workspaceRoot,
    objective: prompt.slice(0, 180) || (currentFile ? `Work on ${currentFile}` : 'BEAST desktop agent request'),
    mode: 'architect',
    provider: selectedProvider,
    model: selectedModel,
    files: pack.files,
    budget: { tokens: 120000, seconds: 3600, cost_usd: 0 },
  });
  currentAgentSession = result.session || null;
  renderAgentDetail(currentAgentSession);
  log(`agent session created for request: ${currentAgentSession?.session_id || JSON.stringify(result).slice(0, 180)}`);
  return currentAgentSession;
}

async function recordAgentPrompt(prompt) {
  const pack = buildAgentContextPack(prompt);
  if (!currentAgentSession?.session_id || String(currentAgentSession.session_id).startsWith('local-')) {
    appendLocalAgentTurn('operator_prompt', pack.prompt, { local_queued: desktopLocalMode, context_files: pack.files });
    return true;
  }
  const result = await postJson('/edgek/ide/agent-sessions/update', {
    root_path: workspaceRoot,
    session_id: currentAgentSession.session_id,
    output: {
      kind: 'operator_prompt',
      text: pack.prompt,
      provider: selectedProvider,
      model: selectedModel,
      context_files: pack.files,
      context_summary: pack.summary,
    },
    files: pack.files,
  });
  if (result.ok) {
    currentAgentSession = result.session;
    renderAgentDetail(currentAgentSession);
    return true;
  }
  return false;
}

async function recordAgentDiagnostic(kind, text, extra = {}) {
  if (!currentAgentSession?.session_id || String(currentAgentSession.session_id).startsWith('local-') || desktopLocalMode) {
    appendLocalAgentTurn(kind, text, extra);
    return;
  }
  try {
    const result = await postJson('/edgek/ide/agent-sessions/update', {
      root_path: workspaceRoot,
      session_id: currentAgentSession.session_id,
      output: {
        kind,
        text,
        provider: selectedProvider,
        model: selectedModel,
        ...extra,
      },
    });
    if (result.ok) {
      currentAgentSession = result.session;
      renderAgentDetail(currentAgentSession);
    }
  } catch (error) {
    appendLocalAgentTurn(kind, text, { ...extra, persist_error: error.message || String(error) });
  }
}

async function sendAgentPrompt() {
  const prompt = $('agentPromptText').value.trim();
  if (!prompt) {
    log('agent request blocked: prompt is empty.');
    return;
  }
  if (desktopLocalMode) {
    const pack = buildAgentContextPack(prompt);
    appendLocalAgentTurn('operator_prompt', pack.prompt, { local_queued: true, context_files: pack.files });
    $('agentOutputText').value = [
      $('agentOutputText').value.trim(),
      `\n[queued request]\n${pack.prompt}\n\nGateway is offline. Start or restart the gateway to stream this request through ${selectedProvider}.`,
    ].filter(Boolean).join('\n');
    log('agent request queued locally: gateway unavailable.');
    return;
  }
  await ensureAgentSessionForPrompt(prompt);
  await recordAgentPrompt(prompt);
  runAgentStream(prompt);
}

async function saveAgentOutput() {
  if (!currentAgentSession?.session_id) {
    log('agent output save blocked: no session selected.');
    return;
  }
  const text = $('agentOutputText').value.trim();
  if (!text) {
    log('agent output save blocked: output is empty.');
    return;
  }
  const result = await postJson('/edgek/ide/agent-sessions/update', {
    root_path: workspaceRoot,
    session_id: currentAgentSession.session_id,
    output: { kind: 'operator_agent_output', text, provider: selectedProvider, model: selectedModel },
    budget_delta: { tokens: Math.ceil(text.length / 4) },
  });
  if (result.ok) {
    currentAgentSession = result.session;
    renderAgentDetail(currentAgentSession);
    log(`agent output saved: ${currentAgentSession.session_id}`);
  }
}

async function agentOutputToSourcePlan() {
  if (!currentAgentSession?.session_id) {
    log('SourcePlan conversion blocked: no session selected.');
    return;
  }
  const text = $('agentOutputText').value.trim();
  if (!text || /^\[stream status\]/i.test(text) || /^\[stream error\]/i.test(text)) {
    const message = 'No agent response is available to compile yet. Send/Stream a prompt and wait for provider tokens before compiling a SourcePlan.';
    $('agentRunInspector').textContent = message;
    $('agentRunInspector').className = 'status-box warn';
    setAgentPatchStatus(message, 'warn');
    log('agent SourcePlan conversion blocked: no provider response.');
    return;
  }
  const contextFiles = buildAgentContextPack($('agentPromptText')?.value || '').files;
  const actionIrResult = await postJson('/edgek/ide/agent-sessions/action-ir-sourceplan', {
    root_path: workspaceRoot,
    session_id: currentAgentSession.session_id,
    output: text,
    active_file: currentFile,
    files: contextFiles,
    provider: selectedProvider,
    objective: currentAgentSession.objective || (currentFile ? `Apply agent edit to ${currentFile}` : 'Apply agent Action IR'),
  }).catch(error => ({ ok: false, error: error.message || String(error), status: 'request_failed' }));
  if (actionIrResult.ok && actionIrResult.plan) {
    currentSourcePlan = actionIrResult.plan;
    $('diffPreview').textContent = JSON.stringify(actionIrResult.plan, null, 2);
    $('diffMeta').textContent = `Agent Action IR SourcePlan ${actionIrResult.plan.plan_id}`;
    setSourcePlanStatus(`Agent Action IR SourcePlan ready: ${actionIrResult.plan.plan_id}\nOperations: ${actionIrResult.operation_count || 0}`, 'ready');
    document.querySelector('[data-editor-tab="diff"]').click();
    log(`agent Action IR compiled: ${actionIrResult.plan.plan_id}`);
    await refreshSourcePlanLifecycle();
    return;
  }
  renderAgentActionIrRetry(actionIrResult);
  log(`agent Action IR not compiled: ${actionIrResult.status || actionIrResult.error || 'not_action_ir'}; falling back to advisory draft.`);
  const result = await postJson('/edgek/ide/agent-sessions/sourceplan-draft', {
    root_path: workspaceRoot,
    session_id: currentAgentSession.session_id,
    output: text,
  });
  if (!result.ok) {
    log(`agent SourcePlan draft failed: ${result.error || 'unknown error'}`);
    return;
  }
  currentSourcePlan = result.plan;
  $('diffPreview').textContent = JSON.stringify(result.plan, null, 2);
  setSourcePlanStatus(`Agent SourcePlan ready: ${result.plan.plan_id}\nRequires operator translation: ${result.plan.requires_operator_translation}`, 'ready');
  document.querySelector('[data-editor-tab="diff"]').click();
  log(`agent output converted to SourcePlan draft: ${result.plan.plan_id}`);
  await refreshSourcePlanLifecycle();
}

function renderAgentActionIrRetry(result = {}) {
  const questions = (result.missing_context_questions || []).map(item => `- ${item}`).join('\n');
  const retries = (result.retry_options || []).map(item => `- ${item.label || item.id}`).join('\n');
  const guidance = [
    `Action IR status: ${result.status || 'not_action_ir'}`,
    result.error ? `Reason: ${result.error}` : '',
    questions ? `Missing context:\n${questions}` : '',
    retries ? `Retry options:\n${retries}` : '',
    'Provider contract: return BEAST Action IR JSON with exact path, old snippet, and new snippet; ask for missing context instead of guessing.',
  ].filter(Boolean).join('\n\n');
  $('agentRunInspector').textContent = guidance;
  $('agentRunInspector').className = 'status-box warn';
  recordAgentDiagnostic('action_ir_retry_options', guidance, {
    status: result.status || 'not_action_ir',
    retry_options: result.retry_options || [],
    missing_context_questions: result.missing_context_questions || [],
  });
}

async function copyAgentOutput() {
  const text = $('agentOutputText').value.trim();
  if (!text) {
    log('copy blocked: agent output is empty.');
    return;
  }
  await navigator.clipboard.writeText(text);
  log('agent output copied.');
}

function askAgentAboutSelection() {
  if (!currentFile) {
    log('Ask Selection blocked: no active file.');
    return;
  }
  const info = editorSelectionInfo();
  if (!info.selected) {
    log('Ask Selection blocked: select code in the editor first.');
    return;
  }
  $('agentIncludeActiveFile').checked = true;
  $('agentIncludeSelection').checked = true;
  $('agentPromptText').value = `Explain this selection and suggest a governed BEAST SourcePlan-safe improvement for ${currentFile}:${info.line}-${info.lineEnd}.`;
  setDesktopPage('agents');
  renderAgentContextPack();
}

function setAgentPatchStatus(text, state = 'muted') {
  const node = $('agentPatchStatus');
  node.textContent = text;
  node.className = `status-box ${state}`;
}

function parseJsonLikeFence(text) {
  const body = String(text || '').trim();
  if (!/^[\[{]/.test(body)) return null;
  try {
    return JSON.parse(body);
  } catch {
    return null;
  }
}

function isAgentToolCommandFence(text) {
  const parsed = parseJsonLikeFence(text);
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return false;
  const command = String(parsed.command || parsed.tool || parsed.action || '').toLowerCase();
  return Boolean(command && ['read', 'open', 'search', 'grep', 'edit', 'write', 'patch'].includes(command));
}

function sourceLanguageForPath(path) {
  const ext = String(path || '').split('.').pop().toLowerCase();
  return {
    py: 'python',
    js: 'javascript',
    jsx: 'javascript',
    ts: 'typescript',
    tsx: 'typescript',
    html: 'html',
    css: 'css',
    json: 'json',
    md: 'markdown',
    sh: 'shell',
  }[ext] || '';
}

function looksLikeNarrativePatch(text) {
  const body = String(text || '').trim();
  const lowered = body.toLowerCase();
  const badPhrases = [
    'but note:',
    'however,',
    'actually,',
    "let's look",
    'the previous answer',
    "the user's last message",
    'we must continue',
    'we need to',
    'i will',
    'here is',
    'explanation',
  ];
  return badPhrases.some(phrase => lowered.includes(phrase));
}

function validateAgentPatchCandidate(text, selection = null, language = sourceLanguageForPath(currentFile)) {
  const body = String(text || '');
  const trimmed = body.trim();
  if (!trimmed) return { ok: false, reason: 'replacement is empty' };
  if (trimmed.includes('```')) return { ok: false, reason: 'replacement contains nested fenced markdown' };
  if (trimmed.includes('[selection truncated by BEAST Desktop]')) return { ok: false, reason: 'replacement contains a BEAST truncation marker' };
  if (looksLikeNarrativePatch(trimmed)) return { ok: false, reason: 'replacement looks like model reasoning/prose, not source code' };
  const lines = trimmed.split(/\r?\n/);
  const codeSignals = [
    /^\s*(def|class|async def|return|if|elif|else:|for|while|try:|except|with|from\s+\S+\s+import|import\s+\S+)/m,
    /^\s*(const|let|var|function|export|import|return|if|for|while|class)\b/m,
    /[{}();=]/,
  ];
  if (language && !['markdown', 'text'].includes(language) && !codeSignals.some(pattern => pattern.test(trimmed))) {
    return { ok: false, reason: `replacement does not look like ${language} source code` };
  }
  if (selection?.selected) {
    const selectedLines = Math.max(1, selection.selected.split(/\r?\n/).length);
    if (lines.length > Math.max(80, selectedLines * 3)) {
      return { ok: false, reason: `replacement is too large for the selected range (${lines.length} lines for ${selectedLines} selected)` };
    }
  }
  return { ok: true, reason: 'source-like replacement' };
}

function extractFencedBlocks(text) {
  const body = String(text || '');
  return Array.from(body.matchAll(/```([^\n`]*)\n([\s\S]*?)```/g))
    .map(match => ({ language: String(match[1] || '').trim().toLowerCase(), text: String(match[2] || '').trim() }))
    .filter(item => item.text);
}

function extractLastCodeFence(text) {
  const fences = extractFencedBlocks(text);
  const sourceLike = fences.filter(item => {
    if (isAgentToolCommandFence(item.text)) return false;
    if (['json', 'yaml', 'yml'].includes(item.language)) return false;
    return validateAgentPatchCandidate(item.text, editorSelectionInfo(), item.language || sourceLanguageForPath(currentFile)).ok;
  });
  const preferred = [...sourceLike].reverse().find(item => item.language === sourceLanguageForPath(currentFile)) || sourceLike[sourceLike.length - 1];
  return preferred?.text || '';
}

function latestAgentToolCommand(text) {
  const fences = extractFencedBlocks(text);
  for (const item of fences.reverse()) {
    if (isAgentToolCommandFence(item.text)) return parseJsonLikeFence(item.text);
  }
  return null;
}

function extractAgentPatchCandidate() {
  const fenced = extractLastCodeFence($('agentOutputText').value);
  if (!fenced) {
    const toolCommand = latestAgentToolCommand($('agentOutputText').value);
    if (toolCommand) {
      setAgentPatchStatus(`Agent returned a tool request (${toolCommand.command || toolCommand.tool || toolCommand.action}) for ${toolCommand.path || 'unknown path'}, not replacement code. Use Request Patch for diffable code.`, 'warn');
      log(`agent returned tool request instead of patch: ${JSON.stringify(toolCommand).slice(0, 220)}`);
      return;
    }
    setAgentPatchStatus('No valid source-code replacement block found. The output may be prose, a tool request, or an oversized planning answer; ask for a narrower code block before previewing.', 'warn');
    log('agent patch extraction found no valid source-code replacement block.');
    return;
  }
  $('agentProposedText').value = fenced;
  setAgentPatchStatus(`Extracted ${fenced.length} chars from the latest fenced code block.`, 'ready');
  log(`agent patch extracted: ${fenced.length} chars`);
}

function buildAgentPatchPreview() {
  if (!currentFile) {
    setAgentPatchStatus('Select a file before previewing an agent patch.', 'warn');
    return null;
  }
  const info = editorSelectionInfo();
  if (!info.selected) {
    setAgentPatchStatus('Select the code to replace before previewing an agent patch.', 'warn');
    return null;
  }
  const replacement = $('agentProposedText').value;
  if (!replacement.trim()) {
    setAgentPatchStatus('Paste or extract replacement text before previewing.', 'warn');
    return null;
  }
  const validation = validateAgentPatchCandidate(replacement, info);
  if (!validation.ok) {
    pendingAgentPatch = null;
    $('diffPreview').textContent = [
      'Agent patch rejected before diff preview.',
      '',
      `Reason: ${validation.reason}`,
      '',
      'Ask the agent for a narrower fenced source-code replacement, or use a SourcePlan/Action IR planning request for large ranges.',
    ].join('\n');
    document.querySelector('[data-editor-tab="diff"]').click();
    setAgentPatchStatus(`Patch rejected: ${validation.reason}`, 'bad');
    log(`agent patch rejected: ${validation.reason}`);
    return null;
  }
  const current = getEditorValue();
  const next = `${current.slice(0, info.start)}${replacement}${current.slice(info.end)}`;
  return { info, replacement, current, next };
}

function previewAgentPatch() {
  const patch = buildAgentPatchPreview();
  if (!patch) return null;
  pendingAgentPatch = patch;
  $('diffPreview').textContent = [
    `--- a/${currentFile}`,
    `+++ b/${currentFile}`,
    `@@ agent selected replacement ${patch.info.line}-${patch.info.lineEnd} @@`,
    ...simpleLineDiff(patch.current, patch.next),
    '',
    'Agent patch policy: preview only. Compile Plan creates explicit SourcePlan operations; Apply writes only after approval, verification, rollback, and evidence.',
  ].join('\n');
  $('diffMeta').textContent = `${currentFile}:${patch.info.line}-${patch.info.lineEnd} · agent replacement preview`;
  updateMonacoDiff(patch.current, patch.next);
  document.querySelector('[data-editor-tab="diff"]').click();
  setAgentPatchStatus(`Preview ready for ${currentFile}:${patch.info.line}-${patch.info.lineEnd}.`, 'ready');
  return patch;
}

async function compileAgentPatchSourcePlan() {
  if (desktopLocalMode) {
    previewAgentPatch();
    setAgentPatchStatus('Local IDE Mode: diff preview is ready, but SourcePlan compilation requires gateway.', 'warn');
    return;
  }
  const patch = previewAgentPatch();
  if (!patch) return;
  const result = await postJson('/edgek/ide/sourceplan/from-selection', {
    root_path: workspaceRoot,
    path: currentFile,
    original_text: originalText,
    selection_text: patch.info.selected,
    replacement_text: patch.replacement,
    objective: `Apply agent-proposed selected replacement to ${currentFile}:${patch.info.line}-${patch.info.lineEnd}`,
    provider: selectedProvider,
    char_start: patch.info.start,
    char_end: patch.info.end,
    line_start: patch.info.line,
    line_end: patch.info.lineEnd,
  });
  document.querySelector('[data-editor-tab="diff"]').click();
  if (!result.ok) {
    const reason = result.error || 'agent_patch_compile_failed';
    setAgentPatchStatus(`${reason}${result.stale_context ? '\nReload file before compiling.' : ''}`, result.stale_context ? 'bad' : 'warn');
    $('diffPreview').textContent = JSON.stringify(result, null, 2);
    log(`agent patch SourcePlan failed: ${reason}`);
    return;
  }
  currentSourcePlan = result.plan;
  $('diffPreview').textContent = [
    `# BEAST Agent Patch SourcePlan: ${currentSourcePlan.plan_id}`,
    `# ${currentFile}:${patch.info.line}-${patch.info.lineEnd}`,
    '',
    result.preview_text || 'No diff text returned.',
  ].join('\n');
  setSourcePlanStatus(`Agent patch plan ready: ${currentSourcePlan.plan_id}\n${currentFile}:${patch.info.line}-${patch.info.lineEnd}`, 'ready');
  setAgentPatchStatus(`Compiled SourcePlan ${currentSourcePlan.plan_id}. Verify before apply.`, 'ready');
  setDesktopPage('source');
  log(`agent patch SourcePlan ready: ${currentSourcePlan.plan_id}`);
  await refreshSourcePlanLifecycle();
}

function stageAgentPatchBuffer() {
  const patch = previewAgentPatch();
  if (!patch) return;
  if (!window.confirm('Stage this agent patch into the editor buffer? This does not write to disk; SourcePlan is still required for apply.')) return;
  setEditorValue(patch.next);
  dirtyFiles.add(currentFile);
  updateEditorMeta();
  updateOpenTabs();
  renderFileExplorer();
  diffCurrentEdit();
  setAgentPatchStatus('Patch staged in editor buffer. Use SourcePlan Draft to compile before writing.', 'ready');
}

function requestAgentPatchForSelection() {
  if (!currentFile) {
    setAgentPatchStatus('Select a file before requesting a patch.', 'warn');
    return;
  }
  const info = editorSelectionInfo();
  if (!info.selected) {
    setAgentPatchStatus('Select the exact code range before requesting a patch.', 'warn');
    return;
  }
  $('agentIncludeActiveFile').checked = true;
  $('agentIncludeSelection').checked = true;
  const summary = selectionContextSummary(info);
  if (info.selected.length > AGENT_PATCH_REPLACEMENT_LIMIT) {
    $('agentPromptText').value = [
      `Analyze ${summary.range} without rewriting the whole selected range.`,
      `The selection is ${summary.chars} chars across ${summary.lines} lines, so BEAST Desktop will not inline it or request one fenced replacement block.`,
      'Return a concise SourcePlan-safe implementation plan with specific symbols/anchors/hunks to change.',
      'Prefer Action IR-style targeted edits or ask the operator to narrow the selection before generating replacement code.',
      'Do not infer missing code from partial previews, truncation markers, or context summaries.',
    ].join(' ');
    setAgentPatchStatus('Large selection detected. Replacement request converted to a scoped SourcePlan/Action IR planning request; narrow the selection for direct patch preview.', 'warn');
  } else {
    $('agentPromptText').value = [
      `Return a SourcePlan-safe replacement for ${currentFile}:${info.line}-${info.lineEnd}.`,
      'Return only one fenced code block containing the replacement text for the selected range.',
      'Do not return JSON commands, tool calls, prose, markdown explanations, or whole-file rewrites.',
      'Preserve existing behavior unless the selected code clearly needs the minimal improvement.',
    ].join(' ');
    setAgentPatchStatus('Patch request prepared. Send it, then Extract Code and Preview Diff.', 'ready');
  }
  setDesktopPage('agents');
  renderAgentContextPack();
}

async function copyProviderSetup() {
  const payload = $('providerRaw').textContent || JSON.stringify({ selectedProvider, selectedModel }, null, 2);
  await navigator.clipboard.writeText(payload);
  log('provider setup copied.');
}

function runAgentStream(promptOverride = '') {
  if (!currentAgentSession?.session_id) {
    log('agent stream blocked: no session selected.');
    return;
  }
  if (desktopLocalMode || String(currentAgentSession.session_id).startsWith('local-')) {
    log('agent stream blocked: gateway unavailable; request remains queued locally.');
    return;
  }
  resetAgentRunStream();
  resetAgentRunInspector();
  const rawPrompt = String(promptOverride || $('agentPromptText').value.trim() || $('agentOutputText').value.trim() || currentAgentSession.objective || 'Continue this BEAST agent session.').trim();
  const pack = buildAgentContextPack(rawPrompt);
  const prompt = pack.prompt;
  $('agentOutputText').value = `[stream status]\nConnecting to ${selectedProvider} · ${selectedModel}...\n`;
  renderAgentDetail({ ...currentAgentSession, status: 'running' });
  const params = new URLSearchParams();
  if (workspaceRoot) params.set('root_path', workspaceRoot);
  params.set('prompt', prompt);
  params.set('provider', selectedProvider || currentAgentSession.provider || 'nvidia_nim');
  params.set('model', selectedModel || currentAgentSession.model || DEFAULT_NVIDIA_NIM_MODEL);
  params.set('max_tokens', '2000');
  params.set('context_max_chars_each', String(AGENT_CONTEXT_FILE_CHARS));
  pack.files.forEach(path => params.append('context_files', path));
  if ($('agentSimulateRun').checked) params.set('simulate', 'true');
  const url = `${gatewayUrl}/edgek/ide/agent-sessions/${encodeURIComponent(currentAgentSession.session_id)}/run-events?${params.toString()}`;
  agentRunStream = new EventSource(url);
  let streamOpened = false;
  let tokenSeen = false;
  const streamWatchdog = setTimeout(() => {
    if (streamOpened || tokenSeen) return;
    const message = [
      '[stream error]',
      `No agent stream events arrived from ${gatewayUrl} within 12 seconds.`,
      'The gateway may be busy, restarting, or the IDE route may be blocked.',
      `Provider: ${selectedProvider}`,
      `Model: ${selectedModel}`,
      'NIM smoke may still pass because it uses a different endpoint than agent run-events.',
    ].join('\n');
    $('agentOutputText').value = message;
    setStreamState('agent stream stalled', 'bad');
    setAgentProviderHealth(message, 'bad');
    log('agent stream stalled before first event.');
  }, 12000);
  setStreamState('agent stream running', 'ready');
  setAgentProviderHealth(`${selectedProvider} · ${selectedModel}\nstream starting`, 'warn');
  log(`agent stream started: ${currentAgentSession.session_id}`);
  agentRunStream.addEventListener('agent_run_started', event => {
    streamOpened = true;
    clearTimeout(streamWatchdog);
    const envelope = JSON.parse(event.data || '{}');
    log(`agent run provider: ${envelope.payload?.provider || 'provider'}`);
    setAgentProviderHealth(`${envelope.payload?.provider || selectedProvider} · ${envelope.payload?.model || selectedModel}\nstream live`, 'ready');
    pushAgentStage('run started');
    $('agentPromptText').value = '';
    $('agentOutputText').value = '';
  });
  agentRunStream.addEventListener('agent_run_stage', event => {
    const envelope = JSON.parse(event.data || '{}');
    const text = envelope.payload?.text || '';
    pushAgentStage(text);
    log(`agent stage: ${text}`);
  });
  agentRunStream.addEventListener('agent_run_tool', event => {
    const envelope = JSON.parse(event.data || '{}');
    const text = envelope.payload?.text || '';
    pushAgentTool(text);
    log(`agent tool: ${text}`);
  });
  agentRunStream.addEventListener('agent_run_provider_done', event => {
    const envelope = JSON.parse(event.data || '{}');
    const data = envelope.payload?.data || {};
    const handoff = data.handoff || {};
    const providerError = data.provider_error || '';
    const line = [
      `provider completed: ${data.provider_completed ? 'yes' : 'no'}`,
      `streaming: ${data.provider_streaming ? 'yes' : 'no'}`,
      `recovered: ${data.provider_recovered ? 'yes' : 'no'}`,
      `handoff: ${handoff.ready ? 'ready' : 'not ready'}`,
      providerError ? `error: ${String(providerError).slice(0, 180)}` : '',
    ].filter(Boolean).join(' · ');
    setAgentProviderHealth(line, data.provider_completed ? 'ready' : data.provider_recovered ? 'warn' : 'bad');
    if (!data.provider_completed) renderProviderRetryOptions(providerError || line);
    recordAgentDiagnostic('provider_diagnostics', line, {
      provider_completed: data.provider_completed,
      provider_streaming: data.provider_streaming,
      provider_recovered: data.provider_recovered,
      handoff_ready: Boolean(handoff.ready),
      provider_error: providerError,
    }).catch(error => log(`agent provider diagnostic save failed: ${error.message || error}`));
    log(`agent provider diagnostics: ${line}`);
  });
  agentRunStream.addEventListener('agent_run_token', event => {
    tokenSeen = true;
    clearTimeout(streamWatchdog);
    const envelope = JSON.parse(event.data || '{}');
    $('agentOutputText').value += envelope.payload?.text || '';
    $('agentOutputText').scrollTop = $('agentOutputText').scrollHeight;
  });
  agentRunStream.addEventListener('agent_run_done', event => {
    clearTimeout(streamWatchdog);
    const envelope = JSON.parse(event.data || '{}');
    const session = envelope.payload?.session;
    if (session) {
      currentAgentSession = session;
      renderAgentDetail(session);
    }
    setStreamState('event stream live', 'ready');
    setAgentProviderHealth(`done · ${envelope.payload?.chars || 0} chars\n${selectedProvider} · ${selectedModel}`, 'ready');
    log(`agent stream done: ${envelope.payload?.chars || 0} chars`);
    resetAgentRunStream();
    refreshSnapshot();
  });
  agentRunStream.addEventListener('agent_run_error', event => {
    clearTimeout(streamWatchdog);
    const envelope = JSON.parse(event.data || '{}');
    const message = `[stream error]\n${envelope.payload?.error || 'unknown error'}`;
    $('agentOutputText').value = message;
    setStreamState('agent stream error', 'bad');
    renderProviderRetryOptions(envelope.payload?.error || 'unknown error');
    log(`agent stream error: ${envelope.payload?.error || 'unknown error'}`);
    resetAgentRunStream();
  });
  agentRunStream.onerror = () => {
    if (!streamOpened && !tokenSeen) {
      clearTimeout(streamWatchdog);
      const message = [
        '[stream error]',
        `Could not connect to agent run-events at ${gatewayUrl}.`,
        'Check that the BEAST gateway is running and restart it after backend edits.',
        `Provider: ${selectedProvider}`,
        `Model: ${selectedModel}`,
      ].join('\n');
      $('agentOutputText').value = message;
      setAgentProviderHealth(message, 'bad');
      log('agent stream connection failed before first event.');
    }
    setStreamState(streamOpened || tokenSeen ? 'agent stream reconnecting' : 'agent stream error', streamOpened || tokenSeen ? 'warn' : 'bad');
  };
}

async function verifySourcePlan() {
  if (desktopLocalMode) {
    setSourcePlanStatus('Local IDE Mode: verification requires the BEAST gateway.', 'warn');
    return;
  }
  if (!currentSourcePlan) {
    setSourcePlanStatus('No SourcePlan draft to verify.', 'warn');
    return;
  }
  try {
    const result = await postJson('/edgek/sourceplan/verify', {
      root_path: workspaceRoot,
      plan: currentSourcePlan,
    });
    setSourcePlanStatus(`Verified: ${currentSourcePlan.plan_id}\n${result.selected_count || 0} selected operations\n${(result.errors || []).join('\n')}`, 'ready');
    log(`SourcePlan verified: ${currentSourcePlan.plan_id}`);
    await refreshSourcePlanLifecycle();
  } catch (error) {
    setSourcePlanStatus(`Verify failed: ${error.message || error}`, 'bad');
    log(`SourcePlan verify failed: ${error.message || error}`);
  }
}

async function applySourcePlan(confirmApply = true) {
  if (desktopLocalMode) {
    setSourcePlanStatus('Local IDE Mode: apply is disabled until the BEAST gateway is online.', 'warn');
    return;
  }
  if (!currentSourcePlan) {
    setSourcePlanStatus('No SourcePlan draft to apply.', 'warn');
    return;
  }
  const planId = currentSourcePlan.plan_id || 'draft';
  if (confirmApply && !window.confirm(`Apply SourcePlan ${planId}? BEAST will verify, write rollback data, and close evidence.`)) return;
  try {
    const result = await postJson('/edgek/sourceplan/apply', {
      root_path: workspaceRoot,
      plan: currentSourcePlan,
      approved: true,
    });
    lastApplyResult = result;
    renderApplyTimeline(result);
    setSourcePlanStatus(`Applied: ${planId}\n${(result.applied || []).join('\n') || 'No file list returned.'}`, 'ready');
    log(`SourcePlan applied: ${planId}`);
    if (currentFile) {
      dirtyFiles.delete(currentFile);
      clearPersistedBuffer(currentFile);
      fileModels.get(currentFile)?.dispose();
      fileModels.delete(currentFile);
      await openFile(currentFile);
    }
    await refreshSnapshot();
    await refreshSourcePlanLifecycle();
  } catch (error) {
    setSourcePlanStatus(`Apply failed: ${error.message || error}`, 'bad');
    log(`SourcePlan apply failed: ${error.message || error}`);
  }
}

function clearSourcePlan() {
  currentSourcePlan = null;
  currentSourcePlanLifecycle = null;
  selectedSourcePlanOpId = '';
  setSourcePlanStatus('No editor draft yet.', 'muted');
  $('sourcePlanLifecycle').innerHTML = '<div class="mini-card muted">No lifecycle loaded.</div>';
  $('sourcePlanOperations').innerHTML = '<div class="mini-card muted">No operations loaded.</div>';
  $('sourcePlanActionContract').textContent = 'No contract loaded.';
  $('sourcePlanActionContract').className = 'status-box muted';
  $('sourcePlanOperationLedger').innerHTML = '<div class="mini-card muted">No operation ledger loaded.</div>';
  $('sourcePlanRollbackPreview').textContent = 'Rollback preview appears after a lifecycle refresh or apply.';
  $('sourcePlanRollbackPreview').className = 'status-box muted';
  renderApplyTimeline(null);
  diffCurrentEdit();
}

async function searchEvidenceDrawer(mode = 'query') {
  const source = $('evidenceSource').value.trim();
  const artifactType = $('evidenceType').value.trim();
  const status = $('evidenceStatus').value.trim();
  const key = $('evidenceKey').value.trim();
  const params = new URLSearchParams();
  if (workspaceRoot) params.set('root_path', workspaceRoot);
  params.set('limit', '80');
  if (mode === 'related' && key) {
    const payload = await getJson(`/edgek/evidence-bus/related/${encodeURIComponent(key)}?${params.toString()}`);
    renderEvidenceReceipts(payload.receipts || []);
    log(`Evidence related ${key}: ${payload.match_count || 0} receipt(s)`);
    return;
  }
  if (source) params.set('source', source);
  if (artifactType) params.set('artifact_type', artifactType);
  if (status) params.set('status', status);
  if (key) params.set('plan_id', key);
  const payload = await getJson(`/edgek/evidence-bus/query?${params.toString()}`);
  renderEvidenceReceipts(payload.receipts || []);
  log(`Evidence query: ${payload.match_count || 0} receipt(s)`);
}

function renderEvidenceReceipts(receipts) {
  renderList($('evidenceBus'), receipts || [], item => [
    '<div class="mini-card">',
    `<b>${escapeHtml(item.status || 'recorded')}</b> · ${escapeHtml(item.source || 'source')}`,
    `<br><span>${escapeHtml(item.artifact_type || item.receipt_id || 'evidence')}</span>`,
    item.summary ? `<br><span class="muted">${escapeHtml(item.summary)}</span>` : '',
    item.task_id ? `<br><span class="muted">task ${escapeHtml(item.task_id)}</span>` : '',
    '</div>',
  ].join(''), 'No evidence receipts match this view.', 'Run verification, terminal commands, SourcePlan lifecycle, or clear filters.');
  updateStatusChips();
  renderNextActionInspector();
}

function clearEvidenceFilters() {
  ['evidenceSource', 'evidenceType', 'evidenceStatus', 'evidenceKey'].forEach(id => { $(id).value = ''; });
  const evidence = currentSnapshot?.evidence_bus || {};
  renderEvidenceReceipts(evidence.recent || evidence.receipts || []);
}

function selectWorktreeTask(taskId) {
  const rows = currentSnapshot?.worktrees?.tasks || currentSnapshot?.worktrees?.items || [];
  currentWorktreeTask = rows.find(item => item.task_id === taskId) || { task_id: taskId };
  renderWorktreeMissions(rows);
  $('worktreeWizardState').textContent = [
    `Selected ${currentWorktreeTask.task_id || taskId}`,
    currentWorktreeTask.worktree_path ? `path: ${currentWorktreeTask.worktree_path}` : 'path pending',
    'Use Open Window, Diff, Promote, Verify, or Close.',
  ].join('\n');
  $('worktreeWizardState').className = 'status-box ready';
  renderWorktreeWizardSteps('selected');
  saveWorkspaceState();
  log(`worktree selected: ${taskId}`);
}

function renderWorktreeWizardSteps(active = '') {
  const steps = [
    ['selected', 'Select', Boolean(currentWorktreeTask?.task_id)],
    ['verify', 'Verify', ['verify', 'diff', 'promote', 'ready'].includes(active)],
    ['diff', 'Diff', ['diff', 'promote', 'ready'].includes(active)],
    ['promote', 'Promote', ['promote', 'ready'].includes(active)],
    ['close', 'Close', active === 'close'],
  ];
  const node = $('worktreeWizardSteps');
  if (!node) return;
  node.innerHTML = steps.map(([id, label, ok]) => `<span class="step ${ok ? 'ready' : id === active ? 'warn' : ''}">${escapeHtml(label)}</span>`).join('');
}

function renderWorktreeDiffSummary(result = {}) {
  const node = $('worktreeDiffSummary');
  if (!node) return;
  const text = result.diff || result.patch || '';
  const added = text.split('\n').filter(line => line.startsWith('+') && !line.startsWith('+++')).length;
  const removed = text.split('\n').filter(line => line.startsWith('-') && !line.startsWith('---')).length;
  node.innerHTML = text
    ? `<div class="mini-card"><b>Diff Summary</b><br>+${added} / -${removed} · ${escapeHtml(currentWorktreeTask?.task_id || '')}<br><span class="muted">Review diff, draft SourcePlan, verify, then apply through BEAST.</span></div>`
    : emptyCard('No worktree diff loaded.', 'Click Diff before promoting.');
}

async function testWorktreeMission() {
  if (!currentWorktreeTask?.task_id) {
    log('worktree verify blocked: no mission selected.');
    return;
  }
  const result = await postJson('/edgek/ide/worktree-mission/test', {
    root_path: workspaceRoot,
    task_id: currentWorktreeTask.task_id,
    timeout: 120,
  });
  renderWorktreeWizardSteps('verify');
  log(`worktree verify ${currentWorktreeTask.task_id}: ${result.ok ? 'ok' : 'failed'} ${result.error || ''}`);
  await refreshSnapshot();
}

async function draftWorktreeSourcePlan() {
  if (!currentWorktreeTask?.task_id) {
    log('worktree SourcePlan blocked: no mission selected.');
    return;
  }
  const result = await postJson('/edgek/ide/worktree-mission/sourceplan-draft', {
    root_path: workspaceRoot,
    task_id: currentWorktreeTask.task_id,
    max_chars: 80000,
  });
  if (!result.ok) {
    setSourcePlanStatus(`Worktree plan failed: ${result.error || 'unknown error'}`, 'bad');
    log(`worktree SourcePlan failed: ${result.error || 'unknown error'}`);
    return;
  }
  currentSourcePlan = result.plan;
  $('diffPreview').textContent = result.plan.worktree_diff || JSON.stringify(result.plan, null, 2);
  setSourcePlanStatus(`Worktree SourcePlan ready: ${result.plan.plan_id}\nOperations: ${(result.plan.operations || []).length}\nTranslation needed: ${result.plan.requires_operator_translation}`, result.plan.requires_operator_translation ? 'warn' : 'ready');
  document.querySelector('[data-editor-tab="diff"]').click();
  log(`worktree SourcePlan draft ready: ${result.plan.plan_id}`);
  await refreshSourcePlanLifecycle();
}

async function openWorktreeWindow() {
  const path = currentWorktreeTask?.worktree_path || currentWorktreeTask?.path || '';
  if (!path) {
    $('worktreeWizardState').textContent = 'Selected worktree has no path yet. Refresh missions or create a new worktree.';
    $('worktreeWizardState').className = 'status-box warn';
    return;
  }
  const result = await window.beastDesktop.openWorkspaceWindow(path);
  $('worktreeWizardState').textContent = result.ok ? `Opened BEAST IDE window for ${path}` : `Open failed: ${result.error || path}`;
  $('worktreeWizardState').className = result.ok ? 'status-box ready' : 'status-box bad';
}

async function browseWorktreeDiff() {
  if (!currentWorktreeTask?.task_id) {
    $('worktreeWizardState').textContent = 'Select a worktree mission before browsing diff.';
    $('worktreeWizardState').className = 'status-box warn';
    return;
  }
  const result = await postJson('/edgek/ide/worktree-mission/diff', {
    root_path: workspaceRoot,
    task_id: currentWorktreeTask.task_id,
    max_chars: 120000,
  });
  $('diffPreview').textContent = result.diff || result.patch || JSON.stringify(result, null, 2);
  $('diffMeta').textContent = `Worktree diff ${currentWorktreeTask.task_id}`;
  document.querySelector('[data-editor-tab="diff"]').click();
  renderWorktreeDiffSummary(result);
  renderWorktreeWizardSteps('diff');
  $('worktreeWizardState').textContent = result.ok ? `Diff loaded for ${currentWorktreeTask.task_id}` : `Diff failed: ${result.error || 'unknown error'}`;
  $('worktreeWizardState').className = result.ok ? 'status-box ready' : 'status-box bad';
}

async function runWorktreePromotionWizard() {
  if (!currentWorktreeTask?.task_id) {
    $('worktreeWizardState').textContent = 'Select a worktree mission before promotion.';
    $('worktreeWizardState').className = 'status-box warn';
    return;
  }
  $('worktreeWizardState').textContent = 'Step 1/3: verifying worktree mission...';
  $('worktreeWizardState').className = 'status-box warn';
  renderWorktreeWizardSteps('verify');
  await testWorktreeMission();
  $('worktreeWizardState').textContent = 'Step 2/3: loading worktree diff...';
  renderWorktreeWizardSteps('diff');
  await browseWorktreeDiff();
  $('worktreeWizardState').textContent = 'Step 3/3: drafting SourcePlan promotion preview...';
  renderWorktreeWizardSteps('promote');
  await draftWorktreeSourcePlan();
  $('worktreeWizardState').textContent = 'Promotion preview ready. Review SourcePlan operations, verify, then apply through BEAST.';
  $('worktreeWizardState').className = 'status-box ready';
  renderWorktreeWizardSteps('ready');
  setDesktopPage('source');
}

async function closeWorktreeMission() {
  if (!currentWorktreeTask?.task_id) {
    log('worktree close blocked: no mission selected.');
    return;
  }
  if (!window.confirm(`Close worktree mission ${currentWorktreeTask.task_id}?`)) return;
  const result = await postJson('/edgek/ide/worktree-mission/close', {
    root_path: workspaceRoot,
    task_id: currentWorktreeTask.task_id,
    reason: 'closed from BEAST Desktop IDE',
  });
  log(`worktree close ${currentWorktreeTask.task_id}: ${result.ok ? 'ok' : 'failed'} ${result.error || ''}`);
  currentWorktreeTask = null;
  await refreshSnapshot();
}

async function classifyTerminalCommand() {
  const command = $('terminalCommand').value.trim();
  if (!command) {
    log('Safety Governor command check blocked: empty command.');
    renderTerminalDecision(null, 'empty command');
    return;
  }
  if (desktopLocalMode) {
    renderTerminalDecision(null, 'Gateway unavailable; classification requires Safety Governor.');
    log('Safety Governor command check blocked: gateway unavailable.');
    return;
  }
  try {
    const result = await postJson('/edgek/safety-governor/classify-command', {
      root_path: workspaceRoot,
      command,
      mode: currentAgentSession?.mode || 'operator',
      task_id: currentAgentSession?.session_id || currentWorktreeTask?.task_id || '',
    });
    lastCommandSafety = result;
    rememberTerminalCommand(command);
    renderTerminalDecision(result);
    const decision = result.decision || result.status || 'classified';
    const reasons = (result.reasons || result.findings || []).map(item => typeof item === 'string' ? item : JSON.stringify(item)).join('; ');
    log(`Safety Governor: ${decision} :: ${command}`);
    if (reasons) log(`Safety reasons: ${reasons}`);
  } catch (error) {
    renderTerminalDecision(null, error.message || String(error));
    log(`Safety Governor failed: ${error.message || error}`);
  }
}

async function executeTerminalCommand() {
  const command = $('terminalCommand').value.trim();
  if (!command) {
    log('Governed execute blocked: empty command.');
    renderTerminalDecision(null, 'empty command');
    return;
  }
  if (desktopLocalMode) {
    renderTerminalDecision(null, 'Gateway unavailable; governed execution requires Safety Governor.');
    log('Governed execute blocked: gateway unavailable.');
    return;
  }
  let approved = false;
  let override = '';
  const decision = lastCommandSafety?.command === command ? (lastCommandSafety.decision || 'allow') : '';
  if (!decision) {
    await classifyTerminalCommand();
  }
  const finalDecision = lastCommandSafety?.command === command ? (lastCommandSafety.decision || 'allow') : 'allow';
  if (finalDecision === 'block') {
    log(`Governed execute blocked by Safety Governor: ${command}`);
    renderTerminalDecision(lastCommandSafety);
    return;
  }
  if (['warn', 'require_approval', 'sandbox/worktree_only'].includes(finalDecision)) {
    approved = window.confirm(`Safety Governor decision is ${finalDecision}. Execute anyway with evidence?`);
    if (!approved) {
      log(`Governed execute cancelled: ${command}`);
      return;
    }
    override = `Approved from BEAST Desktop IDE after ${finalDecision}`;
  }
  log(`$ ${command}`);
  rememberTerminalCommand(command);
  startTerminalStream(command, { approved, override });
}

function setTerminalStreamState(text, state = 'warn') {
  const node = $('terminalStreamState');
  if (!node) return;
  node.textContent = text;
  node.className = `stream-state ${state}`;
}

function startTerminalStream(command, options = {}) {
  if (terminalStreamSource) {
    log('terminal stream blocked: another command is already running.');
    return;
  }
  const params = new URLSearchParams();
  if (workspaceRoot) params.set('root_path', workspaceRoot);
  params.set('command', command);
  params.set('cwd', $('terminalCwd')?.value?.trim() || workspaceRoot);
  params.set('mode', currentAgentSession?.mode || 'operator');
  params.set('task_id', currentAgentSession?.session_id || currentWorktreeTask?.task_id || '');
  params.set('approved', options.approved ? 'true' : 'false');
  params.set('operator_override', options.override || '');
  params.set('timeout', String(Number($('terminalTimeout')?.value || 120)));
  terminalStreamBuffer = {
    ok: false,
    command,
    cwd: params.get('cwd'),
    stdout: '',
    stderr: '',
    safety: lastCommandSafety,
    streamed: true,
  };
  setTerminalStreamState('streaming command output...', 'warn');
  terminalStreamSource = new EventSource(`${gatewayUrl}/edgek/ide/terminal/stream?${params.toString()}`);
  terminalStreamSource.addEventListener('start', event => {
    const payload = JSON.parse(event.data || '{}');
    log(`stream start: ${payload.command || command}`);
  });
  terminalStreamSource.addEventListener('chunk', event => {
    const payload = JSON.parse(event.data || '{}');
    const text = payload.text || '';
    if (payload.stream === 'stderr') terminalStreamBuffer.stderr += text;
    else terminalStreamBuffer.stdout += text;
    $('terminalLog').textContent += text;
    $('terminalLog').scrollTop = $('terminalLog').scrollHeight;
  });
  terminalStreamSource.addEventListener('heartbeat', event => {
    const payload = JSON.parse(event.data || '{}');
    setTerminalStreamState(`streaming · ${payload.elapsed_ms || 0}ms`, 'warn');
  });
  terminalStreamSource.addEventListener('done', async event => {
    const payload = JSON.parse(event.data || '{}');
    terminalStreamSource.close();
    terminalStreamSource = null;
    terminalStreamBuffer = { ...terminalStreamBuffer, ...payload };
    recordTerminalExecution(terminalStreamBuffer);
    setTerminalStreamState(`done · exit ${payload.returncode ?? 'n/a'}`, payload.ok ? 'ready' : 'bad');
    log(`stream command ${payload.ok ? 'ok' : 'failed'}: exit ${payload.returncode}`);
    if (payload.evidence_receipt?.receipt_id) log(`terminal evidence: ${payload.evidence_receipt.receipt_id}`);
    await refreshMissionTimeline();
    await searchEvidenceDrawer('query');
  });
  terminalStreamSource.addEventListener('error', event => {
    if (terminalStreamSource) terminalStreamSource.close();
    terminalStreamSource = null;
    const payload = event?.data ? JSON.parse(event.data || '{}') : {};
    const error = payload.error || 'terminal stream failed or closed';
    recordTerminalExecution({ ...(terminalStreamBuffer || {}), ok: false, command, error, safety: lastCommandSafety });
    setTerminalStreamState(error, 'bad');
    log(`Governed stream failed: ${error}`);
  });
}

function cancelTerminalCommand() {
  if (!terminalStreamSource) {
    setTerminalStreamState('no terminal stream to cancel', 'warn');
    return;
  }
  terminalStreamSource.close();
  terminalStreamSource = null;
  recordTerminalExecution({ ...(terminalStreamBuffer || {}), ok: false, error: 'cancelled by operator', safety: lastCommandSafety });
  setTerminalStreamState('cancelled by operator', 'bad');
  log('terminal stream cancelled by operator.');
}

function terminalHistoryStorageKey() {
  return `${TERMINAL_HISTORY_KEY}:${workspaceRoot || 'workspace'}`;
}

function terminalExecutionsStorageKey() {
  return `${TERMINAL_EXECUTIONS_KEY}:${workspaceRoot || 'workspace'}`;
}

function loadTerminalState() {
  try {
    terminalHistory = JSON.parse(localStorage.getItem(terminalHistoryStorageKey()) || '[]').filter(Boolean).slice(0, 80);
  } catch (_error) {
    terminalHistory = [];
  }
  try {
    terminalExecutions = JSON.parse(localStorage.getItem(terminalExecutionsStorageKey()) || '[]').filter(Boolean).slice(0, 30);
  } catch (_error) {
    terminalExecutions = [];
  }
  terminalHistoryIndex = terminalHistory.length;
  lastTerminalExecution = terminalExecutions[0] || null;
  if ($('terminalCwd') && !$('terminalCwd').value) $('terminalCwd').value = workspaceRoot || '';
  renderTerminalHistory();
  renderTerminalEvidence();
}

function rememberTerminalCommand(command) {
  const clean = String(command || '').trim();
  if (!clean) return;
  terminalHistory = [clean, ...terminalHistory.filter(item => item !== clean)].slice(0, 80);
  terminalHistoryIndex = terminalHistory.length;
  localStorage.setItem(terminalHistoryStorageKey(), JSON.stringify(terminalHistory));
  renderTerminalHistory();
}

function commandDecisionClass(decision) {
  if (decision === 'allow') return 'ready';
  if (decision === 'block') return 'bad';
  return decision ? 'warn' : 'muted';
}

function renderTerminalDecision(receipt, error = '') {
  const decision = receipt?.decision || '';
  const risk = receipt?.risk_level || '';
  const reasons = (receipt?.reasons || receipt?.findings || [])
    .map(item => typeof item === 'string' ? item : `${item.kind || item.decision || 'reason'}: ${item.detail || item.decision || JSON.stringify(item)}`)
    .slice(0, 4);
  const lines = error
    ? [`Safety Governor unavailable: ${error}`]
    : receipt
      ? [`${decision || 'classified'} · risk ${risk || 'n/a'}`, ...reasons]
      : ['No command classified yet.'];
  const className = `terminal-decision-card ${error ? 'bad' : commandDecisionClass(decision)}`;
  if ($('terminalDecisionCard')) {
    $('terminalDecisionCard').textContent = lines.join('\n');
    $('terminalDecisionCard').className = className;
  }
  if ($('terminalPolicySummary')) {
    $('terminalPolicySummary').textContent = lines.join('\n');
    $('terminalPolicySummary').className = `status-box ${error ? 'bad' : commandDecisionClass(decision)}`;
  }
}

function recordTerminalExecution(result) {
  const item = {
    at: new Date().toISOString(),
    ok: Boolean(result?.ok),
    command: result?.command || $('terminalCommand')?.value?.trim() || '',
    cwd: result?.cwd || $('terminalCwd')?.value?.trim() || workspaceRoot,
    returncode: result?.returncode,
    duration_ms: result?.duration_ms,
    decision: result?.safety?.decision || lastCommandSafety?.decision || '',
    evidence_receipt: result?.evidence_receipt || null,
    error: result?.error || '',
  };
  lastTerminalExecution = item;
  terminalExecutions = [item, ...terminalExecutions].slice(0, 30);
  localStorage.setItem(terminalExecutionsStorageKey(), JSON.stringify(terminalExecutions));
  renderTerminalEvidence();
  renderTerminalHistory();
}

function renderTerminalHistory() {
  const node = $('terminalHistoryList');
  if (!node) return;
  const rows = terminalHistory.slice(0, 12);
  node.innerHTML = rows.length ? rows.map((command, index) => `
    <button class="status-box terminal-history-card" data-terminal-history-index="${index}">
      <strong>${escapeHtml(command)}</strong>
      <small>${index === 0 ? 'latest' : `history ${index + 1}`}</small>
    </button>
  `).join('') : emptyCard('No terminal history yet.', 'Classify a command to pin it here.');
}

function renderTerminalEvidence() {
  const node = $('terminalEvidenceDetail');
  if (!node) return;
  const item = lastTerminalExecution;
  if (!item) {
    node.textContent = 'No terminal evidence captured yet.';
    node.className = 'status-box muted';
    return;
  }
  const receiptId = item.evidence_receipt?.receipt_id || item.evidence_receipt?.id || 'not recorded';
  node.textContent = [
    `${item.ok ? 'ok' : 'failed'} · ${item.command}`,
    `decision: ${item.decision || 'n/a'} · exit: ${item.returncode ?? 'n/a'} · ${item.duration_ms ?? 'n/a'}ms`,
    `cwd: ${item.cwd || workspaceRoot}`,
    `receipt: ${receiptId}`,
    item.error ? `error: ${item.error}` : '',
  ].filter(Boolean).join('\n');
  node.className = `status-box ${item.ok ? 'ready' : 'warn'}`;
}

function copyLastTerminalReceipt() {
  if (!lastTerminalExecution) {
    log('terminal receipt copy blocked: no execution receipt yet.');
    return;
  }
  navigator.clipboard?.writeText(JSON.stringify(lastTerminalExecution, null, 2));
  log('terminal execution receipt copied.');
}

function applyTerminalEvidenceFilter() {
  $('evidenceSource').value = 'governed_terminal';
  $('evidenceType').value = 'beast_governed_terminal_execution';
  $('evidenceStatus').value = '';
  $('evidenceKey').value = lastTerminalExecution?.evidence_receipt?.receipt_id || lastTerminalExecution?.command || '';
  setDesktopPage('evidence');
  searchEvidenceDrawer('query').catch(error => log(`terminal evidence filter failed: ${error.message || error}`));
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

document.querySelectorAll('.rail-section-header').forEach(btn => {
  btn.addEventListener('click', () => {
    const section = btn.closest('.rail-section');
    if (!section) return;
    section.classList.toggle('collapsed');
    const icon = btn.querySelector('.toggle-icon');
    if (icon) icon.textContent = section.classList.contains('collapsed') ? '+' : '-';
  });
});

document.addEventListener('click', event => {
  const fileButton = event.target.closest('.file-item');
  const symbolSearchButton = event.target.closest('[data-symbol-search-path]');
  if (symbolSearchButton) {
    selectSymbolSearchResult(symbolSearchButton);
    return;
  }
  if (fileButton && fileButton.dataset.symbolLine) {
    selectSymbolFromButton(fileButton);
    return;
  }
  if (fileButton && fileButton.dataset.path) openFile(fileButton.dataset.path);
  const folderButton = event.target.closest('[data-folder-path]');
  if (folderButton) {
    const path = folderButton.dataset.folderPath;
    if (collapsedFolders.has(path)) collapsedFolders.delete(path);
    else collapsedFolders.add(path);
    renderFileExplorer();
    saveWorkspaceState();
    return;
  }
  const railButton = event.target.closest('.rail-button[data-view]');
  if (railButton) setDesktopPage(railButton.dataset.view);
  const navItem = event.target.closest('.nav-item[data-desktop-page]');
  if (navItem) { setDesktopPage(navItem.dataset.desktopPage); return; }
  const commandChip = event.target.closest('.command-chip[data-desktop-page]');
  if (commandChip) { setDesktopPage(commandChip.dataset.desktopPage); return; }
  const nextPageButton = event.target.closest('[data-next-page]');
  if (nextPageButton) {
    setDesktopPage(nextPageButton.dataset.nextPage);
    return;
  }
  const collapseButton = event.target.closest('[data-collapse-panel]');
  if (collapseButton) {
    const body = document.querySelector(`[data-panel-body="${CSS.escape(collapseButton.dataset.collapsePanel)}"]`);
    if (body) {
      body.classList.toggle('collapsed');
      collapseButton.classList.toggle('collapsed', body.classList.contains('collapsed'));
      saveWorkspaceState();
    }
    return;
  }
  const hunkButton = event.target.closest('[data-diff-hunk]');
  if (hunkButton) {
    toggleDiffHunk(hunkButton);
    return;
  }
  const ideAction = event.target.closest('[data-ide-action]');
  if (ideAction) {
    runIdeAction(ideAction.dataset.ideAction).catch(error => log(`IDE action failed: ${error.message || error}`));
    closeCommandPaletteModal();
    return;
  }
  const killPidButton = event.target.closest('[data-kill-pid]');
  if (killPidButton) {
    killSystemProcess(killPidButton.dataset.killPid, killPidButton.dataset.killName || '').catch(error => log(`kill failed: ${error.message || error}`));
    return;
  }
  const freePortButton = event.target.closest('[data-free-port]');
  if (freePortButton) {
    freeSystemPort(freePortButton.dataset.freePort).catch(error => log(`free-port failed: ${error.message || error}`));
    return;
  }
  const runTerminalButton = event.target.closest('[data-run-terminal]');
  if (runTerminalButton) {
    const cmd = runTerminalButton.dataset.runTerminal || '';
    setDesktopPage('terminal');
    if ($('terminalCommand')) $('terminalCommand').value = cmd;
    log(`prefilled governed terminal: ${cmd} (classify + execute to run)`);
    return;
  }
  const copyMcpButton = event.target.closest('[data-copy-mcp]');
  if (copyMcpButton) { copyCatalogMcp(copyMcpButton.dataset.copyMcp); return; }
  const registerMcpButton = event.target.closest('[data-register-mcp]');
  if (registerMcpButton) { registerCatalogMcp(registerMcpButton.dataset.registerMcp).catch(error => log(`register failed: ${error.message || error}`)); return; }
  const editorJump = event.target.closest('[data-editor-jump]');
  if (editorJump) activateEditorTab(editorJump.dataset.editorJump);
  const closeTab = event.target.closest('[data-close-tab]');
  if (closeTab) {
    event.stopPropagation();
    closeEditorTab(closeTab.dataset.closeTab);
    return;
  }
  const openTab = event.target.closest('[data-tab-path]');
  if (openTab) {
    const path = openTab.dataset.tabPath;
    if (fileModels.has(path)) {
      currentFile = path;
      originalText = fileOriginals.get(path) || '';
      monacoEditor?.setModel(fileModels.get(path));
      monacoSplitEditor?.setModel(fileModels.get(path));
      $('editorText').value = getEditorValue();
      $('activeFile').textContent = path;
      updateOpenTabs();
      renderFileExplorer();
      updateEditorMeta();
      updateDiagnosticsAndDecorations();
      diffCurrentEdit();
      refreshRelatedContext();
      saveWorkspaceState();
    } else {
      openFile(path);
    }
  }
  const sessionButton = event.target.closest('[data-session-id]');
  if (sessionButton) selectAgentSession(sessionButton.dataset.sessionId);
  const worktreeButton = event.target.closest('[data-worktree-id]');
  if (worktreeButton) selectWorktreeTask(worktreeButton.dataset.worktreeId);
  const terminalHistoryButton = event.target.closest('[data-terminal-history-index]');
  if (terminalHistoryButton) {
    const command = terminalHistory[Number(terminalHistoryButton.dataset.terminalHistoryIndex)] || '';
    if (command) {
      $('terminalCommand').value = command;
      activateEditorTab('terminal');
      renderTerminalDecision(null, 'Command loaded from history; classify before executing.');
    }
    return;
  }
  const sourceplanOp = event.target.closest('[data-sourceplan-op]');
  if (sourceplanOp) toggleSourcePlanOperation(sourceplanOp.dataset.sourceplanOp);
  const tab = event.target.closest('[data-editor-tab]');
  if (tab) {
    activateEditorTab(tab.dataset.editorTab);
  }
});

document.addEventListener('keydown', event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
    event.preventDefault();
    saveViaSourcePlan();
    return;
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault();
    focusCommandPalette();
    return;
  }
  if (event.key === 'Escape' && !$('commandPaletteOverlay').classList.contains('hidden')) {
    closeCommandPaletteModal();
    return;
  }
  if (['INPUT', 'TEXTAREA'].includes(event.target.tagName)) return;
  const shortcuts = {
    1: 'mission',
    2: 'source',
    3: 'agents',
    4: 'worktrees',
    5: 'evidence',
    6: 'terminal',
    7: 'providers',
    8: 'tooling',
    9: 'doctor',
  };
  if (shortcuts[event.key]) {
    event.preventDefault();
    setDesktopPage(shortcuts[event.key]);
  }
});

$('chooseWorkspace').addEventListener('click', async () => {
  const selected = await window.beastDesktop.chooseWorkspace();
  if (selected) {
    workspaceRoot = selected;
    restoredWorkspaceRoot = '';
    currentAgentSession = null;
    currentWorktreeTask = null;
    openFiles = [];
    currentFile = '';
    dirtyFiles.clear();
    collapsedFolders = new Set();
    if ($('fileFilter')) $('fileFilter').value = '';
    if ($('workspacePath')) $('workspacePath').textContent = workspaceRoot;
    if ($('activeFile')) $('activeFile').textContent = 'No file selected';
    if ($('fileList')) $('fileList').innerHTML = `<div class="mini-card muted">Loading workspace files...</div>`;
    resetIdeEventStream();
    resetAgentRunStream();
    await refreshSnapshot({ force: true });
    saveWorkspaceState();
  }
});
$('refreshSnapshot').addEventListener('click', () => refreshSnapshot({ force: true }));
$('restartGateway').addEventListener('click', async () => { await window.beastDesktop.restartGateway(); await refreshSnapshot({ force: true }); });
$('openCommandPalette').addEventListener('click', focusCommandPalette);
$('refreshCommandPalette').addEventListener('click', () => refreshActionManifest().catch(error => log(`Action refresh failed: ${error.message || error}`)));
$('clearCommandPalette').addEventListener('click', () => {
  $('commandPaletteSearch').value = '';
  $('commandPaletteModalSearch').value = '';
  renderCommandPalette();
});
$('commandPaletteSearch').addEventListener('input', () => syncCommandPaletteSearch(false));
$('commandPaletteModalSearch').addEventListener('input', () => syncCommandPaletteSearch(true));
$('closeCommandPalette').addEventListener('click', closeCommandPaletteModal);
$('commandPaletteOverlay').addEventListener('click', event => {
  if (event.target.id === 'commandPaletteOverlay') closeCommandPaletteModal();
});
$('doctorRestartGateway').addEventListener('click', async () => { await window.beastDesktop.restartGateway(); await refreshSnapshot({ force: true }); setDesktopPage('doctor'); });
$('copyDoctorReport').addEventListener('click', copyDoctorReport);
$('openGatewayBrowser').addEventListener('click', () => window.beastDesktop.openGateway?.());
$('fileFilter').addEventListener('input', renderFileExplorer);
$('expandExplorer').addEventListener('click', () => {
  collapsedFolders.clear();
  explorerFlatMode = false;
  renderFileExplorer();
  saveWorkspaceState();
});
$('collapseExplorer').addEventListener('click', () => {
  const collect = node => {
    node.folders.forEach(folder => {
      collapsedFolders.add(folder.path);
      collect(folder);
    });
  };
  collect(buildFileTree(explorerRows));
  explorerFlatMode = false;
  renderFileExplorer();
  saveWorkspaceState();
});
$('toggleExplorerMode').addEventListener('click', () => {
  explorerFlatMode = !explorerFlatMode;
  renderFileExplorer();
  saveWorkspaceState();
});
$('revealActiveFile').addEventListener('click', () => {
  if (!currentFile) return;
  const parts = currentFile.split('/').filter(Boolean);
  let prefix = '';
  for (const part of parts.slice(0, -1)) {
    prefix = prefix ? `${prefix}/${part}` : part;
    collapsedFolders.delete(prefix);
  }
  explorerFlatMode = false;
  renderFileExplorer();
  const target = Array.from(document.querySelectorAll('[data-path]')).find(node => node.dataset.path === currentFile);
  target?.scrollIntoView({ block: 'center' });
  saveWorkspaceState();
});
$('refreshSymbolOutline').addEventListener('click', refreshSymbolOutline);
$('askSymbolAgent').addEventListener('click', askAgentAboutSymbol);
$('runSymbolSearch').addEventListener('click', runSymbolSearch);
$('openSymbolSearchResult').addEventListener('click', openSelectedSymbolSearchResult);
$('askSymbolSearchAgent').addEventListener('click', askAgentAboutSymbolSearchResult);
$('goToDefinition').addEventListener('click', goToDefinition);
$('findReferences').addEventListener('click', findReferences);
$('relatedTestsRoutes').addEventListener('click', relatedTestsRoutes);
$('symbolSearchQuery').addEventListener('keydown', event => {
  if (event.key === 'Enter') {
    event.preventDefault();
    runSymbolSearch();
  }
});
$('saveViaSourcePlan').addEventListener('click', saveViaSourcePlan);
$('newWorkspaceFile').addEventListener('click', createWorkspaceFile);
$('renameWorkspaceFile').addEventListener('click', renameWorkspaceFile);
$('deleteWorkspaceFile').addEventListener('click', deleteWorkspaceFile);
$('undoEdit').addEventListener('click', undoEdit);
$('redoEdit').addEventListener('click', redoEdit);
$('toggleSplitEditor').addEventListener('click', toggleSplitEditor);
$('revertEditorBuffer').addEventListener('click', revertEditorBuffer);
$('reloadActiveFile').addEventListener('click', () => reloadActiveFileFromDisk(false));
$('closeFileTab').addEventListener('click', () => closeEditorTab(currentFile));
$('editorText').addEventListener('input', () => {
  if (monacoEditor && monacoEditor.getValue() !== $('editorText').value) {
    monacoEditor.setValue($('editorText').value);
  }
  diffCurrentEdit();
});
$('editorText').addEventListener('keyup', updateEditorMeta);
$('editorText').addEventListener('click', updateEditorMeta);
$('editorText').addEventListener('select', updateEditorMeta);
$('sourcePlanFromEdit').addEventListener('click', sourcePlanDraft);
$('sourcePlanFromSelection').addEventListener('click', sourcePlanSelectionDraft);
$('createAgent').addEventListener('click', createAgentSession);
$('createWorktree').addEventListener('click', createWorktreeMission);
$('pauseAgent').addEventListener('click', () => updateAgentSessionStatus('paused'));
$('resumeAgent').addEventListener('click', () => updateAgentSessionStatus('active'));
$('cancelAgent').addEventListener('click', () => updateAgentSessionStatus('cancelled'));
$('sendAgentPrompt').addEventListener('click', sendAgentPrompt);
$('runAgentStream').addEventListener('click', () => runAgentStream());
$('saveAgentOutput').addEventListener('click', saveAgentOutput);
$('agentOutputSourcePlan').addEventListener('click', () => {
  if ($('agentProposedText').value.trim()) compileAgentPatchSourcePlan();
  else agentOutputToSourcePlan();
});
$('agentAskSelection').addEventListener('click', askAgentAboutSelection);
$('agentRefreshContext').addEventListener('click', () => {
  refreshRelatedContext().finally(renderAgentContextPack);
});
$('agentClearOutput').addEventListener('click', () => { $('agentOutputText').value = ''; });
$('agentExtractPatch').addEventListener('click', extractAgentPatchCandidate);
$('agentPreviewPatch').addEventListener('click', previewAgentPatch);
$('agentCompilePatch').addEventListener('click', compileAgentPatchSourcePlan);
$('agentStagePatch').addEventListener('click', stageAgentPatchBuffer);
$('agentRequestPatch').addEventListener('click', requestAgentPatchForSelection);
$('agentClearPatch').addEventListener('click', () => {
  $('agentProposedText').value = '';
  pendingAgentPatch = null;
  setAgentPatchStatus('Patch cleared. Select code, then extract or paste replacement text.', 'muted');
});
$('agentPatchToSource').addEventListener('click', () => setDesktopPage('source'));
$('clearAgentPrompt').addEventListener('click', () => { $('agentPromptText').value = ''; });
$('copyAgentOutput').addEventListener('click', copyAgentOutput);
$('agentPromptText').addEventListener('input', renderAgentContextPack);
['agentIncludeActiveFile', 'agentIncludeSelection', 'agentIncludeRelated'].forEach(id => {
  $(id).addEventListener('change', renderAgentContextPack);
});
$('agentPromptText').addEventListener('keydown', event => {
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
    event.preventDefault();
    sendAgentPrompt();
  }
});
$('providerSelect').addEventListener('change', () => {
  saveProviderSetup($('providerSelect').value, $('providerModel').value.trim());
  refreshProviderSetup().catch(error => log(`Provider refresh failed: ${error.message || error}`));
});
$('providerModel').addEventListener('input', () => saveProviderSetup($('providerSelect').value, $('providerModel').value.trim()));
$('refreshProviders').addEventListener('click', refreshProviderSetup);
$('useNvidiaProvider').addEventListener('click', () => {
  saveProviderSetup('nvidia_nim', DEFAULT_NVIDIA_NIM_MODEL);
  refreshProviderSetup().catch(error => log(`Provider refresh failed: ${error.message || error}`));
});
$('smokeNvidiaProvider').addEventListener('click', smokeNvidiaProvider);
$('copyProviderSetup').addEventListener('click', copyProviderSetup);
$('providerAgentPage').addEventListener('click', () => setDesktopPage('agents'));
$('providerDoctorPage').addEventListener('click', () => setDesktopPage('doctor'));
$('refreshTooling').addEventListener('click', refreshToolingSnapshot);
$('runSyntaxCheck').addEventListener('click', runSyntaxToolingCheck);
$('runLintCheck').addEventListener('click', showLintToolingContract);
$('openMcpPanel').addEventListener('click', focusMcpTooling);
$('openPluginPanel').addEventListener('click', focusPluginTooling);
$('openEnvironmentPanel').addEventListener('click', focusEnvironmentTooling);
$('refreshMcpOps').addEventListener('click', refreshMcpOps);
$('approveMcpRequest').addEventListener('click', () => resolveMcpApproval('approve'));
$('denyMcpRequest').addEventListener('click', () => resolveMcpApproval('deny'));
$('refreshPluginOps').addEventListener('click', refreshPluginOps);
$('validatePluginManifest').addEventListener('click', validatePluginManifest);
$('runBenchmarkGrading').addEventListener('click', runBenchmarkGradingDaemon);
$('copyBenchmarkVerdict').addEventListener('click', copyBenchmarkVerdict);
$('copyToolingReport').addEventListener('click', copyToolingReport);
$('refreshSystem').addEventListener('click', refreshSystemSnapshot);
$('refreshSystemPorts').addEventListener('click', refreshSystemPorts);
$('refreshSystemProcesses').addEventListener('click', refreshSystemProcesses);
$('refreshSystemEnvironment').addEventListener('click', refreshSystemEnvironment);
$('refreshSystemPackages').addEventListener('click', refreshSystemPackages);
$('refreshSystemExtensions').addEventListener('click', refreshSystemExtensions);
$('refreshSystemCatalog').addEventListener('click', refreshSystemCatalog);
$('freeSystemPortBtn').addEventListener('click', () => freeSystemPort());
$('copySystemReport').addEventListener('click', copySystemReport);
$('systemProcessQuery').addEventListener('keydown', event => { if (event.key === 'Enter') refreshSystemProcesses(); });
$('verifySourcePlan').addEventListener('click', verifySourcePlan);
$('applySourcePlan').addEventListener('click', applySourcePlan);
$('clearSourcePlan').addEventListener('click', clearSourcePlan);
$('selectAllSourceOps').addEventListener('click', () => setSourcePlanOperationSelection('all'));
$('selectNoSourceOps').addEventListener('click', () => setSourcePlanOperationSelection('none'));
$('reloadForSourcePlan').addEventListener('click', reloadBaseForSourcePlan);
$('editSourcePlanOp').addEventListener('click', editSelectedSourcePlanOperation);
$('moveSourcePlanOpUp').addEventListener('click', () => moveSelectedSourcePlanOperation(-1));
$('moveSourcePlanOpDown').addEventListener('click', () => moveSelectedSourcePlanOperation(1));
$('rebaseSourcePlan').addEventListener('click', rebaseSourcePlanAgainstDisk);
$('showRollbackPreview').addEventListener('click', () => renderRollbackPreview());
$('showApplyTimeline').addEventListener('click', () => renderApplyTimeline());
$('exportMissionRunbook').addEventListener('click', exportMissionRunbook);
$('verifyMissionRunbook').addEventListener('click', verifyMissionRunbook);
$('chooseSourceReceipt').addEventListener('click', () => chooseReceiptsForAction('sourceplan.apply'));
$('copySourceRunbook').addEventListener('click', copySourceRunbook);
$('createHandoffPackage').addEventListener('click', createHandoffPackage);
$('proposeLearning').addEventListener('click', proposeLearning);
$('checkReleaseReadiness').addEventListener('click', checkReleaseReadiness);

// Inference Monitor stubs — wired to gateway when available
$('refreshInferenceStats').addEventListener('click', async () => {
  const nodes = { ctx: $('contextWindowStats'), kv: $('kvCacheStats'), comp: $('compressionStats'), budget: $('tokenBudgetStats') };
  if (desktopLocalMode || !lastGatewayStatus?.health?.ok) {
    nodes.kv.textContent = 'Gateway offline — KV cache stats unavailable.';
    nodes.comp.textContent = 'Gateway offline — compression stats unavailable.';
    return;
  }
  try {
    const data = await getJson(`/edgek/providers/inference-stats?root_path=${encodeURIComponent(workspaceRoot)}`);
    nodes.ctx.textContent = data.context_window ? `${data.context_window.used_tokens ?? '?'} / ${data.context_window.max_tokens ?? '?'} tokens` : 'No context window data.';
    nodes.kv.textContent = data.kv_cache ? `hit rate: ${data.kv_cache.hit_rate ?? 'n/a'} · size: ${data.kv_cache.size_mb ?? '?'} MB · entries: ${data.kv_cache.entries ?? '?'}` : 'KV cache not reported by this provider.';
    nodes.comp.textContent = data.compression ? `mode: ${data.compression.mode ?? 'none'} · ratio: ${data.compression.ratio ?? 'n/a'} · savings: ${data.compression.tokens_saved ?? '?'} tokens` : 'No compression active.';
    nodes.budget.textContent = data.token_budget ? `used: ${data.token_budget.used ?? '?'} · limit: ${data.token_budget.limit ?? '?'} · remaining: ${data.token_budget.remaining ?? '?'}` : 'No budget configured.';
  } catch (error) {
    nodes.kv.textContent = `Stats unavailable: ${error.message || error}`;
    log(`Inference stats unavailable: ${error.message || error}`);
  }
});
$('clearKvCache').addEventListener('click', async () => {
  if (!lastGatewayStatus?.health?.ok) { log('Clear KV cache: gateway offline.'); return; }
  try {
    await postJson('/edgek/providers/kv-cache/clear', { root_path: workspaceRoot });
    $('kvCacheStats').textContent = 'KV cache cleared.';
    log('KV cache cleared.');
  } catch (error) { log(`Clear KV cache failed: ${error.message || error}`); }
});
$('toggleCompression').addEventListener('click', async () => {
  const current = $('compressionStats').textContent || '';
  const enable = current.includes('none') || current.includes('No compression');
  if (!lastGatewayStatus?.health?.ok) { log('Toggle compression: gateway offline.'); return; }
  try {
    await postJson('/edgek/providers/compression/toggle', { root_path: workspaceRoot, enable });
    $('compressionStats').textContent = `Compression ${enable ? 'enabled' : 'disabled'}. Refresh to see stats.`;
    log(`Compression ${enable ? 'enabled' : 'disabled'}.`);
  } catch (error) { log(`Toggle compression failed: ${error.message || error}`); }
});

$('testWorktree').addEventListener('click', testWorktreeMission);
$('draftWorktreePlan').addEventListener('click', draftWorktreeSourcePlan);
$('closeWorktree').addEventListener('click', closeWorktreeMission);
$('openWorktreeWindow').addEventListener('click', openWorktreeWindow);
$('browseWorktreeDiff').addEventListener('click', browseWorktreeDiff);
$('worktreePromotionWizard').addEventListener('click', runWorktreePromotionWizard);
$('classifyCommand').addEventListener('click', classifyTerminalCommand);
$('executeCommand').addEventListener('click', executeTerminalCommand);
$('cancelCommand').addEventListener('click', cancelTerminalCommand);
$('terminalUseWorkspaceCwd').addEventListener('click', () => { $('terminalCwd').value = workspaceRoot || ''; });
$('terminalClearLog').addEventListener('click', () => { $('terminalLog').textContent = 'Terminal log cleared. Gateway logs will append here.'; });
$('terminalCopyLastReceipt').addEventListener('click', copyLastTerminalReceipt);
$('terminalRerunLast').addEventListener('click', () => {
  const command = lastTerminalExecution?.command || terminalHistory[0] || '';
  if (!command) return;
  $('terminalCommand').value = command;
  activateEditorTab('terminal');
  classifyTerminalCommand();
});
$('terminalClearHistory').addEventListener('click', () => {
  terminalHistory = [];
  terminalHistoryIndex = 0;
  localStorage.removeItem(terminalHistoryStorageKey());
  renderTerminalHistory();
});
$('terminalEvidenceFilter').addEventListener('click', applyTerminalEvidenceFilter);
$('terminalCommand').addEventListener('keydown', event => {
  if (event.key === 'Enter') {
    event.preventDefault();
    classifyTerminalCommand();
  } else if (event.key === 'ArrowUp') {
    event.preventDefault();
    terminalHistoryIndex = Math.min(terminalHistory.length - 1, Math.max(0, terminalHistoryIndex - 1));
    $('terminalCommand').value = terminalHistory[terminalHistoryIndex] || $('terminalCommand').value;
  } else if (event.key === 'ArrowDown') {
    event.preventDefault();
    terminalHistoryIndex = Math.min(terminalHistory.length, terminalHistoryIndex + 1);
    $('terminalCommand').value = terminalHistory[terminalHistoryIndex] || '';
  }
});
$('searchEvidence').addEventListener('click', () => searchEvidenceDrawer('query'));
$('relatedEvidence').addEventListener('click', () => searchEvidenceDrawer('related'));
$('clearEvidenceFilters').addEventListener('click', clearEvidenceFilters);
$('chooseEvidenceReceipt').addEventListener('click', () => chooseReceiptsForAction('sourceplan.apply'));
$('exportEvidenceRunbook').addEventListener('click', exportMissionRunbook);
$('terminalEvidenceShortcut').addEventListener('click', () => setDesktopPage('evidence'));
// command bar wiring (new OPCB command bar)
if ($('commandBarInput')) {
  $('commandBarInput').addEventListener('keydown', event => {
    if (event.key === 'Enter') {
      const val = $('commandBarInput').value.trim();
      if (!val) return;
      $('commandPaletteModalSearch').value = val;
      $('commandPaletteSearch').value = val;
      syncCommandPaletteSearch(false);
      focusCommandPalette();
      $('commandBarInput').value = '';
    }
  });
}
if ($('commandBarSend')) {
  $('commandBarSend').addEventListener('click', () => {
    const val = $('commandBarInput')?.value?.trim();
    if (!val) { focusCommandPalette(); return; }
    $('commandPaletteModalSearch').value = val;
    $('commandPaletteSearch').value = val;
    syncCommandPaletteSearch(false);
    focusCommandPalette();
    if ($('commandBarInput')) $('commandBarInput').value = '';
  });
}
if ($('commandChipRefresh')) $('commandChipRefresh').addEventListener('click', () => refreshSnapshot({ force: true }));
if ($('commandChipPalette')) $('commandChipPalette').addEventListener('click', focusCommandPalette);
// cube zone tab buttons
if ($('cmdTabCommand')) {
  [$('cmdTabCommand'), $('cmdTabRunbook'), $('cmdTabNotes')].filter(Boolean).forEach(btn => {
    btn.addEventListener('click', () => {
      [$('cmdTabCommand'), $('cmdTabRunbook'), $('cmdTabNotes')].filter(Boolean).forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
    });
  });
}
window.beastDesktop.onGatewayLog(lines => {
  if (lastTerminalExecution) return;
  $('terminalLog').textContent = lines.join('\n');
});
window.beastDesktop.onWorkspaceSelected(async selected => { saveWorkspaceState(); workspaceRoot = selected; restoredWorkspaceRoot = ''; currentAgentSession = null; currentWorktreeTask = null; resetIdeEventStream(); resetAgentRunStream(); await refreshSnapshot({ force: true }); });
window.beastDesktop.onRefresh(() => refreshSnapshot({ force: false }));

refreshSnapshot().catch(error => {
  log(`startup failed: ${error.message || error}`);
  refreshStatus();
});
initMonaco().then(() => {
  if (!currentFile && monacoEditor) monacoEditor.setValue('// Select a file from the explorer. Edits are staged into BEAST SourcePlan, not written directly.');
});
initSplitters();
syncProviderControls();
setDesktopPage('mission');
