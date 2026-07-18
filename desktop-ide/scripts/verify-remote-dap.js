const path = require('path');
const { IdeCompatibilityHost } = require('../ide-compatibility-host');

const repo = path.resolve(__dirname, '..', '..');
const rows = [];
const record = (name, status, detail = '') => rows.push({ name, status, detail });

function handshake(name, target, adapter) {
  return new Promise(resolve => {
    const host = new IdeCompatibilityHost(repo);
    let settled = false;
    const finish = (status, detail = '') => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      host.stopAll();
      record(name, status, detail);
      resolve();
    };
    const sender = {
      isDestroyed: () => false,
      send: (_channel, message) => {
        if (message?.type === 'ready') finish('passed', `${target.kind} ${adapter} initialized`);
        if (message?.type === 'error') finish('failed', String(message.error || 'DAP initialization failed'));
      },
    };
    let timer = setTimeout(() => finish('failed', 'DAP initialization timed out after 15 seconds'), 15000);
    try {
      host.start({ kind: 'dap', adapter, root: repo, target }, sender);
    } catch (error) {
      finish('failed', String(error.message || error));
    }
  });
}

async function main() {
  const sshHost = process.env.BEAST_PARITY_SSH_HOST;
  if (sshHost) await handshake('SSH remote DAP handshake', { kind: 'ssh', host: sshHost, remoteRoot: process.env.BEAST_PARITY_SSH_ROOT || '~' }, process.env.BEAST_PARITY_SSH_DAP_ADAPTER || 'debugpy');
  else record('SSH remote DAP handshake', 'skipped', 'Set BEAST_PARITY_SSH_HOST and BEAST_PARITY_SSH_ROOT to validate a real remote adapter.');
  const containerId = process.env.BEAST_PARITY_CONTAINER_ID;
  if (containerId) await handshake('Container DAP handshake', { kind: 'container', containerId, workspaceFolder: process.env.BEAST_PARITY_CONTAINER_WORKSPACE || '/workspace' }, process.env.BEAST_PARITY_CONTAINER_DAP_ADAPTER || 'debugpy');
  else record('Container DAP handshake', 'skipped', 'Set BEAST_PARITY_CONTAINER_ID to validate a running container adapter.');
  const failed = rows.filter(row => row.status === 'failed');
  console.log(JSON.stringify({ ok: failed.length === 0, checks: rows.length, passed: rows.filter(row => row.status === 'passed').length, skipped: rows.filter(row => row.status === 'skipped').length, failed }, null, 2));
  if (failed.length) process.exit(1);
}

main().catch(error => { console.error(error); process.exit(1); });
