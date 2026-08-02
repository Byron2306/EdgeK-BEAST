#!/usr/bin/env node
'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
function arg(name, fallback = null) { const i = process.argv.indexOf(name); return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback; }
function digest(value) { return `sha256:${crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex')}`; }
const dir = path.resolve(arg('--receipts', '.'));
const out = path.resolve(arg('--json', path.join(dir, 'phase6_7_matrix_closure.json')));
const files = fs.existsSync(dir) ? fs.readdirSync(dir).filter(n => n.endsWith('.json')) : [];
const receipts = [];
for (const name of files) {
  try {
    const value = JSON.parse(fs.readFileSync(path.join(dir, name), 'utf8'));
    if (value.beast_object_type === 'beast_phase6_7_platform_exit_receipt') receipts.push({ file: name, ...value });
  } catch (_) {}
}
const required = [
  ['linux', 'local'], ['win32', 'local'], ['darwin', 'local'],
  ['linux', 'ssh'], ['linux', 'container'],
];
const matrix = required.map(([platform, target]) => {
  const found = receipts.find(r => r.platform === platform && r.target === target && r.validated === true);
  return { platform, target, passed: Boolean(found), receipt: found?.file || null, digest: found?.receipt_digest || null };
});
const validated = matrix.every(x => x.passed);
const result = {
  beast_object_type: 'beast_phase6_7_cross_platform_closure',
  schema: 'beast.ide.phase6.cross-platform-closure.v1',
  created_at: new Date().toISOString(),
  validated,
  status: validated ? 'pass' : 'incomplete',
  required_matrix: matrix,
  receipts_seen: receipts.map(r => ({ file: r.file, platform: r.platform, target: r.target, validated: r.validated, digest: r.receipt_digest })),
};
result.receipt_digest = digest(result);
fs.mkdirSync(path.dirname(out), { recursive: true });
fs.writeFileSync(out, JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify({ receipt: out, validated, missing: matrix.filter(x => !x.passed), receipt_digest: result.receipt_digest }, null, 2));
process.exit(validated ? 0 : 2);
