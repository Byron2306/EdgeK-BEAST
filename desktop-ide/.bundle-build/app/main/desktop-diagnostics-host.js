'use strict';

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

function createDesktopDiagnosticsHost({ repoRoot, desktopRoot, buildIdentity, desktopVersion, safeWorkspacePath, getActiveWorkspaceRoot, getGatewaySnapshot }) {
  let resolvedBeastPython = null;

function runDesktopScript(scriptName) {
  const scriptPath = path.join(desktopRoot, 'scripts', scriptName);
  if (!fs.existsSync(scriptPath)) {
    return { ran: false, ok: false, error: `${scriptName} missing`, script: scriptPath };
  }
  try {
    const completed = spawnSync('node', [scriptPath], {
      cwd: desktopRoot,
      encoding: 'utf8',
      timeout: 30000,
    });
    return {
      ran: true,
      ok: completed.status === 0,
      returncode: completed.status,
      stdout: String(completed.stdout || '').slice(-4000),
      stderr: String(completed.stderr || '').slice(-4000),
      script: scriptPath,
    };
  } catch (error) {
    return { ran: true, ok: false, error: String(error.message || error), script: scriptPath };
  }
}

function localReleaseReadiness(rootPath = repoRoot) {
  const gatewaySnapshot = getGatewaySnapshot();
  const root = path.resolve(rootPath || repoRoot);
  const files = {
    desktop_package: path.join(desktopRoot, 'package.json'),
    desktop_main: path.join(desktopRoot, 'main.js'),
    desktop_preload: path.join(desktopRoot, 'preload.js'),
    desktop_renderer: path.join(desktopRoot, 'renderer', 'app.js'),
    desktop_html: path.join(desktopRoot, 'renderer', 'index.html'),
    desktop_styles: path.join(desktopRoot, 'renderer', 'styles.css'),
    desktop_smoke: path.join(desktopRoot, 'scripts', 'smoke-desktop-ide.js'),
    desktop_launch_smoke: path.join(desktopRoot, 'scripts', 'launch-smoke-desktop-ide.js'),
    ide_routes: path.join(root, 'app', 'routes', 'ide.py'),
    desktop_tests: path.join(root, 'tests', 'test_desktop_ide_manifest.py'),
  };
  const read = filePath => {
    try {
      return fs.readFileSync(filePath, 'utf8');
    } catch (_error) {
      return '';
    }
  };
  const packageText = read(files.desktop_package);
  const rendererText = read(files.desktop_renderer);
  const htmlText = read(files.desktop_html);
  const mainModuleDir = path.join(desktopRoot, 'main');
  const mainText = [read(files.desktop_main), ...((fs.existsSync(mainModuleDir) ? fs.readdirSync(mainModuleDir) : []).filter(name => name.endsWith('.js')).map(name => read(path.join(mainModuleDir, name))) )].join('\n');
  const preloadText = read(files.desktop_preload);
  const routeText = read(files.ide_routes);
  const smoke = runDesktopScript('smoke-desktop-ide.js');
  const launchSmoke = runDesktopScript('launch-smoke-desktop-ide.js');
  const checks = [
    ...Object.entries(files).map(([name, filePath]) => ({ check: `${name}_exists`, passed: fs.existsSync(filePath), path: filePath })),
    { check: 'monaco_packaged', passed: packageText.includes('monaco-editor') },
    { check: 'command_palette_modal_present', passed: htmlText.includes('commandPaletteOverlay') && rendererText.includes('openCommandPaletteModal') },
    { check: 'status_chips_present', passed: htmlText.includes('statusChipBar') && rendererText.includes('updateStatusChips') },
    { check: 'local_readiness_ipc_present', passed: mainText.includes('localReleaseReadiness') && preloadText.includes('releaseReadiness') },
    { check: 'release_route_present', passed: routeText.includes('release-readiness/check') },
    { check: 'desktop_smoke_passed', passed: Boolean(smoke.ok), detail: smoke },
    { check: 'desktop_launch_smoke_passed', passed: Boolean(launchSmoke.ok), detail: launchSmoke },
  ];
  const passed = checks.filter(item => item.passed).length;
  return {
    ok: passed === checks.length,
    beast_object_type: 'beast_desktop_local_release_readiness',
    version: desktopVersion,
    build_identity: buildIdentity,
    source: 'electron_main_local',
    created_at: Date.now(),
    repoRoot: root,
    desktopRoot: desktopRoot,
    status: passed === checks.length ? 'pass' : 'warn',
    summary: { checks: checks.length, passed, failed: checks.length - passed },
    checks,
    smoke,
    launch_smoke: launchSmoke,
    gateway: {
      url: gatewaySnapshot.url,
      local_mode: gatewaySnapshot.localMode,
      processPid: gatewaySnapshot.processPid || null,
    },
    read_only: true,
  };
}

function commandVersion(command, args = ['--version']) {
  try {
    const completed = spawnSync(command, args, {
      cwd: repoRoot,
      encoding: 'utf8',
      timeout: 5000,
    });
    const output = String(completed.stdout || completed.stderr || '').trim().split('\n')[0] || 'available';
    return { ok: completed.status === 0, command, version: output, returncode: completed.status };
  } catch (error) {
    return { ok: false, command, error: String(error.message || error) };
  }
}

function syntaxCheckFile(rootPath = repoRoot, relPath = '') {
  if (!relPath) return { ok: true, status: 'idle', detail: 'No active file selected.' };
  const pathCheck = safeWorkspacePath(rootPath || repoRoot, relPath);
  if (!pathCheck.ok) return { ok: false, status: 'blocked', detail: pathCheck.error, path: relPath };
  const suffix = path.extname(pathCheck.target).toLowerCase();
  try {
    if (suffix === '.json') {
      JSON.parse(fs.readFileSync(pathCheck.target, 'utf8'));
      return { ok: true, status: 'pass', kind: 'json', path: relPath };
    }
    if (suffix === '.js' || suffix === '.mjs' || suffix === '.cjs') {
      const completed = spawnSync('node', ['--check', pathCheck.target], { encoding: 'utf8', timeout: 10000 });
      return {
        ok: completed.status === 0,
        status: completed.status === 0 ? 'pass' : 'warn',
        kind: 'node',
        path: relPath,
        stdout: String(completed.stdout || '').slice(-2000),
        stderr: String(completed.stderr || '').slice(-2000),
      };
    }
    if (suffix === '.py') {
      const completed = spawnSync('python3', ['-m', 'py_compile', pathCheck.target], { encoding: 'utf8', timeout: 10000 });
      return {
        ok: completed.status === 0,
        status: completed.status === 0 ? 'pass' : 'warn',
        kind: 'python',
        path: relPath,
        stdout: String(completed.stdout || '').slice(-2000),
        stderr: String(completed.stderr || '').slice(-2000),
      };
    }
    return { ok: true, status: 'skipped', kind: suffix || 'text', path: relPath, detail: 'No syntax checker registered for this file type.' };
  } catch (error) {
    return { ok: false, status: 'warn', path: relPath, error: String(error.message || error) };
  }
}

function localToolingSnapshot(rootPath = repoRoot, activeFile = '') {
  const root = path.resolve(rootPath || repoRoot);
  const packagePath = path.join(root, 'package.json');
  const desktopPackagePath = path.join(root, 'desktop-ide', 'package.json');
  const cursorMcp = path.join(root, '.cursor', 'mcp.json');
  const vscodeDir = path.join(root, 'vscode-extension');
  const desktopDir = path.join(root, 'desktop-ide');
  const readJson = filePath => {
    try {
      return JSON.parse(fs.readFileSync(filePath, 'utf8'));
    } catch (_error) {
      return {};
    }
  };
  const rootPackage = readJson(packagePath);
  const desktopPackage = readJson(desktopPackagePath);
  const scripts = {
    root: Object.keys(rootPackage.scripts || {}),
    desktop: Object.keys(desktopPackage.scripts || {}),
  };
  const env = [
    commandVersion('python3', ['--version']),
    commandVersion('node', ['--version']),
    commandVersion('npm', ['--version']),
    commandVersion('git', ['--version']),
  ];
  const mcpConfigured = fs.existsSync(cursorMcp);
  return {
    ok: true,
    beast_object_type: 'beast_desktop_local_tooling_snapshot',
    version: desktopVersion,
    source: 'electron_main_local',
    repoRoot: root,
    activeFile,
    syntax: syntaxCheckFile(root, activeFile),
    linting: {
      scripts,
      has_root_lint: scripts.root.some(item => item.includes('lint')),
      has_desktop_smoke: scripts.desktop.includes('smoke'),
      has_launch_smoke: scripts.desktop.includes('smoke:launch'),
      recommendation: scripts.root.some(item => item.includes('lint'))
        ? 'Use the project lint script through the governed terminal.'
        : 'No root lint script detected; use syntax checks and focused tests until a lint contract is added.',
    },
    mcp: {
      configured: mcpConfigured,
      cursor_config: cursorMcp,
      expected_routes: ['/edgek/mcp/state', '/edgek/mcp/servers', '/edgek/mcp/audit', '/edgek/mcp/executions', '/edgek/mcp/approvals'],
      status: mcpConfigured ? 'configured' : 'no local .cursor/mcp.json',
    },
    plugins: {
      vscode_extension_present: fs.existsSync(vscodeDir),
      desktop_ide_present: fs.existsSync(desktopDir),
      expected_routes: ['/edgek/plugins', '/edgek/plugins/manifest/prepare', '/edgek/plugins/manifest/validate', '/edgek/plugins/install'],
      status: fs.existsSync(vscodeDir) || fs.existsSync(desktopDir) ? 'local surfaces present' : 'no local plugin surfaces detected',
    },
    environments: env,
    read_only: true,
  };
}

function localSystemSnapshot(rootPath = repoRoot) {
  const root = path.resolve(rootPath || getActiveWorkspaceRoot() || repoRoot);
  const python = resolveBeastPython();
  const code = [
    'import json, sys',
    'from pathlib import Path',
    'from app.kernel.workspaces import system_inspector',
    'root = Path(sys.argv[1]).resolve()',
    'snap = system_inspector.system_snapshot(root, port_limit=120, process_limit=80)',
    'snap["catalog"] = system_inspector.catalog_report(root)',
    'print(json.dumps(snap, default=str))',
  ].join('; ');
  const completed = spawnSync(python, ['-c', code, repoRoot], {
    cwd: repoRoot,
    env: { ...process.env, BEAST_ACTIVE_WORKSPACE: root, BEAST_WORKSPACE: root },
    encoding: 'utf8',
    timeout: 12000,
  });
  if (completed.error) {
    return { ok: false, source: 'electron_main_local', error: String(completed.error.message || completed.error) };
  }
  if (completed.status !== 0) {
    return {
      ok: false,
      source: 'electron_main_local',
      error: (completed.stderr || completed.stdout || `python exited ${completed.status}`).trim(),
    };
  }
  try {
    return { ...JSON.parse(completed.stdout || '{}'), source: 'electron_main_local' };
  } catch (error) {
    return { ok: false, source: 'electron_main_local', error: String(error.message || error), raw: completed.stdout };
  }
}

function resolveBeastPython() {
  if (resolvedBeastPython) return resolvedBeastPython;
  const candidates = [
    process.env.BEAST_PYTHON,
    path.join(repoRoot, 'venv', 'bin', 'python'),
    path.join(repoRoot, '.venv', 'bin', 'python'),
    'python3',
    'python',
  ].filter(Boolean);
  for (const candidate of candidates) {
    const completed = spawnSync(candidate, ['-c', 'import fastapi, uvicorn, cryptography, yaml'], {
      cwd: repoRoot,
      encoding: 'utf8',
      timeout: 5000,
    });
    if (!completed.error && completed.status === 0) {
      resolvedBeastPython = candidate;
      return resolvedBeastPython;
    }
  }
  resolvedBeastPython = process.env.BEAST_PYTHON || 'python3';
  return resolvedBeastPython;
}


  return { localReleaseReadiness, localToolingSnapshot, localSystemSnapshot, resolveBeastPython, syntaxCheckFile, commandVersion };
}

module.exports = { createDesktopDiagnosticsHost };
