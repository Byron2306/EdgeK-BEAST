'use strict';

const fs = require('fs');
const path = require('path');

function resolveRepoRoot({ baseDirectory = path.resolve(__dirname, '..'), env = process.env, cwd = process.cwd() } = {}) {
  const candidates = [
    env.BEAST_REPO_ROOT,
    env.BEAST_WORKSPACE,
    cwd,
    path.resolve(baseDirectory, '..'),
    path.resolve(baseDirectory, '..', '..', '..', '..'),
    path.resolve(baseDirectory, '..', '..', '..', '..', '..'),
  ].filter(Boolean);
  for (const candidate of candidates) {
    const root = path.resolve(candidate);
    if (fs.existsSync(path.join(root, 'bin', 'beast')) && fs.existsSync(path.join(root, 'app', 'main.py'))) return root;
  }
  return path.resolve(baseDirectory, '..');
}

function runtimeResourcePath(baseDirectory, resourcesPath, ...parts) {
  const resource = resourcesPath ? path.join(resourcesPath, ...parts) : '';
  return resource && fs.existsSync(resource) ? resource : path.join(baseDirectory, ...parts);
}

function pythonToolRoot(baseDirectory, resourcesPath) {
  const resource = resourcesPath ? path.join(resourcesPath, 'python-tools') : '';
  return resource && fs.existsSync(resource) ? resource : path.join(baseDirectory, '.beast-python-tools');
}

module.exports = { resolveRepoRoot, runtimeResourcePath, pythonToolRoot };
