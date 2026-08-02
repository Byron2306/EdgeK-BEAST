'use strict';

const path = require('path');

function createWorkspacePathTools({ repoRoot }) {
  if (!repoRoot) throw new Error('createWorkspacePathTools requires repoRoot');

  function safeWorkspacePath(rootPath, relPath) {
    const root = path.resolve(rootPath || repoRoot);
    const target = path.resolve(root, relPath || '');
    if (target === root || !target.startsWith(`${root}${path.sep}`)) {
      return { ok: false, error: 'path escaped workspace', root, target };
    }
    return { ok: true, root, target };
  }

  function taskCwd(rootPath, candidate) {
    const root = path.resolve(rootPath || repoRoot);
    const target = path.resolve(root, String(candidate || '.'));
    return target === root || target.startsWith(`${root}${path.sep}`) ? target : '';
  }

  return { safeWorkspacePath, taskCwd };
}

module.exports = { createWorkspacePathTools };
