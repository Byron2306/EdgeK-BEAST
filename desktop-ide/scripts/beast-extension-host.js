#!/usr/bin/env node
'use strict';

// Extensions execute inside a VM with an intentionally small, serializable
// vscode-compatible surface. This host owns filesystem mediation and never
// exposes process, sockets, arbitrary child-process access, or raw fs.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { TextDecoder, TextEncoder } = require('util');

const CAPABILITIES = new Set(['workspace.read', 'workspace.write', 'language.client', 'terminal.execute', 'network.loopback']);
const ID = /^[a-z0-9][a-z0-9._-]{1,95}$/i;
const COMMAND_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{1,160}$/;
const SAFE_BUILTINS = new Set(['path', 'util']);
const ACTION_KINDS = new Set(['navigate', 'notice', 'command', 'webview', 'tree', 'status', 'watcher', 'config', 'task', 'terminal', 'language', 'debug', 'storage', 'secret']);
const EXTENSION_FILE_LIMIT = 128 * 1024;
const activatedRegistry = new Map();
let buffer = '';
let pending = 0;
let inputEnded = false;
let untitledDocumentSeq = 0;

function send(value) { process.stdout.write(`${JSON.stringify(value)}\n`); }
function readJson(file) { try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch (_) { return null; } }
function boundedArray(value, limit = 120) { return Array.isArray(value) ? value.slice(0, limit) : []; }
function cloneJson(value) { return value === undefined ? undefined : JSON.parse(JSON.stringify(value)); }
function countContribution(value) {
  if (Array.isArray(value)) return value.length;
  if (value && typeof value === 'object') return Object.keys(value).length;
  return 0;
}
function sanitizeContribution(value, limit = 80) {
  if (Array.isArray(value)) return value.map(item => cloneJson(item)).slice(0, limit);
  if (!value || typeof value !== 'object') return value == null ? undefined : cloneJson(value);
  const result = {};
  for (const key of Object.keys(value).slice(0, limit)) result[String(key).slice(0, 120)] = cloneJson(value[key]);
  return result;
}
function normalizeManifest(raw, file, origin, kind) {
  if (!raw) return null;
  const idValue = String(raw.id || (raw.publisher && raw.name ? `${raw.publisher}.${raw.name}` : raw.name) || '');
  if (!ID.test(idValue)) return null;
  const requested = [...new Set(boundedArray(raw.capabilities).map(String).filter(capability => CAPABILITIES.has(capability)))];
  const rawCommands = boundedArray(raw.contributes?.commands);
  const commands = rawCommands.map(item => ({
    id: String(item?.id || item?.command || ''),
    title: String(item?.title || item?.command || item?.id || ''),
    category: item?.category ? String(item.category).slice(0, 80) : '',
  })).filter(item => COMMAND_ID.test(item.id) && item.title).slice(0, 120);
  const contributes = {
    commands,
    views: sanitizeContribution(raw.contributes?.views),
    viewsContainers: sanitizeContribution(raw.contributes?.viewsContainers),
    menus: sanitizeContribution(raw.contributes?.menus),
    configuration: sanitizeContribution(raw.contributes?.configuration),
    languages: sanitizeContribution(raw.contributes?.languages),
    debuggers: sanitizeContribution(raw.contributes?.debuggers),
    taskDefinitions: sanitizeContribution(raw.contributes?.taskDefinitions),
    themes: sanitizeContribution(raw.contributes?.themes),
    grammars: sanitizeContribution(raw.contributes?.grammars),
    jsonValidation: sanitizeContribution(raw.contributes?.jsonValidation),
  };
  const contributionSummary = Object.freeze({
    commands: commands.length,
    views: countContribution(contributes.views),
    viewsContainers: countContribution(contributes.viewsContainers),
    menus: countContribution(contributes.menus),
    configuration: countContribution(contributes.configuration),
    languages: countContribution(contributes.languages),
    debuggers: countContribution(contributes.debuggers),
    taskDefinitions: countContribution(contributes.taskDefinitions),
    themes: countContribution(contributes.themes),
    grammars: countContribution(contributes.grammars),
    jsonValidation: countContribution(contributes.jsonValidation),
  });
  const main = typeof raw.main === 'string' && /^[A-Za-z0-9._/-]{1,180}$/.test(raw.main) && !raw.main.split('/').includes('..') ? raw.main : '';
  const activationEvents = boundedArray(raw.activationEvents).map(String).filter(item => item.length <= 180).slice(0, 120);
  const extensionDependencies = boundedArray(raw.extensionDependencies, 80).map(String).filter(item => ID.test(item)).slice(0, 80);
  const extensionPack = boundedArray(raw.extensionPack, 80).map(String).filter(item => ID.test(item)).slice(0, 80);
  return {
    id: idValue,
    name: String(raw.displayName || raw.name || idValue).slice(0, 120),
    version: String(raw.version || '0.0.0').slice(0, 40),
    description: String(raw.description || '').slice(0, 500),
    capabilities: requested,
    contributes,
    contributionSummary,
    activationEvents,
    extensionDependencies,
    extensionPack,
    origin,
    manifest: file,
    manifestKind: kind,
    main,
    root: path.dirname(file),
    compatibility: kind === 'package.json' ? 'vscode-package-json' : 'beast-extension-json',
  };
}
function manifestAt(folder, origin) {
  const beast = path.join(folder, 'beast-extension.json');
  const vscode = path.join(folder, 'package.json');
  return normalizeManifest(readJson(beast), beast, origin, 'beast-extension.json') || normalizeManifest(readJson(vscode), vscode, origin, 'package.json');
}
function discover(roots) {
  const extensions = [];
  const seen = new Set();
  for (const item of Array.isArray(roots) ? roots : []) {
    const root = path.resolve(String(item?.path || ''));
    const origin = String(item?.origin || 'workspace');
    let entries = [];
    try { entries = fs.readdirSync(root, { withFileTypes: true }); } catch (_) { continue; }
    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      const extension = manifestAt(path.join(root, entry.name), origin);
      if (extension && !seen.has(extension.id)) { seen.add(extension.id); extensions.push(extension); }
    }
  }
  return extensions.sort((a, b) => a.name.localeCompare(b.name));
}
function extensionPath(extension, relative) {
  const target = path.resolve(extension.root, String(relative || ''));
  if (target !== extension.root && !target.startsWith(`${extension.root}${path.sep}`)) throw new Error('Extension asset path escaped its package.');
  return target;
}
function readExtensionSource(file, label) {
  const stat = fs.statSync(file);
  if (!stat.isFile() || stat.size > EXTENSION_FILE_LIMIT) throw new Error(`${label} exceeds the ${EXTENSION_FILE_LIMIT / 1024} KiB sandbox limit.`);
  return fs.readFileSync(file, 'utf8');
}
function candidateModuleFiles(base) {
  const normalized = path.resolve(base);
  const candidates = [normalized];
  if (!path.extname(normalized)) {
    candidates.push(`${normalized}.js`, `${normalized}.json`, path.join(normalized, 'index.js'), path.join(normalized, 'index.json'));
  }
  return [...new Set(candidates)];
}
function resolvePackageEntry(packageRoot, entry = '') {
  const normalized = String(entry || '').trim();
  const base = normalized && normalized !== '.' ? path.resolve(packageRoot, normalized) : path.join(packageRoot, 'index.js');
  for (const candidate of candidateModuleFiles(base)) {
    if (candidate === packageRoot || candidate.startsWith(`${packageRoot}${path.sep}`)) {
      try {
        const stat = fs.statSync(candidate);
        if (stat.isFile()) return candidate;
      } catch (_) {}
    }
  }
  throw new Error(`Extension package entrypoint is missing: ${normalized || 'index.js'}`);
}
function packageExportTarget(exportsField, subpath) {
  if (typeof exportsField === 'string') return exportsField;
  if (!exportsField || typeof exportsField !== 'object') return '';
  const direct = subpath === '.' ? exportsField['.'] ?? exportsField.default ?? '' : exportsField[subpath] ?? '';
  if (typeof direct === 'string') return direct;
  if (direct && typeof direct === 'object') {
    return direct.require || direct.default || direct.node || '';
  }
  if (subpath === '.' && typeof exportsField.require === 'string') return exportsField.require;
  if (subpath === '.' && typeof exportsField.default === 'string') return exportsField.default;
  return '';
}
function globToRegExp(pattern) {
  const raw = String(pattern || '**/*').replace(/\\/g, '/');
  let expression = '';
  for (let index = 0; index < raw.length; index += 1) {
    const char = raw[index];
    if (char === '*' && raw[index + 1] === '*') {
      if (raw[index + 2] === '/') { expression += '(?:.*/)?'; index += 2; } else { expression += '.*'; index += 1; }
    } else if (char === '*') expression += '[^/]*';
    else if (char === '?') expression += '[^/]';
    else expression += /[.+^${}()|[\]\\]/.test(char) ? `\\${char}` : char;
  }
  return new RegExp(`^${expression}$`);
}
function workspaceContains(workspaceRoot, pattern) {
  const matcher = globToRegExp(pattern);
  const skip = new Set(['.git', '.beast', 'node_modules', '.venv', 'venv', 'dist', 'build', '__pycache__']);
  let checked = 0;
  const walk = folder => {
    if (checked > 5000) return false;
    let entries = [];
    try { entries = fs.readdirSync(folder, { withFileTypes: true }); } catch (_) { return false; }
    for (const entry of entries) {
      if (skip.has(entry.name)) continue;
      const full = path.join(folder, entry.name);
      const rel = path.relative(workspaceRoot, full).split(path.sep).join('/');
      checked += 1;
      if (matcher.test(rel)) return true;
      if (entry.isDirectory() && walk(full)) return true;
    }
    return false;
  };
  return walk(workspaceRoot);
}
function activationMatches(extension, activationEvent, message) {
  const requested = String(activationEvent || 'onStartupFinished');
  const events = Array.isArray(extension.activationEvents) ? extension.activationEvents : [];
  if (events.includes('*') || events.includes(requested)) return true;
  if (requested.startsWith('onCommand:')) return events.includes(requested);
  if (requested.startsWith('onLanguage:')) {
    const language = requested.slice('onLanguage:'.length);
    return events.includes(`onLanguage:${language}`) || (extension.contributes?.languages || []).some(item => String(item?.id || '') === language);
  }
  if (requested.startsWith('onView:')) {
    const viewId = requested.slice('onView:'.length);
    const views = extension.contributes?.views && typeof extension.contributes.views === 'object' ? Object.values(extension.contributes.views).flatMap(value => Array.isArray(value) ? value : []) : [];
    return events.includes(`onView:${viewId}`) || views.some(item => String(item?.id || '') === viewId);
  }
  if (requested.startsWith('onDebug:')) {
    const debugType = requested.slice('onDebug:'.length);
    return events.includes(`onDebug:${debugType}`) || (extension.contributes?.debuggers || []).some(item => String(item?.type || '') === debugType);
  }
  if (requested.startsWith('onTaskType:')) {
    const taskType = requested.slice('onTaskType:'.length);
    return events.includes(`onTaskType:${taskType}`) || (extension.contributes?.taskDefinitions || []).some(item => String(item?.type || '') === taskType);
  }
  if (requested === 'onStartupFinished') return events.includes('onStartupFinished');
  if (requested === 'workspaceContains') {
    const workspaceRoot = path.resolve(String(message.workspaceRoot || ''));
    return events.some(event => event.startsWith('workspaceContains:') && workspaceContains(workspaceRoot, event.slice('workspaceContains:'.length)));
  }
  return false;
}
function safeStateFile(workspaceRoot, extensionId, name) {
  const safeId = String(extensionId || '').replace(/[^A-Za-z0-9._-]/g, '_').slice(0, 120);
  const target = path.resolve(workspaceRoot, '.beast', 'extension-runtime', safeId, `${name}.json`);
  if (!target.startsWith(`${path.resolve(workspaceRoot)}${path.sep}.beast${path.sep}extension-runtime${path.sep}`)) throw new Error('Extension runtime state path escaped its workspace.');
  return target;
}
function readStateFile(file, fallback) {
  try {
    const stat = fs.statSync(file);
    if (!stat.isFile() || stat.size > 512 * 1024) return fallback;
    const value = JSON.parse(fs.readFileSync(file, 'utf8'));
    return value && typeof value === 'object' ? value : fallback;
  } catch (_) {
    return fallback;
  }
}
function writeStateFile(file, value) {
  const text = `${JSON.stringify(value, null, 2)}\n`;
  if (Buffer.byteLength(text, 'utf8') > 512 * 1024) throw new Error('Extension runtime state exceeded the 512 KiB limit.');
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  const tmp = `${file}.${process.pid}.${Date.now()}.tmp`;
  fs.writeFileSync(tmp, text, { encoding: 'utf8', mode: 0o600 });
  fs.renameSync(tmp, file);
}
function createMemento(kind, file, emit) {
  const persisted = readStateFile(file, {});
  const store = new Map(Object.entries(persisted));
  return Object.freeze({
    get: (key, fallback) => store.has(String(key)) ? store.get(String(key)) : fallback,
    update: async (key, value) => { store.set(String(key), cloneJson(value)); writeStateFile(file, Object.fromEntries(store.entries())); emit('storage', { scope: kind, key: String(key).slice(0, 160), size: JSON.stringify(value ?? null).length, persisted: true }); },
    keys: () => [...store.keys()],
  });
}
function createEmitter(disposable) {
  return new class {
    constructor() { this.listeners = []; this.event = listener => { this.listeners.push(listener); return disposable(() => { this.listeners = this.listeners.filter(item => item !== listener); }); }; }
    fire(value) { for (const listener of this.listeners.slice()) listener(value); }
    dispose() { this.listeners = []; }
  }();
}
function createSimpleDisposable(dispose) {
  return Object.freeze({ dispose: typeof dispose === 'function' ? dispose : () => {} });
}
function summarizeActions(actions = []) {
  const summary = {
    actionCount: 0,
    kinds: {},
    commands: [],
    webviews: [],
    trees: [],
    statuses: [],
    watchers: 0,
    tasks: 0,
    terminals: 0,
    languages: [],
    debuggers: [],
    configs: 0,
    storageWrites: 0,
    secretWrites: 0,
  };
  for (const action of Array.isArray(actions) ? actions : []) {
    const kind = String(action?.kind || '');
    const payload = action && typeof action.payload === 'object' ? action.payload : {};
    if (!kind) continue;
    summary.actionCount += 1;
    summary.kinds[kind] = Number(summary.kinds[kind] || 0) + 1;
    if (kind === 'command' && payload.id) summary.commands.push(String(payload.id).slice(0, 160));
    if (kind === 'webview' && (payload.viewType || payload.title)) summary.webviews.push({ viewType: String(payload.viewType || '').slice(0, 160), title: String(payload.title || '').slice(0, 200) });
    if (kind === 'tree' && payload.id) summary.trees.push({ id: String(payload.id).slice(0, 160), provider: Boolean(payload.provider), refresh: Boolean(payload.refresh) });
    if (kind === 'status' && payload.id) summary.statuses.push({ id: String(payload.id).slice(0, 160), text: String(payload.text || '').slice(0, 160), hidden: Boolean(payload.hidden) });
    if (kind === 'watcher' && payload.created) summary.watchers += 1;
    if (kind === 'task' && (payload.provider || payload.execute)) summary.tasks += 1;
    if (kind === 'terminal' && (payload.created || payload.command || payload.text)) summary.terminals += 1;
    if (kind === 'language' && payload.feature) summary.languages.push(String(payload.feature).slice(0, 160));
    if (kind === 'debug' && payload.type) summary.debuggers.push(String(payload.type).slice(0, 120));
    if (kind === 'config') summary.configs += 1;
    if (kind === 'storage' && payload.persisted) summary.storageWrites += 1;
    if (kind === 'secret' && payload.persisted && (payload.stored || payload.deleted)) summary.secretWrites += 1;
  }
  summary.commands = [...new Set(summary.commands)].slice(0, 20);
  summary.languages = [...new Set(summary.languages)].slice(0, 20);
  summary.debuggers = [...new Set(summary.debuggers)].slice(0, 20);
  summary.webviews = summary.webviews.slice(0, 12);
  summary.trees = summary.trees.slice(0, 12);
  summary.statuses = summary.statuses.slice(0, 12);
  return summary;
}
function createSandboxWebview(emit, panelOrView, title, options = {}) {
  let html = '';
  return Object.freeze({
    get html() { return html; },
    set html(value) {
      html = String(value || '').slice(0, 200000);
      emit('webview', { viewType: String(panelOrView || '').slice(0, 160), title: String(title || panelOrView || '').slice(0, 200), htmlBytes: Buffer.byteLength(html, 'utf8') });
    },
    postMessage: async message => { emit('webview', { viewType: String(panelOrView || '').slice(0, 160), postMessage: cloneJson(message ?? null) }); return true; },
    onDidReceiveMessage: createEmitter(createSimpleDisposable).event,
    asWebviewUri: value => Object.freeze({ scheme: 'file', fsPath: String(value?.fsPath || value?.path || value), path: String(value?.fsPath || value?.path || value), toString: () => `file://${String(value?.fsPath || value?.path || value)}` }),
    options: cloneJson(options || {}),
  });
}
function createMockFetch(message, emit) {
  const responses = message && typeof message.mockFetchResponses === 'object' && message.mockFetchResponses ? cloneJson(message.mockFetchResponses) : null;
  if (!responses) return fetch;
  return async (input, init = {}) => {
    const raw = typeof input === 'string' ? input : String(input?.url || '');
    const url = new URL(raw, 'http://127.0.0.1');
    const key = `${String(init?.method || 'GET').toUpperCase()} ${url.pathname}`;
    const entry = responses[key] || responses[url.pathname] || responses[raw];
    emit('command', { id: 'mock.fetch', url: `${url.pathname}${url.search}`, method: String(init?.method || 'GET').toUpperCase(), mocked: Boolean(entry) });
    if (!entry) throw new Error(`mock fetch has no response for ${key}`);
    const status = Number(entry.status || 200);
    const headers = new Map(Object.entries(entry.headers || { 'content-type': 'application/json' }));
    const body = entry.body == null ? '' : (typeof entry.body === 'string' ? entry.body : JSON.stringify(entry.body));
    return {
      ok: status >= 200 && status < 300,
      status,
      statusText: String(entry.statusText || ''),
      headers: { get: name => headers.get(String(name || '').toLowerCase()) || headers.get(String(name || '')) || null },
      json: async () => (typeof entry.body === 'string' ? JSON.parse(entry.body || 'null') : cloneJson(entry.body)),
      text: async () => body,
    };
  };
}
function createBuiltinShims(extension, runtime) {
  const workspaceRoot = path.resolve(String(runtime.context?.workspaceState ? runtime.context.storageUri?.fsPath || '' : ''));
  const safeHostPath = value => {
    const target = path.resolve(String(value || ''));
    const roots = [path.resolve(extension.root), path.resolve(String(runtime.context.extensionPath || extension.root)), path.resolve(String(runtime.context.globalStorageUri?.fsPath || extension.root)), path.resolve(String(runtime.context.storageUri?.fsPath || extension.root))];
    if (String(runtime.context.extensionPath || '').startsWith('/')) roots.push(path.resolve(path.dirname(String(runtime.context.extensionPath))));
    if (workspaceRoot) roots.push(path.resolve(path.dirname(workspaceRoot)));
    if (roots.some(root => target === root || target.startsWith(`${root}${path.sep}`))) return target;
    throw new Error(`Builtin fs path escaped the managed extension sandbox: ${target}`);
  };
  return Object.freeze({
    fs: Object.freeze({
      existsSync: value => { try { return fs.existsSync(safeHostPath(value)); } catch (_) { return false; } },
      statSync: value => fs.statSync(safeHostPath(value)),
      readFileSync: (value, encoding) => fs.readFileSync(safeHostPath(value), encoding),
      writeFileSync: (value, content, encoding) => fs.writeFileSync(safeHostPath(value), content, encoding),
      mkdirSync: (value, options) => fs.mkdirSync(safeHostPath(value), options),
    }),
    child_process: Object.freeze({
      execFile: (file, args = [], options = {}, callback) => {
        const payload = { file: String(file || '').slice(0, 240), args: Array.isArray(args) ? args.map(arg => String(arg).slice(0, 240)).slice(0, 40) : [], cwd: String(options?.cwd || '').slice(0, 240) };
        runtime.emit('terminal', { name: `${extension.id} execFile`, command: payload.file, args: payload.args, cwd: payload.cwd, blocked: true });
        const error = new Error('child_process.execFile is mediated and not executable inside the BEAST extension sandbox.');
        if (typeof callback === 'function') setImmediate(() => callback(error, '', ''));
        return Object.freeze({ pid: 0, kill: () => false });
      },
    }),
  });
}
function runtimeFor(extension, message, actions) {
  const workspaceRoot = path.resolve(String(message.workspaceRoot || ''));
  if (!workspaceRoot || !fs.existsSync(workspaceRoot) || !fs.statSync(workspaceRoot).isDirectory()) throw new Error('Extension workspace root is invalid.');
  const grants = new Set((Array.isArray(message.granted) ? message.granted : []).map(String).filter(capability => extension.capabilities.includes(capability) && CAPABILITIES.has(capability)));
  const emit = (kind, payload = {}) => { if (!ACTION_KINDS.has(String(kind))) throw new Error('Extension requested an unsupported mediated action'); actions.push({ kind: String(kind), payload }); };
  const globalStateFile = safeStateFile(workspaceRoot, extension.id, 'global-state');
  const workspaceStateFile = safeStateFile(workspaceRoot, extension.id, 'workspace-state');
  const secretsFile = safeStateFile(workspaceRoot, extension.id, 'secrets');
  const configFile = safeStateFile(workspaceRoot, extension.id, 'configuration');
  const initialConfiguration = message && typeof message.configuration === 'object' && message.configuration ? message.configuration : {};
  const configurationValues = new Map(Object.entries({ ...readStateFile(configFile, {}), ...cloneJson(initialConfiguration) }));
  const textDocuments = new Map();
  const activeEditorEmitter = createEmitter(createSimpleDisposable);
  const textDocumentEmitter = createEmitter(createSimpleDisposable);
  const workspaceFoldersEmitter = createEmitter(createSimpleDisposable);
  const configurationEmitter = createEmitter(createSimpleDisposable);
  const openTextDocumentEmitter = createEmitter(createSimpleDisposable);
  const closeTextDocumentEmitter = createEmitter(createSimpleDisposable);
  const saveTextDocumentEmitter = createEmitter(createSimpleDisposable);
  const createFilesEmitter = createEmitter(createSimpleDisposable);
  const deleteFilesEmitter = createEmitter(createSimpleDisposable);
  const renameFilesEmitter = createEmitter(createSimpleDisposable);
  const terminalOpenEmitter = createEmitter(createSimpleDisposable);
  const terminalCloseEmitter = createEmitter(createSimpleDisposable);
  const taskStartEmitter = createEmitter(createSimpleDisposable);
  const taskEndEmitter = createEmitter(createSimpleDisposable);
  const decorationTypes = new Map();
  const fileWatchers = [];
  const requireCapability = capability => { if (!grants.has(capability)) throw new Error(`Extension capability is not granted: ${capability}`); };
  const workspacePath = value => {
    const raw = typeof value === 'string' ? value : value?.fsPath || value?.path || '';
    const target = path.resolve(workspaceRoot, String(raw || ''));
    if (target === workspaceRoot || !target.startsWith(`${workspaceRoot}${path.sep}`)) throw new Error('Extension path escaped its workspace.');
    return target;
  };
  const uri = value => Object.freeze({ scheme: 'file', fsPath: String(value), path: String(value), toString: () => `file://${String(value)}` });
  const toUri = target => uri(target);
  const ensureDocument = (uriValue, initialText = '') => {
    const key = String(uriValue?.toString?.() || uriValue?.path || uriValue?.fsPath || '');
    if (textDocuments.has(key)) return textDocuments.get(key);
    const document = {
      uri: uriValue,
      fileName: String(uriValue?.fsPath || uriValue?.path || key).replace(/^untitled:/, ''),
      languageId: 'plaintext',
      isUntitled: String(uriValue?.scheme || '') === 'untitled',
      getText: () => String(document._text || ''),
      lineCount: () => String(document._text || '').split(/\r?\n/).length,
      _text: String(initialText || ''),
    };
    textDocuments.set(key, document);
    return document;
  };
  const refreshTextDocuments = () => { workspaceApi.textDocuments = [...textDocuments.values()]; };
  const workspaceRelativePath = target => path.relative(workspaceRoot, target).split(path.sep).join('/');
  const watcherEventFor = target => Object.freeze({ uri: toUri(target), fsPath: target, path: target, relativePath: workspaceRelativePath(target) });
  const fileOperationEventFor = target => Object.freeze({ uri: toUri(target) });
  const fileRenameEventFor = (oldTarget, newTarget) => Object.freeze({ oldUri: toUri(oldTarget), newUri: toUri(newTarget) });
  const fireWatcherEvent = (kind, target) => {
    const rel = workspaceRelativePath(target);
    for (const watcher of fileWatchers.slice()) {
      if (watcher.matcher.test(rel)) watcher.emitters[kind].fire(watcherEventFor(target));
    }
  };
  const emitDocumentChange = (document, edits, reason = 'change') => {
    textDocumentEmitter.fire({ document, contentChanges: Array.isArray(edits) ? edits : [], reason: String(reason || 'change') });
    emit('language', { feature: `textDocument.${String(reason || 'change')}`, uri: document.uri?.toString?.() || '', language: document.languageId });
  };
  const revealDocument = document => {
    const editor = {
      document,
      selection: { active: new vscode.Position(0, 0) },
      setDecorations: (decorationType, ranges) => emit('language', { feature: 'decorations', key: decorationType?.key || '', count: Array.isArray(ranges) ? ranges.length : 0 }),
      edit: async callback => {
        const edits = [];
        const builder = {
          insert: (position, value) => edits.push({ kind: 'insert', position, value: String(value || '') }),
          replace: (range, value) => edits.push({ kind: 'replace', range, value: String(value || '') }),
          delete: range => edits.push({ kind: 'delete', range }),
        };
        callback(builder);
        for (const edit of edits) {
          if (edit.kind === 'insert' || edit.kind === 'replace') document._text = String(edit.value || '');
          if (edit.kind === 'delete') document._text = '';
        }
        emitDocumentChange(document, edits.map(edit => ({ text: edit.value || '' })), 'change');
        return true;
      },
    };
    vscode.window.activeTextEditor = editor;
    activeEditorEmitter.fire(editor);
    return editor;
  };
  const globMatcher = pattern => {
    const raw = String(pattern || '**/*');
    let expression = '';
    for (let index = 0; index < raw.length; index += 1) {
      const char = raw[index];
      if (char === '*' && raw[index + 1] === '*') { if (raw[index + 2] === '/') { expression += '(?:.*/)?'; index += 2; } else { expression += '.*'; index += 1; } }
      else if (char === '*') expression += '[^/]*';
      else if (char === '?') expression += '[^/]';
      else expression += /[.+^${}()|[\]\\]/.test(char) ? `\\${char}` : char;
    }
    return new RegExp(`^${expression}$`);
  };
  const findFiles = (include = '**/*', exclude = '', maxResults = 100) => {
    requireCapability('workspace.read');
    const matcher = globMatcher(include);
    const ignored = String(exclude || '').trim();
    const rows = [];
    const skip = new Set(['.git', '.beast', 'node_modules', '.venv', 'venv', 'dist', 'build', '__pycache__']);
    const limit = Math.max(1, Math.min(Number(maxResults) || 100, 500));
    const walk = folder => {
      if (rows.length >= limit) return;
      for (const entry of fs.readdirSync(folder, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
        if (skip.has(entry.name)) continue;
        const full = path.join(folder, entry.name);
        const rel = path.relative(workspaceRoot, full).split(path.sep).join('/');
        if (entry.isDirectory()) walk(full);
        else if (entry.isFile() && matcher.test(rel) && (!ignored || !rel.includes(ignored.replaceAll('*', '')))) rows.push(toUri(full));
        if (rows.length >= limit) return;
      }
    };
    walk(workspaceRoot);
    return rows;
  };
  const registered = new Map();
  const taskProviders = new Map();
  let taskExecutionSeq = 0;
  const disposable = dispose => Object.freeze({ dispose: typeof dispose === 'function' ? dispose : () => {} });
  const systemCommands = {
    'beast.openMission': () => emit('navigate', { route: 'mission' }),
    'beast.openCompatibility': () => emit('navigate', { route: 'compatibility' }),
    'beast.openWorkspace': () => emit('navigate', { route: 'workspace' }),
    'beast.openTerminal': () => emit('navigate', { route: 'terminal' }),
    'vscode.diff': (left, right, title) => emit('navigate', { route: 'source', diff: { left: cloneJson(left || null), right: cloneJson(right || null), title: String(title || '').slice(0, 240) } }),
    'vscode.openFolder': (folderUri, forceNewWindow) => emit('navigate', { route: 'workspace', openFolder: { uri: cloneJson(folderUri || null), forceNewWindow: Boolean(forceNewWindow) } }),
  };
  let vscode = {};
  Object.assign(vscode, {
    Uri: Object.freeze({
      file: value => uri(workspacePath(value)),
      parse: value => uri(String(value || '').replace(/^file:\/\//, '')),
      joinPath: (base, ...segments) => uri(path.join(String(base?.fsPath || base?.path || ''), ...segments.map(String))),
    }),
    EventEmitter: class {
      constructor() { this.listeners = []; this.event = listener => { this.listeners.push(listener); return disposable(() => { this.listeners = this.listeners.filter(item => item !== listener); }); }; }
      fire(value) { for (const listener of this.listeners.slice()) listener(value); }
      dispose() { this.listeners = []; }
    },
    Disposable: class {
      constructor(call) { this._call = call; }
      dispose() { if (this._call) this._call(); this._call = null; }
      static from(...items) { return disposable(() => items.forEach(item => item?.dispose?.())); }
    },
    Position: class { constructor(line, character) { this.line = Number(line) || 0; this.character = Number(character) || 0; } },
    Range: class { constructor(startLine, startCharacter, endLine, endCharacter) { this.start = { line: startLine, character: startCharacter }; this.end = { line: endLine, character: endCharacter }; } },
    ThemeColor: class { constructor(id) { this.id = String(id); } },
    ThemeIcon: class { constructor(id) { this.id = String(id); } },
    StatusBarAlignment: Object.freeze({ Left: 1, Right: 2 }),
    OverviewRulerLane: Object.freeze({ Left: 1, Center: 2, Right: 4, Full: 7 }),
    ConfigurationTarget: Object.freeze({ Global: 1, Workspace: 2, WorkspaceFolder: 3 }),
    ShellExecution: class { constructor(commandLine, options = {}) { this.commandLine = String(commandLine || ''); this.options = options; } },
    Task: class { constructor(definition, scope, name, source, execution) { this.definition = definition; this.scope = scope; this.name = String(name || 'Task'); this.source = String(source || extension.id); this.execution = execution; } },
    TaskScope: Object.freeze({ Global: 1, Workspace: 2 }),
    TreeItem: class { constructor(label, collapsibleState = 0) { this.label = String(label || ''); this.collapsibleState = collapsibleState; this.id = ''; this.description = ''; this.tooltip = ''; this.command = null; this.iconPath = null; this.contextValue = ''; } },
    TreeItemCollapsibleState: Object.freeze({ None: 0, Collapsed: 1, Expanded: 2 }),
    ViewColumn: Object.freeze({ Active: -1, Beside: -2, One: 1, Two: 2, Three: 3 }),
    commands: Object.freeze({
      registerCommand: (id, handler) => { if (!COMMAND_ID.test(String(id || ''))) throw new Error('Extension registered an unsupported command id.'); registered.set(String(id), handler); return disposable(() => registered.delete(String(id))); },
      getCommands: async () => [...new Set([...registered.keys(), ...Object.keys(systemCommands)])].sort(),
      executeCommand: async (id, ...args) => { const key = String(id); if (registered.has(key)) return registered.get(key)(...args); const handler = systemCommands[key]; if (handler) return handler(...args); emit('command', { id: key, args }); return undefined; },
    }),
    extensions: Object.freeze({
      getExtension: id => {
        const key = String(id || '');
        const record = activatedRegistry.get(key);
        if (!record) return undefined;
        return Object.freeze({ id: key, extensionPath: record.extensionPath, extensionUri: uri(record.extensionPath), isActive: true, packageJSON: cloneJson(record.packageJSON || {}), exports: record.exports, activate: async () => record.exports });
      },
      get all() {
        return [...activatedRegistry.entries()].map(([id, record]) => Object.freeze({ id, extensionPath: record.extensionPath, extensionUri: uri(record.extensionPath), isActive: true, packageJSON: cloneJson(record.packageJSON || {}), exports: record.exports, activate: async () => record.exports }));
      },
    }),
  });
  const windowApi = {
      showInformationMessage: async (message, ...items) => { emit('notice', { severity: 'info', message: String(message), choices: items.map(item => String(item)) }); return items[0]; },
      showWarningMessage: async (message, ...items) => { emit('notice', { severity: 'warning', message: String(message), choices: items.map(item => String(item)) }); return items[0]; },
      showErrorMessage: async (message, ...items) => { emit('notice', { severity: 'error', message: String(message), choices: items.map(item => String(item)) }); return items[0]; },
      showInputBox: async options => String(options?.value || ''),
      showQuickPick: async (items = []) => Array.isArray(items) ? items[0] : undefined,
      showTextDocument: async (document) => { const editor = revealDocument(document); windowApi.visibleTextEditors = [editor]; return editor; },
      onDidChangeActiveTextEditor: activeEditorEmitter.event,
      onDidOpenTerminal: terminalOpenEmitter.event,
      onDidCloseTerminal: terminalCloseEmitter.event,
      createTextEditorDecorationType: options => { const key = `${extension.id}.decoration.${decorationTypes.size + 1}`; const type = { key, options: cloneJson(options || {}), dispose: () => decorationTypes.delete(key) }; decorationTypes.set(key, type); return type; },
      createOutputChannel: name => Object.freeze({ name: String(name || 'Extension').slice(0, 80), append: value => emit('notice', { severity: 'info', channel: String(name || 'Extension').slice(0, 80), message: String(value).slice(0, 1000) }), appendLine: value => emit('notice', { severity: 'info', channel: String(name || 'Extension').slice(0, 80), message: String(value).slice(0, 1000) }), show: preserveFocus => emit('notice', { severity: 'info', channel: String(name || 'Extension').slice(0, 80), show: true, preserveFocus:Boolean(preserveFocus) }), dispose: () => emit('notice', { severity: 'info', channel: String(name || 'Extension').slice(0, 80), disposed: true }) }),
      createStatusBarItem: (idOrAlignment = 'extension', alignment = 1) => {
        const item = { id: typeof idOrAlignment === 'string' ? idOrAlignment : `${extension.id}.status`, alignment: typeof idOrAlignment === 'number' ? idOrAlignment : alignment, text: '', tooltip: '', command: '', show: () => emit('status', { id: item.id, text: String(item.text || '').slice(0, 300), tooltip: String(item.tooltip || '').slice(0, 300), command: item.command || '' }), hide: () => emit('status', { id: item.id, hidden: true }), dispose: () => emit('status', { id: item.id, disposed: true }) };
        return item;
      },
      createTreeView: (id, options = {}) => { const view = { id: String(id).slice(0, 160), visible: true, reveal: async item => emit('tree', { id: String(id).slice(0, 160), reveal: cloneJson(item ?? null) }), dispose: () => emit('tree', { id: String(id).slice(0, 160), disposed: true }) }; emit('tree', { id: view.id, registered: true, canSelectMany: Boolean(options.canSelectMany) }); return view; },
      registerTreeDataProvider: (id, provider) => {
        const treeId = String(id).slice(0, 160);
        emit('tree', { id: treeId, provider: true, hasGetChildren: typeof provider?.getChildren === 'function' });
        if (provider?.onDidChangeTreeData && typeof provider.onDidChangeTreeData === 'function') {
          provider.onDidChangeTreeData(item => emit('tree', { id: treeId, refresh: true, item: cloneJson(item ?? null) }));
        }
        return disposable(() => emit('tree', { id: treeId, disposed: true }));
      },
      registerWebviewViewProvider: (id, provider, options = {}) => {
        const viewId = String(id).slice(0, 160);
        emit('webview', { viewType: viewId, viewProvider: true, retainContextWhenHidden: Boolean(options?.webviewOptions?.retainContextWhenHidden) });
        if (provider && typeof provider.resolveWebviewView === 'function') {
          const disposeEmitter = createEmitter(disposable);
          const webviewView = {
            viewType: viewId,
            title: viewId,
            description: '',
            visible: true,
            webview: createSandboxWebview(emit, viewId, viewId, options?.webviewOptions || {}),
            onDidDispose: disposeEmitter.event,
            show: preserveFocus => emit('webview', { viewType: viewId, reveal: true, preserveFocus: Boolean(preserveFocus), hosted: true }),
            dispose: () => { emit('webview', { viewType: viewId, disposed: true, hosted: true }); disposeEmitter.fire({ viewType: viewId }); },
          };
          Promise.resolve(provider.resolveWebviewView(webviewView, {}, {})).catch(error => emit('notice', { severity: 'error', message: String(error?.message || error).slice(0, 500) }));
        }
        return disposable(() => emit('webview', { viewType: viewId, disposed: true, viewProvider: true }));
      },
      createWebviewPanel: (viewType, title, showOptions = {}, options = {}) => {
        const receive = createEmitter(disposable);
        const disposeEmitter = createEmitter(disposable);
        const panel = { viewType: String(viewType).slice(0, 160), title: String(title || viewType).slice(0, 200), options, webview: createSandboxWebview(emit, String(viewType).slice(0, 160), String(title || viewType).slice(0, 200), options), onDidDispose: disposeEmitter.event, reveal: () => emit('webview', { viewType: panel.viewType, reveal: true, showOptions }), dispose: () => { emit('webview', { viewType: panel.viewType, disposed: true }); disposeEmitter.fire({ viewType: panel.viewType }); } };
        emit('webview', { viewType: panel.viewType, title: panel.title, created: true, enableScripts: Boolean(options.enableScripts) });
        return panel;
      },
      createTerminal: (options = {}) => {
        const terminal = {
          name: String(options.name || `${extension.id} terminal`).slice(0, 120),
          sendText: text => emit('terminal', { name: terminal.name, text: String(text || '').slice(0, 1000) }),
          show: () => emit('terminal', { name: terminal.name, show: true }),
          dispose: () => {
            emit('terminal', { name: terminal.name, disposed: true });
            if (windowApi.activeTerminal === terminal) windowApi.activeTerminal = null;
            terminalCloseEmitter.fire(terminal);
          },
        };
        emit('terminal', { name: terminal.name, created: true });
        windowApi.activeTerminal = terminal;
        terminalOpenEmitter.fire(terminal);
        return terminal;
      },
  };
  windowApi.activeTerminal = null;
  windowApi.activeTextEditor = null;
  windowApi.visibleTextEditors = [];
  const workspaceApi = {
      workspaceFolders:grants.has('workspace.read') ? Object.freeze([{ uri: uri(workspaceRoot), name: path.basename(workspaceRoot), index: 0 }]) : Object.freeze([]),
      textDocuments: [],
      onDidChangeWorkspaceFolders: workspaceFoldersEmitter.event,
      onDidChangeTextDocument: textDocumentEmitter.event,
      onDidOpenTextDocument: openTextDocumentEmitter.event,
      onDidCloseTextDocument: closeTextDocumentEmitter.event,
      onDidSaveTextDocument: saveTextDocumentEmitter.event,
      onDidChangeConfiguration: configurationEmitter.event,
      onDidCreateFiles: createFilesEmitter.event,
      onDidDeleteFiles: deleteFilesEmitter.event,
      onDidRenameFiles: renameFilesEmitter.event,
      getConfiguration: (section = '') => {
        return Object.freeze({ get: (key, fallback) => configurationValues.has(`${section}.${key}`) ? configurationValues.get(`${section}.${key}`) : fallback, has: key => configurationValues.has(`${section}.${key}`), inspect: key => configurationValues.has(`${section}.${key}`) ? { workspaceValue: configurationValues.get(`${section}.${key}`) } : undefined, update: async (key, value, target) => { const fullKey = `${section}.${key}`; configurationValues.set(fullKey, cloneJson(value)); writeStateFile(configFile, Object.fromEntries(configurationValues.entries())); emit('config', { section: String(section).slice(0, 120), key: String(key).slice(0, 160), target: target || 0, persisted: true }); configurationEmitter.fire({ affectsConfiguration: candidate => String(candidate || '') === fullKey || String(candidate || '') === section }); } });
      },
      asRelativePath: value => path.relative(workspaceRoot, workspacePath(value)).split(path.sep).join('/'),
      openTextDocument: async value => {
        if (value?.scheme === 'untitled' || String(value?.toString?.() || '').startsWith('untitled:')) {
          const document = ensureDocument(value, '');
          refreshTextDocuments();
          openTextDocumentEmitter.fire(document);
          emit('language', { feature: 'textDocument.open', uri: document.uri?.toString?.() || '', untitled: true });
          return document;
        }
        const uriValue = typeof value === 'string' ? (String(value).startsWith('untitled:') ? uri(value) : vscode.Uri.file(value)) : value;
        const target = workspacePath(uriValue);
        const content = fs.existsSync(target) ? fs.readFileSync(target, 'utf8') : '';
        const document = ensureDocument(uriValue, content);
        document.languageId = path.extname(document.fileName).replace(/^\./, '') || 'plaintext';
        refreshTextDocuments();
        openTextDocumentEmitter.fire(document);
        emit('language', { feature: 'textDocument.open', uri: document.uri?.toString?.() || '', untitled: false });
        return document;
      },
      registerTextDocumentContentProvider: (scheme, provider) => { emit('language', { feature: 'textDocumentContentProvider', scheme: String(scheme || '') }); return disposable(() => {}); },
      findFiles,
      createFileSystemWatcher: pattern => {
        const id = `${extension.id}.watcher.${Math.random().toString(36).slice(2, 8)}`;
        const watcher = { id, matcher: globMatcher(String(pattern || '**/*')), emitters: { create: createEmitter(disposable), change: createEmitter(disposable), delete: createEmitter(disposable) } };
        fileWatchers.push(watcher);
        emit('watcher', { id, pattern: String(pattern || '').slice(0, 240), created: true });
        return Object.freeze({
          onDidCreate: watcher.emitters.create.event,
          onDidChange: watcher.emitters.change.event,
          onDidDelete: watcher.emitters.delete.event,
          dispose: () => {
            const index = fileWatchers.indexOf(watcher);
            if (index >= 0) fileWatchers.splice(index, 1);
            emit('watcher', { id, disposed: true });
          },
        });
      },
      fs: Object.freeze({
        readFile: async value => { requireCapability('workspace.read'); const target = workspacePath(value); const stat = fs.statSync(target); if (!stat.isFile() || stat.size > 1024 * 1024) throw new Error('Extension read is limited to workspace files up to 1 MiB.'); return Uint8Array.from(fs.readFileSync(target)); },
        writeFile: async (value, content) => {
          requireCapability('workspace.write');
          const target = workspacePath(value);
          const bytes = Buffer.from(content || '');
          if (bytes.length > 1024 * 1024) throw new Error('Extension write is limited to 1 MiB.');
          const existed = fs.existsSync(target);
          fs.mkdirSync(path.dirname(target), { recursive: true });
          fs.writeFileSync(target, bytes);
          const document = ensureDocument(toUri(target), bytes.toString('utf8'));
          document._text = bytes.toString('utf8');
          document.languageId = path.extname(document.fileName).replace(/^\./, '') || document.languageId || 'plaintext';
          refreshTextDocuments();
          emitDocumentChange(document, [{ text: document._text }], existed ? 'change' : 'create');
          saveTextDocumentEmitter.fire(document);
          emit('language', { feature: 'textDocument.save', uri: document.uri?.toString?.() || '' });
          if (!existed) createFilesEmitter.fire({ files: [fileOperationEventFor(target)] });
          fireWatcherEvent(existed ? 'change' : 'create', target);
        },
        delete: async value => {
          requireCapability('workspace.write');
          const target = workspacePath(value);
          if (!fs.existsSync(target)) return;
          const uriValue = toUri(target);
          const key = String(uriValue.toString());
          const document = textDocuments.get(key) || ensureDocument(uriValue, fs.statSync(target).isFile() ? fs.readFileSync(target, 'utf8') : '');
          closeTextDocumentEmitter.fire(document);
          textDocuments.delete(key);
          if (fs.statSync(target).isDirectory()) fs.rmSync(target, { recursive: true, force: true });
          else fs.unlinkSync(target);
          refreshTextDocuments();
          deleteFilesEmitter.fire({ files: [fileOperationEventFor(target)] });
          emit('language', { feature: 'textDocument.delete', uri: uriValue.toString() });
          fireWatcherEvent('delete', target);
        },
        rename: async (oldValue, newValue, options = {}) => {
          requireCapability('workspace.write');
          const oldTarget = workspacePath(oldValue);
          const newTarget = workspacePath(newValue);
          if (!fs.existsSync(oldTarget)) throw new Error('Extension rename source does not exist.');
          if (fs.existsSync(newTarget) && !options?.overwrite) throw new Error('Extension rename target exists.');
          fs.mkdirSync(path.dirname(newTarget), { recursive: true });
          fs.renameSync(oldTarget, newTarget);
          const oldUri = toUri(oldTarget);
          const newUri = toUri(newTarget);
          const oldKey = String(oldUri.toString());
          if (textDocuments.has(oldKey)) {
            const document = textDocuments.get(oldKey);
            textDocuments.delete(oldKey);
            document.uri = newUri;
            document.fileName = newTarget;
            textDocuments.set(String(newUri.toString()), document);
          }
          refreshTextDocuments();
          renameFilesEmitter.fire({ files: [fileRenameEventFor(oldTarget, newTarget)] });
          emit('language', { feature: 'textDocument.rename', from: oldUri.toString(), to: newUri.toString() });
          fireWatcherEvent('delete', oldTarget);
          fireWatcherEvent('create', newTarget);
        },
      }),
  };
  Object.assign(vscode, {
    window: windowApi,
    workspace: workspaceApi,
    languages: Object.freeze({
      registerHoverProvider: (selector) => { emit('language', { feature: 'hover', selector: cloneJson(selector ?? null) }); return disposable(() => {}); },
      registerCompletionItemProvider: (selector) => { emit('language', { feature: 'completion', selector: cloneJson(selector ?? null) }); return disposable(() => {}); },
      registerCodeLensProvider: (selector) => { emit('language', { feature: 'codelens', selector: cloneJson(selector ?? null) }); return disposable(() => {}); },
      setTextDocumentLanguage: async (document, language) => { document.languageId = String(language || 'plaintext'); emit('language', { feature: 'set-language', language: document.languageId, uri: document.uri?.toString?.() || '' }); return document; },
      createDiagnosticCollection: name => Object.freeze({ name: String(name || extension.id).slice(0, 120), set: (uriValue, diagnostics) => emit('language', { feature: 'diagnostics', uri: uriValue?.fsPath || uriValue?.path || '', count: Array.isArray(diagnostics) ? diagnostics.length : 0 }), clear: () => emit('language', { feature: 'diagnostics.clear', name: String(name || extension.id).slice(0, 120) }), dispose: () => {} }),
    }),
    debug: Object.freeze({ registerDebugConfigurationProvider: (type) => { emit('debug', { type: String(type || '').slice(0, 120), provider: true }); return disposable(() => {}); } }),
    tasks: Object.freeze({
      registerTaskProvider: (type, provider) => { taskProviders.set(String(type), provider); emit('task', { type: String(type).slice(0, 120), provider: true }); return disposable(() => taskProviders.delete(String(type))); },
      executeTask: async task => {
        requireCapability('terminal.execute');
        taskExecutionSeq += 1;
        const execution = Object.freeze({
          id: `${extension.id}.task.${taskExecutionSeq}`,
          task: Object.freeze(task || {}),
          terminate: () => emit('task', { id: `${extension.id}.task.${taskExecutionSeq}`, terminated: true }),
        });
        emit('task', { execute: true, id: execution.id, name: String(task?.name || '').slice(0, 160), source: String(task?.source || '').slice(0, 120), commandLine: String(task?.execution?.commandLine || '').slice(0, 1000) });
        taskStartEmitter.fire({ execution });
        taskEndEmitter.fire({ execution, exitCode: 0 });
        return execution;
      },
      onDidStartTaskProcess: taskStartEmitter.event,
      onDidEndTaskProcess: taskEndEmitter.event,
    }),
    env: Object.freeze({ appName: 'BEAST IDE', language: 'en', clipboard: Object.freeze({ writeText: async value => emit('command', { id: 'clipboard.writeText', text: String(value || '').slice(0, 4000) }) }) }),
  });
  const secrets = new Map(Object.entries(readStateFile(secretsFile, {})));
  const context = Object.seal({
    subscriptions: [],
    extensionPath: extension.root,
    extensionUri: uri(extension.root),
    storageUri: uri(path.dirname(workspaceStateFile)),
    globalStorageUri: uri(path.dirname(globalStateFile)),
    logUri: uri(path.dirname(safeStateFile(workspaceRoot, extension.id, 'log'))),
    asAbsolutePath: relative => extensionPath(extension, relative),
    globalState: createMemento('global', globalStateFile, emit),
    workspaceState: createMemento('workspace', workspaceStateFile, emit),
    secrets: Object.freeze({
      get: async key => secrets.get(String(key)),
      store: async (key, value) => { secrets.set(String(key), String(value)); writeStateFile(secretsFile, Object.fromEntries(secrets.entries())); emit('secret', { key: String(key).slice(0, 160), stored: true, persisted: true }); },
      delete: async key => { secrets.delete(String(key)); writeStateFile(secretsFile, Object.fromEntries(secrets.entries())); emit('secret', { key: String(key).slice(0, 160), deleted: true, persisted: true }); },
      onDidChange: createEmitter(disposable).event,
    }),
  });
  const runtime = { context, emit };
  // Keep the mediator exact and frozen before extension code runs: vscode=Object.freeze(...)
  vscode=Object.freeze(vscode);
  return { grants, emit, vscode, registered, context, builtins:createBuiltinShims(extension, runtime), fetchImpl:createMockFetch(message, emit) };
}
function resolvePackageMain(root, request) {
  const parts = String(request).split('/');
  const packageName = request.startsWith('@') ? `${parts[0]}/${parts[1]}` : parts[0];
  if (!/^(@[A-Za-z0-9._-]+\/)?[A-Za-z0-9._-]+$/.test(packageName)) throw new Error(`Extension attempted to require unsupported package: ${request}`);
  const packageRoot = path.join(root, 'node_modules', packageName);
  const packageJson = readJson(path.join(packageRoot, 'package.json'));
  if (!packageJson) throw new Error(`Extension attempted to require missing package: ${request}`);
  const remainder = request.startsWith('@') ? parts.slice(2).join('/') : parts.slice(1).join('/');
  const subpath = remainder ? `./${remainder}` : '.';
  const exportTarget = packageExportTarget(packageJson.exports, subpath);
  if (exportTarget) return resolvePackageEntry(packageRoot, exportTarget);
  if (remainder) return resolvePackageEntry(packageRoot, remainder);
  const main = typeof packageJson?.main === 'string' ? packageJson.main : 'index.js';
  return resolvePackageEntry(packageRoot, main);
}
function createExtensionRequire(extension, runtime, moduleCache, baseDir = extension.root) {
  const loadModule = filename => {
    let resolved = '';
    for (const candidate of candidateModuleFiles(filename)) {
      try {
        const stat = fs.statSync(candidate);
        if (stat.isFile()) {
          resolved = path.resolve(candidate);
          break;
        }
      } catch (_) {}
    }
    if (!resolved) throw new Error(`Extension dependency could not be resolved: ${filename}`);
    if (resolved !== extension.root && !resolved.startsWith(`${extension.root}${path.sep}`)) throw new Error('Extension dependency escaped its package.');
    if (moduleCache.has(resolved)) return moduleCache.get(resolved).exports;
    if (resolved.endsWith('.json')) {
      const parsed = readJson(resolved);
      moduleCache.set(resolved, { exports: parsed });
      return parsed;
    }
    const source = readExtensionSource(resolved, 'Extension dependency');
    const moduleObj = { exports: {} };
    moduleCache.set(resolved, moduleObj);
    const localRequire = createExtensionRequire(extension, runtime, moduleCache, path.dirname(resolved));
    const sandbox = { module: moduleObj, exports: moduleObj.exports, require: localRequire, api: Object.freeze({ emit: runtime.emit, vscode: runtime.vscode, capabilities: Object.freeze([...runtime.grants]) }), vscode: runtime.vscode, Uint8Array, TextEncoder, TextDecoder, Buffer, setTimeout, clearTimeout, setInterval, clearInterval, queueMicrotask, URL, URLSearchParams, AbortController };
    vm.createContext(sandbox);
    new vm.Script(`'use strict';\n${source}`, { filename: resolved }).runInContext(sandbox, { timeout: 500 });
    return moduleObj.exports;
  };
  return request => {
    const name = String(request || '');
    if (name === 'vscode') return runtime.vscode;
    if (name === 'fs' || name === 'child_process') return runtime.builtins[name];
    if (SAFE_BUILTINS.has(name)) return require(name);
    if (name.startsWith('./') || name.startsWith('../')) return loadModule(path.resolve(baseDir, name));
    return loadModule(resolvePackageMain(extension.root, name));
  };
}
async function activateExtension(extension, message, actions, activationEvent = '') {
  if (activatedRegistry.has(extension.id) && !message.forceReactivate) {
    const existing = activatedRegistry.get(extension.id);
    return { runtime: existing.runtime, exported: existing.moduleExports, reused: true };
  }
  if (!extension.main) throw new Error('Extension does not declare an executable sandbox entrypoint.');
  const sourcePath = extensionPath(extension, extension.main);
  const source = readExtensionSource(sourcePath, 'Extension entrypoint');
  const runtime = runtimeFor(extension, message, actions);
  const moduleObj = { exports: {} };
  const moduleCache = new Map([[sourcePath, moduleObj]]);
  const requireShim = createExtensionRequire(extension, runtime, moduleCache, path.dirname(sourcePath));
  const api = Object.freeze({ emit: runtime.emit, vscode: runtime.vscode, capabilities: Object.freeze([...runtime.grants]), activationEvent: String(activationEvent || '') });
  const sandbox = { module: moduleObj, exports: moduleObj.exports, require: requireShim, api, vscode: runtime.vscode, Uint8Array, TextEncoder, TextDecoder, Buffer, setTimeout, clearTimeout, setInterval, clearInterval, queueMicrotask, fetch: runtime.fetchImpl, URL, URLSearchParams, AbortController };
  const context = vm.createContext(sandbox);
  new vm.Script(`'use strict';\n${source}`, { filename: sourcePath }).runInContext(context, { timeout: 500 });
  const exported = moduleObj.exports;
  const activationResult = await Promise.race([
    Promise.resolve((async () => {
      if (typeof exported.activate === 'function') return exported.activate(runtime.context);
      if (typeof exported.run === 'function') return undefined;
      throw new Error('Extension entrypoint must export activate(context) or run(api, command).');
    })()),
    new Promise((_, reject) => setTimeout(() => reject(new Error('Extension activation timed out.')), 2000)),
  ]);
  const publicExports = activationResult === undefined ? exported.exports || {} : activationResult;
  activatedRegistry.set(extension.id, { extensionPath: extension.root, packageJSON: { id: extension.id, name: extension.name, version: extension.version, activationEvents: extension.activationEvents, extensionDependencies: extension.extensionDependencies, extensionPack: extension.extensionPack, contributes: extension.contributes }, exports: publicExports, moduleExports: exported, runtime });
  return { runtime, exported };
}
function grantedForExtension(message, extension) {
  return Array.isArray(message.grantsByExtension?.[extension.id]) ? message.grantsByExtension[extension.id] : (Array.isArray(message.granted) ? message.granted : []);
}
async function activateWithDependencies(extension, message, actions, activationEvent, allExtensions, stack = []) {
  if (stack.includes(extension.id)) throw new Error(`Extension dependency cycle: ${[...stack, extension.id].join(' -> ')}`);
  const dependencyResults = [];
  for (const dependencyId of extension.extensionDependencies || []) {
    const dependency = allExtensions.get(dependencyId);
    if (!dependency) throw new Error(`Missing extension dependency: ${dependencyId}`);
    const scopedActions = [];
    const result = await activateWithDependencies(dependency, { ...message, extensionId: dependency.id, granted: grantedForExtension(message, dependency) }, scopedActions, `dependency:${extension.id}`, allExtensions, [...stack, extension.id]);
    dependencyResults.push({ id: dependency.id, ok: true, reused: Boolean(result.reused), actionCount: scopedActions.length });
    actions.push(...scopedActions.map(action => ({ ...action, extensionId: dependency.id, dependencyFor: extension.id })));
  }
  return activateExtension(extension, { ...message, extensionId: extension.id, granted: grantedForExtension(message, extension) }, actions, activationEvent);
}
async function execute(message = {}) {
  const extension = discover(message.roots).find(item => item.id === String(message.extensionId || ''));
  const command = String(message.command || '');
  if (!extension?.main) throw new Error('Extension does not declare an executable sandbox entrypoint.');
  if (!extension.contributes.commands.some(item => item.id === command)) throw new Error('Extension command is not declared in its manifest.');
  const actions = [];
  const allExtensions = new Map(discover(message.roots).map(item => [item.id, item]));
  const { runtime, exported } = await activateWithDependencies(extension, { ...message, forceReactivate: true }, actions, `onCommand:${command}`, allExtensions);
  await Promise.race([
    Promise.resolve((async () => {
      if (runtime.registered.has(command)) return runtime.vscode.commands.executeCommand(command);
      if (typeof exported.run === 'function') return exported.run(Object.freeze({ emit: runtime.emit, vscode: runtime.vscode, capabilities: Object.freeze([...runtime.grants]) }), command);
      throw new Error('Extension activated but did not register the requested command.');
    })()),
    new Promise((_, reject) => setTimeout(() => reject(new Error('Extension command timed out.')), 12000)),
  ]);
  const actionKinds = [...new Set(actions.map(action => String(action.kind || '')).filter(Boolean))];
  return { extensionId: extension.id, manifestKind: extension.manifestKind, compatibility: extension.compatibility, contributionSummary: extension.contributionSummary, granted: [...runtime.grants], actions, actionKinds, actionSummary: summarizeActions(actions), registeredCommands: [...runtime.registered.keys()] };
}
async function activate(message = {}) {
  const extension = discover(message.roots).find(item => item.id === String(message.extensionId || ''));
  if (!extension?.main) throw new Error('Extension does not declare an executable sandbox entrypoint.');
  const actions = [];
  const activationEvent = String(message.activationEvent || 'onStartupFinished');
  const allExtensions = new Map(discover(message.roots).map(item => [item.id, item]));
  const { runtime } = await activateWithDependencies(extension, message, actions, activationEvent, allExtensions);
  const actionKinds = [...new Set(actions.map(action => String(action.kind || '')).filter(Boolean))];
  return { extensionId: extension.id, activationEvent, manifestKind: extension.manifestKind, compatibility: extension.compatibility, contributionSummary: extension.contributionSummary, granted: [...runtime.grants], actions, actionKinds, actionSummary: summarizeActions(actions), registeredCommands: [...runtime.registered.keys()] };
}
async function activateByEvent(message = {}) {
  const activationEvent = String(message.activationEvent || 'onStartupFinished');
  const allDiscovered = discover(message.roots);
  const allExtensions = new Map(allDiscovered.map(item => [item.id, item]));
  const extensions = allDiscovered.filter(extension => extension.main && activationMatches(extension, activationEvent, message)).slice(0, Math.max(1, Math.min(Number(message.limit || 30), 80)));
  const started = Date.now();
  const results = [];
  const actions = [];
  for (const extension of extensions) {
    const scopedActions = [];
    try {
      const { runtime } = await activateWithDependencies(extension, { ...message, extensionId: extension.id, granted: grantedForExtension(message, extension) }, scopedActions, activationEvent, allExtensions);
      actions.push(...scopedActions.map(action => ({ ...action, extensionId: action.extensionId || extension.id })));
      results.push({ id: extension.id, ok: true, activationEvent, dependencies: extension.extensionDependencies || [], registeredCommands: [...runtime.registered.keys()], actionCount: scopedActions.length, actionKinds:[...new Set(scopedActions.map(action => String(action.kind || '')).filter(Boolean))], actionSummary: summarizeActions(scopedActions), contributionSummary: extension.contributionSummary });
    } catch (error) {
      results.push({ id: extension.id, ok: false, activationEvent, dependencies: extension.extensionDependencies || [], error: String(error.message || error).slice(0, 500), actionCount: scopedActions.length, actionKinds:[...new Set(scopedActions.map(action => String(action.kind || '')).filter(Boolean))], actionSummary: summarizeActions(scopedActions), contributionSummary: extension.contributionSummary });
    }
  }
  const failures = results.filter(item => !item.ok);
  return { ok: failures.length === 0, activationEvent, matched: extensions.length, activated: results.filter(item => item.ok).length, failed: failures.length, durationMs: Date.now() - started, results, actions, actionKinds:[...new Set(actions.map(action => String(action.kind || '')).filter(Boolean))] };
}
async function stressProbe(message = {}) {
  const roots = Array.isArray(message.roots) ? message.roots : [];
  const extensions = discover(roots).slice(0, Math.max(1, Math.min(Number(message.limit || 20), 80)));
  const started = Date.now();
  const results = [];
  for (const extension of extensions) {
    const commands = (extension.contributes?.commands || []).slice(0, Math.max(1, Math.min(Number(message.commandLimit || 3), 10)));
    results.push({
      id: extension.id,
      origin: extension.origin,
      manifestOk: Boolean(extension.main || commands.length || Object.values(extension.contributionSummary || {}).some(Boolean)),
      commandCount: commands.length,
      capabilityCount: (extension.capabilities || []).length,
      contributionSummary: extension.contributionSummary,
      activationEvents: extension.activationEvents,
      extensionDependencies: extension.extensionDependencies || [],
      extensionPack: extension.extensionPack || [],
      lifecycleMatches: {
        onStartupFinished: activationMatches(extension, 'onStartupFinished', message),
        workspaceContains: activationMatches(extension, 'workspaceContains', message),
        onView: ['views', 'viewsContainers'].some(Boolean) && Array.isArray(extension.activationEvents) ? extension.activationEvents.some(event => String(event).startsWith('onView:')) : false,
        onDebug: Array.isArray(extension.activationEvents) ? extension.activationEvents.some(event => String(event).startsWith('onDebug:')) : false,
        onTaskType: Array.isArray(extension.activationEvents) ? extension.activationEvents.some(event => String(event).startsWith('onTaskType:')) : false,
      },
      entrypointBytes: extension.main ? fs.statSync(path.resolve(extension.root, extension.main)).size : 0,
      commands: commands.map(command => command.id),
    });
  }
  const failures = results.filter(item => !item.manifestOk || item.entrypointBytes > EXTENSION_FILE_LIMIT);
  return {
    ok: failures.length === 0,
    mode: 'bounded_extension_ecology_stress_probe',
    extensionCount: extensions.length,
    commandCount: results.reduce((count, item) => count + item.commandCount, 0),
    capabilityCount: results.reduce((count, item) => count + item.capabilityCount, 0),
    contributionSummary: results.reduce((memo, item) => { for (const [key, value] of Object.entries(item.contributionSummary || {})) memo[key] = (memo[key] || 0) + value; return memo; }, {}),
    durationMs: Date.now() - started,
    failures,
    results,
  };
}
async function handle(message = {}) {
  if (message.operation === 'discover') return { extensions: discover(message.roots) };
  if (message.operation === 'ping') return { host: 'beast-declarative-extension-host', capabilities: [...CAPABILITIES], actionKinds: [...ACTION_KINDS] };
  if (message.operation === 'activate') return activate(message);
  if (message.operation === 'activateByEvent') return activateByEvent(message);
  if (message.operation === 'execute') return execute(message);
  if (message.operation === 'stressProbe') return stressProbe(message);
  throw new Error('Unsupported extension host operation.');
}

function maybeExit() {
  if (inputEnded && pending === 0) process.exit(0);
}

function startStdioHost() {
  send({ type: 'ready', host: 'beast-declarative-extension-host', capabilities: [...CAPABILITIES], actionKinds: [...ACTION_KINDS] });
  process.stdin.on('data', chunk => {
    buffer += String(chunk);
    let cut;
    while ((cut = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 1);
      if (!line.trim()) continue;
      let request = {};
      try {
        request = JSON.parse(line);
        pending += 1;
        Promise.resolve(handle(request)).then(result => send({ id: request.id, ok: true, ...result })).catch(error => send({ id: request.id, ok: false, error: String(error.message || error) })).finally(() => { pending -= 1; maybeExit(); });
      } catch (error) {
        send({ id: request.id, ok: false, error: String(error.message || error) });
      }
    }
  });
  process.stdin.on('end', () => { inputEnded = true; maybeExit(); });
}

if (require.main === module) startStdioHost();

module.exports = { CAPABILITIES, ACTION_KINDS, discover, activate, activateByEvent, execute, stressProbe, handle, startStdioHost };
