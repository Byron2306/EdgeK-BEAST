// Phase 10 IPC gateway-request example. Add to the existing main process and keep your current security checks.
const { ipcMain } = require('electron');
ipcMain.handle('beast:gateway-request', async (_event, request) => {
  const base = process.env.BEAST_GATEWAY_URL || 'http://127.0.0.1:8101';
  const target = new URL(request.path || request.url, base);
  if (!['127.0.0.1','localhost'].includes(target.hostname)) throw new Error('Blocked non-local gateway target');
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), Math.min(Number(request.timeoutMs)||6000, 120000));
  try {
    const response = await fetch(target, {
      method: request.method || 'GET',
      headers: { Accept:'application/json', ...(request.body ? {'Content-Type':'application/json'} : {}), ...(request.headers||{}) },
      body: request.body == null ? undefined : JSON.stringify(request.body),
      signal: controller.signal
    });
    const type = response.headers.get('content-type') || '';
    const data = type.includes('application/json') ? await response.json() : await response.text();
    return { ok: response.ok, status: response.status, data, error: response.ok ? '' : String(data) };
  } finally { clearTimeout(timer); }
});
