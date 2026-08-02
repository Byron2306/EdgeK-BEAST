// BEAST Pair Programmer renderer module: verification-view.js
(() => {
  const registry = window.BeastAICodingModules = window.BeastAICodingModules || {};
  registry.createVerificationView = runtime => {
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
  const appendTrace = (...args) => api.appendTrace(...args);
  const patch = (...args) => api.patch(...args);
  const persist = (...args) => api.persist(...args);
  const proposalFromActions = (...args) => api.proposalFromActions(...args);
  const proposalSummary = (...args) => api.proposalSummary(...args);

  async function verifyRequestedChecks() {
    const state = BeastStore.get();
    const plan = state.sourcePlan?.plan;
    if (!plan?.operations?.length) throw new Error('No AI SourcePlan is ready to verify.');
    const planId = String(plan.plan_id || state.aiCoding.sourcePlanId || '');
    patch({ status:'verifying-agent-checks', error:'' });
    appendTrace('tests', 'Running agent-requested checks in an isolated temporary workspace');
    const requestedCommands = [
      ...((plan.action_ir?.verify || []).map(command => String(command || '').trim()).filter(Boolean)),
      ...((plan.non_mutating_requests || []).map(item => {
        const parameters = item && typeof item.parameters === 'object' ? item.parameters : {};
        return String(parameters.command || item?.command || '').trim();
      }).filter(Boolean))
    ].slice(0,6);
    const queuedCommands = requestedCommands.length ? requestedCommands : ['BEAST isolated verifier suite'];
    const beforeMessages = BeastStore.get().aiCoding.messages.map(message => {
      if (message.role !== 'assistant' || !message.proposal) return message;
      const samePlan = planId && String(message.proposal.planId || '') === planId;
      if (!samePlan && message !== [...BeastStore.get().aiCoding.messages].reverse().find(item => item.role === 'assistant' && item.proposal)) return message;
      const turns = Array.isArray(message.turns) ? message.turns : [];
      const commandTurns = queuedCommands.map(command => ({
        id:`turn-${now()}-${Math.random()}`,
        kind:'command',
        type:'command_call',
        role:'command',
        text:'Operator approved; running in an isolated temporary workspace.',
        state:'active',
        command,
        tool:'BEAST isolated verifier',
        authority:'isolated temporary workspace',
        evidence:'',
        at:now()
      }));
      return {
        ...message,
        activity:'Running isolated checks',
        turns:[...turns, { id:`turn-${now()}-${Math.random()}`, kind:'permission', type:'permission_request', role:'operator', text:'Operator approved isolated verifier checks.', state:'done', authority:'operator approved isolated verifier', evidence:'', at:now() }, ...commandTurns].slice(-80)
      };
    });
    patch({ messages:beforeMessages });
    const result = await BeastRuntime.request('/edgek/ide/agent-sessions/verify-sourceplan', {
      method:'POST', timeoutMs:90000,
      body:{ root_path:root(), session_id:state.aiCoding.sessionId, plan }
    });
    const verifiedPlan = result?.plan && typeof result.plan === 'object' ? result.plan : { ...plan, validation:result?.validation || plan.validation || {} };
    const validation = verifiedPlan.validation || result?.validation || {};
    const proposal = proposalFromActions(verifiedPlan.operations || [], true, verifiedPlan.plan_id || planId, validation, verifiedPlan.intelligence || {}, verifiedPlan.non_mutating_requests || []);
    BeastStore.patch('sourcePlan', {
      plan:verifiedPlan, lifecycle:null,
      status:validation.ok ? 'verified' : 'verification-failed',
      message:`Agent requested checks ${validation.status || 'completed'} · ${Number(validation.check_count || 0)} checks`,
      error:validation.ok ? '' : (validation.failures || []).slice(0,3).join(' · '),
      updatedAt:now()
    });
    const messages = BeastStore.get().aiCoding.messages.map(message => {
      if (message.role !== 'assistant' || !message.proposal) return message;
      const samePlan = planId && String(message.proposal.planId || '') === planId;
      if (!samePlan && message !== [...BeastStore.get().aiCoding.messages].reverse().find(item => item.role === 'assistant' && item.proposal)) return message;
      const turns = Array.isArray(message.turns) ? message.turns : [];
      const commandTurns = (Array.isArray(validation.isolated_verifiers?.commands) ? validation.isolated_verifiers.commands : []).slice(0,6).map(item => ({
        id:`turn-${now()}-${Math.random()}`,
        kind:'command',
        type:'command_result',
        role:'command',
        text:String(item.message || item.status || 'verifier completed').slice(0,500),
        state:String(item.status || (validation.ok ? 'done' : 'failed')),
        command:String(item.command || 'verifier'),
        tool:'BEAST isolated verifier',
        authority:'isolated temporary workspace',
        evidence:String(result?.evidence_receipt?.receipt_id || ''),
        at:now()
      }));
      return {
        ...message,
        content:proposalSummary(proposal, verifiedPlan.objective),
        proposal,
        turns:[...turns, { id:`turn-${now()}-${Math.random()}`, kind:'validation', type:'verification', role:'verifier', text:`Agent requested checks ${validation.status || 'completed'} · ${Number(validation.check_count || 0)} checks`, state:validation.ok?'done':'failed', authority:'operator approved isolated verifier', evidence:String(result?.evidence_receipt?.receipt_id || ''), at:now() }, ...commandTurns].slice(-80)
      };
    });
    patch({ messages, status:validation.ok?'agent-checks-passed':'agent-checks-failed' });
    appendTrace('tests', `Agent requested checks ${validation.status || 'completed'} · ${(validation.isolated_verifiers || {}).passed || 0} passed · ${(validation.isolated_verifiers || {}).failed || 0} failed`);
    persist();
    return result;
  }

    return { verifyRequestedChecks };
  };
})();
