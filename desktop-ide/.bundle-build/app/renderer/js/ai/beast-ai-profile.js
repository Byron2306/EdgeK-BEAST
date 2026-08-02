(() => {
  'use strict';

  function isAgentAnalysisPrompt(prompt = '') {
    const text = String(prompt || '').toLowerCase();
    const asksForPatch = /\b(fix|change|modify|update|implement|add|remove|replace|refactor|write|patch|edit|make it|create)\b/.test(text);
    const asksForAnalysis = /\b(look over|review|analy[sz]e|analysis|deep dive|inspect|explain|understand|summari[sz]e|walk through|what does|how does|find risks|identify issues|audit)\b/.test(text);
    return asksForAnalysis && !asksForPatch;
  }

  function agentTurnProfile(prompt = '', mode = 'agent', analysisRun = false, files = []) {
    const text = String(prompt || '').toLowerCase();
    const wantsTests = /\b(test|tests|pytest|jest|vitest|lint|typecheck|verify|check|run)\b/.test(text);
    const wantsDebug = /\b(debug|bug|broken|error|failure|trace|why is|root cause)\b/.test(text);
    const wantsRefactor = /\b(refactor|cleanup|clarity|simplify|rename|reorganize)\b/.test(text);
    const wantsMultiFile = files.length > 1 || /\b(across|multi[- ]file|callers|dependencies|routes|tests|frontend|backend)\b/.test(text);
    const kind = mode === 'ask' ? 'answer'
      : analysisRun ? 'analysis'
      : wantsTests ? 'test-focused implementation'
      : wantsDebug ? 'debug implementation'
      : wantsRefactor ? 'refactor implementation'
      : 'implementation';
    const mutating = mode !== 'ask' && !analysisRun;
    const loop = [
      'read selected files',
      wantsMultiFile ? 'map cross-file dependencies' : 'map local dependencies',
      'search symbols/references when approved',
      'use verified BEAST recipes when relevant',
      mutating ? 'draft governed SourcePlan' : 'return first-person analysis',
      wantsTests || mutating ? 'request isolated checks/tests' : 'name likely follow-up checks'
    ];
    return { kind, mutating, wantsTests, wantsDebug, wantsRefactor, wantsMultiFile, loop };
  }

  function initialAgentTurns(profile, files = [], now = () => Date.now()) {
    const turns = [
      { id:`turn-${now()}-context`, kind:'context', type:'context_read', role:'tool', tool:'Workspace File Read', text:`Context gathered · ${files.length} file${files.length === 1 ? '' : 's'} in scope`, state:'done', authority:'selected files only', at:now() },
      { id:`turn-${now()}-loop`, kind:'agent_loop', type:'agent_reasoning', role:'agent', text:`Operating mode: ${profile.kind}; loop: ${profile.loop.join(' → ')}`, state:'active', authority:profile.mutating ? 'SourcePlan required before writes' : 'read-only analysis', at:now() },
      { id:`turn-${now()}-cortex`, kind:'repository_observation', type:'tool_call', role:'tool', tool:'Code Cortex', text:'Inspect selected files, symbols, imports, and direct dependents before answering.', state:'active', authority:'read-only/governed', at:now() }
    ];
    if (profile.wantsMultiFile) turns.push({ id:`turn-${now()}-search`, kind:'workspace_search', type:'tool_call', role:'tool', tool:'Workspace Search', text:'Search symbols and references to avoid one-file tunnel vision.', state:'active', authority:'operator-approved read-only expansion when needed', at:now() });
    if (profile.wantsTests) turns.push({ id:`turn-${now()}-verify-request`, kind:'command', type:'command_request', role:'command', tool:'BEAST isolated verifier', command:'discover and run focused workspace checks', text:'I will request declared tests or verifier commands once the target surface is clear.', state:'active', authority:'operator approval required; isolated temporary workspace', at:now() });
    return turns;
  }

  function initialAgentProgress(profile, files = [], now = () => Date.now()) {
    return [
      { phase:'context', label:'Read selected context', detail:`${files.length} file${files.length === 1 ? '' : 's'} in scope`, state:'done', at:now() },
      { phase:'observe', label:'Inspect repository surface', detail:profile.wantsMultiFile ? 'Code Cortex + reference search' : 'Code Cortex selected-file map', state:'active', at:now() },
      { phase:'skills', label:'Skill/recipe check', detail:'Use verified BEAST recipes when relevant', state:'idle', at:now() },
      { phase:'draft', label:profile.mutating ? 'Prepare governed edit plan' : 'Prepare read-only answer', detail:profile.kind, state:'idle', at:now() },
      { phase:'verify', label:'Verification loop', detail:profile.wantsTests || profile.mutating ? 'Approval-gated isolated checks' : 'Suggested follow-up checks', state:'idle', at:now() }
    ];
  }

  window.BeastAIProfile = Object.freeze({
    isAgentAnalysisPrompt,
    agentTurnProfile,
    initialAgentTurns,
    initialAgentProgress,
  });
})();
