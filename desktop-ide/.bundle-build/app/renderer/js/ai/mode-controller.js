// BEAST Pair Programmer renderer module: mode-controller.js
(() => {
  const registry = window.BeastAICodingModules = window.BeastAICodingModules || {};
  registry.createModeController = runtime => {
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
  const cancel = (...args) => api.cancel(...args);
  const patch = (...args) => api.patch(...args);
  const persist = (...args) => api.persist(...args);

  async function setMode(mode) {
    const next = ['ask','edit','agent','review'].includes(mode) ? mode : 'agent';
    const current = BeastStore.get().aiCoding;
    if (next === current.mode) return;
    const runId = window.BeastOperationsConsole?.activeRunId?.() || '';
    try {
      if (runId) {
        const conversionConfirmed = current.mode === 'review' && next === 'agent'
          ? await governedModeConfirmation('Review findings must become a new governed Agent run before mutation. Convert now?')
          : false;
        if (current.mode === 'review' && next === 'agent' && !conversionConfirmed) return;
        await window.BeastOperationsConsole.transitionMode(next, {
          runId,
          conversionConfirmed,
          reason:`Operator changed Pair Programmer mode from ${current.mode || 'unknown'} to ${next}`
        });
      }
      cancel();
      patch({ mode:next, status:'idle', error:'', sourcePlanReady:false, sourcePlanId:'', selection:null });
      persist();
    } catch (error) {
      patch({ status:'error', error:`Mode transition denied: ${String(error.message || error)}` });
    }
  }

  function governedModeConfirmation(message) {
    return new Promise(resolve => {
      const prior = document.querySelector('[data-beast-mode-dialog]');
      if (prior) prior.remove();
      const dialog = document.createElement('section');
      dialog.className = 'cortex-workspace-dialog confirm';
      dialog.dataset.beastModeDialog = 'true';
      dialog.setAttribute('role','alertdialog');
      dialog.setAttribute('aria-modal','true');
      dialog.innerHTML = `<form><header><b>Convert Review to Agent?</b><small>${String(message).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c])}</small></header><footer><button type="button" data-mode-cancel>Cancel</button><button type="submit">Create governed Agent run</button></footer></form>`;
      document.body.append(dialog);
      const close = value => { dialog.remove(); resolve(Boolean(value)); };
      dialog.querySelector('[data-mode-cancel]').addEventListener('click', () => close(false));
      dialog.querySelector('form').addEventListener('submit', event => { event.preventDefault(); close(true); });
      requestAnimationFrame(() => dialog.querySelector('[data-mode-cancel]')?.focus());
    });
  }

  function resolvedModeForPrompt(mode,prompt) {
    // The mode picker is an explicit user contract.  Previous heuristic
    // routing silently changed Edit/Agent to Ask for prompts starting with
    // words such as "review" or "explain", so a selected editing mode could
    // never produce a SourcePlan.  Keep the selection intact; Ask remains the
    // only intentionally conversational mode.
    return ['ask','edit','agent','review'].includes(mode) ? mode : 'agent';
  }

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
      : mode === 'review' ? 'review'
      : analysisRun ? 'analysis'
      : wantsTests ? 'test-focused implementation'
      : wantsDebug ? 'debug implementation'
      : wantsRefactor ? 'refactor implementation'
      : 'implementation';
    const mutating = !['ask','review'].includes(mode) && !analysisRun;
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

  function initialAgentTurns(profile, files = []) {
    const turns = [
      { id:`turn-${now()}-context`, kind:'context', type:'context_read', role:'tool', tool:'Workspace File Read', text:`Context gathered · ${files.length} file${files.length === 1 ? '' : 's'} in scope`, state:'done', authority:'selected files only', at:now() },
      { id:`turn-${now()}-loop`, kind:'agent_loop', type:'agent_reasoning', role:'agent', text:`Operating mode: ${profile.kind}; loop: ${profile.loop.join(' → ')}`, state:'active', authority:profile.mutating ? 'SourcePlan required before writes' : 'read-only analysis', at:now() },
      { id:`turn-${now()}-cortex`, kind:'repository_observation', type:'tool_call', role:'tool', tool:'Code Cortex', text:'Inspect selected files, symbols, imports, and direct dependents before answering.', state:'active', authority:'read-only/governed', at:now() }
    ];
    if (profile.wantsMultiFile) turns.push({ id:`turn-${now()}-search`, kind:'workspace_search', type:'tool_call', role:'tool', tool:'Workspace Search', text:'Search symbols and references to avoid one-file tunnel vision.', state:'active', authority:'operator-approved read-only expansion when needed', at:now() });
    if (profile.wantsTests) turns.push({ id:`turn-${now()}-verify-request`, kind:'command', type:'command_request', role:'command', tool:'BEAST isolated verifier', command:'discover and run focused workspace checks', text:'I will request declared tests or verifier commands once the target surface is clear.', state:'active', authority:'operator approval required; isolated temporary workspace', at:now() });
    return turns;
  }

  function initialAgentProgress(profile, files = []) {
    return [
      { phase:'context', label:'Read selected context', detail:`${files.length} file${files.length === 1 ? '' : 's'} in scope`, state:'done', at:now() },
      { phase:'observe', label:'Inspect repository surface', detail:profile.wantsMultiFile ? 'Code Cortex + reference search' : 'Code Cortex selected-file map', state:'active', at:now() },
      { phase:'skills', label:'Skill/recipe check', detail:'Use verified BEAST recipes when relevant', state:'idle', at:now() },
      { phase:'draft', label:profile.mutating ? 'Prepare governed edit plan' : 'Prepare read-only answer', detail:profile.kind, state:'idle', at:now() },
      { phase:'verify', label:'Verification loop', detail:profile.wantsTests || profile.mutating ? 'Approval-gated isolated checks' : 'Suggested follow-up checks', state:'idle', at:now() }
    ];
  }

  function instructionFor(mode, prompt, files, selection, compactLocal = false) {
    const scope = files.length ? files.map(path => `- ${path}`).join('\n') : '- no files attached';
    const selected = selection?.text
      ? `\n\nSelected code in ${selection.path} (${JSON.stringify(selection.range || {})}):\n---\n${selection.text}\n---`
      : '';
    if (mode === 'ask') return `Act as my coding partner. Answer from the attached repository context, cite relevant files, and identify uncertainty.\n\nQuestion: ${prompt}\n\nAttached workspace scope:\n${scope}${selected}`;
    if (mode === 'agent' && isAgentAnalysisPrompt(prompt)) return `Act as my agentic coding partner in first person. Inspect the attached repository context before answering. Use the available governed repository tools conceptually as evidence: read the active file, map important symbols/dependencies, call out uncertainty, and ask for more context if needed. This is an analysis turn, not an edit request: do not propose a patch, do not return Action IR, and do not claim files changed. Give a deep, context-aware analysis with concrete references to the attached files and likely follow-up checks.\n\nQuestion: ${prompt}\n\nAttached workspace scope:\n${scope}${selected}`;
    const actionRules = `\n\nReturn BEAST Action IR JSON only after inspecting the attached files. Use this exact shape:\n{"kind":"beast.action_intent.v1","objective":"...","actions":[{"type":"replace_exact","target":{"path":"relative/file","anchor_ref":"A1"},"old":"exact current snippet","new":"replacement","intent":"why"},{"type":"run_verifier","intent":"run focused checks","parameters":{"command":"python -m pytest relevant/test.py -q"}}],"verify":["relevant test or check"]}\nUse only attached files and copy old snippets exactly from the current file. If the prompt includes selected code, prefer replacing that exact complete selected range: set old to the selected text verbatim and new to the full replacement for that same range. If BEAST supplies or implies anchor_ref values, use the matching target.anchor_ref and make new replace the complete anchor. Every source-edit action must make a real, complete source change: never emit an unchanged old/new pair, an ellipsis, placeholders, or prose such as "rest of the function remains the same." You may include non-mutating run_verifier or ask_for_context actions for the next governed loop; they cannot edit files and require approval. Never satisfy an implementation request with a cosmetic comment, a signature-only change, or the first plausible one-line tweak. Emit at most one source-edit action per file: when a file needs several changes, make one complete anchor replacement containing all of them. Trace the requested behavior through every attached implementation, caller, configuration, and test surface; emit all edits that are genuinely required. A one-hunk plan is valid only when the attached scope proves the behavior is truly isolated. ${compactLocal ? 'For the local Qwen route, emit at most three replace_exact actions and only lightweight syntax checks. ' : 'Keep scope controlled, but make the implementation complete. If multiple files are attached because the feature crosses UI, runtime, tests, and docs, produce a coordinated multi-file patch rather than a tiny isolated edit. '}Do not include markdown or prose outside the JSON.`;
    if (mode === 'edit') return `${prompt}\n\nEdit scope:\n${scope}${selected}${actionRules}`;
    return `Act as BEAST's autonomous implementation agent. Investigate with the available governed repository tools before deciding on edits: search symbols and references, read the attached files, inspect Code Cortex relationships, and use relevant verified BEAST skill recipes when available. Follow the resulting evidence through callers, configuration, and tests. Then return the complete reviewable Action IR needed to implement this task. BEAST will run only allowlisted verification in a temporary isolated workspace; it will ask for approval before any expanded file reads, skill use, or command execution.\n\nTask: ${prompt}\n\nInitial workspace scope:\n${scope}${selected}${actionRules}`;
  }

    return { setMode, resolvedModeForPrompt, isAgentAnalysisPrompt, agentTurnProfile, initialAgentTurns, initialAgentProgress, instructionFor };
  };
})();
