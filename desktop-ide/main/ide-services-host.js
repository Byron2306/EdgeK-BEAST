'use strict';
const fs = require('fs');
const path = require('path');

function createIdeServicesHost({
  repoRoot,
  ideCompatibilityHost,
  gitHost,
  taskTestHost,
  executionTargetHost,
  beastExtensionHost,
  workspaceIndexHost = null,
}) {
  if (!repoRoot || !ideCompatibilityHost || !gitHost || !taskTestHost || !executionTargetHost || !beastExtensionHost) {
    throw new Error('createIdeServicesHost requires IDE, Git, task/test, target, and extension dependencies');
  }

  const safeCount = value => Math.max(0, Number(value) || 0);
  const statusOf = value => value ? 'ready' : 'missing';
  const targetSummary = target => executionTargetHost.executionTargetSummary(target || executionTargetHost.getActiveExecutionTarget());
  const LANGUAGE_MATRIX = {
    python: { lsp:['pyright','pylsp'], debug:['debugpy'], tests:['pytest','django'] },
    javascript: { lsp:['typescript'], debug:['node'], tests:['npm','node:test','jest','vitest','playwright','cypress'] },
    typescript: { lsp:['typescript'], debug:['node'], tests:['npm','jest','vitest','playwright','cypress'] },
    go: { lsp:['go'], debug:['delve'], tests:['go'] },
    rust: { lsp:['rust'], debug:['lldb'], tests:['cargo'] },
    java: { lsp:['java'], debug:['java'], tests:['maven','gradle'] },
    csharp: { lsp:['csharp'], debug:['dotnet'], tests:['dotnet'] },
    cpp: { lsp:['clangd'], debug:['lldb'], tests:[] },
    nim: { lsp:['nimlangserver'], debug:[], tests:[] },
  };

  function capabilityRows(discovery, target) {
    const languageRows = (discovery.languages || []).map(item => ({
      id: item.id,
      label: item.label,
      kind: 'lsp',
      status: target.kind === 'local' ? statusOf(item.available) : 'delegated',
      detail: target.kind === 'local' ? item.detail : `delegated over ${target.transport || target.kind}`,
      languages: item.languages || [],
    }));
    const debugRows = (discovery.debug || []).map(item => ({
      id: item.id,
      label: item.label,
      kind: 'dap',
      status: target.kind === 'local' ? statusOf(item.available) : 'delegated',
      detail: target.kind === 'local' ? item.detail : `delegated over ${target.transport || target.kind}`,
    }));
    return { languages: languageRows, debug: debugRows };
  }

  function languageServiceMatrix(index, rows, tests) {
    const languages = Object.keys(index.summary?.languages || {});
    const availableLsp = new Set(rows.languages.filter(item => ['ready', 'delegated'].includes(item.status)).flatMap(item => [item.id, ...(item.languages || [])]));
    const availableDebug = new Set(rows.debug.filter(item => ['ready', 'delegated'].includes(item.status)).map(item => item.id));
    const frameworks = new Set((tests.tests || []).map(item => String(item.framework || '')).filter(Boolean));
    return languages.sort().map(language => {
      const contract = LANGUAGE_MATRIX[language] || { lsp:[], debug:[], tests:[] };
      const lspReady = !contract.lsp.length || contract.lsp.some(item => availableLsp.has(item));
      const debugReady = !contract.debug.length || contract.debug.some(item => availableDebug.has(item));
      const testsReady = !contract.tests.length || contract.tests.some(item => frameworks.has(item));
      const ready = [lspReady, debugReady, testsReady].filter(Boolean).length;
      return { language, files:Number(index.summary?.languages?.[language] || 0), lspReady, debugReady, testsReady, percent:Math.round((ready / 3) * 100), expected:contract };
    });
  }

  function readLaunchCatalog(root) {
    const file = path.join(root, '.vscode', 'launch.json');
    try {
      const text = fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, '').replace(/\/\/.*$/gm, '');
      const value = JSON.parse(text);
      return {
        ok: true,
        file: '.vscode/launch.json',
        configurations: Array.isArray(value.configurations) ? value.configurations.map(item => ({
          name: String(item?.name || '').slice(0, 160),
          type: String(item?.type || '').slice(0, 80),
          request: String(item?.request || '').slice(0, 40),
          program: String(item?.program || item?.module || '').slice(0, 240),
          cwd: String(item?.cwd || '').slice(0, 240),
        })).filter(item => item.name && item.type).slice(0, 80) : [],
        compounds: Array.isArray(value.compounds) ? value.compounds.map(item => ({
          name: String(item?.name || '').slice(0, 160),
          configurations: (Array.isArray(item?.configurations) ? item.configurations : []).map(entry => typeof entry === 'string' ? entry : String(entry?.name || '')).filter(Boolean).slice(0, 20),
        })).filter(item => item.name).slice(0, 40) : [],
      };
    } catch (error) {
      return { ok: false, file: '.vscode/launch.json', configurations: [], compounds: [], error: fs.existsSync(file) ? String(error.message || error) : '' };
    }
  }

  function debugProfiles(index, rows, launchCatalog = { configurations: [], compounds: [] }) {
    const languages = new Set(Object.keys(index.summary?.languages || {}));
    const adapters = new Set(rows.debug.map(item => item.id));
    const profiles = [];
    if (languages.has('python')) profiles.push({ id:'python:file', label:'Python file', adapter:'debugpy', available:adapters.has('debugpy'), handoff:'active Python file or launch.json' });
    if (languages.has('go')) profiles.push({ id:'go:package', label:'Go package', adapter:'delve', available:adapters.has('delve'), handoff:'active Go file package' });
    if (languages.has('rust') || languages.has('cpp')) profiles.push({ id:'native:binary', label:'Native binary', adapter:'lldb', available:adapters.has('lldb'), handoff:'compiled executable path' });
    for (const config of launchCatalog.configurations || []) {
      const adapter = config.type === 'python' ? 'debugpy' : config.type === 'go' ? 'delve' : ['lldb', 'cppdbg', 'cppvsdbg'].includes(config.type) ? 'lldb' : config.type;
      profiles.push({ id:`launch:${config.name}`, label:config.name, adapter, available:adapters.has(adapter) || adapters.has(config.type), handoff:'launch.json', request:config.request, program:config.program });
    }
    return profiles;
  }

  async function scmSnapshot(root, target) {
    if (target.kind === 'local') {
      const status = await gitHost.workspaceGitStatus(root);
      return {
        ok: Boolean(status.ok),
        target,
        mode: 'local-git-host',
        branch: status.branch || '',
        branchName: status.branchName || '',
        counts: status.counts || { staged: 0, unstaged: 0, conflicts: 0 },
        changes: (status.changes || []).slice(0, 200),
        remotes: [],
        error: status.error || '',
      };
    }
    const base = target.kind === 'ssh' ? executionTargetHost.remotePath(target.remoteRoot || target.path || '') : executionTargetHost.remotePath(target.workspaceFolder || target.path || '');
    if (!base) return { ok: false, target, mode: 'remote-git-status', counts: { staged: 0, unstaged: 0, conflicts: 0 }, changes: [], error: 'Remote SCM target has no workspace root.' };
    const command = `cd ${executionTargetHost.shellQuote(base)} && printf 'BEAST_SCM_BRANCH\\n' && git status --porcelain=v1 --branch && printf 'BEAST_SCM_REMOTES\\n' && git remote -v`;
    const result = await executionTargetHost.runOnExecutionTarget(target, root, 'sh', ['-lc', command], { timeoutMs: 20000, outputLimit: 192000 });
    const stdout = String(result.stdout || '');
    const branchPart = stdout.includes('BEAST_SCM_REMOTES') ? stdout.split('BEAST_SCM_REMOTES', 1)[0] : stdout;
    const lines = branchPart.split(/\r?\n/).filter(line => line && line !== 'BEAST_SCM_BRANCH');
    const branch = lines.find(line => line.startsWith('## ')) || '';
    const changes = lines.filter(line => !line.startsWith('## ')).slice(0, 200).map(line => {
      const index = line.slice(0, 2);
      const filePath = line.slice(3);
      return {
        index,
        path: filePath,
        staged: index[0] !== ' ' && index[0] !== '?',
        unstaged: index[1] !== ' ' || index === '??',
        conflict: /U|AA|DD/.test(index),
        untracked: index === '??',
      };
    });
    const remotes = stdout.includes('BEAST_SCM_REMOTES') ? stdout.split('BEAST_SCM_REMOTES', 2)[1].split(/\r?\n/).filter(Boolean).slice(0, 80) : [];
    return {
      ok: Boolean(result.ok),
      target,
      mode: 'remote-git-status',
      branch,
      branchName: branch.replace(/^##\s+/, '').split('...')[0].trim(),
      counts: {
        staged: changes.filter(item => item.staged).length,
        unstaged: changes.filter(item => item.unstaged).length,
        conflicts: changes.filter(item => item.conflict).length,
      },
      changes,
      remotes,
      error: result.ok ? '' : String(result.stderr || result.error || 'remote Git status failed'),
    };
  }

  function score(sections) {
    const checks = [
      sections.lsp.languages.length > 0,
      sections.debug.adapters.length > 0,
      sections.index.ok,
      sections.tests.ok,
      sections.tasks.ok,
      sections.scm.ok,
      Boolean(sections.extensions.lifecycle),
      sections.extensions.runtimeReady,
    ];
    return {
      ready: checks.filter(Boolean).length,
      total: checks.length,
      percent: Math.round((checks.filter(Boolean).length / checks.length) * 100),
    };
  }

  async function snapshot(rootPath, options = {}) {
    const root = String(rootPath || repoRoot);
    const target = targetSummary(options.target || executionTargetHost.getActiveExecutionTarget());
    const [discovery, tests, tasks, history, scm, extensions, index] = await Promise.all([
      Promise.resolve(ideCompatibilityHost.discover(root)),
      taskTestHost.workspaceTestsForTarget(root, { target }),
      Promise.resolve(taskTestHost.workspaceTasks(root)),
      Promise.resolve(typeof taskTestHost.historySummary === 'function' ? taskTestHost.historySummary() : { ok: true, tests: [], tasks: [], counts: { tests: 0, tasks: 0 } }),
      scmSnapshot(root, target),
      Promise.resolve(beastExtensionHost.lifecycleStatus(target)),
      workspaceIndexHost ? workspaceIndexHost.snapshot(root, { target, limit: 4000 }) : Promise.resolve({ ok: false, summary: {}, files: [], symbols: [], imports: [], error: 'workspace index host is unavailable' }),
    ]);
    const rows = capabilityRows(discovery, target);
    const launchCatalog = readLaunchCatalog(root);
    const sections = {
      target,
      lsp: {
        status: rows.languages.some(item => ['ready', 'delegated'].includes(item.status)) ? 'ready' : 'missing',
        languages: rows.languages,
        sessions: (discovery.sessions || []).filter(item => item.kind === 'lsp'),
        matrix: languageServiceMatrix(index, rows, tests),
      },
      debug: {
        status: rows.debug.some(item => ['ready', 'delegated'].includes(item.status)) ? 'ready' : 'missing',
        adapters: rows.debug,
        sessions: (discovery.sessions || []).filter(item => item.kind === 'dap'),
        profiles: debugProfiles(index, rows, launchCatalog),
        launch: launchCatalog,
      },
      index: {
        ok: Boolean(index.ok),
        status: index.ok ? 'ready' : 'error',
        digest: index.indexDigest || '',
        fileCount: safeCount(index.summary?.fileCount),
        symbolCount: safeCount(index.summary?.symbolCount),
        importCount: safeCount(index.summary?.importCount),
        referenceCount: safeCount(index.summary?.referenceCount || index.semantic?.referenceCount),
        importEdgeCount: safeCount(index.summary?.importEdgeCount || index.semantic?.importEdgeCount),
        languages: index.summary?.languages || {},
        symbolKinds: index.summary?.symbolKinds || {},
        semantic: {
          definitionCount: safeCount(index.semantic?.definitionCount),
          referenceCount: safeCount(index.semantic?.referenceCount),
          importEdgeCount: safeCount(index.semantic?.importEdgeCount),
          unresolvedImportCount: safeCount(index.semantic?.unresolvedImportCount),
          topReferences: (index.semantic?.topReferences || []).slice(0, 20),
          importEdges: (index.semantic?.importEdges || []).slice(0, 80),
          dependents: index.semantic?.dependents || {},
          workspaceSymbols: (index.semantic?.workspaceSymbols || []).slice(0, 200),
        },
        diagnostics: (index.diagnostics || []).slice(0, 80),
        codeActions: (index.codeActions || []).slice(0, 80),
        source: index.source || '',
        truncated: Boolean(index.truncated),
        error: index.error || '',
      },
      navigation: {
        ok: Boolean(index.ok && index.semantic?.workspaceSymbols?.length),
        status: index.ok && index.semantic?.workspaceSymbols?.length ? 'ready' : 'limited',
        workspaceSymbolCount: safeCount(index.semantic?.workspaceSymbols?.length),
        topReferenceCount: safeCount(index.semantic?.topReferences?.length),
        importEdgeCount: safeCount(index.semantic?.importEdgeCount),
        supports: {
          workspaceSymbols: Boolean(index.semantic?.workspaceSymbols?.length),
          definitions: Boolean(index.semantic?.workspaceSymbols?.length),
          references: Boolean(index.semantic?.topReferences?.length),
          dependents: Boolean(Object.keys(index.semantic?.dependents || {}).length),
        },
      },
      diagnostics: {
        ok: Boolean(index.ok),
        status: index.ok ? 'ready' : 'limited',
        count: safeCount(index.diagnostics?.length),
        bySeverity: (index.diagnostics || []).reduce((memo, item) => { const key = String(item.severity || 'information'); memo[key] = (memo[key] || 0) + 1; return memo; }, {}),
        codeActionCount: safeCount(index.codeActions?.length),
        recent: (index.diagnostics || []).slice(0, 40),
      },
      refactor: {
        ok: Boolean(index.ok && index.semantic?.workspaceSymbols?.length),
        status: index.ok && index.semantic?.workspaceSymbols?.length ? 'ready' : 'limited',
        supportsRenamePreview: Boolean(index.semantic?.topReferences?.length),
        supportsCodeActions: Boolean(index.codeActions?.length),
        symbolCount: safeCount(index.semantic?.workspaceSymbols?.length),
      },
      tests: {
        ok: Boolean(tests.ok),
        status: tests.ok ? 'ready' : 'error',
        testCount: safeCount((tests.tests || []).length),
        fileCount: safeCount((tests.files || []).length),
        nodeCount: safeCount((tests.nodes || []).length),
        frameworks: [...new Set((tests.tests || []).map(item => String(item.framework || '')).filter(Boolean))].sort(),
        historyCount: safeCount(history.counts?.tests),
        flakyCount: safeCount(history.counts?.flakyTests),
        flaky: (history.flakyTests || []).slice(0, 20),
        recent: (history.tests || []).slice(0, 20),
        executionTarget: tests.executionTarget || target,
        error: tests.error || '',
      },
      tasks: {
        ok: Boolean(tasks.ok),
        status: tasks.ok ? 'ready' : 'error',
        taskCount: safeCount((tasks.tasks || []).length),
        backgroundCount: safeCount((tasks.tasks || []).filter(item => item.isBackground).length),
        dependencyTaskCount: safeCount((tasks.tasks || []).filter(item => (item.dependsOn || []).length).length),
        presentationCount: safeCount((tasks.tasks || []).filter(item => item.presentation && Object.keys(item.presentation).length).length),
        problemMatcherCount: safeCount((tasks.tasks || []).reduce((count, item) => count + ((item.problemMatchers || []).length || 0), 0)),
        historyCount: safeCount(history.counts?.tasks),
        recent: (history.tasks || []).slice(0, 20),
        error: tasks.error || '',
      },
      scm,
      extensions: {
        status: extensions.active?.status || 'unknown',
        runtimeReady: ['running', 'deployed', 'idle'].includes(String(extensions.active?.status || '')),
        lifecycle: extensions.active || null,
        targets: extensions.targets || [],
      },
    };
    return {
      ok: true,
      beast_object_type: 'beast_ide_services_snapshot',
      version: '1.0',
      root,
      target,
      updatedAt: new Date().toISOString(),
      score: score(sections),
      services: sections,
    };
  }

  return { snapshot };
}

module.exports = { createIdeServicesHost };
