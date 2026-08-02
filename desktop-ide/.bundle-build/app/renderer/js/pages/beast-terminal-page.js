(() => {
  const esc = value => String(value ?? '').replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  const trimOutput = value => String(value || '').slice(-30000);
  const taskRuntime={sessions:[],problems:[],output:'',status:'idle',lastReceipt:null};
  const taskSubscribers=new Set();
  function notifyTasks(){for(const callback of taskSubscribers)callback(taskRuntime);}
  function handleTaskMessage(message={}){const session=message.session||{};taskRuntime.sessions=taskRuntime.sessions.filter(item=>item.id!==session.id);if(session.id&&!['exit','stopped'].includes(message.type))taskRuntime.sessions.unshift(session);if(message.type==='started'){taskRuntime.output=`TASK · ${session.task?.label||session.id}\nSTATUS · ${session.status}\n`;taskRuntime.problems=session.problems||[];taskRuntime.status=session.status||'running';}if(message.type==='output'){taskRuntime.output=trimOutput(`${taskRuntime.output}${message.text||''}`);taskRuntime.problems=session.problems||taskRuntime.problems;taskRuntime.status=session.status||taskRuntime.status;}if(message.type==='exit'){taskRuntime.output=trimOutput(`${taskRuntime.output}${message.error?`\n[ERROR] ${message.error}`:''}\n${message.receipt?.id||''}`);taskRuntime.problems=message.problems||session.problems||[];taskRuntime.status=message.ok?'completed':'failed';taskRuntime.lastReceipt=message.receipt||null;}if(message.type==='stopped')taskRuntime.status='stopped';notifyTasks();}
  window.beastDesktop?.onWorkspaceTaskMessage?.(handleTaskMessage);

  function template() {
    const root=document.createElement('div');
    root.className='beast-page beast-terminal-page';
    root.innerHTML=`
      <header class="beast-page-head">
        <div><h2>Terminal Nexus</h2><div class="sub">SAFETY GOVERNOR // STREAMED EXECUTION // EVIDENCE RECEIPTS // WORKSPACE-BOUND CWD</div></div>
        <div class="beast-page-actions">
          <button class="beast-button secondary" data-terminal-action="sync-model"><img src="${BeastAssets.icon('models')}" alt="">Use Selected Model</button>
          <button class="beast-button secondary" data-terminal-action="chat-open"><img src="${BeastAssets.icon('agents')}" alt="">Open Chat</button>
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
        <section class="beast-card wide terminal-chat-card">
          <header class="beast-panel-head"><div><h3>Model Chat Stream</h3><span>Visible model selection for local streaming conversations</span></div><span class="beast-pill" data-terminal-chat-status>idle</span></header>
          <div class="terminal-chat-controls">
            <label><span>Model</span><select data-terminal-model-select></select></label>
            <label><span>Prompt</span><input data-terminal-chat-prompt spellcheck="false" autocomplete="off" placeholder="Explain this file, review this patch, or plan the next step…"></label>
          </div>
          <div class="terminal-chat-actions">
            <button class="beast-button hot" data-terminal-action="chat-start"><img src="${BeastAssets.icon('agents')}" alt="">Start Streaming Chat</button>
            <button class="beast-button secondary" data-terminal-action="chat-stop"><img src="${BeastAssets.icon('alerts')}" alt="">Stop Chat</button>
            <button class="beast-button secondary" data-terminal-action="chat-clear"><img src="${BeastAssets.icon('memory')}" alt="">Clear Chat</button>
          </div>
          <div class="terminal-chat-meta">
            <div><span>Provider</span><b data-terminal-chat-provider>local_ollama</b></div>
            <div><span>Session</span><b data-terminal-chat-session>none</b></div>
            <div><span>Selected</span><b data-terminal-chat-model>none</b></div>
          </div>
          <pre class="terminal-chat-output" data-terminal-chat-output aria-live="polite"></pre>
          <details class="terminal-chat-trace"><summary>Show chat run details <small>PREC, context, and provider lifecycle</small><span data-terminal-chat-trace-count>0 events</span></summary><div data-terminal-chat-trace></div></details>
        </section>
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
          <div class="terminal-session-bar"><button class="beast-button secondary" data-terminal-session-action="start">Start Integrated Shell</button><input data-terminal-session-input spellcheck="false" autocomplete="off" placeholder="Input to persistent shell…"><button class="beast-button secondary" data-terminal-session-action="send">Send</button><button class="beast-button secondary" data-terminal-session-action="stop">Disconnect</button><span data-terminal-session-status>disconnected</span></div>
          <pre class="terminal-session-output" data-terminal-session-output aria-live="polite">No persistent integrated shell is connected.</pre>
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
        <section class="beast-card terminal-dev-card">
          <header class="beast-panel-head"><div><h3>Workspace Operations</h3><span>Bounded search, previewed replace, Git state, and explicit npm or VS Code tasks.</span></div><span class="beast-pill" data-dev-status>READY</span></header>
          <div class="terminal-chat-controls"><label><span>WORKSPACE FOLDER</span><select data-dev-root></select></label><label><span>SEARCH</span><input data-dev-search placeholder="Find text across workspace"></label><label><span>REPLACE WITH</span><input data-dev-replace placeholder="Optional replacement"></label></div>
          <div class="terminal-chat-actions"><button class="beast-button hot" data-dev-action="search">Search</button><button class="beast-button secondary" data-dev-action="replace-preview">Preview Replace</button><button class="beast-button secondary" data-dev-action="replace-apply">Apply Replace</button><button class="beast-button secondary" data-dev-action="git">Git Status</button><button class="beast-button secondary" data-dev-action="git-repositories">All Repositories</button></div>
          <div class="terminal-chat-controls"><label><span>DECLARED TASK</span><select data-dev-task><option value="">Load tasks…</option></select></label><button class="beast-button secondary" data-dev-action="tasks">Refresh Tasks</button><button class="beast-button hot" data-dev-action="task-run">Run Task</button><button class="beast-button secondary" data-dev-action="task-stop">Stop Active</button></div>
          <div class="terminal-chat-controls"><label><span>TEST TARGET</span><select data-dev-test><option value="">Discover tests…</option></select></label><button class="beast-button secondary" data-dev-action="tests">Discover Tests</button><button class="beast-button hot" data-dev-action="test-run">Run Test</button><button class="beast-button secondary" data-dev-action="test-debug">Debug Test</button></div>
          <div class="terminal-chat-controls"><label><span>TEST FILE</span><select data-dev-test-file><option value="">Discover test files…</option></select></label><button class="beast-button secondary" data-dev-action="test-file-run">Run File</button><button class="beast-button secondary" data-dev-action="test-file-debug">Debug File</button></div>
          <details class="terminal-chat-trace"><summary>Workspace Settings <small>per-folder .vscode/settings.json</small></summary><div class="terminal-chat-actions"><button class="beast-button secondary" data-dev-action="settings-load">Load Settings</button><button class="beast-button hot" data-dev-action="settings-save">Save Settings</button></div><textarea data-dev-settings spellcheck="false" placeholder="Load a workspace folder’s settings to edit JSON here."></textarea></details>
          <div class="terminal-task-sessions" data-dev-task-sessions>No streamed task session is active.</div>
          <pre class="terminal-chat-output" data-dev-output>Search, preview a replace, inspect Git, or run an explicit workspace task.</pre>
          <section class="terminal-problems"><header><span><b>Problems</b><small>Task problem matchers</small></span><em data-dev-problem-count>0</em></header><div data-dev-problems>No task diagnostics yet.</div></section>
        </section>
      </div>`;
    return root;
  }

  function renderer() {
    const root=template();
    let disposed=false;
    let outputKey='';
    let chatOutputKey='';
    let terminalFollowOutput=true;
    let chatFollowOutput=true;
    let listKey='';
    let devOutput='Search, preview a replace, inspect Git, or run an explicit workspace task.';
    let devTasks=[];
    const workspaceScope=()=>{const id=root.querySelector('[data-dev-root]')?.value||'';return id?{rootId:id}:{};};
    const terminalOutputPane=root.querySelector('[data-terminal-output]');
    terminalOutputPane.addEventListener('scroll',()=>{terminalFollowOutput=terminalOutputPane.scrollHeight-terminalOutputPane.scrollTop-terminalOutputPane.clientHeight<80;},{passive:true});
    const chatOutputPane=root.querySelector('[data-terminal-chat-output]');
    chatOutputPane.addEventListener('scroll',()=>{chatFollowOutput=chatOutputPane.scrollHeight-chatOutputPane.scrollTop-chatOutputPane.clientHeight<80;},{passive:true});

    function revealChat({ focus=false }={}) {
      const card=root.querySelector('.terminal-chat-card');
      card?.scrollIntoView({ block:'start', behavior:'smooth' });
      if (focus) root.querySelector('[data-terminal-chat-prompt]')?.focus({ preventScroll:true });
    }
    function renderTaskRuntime(state=taskRuntime){const sessions=root.querySelector('[data-dev-task-sessions]');sessions.innerHTML=state.sessions.length?state.sessions.map(session=>`<div><span><b>${esc(session.task?.label||session.id)}</b><small>${esc(String(session.status||'running').replaceAll('-',' '))} · ${esc(session.task?.source||'workspace')} ${session.task?.isBackground?'· background':''}</small></span><button type="button" data-dev-task-stop="${esc(session.id)}">Stop</button></div>`).join(''):'No streamed task session is active.';root.querySelector('[data-dev-problem-count]').textContent=String(state.problems.length);root.querySelector('[data-dev-problems]').innerHTML=state.problems.length?state.problems.map(problem=>`<button type="button" class="${esc(problem.severity||'error')}" data-dev-problem-path="${esc(problem.file)}" data-dev-problem-line="${Number(problem.line)||1}"><span>${esc(String(problem.severity||'error').toUpperCase())}</span><b>${esc(problem.file)}:${Number(problem.line)||1}:${Number(problem.column)||1}</b><small>${esc(problem.message||'Task diagnostic')}${problem.code?` · ${esc(problem.code)}`:''}</small></button>`).join(''):'No task diagnostics yet.';if(state.output){devOutput=state.output;root.querySelector('[data-dev-output]').textContent=state.output;root.querySelector('[data-dev-status]').textContent=String(state.status||'idle').toUpperCase();}}

    function patch(state) {
      if (disposed) return;
      const terminal=state.terminal;
      const selectedModel=state.models.registry.find(model => model.id === terminal.selectedModel) || state.models.registry.find(model => model.id === state.models.selectedId) || state.models.registry.find(model => model.id === state.models.active) || {};
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
      const session=state.runtime?.terminal || {};
      root.querySelector('[data-terminal-session-status]').textContent=String(session.sessionStatus||'disconnected');
      root.querySelector('[data-terminal-session-output]').textContent=session.sessionOutput||'No persistent integrated shell is connected.';
      root.querySelector('.terminal-live-pill').classList.toggle('active',terminal.streaming);
      root.querySelector('[data-terminal-chat-status]').textContent=terminal.chatStreaming ? 'streaming' : String(terminal.chatStatus || 'idle');
      root.querySelector('[data-terminal-chat-status]').className=`beast-pill ${terminal.chatStreaming ? 'live' : ['error','failed'].includes(terminal.chatStatus) ? 'bad' : terminal.chatStatus === 'operator-needed' ? 'warn' : ''}`;
      root.querySelector('[data-terminal-chat-provider]').textContent=terminal.selectedProvider || state.models.provider || 'local_ollama';
      root.querySelector('[data-terminal-chat-session]').textContent=terminal.chatSessionId || 'none';
      root.querySelector('[data-terminal-chat-model]').textContent=selectedModel.id || terminal.selectedModel || state.models.selectedId || state.models.active || 'none';
      const command=root.querySelector('[data-terminal-command]');
      const cwd=root.querySelector('[data-terminal-cwd]');
      const timeout=root.querySelector('[data-terminal-timeout]');
      if (document.activeElement !== command && command.value !== terminal.command) command.value=terminal.command || '';
      if (document.activeElement !== cwd && cwd.value !== terminal.cwd) cwd.value=terminal.cwd || state.workspace.root || '';
      if (timeout.value !== String(terminal.timeout)) timeout.value=String(terminal.timeout);
      root.querySelector('[data-terminal-prompt]').textContent=`${terminal.cwd || '~'}$`;
      const chatPrompt=root.querySelector('[data-terminal-chat-prompt]');
      if (document.activeElement !== chatPrompt && chatPrompt.value !== terminal.chatPrompt) chatPrompt.value=terminal.chatPrompt || '';
      const modelSelect=root.querySelector('[data-terminal-model-select]');
      const models=(state.models.registry || []).filter(model=>model.selectable !== false && model.credentialReady !== false && !/disabled|unavailable|missing/i.test(String(model.status || '')));
      const optionsKey=JSON.stringify([models.map(model => [model.id, model.provider, model.status]), terminal.selectedModel, state.models.selectedId, state.models.active]);
      if (modelSelect.dataset.optionsKey !== optionsKey) {
        modelSelect.dataset.optionsKey = optionsKey;
        modelSelect.innerHTML = models.length ? models.map(model => `<option value="${esc(model.id)}">${esc(model.id)} · ${esc(model.provider)} · ${esc(model.runtime || 'runtime')}</option>`).join('') : `<option value="${esc(terminal.selectedModel || state.models.selectedId || state.models.active || '')}">${esc(terminal.selectedModel || state.models.selectedId || state.models.active || 'No model discovered')}</option>`;
      }
      const selectedValue=terminal.selectedModel || state.models.selectedId || state.models.active || '';
      if (selectedValue && modelSelect.value !== selectedValue) modelSelect.value = selectedValue;
      const rootSelect=root.querySelector('[data-dev-root]');const folders=state.workspace.roots||[];const rootKey=JSON.stringify(folders.map(folder=>[folder.id,folder.name,folder.path]));if(rootSelect.dataset.key!==rootKey){const prior=rootSelect.value;rootSelect.dataset.key=rootKey;rootSelect.innerHTML=folders.map(folder=>`<option value="${esc(folder.id)}">${esc(folder.name)}${folder.primary?' · primary':''}</option>`).join('')||'<option value="">Primary workspace</option>';rootSelect.value=folders.some(folder=>folder.id===prior)?prior:(folders.find(folder=>folder.primary)?.id||'');}

      const output=`${terminal.stdout || ''}${terminal.stderr ? `\n[STDERR]\n${terminal.stderr}` : ''}${terminal.error ? `\n[ERROR] ${terminal.error}` : ''}` || 'BEAST Terminal Nexus ready.\nClassify a command before execution.\n';
      const nextOutputKey=`${output.length}:${terminal.status}:${terminal.durationMs}`;
      if (nextOutputKey !== outputKey) {
        outputKey=nextOutputKey;
        const screen=root.querySelector('[data-terminal-output]');
        const followOutput=terminalFollowOutput || screen.scrollHeight-screen.scrollTop-screen.clientHeight < 80;
        const previousTop=screen.scrollTop;
        screen.textContent=trimOutput(output);
        screen.scrollTop=followOutput ? screen.scrollHeight : previousTop;
        terminalFollowOutput=followOutput;
      }
      const chatOutput=`${terminal.chatOutput || ''}${terminal.chatError ? `\n[ERROR] ${terminal.chatError}` : ''}` || 'Choose a model, enter a prompt, and start a visible stream.\n';
      // Length alone stops repainting once the bounded transcript reaches its
      // cap. Keep the visible tail itself in the key so every stream token can
      // repaint the terminal surface.
      const nextChatKey=`${chatOutput}\u0000${terminal.chatStatus}:${terminal.chatStreaming}:${terminal.chatSessionId}`;
      if (nextChatKey !== chatOutputKey) {
        chatOutputKey=nextChatKey;
        const pane=root.querySelector('[data-terminal-chat-output]');
        const followOutput=chatFollowOutput || pane.scrollHeight-pane.scrollTop-pane.clientHeight < 80;
        const previousTop=pane.scrollTop;
        pane.textContent=trimOutput(chatOutput);
        pane.scrollTop=followOutput ? pane.scrollHeight : previousTop;
        chatFollowOutput=followOutput;
      }
      const trace=terminal.chatTrace || [];
      const traceKey=JSON.stringify(trace);
      const tracePanel=root.querySelector('[data-terminal-chat-trace]');
      if (tracePanel.dataset.key !== traceKey) {
        tracePanel.dataset.key=traceKey;
        tracePanel.innerHTML=trace.length ? trace.map(item=>`<div class="trace-${esc(item.kind)}"><b>${esc(String(item.kind || 'event').toUpperCase())}</b><span>${esc(item.text)}</span></div>`).join('') : '<span>No run details yet.</span>';
        root.querySelector('[data-terminal-chat-trace-count]').textContent=`${trace.length} event${trace.length===1?'':'s'}`;
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
      root.querySelectorAll('[data-terminal-action="chat-start"]').forEach(button => button.disabled=terminal.chatStreaming);
      root.querySelectorAll('[data-terminal-action="chat-stop"]').forEach(button => button.disabled=!terminal.chatStreaming);

      const nextListKey=JSON.stringify([terminal.history,terminal.executions]);
      if (nextListKey !== listKey) {
        listKey=nextListKey;
        root.querySelector('[data-terminal-history]').innerHTML=terminal.history.length ? terminal.history.slice(0,12).map((item,index)=>`<button data-terminal-history-index="${index}"><img src="${BeastAssets.icon('terminal')}" alt=""><span><b>${esc(item)}</b><small>${index===0?'latest command':`history ${index+1}`}</small></span><em>LOAD</em></button>`).join('') : '<div class="cortex-empty-list">No governed command history yet.</div>';
        root.querySelector('[data-terminal-executions]').innerHTML=terminal.executions.length ? terminal.executions.slice(0,10).map((item,index)=>`<button data-terminal-execution-index="${index}" class="${item.ok?'ok':'failed'}"><img src="${BeastAssets.icon(item.ok?'trust':'alerts')}" alt=""><span><b>${esc(item.command || 'command')}</b><small>${esc(item.at || '')} · ${esc(item.decision || 'n/a')} · exit ${esc(item.returncode ?? 'n/a')}</small></span><em>${item.ok?'VERIFIED':'FAILED'}</em></button>`).join('') : '<div class="cortex-empty-list">Execution receipts appear after governed runs.</div>';
      }
    }

    const unsubscribe=BeastStore.subscribe(patch);
    const taskSubscription=state=>renderTaskRuntime(state);taskSubscribers.add(taskSubscription);renderTaskRuntime();
    root.addEventListener('input',event => {
      if (event.target.matches('[data-terminal-command]')) BeastTerminalToolingDoctorBridge.setCommand(event.target.value);
      if (event.target.matches('[data-terminal-cwd]')) BeastTerminalToolingDoctorBridge.setCwd(event.target.value);
      if (event.target.matches('[data-terminal-chat-prompt]')) BeastTerminalToolingDoctorBridge.setChatPrompt(event.target.value);
      if (event.target.matches('[data-terminal-model-select]')) BeastTerminalToolingDoctorBridge.syncModelSelection(event.target.value);
    });
    root.addEventListener('change',event => {
      if (event.target.matches('[data-terminal-timeout]')) BeastTerminalToolingDoctorBridge.setTimeoutSeconds(event.target.value);
      if (event.target.matches('[data-terminal-model-select]')) BeastTerminalToolingDoctorBridge.syncModelSelection(event.target.value);
      if (event.target.matches('[data-dev-root]')) document.dispatchEvent(new CustomEvent('beast:source-control-root',{detail:{rootId:event.target.value}}));
    });
    root.addEventListener('keydown',event => {
      if (event.target.matches('[data-terminal-command]') && event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); BeastTerminalToolingDoctorBridge.classify(event.target.value).catch(error=>BeastStore.patch('terminal',{status:'error',error:String(error.message||error)})); }
      if (event.target.matches('[data-terminal-command]') && event.key === 'ArrowUp') {
        const history=BeastStore.get().terminal.history; if (history[0]) { event.preventDefault(); BeastTerminalToolingDoctorBridge.setCommand(history[0]); }
      }
      if (event.target.matches('[data-terminal-chat-prompt]') && event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        revealChat();
        BeastTerminalToolingDoctorBridge.startChat(event.target.value,{model:root.querySelector('[data-terminal-model-select]')?.value || BeastStore.get().terminal.selectedModel}).catch(error=>BeastStore.patch('terminal',{chatStatus:'error',chatError:String(error.message||error)}));
      }
    });
    root.addEventListener('click',async event => {
      const sessionAction=event.target.closest('[data-terminal-session-action]')?.dataset.terminalSessionAction;
      if(sessionAction){try{if(sessionAction==='start')await BeastIDERuntime.startTerminalSession({cwd:BeastStore.get().workspace.root});if(sessionAction==='send')await BeastIDERuntime.sendTerminalSession(root.querySelector('[data-terminal-session-input]').value);if(sessionAction==='stop')await BeastIDERuntime.stopTerminalSession();if(sessionAction==='send')root.querySelector('[data-terminal-session-input]').value='';}catch(error){BeastStore.patch('terminal',{sessionStatus:'error',sessionError:String(error.message||error)});}return;}
      const testAction=event.target.closest('[data-dev-action]')?.dataset.devAction;
      if(['tests','test-run','test-debug','test-file-run','test-file-debug','settings-load','settings-save','git-repositories'].includes(testAction)){
        event.stopImmediatePropagation();const desktop=window.beastDesktop;const output=root.querySelector('[data-dev-output]');const status=root.querySelector('[data-dev-status]');
        try{status.textContent=testAction.startsWith('settings')?'SETTINGS':testAction==='git-repositories'?'GIT':'TESTING';const chosenFile=root.querySelector('[data-dev-test-file]').value;if(testAction==='git-repositories'){const result=await desktop.workspaceGitRepositories();output.textContent=(result.repositories||[]).map(row=>{const state=row.status||{};const counts=state.counts||{};return `${row.folder?.name||row.folder?.id} · ${state.ok?state.branchName||state.branch||'repository':'not a repository'}\n  staged ${counts.staged||0} · unstaged ${counts.unstaged||0} · conflicts ${counts.conflicts||0}${state.error?` · ${state.error}`:''}`;}).join('\n\n')||'No workspace folders selected.';}else if(testAction==='tests'){const result=await desktop.workspaceTests(workspaceScope());const tests=result.tests||[];root.querySelector('[data-dev-test]').innerHTML='<option value="">Select test target…</option>'+tests.map(test=>`<option value="${esc(test.id)}">${esc(test.label)} · ${esc(test.framework)}</option>`).join('');const files=result.files||[];root.querySelector('[data-dev-test-file]').innerHTML='<option value="">Select discovered test file…</option>'+files.map(file=>`<option value="${esc(file.path)}">${esc(file.path)}</option>`).join('');output.textContent=tests.length?`${tests.length} runnable target(s) · ${files.length} discovered test file(s)\n`+files.slice(0,80).map(file=>`  ${file.path}`).join('\n'):'No declared test target found.';}else if(testAction==='test-run'||testAction==='test-file-run'){const id=root.querySelector('[data-dev-test]').value;if(!id)throw new Error('Discover and select a test target first.');if(testAction==='test-file-run'&&!chosenFile)throw new Error('Select a discovered test file first.');const result=await desktop.runWorkspaceTest({...workspaceScope(),id,...(testAction==='test-file-run'?{file:chosenFile}:{})});output.textContent=result.ok?`TEST · ${result.file||result.test?.label||id}\n${result.stdout||''}${result.stderr?`\n[stderr]\n${result.stderr}`:''}\n${result.receipt?.id||''}`:result.error||result.stderr||'Test failed.';}else if(testAction==='test-debug'||testAction==='test-file-debug'){const id=root.querySelector('[data-dev-test]').value;if(id!=='python:pytest')throw new Error('Debug Test currently supports the discovered pytest target.');if(testAction==='test-file-debug'&&!chosenFile)throw new Error('Select a discovered test file first.');await BeastIDERuntime.startDebug({adapter:'debugpy',configuration:{name:`BEAST pytest${chosenFile?` · ${chosenFile}`:''}`,type:'python',request:'launch',module:'pytest',args:testAction==='test-file-debug'?[chosenFile]:[],cwd:BeastDesktopBridge.workspaceFolderForPath?.(BeastStore.get().editor.activePath)?.root||BeastStore.get().workspace.root,console:'internalConsole',justMyCode:true}});output.textContent='PYTEST DEBUG SESSION STARTED · use IDE Compatibility to control execution.';await BeastRouter.navigate('compatibility');}else if(testAction==='settings-load'){const result=await desktop.workspaceSettings(workspaceScope());if(!result.ok)throw new Error(result.error||'Unable to load workspace settings.');root.querySelector('[data-dev-settings]').value=JSON.stringify(result.settings||{},null,2);output.textContent=`SETTINGS · ${result.path}\n${result.exists?'Loaded existing workspace settings.':'No settings file yet; editing will create one.'}`;}else{let settings;try{settings=JSON.parse(root.querySelector('[data-dev-settings]').value||'{}');}catch(_){throw new Error('Workspace settings must be valid JSON.');}const result=await desktop.saveWorkspaceSettings({...workspaceScope(),settings});if(!result.ok)throw new Error(result.error||'Unable to save workspace settings.');output.textContent=`SETTINGS SAVED · ${result.path}\n${result.receipt?.id||''}`;}status.textContent='READY';}catch(error){output.textContent=String(error.message||error);status.textContent='ERROR';}return;
      }
      const problem=event.target.closest('[data-dev-problem-path]');if(problem){await BeastEditorCortex.openFile(problem.dataset.devProblemPath);await BeastRouter.navigate('workspace');BeastEditorCortex.gotoLine(Number(problem.dataset.devProblemLine)||1);return;}
      const stopTask=event.target.closest('[data-dev-task-stop]')?.dataset.devTaskStop;if(stopTask){await window.beastDesktop.stopWorkspaceTask(stopTask);return;}
      const preset=event.target.closest('[data-terminal-preset]');
      if (preset) { BeastTerminalToolingDoctorBridge.setCommand(preset.dataset.terminalPreset); root.querySelector('[data-terminal-command]').focus(); return; }
      const history=event.target.closest('[data-terminal-history-index]');
      if (history) { const command=BeastStore.get().terminal.history[Number(history.dataset.terminalHistoryIndex)] || ''; BeastTerminalToolingDoctorBridge.setCommand(command); root.querySelector('[data-terminal-command]').focus(); return; }
      const execution=event.target.closest('[data-terminal-execution-index]');
      if (execution) { const item=BeastStore.get().terminal.executions[Number(execution.dataset.terminalExecutionIndex)]; if (item?.command) BeastTerminalToolingDoctorBridge.setCommand(item.command); return; }
      const action=event.target.closest('[data-terminal-action]')?.dataset.terminalAction;
      const devAction=event.target.closest('[data-dev-action]')?.dataset.devAction;
      if(devAction){const desktop=window.beastDesktop;const output=root.querySelector('[data-dev-output]');const status=root.querySelector('[data-dev-status]');const query=root.querySelector('[data-dev-search]').value;const replacement=root.querySelector('[data-dev-replace]').value;const scope=workspaceScope();try{status.textContent='WORKING';if(devAction==='search'){const result=await desktop.searchWorkspace({...scope,query});devOutput=result.ok?(result.results||[]).map(row=>`${row.path}:${row.line}:${row.column}  ${row.preview}`).join('\n')||'No matches.':result.error;}if(devAction==='replace-preview'||devAction==='replace-apply'){const result=await desktop.replaceWorkspace({...scope,query,replacement,apply:devAction==='replace-apply'});devOutput=result.ok?`${result.applied?'APPLIED':'PREVIEW'} · ${result.total} replacement(s)\n`+(result.files||[]).map(file=>`${file.path} · ${file.count}`).join('\n'):result.error;}if(devAction==='git'){const result=await desktop.workspaceGitStatus(scope);devOutput=result.ok?`BRANCH ${result.branch||'detached'}\n${(result.changes||[]).map(row=>`${row.index} ${row.path}`).join('\n')||'Working tree clean.'}\n\n${result.diffStat||''}`:result.error;}if(devAction==='tasks'){const result=await desktop.workspaceTasks(scope);devTasks=result.tasks||[];const select=root.querySelector('[data-dev-task]');select.innerHTML='<option value="">Select declared task…</option>'+devTasks.map(task=>`<option value="${esc(task.id)}">${esc(task.label)}${task.isBackground?' · background':''}${task.problemMatchers?.length?' · problems':''}</option>`).join('');const vscode=devTasks.filter(task=>task.source==='.vscode/tasks.json').length;devOutput=devTasks.length?`${devTasks.length} explicit workspace task(s): ${devTasks.length-vscode} npm · ${vscode} VS Code task definition(s).`:'No package.json scripts or .vscode/tasks.json definitions found.';}if(devAction==='task-run'){const id=root.querySelector('[data-dev-task]').value;if(!id)throw new Error('Select a declared task first.');if(desktop.startWorkspaceTask){const result=await desktop.startWorkspaceTask({...scope,id});devOutput=`TASK · ${result.session?.task?.label||id}\nSTATUS · ${result.session?.status||'running'}\nStreaming output and task Problems…`;}else{const result=await desktop.runWorkspaceTask({...scope,id});devOutput=result.ok?`TASK · ${result.task?.label||id}\nSOURCE · ${result.task?.source||'workspace'}\n${result.stdout||''}${result.stderr?`\n[stderr]\n${result.stderr}`:''}\n${result.receipt?.id||''}`:result.error;}}if(devAction==='task-stop'){const id=taskRuntime.sessions[0]?.id;if(!id)throw new Error('No active task session.');await desktop.stopWorkspaceTask(id);devOutput='Task stop requested.';}output.textContent=devOutput.slice(-30000);status.textContent=devAction==='task-run'?'RUNNING':'READY';}catch(error){output.textContent=String(error.message||error);status.textContent='ERROR';}return;}
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
        if (action==='sync-model') BeastTerminalToolingDoctorBridge.syncModelSelection(root.querySelector('[data-terminal-model-select]')?.value || terminal.selectedModel || BeastStore.get().models.selectedId || BeastStore.get().models.active || '');
        if (action==='chat-open') { BeastTerminalToolingDoctorBridge.syncModelSelection(root.querySelector('[data-terminal-model-select]')?.value || terminal.selectedModel || BeastStore.get().models.selectedId || BeastStore.get().models.active || ''); revealChat({focus:true}); }
        if (action==='chat-start') { revealChat(); await BeastTerminalToolingDoctorBridge.startChat(root.querySelector('[data-terminal-chat-prompt]')?.value,{model:root.querySelector('[data-terminal-model-select]')?.value || terminal.selectedModel}); }
        if (action==='chat-stop') BeastTerminalToolingDoctorBridge.cancelChat();
        if (action==='chat-clear') BeastTerminalToolingDoctorBridge.clearChat();
      } catch (error) { BeastStore.patch('terminal',{status:'error',error:String(error.message||error)}); BeastFX.trigger('warning',event.target,{size:210}); }
    });
    if (!BeastStore.get().terminal.history.length && !BeastStore.get().terminal.executions.length) BeastTerminalToolingDoctorBridge.loadTerminalState();
    if (!BeastStore.get().models.registry.length) BeastModelAgentBridge.refreshModels().catch(() => {});
    return {node:root,dispose(){disposed=true;unsubscribe();taskSubscribers.delete(taskSubscription);}};
  }

  window.BeastTerminalPage={renderer};
})();
