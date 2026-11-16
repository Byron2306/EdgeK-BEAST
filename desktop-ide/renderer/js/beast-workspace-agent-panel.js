(() => {
  const page = window.BeastWorkspacePage;
  if (!page || typeof page.renderer !== 'function') throw new Error('Workspace page must load before its Agent Coder panel.');

  const renderWorkspace = page.renderer;
  let restored = false;
  let aiScrollFrame = 0;

  function scheduleAiScroll(host) {
    cancelAnimationFrame(aiScrollFrame);
    aiScrollFrame = requestAnimationFrame(() => {
      aiScrollFrame = 0;
      if (host.isConnected) host.scrollTop = host.scrollHeight;
    });
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' })[char]);
  }

  function createPanel() {
    const panel = document.createElement('aside');
    panel.className = 'beast-card cortex-agent-panel hidden';
    panel.setAttribute('aria-label', 'Agent Coder');
    panel.innerHTML = `
      <header class="cortex-agent-head">
        <div><span>BEAST PAIR PROGRAMMER</span><strong>Agent Coder</strong></div>
        <label class="cortex-agent-model">Model
          <select data-ai-model aria-label="Agent Coder model"></select>
        </label>
        <button type="button" class="beast-button secondary" data-ai-expand aria-label="Toggle Pair Programmer focus mode">Focus</button>
        <button type="button" class="beast-button secondary" data-ai-action="close" aria-label="Close Agent Coder">×</button>
      </header>
      <details class="cortex-ai-context" open>
        <summary>Explicit context · files attached only by you</summary>
        <div class="cortex-ai-context-body">
          <div><span>EXPLICIT CONTEXT</span><button type="button" data-ai-action="attach">Attach active file</button></div>
          <div class="cortex-agent-context-list" data-ai-context-list></div>
          <div class="cortex-agent-suggestions" data-ai-suggestions></div>
        </div>
      </details>
      <p class="cortex-ai-mode-description" data-ai-mode-description></p>
      <div class="cortex-ai-compose-actions" aria-label="Quick mode selection">
        <button type="button" data-ai-suggestion-mode="ask">Ask</button>
        <button type="button" data-ai-suggestion-mode="edit">Edit</button>
        <button type="button" data-ai-suggestion-mode="agent">Agent</button>
      </div>
      <section class="cortex-ai-cockpit" aria-label="Agent route and verification status">
        <span>Route, repair, tests, and plan state</span>
        <div><b>Execution target</b><em data-ai-execution-target>Local</em></div>
        <div><b>Verifier strategy</b><em data-ai-verifier-strategy>BEAST isolated verifier</em></div>
        <div><b>Prior verifier failure</b><em data-ai-prior-failure>None reported</em></div>
      </section>
      <div class="cortex-agent-approval-host" data-ai-approval-host role="region" aria-label="Pending agent tool authorization" hidden></div>
      <div class="cortex-agent-messages" data-ai-messages role="log" aria-live="polite" aria-relevant="additions text"></div>
      <div class="cortex-agent-status" data-ai-status role="status" aria-live="polite"></div>
      <label class="cortex-agent-mode">MODE
        <select data-ai-mode>
          <option value="agent">Agent · governed edits</option>
          <option value="edit">Edit · SourcePlan</option>
          <option value="ask">Ask · read only</option>
          <option value="review">Review · read only</option>
        </select>
      </label>
      <textarea data-ai-prompt rows="4" placeholder="Describe what you want the agent to do…" aria-label="Agent Coder prompt"></textarea>
      <footer class="cortex-agent-actions">
        <button type="button" class="beast-button secondary" data-ai-action="suggest">Suggest context</button>
        <button type="button" class="beast-button secondary" data-ai-action="retry">Retry with locked context</button>
        <button type="button" class="beast-button secondary" data-ai-action="clear">New chat</button>
        <button type="button" class="beast-button secondary hidden" data-ai-action="cancel">Stop</button>
        <button type="button" class="beast-button secondary" data-ai-action="worktree-agent" title="Create an isolated Git worktree, then run the coding agent there">Isolate</button>
        <button type="button" class="beast-button hot" data-ai-action="send" data-ai-send-label="Run agent">Run agent</button>
      </footer>`;
    return panel;
  }

  function renderMessages(host, state) {
    const messages = (state.messages || []).slice(-24);
    const signature = messages.map(message => `${message.id}:${String(message.content || '').length}:${String(message.content || '').slice(-64)}:${message.streaming ? 1 : 0}:${message.turns?.length || 0}:${String(message.turns?.at(-1)?.text || '').slice(-32)}:${message.proposal?.planId || ''}:${message.proposal?.validation?.status || ''}:${message.draftPreview?.chars || 0}:${message.memoryEvidence?.event_id || ''}`).join('|');
    if (host.dataset.signature === signature) return;
    const wasNearBottom = host.scrollHeight - host.scrollTop - host.clientHeight < 64;
    const fragment = document.createDocumentFragment();

    if (!messages.length) {
      const empty = document.createElement('p');
      empty.className = 'cortex-agent-empty';
      empty.textContent = 'Choose a mode, attach only the files you want in scope, then describe the task.';
      fragment.append(empty);
    }

    for (const message of messages) {
      const article = document.createElement('article');
      article.className = `cortex-agent-message ${message.role === 'user' ? 'operator' : 'agent'}`;
      const heading = document.createElement('strong');
      heading.textContent = message.role === 'user' ? 'YOU' : 'AGENT CODER';
      const aiMessageBody = document.createElement('pre');
      aiMessageBody.className = 'cortex-ai-message-body';
      aiMessageBody.textContent = String(message.content || (message.streaming ? 'Working…' : ''));
      article.append(heading, aiMessageBody);
      if (message.memoryEvidence) {
        const receipt = message.memoryEvidence;
        const memory = document.createElement('section');
        memory.className = 'cortex-ai-memory-evidence';
        const title = document.createElement('strong');
        title.textContent = 'L4 MEMORY · VERIFIED REASSESSMENT (ADVISORY)';
        const detail = document.createElement('p');
        detail.textContent = `Original verdict remains unchanged. Later review candidate verified; not promoted. Source event ${receipt.source_sequence} · ${receipt.event_id}`;
        const custody = document.createElement('p');
        custody.textContent = `Source hash: ${receipt.source_event_hash || 'unknown'} · metadata only`;
        memory.append(title, detail, custody);
        article.append(memory);
      }
      if (message.draftPreview) {
        const aiDraftPreview = document.createElement('section');
        aiDraftPreview.className = 'cortex-ai-live-draft';
        aiDraftPreview.innerHTML = '<strong>READ-ONLY AI HUNK PREVIEW</strong>';
        const previewText = document.createElement('p');
        previewText.textContent = `${Number(message.draftPreview.actions || 0)} proposed operations · ${(message.draftPreview.files || []).join(', ') || 'paths are still being identified'}`;
        aiDraftPreview.append(previewText);
        article.append(aiDraftPreview);
      }
      if (Array.isArray(message.turns) && message.turns.length) {
        const trace = document.createElement('details');
        trace.className = 'cortex-ai-trace';
        const summary = document.createElement('summary');
        summary.textContent = `Run details · ${message.turns.length} events`;
        const traceBody = document.createElement('div');
        message.turns.slice(-20).forEach(turn => {
          const row = document.createElement('p');
          row.textContent = `${turn.state || 'event'} · ${turn.kind || turn.type || 'activity'}${turn.text ? ` — ${turn.text}` : ''}${turn.command ? ` · ${turn.command}` : ''}`;
          traceBody.append(row);
        });
        trace.append(summary, traceBody);
        article.append(trace);
      }
      if (message.proposal) {
        const aiProposalCard = document.createElement('section');
        aiProposalCard.className = 'cortex-ai-proposal';
        const proposalHeading = document.createElement('strong');
        proposalHeading.textContent = message.proposal.ready ? 'READY TO REVIEW' : 'PROPOSAL NEEDS RECOVERY';
        proposalHeading.dataset.proposalState = message.proposal.ready ? 'ready-to-review' : 'validating-changes';
        const proposalSummary = document.createElement('p');
        const proposalOperations = Array.isArray(message.proposal.operations) ? message.proposal.operations : [];
        proposalSummary.textContent = `${proposalOperations.length} proposed changes · ${(message.proposal.files || []).length} files`;
        aiProposalCard.append(proposalHeading, proposalSummary);
        for (const operation of proposalOperations.slice(0, 8)) {
          const aiOperationPreview = document.createElement('details');
          aiOperationPreview.className = 'cortex-ai-edit-preview';
          aiOperationPreview.dataset.aiHunk = String(operation.path || '');
          const previewSummary = document.createElement('summary');
          previewSummary.textContent = `Inspect diff · ${operation.path || 'proposed change'}`;
          aiOperationPreview.append(previewSummary);
          const before = document.createElement('pre');
          before.textContent = `BEFORE\n${String(operation.old || '(no prior text)').slice(0, 2400)}`;
          const after = document.createElement('pre');
          after.textContent = `AFTER\n${String(operation.new || '(no proposed text)').slice(0, 2400)}`;
          aiOperationPreview.append(before, after);
          aiProposalCard.append(aiOperationPreview);
          const inspect = document.createElement('button');
          inspect.type = 'button';
          inspect.className = 'beast-button secondary';
          inspect.dataset.aiPreviewPath = String(operation.path || '');
          inspect.setAttribute('data-ai-preview-path', String(operation.path || ''));
          inspect.textContent = 'Inspect diff';
          aiProposalCard.append(inspect);
        }
        const validation = message.proposal.validation || {};
        const verifiers = validation.isolated_verifiers || {};
        const evidence = document.createElement('details');
        evidence.className = 'cortex-ai-validation cortex-ai-verifiers';
        const evidenceSummary = document.createElement('summary');
        evidenceSummary.textContent = 'Isolated verification · verifier evidence';
        const evidenceText = document.createElement('p');
        evidenceText.textContent = `${validation.status || 'not run'} · ${Number(verifiers.passed || 0)} passed · ${Number(verifiers.failed || 0)} failed${validation.evidence_receipt?.receipt_id ? ` · receipt ${validation.evidence_receipt.receipt_id}` : ''}`;
        evidence.append(evidenceSummary, evidenceText);
        const verifierCommands = Array.isArray(verifiers.commands) ? verifiers.commands : [];
        verifierCommands.slice(0, 6).forEach(command => {
          const row = document.createElement('p');
          row.textContent = `${command.status || 'pending'} · ${command.command || 'isolated verifier'}`;
          evidence.append(row);
        });
        aiProposalCard.append(evidence);
        if (message.proposal.planId) {
          const review = document.createElement('button');
          review.type = 'button';
          review.className = 'beast-button hot cortex-ai-review-apply';
          review.dataset.aiAction = 'sourceplan';
          review.dataset.planId = String(message.proposal.planId);
          review.textContent = 'Review & approve';
          aiProposalCard.append(review);
        }
        article.append(aiProposalCard);
      }
      fragment.append(article);
    }

    host.replaceChildren(fragment);
    host.dataset.signature = signature;
    if (wasNearBottom) scheduleAiScroll(host);
  }

  function renderPendingApproval(panel) {
    const host = panel.querySelector('[data-ai-approval-host]');
    if (!host) return;
    const record = panel.__r320PendingApproval;
    const approval = record?.approval;
    const request = approval?.request || {};
    const fingerprint = approval ? `${record.runId}:${approval.approval_id}:${approval.status}` : '';
    if (host.dataset.fingerprint === fingerprint) return;
    host.dataset.fingerprint = fingerprint;
    host.replaceChildren();
    host.hidden = !approval;
    if (!approval) return;
    const heading = document.createElement('strong');
    heading.textContent = 'AUTHORIZATION REQUIRED · BEAST AgentRun';
    const detail = document.createElement('p');
    const files = Array.isArray(request.affected_files) ? request.affected_files : [];
    detail.textContent = `${request.summary || request.tool_id || 'Governed tool'} · ${record.runId}`;
    const scope = document.createElement('pre');
    scope.textContent = JSON.stringify({
      workspace:record.root, tool:request.tool_id, risk:request.risk_class,
      execution_target:request.execution_target, affected_files:files,
      arguments:request.safe_arguments || {}, approval_id:approval.approval_id
    }, null, 2);
    scope.style.cssText = 'max-height:155px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere';
    host.append(heading, detail, scope);
    for (const [action, title] of [['approve','Approve this tool'],['reject','Reject']]) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = `beast-button ${action === 'approve' ? 'hot' : 'secondary'}`;
      button.dataset.aiAction = 'r320-approval';
      button.dataset.r320Decision = action;
      button.textContent = title;
      host.append(button);
    }
    const note = document.createElement('p');
    note.textContent = 'This approval authorizes only the displayed tool step. SourcePlan promotion requires separate review.';
    host.append(note);
    host.style.cssText = 'border:1px solid currentColor;border-radius:8px;padding:10px;max-height:290px;overflow:auto;flex-shrink:0';
  }

  function renderPanel(panel, state) {
    const ai = state.aiCoding || {};
    renderPendingApproval(panel);
    panel.classList.toggle('hidden', !ai.open);
    const layout = panel.closest('.cortex-layout');
    layout?.classList.toggle('agent-open', Boolean(ai.open));
    layout?.classList.toggle('ai-open', Boolean(ai.open));
    layout?.classList.toggle('ai-focus', Boolean(ai.open && ai.expanded));
    layout?.classList.toggle('beast-agent-compact', Boolean(ai.open && layout.clientWidth < 1080));
    const nextWorkload = ai.streaming ? 'interactive' : 'idle';
    window.BeastVisualRuntime?.setWorkload?.(nextWorkload);
    const prompt = panel.querySelector('[data-ai-prompt]');
    const restricted = window.BeastWorkspaceTrust?.isRestricted() ?? true;
    if (document.activeElement !== prompt && prompt.value !== String(ai.prompt || '')) prompt.value = String(ai.prompt || '');
    const mode = panel.querySelector('[data-ai-mode]');
    if (document.activeElement !== mode) mode.value = ['ask','edit','agent','review'].includes(ai.mode) ? ai.mode : 'agent';
    const modelSelect = panel.querySelector('[data-ai-model]');
    if (modelSelect && document.activeElement !== modelSelect) {
      window.BeastModelAgentBridge?.fillModelSelect?.(modelSelect, state);
      modelSelect.disabled = Boolean(ai.streaming || state.models?.loading);
    }
    const descriptions = {
      ask: 'Read-only answers. No file mutations or SourcePlan apply.',
      edit: 'Prepare a governed SourcePlan from explicit context for review.',
      agent: 'Plan and propose governed changes; approval is required before writes.',
      review: 'Read-only review of the selected files and current proposal.'
    };
    panel.querySelector('[data-ai-mode-description]').textContent = descriptions[ai.mode] || descriptions.agent;
    const expand = panel.querySelector('[data-ai-expand]');
    expand.textContent = ai.expanded ? 'Exit focus' : 'Focus';
    expand.setAttribute('aria-pressed', String(Boolean(ai.expanded)));
    const sendButton = panel.querySelector('[data-ai-action="send"]');
    const sendLabels = { ask: 'Ask', edit: 'Prepare edit', agent: 'Run agent', review: 'Review' };
    sendButton.dataset.aiSendLabel = sendLabels[ai.mode] || sendLabels.agent;
    sendButton.textContent = sendButton.dataset.aiSendLabel;
    sendButton.disabled = Boolean(restricted || ai.streaming || !String(ai.prompt || '').trim());
    panel.querySelector('[data-ai-action="worktree-agent"]').disabled = Boolean(restricted || ai.streaming);
    panel.querySelector('[data-ai-action="cancel"]').classList.toggle('hidden', !ai.streaming);
    panel.querySelector('[data-ai-action="retry"]').disabled = ai.streaming || !(ai.messages || []).some(message => message.role === 'user');
    panel.querySelector('[data-ai-action="attach"]').disabled = !state.editor.activePath;
    const aiProgress = ai.status || (ai.streaming ? 'Working…' : 'Ready');
    panel.querySelector('[data-ai-status]').textContent = ai.error
      || (window.BeastWorkspaceTrust?.isRestricted() ? 'Restricted workspace: trust this workspace to enable agent actions.' : String(aiProgress));
    const latestTurn = [...(ai.messages || [])].reverse().find(message => message.role === 'assistant')?.turns?.at(-1) || {};
    panel.querySelector('[data-ai-execution-target]').textContent = latestTurn.execution_target || latestTurn.target_execution || state.workspace.executionTarget?.label || state.workspace.executionTarget?.id || 'Local';
    panel.querySelector('[data-ai-verifier-strategy]').textContent = latestTurn.validation_strategy?.strategy || latestTurn.validation_strategy?.name || 'BEAST isolated verifier';
    panel.querySelector('[data-ai-prior-failure]').textContent = latestTurn.prior_failure?.summary || latestTurn.prior_failure?.message || ai.error || 'None reported';

    const contextHost = panel.querySelector('[data-ai-context-list]');
    const contextKey = (ai.contextFiles || []).join('|');
    if (contextHost.dataset.paths !== contextKey) {
      const contextFragment = document.createDocumentFragment();
      for (const path of ai.contextFiles || []) {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.dataset.aiContextPath = path;
        chip.title = `Remove ${path} from explicit context`;
        chip.textContent = `${path} ×`;
        contextFragment.append(chip);
      }
      if (!(ai.contextFiles || []).length) {
        const empty = document.createElement('span');
        empty.textContent = 'No files attached';
        contextFragment.append(empty);
      }
      contextHost.replaceChildren(contextFragment);
      contextHost.dataset.paths = contextKey;
    }

    const suggestionsHost = panel.querySelector('[data-ai-suggestions]');
    const suggestions = ai.contextSuggestions || [];
    const suggestionsKey = suggestions.map(item => `${item.path}:${item.reason}`).join('|');
    if (suggestionsHost.dataset.suggestions !== suggestionsKey) {
      const suggestionsFragment = document.createDocumentFragment();
      for (const suggestion of suggestions) {
        const button = document.createElement('button');
        button.type = 'button';
        button.dataset.aiSuggestedPath = suggestion.path;
        button.title = suggestion.reason;
        button.textContent = `+ ${suggestion.path}`;
        suggestionsFragment.append(button);
      }
      suggestionsHost.replaceChildren(suggestionsFragment);
      suggestionsHost.dataset.suggestions = suggestionsKey;
    }
    renderMessages(panel.querySelector('[data-ai-messages]'), ai);
  }

  page.renderer = async context => {
    const rendered = await renderWorkspace(context);
    const node = rendered?.node;
    const layout = node?.querySelector('.cortex-layout');
    if (!node || !layout) return rendered;

    const api = window.BeastAICoding;
    if (!api) throw new Error('Agent Coder modules were not initialized before the Workspace route.');
    if (!restored) {
      api.restore();
      restored = true;
    }

    const actions = node.querySelector('.beast-page-actions');
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'beast-button secondary';
    toggle.dataset.aiPanelToggle = '';
    toggle.textContent = 'Agent Coder';
    actions?.append(toggle);

    const panel = createPanel();
    layout.append(panel);
    layout.classList.add('has-agent-panel');
    panel.querySelector('[data-ai-model]')?.addEventListener('change', event => {
      try {
        window.BeastModelAgentBridge?.selectModel?.(event.target.value);
      } catch (error) {
        panel.querySelector('[data-ai-status]').textContent = String(error.message || error);
      }
    });

    // Respond to the real workbench width, including DevTools and side rails.
    const geometryObserver = typeof ResizeObserver === 'function'
      ? new ResizeObserver(() => {
          layout.classList.toggle('beast-agent-compact',
            Boolean(BeastStore.get().aiCoding?.open && layout.clientWidth < 1080));
        })
      : null;
    geometryObserver?.observe(layout);

    let disposed = false;
    let renderQueued = false;
    const scheduleRender = state => {
      if (disposed || renderQueued) return;
      renderQueued = true;
      requestAnimationFrame(() => {
        renderQueued = false;
        if (!disposed) renderPanel(panel, state || BeastStore.get());
      });
    };
    const unsubscribe = BeastStore.subscribe(scheduleRender);
    const onTrustChange = () => scheduleRender();
    window.addEventListener('beast-workspace-trust-changed', onTrustChange);
    scheduleRender(BeastStore.get());
    let approvalPolling = false;
    let approvalRunId = '';
    async function syncRunApproval() {
      if (disposed || approvalPolling) return;
      const ai = BeastStore.get().aiCoding || {};
      const runId = String(ai.activeRunId || '').trim();
      const workspace = String(BeastStore.get().workspace?.root || '').trim();
      if (!runId || !workspace || !ai.streaming) {
        if (panel.__r320PendingApproval) {
          panel.__r320PendingApproval = null;
          renderPendingApproval(panel);
        }
        return;
      }
      approvalPolling = true;
      try {
        const result = await BeastRuntime.request(
          `/edgek/agent-runs/${encodeURIComponent(runId)}/approvals?root_path=${encodeURIComponent(workspace)}`,
          { timeoutMs:8000, cacheTtl:0 });
        if (disposed || String(BeastStore.get().aiCoding?.activeRunId || '') !== runId) return;
        const pending = (Array.isArray(result?.approvals) ? result.approvals : []).find(item =>
          ['pending','waiting_for_approval','requested'].includes(String(item.status || '').toLowerCase()));
        const old = panel.__r320PendingApproval;
        if (pending) {
          panel.__r320PendingApproval = { approval:pending, runId, root:workspace };
          window.BeastAICoding?.holdApprovalWatchdog?.();
          if (BeastStore.get().aiCoding?.status !== 'waiting-for-approval') {
            BeastStore.patch('aiCoding', {status:'waiting-for-approval',error:''});
          }
        } else {
          panel.__r320PendingApproval = null;
          if (old) window.BeastAICoding?.resumeApprovalWatchdog?.();
        }
        renderPendingApproval(panel);
      } catch (error) {
        // Never infer approval absence from a failed lookup; preserve the card.
        if (panel.__r320PendingApproval) {
          panel.__r320PendingApproval.lookupError = String(error.message || error);
        }
      } finally { approvalPolling = false; }
    }
    const approvalTimer = setInterval(() => { void syncRunApproval(); }, 2000);
    void syncRunApproval();


    async function run(action, target) {
      try {
        if (action === 'close') api.setOpen(false);
        else if (action === 'attach') api.addActiveFile();
        else if (action === 'suggest') await api.suggestContext(BeastStore.get().aiCoding.prompt);
        else if (action === 'retry') await api.retryLastRequest();
        else if (action === 'clear') api.clear();
        else if (action === 'cancel') api.cancel();
        else if (action === 'send') await api.send(BeastStore.get().aiCoding.prompt);
        else if (action === 'worktree-agent') await api.runInWorktree(BeastStore.get().aiCoding.prompt);
        else if (action === 'sourceplan') await api.openSourcePlan(target.dataset.planId);
        else if (action === 'r320-approval') {
          const record = panel.__r320PendingApproval;
          if (!record?.approval || !record.runId || !record.root) throw new Error('No live authorization request is available.');
          const decision = String(target.dataset.r320Decision || '');
          if (!['approve','reject'].includes(decision)) throw new Error('Unrecognized approval decision.');
          const approvalId = String(record.approval.approval_id || '');
          if (!approvalId) throw new Error('Approval has no durable identifier.');
          target.disabled = true;
          try {
            const result = await BeastRuntime.request(
              `/edgek/agent-runs/${encodeURIComponent(record.runId)}/approvals/${encodeURIComponent(approvalId)}`,
              { method:'POST', timeoutMs:15000, body:{root_path:record.root,approved:decision==='approve',scope:'once'} });
            if (!result?.ok) throw new Error('The gateway did not confirm the approval decision.');
            panel.__r320PendingApproval = null;
            renderPendingApproval(panel);
            window.BeastAICoding?.resumeApprovalWatchdog?.();
            BeastStore.patch('aiCoding', {status:decision==='approve'?'streaming':'review-needed', error:''});
            await syncRunApproval();
          } finally { target.disabled = false; }
        }
        else if (target.dataset.aiPreviewPath) {
          const openAiDiff = [...panel.querySelectorAll('[data-ai-hunk]')].find(node => node.dataset.aiHunk === target.dataset.aiPreviewPath);
          if (openAiDiff) { openAiDiff.open = true; openAiDiff.scrollIntoView({ block: 'nearest' }); }
        }
        else if (target.dataset.aiContextPath) api.toggleContext(target.dataset.aiContextPath);
        else if (target.dataset.aiSuggestedPath) api.acceptSuggestedContext(target.dataset.aiSuggestedPath);
      } catch (error) {
        BeastStore.patch('aiCoding', { status:'error', error:String(error.message || error) });
      }
    }

    const onClick = event => {
      const target = event.target.closest('[data-ai-action],[data-ai-context-path],[data-ai-suggested-path],[data-ai-preview-path],[data-ai-suggestion-mode]');
      if (target) void run(target.dataset.aiAction, target);
      if (event.target.closest('[data-ai-expand]')) api.setExpanded(!BeastStore.get().aiCoding?.expanded);
      const modeTarget = event.target.closest('[data-ai-suggestion-mode]');
      if (modeTarget) void api.setMode(modeTarget.dataset.aiSuggestionMode);
      if (event.target.closest('[data-ai-panel-toggle]')) api.setOpen(!BeastStore.get().aiCoding?.open);
    };
    const onInput = event => {
      if (event.target.matches('[data-ai-prompt]')) api.setPrompt(event.target.value);
    };
    const onChange = event => {
      if (event.target.matches('[data-ai-mode]')) void api.setMode(event.target.value);
    };
    node.addEventListener('click', onClick);
    node.addEventListener('input', onInput);
    node.addEventListener('change', onChange);

    return {
      ...rendered,
      dispose() {
        disposed = true;
        geometryObserver?.disconnect();
        clearInterval(approvalTimer);
        cancelAnimationFrame(aiScrollFrame);
        aiScrollFrame = 0;
        unsubscribe();
        window.removeEventListener('beast-workspace-trust-changed', onTrustChange);
        node.removeEventListener('click', onClick);
        node.removeEventListener('input', onInput);
        node.removeEventListener('change', onChange);
        rendered.dispose?.();
      }
    };
  };
})();
