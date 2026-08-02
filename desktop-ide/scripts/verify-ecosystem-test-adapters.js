'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const { createTaskTestHost } = require('../main/task-test-host');

function write(file, text = '') {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, text, 'utf8');
}

function walk(root, dir = root, rows = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const target = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(root, target, rows);
    else rows.push({
      path: path.relative(root, target).replace(/\\/g, '/'),
      name: entry.name,
      size: fs.statSync(target).size,
    });
  }
  return rows;
}

const root = fs.mkdtempSync(path.join(os.tmpdir(), 'beast-ecosystem-tests-'));
write(path.join(root, 'package.json'), JSON.stringify({ scripts: { 'test:e2e': 'playwright test', 'cy:run': 'cypress run' } }));
write(path.join(root, 'go.mod'), 'module example.test/beast\n');
write(path.join(root, 'pkg/service/service_test.go'), 'package service\n');
write(path.join(root, 'Cargo.toml'), '[package]\nname="beast"\nversion="0.1.0"\nedition="2021"\n');
write(path.join(root, 'tests/integration.rs'), '#[test]\nfn works() {}\n');
write(path.join(root, 'pom.xml'), '<project></project>\n');
write(path.join(root, 'src/test/java/AppTest.java'), 'class AppTest {}\n');
write(path.join(root, 'build.gradle'), 'plugins { id "java" }\n');
write(path.join(root, 'Beast.sln'), '\n');
write(path.join(root, 'tests/BeastTests.cs'), 'public class BeastTests {}\n');
write(path.join(root, 'playwright.config.ts'), 'export default {};\n');
write(path.join(root, 'e2e/home.spec.ts'), 'test("home", async () => {});\n');
write(path.join(root, 'cypress.config.ts'), 'export default {};\n');
write(path.join(root, 'cypress/e2e/home.cy.ts'), 'describe("home", () => {});\n');

const targetHost = {
  executionTargetSummary: target => target || { kind: 'local' },
  runOnExecutionTarget: async () => ({ ok: true, stdout: '', stderr: '', returncode: 0 }),
  remotePath: value => value,
  shellQuote: value => `'${String(value).replaceAll("'", "'\\''")}'`,
  targetRelativePath: value => String(value || '').replace(/^\.?\//, ''),
  getActiveExecutionTarget: () => ({ kind: 'local' }),
};
const host = createTaskTestHost({
  repoRoot: root,
  workspaceFileCandidates: candidateRoot => walk(candidateRoot),
  safeWorkspacePath: (candidateRoot, file) => {
    const target = path.resolve(candidateRoot, file);
    return target.startsWith(path.resolve(candidateRoot) + path.sep) ? { ok: true, target } : { ok: false };
  },
  taskCwd: candidateRoot => candidateRoot,
  getTargetHost: () => targetHost,
});

const catalog = host.workspaceTests(root);
const frameworks = new Set(catalog.tests.map(item => item.framework));
const nodes = new Set(catalog.nodes.map(item => item.framework));
for (const expected of ['go', 'cargo', 'maven', 'gradle', 'dotnet', 'playwright', 'cypress']) {
  if (!frameworks.has(expected)) throw new Error(`Missing ${expected} workspace test adapter`);
}
for (const expected of ['go', 'cargo', 'java', 'dotnet', 'playwright', 'cypress']) {
  if (!nodes.has(expected)) throw new Error(`Missing ${expected} test node discovery`);
}

const report = { ok: true, tests: catalog.tests.length, nodes: catalog.nodes.length, frameworks: [...frameworks].sort() };
fs.mkdirSync(path.join(path.resolve(__dirname, '..', '..'), 'build'), { recursive: true });
fs.writeFileSync(
  path.join(path.resolve(__dirname, '..', '..'), 'build', 'ECOSYSTEM_TEST_ADAPTERS.json'),
  `${JSON.stringify(report, null, 2)}\n`,
  'utf8',
);
console.log(JSON.stringify(report));
