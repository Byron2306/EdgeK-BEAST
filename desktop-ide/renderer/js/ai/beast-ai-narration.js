(() => {
  'use strict';

  function runDoneSentence(status = '', { needsOperator = false, proposalReady = false, advisoryReceived = false, analysisRun = false } = {}) {
    const raw = String(status || '').replaceAll('_', ' ').trim();
    if (proposalReady) return 'Run complete: I prepared a governed SourcePlan for review.';
    if (needsOperator) return 'Recovery is waiting for your review. No files changed.';
    if (analysisRun || /chat complete|analysis/i.test(raw)) return 'Run complete: I finished the read-only analysis.';
    if (advisoryReceived) return 'Run complete: I returned a read-only answer and made no file changes.';
    if (/advisory response/i.test(raw)) return 'Run complete: no SourcePlan was created and no files changed.';
    return raw ? `Run complete: ${raw}.` : 'Run complete.';
  }

  function narrationFromTurn(payload = {}) {
    const text = String(payload.text || payload.detail || '').replace(/\s+/g, ' ').trim();
    const command = String(payload.command || '').trim();
    const type = String(payload.type || payload.kind || '');
    const tool = String(payload.tool || '').trim();
    const lower = `${tool} ${text}`.toLowerCase();
    if (type === 'context_read') return payload.state === 'failed'
      ? `I couldn’t read the requested context: ${text}`
      : 'I read the selected workspace context and locked it to this run.';
    if (type === 'tool_call') {
      if (lower.includes('code cortex')) return 'I’m inspecting the selected code and nearby dependencies now.';
      if (lower.includes('workspace search')) return 'I’m searching the workspace for the symbols and references that matter.';
      if (lower.includes('related file')) return 'I’m reading the approved related files so the next step is grounded.';
      if (lower.includes('verified skill')) return 'I’m checking the verified BEAST recipes that apply to this task.';
      if (lower.includes('semantic raid')) return 'I’m saving the exact context packet as local evidence for this run.';
      if (lower.includes('provider handoff')) return 'I’m handing the scoped context to the selected model now.';
      return text ? `I’m using ${tool || 'a governed BEAST tool'}: ${text}` : `I’m using ${tool || 'a governed BEAST tool'} now.`;
    }
    if (type === 'tool_result') {
      if (lower.includes('code cortex')) return 'I mapped the selected code, symbols, and direct dependents.';
      if (lower.includes('workspace search')) return 'I found the relevant workspace symbols and editing context.';
      if (lower.includes('related file')) return 'I added the approved related files to this turn.';
      if (lower.includes('verified skill')) return text.includes('no matching') ? 'I checked the skill library; no matching verified recipe was available.' : 'I selected the matching verified BEAST recipe guidance.';
      if (lower.includes('semantic raid')) return lower.includes('deferred') ? 'I couldn’t mirror the context packet, so I’m continuing without that evidence cache.' : 'I saved the exact context packet as local evidence.';
      if (lower.includes('provider handoff')) return 'My governed input is ready and bounded to the selected files.';
      if (lower.includes('insight compile')) return 'I checked prior repo evidence for anything useful to this turn.';
      if (lower.includes('handoff precheck')) return 'I verified my handoff is ready.';
      if (lower.includes('crystal record')) return 'I recorded the useful parts of this run for future reuse.';
      if (lower.includes('crystal reuse')) return 'I checked whether a prior successful run could be safely reused here.';
      return text || `I finished using ${tool || 'a governed BEAST tool'}.`;
    }
    if (type === 'agent_reasoning') {
      if (lower.includes('provider stream')) return 'I’m streaming my response now.';
      if (lower.includes('action ir recovery')) return 'I’m trying to recover a reviewable edit plan from my draft.';
      if (lower.includes('implementation planning')) return 'I’m planning the implementation against the selected files.';
      if (lower.includes('repository observation')) return 'I’m inspecting the repository context first.';
      if (lower.includes('operating mode:')) return text;
      return text ? `I’m working through ${text.charAt(0).toLowerCase()}${text.slice(1)}.` : '';
    }
    if (type === 'permission_request') return payload.state === 'failed'
      ? 'I paused because the extra capability request was declined.'
      : 'You approved the extra governed capability, so I’m continuing with that boundary.';
    if (type === 'model_output') return 'I finished drafting; now I’m checking whether it can become a reviewable SourcePlan.';
    if (type === 'verification') return text ? `I checked the proposed changes: ${text}` : '';
    if (type === 'context_request') return `I need a little more context before the next pass: ${text}`;
    if (type === 'context_search') return `I’m searching for the extra context the agent asked for: ${text}`;
    if (type === 'context_result') return payload.state === 'failed'
      ? `I couldn’t find matching context: ${text}`
      : `I found context candidates for review: ${text}`;
    if (type === 'context_attach') return `I added this file to the next run’s context: ${text}`;
    if (type === 'context_continue') return 'I’m continuing the same task with the expanded context.';
    if (type === 'recovery_request') return text || 'I need to repair the edit packet before it can become a SourcePlan.';
    if (type === 'command_request') return `I’m ready to run an isolated check if you approve it: ${command || text}`;
    if (type === 'command_call') return `I’m running an isolated check now: ${command || text}`;
    if (type === 'command_result') return `The isolated check ${payload.state === 'failed' ? 'failed' : 'finished'}: ${command || text}`;
    if (type === 'sourceplan') return 'I prepared a governed SourcePlan for review.';
    if (type === 'agent_turn') return 'I started the coding run with the selected workspace scope.';
    if (type === 'model_connection') return 'I connected to the selected model and started the run.';
    return text;
  }

  window.BeastAINarration = Object.freeze({ runDoneSentence, narrationFromTurn });
})();
