#!/usr/bin/env node
'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const repoRoot = path.resolve(__dirname, '..', '..');
const gatewayHost = fs.readFileSync(path.join(repoRoot, 'desktop-ide', 'main', 'gateway-host.js'), 'utf8');
const ipcRegistry = fs.readFileSync(path.join(repoRoot, 'desktop-ide', 'main', 'ipc-registry.js'), 'utf8');

const checks = [
  ['single-flight startup joins existing gateway attempts', gatewayHost.includes('gateway startup already in progress; joining existing attempt') && gatewayHost.includes('gatewayStartupPromise')],
  ['busy active listener does not trigger port hopping for ordinary requests', gatewayHost.includes('is listening but busy') && gatewayHost.includes('retaining target')],
  ['compatible-port discovery verifies desktop contract before attach', gatewayHost.includes('ready.ok && ready.capabilities?.ok')],
  ['bounded managed startup falls back to local IDE mode', gatewayHost.includes('enterLocalIdeMode') && gatewayHost.includes('managed BEAST gateway did not become ready quickly')],
  ['status recovery preserves managed compatible port', gatewayHost.includes('recoverStatusHealth') && gatewayHost.includes('status probe recovered compatible BEAST gateway')],
  ['gateway status uses recovered active URL for runtime stack', ipcRegistry.includes('gatewayHost.runtimeStackHealth(health.url || gatewayHost.getGatewayUrl())')],
  ['gateway request body and response are bounded', gatewayHost.includes('4 * 1024 * 1024') && gatewayHost.includes('8 * 1024 * 1024')],
  ['gateway event stream remains main-process mediated', gatewayHost.includes('GatewayEventStreamHost') && ipcRegistry.includes('beast:gateway-stream-start')],
];

for (const [label, ok] of checks) assert.ok(ok, label);

const report = { ok:true, checks:checks.length, mode:'static gateway stability contract' };
fs.mkdirSync(path.join(repoRoot, 'build'), { recursive:true });
fs.writeFileSync(path.join(repoRoot, 'build', 'GATEWAY_STABILITY_CONTRACT.json'), `${JSON.stringify(report, null, 2)}\n`);
console.log(JSON.stringify(report, null, 2));
