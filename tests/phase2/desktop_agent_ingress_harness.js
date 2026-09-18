const fs = require('fs');
const vm = require('vm');

async function main() {
  const baseUrl = String(process.env.BEAST_PHASE2_GATEWAY_URL || '').replace(/\/$/, '');
  const workspace = String(process.env.BEAST_PHASE2_WORKSPACE || '');
  const clientPath = String(process.env.BEAST_PHASE2_AGENT_CLIENT || 'desktop-ide/renderer/js/ai/agent-client.js');
  if (!baseUrl || !workspace) throw new Error('BEAST_PHASE2_GATEWAY_URL and BEAST_PHASE2_WORKSPACE are required');

  global.window = { BeastAICodingModules: {} };
  global.BeastRuntime = {
    request: async (path, options = {}) => {
      const response = await fetch(baseUrl + path, {
        method: options.method || 'GET',
        headers: { 'content-type': 'application/json' },
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
      });
      const text = await response.text();
      let payload = {};
      try { payload = text ? JSON.parse(text) : {}; } catch (_) { payload = { raw: text }; }
      if (!response.ok) throw new Error(`HTTP ${response.status}: ${text}`);
      return payload;
    },
  };

  const source = fs.readFileSync(clientPath, 'utf8');
  vm.runInThisContext(source, { filename: clientPath });
  const patches = [];
  const runtime = {
    api: {
      patch: update => patches.push(update),
      persist: () => {},
    },
    root: () => workspace,
    gatewayUrl: () => baseUrl,
    stateKey: 'phase2-desktop-ingress',
    now: () => Date.now(),
    openRunStream: () => { throw new Error('stream not expected in createSession acceptance'); },
    parseActionIntent: () => null,
    looksLikeActionIntent: () => false,
    constants: {
      MAX_CONTEXT_FILES: 12,
      RELIABLE_LOCAL_CODER: 'qwen2.5-coder:7b',
      RELIABLE_LOCAL_PROFILE: {},
      RELIABLE_PLANNER_PROFILE: {},
    },
  };
  const client = window.BeastAICodingModules.createAgentClient(runtime);
  const sessionId = await client.createSession(
    'Phase 2 desktop ingress acceptance',
    ['sample.py'],
    'phase2-model',
    'phase2-provider',
    'analysis'
  );
  process.stdout.write(JSON.stringify({
    ok: true,
    session_id: sessionId,
    renderer_module: clientPath,
    request_path: '/edgek/ide/agent-sessions/create',
    workspace,
    patches,
  }) + '\n');
}

main().catch(error => {
  process.stderr.write(String(error && error.stack || error) + '\n');
  process.exit(1);
});
