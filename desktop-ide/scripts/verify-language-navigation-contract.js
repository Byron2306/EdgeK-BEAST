#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const repoRoot = path.resolve(__dirname, '..', '..');
const foundationArtifact = path.join(repoRoot, 'build', 'PARITY_FOUNDATION.json');
const servicesArtifact = path.join(repoRoot, 'build', 'IDE_SERVICES_PARITY.json');
const artifactPath = path.join(repoRoot, 'build', 'LANGUAGE_NAVIGATION_CONTRACT.json');

function runScript(script) {
  return spawnSync(process.execPath, [path.join(__dirname, script)], {
    cwd: repoRoot,
    encoding: 'utf8',
    timeout: 180000,
    maxBuffer: 1024 * 1024,
  });
}

function readJson(file) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (_) {
    return null;
  }
}

function main() {
  const foundationRun = runScript('verify-ide-parity-foundation.js');
  const servicesRun = runScript('verify-ide-services-parity.js');
  const foundation = readJson(foundationArtifact);
  const services = readJson(servicesArtifact);
  const handshakes = foundation?.handshakes || {};
  const snapshot = services?.snapshot?.services || {};
  const semantic = services?.semanticQueries || {};
  const ok =
    foundationRun.status === 0 &&
    servicesRun.status === 0 &&
    foundation?.ok === true &&
    services?.ok === true &&
    handshakes.typescript === 'passed' &&
    handshakes.python === 'passed' &&
    handshakes.pylsp === 'passed' &&
    handshakes.bash === 'passed' &&
    handshakes.go === 'passed' &&
    handshakes.rust === 'passed' &&
    handshakes.clangd === 'passed' &&
    snapshot.lsp?.languages?.length >= 5 &&
    snapshot.index?.ok === true &&
    snapshot.navigation?.ok === true &&
    snapshot.refactor?.ok === true &&
    snapshot.diagnostics?.ok === true &&
    semantic.symbolQuery?.symbols?.some(item => item.name === 'answer') &&
    semantic.definitionQuery?.definitions?.some(item => item.file === 'src/helper.js') &&
    semantic.referenceQuery?.references?.some(item => item.file === 'src/math.nim') &&
    semantic.dependentsQuery?.dependents?.includes('src/index.js') &&
    semantic.renamePreview?.renamePreview?.ok === true;
  const report = {
    ok,
    date: '2026-07-31',
    checks: 7 + 9,
    artifacts: {
      foundation: 'build/PARITY_FOUNDATION.json',
      services: 'build/IDE_SERVICES_PARITY.json',
    },
    handshakes: {
      typescript: handshakes.typescript,
      python: handshakes.python,
      pylsp: handshakes.pylsp,
      bash: handshakes.bash,
      go: handshakes.go,
      rust: handshakes.rust,
      clangd: handshakes.clangd,
    },
    semantic: {
      lspLanguages: snapshot.lsp?.languages?.length || 0,
      navigation: snapshot.navigation?.ok === true,
      diagnostics: snapshot.diagnostics?.ok === true,
      refactor: snapshot.refactor?.ok === true,
      symbolQuery: Boolean(semantic.symbolQuery?.symbols?.length),
      definitionQuery: Boolean(semantic.definitionQuery?.definitions?.length),
      referenceQuery: Boolean(semantic.referenceQuery?.references?.length),
      dependentsQuery: Boolean(semantic.dependentsQuery?.dependents?.length),
      renamePreview: semantic.renamePreview?.renamePreview?.ok === true,
    },
  };
  fs.mkdirSync(path.dirname(artifactPath), { recursive: true });
  fs.writeFileSync(artifactPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
  console.log(JSON.stringify(report, null, 2));
  process.exit(ok ? 0 : 1);
}

main();
