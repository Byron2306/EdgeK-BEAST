// BEAST Pair Programmer renderer module: approval-cards.js
(() => {
  const registry = window.BeastAICodingModules = window.BeastAICodingModules || {};
  registry.createApprovalCards = runtime => {
  const api = runtime.api;
  const root = runtime.root;
  const gatewayUrl = runtime.gatewayUrl;
  const stateKey = runtime.stateKey;
  const now = runtime.now;
  const openRunStream = runtime.openRunStream;
  const parseActionIntent = runtime.parseActionIntent;
  const looksLikeActionIntent = runtime.looksLikeActionIntent;
  const MAX_CONTEXT_FILES = runtime.constants.MAX_CONTEXT_FILES;
  const RELIABLE_LOCAL_CODER = runtime.constants.RELIABLE_LOCAL_CODER;
  const RELIABLE_LOCAL_PROFILE = runtime.constants.RELIABLE_LOCAL_PROFILE;
  async function handlePermissionRequest({ event, assistantId, eventSource }) {
    if (runtime.streamState.stream !== eventSource) return false;
    api.armWatchdog(assistantId, eventSource);
    const payload = api.eventPayload(event);
    const capabilities = Array.isArray(payload.capabilities) ? payload.capabilities : [];
    const labels = capabilities.map(item => `• ${item.label || item.id}: ${item.scope || 'read-only'}`).join('\n');
    const approved = window.confirm(`BEAST requests governed capabilities for this agent run:\n\n${labels}\n\nSource writes always remain a separate SourcePlan approval. Test commands, if requested, run only in an isolated temporary workspace. Approve?`);
    if (!approved) {
      api.appendTrace('permission', 'Agent capability request declined');
      api.appendTurn(assistantId, { type:'permission_request', kind:'permission', text:'Capability request declined', state:'failed', authority:'operator declined' });
      return false;
    }
    const paths = capabilities.flatMap(item => Array.isArray(item.paths) ? item.paths : []);
    try {
      await BeastRuntime.request('/edgek/ide/agent-sessions/capabilities/grant', {
        method:'POST', timeoutMs:10000,
        body:{
          root_path:runtime.root(), session_id:payload.session_id, request_id:payload.request_id,
          capabilities:capabilities.map(item => item.id), paths
        }
      });
      api.appendTrace('permission', `Approved ${capabilities.length} governed capability request(s); BEAST will use them before provider dispatch when the grant arrives in time.`);
      api.appendTurn(assistantId, { type:'permission_request', kind:'permission', text:`Approved ${capabilities.length} governed capability request(s)`, state:'done', authority:'operator approved' });
      return true;
    } catch (error) {
      api.appendTrace('permission', `Capability approval could not be saved: ${String(error.message || error)}`);
      return false;
    }
  }

    return { handlePermissionRequest };
  };
})();
