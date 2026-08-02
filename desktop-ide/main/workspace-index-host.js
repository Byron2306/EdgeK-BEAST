'use strict';

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

function createWorkspaceIndexHost({
  repoRoot,
  workspaceFileHost,
  taskTestHost,
  gitHost,
  executionTargetHost,
}) {
  if (!repoRoot || !workspaceFileHost || !taskTestHost || !gitHost || !executionTargetHost) {
    throw new Error('createWorkspaceIndexHost requires workspace, test, Git, and execution-target dependencies');
  }

  const ignored = new Set(['.git', '.beast', 'node_modules', 'dist', 'build', '.venv', 'venv', '__pycache__']);
  const languageByExtension = new Map([
    ['.js', 'javascript'], ['.jsx', 'javascriptreact'], ['.ts', 'typescript'], ['.tsx', 'typescriptreact'],
    ['.py', 'python'], ['.nim', 'nim'], ['.nims', 'nim'], ['.nimble', 'nim'],
    ['.go', 'go'], ['.rs', 'rust'], ['.c', 'c'], ['.h', 'c'], ['.cc', 'cpp'], ['.cpp', 'cpp'], ['.hpp', 'cpp'],
    ['.java', 'java'], ['.cs', 'csharp'], ['.rb', 'ruby'], ['.php', 'php'], ['.sh', 'shell'], ['.json', 'json'],
    ['.md', 'markdown'], ['.html', 'html'], ['.css', 'css'], ['.scss', 'scss'],
  ]);

  const normalizeRel = value => String(value || '').replace(/\\/g, '/').replace(/^\.\//, '');
  const languageFor = file => languageByExtension.get(path.extname(String(file || '')).toLowerCase()) || 'text';
  const lineFor = (text, index) => text.slice(0, index).split(/\r?\n/).length;
  const digest = value => `sha256:${crypto.createHash('sha256').update(value).digest('hex')}`;
  const symbol = (name, kind, file, line, detail = '') => ({ name, kind, file, line, detail });
  const escapeRegExp = value => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

  function extractSymbols(file, language, text) {
    const source = String(text || '').slice(0, 1024 * 1024);
    const rows = [];
    const addMatches = (regexp, kind, nameIndex = 1, detail = '') => {
      for (const match of source.matchAll(regexp)) {
        rows.push(symbol(match[nameIndex], kind, file, lineFor(source, match.index || 0), detail || match[0].slice(0, 180).trim()));
        if (rows.length >= 240) return;
      }
    };
    if (['javascript', 'javascriptreact', 'typescript', 'typescriptreact'].includes(language)) {
      addMatches(/\b(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(/g, 'function');
      addMatches(/\b(?:export\s+)?class\s+([A-Za-z_$][\w$]*)\b/g, 'class');
      addMatches(/\b(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(?[^=\n]*?\)?\s*=>/g, 'function');
      addMatches(/\b(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=/g, 'variable');
    } else if (language === 'python') {
      addMatches(/^\s*class\s+([A-Za-z_]\w*)\b/gm, 'class');
      addMatches(/^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(/gm, 'function');
    } else if (language === 'nim') {
      addMatches(/^\s*(?:proc|func|method|iterator|template|macro|converter)\s+([A-Za-z_]\w*)\s*(?:\[|\(|\*|=|:)/gm, 'function');
      addMatches(/^\s*type\s+([A-Za-z_]\w*)\s*(?:\*|=)/gm, 'type');
      addMatches(/^\s*(?:let|var|const)\s+([A-Za-z_]\w*)\s*(?:\*|=|:)/gm, 'variable');
    } else if (language === 'go') {
      addMatches(/^func\s+(?:\([^)]+\)\s*)?([A-Za-z_]\w*)\s*\(/gm, 'function');
      addMatches(/^type\s+([A-Za-z_]\w*)\s+(?:struct|interface)\b/gm, 'type');
    } else if (language === 'rust') {
      addMatches(/\b(?:pub\s+)?fn\s+([A-Za-z_]\w*)\s*\(/g, 'function');
      addMatches(/\b(?:pub\s+)?(?:struct|enum|trait)\s+([A-Za-z_]\w*)\b/g, 'type');
    } else if (['c', 'cpp', 'java', 'csharp'].includes(language)) {
      addMatches(/\b(?:class|struct|enum|interface)\s+([A-Za-z_]\w*)\b/g, 'type');
      addMatches(/^\s*(?:[\w:<>,~*&]+\s+)+([A-Za-z_]\w*)\s*\([^;{}]*\)\s*(?:const\s*)?[{;]/gm, 'function');
    }
    return rows.slice(0, 240);
  }

  function extractImports(file, language, text) {
    const source = String(text || '').slice(0, 512000);
    const rows = [];
    const add = (target, kind = 'import') => {
      const value = String(target || '').trim().slice(0, 240);
      if (value) rows.push({ file, target: value, kind });
    };
    if (['javascript', 'javascriptreact', 'typescript', 'typescriptreact'].includes(language)) {
      for (const match of source.matchAll(/\bimport\b[^'"]*['"]([^'"]+)['"]/g)) add(match[1]);
      for (const match of source.matchAll(/\brequire\s*\(\s*['"]([^'"]+)['"]\s*\)/g)) add(match[1], 'require');
    } else if (language === 'python') {
      for (const match of source.matchAll(/^\s*from\s+([A-Za-z0-9_.]+)\s+import\b/gm)) add(match[1]);
      for (const match of source.matchAll(/^\s*import\s+([A-Za-z0-9_.,\s]+)/gm)) String(match[1]).split(',').forEach(item => add(item));
    } else if (language === 'nim') {
      for (const match of source.matchAll(/^\s*(?:import|include)\s+(.+)$/gm)) String(match[1]).split(',').forEach(item => add(item.replace(/#.*/, '')));
      for (const match of source.matchAll(/^\s*from\s+([A-Za-z0-9_./]+)\s+import\b/gm)) add(match[1]);
    } else if (language === 'go') {
      for (const match of source.matchAll(/^\s*import\s+"([^"]+)"/gm)) add(match[1]);
      for (const match of source.matchAll(/^\s*"([^"]+)"\s*$/gm)) add(match[1]);
    } else if (language === 'rust') {
      for (const match of source.matchAll(/^\s*use\s+([^;]+);/gm)) add(match[1]);
    }
    return rows.slice(0, 400);
  }

  function resolveImport(file, target, filesByPath) {
    const sourceDir = path.posix.dirname(normalizeRel(file));
    const raw = String(target || '').trim().replace(/^['"]|['"]$/g, '');
    if (!raw || raw.startsWith('std/')) return '';
    const candidates = [];
    const add = value => {
      const normalized = normalizeRel(path.posix.normalize(value));
      candidates.push(normalized);
      for (const ext of ['.js', '.jsx', '.ts', '.tsx', '.py', '.nim', '.go', '.rs', '.java', '.cs']) candidates.push(`${normalized}${ext}`);
      candidates.push(path.posix.join(normalized, 'index.js'));
      candidates.push(path.posix.join(normalized, '__init__.py'));
    };
    const addSiblingByBasename = value => {
      const base = path.posix.basename(String(value || '').replace(/^\.\//, ''));
      for (const filePath of filesByPath.keys()) if (path.posix.basename(filePath, path.posix.extname(filePath)) === base) candidates.push(filePath);
    };
    if (raw.startsWith('.')) add(path.posix.join(sourceDir, raw));
    else if (raw.includes('/')) add(raw);
    else { add(path.posix.join(sourceDir, raw)); add(raw); add(raw.replaceAll('.', '/')); }
    addSiblingByBasename(raw);
    return candidates.find(candidate => filesByPath.has(candidate)) || '';
  }

  function buildSemanticGraph(files, symbols, imports, textByFile = new Map()) {
    const filesByPath = new Map(files.map(file => [file.path, file]));
    const definitions = new Map();
    for (const item of symbols) {
      if (!definitions.has(item.name)) definitions.set(item.name, []);
      definitions.get(item.name).push({ file: item.file, line: item.line, kind: item.kind });
    }
    const importEdges = imports.map(item => ({ ...item, resolved: resolveImport(item.file, item.target, filesByPath) })).slice(0, 2000);
    const dependents = {};
    for (const edge of importEdges) {
      if (!edge.resolved) continue;
      if (!dependents[edge.resolved]) dependents[edge.resolved] = [];
      dependents[edge.resolved].push(edge.file);
    }
    const references = [];
    const names = [...definitions.keys()].filter(name => name.length >= 3).slice(0, 600);
    for (const name of names) {
      const regexp = new RegExp(`\\b${escapeRegExp(name)}\\b`, 'g');
      let count = 0;
      const filesSeen = new Set();
      for (const [file, text] of textByFile.entries()) {
        const matches = String(text || '').match(regexp);
        if (!matches) continue;
        count += matches.length;
        filesSeen.add(file);
        if (count > 500) break;
      }
      references.push({ name, count, files: [...filesSeen].slice(0, 40), definitions: definitions.get(name).slice(0, 12) });
    }
    references.sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
    return {
      definitionCount: symbols.length,
      referenceCount: references.reduce((count, item) => count + item.count, 0),
      importEdgeCount: importEdges.filter(item => item.resolved).length,
      unresolvedImportCount: importEdges.filter(item => !item.resolved).length,
      importEdges: importEdges.slice(0, 400),
      dependents: Object.fromEntries(Object.entries(dependents).map(([file, rows]) => [file, [...new Set(rows)].slice(0, 80)]).slice(0, 400)),
      topReferences: references.slice(0, 80),
      workspaceSymbols: symbols.slice(0, 1000).map(item => ({ name: item.name, kind: item.kind, file: item.file, line: item.line })),
    };
  }

  function extractDiagnostics(files, symbols, semantic, textByFile = new Map()) {
    const diagnostics = [];
    const byName = new Map();
    for (const item of symbols) {
      const key = `${item.file}:${item.name}`;
      if (!byName.has(key)) byName.set(key, []);
      byName.get(key).push(item);
    }
    for (const rows of byName.values()) {
      if (rows.length > 1) diagnostics.push({ file: rows[0].file, line: rows[1].line, severity: 'warning', code: 'duplicate-symbol', source: 'beast-index', message: `Duplicate symbol in file: ${rows[0].name}`, symbol: rows[0].name });
    }
    for (const edge of semantic.importEdges || []) {
      if (edge.resolved || /^(node:|std\/|https?:|[A-Za-z0-9_.-]+$)/.test(String(edge.target || ''))) continue;
      diagnostics.push({ file: edge.file, line: 1, severity: 'warning', code: 'unresolved-import', source: 'beast-index', message: `Unresolved import: ${edge.target}`, target: edge.target });
    }
    for (const file of files) {
      const text = textByFile.get(file.path) || '';
      if (!text) continue;
      const lines = String(text).split(/\r?\n/);
      lines.forEach((line, index) => {
        if (/\b(TODO|FIXME)\b/i.test(line)) diagnostics.push({ file: file.path, line: index + 1, severity: 'hint', code: 'todo-comment', source: 'beast-index', message: line.trim().slice(0, 240) });
        if (line.length > 160) diagnostics.push({ file: file.path, line: index + 1, severity: 'information', code: 'long-line', source: 'beast-index', message: `Line is ${line.length} characters.` });
      });
    }
    return diagnostics.slice(0, 1000);
  }

  function codeActionsForDiagnostics(diagnostics) {
    return diagnostics.map(item => {
      if (item.code === 'unresolved-import') return { title: `Search workspace for ${item.target}`, kind: 'quickfix', diagnostic: item, command: 'beast.workspaceIndexQuery', arguments: [{ query: item.target, mode: 'symbols' }] };
      if (item.code === 'duplicate-symbol') return { title: `Review duplicate ${item.symbol}`, kind: 'refactor.rewrite', diagnostic: item, command: 'beast.workspaceIndexQuery', arguments: [{ query: item.symbol, mode: 'references' }] };
      if (item.code === 'todo-comment') return { title: 'Track TODO in workspace', kind: 'source.organize', diagnostic: item, command: 'beast.openWorkspace', arguments: [{ file: item.file, line: item.line }] };
      return { title: `Inspect ${item.code}`, kind: 'quickfix', diagnostic: item, command: 'beast.workspaceIndexQuery', arguments: [{ file: item.file }] };
    }).slice(0, 200);
  }

  function summarize(files, symbols, imports, tests, target, source, truncated = false, semantic = null, diagnostics = []) {
    const languages = {};
    for (const file of files) languages[file.language] = (languages[file.language] || 0) + 1;
    const symbolKinds = {};
    for (const item of symbols) symbolKinds[item.kind] = (symbolKinds[item.kind] || 0) + 1;
    const indexDigest = digest(JSON.stringify({
      target: target.kind,
      files: files.map(item => [item.path, item.size, item.mtimeMs, item.language]).slice(0, 5000),
      symbols: symbols.map(item => [item.file, item.name, item.kind, item.line]).slice(0, 5000),
      tests: (tests.tests || []).map(item => item.id),
    }));
    return {
      ok: true,
      beast_object_type: 'beast_workspace_index_snapshot',
      version: '1.0',
      source,
      target,
      updatedAt: new Date().toISOString(),
      indexDigest,
      truncated,
      summary: {
        fileCount: files.length,
        symbolCount: symbols.length,
        importCount: imports.length,
        testCount: (tests.tests || []).length,
        testNodeCount: (tests.nodes || []).length,
        referenceCount: safeNumber(semantic?.referenceCount),
        importEdgeCount: safeNumber(semantic?.importEdgeCount),
        diagnosticCount: diagnostics.length,
        languages,
        symbolKinds,
      },
      files,
      symbols,
      imports,
      semantic: semantic || { definitionCount: symbols.length, referenceCount: 0, importEdgeCount: 0, unresolvedImportCount: imports.length, importEdges: [], dependents: {}, topReferences: [], workspaceSymbols: symbols.slice(0, 1000) },
      diagnostics,
      codeActions: codeActionsForDiagnostics(diagnostics),
      tests: {
        ok: Boolean(tests.ok),
        tests: tests.tests || [],
        files: tests.files || [],
        nodes: tests.nodes || [],
        error: tests.error || '',
      },
    };
  }

  function safeNumber(value) { return Math.max(0, Number(value) || 0); }

  async function localSnapshot(root, target, options = {}) {
    const limit = Math.max(1, Math.min(Number(options.limit || 4000), 12000));
    const candidates = workspaceFileHost.workspaceFileCandidates(root, limit);
    const files = [];
    const symbols = [];
    const imports = [];
    const textByFile = new Map();
    for (const item of candidates) {
      const rel = normalizeRel(item.path);
      const language = languageFor(rel);
      const row = { path: rel, name: path.basename(rel), language, size: Number(item.size || 0), mtimeMs: Number(item.mtimeMs || 0) };
      files.push(row);
      if (row.size > 1024 * 1024 || language === 'text') continue;
      const read = workspaceFileHost.readWorkspaceFile(root, rel, 1024 * 1024);
      if (!read.ok || read.binary) continue;
      textByFile.set(rel, read.content || '');
      symbols.push(...extractSymbols(rel, language, read.content || ''));
      imports.push(...extractImports(rel, language, read.content || ''));
    }
    const tests = await taskTestHost.workspaceTestsForTarget(root, { target });
    const scm = await gitHost.workspaceGitStatus(root).catch(error => ({ ok: false, error: String(error.message || error) }));
    const semantic = buildSemanticGraph(files, symbols, imports, textByFile);
    const diagnostics = extractDiagnostics(files, symbols, semantic, textByFile);
    const snapshot = summarize(files, symbols, imports, tests, target, 'desktop-local-index', candidates.length >= limit, semantic, diagnostics);
    snapshot.scm = { ok: Boolean(scm.ok), branchName: scm.branchName || '', counts: scm.counts || { staged: 0, unstaged: 0, conflicts: 0 }, error: scm.error || '' };
    return snapshot;
  }

  async function remoteSnapshot(root, target, options = {}) {
    const limit = Math.max(1, Math.min(Number(options.limit || 1500), 5000));
    const base = target.kind === 'ssh' ? executionTargetHost.remotePath(target.remoteRoot || target.path || '') : executionTargetHost.remotePath(target.workspaceFolder || target.path || '');
    if (!base) return { ok: false, beast_object_type: 'beast_workspace_index_snapshot', target, error: 'Remote workspace index target has no workspace root.' };
    const ignoredExpr = [...ignored].map(name => `! -path './${name}/*'`).join(' ');
    const command = `cd ${executionTargetHost.shellQuote(base)} && find . -maxdepth 8 -type f ${ignoredExpr} -printf '%p\\t%s\\t%T@\\n' 2>/dev/null | head -n ${limit}`;
    const result = await executionTargetHost.runOnExecutionTarget(target, root, 'sh', ['-lc', command], { timeoutMs: 30000, outputLimit: 512000 });
    const files = String(result.stdout || '').split(/\r?\n/).filter(Boolean).map(line => {
      const [file, size = '0', mtime = '0'] = line.split('\t');
      const rel = normalizeRel(file);
      return { path: rel, name: path.basename(rel), language: languageFor(rel), size: Number(size) || 0, mtimeMs: Math.round((Number(mtime) || 0) * 1000) };
    }).filter(item => item.path && item.language);
    const tests = await taskTestHost.workspaceTestsForTarget(root, { target });
    const symbols = [];
    const imports = [];
    const textByFile = new Map();
    const readable = files.filter(item => item.language !== 'text' && item.size > 0 && item.size <= 1024 * 1024).slice(0, Math.max(1, Math.min(Number(options.semanticFileLimit || 200), 600)));
    for (const file of readable) {
      const read = await executionTargetHost.workspaceTargetReadFile(root, { target, path: file.path, maxChars: 1024 * 1024 });
      if (!read.ok || typeof read.content !== 'string') continue;
      textByFile.set(file.path, read.content);
      symbols.push(...extractSymbols(file.path, file.language, read.content));
      imports.push(...extractImports(file.path, file.language, read.content));
    }
    const semantic = buildSemanticGraph(files, symbols, imports, textByFile);
    const diagnostics = extractDiagnostics(files, symbols, semantic, textByFile);
    const snapshot = summarize(files, symbols, imports, tests, target, 'target-remote-semantic-index', files.length >= limit, semantic, diagnostics);
    snapshot.remoteRoot = base;
    snapshot.remoteIndexLimited = readable.length < files.filter(item => item.language !== 'text' && item.size > 0 && item.size <= 1024 * 1024).length;
    snapshot.remoteSemanticFileCount = readable.length;
    snapshot.error = result.ok ? '' : String(result.stderr || result.error || 'remote workspace inventory failed');
    snapshot.ok = Boolean(result.ok);
    return snapshot;
  }

  async function snapshot(rootPath, options = {}) {
    const root = path.resolve(rootPath || repoRoot);
    const target = executionTargetHost.executionTargetSummary(options.target || executionTargetHost.getActiveExecutionTarget());
    if (target.kind === 'local') return localSnapshot(root, target, options);
    return remoteSnapshot(root, target, options);
  }

  function linePreview(text, line) {
    const rows = String(text || '').split(/\r?\n/);
    return String(rows[Math.max(0, Number(line || 1) - 1)] || '').trim().slice(0, 240);
  }

  async function query(rootPath, options = {}) {
    const root = path.resolve(rootPath || repoRoot);
    const queryText = String(options.query || options.symbol || '').trim();
    const mode = String(options.mode || 'symbols');
    const index = await snapshot(root, options);
    const semantic = index.semantic || {};
    const workspaceSymbols = semantic.workspaceSymbols || [];
    const lower = queryText.toLowerCase();
    const symbolMatches = workspaceSymbols.filter(item => !lower || String(item.name || '').toLowerCase().includes(lower)).slice(0, Math.max(1, Math.min(Number(options.limit || 80), 300)));
    const topReferences = semantic.topReferences || [];
    const exactReference = topReferences.find(item => String(item.name || '') === queryText);
    const referenceMatches = queryText ? topReferences.filter(item => String(item.name || '').toLowerCase().includes(lower)).slice(0, 80) : topReferences.slice(0, 80);
    const definitionMatches = queryText ? workspaceSymbols.filter(item => String(item.name || '') === queryText).slice(0, 80) : symbolMatches;
    const textByFile = new Map();
    if (index.target?.kind === 'local') {
      for (const file of new Set([...definitionMatches.map(item => item.file), ...(exactReference?.files || []), String(options.file || '')].filter(Boolean))) {
        const read = workspaceFileHost.readWorkspaceFile(root, file, 1024 * 1024);
        if (read.ok && !read.binary) textByFile.set(file, read.content || '');
      }
    }
    const definitions = definitionMatches.map(item => ({ ...item, preview: linePreview(textByFile.get(item.file), item.line) }));
    const references = queryText ? (exactReference ? exactReference.files.map(file => ({ name: queryText, file, preview: linePreview(textByFile.get(file), 1) })) : []) : referenceMatches.flatMap(item => item.files.map(file => ({ name: item.name, file }))).slice(0, 200);
    const file = normalizeRel(options.file || '');
    const dependents = file ? (semantic.dependents?.[file] || []) : [];
    const renameTo = String(options.newName || '').trim();
    const renamePreview = queryText && renameTo && /^[A-Za-z_$][\w$]*$/.test(renameTo) ? references.map(item => {
      const text = textByFile.get(item.file) || '';
      const regexp = new RegExp(`\\b${escapeRegExp(queryText)}\\b`, 'g');
      const edits = [];
      String(text).split(/\r?\n/).forEach((line, index) => {
        let match;
        while ((match = regexp.exec(line))) edits.push({ line: index + 1, column: match.index + 1, oldText: queryText, newText: renameTo, preview: line.trim().slice(0, 240) });
      });
      return { file: item.file, edits };
    }).filter(item => item.edits.length).slice(0, 80) : [];
    return {
      ok: Boolean(index.ok),
      beast_object_type: 'beast_workspace_semantic_query',
      mode,
      query: queryText,
      target: index.target,
      digest: index.indexDigest || '',
      degraded: index.target?.kind !== 'local',
      symbols: symbolMatches,
      definitions,
      references,
      dependents,
      importEdges: (semantic.importEdges || []).filter(edge => !file || edge.file === file || edge.resolved === file).slice(0, 120),
      diagnostics: (index.diagnostics || []).filter(item => !file || item.file === file).slice(0, 120),
      codeActions: (index.codeActions || []).filter(item => !file || item.diagnostic?.file === file).slice(0, 80),
      renamePreview: {
        ok: Boolean(renamePreview.length),
        symbol: queryText,
        newName: renameTo,
        fileCount: renamePreview.length,
        editCount: renamePreview.reduce((count, item) => count + item.edits.length, 0),
        files: renamePreview,
      },
      error: index.error || '',
    };
  }

  return { snapshot, query, extractSymbols, extractImports, extractDiagnostics, languageFor };
}

module.exports = { createWorkspaceIndexHost };
