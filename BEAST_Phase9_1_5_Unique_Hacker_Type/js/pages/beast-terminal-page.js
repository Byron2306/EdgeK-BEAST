(() => {
  const esc = value => String(value ?? '').replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  const trimOutput = value => String(value || '').slice(-30000);

  function template() {
    const root=document.createElement('div');
    root.className='beast-page beast-terminal-page';
    root.innerHTML=`
      <header class="beast-page-head">
        <div><h2>Terminal Nexus</h2><div class="sub">SAFETY GOVERNOR // STREAMED EXECUTION // EVIDENCE RECEIPTS // WORKSPACE-BOUND CWD</div></div>
        <div class="beast-page-actions">
          <button class="beast-button secondary" data-terminal-action="copy"><img src="${BeastAssets.icon('evidence')}" alt="">Copy Receipt</button>
          <button class="beast-button secondary" data-terminal-action="clear"><img src="${BeastAssets.icon('memory')}" alt="">Clear Output</button>
          <button class="beast-button hot" data-terminal-action="classify"><img src="${BeastAssets.icon('policies')}" alt="">Classify</button>
        </div>
      </header>

      <section class="terminal-metric-grid">
        <article class="beast-card compact terminal-metric"><img src="${BeastAssets.icon('policies')}" alt=""><div><h3>Governor</h3><strong data-terminal-decision>UNCLASSIFIED</strong><span data-terminal-risk>risk pending</span></div></article>
        <article class="beast-card compact terminal-metric"><img src="${BeastAssets.icon('terminal')}" alt=""><div><h3>Stream</h3><strong data-terminal-status>IDLE</strong><span data-terminal-duration>0ms</span></div></article>
        <article class="beast-card compact terminal-metric"><img src="${BeastAssets.icon('memory')}" alt=""><div><h3>History</h3><strong data-terminal-history-count>0</strong><span>workspace scoped</span></div></article>
        <article class="beast-card compact terminal-metric"><img src="${BeastAssets.icon('evidence')}" alt=""><div><h3>Receipt</h3><strong data-terminal-receipt>NONE</strong><span data-terminal-exit>exit n/a</span></div></article>
      </section>

      <div class="terminal-main-grid">
        <section class="beast-card wide terminal-console-card is-active" data-terminal-console>
          <header class="beast-panel-head">
            <div><h3>Governed Shell</h3><span data-terminal-context>workspace context unresolved</span></div>
            <div class="terminal-live-pill"><i></i><span data-terminal-stream-label>STREAM IDLE</span></div>
          </header>
          <div class="terminal-command-controls">
            <label class="terminal-command-field"><span>COMMAND</span><input data-terminal-command spellcheck="false" autocomplete="off" placeholder="beast doctor scan --deep"></label>
            <button class="terminal-icon-button classify" data-terminal-action="classify" title="Classify command"><img src="${BeastAssets.icon('policies')}" alt=""></button>
            <button class="terminal-icon-button execute" data-terminal-action="execute" title="Execute governed command"><img src="${BeastAssets.icon('terminal')}" alt=""></button>
            <button class="terminal-icon-button cancel" data-terminal-action="cancel" title="Cancel active stream"><img src="${BeastAssets.icon('alerts')}" alt=""></button>
          </div>
          <div class="terminal-meta-controls">
            <label><span>CWD</span><input data-terminal-cwd spellcheck="false" placeholder="workspace root"></label>
            <button class="beast-button secondary" data-terminal-action="workspace-cwd"><img src="${BeastAssets.icon('workspace')}" alt="">Use Workspace</button>
            <label class="terminal-timeout"><span>TIMEOUT</span><select data-terminal-timeout><option value="30">30s</option><option value="60">60s</option><option value="120">120s</option><option value="300">300s</option><option value="600">600s</option></select></label>
          </div>
          <div class="terminal-screen-wrap">
            <div class="terminal-screen-head"><span>BEAST TERMINAL NEXUS</span><span>UTF-8 · GOVERNED</span></div>
            <pre class="terminal-screen" data-terminal-output aria-live="polite"></pre>
            <div class="terminal-prompt-line"><span>beast@core:</span><b data-terminal-prompt>~$</b><i></i></div>
          </div>
          <div class="terminal-quick-row">
            <button data-terminal-preset="pwd">pwd</button><button data-terminal-preset="git status --short">git status</button>
            <button data-terminal-preset="python --version">python --version</button><button data-terminal-preset="node --version">node --version</button>
            <button data-terminal-preset="beast doctor scan --deep">doctor scan</button>
          </div>
        </section>

        <section class="beast-card terminal-governor-card" data-terminal-governor-card>
          <header class="beast-panel-head"><div><h3>Safety Decision</h3><span>Classify before mutation</span></div><span class="beast-pill" data-terminal-decision-pill>PENDING</span></header>
          <div class="terminal-governor-hero"><img src="${BeastAssets.icon('trust')}" alt=""><div><strong data-terminal-decision-large>UNCLASSIFIED</strong><span data-terminal-risk-large>risk pending</span></div></div>
          <div class="terminal-reasons" data-terminal-reasons><div>No command classified yet.</div></div>
          <div class="terminal-contract-grid">
            <div><span>Root</span><b data-terminal-root>unresolved</b></div><div><span>Mode</span><b>operator</b></div>
            <div><span>Evidence</span><b>required</b></div><div><span>Override</span><b data-terminal-override>not required</b></div>
          </div>
          <button class="beast-button hot terminal-run-button" data-terminal-action="execute"><img src="${BeastAssets.icon('terminal')}" alt="">Execute Governed Command</button>
        </section>
      </div>

      <div class="terminal-lower-grid">
        <section class="beast-card terminal-history-card">
          <header class="beast-panel-head"><div><h3>Command History</h3><span>Restored per workspace</span></div><button class="beast-button secondary" data-terminal-action="clear-history">Clear</button></header>
          <div class="terminal-history-list" data-terminal-history></div>
        </section>
        <section class="beast-card terminal-receipts-card">
          <header class="beast-panel-head"><div><h3>Execution Receipts</h3><span>Evidence-linked outcomes</span></div><button class="beast-button secondary" data-nav="evidence"><img src="${BeastAssets.icon('evidence')}" alt="">Evidence Forge</button></header>
          <div class="terminal-receipt-list" data-terminal-executions></div>
        </section>
      </div>`;
    return root;
  }

  function renderer() {
    const root=template();
    let disposed=false;
    let outputKey='';
    let listKey='';

    function patch(state) {
      if (disposed) return;
      const terminal=state.terminal;
      const decision=String(terminal.decision || 'unclassified').toUpperCase();
      root.querySelector('[data-terminal-decision]').textContent=decision;
      root.querySelector('[data-terminal-risk]').textContent=`risk ${terminal.risk || 'pending'}`;
      root.querySelector('[data-terminal-status]').textContent=String(terminal.status || 'idle').toUpperCase();
      root.querySelector('[data-terminal-duration]').textContent=`${terminal.durationMs || 0}ms`;
      root.querySelector('[data-terminal-history-count]').textContent=String(terminal.history.length);
      const receiptId=terminal.lastReceipt?.evidence_receipt?.receipt_id || terminal.lastReceipt?.evidence_receipt?.id || terminal.lastReceipt?.at || 'NONE';
      root.querySelector('[data-terminal-receipt]').textContent=receiptId === 'NONE' ? receiptId : String(receiptId).slice(-18);
      root.querySelector('[data-terminal-exit]').textContent=`exit ${terminal.lastReceipt?.returncode ?? terminal.returncode ?? 'n/a'}`;
      root.querySelector('[data-terminal-context]').textContent=`${terminal.cwd || state.workspace.root || 'no workspace'} · timeout ${terminal.timeout}s`;
      root.querySelector('[data-terminal-stream-label]').textContent=terminal.streaming ? 'STREAMING' : `STREAM ${String(terminal.status || 'idle').toUpperCase()}`;
      root.querySelector('.terminal-live-pill').classList.toggle('active',terminal.streaming);
      const command=root.querySelector('[data-terminal-command]');
      const cwd=root.querySelector('[data-terminal-cwd]');
      const timeout=root.querySelector('[data-terminal-timeout]');
      if (document.activeElement !== command && command.value !== terminal.command) command.value=terminal.command || '';
      if (document.activeElement !== cwd && cwd.value !== terminal.cwd) cwd.value=terminal.cwd || state.workspace.root || '';
      if (timeout.value !== String(terminal.timeout)) timeout.value=String(terminal.timeout);
      root.querySelector('[data-terminal-prompt]').textContent=`${terminal.cwd || '~'}$`;

      const output=`${terminal.stdout || ''}${terminal.stderr ? `\n[STDERR]\n${terminal.stderr}` : ''}${terminal.error ? `\n[ERROR] ${terminal.error}` : ''}` || 'BEAST Terminal Nexus ready.\nClassify a command before execution.\n';
      const nextOutputKey=`${output.length}:${terminal.status}:${terminal.durationMs}`;
      if (nextOutputKey !== outputKey) {
        outputKey=nextOutputKey;
        const screen=root.querySelector('[data-terminal-output]');
        const nearBottom=screen.scrollHeight-screen.scrollTop-screen.clientHeight < 80;
        screen.textContent=trimOutput(output);
        if (nearBottom || terminal.streaming) screen.scrollTop=screen.scrollHeight;
      }

      const pill=root.querySelector('[data-terminal-decision-pill]');
      pill.textContent=decision;
      pill.className=`beast-pill ${terminal.decision === 'allow' ? 'live' : terminal.decision === 'block' ? 'bad' : terminal.decision ? 'warn' : ''}`;
      root.querySelector('[data-terminal-decision-large]').textContent=decision;
      root.querySelector('[data-terminal-risk-large]').textContent=`RISK ${String(terminal.risk || 'PENDING').toUpperCase()}`;
      root.querySelector('[data-terminal-root]').textContent=(state.workspace.root || 'unresolved').split('/').slice(-2).join('/') || 'unresolved';
      root.querySelector('[data-terminal-override]').textContent=['warn','require_approval','sandbox/worktree_only'].includes(terminal.decision) ? 'operator approval' : terminal.decision === 'block' ? 'forbidden' : 'not required';
      root.querySelector('[data-terminal-governor-card]').classList.toggle('danger',terminal.decision === 'block');
      root.querySelector('[data-terminal-governor-card]').classList.toggle('warning',['warn','require_approval','sandbox/worktree_only'].includes(terminal.decision));
      root.querySelector('[data-terminal-reasons]').innerHTML=(terminal.reasons.length ? terminal.reasons : ['No command classified yet.']).map((reason,index)=>`<div><span>${String(index+1).padStart(2,'0')}</span><p>${esc(reason)}</p></div>`).join('');
      root.querySelectorAll('[data-terminal-action="execute"]').forEach(button => button.disabled=terminal.streaming || terminal.decision === 'block');
      root.querySelectorAll('[data-terminal-action="cancel"]').forEach(button => button.disabled=!terminal.streaming);

      const nextListKey=JSON.stringify([terminal.history,terminal.executions]);
      if (nextListKey !== listKey) {
        listKey=nextListKey;
        root.querySelector('[data-terminal-history]').innerHTML=terminal.history.length ? terminal.history.slice(0,12).map((item,index)=>`<button data-terminal-history-index="${index}"><img src="${BeastAssets.icon('terminal')}" alt=""><span><b>${esc(item)}</b><small>${index===0?'latest command':`history ${index+1}`}</small></span><em>LOAD</em></button>`).join('') : '<div class="cortex-empty-list">No governed command history yet.</div>';
        root.querySelector('[data-terminal-executions]').innerHTML=terminal.executions.length ? terminal.executions.slice(0,10).map((item,index)=>`<button data-terminal-execution-index="${index}" class="${item.ok?'ok':'failed'}"><img src="${BeastAssets.icon(item.ok?'trust':'alerts')}" alt=""><span><b>${esc(item.command || 'command')}</b><small>${esc(item.at || '')} · ${esc(item.decision || 'n/a')} · exit ${esc(item.returncode ?? 'n/a')}</small></span><em>${item.ok?'VERIFIED':'FAILED'}</em></button>`).join('') : '<div class="cortex-empty-list">Execution receipts appear after governed runs.</div>';
      }
    }

    const unsubscribe=BeastStore.subscribe(patch);
    root.addEventListener('input',event => {
      if (event.target.matches('[data-terminal-command]')) BeastTerminalToolingDoctorBridge.setCommand(event.target.value);
      if (event.target.matches('[data-terminal-cwd]')) BeastTerminalToolingDoctorBridge.setCwd(event.target.value);
    });
    root.addEventListener('change',event => { if (event.target.matches('[data-terminal-timeout]')) BeastTerminalToolingDoctorBridge.setTimeoutSeconds(event.target.value); });
    root.addEventListener('keydown',event => {
      if (event.target.matches('[data-terminal-command]') && event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); BeastTerminalToolingDoctorBridge.classify(event.target.value).catch(error=>BeastStore.patch('terminal',{status:'error',error:String(error.message||error)})); }
      if (event.target.matches('[data-terminal-command]') && event.key === 'ArrowUp') {
        const history=BeastStore.get().terminal.history; if (history[0]) { event.preventDefault(); BeastTerminalToolingDoctorBridge.setCommand(history[0]); }
      }
    });
    root.addEventListener('click',async event => {
      const preset=event.target.closest('[data-terminal-preset]');
      if (preset) { BeastTerminalToolingDoctorBridge.setCommand(preset.dataset.terminalPreset); root.querySelector('[data-terminal-command]').focus(); return; }
      const history=event.target.closest('[data-terminal-history-index]');
      if (history) { const command=BeastStore.get().terminal.history[Number(history.dataset.terminalHistoryIndex)] || ''; BeastTerminalToolingDoctorBridge.setCommand(command); root.querySelector('[data-terminal-command]').focus(); return; }
      const execution=event.target.closest('[data-terminal-execution-index]');
      if (execution) { const item=BeastStore.get().terminal.executions[Number(execution.dataset.terminalExecutionIndex)]; if (item?.command) BeastTerminalToolingDoctorBridge.setCommand(item.command); return; }
      const action=event.target.closest('[data-terminal-action]')?.dataset.terminalAction;
      if (!action) return;
      try {
        const terminal=BeastStore.get().terminal;
        if (action==='classify') await BeastTerminalToolingDoctorBridge.classify(terminal.command,{cwd:terminal.cwd});
        if (action==='execute') await BeastTerminalToolingDoctorBridge.execute(terminal.command,{cwd:terminal.cwd,timeout:terminal.timeout});
        if (action==='cancel') BeastTerminalToolingDoctorBridge.cancel();
        if (action==='clear') BeastTerminalToolingDoctorBridge.clearOutput();
        if (action==='clear-history') BeastTerminalToolingDoctorBridge.clearHistory();
        if (action==='workspace-cwd') BeastTerminalToolingDoctorBridge.setCwd(BeastStore.get().workspace.root);
        if (action==='copy') await BeastTerminalToolingDoctorBridge.copyReceipt();
      } catch (error) { BeastStore.patch('terminal',{status:'error',error:String(error.message||error)}); BeastFX.trigger('warning',event.target,{size:210}); }
    });
    if (!BeastStore.get().terminal.history.length && !BeastStore.get().terminal.executions.length) BeastTerminalToolingDoctorBridge.loadTerminalState();
    return {node:root,dispose(){disposed=true;unsubscribe();}};
  }

  window.BeastTerminalPage={renderer};
})();
