(() => {
  function escapeHtml(value) { return String(value ?? '').replace(/[&<>"']/g, char => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' })[char]); }
  function formatSize(value) {
    const size = Number(value); if (!Number.isFinite(size) || size <= 0) return '';
    if (size < 1024) return `${size} B`; if (size < 1024 ** 2) return `${(size / 1024).toFixed(1)} KB`; return `${(size / 1024 ** 2).toFixed(1)} MB`;
  }
  function iconFor(path, type) {
    if (type === 'directory') return BeastAssets.icon('project');
    const ext = String(path).split('.').pop().toLowerCase();
    return ['js','jsx','ts','tsx','py','html','css','sh','go','rs'].includes(ext) ? BeastAssets.icon('terminal') : BeastAssets.icon('files');
  }
  function fileName(path) { return String(path || '').split('/').pop() || path; }
  function aiInline(value) { return escapeHtml(value).replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/`([^`\n]+)`/g,'<code>$1</code>'); }
  function aiPlainBlocks(value) {
    return String(value||'').split(/\n{2,}/).map(block=>{const lines=block.split('\n').filter((line,index,all)=>line||all.length===1);if(!lines.length)return '';if(lines.every(line=>/^\s*[-*]\s+/.test(line)))return `<ul>${lines.map(line=>`<li>${aiInline(line.replace(/^\s*[-*]\s+/,''))}</li>`).join('')}</ul>`;const heading=lines[0].match(/^#{1,3}\s+(.+)$/);if(heading)return `<h4>${aiInline(heading[1])}</h4>${lines.length>1?`<p>${lines.slice(1).map(aiInline).join('<br>')}</p>`:''}`;return `<p>${lines.map(aiInline).join('<br>')}</p>`;}).join('');
  }
  function aiMessageBody(value) {
    const text=String(value||'');if(!text)return '';
    if(/^[\[{]/.test(text.trim())){try{return `<pre class="cortex-ai-code"><code>${escapeHtml(JSON.stringify(JSON.parse(text),null,2))}</code></pre>`;}catch(_){}}
    const out=[];let cursor=0;const fence=/```([^\n`]*)\n?([\s\S]*?)```/g;let match;
    while((match=fence.exec(text))){if(match.index>cursor)out.push(aiPlainBlocks(text.slice(cursor,match.index)));const language=String(match[1]||'code').trim().replace(/[^A-Za-z0-9_+.-]/g,'').slice(0,24)||'code';out.push(`<pre class="cortex-ai-code"><span>${escapeHtml(language)}</span><code>${escapeHtml(match[2].replace(/\n$/,''))}</code></pre>`);cursor=fence.lastIndex;}
    if(cursor<text.length)out.push(aiPlainBlocks(text.slice(cursor)));return out.join('');
  }
  function aiVisibleMessageContent(message) {
    const liveNarration=message?.role==='assistant'&&message?.mode!=='ask'&&message?.streaming&&!message?.proposal&&!message?.error&&Array.isArray(message?.narration)&&message.narration.length;
    if(liveNarration)return '';
    return message?.content || (message?.streaming ? 'Waiting for the first streamed token…' : '');
  }
  function aiClock(value) { try{return new Date(Number(value)||Date.now()).toLocaleTimeString([],{hour:'numeric',minute:'2-digit'});}catch(_){return '';} }
  function aiProgress(message) {
    const rows=Array.isArray(message?.progress)?message.progress:[];if(!rows.length)return '';
    return `<ol class="cortex-ai-progress" aria-label="Agent run progress">${rows.map(item=>`<li class="${escapeHtml(item.state||'active')}"><i aria-hidden="true">${item.state==='done'||item.state==='ready'?'✓':item.state==='failed'?'!':'•'}</i><span><b>${escapeHtml(item.label||'Working')}</b>${item.detail?`<small>${escapeHtml(item.detail)}</small>`:''}</span></li>`).join('')}</ol>`;
  }
  function aiAgentCockpit(message) {
    if(message?.role!=='assistant'||message?.mode==='ask')return '';
    const turns=Array.isArray(message?.turns)?message.turns:[];const draft=message?.draftPreview||{};const proposal=message?.proposal||{};const profile=message?.agentProfile||{};
    if(!turns.length&&!draft.chars&&!proposal.operations?.length)return '';
    const text=turns.map(item=>`${item.kind||''} ${item.text||''}`.toLowerCase());
    const count=pattern=>text.filter(value=>pattern.test(value)).length;
    const last=[...turns].reverse().find(item=>String(item.text||'').trim());
    const validation=turns.findLast?.(item=>item.kind==='validation')||turns.slice().reverse().find(item=>item.kind==='validation');
    const sourceplan=turns.findLast?.(item=>item.kind==='sourceplan')||turns.slice().reverse().find(item=>item.kind==='sourceplan');
    const cards=[
      ['Intent',profile.kind||message.mode||'agent',profile.mutating===false?'ready':'active'],
      ['Context',count(/context|read|provider input|content loaded/),turns.some(item=>item.kind==='context'&&item.state==='failed')?'attention':'ready'],
      ['Tools',count(/tool|search|semantic|cortex|crystal|handoff|envelope|insight/),'active'],
      ['Skills',count(/skill|recipe/),count(/skill|recipe/)?'ready':'idle'],
      ['Verify',validation?validation.text:'waiting',validation?.state||'idle'],
      ['SourcePlan',sourceplan?sourceplan.text:(proposal.operations?.length?`${proposal.operations.length} ready`:'pending'),sourceplan?.state||(proposal.ready?'ready':'idle')],
    ];
    const draftLine=draft.chars?`${Number(draft.chars).toLocaleString()} streamed chars · ${Number(draft.actions||0)} structured edit${Number(draft.actions||0)===1?'':'s'}`:(proposal.operations?.length?'SourcePlan draft ready':'Reading workspace context');
    return `<section class="cortex-ai-cockpit" aria-label="Agent cockpit"><header><span><b>Agent cockpit</b><small>${escapeHtml(draftLine)}</small></span><em>${escapeHtml(last?.text||message.activity||'Working')}</em></header><div>${cards.map(([label,value,state])=>`<p class="${escapeHtml(state||'idle')}"><b>${escapeHtml(label)}</b><span>${escapeHtml(value)}</span></p>`).join('')}</div></section>`;
  }
  function aiNarrationSentence(item) {
    const text=String(item?.text||'').replace(/\s+/g,' ').trim();const command=String(item?.command||'').trim();const type=String(item?.type||item?.kind||'');const tool=String(item?.tool||'').trim();const lower=`${tool} ${text}`.toLowerCase();
    if(!text&&!command)return '';
    if(type==='context_read')return item.state==='failed'?`I could not read the requested context: ${text}`:`I read the selected workspace context and locked it to this run.`;
    if(type==='tool_call'){
      if(lower.includes('code cortex'))return 'I’m inspecting the selected code and nearby dependencies now.';
      if(lower.includes('workspace search'))return 'I’m searching the workspace for the symbols and references that matter.';
      if(lower.includes('related file'))return 'I’m reading the approved related files so the next step is grounded.';
      if(lower.includes('verified skill'))return 'I’m checking the verified BEAST recipes that apply to this task.';
      if(lower.includes('semantic raid'))return 'I’m saving the exact context packet as local evidence for this run.';
      if(lower.includes('provider handoff'))return 'I’m handing the scoped context to the selected model now.';
      return text?`I’m using ${tool||'a governed BEAST tool'}: ${text}`:`I’m using ${tool||'a governed BEAST tool'} now.`;
    }
    if(type==='tool_result'){
      if(lower.includes('code cortex'))return 'I mapped the selected code, symbols, and direct dependents.';
      if(lower.includes('workspace search'))return 'I found the relevant workspace symbols and editing context.';
      if(lower.includes('related file'))return 'I added the approved related files to this turn.';
      if(lower.includes('verified skill'))return text.includes('no matching')?'I checked the skill library; no matching verified recipe was available.':'I selected the matching verified BEAST recipe guidance.';
      if(lower.includes('semantic raid'))return lower.includes('deferred')?'I could not mirror the context packet, so I’m continuing without that evidence cache.':'I saved the exact context packet as local evidence.';
      if(lower.includes('provider handoff'))return 'My governed input is ready and bounded to the selected files.';
      if(lower.includes('insight compile'))return 'I checked prior repo evidence for anything useful to this turn.';
      if(lower.includes('handoff precheck'))return 'I verified my handoff is ready.';
      if(lower.includes('crystal record'))return 'I recorded the useful parts of this run for future reuse.';
      if(lower.includes('crystal reuse'))return 'I checked whether a prior successful run could be safely reused here.';
      if(lower.includes('task envelope'))return 'I wrapped the request in a bounded task envelope.';
      if(lower.includes('context files'))return 'I loaded the selected context files for this run.';
      return text||`I finished using ${tool||'a governed BEAST tool'}.`;
    }
    if(type==='agent_reasoning'){
      if(lower.includes('provider stream'))return 'I’m streaming my response now.';
      if(lower.includes('action ir recovery'))return 'I’m trying to recover a reviewable edit plan from my draft.';
      if(lower.includes('implementation planning'))return 'I’m planning the implementation against the selected files.';
      if(lower.includes('repository observation'))return 'I’m inspecting the repository context first.';
      if(lower.includes('operating mode:'))return text;
      return `I’m working through ${text.charAt(0).toLowerCase()}${text.slice(1)}.`;
    }
    if(type==='permission_request')return item.state==='failed'?`I paused because the extra capability request was declined.`:`You approved the extra governed capability, so I’m continuing with that boundary.`;
    if(type==='model_output')return `I finished drafting; now I’m checking what kind of result I can safely return.`;
    if(type==='verification')return `I checked the proposed changes: ${text}`;
    if(type==='command_request')return `I’m ready to run an isolated check if you approve it: ${command||text}`;
    if(type==='command_call')return `I’m running an isolated check now: ${command||text}`;
    if(type==='command_result')return `The isolated check ${item.state==='failed'?'failed':'finished'}: ${command||text}`;
    if(type==='context_search')return `I’m searching for the extra context the agent asked for: ${text}`;
    if(type==='context_result')return item.state==='failed'?`I could not find matching context: ${text}`:`I found context candidates for review: ${text}`;
    if(type==='context_attach')return `I added this file to the next run’s context: ${text}`;
    if(type==='context_continue')return 'I’m continuing the same task with the expanded context.';
    if(type==='recovery_request')return text||'I need to repair the edit packet before it can become a SourcePlan.';
    if(type==='sourceplan')return `I prepared a governed SourcePlan for review.`;
    if(type==='agent_turn')return `I started the coding run with the selected workspace scope.`;
    return text;
  }
  function aiNarration(message) {
    if(message?.role!=='assistant'||message?.mode==='ask')return '';
    const explicit=Array.isArray(message?.narration)?message.narration.filter(Boolean):[];
    const rows=(Array.isArray(message?.turns)?message.turns:[]).map(aiNarrationSentence).filter(Boolean);
    const combined=[...explicit,...rows];
    if(!combined.length)return '';
    const unique=[];for(const row of combined){if(unique.at(-1)!==row)unique.push(row);}
    return `<section class="cortex-ai-narration" aria-label="Agent updates">${unique.slice(-5).map(row=>`<p>${escapeHtml(row)}</p>`).join('')}</section>`;
  }
  function aiTurns(message) {
    const rows=Array.isArray(message?.turns)?message.turns:[];if(!rows.length)return '';
    return `<details class="cortex-ai-turns" aria-label="Debug agent transcript"><summary><b>Debug transcript</b><small>${rows.length} typed event${rows.length===1?'':'s'}</small></summary><div>${rows.slice(-18).map(item=>`<p class="${escapeHtml(`${item.state||'active'} ${item.type||''}`)}"><i>${escapeHtml(item.type||item.kind||'event')}</i><span>${item.command?`<code>${escapeHtml(item.command)}</code>`:escapeHtml(item.text||'')}${item.authority?`<small>${escapeHtml(item.authority)}</small>`:''}</span></p>`).join('')}</div></details>`;
  }
  function aiActiveAgentRequests(message) {
    if(message?.role!=='assistant'||message?.mode==='ask'||message?.proposal?.operations?.length)return '';
    const rows=(Array.isArray(message?.turns)?message.turns:[]).filter(item=>['command_request','context_request'].includes(String(item.type||''))&&String(item.state||'active')!=='done').slice(-4);
    if(!rows.length)return '';
    return `<section class="cortex-ai-agent-requests"><header><b>Agent requests</b><small>non-mutating · approval gated</small></header>${rows.map(item=>{const type=String(item.type||'request');const command=String(item.command||'');const label=type==='command_request'?'Open governed terminal':'Find related context';const action=type==='command_request'?'agent-open-terminal':'agent-suggest-context';return `<p><i>${escapeHtml(type)}</i><span>${escapeHtml(command||item.text||'Agent request')}</span></p><button type="button" data-ai-action="${escapeHtml(action)}" ${command?`data-agent-command="${escapeHtml(command)}"`:''}><span>${escapeHtml(label)}</span><small>${escapeHtml(item.authority||'review before continuing')}</small></button>`;}).join('')}</section>`;
  }
  function aiDraftPreview(message) {
    const draft=message?.draftPreview;if(!draft?.chars||message?.proposal?.ready)return '';
    const files=Array.isArray(draft.files)?draft.files:[];const intents=Array.isArray(draft.intents)?draft.intents:[];
    return `<section class="cortex-ai-live-draft"><header><b>${message.streaming?'Live patch draft':'Uncompiled patch draft'}</b><small>${Number(draft.chars).toLocaleString()} chars · ${Number(draft.actions||0)} edit${Number(draft.actions||0)===1?'':'s'}</small></header>${files.length?`<div>${files.map(path=>`<span><img src="${iconFor(path,'file')}" alt=""><code>${escapeHtml(path)}</code></span>`).join('')}</div>`:'<p>Receiving structured edit fields from the model…</p>'}${intents.length?`<p>${escapeHtml(intents.at(-1))}</p>`:''}</section>`;
  }
  function aiChangeStats(operation) {
    const lines=value=>String(value||'').split('\n').length;const oldLines=operation.old?lines(operation.old):0;const newLines=operation.new?lines(operation.new):0;
    return `<em><ins>+${newLines}</ins><del>−${oldLines}</del></em>`;
  }
  function aiOperationPreview(operation) {
    if(!operation.old&&!operation.new)return '';
    const oldText=String(operation.old||'').slice(0,900);const newText=String(operation.new||'').slice(0,900);
    return `<details class="cortex-ai-edit-preview"><summary>Preview edit</summary><div>${oldText?`<pre class="removed"><span>BEFORE</span>${escapeHtml(oldText)}</pre>`:''}${newText?`<pre class="added"><span>AFTER</span>${escapeHtml(newText)}</pre>`:''}</div></details>`;
  }
  function aiIntelligenceCard(proposal) {
    const data=proposal?.intelligence;if(!data||typeof data!=='object'||!Object.keys(data).length)return '';
    const pathfinder=data.pathfinder||{};const quality=data.quality_cascade||{};const conductor=data.conductor||{};const dispatch=data.conductor_dispatch||{};const insight=data.insight_packet||{};const canon=data.canon||{};const handoff=data.provider_handoff||{};const recipes=Array.isArray(data.skill_recipes)?data.skill_recipes:[];const laziness=data.tool_laziness||{};
    const skipped=Array.isArray(laziness.tools_not_to_call)?laziness.tools_not_to_call:[];
    return `<section class="cortex-ai-intelligence"><header><span><b>Governed intelligence evidence</b><small>Advisory evidence; it cannot expand scope or apply edits.</small></span><span class="${canon.valid?'passed':'review'}">${canon.valid?'Canon valid':'Canon review'}</span></header><div class="cortex-ai-intelligence-grid"><p><b>Pathfinder</b><small>${escapeHtml(pathfinder.name||pathfinder.route_id||'route unavailable')}</small></p><p><b>Insight Compiler</b><small>${Number((insight.evidence||[]).length)} ranked local evidence item(s)</small></p><p><b>Quality Cascade</b><small>${escapeHtml(quality.status||'not run')}</small></p><p><b>Conductor</b><small>${escapeHtml(conductor.decision||conductor.execution_mode||'advisory')}</small></p><p><b>Dispatch</b><small>${escapeHtml(dispatch.stopped||'not dispatched')}${dispatch.artifact?.path?' · persisted':''}</small></p><p><b>Handoff</b><small>${escapeHtml(handoff.context_packet_id||'packet unavailable')}</small></p></div>${recipes.length?`<details><summary>Verified Skill Tree recipes (${recipes.length})</summary>${recipes.map(item=>`<p><b>${escapeHtml(item.name||item.skill_id)}</b><small>${escapeHtml(item.category||'skill')} · ${Math.round(Number(item.success_rate||0)*100)}% success · advisory only${item.description?` — ${escapeHtml(item.description)}`:''}</small></p>`).join('')}</details>`:''}${skipped.length?`<small class="cortex-ai-intelligence-note">Tool Laziness skipped: ${escapeHtml(skipped.map(item=>item.name||item).join(', '))}</small>`:''}</section>`;
  }
  function aiProposalCard(message) {
    const proposal=message?.proposal;if(!proposal?.operations?.length)return '';
    const files=Array.isArray(proposal.files)?proposal.files:[];const operations=proposal.operations.slice(0,6);
    const validation=proposal.validation||{};const validationStatus=String(validation.status||'');const validationLabel=validationStatus==='passed'?'Checks passed':validationStatus==='partial'?'Safety checks passed':validationStatus==='failed'?'Checks failed':'Not checked';
    const isolated=validation.isolated_verifiers||{};const verifierCommands=Array.isArray(isolated.commands)?isolated.commands.slice(0,3):[];
    const verifierSummary=isolated.status?`<section class="cortex-ai-verifiers"><header><b>Isolated verification</b><span class="${escapeHtml(isolated.status)}">${escapeHtml(isolated.status)}</span></header><div>${verifierCommands.map(item=>`<p><code>${escapeHtml(item.command||'verifier')}</code><small>${escapeHtml(item.status||'')}</small></p>`).join('')||'<p><code>No verifier command</code><small>skipped</small></p>'}</div></section>`:'';
    const requests=Array.isArray(proposal.requests)?proposal.requests.slice(0,5):[];
    const runnable=requests.some(item=>item.type==='run_verifier'||item.command);
    const contextable=requests.some(item=>item.type==='ask_for_context'||item.query);
    const addedContext=Array.isArray(BeastStore.get()?.aiCoding?.contextFiles)?BeastStore.get().aiCoding.contextFiles.length:0;
    const continueContext=contextable&&addedContext?'<button type="button" data-ai-action="agent-continue-context"><span>Continue with added context</span><small>rerun same task</small></button>':'';
    const requestSummary=requests.length?`<section class="cortex-ai-agent-requests"><header><b>Agent next actions</b><small>non-mutating · approval gated</small></header>${requests.map(item=>`<p><i>${escapeHtml(item.type||'request')}</i><span>${escapeHtml(item.command||item.query||item.intent||'Agent request')}</span></p>`).join('')}${contextable?'<button type="button" data-ai-action="agent-context"><span>Find requested context</span><small>review before adding</small></button>':''}${continueContext}${runnable?'<button type="button" data-ai-action="agent-verify"><span>Run requested checks</span><small>isolated verifier</small></button>':''}</section>`:'';
    return `<section class="cortex-ai-proposal ${proposal.ready?'ready':'blocked'}"><header><span><b>${proposal.ready?'Changes ready':'Draft not compiled'}</b><small>${proposal.operations.length} edit${proposal.operations.length===1?'':'s'} · ${files.length} file${files.length===1?'':'s'}</small></span><span class="cortex-ai-validation ${escapeHtml(validationStatus||'pending')}"><i>${validationStatus==='failed'?'!':validationStatus?'✓':'○'}</i>${escapeHtml(validationLabel)}${validation.check_count?` · ${Number(validation.check_count)}`:''}</span></header><div>${operations.map(item=>`<article><button type="button" data-ai-preview-path="${escapeHtml(item.path)}" title="Show highlighted hunks for ${escapeHtml(item.path)}"><img src="${iconFor(item.path,'file')}" alt=""><span><b>${escapeHtml(item.path)}</b><small>${escapeHtml(item.intent||item.op||'Proposed edit')}</small></span>${aiChangeStats(item)}</button>${aiOperationPreview(item)}</article>`).join('')}${proposal.operations.length>operations.length?`<p>+ ${proposal.operations.length-operations.length} more change${proposal.operations.length-operations.length===1?'':'s'}</p>`:''}</div>${requestSummary}${verifierSummary}${aiIntelligenceCard(proposal)}${proposal.planId?`<p class="cortex-ai-plan-id">Plan ${escapeHtml(proposal.planId)}</p>`:''}${proposal.ready?'<div class="cortex-ai-proposal-actions"><button type="button" class="cortex-ai-review-diff" data-ai-action="diff"><span class="cortex-ai-action-icon" aria-hidden="true">⌘</span><span><b>Inspect diff</b><small>Review every changed hunk</small></span></button><button type="button" class="cortex-ai-review-apply" data-ai-action="sourceplan"><span class="cortex-ai-action-icon" aria-hidden="true">✓</span><span><b>Review & approve</b><small>SourcePlan · approval required</small></span><i aria-hidden="true">→</i></button></div>':'<p>The selected file stayed attached. Retry this edit or select a narrower code range.</p>'}</section>`;
  }
  function aiRecoveryCard(message) {
    const recovery=message?.recovery;if(!recovery||typeof recovery!=='object')return '';
    const actions=Array.isArray(recovery.actions)?recovery.actions:[];
    return `<section class="cortex-ai-recovery" aria-label="Agent recovery"><header><span><b>${escapeHtml(recovery.title||'Recovery needed')}</b><small>${escapeHtml(recovery.message||'No files changed. Choose the next recovery step.')}</small></span><i>held</i></header><div>${actions.map(item=>`<button type="button" data-ai-action="${escapeHtml(item.id||'retry')}"><span>${escapeHtml(item.label||'Retry')}</span><small>${escapeHtml(item.detail||'continue safely')}</small></button>`).join('')||'<button type="button" data-ai-action="retry"><span>Retry</span><small>same request and context</small></button>'}</div></section>`;
  }
  function workspaceTextDialog(pageRoot, options = {}) {
    return new Promise(resolve => {
      const prior = pageRoot.querySelector('[data-workspace-dialog]');
      if (prior) prior.remove();
      const dialog = document.createElement('section');
      dialog.className = 'cortex-workspace-dialog';
      dialog.dataset.workspaceDialog = 'text';
      dialog.setAttribute('role','dialog');
      dialog.setAttribute('aria-modal','true');
      const title = String(options.title || 'Workspace input');
      dialog.innerHTML = `<form><header><b>${escapeHtml(title)}</b>${options.message?`<small>${escapeHtml(options.message)}</small>`:''}</header><input value="${escapeHtml(options.value || '')}" aria-label="${escapeHtml(title)}" autocomplete="off"><footer><button type="button" data-dialog-cancel>Cancel</button><button type="submit">${escapeHtml(options.confirmLabel || 'Continue')}</button></footer></form>`;
      pageRoot.append(dialog);
      const input = dialog.querySelector('input');
      const close = value => { dialog.remove(); resolve(value); };
      dialog.querySelector('[data-dialog-cancel]').addEventListener('click', () => close(null));
      dialog.addEventListener('keydown', event => { if (event.key === 'Escape') { event.preventDefault(); close(null); } });
      dialog.querySelector('form').addEventListener('submit', event => { event.preventDefault(); close(input.value.trim()); });
      requestAnimationFrame(() => { input.focus(); input.select(); });
    });
  }
  function workspaceConfirm(pageRoot, options = {}) {
    return new Promise(resolve => {
      const prior = pageRoot.querySelector('[data-workspace-dialog]');
      if (prior) prior.remove();
      const dialog = document.createElement('section');
      dialog.className = 'cortex-workspace-dialog confirm';
      dialog.dataset.workspaceDialog = 'confirm';
      dialog.setAttribute('role','alertdialog');
      dialog.setAttribute('aria-modal','true');
      dialog.innerHTML = `<form><header><b>${escapeHtml(options.title || 'Confirm action')}</b>${options.message?`<small>${escapeHtml(options.message)}</small>`:''}</header><footer><button type="button" data-dialog-cancel>${escapeHtml(options.cancelLabel || 'Cancel')}</button><button type="submit">${escapeHtml(options.confirmLabel || 'Confirm')}</button></footer></form>`;
      pageRoot.append(dialog);
      const close = value => { dialog.remove(); resolve(Boolean(value)); };
      dialog.querySelector('[data-dialog-cancel]').addEventListener('click', () => close(false));
      dialog.addEventListener('keydown', event => { if (event.key === 'Escape') { event.preventDefault(); close(false); } });
      dialog.querySelector('form').addEventListener('submit', event => { event.preventDefault(); close(true); });
      requestAnimationFrame(() => dialog.querySelector('[data-dialog-cancel]')?.focus());
    });
  }

  function buildTree(files) {
    const root = { name: '', path: '', type: 'directory', children: new Map() };
    for (const file of files) {
      const parts = file.path.split('/').filter(Boolean);
      let cursor = root;
      parts.forEach((part, index) => {
        const path = parts.slice(0, index + 1).join('/');
        if (!cursor.children.has(part)) cursor.children.set(part, { name: part, path, type: index === parts.length - 1 ? file.type : 'directory', size: index === parts.length - 1 ? file.size : '', children: new Map() });
        cursor = cursor.children.get(part);
      });
    }
    return root;
  }

  function renderTreeNode(node, fragment, depth, state, query) {
    const entries = [...node.children.values()].sort((a, b) => (a.type === b.type ? a.name.localeCompare(b.name) : a.type === 'directory' ? -1 : 1));
    for (const item of entries) {
      const hasMatch = !query || item.path.toLowerCase().includes(query) || [...item.children.values()].some(child => child.path.toLowerCase().includes(query));
      if (!hasMatch) continue;
      const row = document.createElement('button'); row.type = 'button'; row.className = `beast-file-row ${item.type === 'directory' ? 'folder' : ''}`;
      row.style.setProperty('--tree-depth', depth);
      if (item.type === 'directory') row.dataset.folderPath = item.path; else row.dataset.filePath = item.path;
      if (state.editor.activePath === item.path) row.classList.add('active');
      const collapsed = state.editor.collapsedFolders.includes(item.path);
      const workspaceFolder=depth===0&&item.name.startsWith('@')?(state.workspace.roots||[]).find(folder=>`@${folder.id}`===item.name):null;
      const label=workspaceFolder?.name||item.name;
      const detail=workspaceFolder?workspaceFolder.path:(item.type === 'directory' ? item.path : fileName(item.path));
      row.innerHTML = `<span class="beast-tree-caret">${item.type === 'directory' ? (collapsed ? '›' : '⌄') : ''}</span><img src="${iconFor(item.path, item.type)}" alt=""><span class="beast-file-copy"><strong>${escapeHtml(label)}</strong><small>${escapeHtml(detail)}</small></span><em>${formatSize(item.size)}</em>`;
      fragment.append(row);
      if (item.type === 'directory' && !collapsed) renderTreeNode(item, fragment, depth + 1, state, query);
    }
  }

  function template() {
    const root = document.createElement('div');
    root.className = 'beast-page beast-workspace-page phase2-workspace';
    root.innerHTML = `
      <header class="beast-page-head">
        <div><h2>Editor Cortex</h2><div class="sub">MULTI-TAB MONACO // PERSISTENT BUFFERS // GOVERNED MUTATIONS</div></div>
        <div class="beast-page-actions"><button class="beast-button secondary" data-workspace-action="choose">Choose Folder</button><button class="beast-button secondary" data-workspace-action="add-folder">Add Folder</button><button class="beast-button" data-workspace-action="refresh">Refresh Index</button></div>
      </header>
      <section class="beast-workspace-toolbar beast-card wide cortex-toolbar">
        <div class="cortex-root-block">
          <img src="${BeastAssets.icon('workspace')}" alt="">
          <div class="cortex-root"><span class="tiny">ACTIVE WORKSPACE</span><strong data-workspace-root>No workspace selected</strong><div class="cortex-workspace-folders" data-workspace-folders></div></div>
          <div class="beast-workspace-state"><span class="beast-pill" data-workspace-count>0 files</span><span class="beast-pill" data-model-count>0 models</span><span class="beast-pill" data-workspace-dirty>clean</span></div>
        </div>
        <div class="cortex-intelligence" aria-label="BEAST intelligence plane">
          <button type="button" class="cortex-intel-node" data-intel-action="context" title="Open the BEAST copilot with Code Cortex context">
            <img src="${BeastAssets.icon('context')}" alt=""><span><small>CODE CORTEX</small><strong data-intel-context>ACTIVE FILE</strong></span><i data-intel-context-detail>scope ready</i>
          </button>
          <button type="button" class="cortex-intel-node crystal" data-intel-action="crystal" title="Inspect crystallised compute reuse">
            <img src="${BeastAssets.icon('crystal')}" alt=""><span><small>CRYSTAL REUSE</small><strong data-intel-crystal>ARMED</strong></span><i data-intel-crystal-detail>preflight first</i>
          </button>
          <button type="button" class="cortex-intel-node" data-intel-action="governance" title="Open the governed SourcePlan">
            <img src="${BeastAssets.icon('trust-core')}" alt=""><span><small>GOVERNANCE</small><strong data-intel-governance>ENFORCED</strong></span><i data-intel-governance-detail>review before write</i>
          </button>
          <button type="button" class="cortex-intel-node" data-intel-action="agent" title="Open the BEAST coding agent">
            <img src="${BeastAssets.icon('agent-premium')}" alt=""><span><small>CODING AGENT</small><strong data-intel-agent>STANDING BY</strong></span><i data-intel-agent-detail>Ctrl I</i>
          </button>
        </div>
        <div class="cortex-view-controls" role="group" aria-label="Workbench zoom">
          <button type="button" data-workspace-action="zoom-out" title="Zoom out (Ctrl+-)" aria-label="Zoom out">−</button>
          <button type="button" data-workspace-action="zoom-reset" title="Reset zoom (Ctrl+0)" data-zoom-label>100%</button>
          <button type="button" data-workspace-action="zoom-in" title="Zoom in (Ctrl++)" aria-label="Zoom in">+</button>
        </div>
      </section>
      <div class="cortex-layout">
        <aside class="beast-card cortex-explorer">
          <div class="cortex-tabbar" aria-label="Workspace views"><button data-explorer-tab="files" class="active" aria-label="Files" title="Files"><img src="${BeastAssets.icon('files')}" alt=""></button><button data-explorer-tab="outline" aria-label="Outline" title="Outline"><img src="${BeastAssets.icon('map')}" alt=""></button><button data-explorer-tab="recent" aria-label="Recent files" title="Recent files"><img src="${BeastAssets.icon('evidence')}" alt=""></button><button data-explorer-tab="changes" aria-label="Source Control" title="Source Control (Ctrl Shift G)"><img src="${BeastAssets.icon('source')}" alt=""></button><button data-explorer-tab="search" aria-label="Search" title="Search"><img src="${BeastAssets.icon('context')}" alt=""></button></div>
          <div class="cortex-explorer-tools">
            <input class="beast-filter" data-file-filter placeholder="Filter workspace…" autocomplete="off">
            <button title="New file" data-file-op="new-file">＋</button><button title="New folder" data-file-op="new-folder">⌑</button><button title="Toggle tree/flat" data-file-op="toggle-mode">≋</button>
          </div>
          <div class="beast-file-list" data-explorer-body role="listbox" aria-label="Workspace explorer"></div>
          <footer class="cortex-explorer-foot"><span data-explorer-status>idle</span><div><button data-file-op="git-refresh">GIT</button><button data-file-op="git-stage">+</button><button data-file-op="git-unstage">−</button><button data-file-op="git-discard">↶</button><button data-file-op="rename">REN</button><button data-file-op="delete">DEL</button></div></footer>
        </aside>
        <section class="beast-card cortex-editor wide">
          <div class="cortex-editor-top">
            <div class="cortex-tabs legacy-editor-tabs" data-editor-tabs></div><div class="beast-workbench-indicator"><b data-workbench-group-count>1 PANE</b><span>PHYSICAL GROUP LAYOUT</span></div>
            <div class="cortex-editor-tools"><span class="cortex-git-toolbar-label hidden" data-git-diff-toolbar>READ-ONLY SOURCE CONTROL DIFF</span><button data-editor-action="split">Split</button><button data-editor-action="split-vertical" title="Split vertically">Split V</button><button data-editor-action="move-group" title="Move active editor to next group">Move</button><button data-editor-action="close-group" title="Merge active group into its sibling">Merge</button><button data-editor-action="pin" title="Pin or unpin the active editor">Pin</button><button data-editor-action="reopen" title="Reopen the most recently closed editor">Reopen</button><button data-compare-action="disk" title="Compare active buffer with disk">Compare</button><button data-editor-action="revert">Revert</button><button data-editor-action="save-remote">Save Remote</button><button data-editor-action="assist">Ask AI</button><button class="hot" data-editor-action="draft">Draft SourcePlan</button></div>
          </div>
          <nav class="cortex-breadcrumbs" data-editor-breadcrumbs aria-label="Editor breadcrumbs"><span>No file open</span></nav>
          <div class="cortex-editor-safety-banner hidden" data-editor-safety-banner></div>
          <div class="cortex-editor-stage" data-editor-stage>
            <div class="cortex-editor-text-surface" data-editor-text-surface>
              <div data-editor-workbench></div>
              <div class="cortex-editor-pane" data-editor-host></div>
              <textarea class="beast-editor-fallback hidden" data-editor-fallback spellcheck="false" aria-label="BEAST editor"></textarea>
              <div class="cortex-editor-pane hidden" data-editor-split-host></div>
              <textarea class="beast-editor-fallback hidden" data-editor-split-fallback spellcheck="false" aria-label="BEAST split editor"></textarea>
            </div>
            <section class="cortex-editor-safety-workbench hidden" data-editor-safety-workbench aria-label="Large file and binary safety mode"></section>
            <section class="beast-notebook-workbench hidden" data-notebook-workbench aria-label="Notebook editor"></section>
            <section class="cortex-compare-workbench hidden" data-compare-workbench aria-label="Compare editors">
              <header><span><small data-compare-meta>COMPARE EDITORS</small><strong data-compare-title>Document comparison</strong></span><div><button type="button" data-compare-action="previous" title="Previous change">↑</button><span data-compare-position>No changes</span><button type="button" data-compare-action="next" title="Next change">↓</button><button type="button" data-compare-action="toggle-view">Inline</button><button type="button" data-compare-action="file">Compare file</button><button type="button" data-compare-action="sourceplan">SourcePlan</button><button type="button" data-compare-action="accept-left">Use left</button><button type="button" data-compare-action="accept-right">Use right</button><button type="button" data-compare-action="close" aria-label="Close compare editor">×</button></div></header>
              <div class="cortex-compare-host" data-compare-host></div>
              <pre class="cortex-compare-fallback hidden" data-compare-fallback></pre>
            </section>
            <section class="cortex-git-diff hidden" data-git-diff-workbench aria-label="Source control diff">
              <header><span><small data-git-diff-mode>WORKTREE</small><strong data-git-diff-title>Change preview</strong></span><div><button type="button" class="hidden" data-git-diff-action="sourceplan">Full review</button><button type="button" data-git-diff-action="stage">Stage</button><button type="button" data-git-diff-action="unstage">Unstage</button><button type="button" data-git-diff-action="close" aria-label="Close change diff">×</button></div></header>
              <div class="cortex-git-diff-host" data-git-diff-host></div>
              <pre class="cortex-git-diff-fallback hidden" data-git-diff-fallback></pre>
              <aside class="cortex-git-hunks hidden" data-git-hunks></aside>
              <aside class="cortex-git-conflict hidden" data-git-conflict></aside>
            </section>
            <div class="cortex-empty" data-editor-empty>
              <div class="cortex-empty-orbit"><img src="${BeastAssets.icon('context')}" alt=""></div>
              <small>BEAST CODE CORTEX</small><strong>Build with the whole system in view</strong>
              <span>Open a file for Monaco intelligence, or brief the governed coding agent against the repository.</span>
              <div class="cortex-empty-actions"><button type="button" data-empty-action="choose">Open workspace</button><button type="button" data-empty-action="agent">Brief the agent <kbd>Ctrl I</kbd></button></div>
              <div class="cortex-empty-trust"><i></i> Context-aware <i></i> Reuse-first <i></i> SourcePlan governed</div>
            </div>
          </div>
          <footer class="cortex-statusbar"><button type="button" data-status-action="changes" aria-label="Open Source Control"><span data-git-branch>no repository</span></button><span data-editor-status>No active buffer.</span><span data-editor-position>Ln 1, Col 1</span><span data-layout-status></span></footer>
        </section>
        <aside class="beast-card cortex-ai-panel" data-ai-panel>
          <header class="cortex-ai-head">
            <div class="cortex-ai-identity"><span class="cortex-ai-avatar"><img src="${BeastAssets.icon('agent-premium')}" alt=""></span><span><strong>BEAST Agent</strong><small>Search, read, use skills, verify, and propose governed changes</small><em data-ai-session>New session</em></span></div>
            <div class="cortex-ai-head-actions"><button type="button" data-ai-action="expand" data-ai-expand aria-pressed="false" title="Expand BEAST Agent"><span data-ai-expand-label>Focus</span></button><button type="button" data-ai-action="close" aria-label="Close BEAST Agent" title="Close BEAST Agent">×</button></div>
          </header>
          <div class="cortex-ai-modes" role="group" aria-label="BEAST Agent mode">
            <button type="button" data-ai-mode="ask"><img src="${BeastAssets.icon('chat')}" alt=""><span><b>Ask</b><small>Explain</small></span></button>
            <button type="button" data-ai-mode="edit"><img src="${BeastAssets.icon('source')}" alt=""><span><b>Edit</b><small>Propose</small></span></button>
            <button type="button" data-ai-mode="agent"><img src="${BeastAssets.icon('orchestrator')}" alt=""><span><b>Agent</b><small>Implement</small></span></button>
            <button type="button" data-ai-mode="review"><img src="${BeastAssets.icon('review')}" alt=""><span><b>Review</b><small>Critique</small></span></button>
          </div>
          <section class="cortex-ai-objective" aria-label="Current objective and success criteria">
            <header><span>Objective</span><b data-ai-objective-mode>Ask</b></header>
            <p data-ai-objective>Describe the outcome BEAST should achieve.</p>
            <div class="cortex-ai-success-grid">
              <span data-ai-success-plan>Plan: waiting</span>
              <span data-ai-success-tools>Tools: governed</span>
              <span data-ai-success-verify>Verify: waiting</span>
              <span data-ai-success-sourceplan>SourcePlan: pending</span>
            </div>
          </section>
          <details class="cortex-ai-context">
            <summary><span><b>Context</b><small data-ai-context-count>Active file</small></span><span class="cortex-ai-compute" data-ai-compute><img src="${BeastAssets.icon('crystal')}" alt=""><strong data-ai-crystal>Reuse ready</strong><i data-ai-crystal-confidence>Ready</i></span></summary>
            <div class="cortex-ai-context-body"><div class="cortex-ai-context-actions"><button type="button" data-ai-action="active-file">Add active file</button><button type="button" data-ai-action="selection">Add selection</button><button type="button" data-ai-action="context-file">Add file…</button><button type="button" data-ai-action="suggest-context">Suggest context</button></div><div class="cortex-ai-chips" data-ai-context></div><div class="cortex-ai-context-suggestions" data-ai-context-suggestions></div><section class="phase5-context-manifest"><header><b>Durable Context Manifest</b><span data-phase5-context-summary>no durable run</span></header><div data-phase5-context-list><div class="cortex-empty-list">Start or select an AgentRun to review durable context.</div></div></section><p data-ai-crystal-detail>Prior verified work is checked before inference.</p><p class="cortex-ai-compute-summary" data-ai-compute-summary>Context economics will appear when a run starts.</p></div>
          </details>
          <section class="cortex-ai-ops-console" aria-label="Live agent operations console">
            <article><b>Plan</b><span data-ai-console-plan>waiting</span></article>
            <article><b>Timeline</b><span data-ai-console-timeline>0 events</span></article>
            <article><b>Tools & approvals</b><span data-ai-console-tools>governed</span></article>
            <article><b>Worktree</b><span data-ai-console-worktree>operator workspace protected</span></article>
            <article><b>Verification</b><span data-ai-console-verify>waiting</span></article>
            <article><b>Budget</b><span data-ai-console-budget>120k tokens · governed</span></article>
          </section>
          <div class="cortex-ai-conversation"><div class="cortex-ai-messages" data-ai-messages aria-live="polite" aria-label="BEAST Agent conversation"></div><button type="button" class="cortex-ai-jump-latest hidden" data-ai-action="jump-latest" aria-label="Jump to latest BEAST Agent output">Jump to latest <span data-ai-unread-count></span>↓</button></div>
          <details class="cortex-ai-trace"><summary>Run details <span data-ai-trace-count>0</span></summary><div data-ai-trace></div></details>
          <div class="cortex-ai-compose">
            <div class="cortex-ai-route"><label><span>Model</span><select data-ai-model aria-label="BEAST Agent model"><option value="">Select a model…</option></select></label><p data-ai-mode-description>Give BEAST a goal and review the proposed changes.</p></div>
            <div class="cortex-ai-prompt-shell"><textarea data-ai-prompt rows="4" aria-label="Message BEAST Agent" placeholder="Describe what you want to build or change…"></textarea><span><kbd>Enter</kbd> send · <kbd>Shift Enter</kbd> newline</span></div>
            <div class="cortex-ai-compose-actions"><span data-ai-status role="status" aria-live="polite">Ready</span><div><button type="button" class="beast-button secondary" data-ai-action="clear">New chat</button><button type="button" class="beast-button secondary hidden" data-ai-action="cancel">Stop</button><button type="button" class="beast-button secondary" data-ai-action="worktree-agent" title="Create an isolated Git worktree, then run the coding agent there">Isolate</button><button type="button" class="beast-button hot" data-ai-action="send"><span data-ai-send-label>Run agent</span> <span aria-hidden="true">↗</span></button></div></div>
          </div>
          <button type="button" class="beast-button hot cortex-ai-sourceplan hidden" data-ai-action="sourceplan"><img src="${BeastAssets.icon('trust-core')}" alt=""><span><b>Review proposed changes</b><small>Open the governed SourcePlan</small></span><i>→</i></button>
        </aside>
        <div class="cortex-pane-resizer explorer" data-pane-resizer="explorer" role="separator" aria-orientation="vertical" aria-label="Resize Explorer" tabindex="0"></div>
        <div class="cortex-pane-resizer ai" data-pane-resizer="ai" role="separator" aria-orientation="vertical" aria-label="Resize Pair Programmer" tabindex="0"></div>
      </div>`;
    return root;
  }

  async function renderer({ signal }) {
    const root = template();
    const explorer = root.querySelector('[data-explorer-body]');
    const filter = root.querySelector('[data-file-filter]');
    const workbenchHost = root.querySelector('[data-editor-workbench]');
    const editorHost = root.querySelector('[data-editor-host]');
    const fallback = root.querySelector('[data-editor-fallback]');
    const splitHost = root.querySelector('[data-editor-split-host]');
    const splitFallback = root.querySelector('[data-editor-split-fallback]');
    let disposed = false;
    let durableConsoleKey = '';
    let durableConsoleTimer = null;
    let lastExplorerKey = '';
    let lastTabsKey = '';
    let lastAiMessagesKey = '';
    let lastAiContextKey = '';
    let lastAiModelsKey = '';
    let lastNotebookKey = '';
    let gitState={status:'idle',branch:'',branchName:'',branches:[],changes:[],counts:{staged:0,unstaged:0,conflicts:0},diffStat:'',stagedDiffStat:'',error:'',message:'',updatedAt:0};
    let selectedGitRootId='';
    let gitCommitMessage='';
    let gitNewBranchOpen=false;let gitNewBranchName='';
    let gitDetails={history:[],remotes:[],loading:false,rebaseBase:'',cherryPick:'',error:''};
    let gitDiffState={status:'idle',path:'',originalPath:'',mode:'worktree',originalText:'',modifiedText:'',patch:'',error:'',truncated:false};
    let gitHunksState={status:'idle',path:'',mode:'worktree',hunks:[],error:''};let gitConflictState={status:'idle',path:'',baseText:'',currentText:'',incomingText:'',resultText:'',digest:'',regions:0,error:''};
    let gitDiffCleanup=null;let gitDiffKey='';let gitDiffMountToken=0;
    let aiPreviewPlanId='';
    let aiFollowOutput=true;let aiUnreadOutput=0;let aiScrollFrame=0;let visualWorkload='';
    let searchState={status:'idle',query:'',replacement:'',results:[],preview:[],total:0,error:'',message:'Search the active workspace.'};
    const layout=root.querySelector('.cortex-layout');
    const layoutStorageKey='beast.workspace.layout.v1';const zoomStorageKey='beast.desktop.zoom-level.v1';
    let zoomLevel=0;let resizeCleanup=null;

    function savedLayout(){try{return JSON.parse(localStorage.getItem(layoutStorageKey)||'{}')||{};}catch(_){return {};}}
    function saveLayout(){try{localStorage.setItem(layoutStorageKey,JSON.stringify({explorer:Number.parseInt(layout.style.getPropertyValue('--cortex-explorer-width'),10)||205,ai:Number.parseInt(layout.style.getPropertyValue('--cortex-ai-width'),10)||430}));}catch(_){}}
    function setPaneWidth(pane,width,{persist=true}={}){const max=Math.max(pane==='ai'?520:360,Math.floor(window.innerWidth*(pane==='ai'?.72:.48)));const bounds=pane==='ai'?[280,max]:[160,max];const value=Math.max(bounds[0],Math.min(bounds[1],Math.round(Number(width)||bounds[0])));layout.style.setProperty(pane==='ai'?'--cortex-ai-width':'--cortex-explorer-width',`${value}px`);if(persist)saveLayout();}
    function updateZoomControls(){const label=root.querySelector('[data-zoom-label]');if(label)label.textContent=`${Math.round(Math.pow(1.2,zoomLevel)*100)}%`;}
    async function applyZoom(level,{reset=false}={}){if(!window.beastDesktop?.setZoom)return;const result=reset?await window.beastDesktop.resetZoom():await window.beastDesktop.setZoom(level);zoomLevel=Number(result?.level)||0;try{localStorage.setItem(zoomStorageKey,String(zoomLevel));}catch(_){}updateZoomControls();}
    async function restoreViewPreferences(){const saved=savedLayout();if(saved.explorer)setPaneWidth('explorer',saved.explorer,{persist:false});if(saved.ai)setPaneWidth('ai',saved.ai,{persist:false});const stored=Number(localStorage.getItem(zoomStorageKey));try{const result=Number.isFinite(stored)&&stored!==0?await window.beastDesktop?.setZoom(stored):await window.beastDesktop?.getZoom?.();zoomLevel=Number(result?.level)||0;}catch(_){zoomLevel=0;}updateZoomControls();}
    function beginPaneResize(event,pane){if(window.innerWidth<=900||(pane==='ai'&&(!layout.classList.contains('ai-open')||layout.classList.contains('ai-focus'))))return;event.preventDefault();const pointerId=event.pointerId;const rect=layout.getBoundingClientRect();const resizer=event.currentTarget;resizer.setPointerCapture?.(pointerId);root.classList.add('resizing-pane');const move=moveEvent=>{if(moveEvent.pointerId===pointerId)setPaneWidth(pane,pane==='ai'?rect.right-moveEvent.clientX:moveEvent.clientX-rect.left,{persist:false});};const finish=finishEvent=>{if(finishEvent.pointerId!==pointerId)return;resizer.removeEventListener('pointermove',move);resizer.removeEventListener('pointerup',finish);resizer.removeEventListener('pointercancel',finish);root.classList.remove('resizing-pane');saveLayout();resizeCleanup=null;};resizeCleanup=()=>finish({pointerId});resizer.addEventListener('pointermove',move);resizer.addEventListener('pointerup',finish);resizer.addEventListener('pointercancel',finish);}
    root.querySelectorAll('[data-pane-resizer]').forEach(resizer=>{resizer.addEventListener('pointerdown',event=>beginPaneResize(event,resizer.dataset.paneResizer));resizer.addEventListener('keydown',event=>{const pane=resizer.dataset.paneResizer;if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const current=Number.parseInt(layout.style.getPropertyValue(pane==='ai'?'--cortex-ai-width':'--cortex-explorer-width'),10)||(pane==='ai'?430:205);const direction=event.key==='ArrowLeft'?-1:event.key==='ArrowRight'?1:0;const target=event.key==='Home'?(pane==='ai'?280:160):event.key==='End'?(pane==='ai'?Math.floor(window.innerWidth*.72):Math.floor(window.innerWidth*.48)):current+(pane==='ai'?-direction:direction)*20;setPaneWidth(pane,target);});});

    function aiAtBottom(host) { return host.scrollHeight-host.scrollTop-host.clientHeight<28; }
    function syncAiFollowControl() {
      const button=root.querySelector('[data-ai-action="jump-latest"]');if(!button)return;
      button.classList.toggle('hidden',aiFollowOutput);
      const count=button.querySelector('[data-ai-unread-count]');if(count)count.textContent=aiUnreadOutput>1?`(${aiUnreadOutput})`:'';
    }
    function jumpToLatestAiOutput() {
      const host=root.querySelector('[data-ai-messages]');if(!host)return;
      aiFollowOutput=true;aiUnreadOutput=0;host.scrollTop=host.scrollHeight;syncAiFollowControl();
    }
    root.querySelector('[data-ai-messages]').addEventListener('scroll',event=>{
      const host=event.currentTarget;const wasFollowing=aiFollowOutput;aiFollowOutput=aiAtBottom(host);
      if(aiFollowOutput&&!wasFollowing)aiUnreadOutput=0;
      syncAiFollowControl();
    },{passive:true});

    function gitRootPayload() { if(selectedGitRootId)return {rootId:selectedGitRootId};const active=BeastStore.get().editor.activePath;const folder=BeastDesktopBridge.workspaceFolderForPath?.(active)?.folder;return folder?.id?{rootId:folder.id}:{}; }
    async function refreshGit() {
      if (!window.beastDesktop?.workspaceGitStatus) { gitState={...gitState,status:'error',error:'Git status is available only in the BEAST desktop shell.'};renderExplorer(BeastStore.get());return; }
      gitState={...gitState,status:'loading',error:''};renderExplorer(BeastStore.get());
      try { const result=await window.beastDesktop.workspaceGitStatus(gitRootPayload());gitState={status:result.ok?'ready':'error',branch:result.branch||'',branchName:result.branchName||'',branches:result.branches||[],changes:result.changes||[],counts:result.counts||{staged:0,unstaged:0,conflicts:0},diffStat:result.diffStat||'',stagedDiffStat:result.stagedDiffStat||'',error:result.error||'',message:gitState.message||'',updatedAt:Date.now()}; }
      catch(error) { gitState={...gitState,status:'error',error:String(error.message||error),updatedAt:Date.now()}; }
      patch(BeastStore.get());
    }
    async function refreshGitDetails(){if(!window.beastDesktop?.workspaceGitHistory)return;gitDetails={...gitDetails,loading:true,error:''};renderExplorer(BeastStore.get());try{const scope=gitRootPayload();const [history,remotes]=await Promise.all([window.beastDesktop.workspaceGitHistory({...scope,limit:40}),window.beastDesktop.workspaceGitRemotes(scope)]);gitDetails={...gitDetails,history:history?.commits||[],remotes:remotes?.remotes||[],loading:false,error:''};}catch(error){gitDetails={...gitDetails,loading:false,error:String(error.message||error)};}renderExplorer(BeastStore.get());}
    async function runGitOperation(action){if(!window.beastDesktop?.workspaceGitOperation)throw new Error('Advanced Git operations are available only in the BEAST desktop shell.');const payload={...gitRootPayload(),action,remote:gitDetails.remotes[0]?.name||'origin',base:gitDetails.rebaseBase,revision:gitDetails.cherryPick};const result=await window.beastDesktop.workspaceGitOperation(payload);if(!result?.ok)throw new Error(result?.error||result?.stderr||`Git ${action} failed.`);gitState={...gitState,message:`${action.replaceAll('-',' ')} complete · ${result.receipt?.id||'verified'}`,error:''};BeastStore.addLedger(`Git ${action} · ${result.receipt?.id||''}`);await Promise.all([refreshGit(),refreshGitDetails()]);}
    async function runGitAction(action,path='') {
      if(!window.beastDesktop?.workspaceGitAction)throw new Error('Source Control is available only in the BEAST desktop shell.');
      const result=await window.beastDesktop.workspaceGitAction({...gitRootPayload(),action,path:BeastDesktopBridge.workspaceFolderForPath?.(path)?.path||path});if(!result?.ok)throw new Error(result?.error||result?.stderr||`Git ${action} failed.`);
      gitState={...gitState,message:`${action.replaceAll('-',' ')} complete · ${result.receipt?.id||'verified'}`,error:''};BeastStore.addLedger(`Git ${action}${path?`: ${path}`:''} · ${result.receipt?.id||''}`);await refreshGit();return result;
    }
    async function openGitDiff(path,mode='worktree',originalPath='') {
      if(!window.beastDesktop?.workspaceGitDiff)return;
      gitDiffState={status:'loading',path,originalPath,mode,originalText:'',modifiedText:'',patch:'',error:'',truncated:false};patch(BeastStore.get());
      try{const target=BeastDesktopBridge.workspaceFolderForPath?.(path)||{path};const payload={...gitRootPayload(),rootId:target.folder?.id||gitRootPayload().rootId,path:target.path,mode,originalPath};const [result,hunks]=await Promise.all([window.beastDesktop.workspaceGitDiff(payload),window.beastDesktop.workspaceGitHunks?.(payload)]);if(!result?.ok)throw new Error(result?.error||'Git diff preview failed.');gitDiffState={status:'ready',...result,error:''};gitHunksState={status:hunks?.ok?'ready':'error',path,mode,hunks:hunks?.hunks||[],error:hunks?.error||''};gitConflictState={status:'idle',path:'',baseText:'',currentText:'',incomingText:'',resultText:'',digest:'',regions:0,error:''};}
      catch(error){gitDiffState={...gitDiffState,status:'error',error:String(error.message||error)};}
      patch(BeastStore.get());
    }
    async function openGitConflict(path){if(!window.beastDesktop?.workspaceGitConflict)throw new Error('Conflict resolution is available only in the BEAST desktop shell.');gitConflictState={status:'loading',path,baseText:'',currentText:'',incomingText:'',resultText:'',digest:'',regions:0,error:''};gitDiffState={status:'loading',path,originalPath:'',mode:'conflict',originalText:'',modifiedText:'',patch:'',error:'',truncated:false};patch(BeastStore.get());try{const target=BeastDesktopBridge.workspaceFolderForPath?.(path)||{path};const result=await window.beastDesktop.workspaceGitConflict({...gitRootPayload(),rootId:target.folder?.id||gitRootPayload().rootId,path:target.path});if(!result?.ok)throw new Error(result?.error||'Unable to load conflict.');gitConflictState={status:'ready',...result,error:''};gitDiffState={status:'ready',path,originalPath:'',mode:'conflict',originalText:result.currentText||result.baseText||'',modifiedText:result.resultText||'',patch:'',error:'',truncated:Boolean(result.truncated)};}catch(error){gitConflictState={...gitConflictState,status:'error',error:String(error.message||error)};gitDiffState={...gitDiffState,status:'error',error:String(error.message||error)};}patch(BeastStore.get());}
    async function runGitHunkAction(action,hunkId){const target=BeastDesktopBridge.workspaceFolderForPath?.(gitHunksState.path)||{path:gitHunksState.path};const result=await window.beastDesktop.workspaceGitHunkAction({...gitRootPayload(),rootId:target.folder?.id||gitRootPayload().rootId,action,path:target.path,hunkId});if(!result?.ok)throw new Error(result?.error||result?.stderr||'Hunk operation failed.');await openGitDiff(gitHunksState.path,action==='stage'?'staged':'worktree',gitDiffState.originalPath);await refreshGit();}
    async function resolveGitConflict(){const text=root.querySelector('[data-git-conflict-result]')?.value??gitConflictState.resultText;const target=BeastDesktopBridge.workspaceFolderForPath?.(gitConflictState.path)||{path:gitConflictState.path};const result=await window.beastDesktop.workspaceGitResolve({...gitRootPayload(),rootId:target.folder?.id||gitRootPayload().rootId,path:target.path,content:text,expectedDigest:gitConflictState.digest});if(!result?.ok)throw new Error(result?.error||result?.stderr||'Conflict resolution failed.');BeastStore.addLedger(`Git conflict resolved: ${gitConflictState.path} · ${result.receipt?.id||''}`);closeGitDiff();await refreshGit();}
    async function openAiDiff(plan,preferredPath='') {
      const operations=Array.isArray(plan?.operations)?plan.operations:[];const paths=[...new Set(operations.map(item=>String(item.path||'')).filter(Boolean))];const path=paths.includes(preferredPath)?preferredPath:paths[0];
      if(!path)return;
      gitDiffState={status:'loading',path,originalPath:'',mode:'ai',planId:String(plan.plan_id||''),originalText:'',modifiedText:'',patch:'',error:'',truncated:false};patch(BeastStore.get());
      try{
        const active=BeastEditorCortex.getActive()||{};const loaded=active.path===path?{text:String(active.text||'')}:await BeastDesktopBridge.loadFile(path,{maxChars:2000000,signal});if(!loaded)throw new Error(`Could not read ${path} for the AI diff.`);
        const originalText=String(loaded.text||'');let modifiedText=originalText;let applied=0;
        for(const operation of operations.filter(item=>String(item.path||'')===path)){
          const kind=String(operation.op||operation.type||'replace_exact');const oldText=String(operation.old??operation.old_text??operation.before??'');const newText=String(operation.new??operation.new_text??operation.after??operation.content??'');
          if(kind==='create_or_replace'){modifiedText=newText;applied+=1;continue;}
          if(kind==='append'){modifiedText=`${modifiedText}${newText}`;applied+=1;continue;}
          if(!oldText||modifiedText.split(oldText).length!==2)throw new Error(`Edit ${operation.op_id||operation.id||'?'} no longer has one exact hunk in ${path}.`);
          modifiedText=modifiedText.replace(oldText,newText);applied+=1;
        }
        if(!applied||modifiedText===originalText)throw new Error(`The proposal contains no visible text change for ${path}.`);
        gitDiffState={...gitDiffState,status:'ready',originalText,modifiedText,patch:BeastDesktopBridge.localDiff(originalText,modifiedText),error:''};
      }catch(error){gitDiffState={...gitDiffState,status:'error',error:String(error.message||error)};}
      patch(BeastStore.get());
    }
    async function commitGit() {
      const message=gitCommitMessage.trim();if(!message){gitState={...gitState,error:'Enter a commit message before committing.'};renderExplorer(BeastStore.get());return;}
      try{const result=await window.beastDesktop.workspaceGitCommit({...gitRootPayload(),message});if(!result?.ok)throw new Error(result?.error||result?.stderr||'Git commit failed.');gitCommitMessage='';gitState={...gitState,error:'',message:`Commit created · ${result.receipt?.id||'verified'}`};BeastStore.addLedger(`Git commit · ${result.receipt?.id||''}`);await refreshGit();}
      catch(error){gitState={...gitState,error:String(error.message||error),message:''};renderExplorer(BeastStore.get());}
    }
    async function changeGitBranch(operation,name) {
      try{const result=await window.beastDesktop.workspaceGitBranch({...gitRootPayload(),operation,name});if(!result?.ok)throw new Error(result?.error||result?.stderr||`Unable to ${operation} branch.`);gitNewBranchOpen=false;gitNewBranchName='';gitState={...gitState,error:'',message:`Branch ${operation} complete · ${result.receipt?.id||'verified'}`};BeastStore.addLedger(`Git branch ${operation}: ${name} · ${result.receipt?.id||''}`);closeGitDiff();await refreshGit();}
      catch(error){gitState={...gitState,error:String(error.message||error),message:''};renderExplorer(BeastStore.get());}
    }
    function closeGitDiff() { gitDiffMountToken+=1;gitDiffCleanup?.();gitDiffCleanup=null;gitDiffKey='';gitDiffState={status:'idle',path:'',originalPath:'',mode:'worktree',originalText:'',modifiedText:'',patch:'',error:'',truncated:false};gitHunksState={status:'idle',path:'',mode:'worktree',hunks:[],error:''};gitConflictState={status:'idle',path:'',baseText:'',currentText:'',incomingText:'',resultText:'',digest:'',regions:0,error:''};patch(BeastStore.get()); }
    function renderGitDiff(state) {
      const workbench=root.querySelector('[data-git-diff-workbench]');const active=gitDiffState.status!=='idle';workbench.classList.toggle('hidden',!active);root.querySelector('.cortex-editor').classList.toggle('git-diff-active',active);root.querySelector('[data-git-diff-toolbar]').classList.toggle('hidden',!active);
      if(!active)return;
      const aiDiff=gitDiffState.mode==='ai';
      [editorHost,fallback,splitHost,splitFallback,root.querySelector('[data-notebook-workbench]'),root.querySelector('[data-editor-empty]')].forEach(node=>node?.classList.add('hidden'));
      root.querySelector('[data-git-diff-title]').textContent=gitDiffState.path||'Change preview';root.querySelector('[data-git-diff-mode]').textContent=`${aiDiff?'AI PROPOSAL · ORIGINAL ↔ PROPOSED':gitDiffState.mode==='staged'?'INDEX ↔ HEAD':'WORKTREE ↔ INDEX'}${gitDiffState.truncated?' · TRUNCATED':''}`;
      root.querySelector('[data-git-diff-toolbar]').textContent=aiDiff?'READ-ONLY AI HUNK PREVIEW':'READ-ONLY SOURCE CONTROL DIFF';root.querySelector('[data-editor-status]').textContent=aiDiff?'AI proposal diff · highlighted hunks · no files changed':`Git ${gitDiffState.mode} diff · read-only · workspace bounded`;
      root.querySelector('[data-git-diff-action="sourceplan"]').classList.toggle('hidden',!aiDiff);root.querySelector('[data-git-diff-action="stage"]').classList.toggle('hidden',aiDiff||gitDiffState.mode==='staged');root.querySelector('[data-git-diff-action="unstage"]').classList.toggle('hidden',aiDiff||gitDiffState.mode!=='staged');
      const hunks=root.querySelector('[data-git-hunks]');const conflict=root.querySelector('[data-git-conflict]');const showHunks=!aiDiff&&gitDiffState.mode!=='conflict'&&gitHunksState.status==='ready';hunks.classList.toggle('hidden',!showHunks);hunks.innerHTML=showHunks?`<header><b>PATCH HUNKS</b><small>${gitHunksState.hunks.length} independently stageable</small></header>${gitHunksState.hunks.map(hunk=>`<article><span><b>${escapeHtml(hunk.header)}</b><small>+${hunk.added} −${hunk.removed} ${escapeHtml(hunk.context||'')}</small></span><button type="button" data-git-hunk-action="${gitDiffState.mode==='staged'?'unstage':'stage'}" data-git-hunk-id="${escapeHtml(hunk.id)}">${gitDiffState.mode==='staged'?'Unstage':'Stage'}</button></article>`).join('')||'<small>No independent hunks in this diff.</small>'}`:'';
      const showConflict=gitConflictState.status==='ready';conflict.classList.toggle('hidden',!showConflict);conflict.innerHTML=showConflict?`<header><b>MERGE RESOLUTION</b><small>${gitConflictState.regions||0} conflict region(s) · resolve and stage</small></header><div class="cortex-conflict-sources"><details><summary>Current branch</summary><pre>${escapeHtml(gitConflictState.currentText||'')}</pre></details><details><summary>Incoming branch</summary><pre>${escapeHtml(gitConflictState.incomingText||'')}</pre></details></div><label>RESOLVED RESULT<textarea data-git-conflict-result spellcheck="false">${escapeHtml(gitConflictState.resultText||'')}</textarea></label><button type="button" data-git-conflict-action="resolve">Save resolution + stage</button>`:'';
      const host=root.querySelector('[data-git-diff-host]');const fallbackNode=root.querySelector('[data-git-diff-fallback]');
      if(gitDiffState.status!=='ready'){host.classList.add('hidden');fallbackNode.classList.remove('hidden');fallbackNode.textContent=gitDiffState.status==='loading'?'Loading verified Git diff…':gitDiffState.error;return;}
      const key=`${gitDiffState.mode}:${gitDiffState.planId||''}:${gitDiffState.path}:${gitDiffState.originalText.length}:${gitDiffState.modifiedText.length}:${gitState.updatedAt}`;if(key===gitDiffKey)return;gitDiffKey=key;gitDiffCleanup?.();gitDiffCleanup=null;const token=++gitDiffMountToken;
      BeastEditorCortex.mountContentDiff(host,fallbackNode,{identity:aiDiff?`ai-${gitDiffState.planId||'proposal'}`:`git-${gitDiffState.mode}`,path:gitDiffState.path,originalText:gitDiffState.originalText,modifiedText:gitDiffState.modifiedText,patch:gitDiffState.patch}).then(cleanup=>{if(token!==gitDiffMountToken)cleanup?.();else gitDiffCleanup=cleanup;}).catch(error=>{fallbackNode.classList.remove('hidden');fallbackNode.textContent=String(error.message||error);});
    }
    async function runWorkspaceSearch(action='search') {
      const api=window.beastDesktop;if(!api?.searchWorkspace||!api?.replaceWorkspace){searchState={...searchState,status:'error',error:'Workspace search is available only in the BEAST desktop shell.'};renderExplorer(BeastStore.get());return;}
      if(!searchState.query.trim()){searchState={...searchState,status:'error',error:'Enter text to search.'};renderExplorer(BeastStore.get());return;}
      searchState={...searchState,status:'loading',error:''};renderExplorer(BeastStore.get());
      try { if(action==='search'){const result=await api.searchWorkspace({query:searchState.query});searchState={...searchState,status:'ready',results:result.results||[],preview:[],total:(result.results||[]).length,message:result.truncated?'Result limit reached. Refine the search.':`${(result.results||[]).length} match(es).`,error:result.error||''};}else{const result=await api.replaceWorkspace({query:searchState.query,replacement:searchState.replacement,apply:action==='apply'});searchState={...searchState,status:result.ok?'ready':'error',preview:result.files||[],results:[],total:result.total||0,message:result.ok?(result.applied?`${result.total} replacement(s) applied.`:`Preview: ${result.total} replacement(s) across ${(result.files||[]).length} file(s).`):'',error:result.error||''};if(result.applied)await BeastDesktopBridge.listFiles({signal});} }
      catch(error){searchState={...searchState,status:'error',error:String(error.message||error)};}
      renderExplorer(BeastStore.get());
    }

    async function refreshDurableConsole(state, force = false) {
      const runId = String(state.aiCoding.activeRunId || state.aiCoding.sessionId || '').trim();
      if (!runId || !window.BeastOperationsConsole) return;
      const key = `${state.workspace.root || ''}:${runId}`;
      if (!force && key === durableConsoleKey) return;
      durableConsoleKey = key;
      try {
        const [snapshot, mission] = await Promise.all([
          BeastOperationsConsole.load(runId, { force:true }),
          BeastOperationsConsole.loadMission(runId).catch(() => null)
        ]);
        if (disposed) return;
        const objective = mission?.current?.objective || mission?.objective || snapshot?.run?.objective || '';
        const criteria = mission?.current?.success_criteria || mission?.success_criteria || snapshot?.run?.success_criteria || [];
        const plan = mission?.current?.plan || mission?.plan || snapshot?.plan || {};
        const activeStep = plan?.steps?.find?.(step => step.status === 'active') || null;
        if (objective) root.querySelector('[data-ai-objective]').textContent = objective;
        root.querySelector('[data-ai-success-plan]').textContent = `Plan v${mission?.current?.plan_version || mission?.plan_version || plan?.version || '—'}: ${activeStep?.title || plan?.active_step_id || plan?.status || 'waiting'}`;
        root.querySelector('[data-ai-console-plan]').textContent = activeStep?.title || plan?.active_step_id || plan?.status || 'waiting';
        root.querySelector('[data-ai-console-timeline]').textContent = `${snapshot?.timeline?.event_count || 0} durable events`;
        root.querySelector('[data-ai-console-tools]').textContent = `${snapshot?.tool_activity?.count || 0} tools · ${snapshot?.approvals?.pending || 0} pending approvals`;
        root.querySelector('[data-ai-console-worktree]').textContent = snapshot?.worktree?.status || 'operator workspace protected';
        root.querySelector('[data-ai-console-verify]').textContent = snapshot?.verification?.status || 'waiting';
        const used = snapshot?.budget?.used_tokens ?? snapshot?.budget?.tokens_used;
        const limit = snapshot?.budget?.token_limit ?? snapshot?.budget?.max_tokens;
        root.querySelector('[data-ai-console-budget]').textContent = used != null ? `${used}${limit ? ` / ${limit}` : ''} tokens` : 'governed';
        if (criteria.length) root.querySelector('[data-ai-success-verify]').title = criteria.join('\n');
        const contextPayload = await BeastOperationsConsole.loadSurface('context', runId).catch(() => null);
        const contextItems = contextPayload?.items || contextPayload?.cards || [];
        const contextSummary = contextPayload?.summary || {};
        root.querySelector('[data-phase5-context-summary]').textContent = `${contextSummary.selected_items ?? contextSummary.accepted_count ?? 0} selected · ${contextSummary.admitted_items ?? contextSummary.admitted_count ?? 0} admitted`;
        root.querySelector('[data-phase5-context-list]').innerHTML = contextItems.length ? contextItems.slice(0,12).map(item => `<article class="phase5-context-card"><div><b>${BeastOperationsConsole.esc(item.source_reference || item.path || item.source || 'context item')}</b><small>${BeastOperationsConsole.esc(item.status || 'DISCOVERED')} · ${BeastOperationsConsole.esc(item.privacy_level || 'INTERNAL')} · ${BeastOperationsConsole.esc(item.provider_visibility || 'LOCAL_ONLY')}</small></div><span>${Number(item.token_estimate || 0)} tok</span><div class="phase5-context-actions">${(item.valid_actions || []).map(action => `<button type="button" data-phase5-context-action="${BeastOperationsConsole.esc(action)}" data-context-item-id="${BeastOperationsConsole.esc(item.item_id)}">${BeastOperationsConsole.esc(action.replaceAll('_',' '))}</button>`).join('')}</div></article>`).join('') : '<div class="cortex-empty-list">No durable context items recorded.</div>';
      } catch (error) {
        if (!disposed) root.querySelector('[data-ai-console-timeline]').textContent = `durable console unavailable: ${String(error.message || error)}`;
      }
    }

    function renderAi(state) {
      const ai = state.aiCoding;
      const nextWorkload=ai.streaming?'interactive':'idle';
      if(nextWorkload!==visualWorkload){visualWorkload=nextWorkload;window.BeastVisualRuntime?.setWorkload?.(nextWorkload);}
      const modeCopy={ask:{description:'Read-only answers from explicitly selected context.',placeholder:'Ask a question about this codebase…',send:'Ask BEAST'},edit:{description:'One bounded proposal, one repair turn, SourcePlan required.',placeholder:'Describe the focused change you want to make…',send:'Propose edit'},agent:{description:'Durable isolated execution with governed tools, verification, and SourcePlan promotion boundary.',placeholder:'Describe the outcome you want BEAST to implement…',send:'Run agent'},review:{description:'Critic and verifier roles only. Convert explicitly to Agent before mutation.',placeholder:'Describe what BEAST should review or verify…',send:'Run review'}}[ai.mode]||{};
      root.classList.toggle('ai-open', Boolean(ai.open));
      root.classList.toggle('ai-focus', Boolean(ai.open&&ai.expanded));
      root.querySelector('.cortex-layout').classList.toggle('ai-open', ai.open);
      root.querySelector('.cortex-layout').classList.toggle('ai-focus', Boolean(ai.open&&ai.expanded));
      root.querySelector('[data-ai-panel]').classList.toggle('hidden', !ai.open);
      root.querySelectorAll('[data-ai-mode]').forEach(button => {const active=button.dataset.aiMode===ai.mode;button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));});
      const expand=root.querySelector('[data-ai-expand]');expand.setAttribute('aria-pressed',String(Boolean(ai.expanded)));expand.title=ai.expanded?'Return to normal workbench layout':'Expand Pair Programmer';root.querySelector('[data-ai-expand-label]').textContent=ai.expanded?'Workbench':'Focus';
      const prompt = root.querySelector('[data-ai-prompt]');
      if (document.activeElement !== prompt && prompt.value !== ai.prompt) prompt.value = ai.prompt || '';
      prompt.placeholder=modeCopy.placeholder||'Describe what you want to build or change…';root.querySelector('[data-ai-mode-description]').textContent=modeCopy.description||'';root.querySelector('[data-ai-send-label]').textContent=modeCopy.send||'Send';
      const objectiveText=(ai.prompt||ai.messages.slice().reverse().find(message=>message.role==='user')?.content||modeCopy.placeholder||'Describe the outcome BEAST should achieve.').trim();
      root.querySelector('[data-ai-objective-mode]').textContent=(ai.mode||'ask').toUpperCase();
      root.querySelector('[data-ai-objective]').textContent=objectiveText.length>180?`${objectiveText.slice(0,177)}…`:objectiveText;
      refreshDurableConsole(state);
      const latestAssistant=ai.messages.slice().reverse().find(message=>message.role==='assistant')||{};
      const turns=Array.isArray(latestAssistant.turns)?latestAssistant.turns:[];
      const progress=Array.isArray(latestAssistant.progress)?latestAssistant.progress:[];
      const toolCount=turns.filter(turn=>/tool|context|search|read|verify|approval/i.test(`${turn.type||''} ${turn.kind||''}`)).length;
      const doneCount=progress.filter(item=>item.state==='done').length;
      const failedCount=progress.filter(item=>item.state==='failed').length;
      const planState=ai.sourcePlanReady?'ready':latestAssistant.proposal?.ready?'drafted':ai.streaming?'planning':'waiting';
      const verifyState=failedCount?'failed':progress.some(item=>String(item.phase||'').includes('verify')&&item.state==='done')?'checked':ai.streaming?'waiting':'idle';
      root.querySelector('[data-ai-success-plan]').textContent=`Plan: ${planState}`;
      root.querySelector('[data-ai-success-tools]').textContent=`Tools: ${toolCount || 'governed'}`;
      root.querySelector('[data-ai-success-verify]').textContent=`Verify: ${verifyState}`;
      root.querySelector('[data-ai-success-sourceplan]').textContent=`SourcePlan: ${ai.sourcePlanReady?'ready':'pending'}`;
      root.querySelector('[data-ai-console-plan]').textContent=planState;
      root.querySelector('[data-ai-console-timeline]').textContent=`${ai.trace.length} event${ai.trace.length===1?'':'s'}`;
      root.querySelector('[data-ai-console-tools]').textContent=toolCount?`${toolCount} visible turn${toolCount===1?'':'s'}`:'governed';
      root.querySelector('[data-ai-console-worktree]').textContent=ai.mode==='agent'?'isolate available · no direct workspace write':'no worktree needed';
      root.querySelector('[data-ai-console-verify]').textContent=verifyState;
      root.querySelector('[data-ai-console-budget]').textContent=ai.streaming?'active budget':'120k tokens · governed';
      const modelKey = JSON.stringify([state.models.registry.map(row => [row.id,row.provider,row.status]), ai.model]);
      if (modelKey !== lastAiModelsKey) {
        lastAiModelsKey = modelKey;
        const select = root.querySelector('[data-ai-model]');
        select.innerHTML = '<option value="">Select a model…</option>' + state.models.registry.map(row => `<option value="${escapeHtml(row.id)}" ${row.id === ai.model ? 'selected' : ''}>${escapeHtml(row.id)} · ${escapeHtml(row.provider || '')}${row.status&&row.status!=='ready'?` · ${escapeHtml(row.status)}`:''}</option>`).join('');
      }
      const contextKey = JSON.stringify([ai.contextFiles, ai.selection]);
      if (contextKey !== lastAiContextKey) {
        lastAiContextKey = contextKey;
        const chips = ai.contextFiles.map(path => `<button type="button" data-ai-context-path="${escapeHtml(path)}" title="Remove context">${escapeHtml(fileName(path))}<i>×</i></button>`);
        if (ai.selection?.text) chips.push(`<button type="button" data-ai-action="remove-selection" title="Remove selection">Selection · ${escapeHtml(ai.selection.path)}<i>×</i></button>`);
        root.querySelector('[data-ai-context]').innerHTML = chips.join('') || '<span>No context pinned. The active file is attached automatically.</span>';
      }
      const suggestionKey=JSON.stringify([ai.contextSuggestions,ai.contextSuggestionStatus]);
      if(suggestionKey!==root.dataset.aiSuggestionKey){root.dataset.aiSuggestionKey=suggestionKey;const host=root.querySelector('[data-ai-context-suggestions]');const rows=Array.isArray(ai.contextSuggestions)?ai.contextSuggestions:[];const cards=rows.map(item=>`<button type="button" data-ai-accept-suggestion="${escapeHtml(item.path)}"><span><b>${escapeHtml(fileName(item.path))}</b><small>${escapeHtml(item.reason)}${item.line?` · line ${item.line}`:''}</small></span><i>Add</i></button>`).join('');host.innerHTML=ai.contextSuggestionStatus==='loading'?'<small>Finding metadata-first context suggestions…</small>':rows.length?`<small>Suggested context — review before adding</small>${cards}`:'<small>No unapproved suggestions.</small>';}
      const scopeCount = new Set([state.editor.activePath, ...ai.contextFiles].filter(Boolean)).size;
      const primaryContext=state.editor.activePath||ai.contextFiles[0]||'';root.querySelector('[data-ai-context-count]').textContent = scopeCount===1?`${fileName(primaryContext)} · active${ai.selection?.text?' + selection':''}`:`${scopeCount||'No'} files${ai.selection?.text?' + selection':''}`;
      // During a stream, only the assistant body changes for most tokens.
      // Replacing the entire messages subtree on every chunk reset its scroll
      // geometry and produced the long right-edge scrollbar / snap-back.
      const host = root.querySelector('[data-ai-messages]');
      const messageKey = JSON.stringify([ai.messages.map(message=>({id:message.id,role:message.role,streaming:message.streaming,error:message.error,mode:message.mode,files:message.files,proposal:message.proposal?.ready,recovery:message.recovery,progress:message.progress,turns:message.turns,draftPreview:message.draftPreview,activity:message.activity})),ai.mode,state.editor.activePath]);
      if (messageKey !== lastAiMessagesKey) {
        lastAiMessagesKey = messageKey;
        const followOutput=aiFollowOutput||aiAtBottom(host);
        const previousTop=host.scrollTop;
        // Rendering replaces the message subtree. Cancel any deferred scroll
        // from its previous incarnation before replacing it; otherwise an old
        // proposal callback can apply an obsolete bounding-rect delta after a
        // newer streaming update and visibly snap the scrollbar backwards.
        if(aiScrollFrame){cancelAnimationFrame(aiScrollFrame);aiScrollFrame=0;}
        host.innerHTML = ai.messages.map(message => `<article data-ai-message-id="${escapeHtml(message.id)}" class="cortex-ai-message ${escapeHtml(message.role)} ${message.error ? 'error' : ''} ${message.proposal?.ready?'has-proposal':''}"><header><span class="cortex-ai-message-author"><img src="${message.role === 'user' ? BeastAssets.icon('context') : BeastAssets.icon('agent-premium')}" alt=""><b>${message.role === 'user' ? 'You' : 'BEAST'}</b></span><span>${message.streaming?`<i>${escapeHtml(message.activity||'Working…')}</i>`:escapeHtml(aiClock(message.at))}<button type="button" data-ai-copy-id="${escapeHtml(message.id)}" aria-label="Copy this message" title="Copy message">Copy</button></span></header><div class="cortex-ai-message-body">${aiMessageBody(aiVisibleMessageContent(message))}</div>${aiAgentCockpit(message)}${aiNarration(message)}${aiProgress(message)}${aiDraftPreview(message)}${aiRecoveryCard(message)}${aiActiveAgentRequests(message)}${aiProposalCard(message)}${aiTurns(message)}${message.error&&message.role==='assistant'&&message.mode!=='ask'?'<button type="button" class="cortex-ai-retry" data-ai-action="retry">Retry with locked context</button>':''}${message.files?.length ? `<footer>${message.files.length} context file${message.files.length === 1 ? '' : 's'} used · ${escapeHtml(message.mode||'ask')}</footer>` : ''}</article>`).join('') || `<div class="cortex-ai-empty"><header><img src="${BeastAssets.icon('agent-premium')}" alt=""><span><strong>What do you want to build?</strong><small>${escapeHtml(modeCopy.description||'Work with BEAST across your repository.')}</small></span></header><p>The active file is included automatically. Add more context only when you need it.</p><div class="cortex-ai-suggestions"><button type="button" data-ai-suggestion-mode="ask" data-ai-suggestion="Explain the active file and identify its key dependencies."><b>Explain this file</b><small>Ask mode · stream an explanation</small></button><button type="button" data-ai-suggestion-mode="agent" data-ai-suggestion="Find the most likely bug in the active file and propose the smallest safe fix."><b>Find and fix a bug</b><small>Agent mode · inspect and propose a patch</small></button><button type="button" data-ai-suggestion-mode="agent" data-ai-suggestion="Add focused tests for the active file, covering its riskiest behavior."><b>Add focused tests</b><small>Agent mode · create reviewable edits</small></button><button type="button" data-ai-suggestion-mode="edit" data-ai-suggestion="Refactor the selected code for clarity without changing behavior."><b>Refactor safely</b><small>Edit mode · produce exact hunks</small></button></div></div>`;
        if(followOutput){
          // One scroll authority: follow the newest content only when the
          // operator was already following. Never scroll to a proposal's
          // moving bounding rectangle—its asynchronous layout was the source
          // of the right-edge scrollbar jump/reset.
          aiScrollFrame=requestAnimationFrame(()=>{
            aiScrollFrame=0;
            if(aiFollowOutput||aiAtBottom(host))host.scrollTop=host.scrollHeight;
          });
        } else {host.scrollTop=Math.min(previousTop,Math.max(0,host.scrollHeight-host.clientHeight));if(ai.streaming)aiUnreadOutput+=1;}
        aiFollowOutput=followOutput;syncAiFollowControl();
      } else {
        // Keep the existing scroll container and its native scrollbar intact;
        // only replace message bodies whose streamed text actually changed.
        ai.messages.forEach(message=>{const body=root.querySelector(`[data-ai-message-id="${CSS.escape(String(message.id))}"] .cortex-ai-message-body`);if(!body)return;const next=aiMessageBody(aiVisibleMessageContent(message));if(body.innerHTML!==next)body.innerHTML=next;});
        if(aiFollowOutput){if(aiScrollFrame)cancelAnimationFrame(aiScrollFrame);aiScrollFrame=requestAnimationFrame(()=>{aiScrollFrame=0;if(aiFollowOutput)host.scrollTop=host.scrollHeight;});}
      }
      root.querySelector('[data-ai-trace]').innerHTML = ai.trace.slice().reverse().map(item => `<div><b>${escapeHtml(item.kind)}</b><span>${escapeHtml(item.text)}</span></div>`).join('') || '<span>No run events yet.</span>';
      root.querySelector('[data-ai-trace-count]').textContent = ai.trace.length;
      const status = root.querySelector('[data-ai-status]');
      const statusCopy={'gathering-context':'Finding relevant files…',creating:'Starting the coding session…',streaming:'Inspecting and planning…',finishing:'Finishing response…','building-changes':'Building a reviewable patch…','validating-changes':'Validating proposed files…','ready-to-review':'Validated changes ready to review',complete:'Response complete','review-needed':'Needs your input',interrupted:'Previous run interrupted',cancelled:'Stopped',error:'Something went wrong'};
      status.textContent = ai.error || statusCopy[ai.status] || (ai.sessionId ? 'Ready for your next message' : 'Ready');
      status.classList.toggle('error', Boolean(ai.error));
      root.querySelector('[data-ai-action="send"]').disabled = ai.streaming;
      root.querySelector('[data-ai-action="cancel"]').classList.toggle('hidden', !ai.streaming);
      root.querySelector('.cortex-ai-sourceplan').classList.toggle('hidden', !ai.sourcePlanReady);
      const crystal = root.querySelector('[data-ai-crystal]');
      crystal.textContent = ai.crystal.reused ? `Reused · ${ai.crystal.avoidedTokens || 0} tokens saved` : ai.crystal.recorded ? 'Verified reuse saved' : ai.crystal.candidate ? 'Candidate captured' : ai.crystal.action ? ai.crystal.action.replaceAll('_',' ') : 'Reuse ready';
      root.querySelector('[data-ai-crystal-detail]').textContent = ai.crystal.reused ? `Served from ${ai.crystal.source || 'verified prior work'} without another model call.` : ai.crystal.recorded ? 'This verified result can be reused on an exact future request.' : ai.crystal.candidate ? 'Captured for learning; it cannot serve edits until SourcePlan verification and apply succeed.' : 'Prior verified work is checked before inference.';
      root.querySelector('[data-ai-crystal-confidence]').textContent = ai.crystal.confidence ? `${Math.round(ai.crystal.confidence * 100)}%` : 'On';
      root.querySelector('[data-ai-compute]').classList.toggle('live', Boolean(ai.crystal.reused || ai.crystal.recorded));
      const compute=ai.compute||{};const supplied=Number(compute.suppliedChars||0);const source=Number(compute.sourceChars||0);const withheld=Math.max(0,source-supplied);
      root.querySelector('[data-ai-compute-summary]').textContent = supplied
        ? `Economizer: ${compute.historyChanged?`${compute.historyOriginalTokens}→${compute.historyFinalTokens} history tokens; `:'history preserved; '}${compute.readableFiles||0}/${compute.selectedFiles||0} selected source files · ${supplied.toLocaleString()} chars supplied${withheld ? ` · ${withheld.toLocaleString()} chars withheld` : ''}. KV cache: ${compute.kvCache==='provider_managed'?'provider-managed':'not reported'}. Crystal: ${compute.crystal||'preflight'}.`
        : 'Context economics will appear when a run starts.';
      root.querySelector('[data-ai-session]').textContent = ai.sessionId ? `Session ${ai.sessionId.slice(-6)}` : 'New chat';
    }

    function renderTabs(state) {
      const key = `${state.editor.openTabs.join('|')}::${state.editor.activePath}::${state.editor.dirtyPaths.join('|')}::${gitDiffState.status}:${gitDiffState.mode}:${gitDiffState.path}`;
      if (key === lastTabsKey) return; lastTabsKey = key;
      const host = root.querySelector('[data-editor-tabs]');
      const fragment = document.createDocumentFragment();
      const layout = window.BeastEditorGroups?.snapshot?.();
      const owningGroup = path => Object.values(layout?.groups || {}).find(group => group.tabs.includes(path));
      state.editor.openTabs.forEach(path => {
        const group = owningGroup(path);
        const tab = document.createElement('button'); tab.type = 'button'; tab.className = 'cortex-tab'; tab.dataset.editorTab = path;
        tab.draggable = true; tab.dataset.editorGroup = group?.groupId || '';
        if (path === state.editor.activePath&&gitDiffState.status==='idle') tab.classList.add('active');
        if (state.editor.dirtyPaths.includes(path)) tab.classList.add('dirty');
        if (group?.pinnedDocumentIds?.includes(path)) tab.classList.add('pinned');
        if (group?.previewDocumentId === path) tab.classList.add('preview');
        tab.innerHTML = `<img src="${iconFor(path, 'file')}" alt=""><span>${escapeHtml(fileName(path))}</span>${group?.pinnedDocumentIds?.includes(path)?'<em title="Pinned editor">◆</em>':''}<i data-close-tab="${escapeHtml(path)}">×</i>`;
        fragment.append(tab);
      });
      if(gitDiffState.status!=='idle'){
        const tab=document.createElement('button');tab.type='button';tab.className='cortex-tab active git-diff-tab';tab.dataset.gitDiffTab='true';tab.innerHTML=`<img src="${iconFor(gitDiffState.path,'file')}" alt=""><span>${escapeHtml(fileName(gitDiffState.path))} <small>(${gitDiffState.mode==='ai'?'AI Proposal':gitDiffState.mode==='staged'?'Index':'Working Tree'})</small></span><i data-git-diff-action="close" aria-label="Close change diff">×</i>`;fragment.append(tab);
      }
      host.replaceChildren(fragment);
    }

    function renderBreadcrumbs(state) {
      const host=root.querySelector('[data-editor-breadcrumbs]');const path=gitDiffState.status!=='idle'?gitDiffState.path:state.editor.activePath;
      if(!path){host.innerHTML='<span>No file open</span>';return;}
      const parts=String(path).split('/').filter(Boolean);let cursor='';host.innerHTML=parts.map((part,index)=>{cursor=cursor?`${cursor}/${part}`:part;const last=index===parts.length-1;return `${index?'<i aria-hidden="true">›</i>':''}<button type="button" ${last?`data-breadcrumb-file="${escapeHtml(path)}"`:`data-breadcrumb-filter="${escapeHtml(cursor)}/"`} ${last?'aria-current="page"':''}>${last?`<img src="${iconFor(path,'file')}" alt="">`:''}${escapeHtml(part)}</button>`;}).join('');
      if(gitDiffState.status!=='idle')host.insertAdjacentHTML('afterbegin',`<b>${gitDiffState.mode==='ai'?'AI Changes':'Source Control'}</b><i aria-hidden="true">›</i>`);
    }

    function notebookOutput(output = {}) {
      const data = output.data || {};
      const image = typeof data['image/png'] === 'string' && /^[A-Za-z0-9+/=]+$/.test(data['image/png']) ? `<img src="data:image/png;base64,${data['image/png']}" alt="Notebook output">` : '';
      const text = output.type === 'error' ? `${output.ename || 'Error'}: ${output.evalue || ''}\n${(output.traceback || []).join('\n')}` : output.text || data['text/plain'] || '';
      return `<div class="beast-notebook-output ${output.type === 'error' ? 'error' : ''}">${image}${text ? `<pre>${escapeHtml(typeof text === 'string' ? text : JSON.stringify(text, null, 2))}</pre>` : ''}</div>`;
    }
    function markdownPreview(source) {
      return escapeHtml(source).replace(/^### (.*)$/gm, '<h4>$1</h4>').replace(/^## (.*)$/gm, '<h3>$1</h3>').replace(/^# (.*)$/gm, '<h2>$1</h2>').replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\n/g, '<br>');
    }
    function renderNotebook(state) {
      const path = state.editor.activePath;
      const document = BeastEditorCortex.getNotebook(path);
      const host = root.querySelector('[data-notebook-workbench]');
      const isActive = Boolean(document);
      host.classList.toggle('hidden', !isActive);
      if (isActive) [editorHost, fallback, splitHost, splitFallback].forEach(node => node.classList.add('hidden'));
      else {
        const monacoActive = state.editor.owner === 'monaco';
        editorHost.classList.toggle('hidden', !monacoActive); fallback.classList.toggle('hidden', monacoActive);
        splitHost.classList.toggle('hidden', !monacoActive || !state.editor.split); splitFallback.classList.toggle('hidden', monacoActive || !state.editor.split);
        lastNotebookKey = ''; return;
      }
      const cellKey = document.cells.map(cell => `${cell.id}:${cell.cell_type}:${cell.execution_count}:${JSON.stringify(cell.outputs || [])}`).join('|');
      const key = `${path}:${document.parseError}:${cellKey}:${state.compatibility?.runtime?.notebook?.kernelStatus || ''}`;
      if (key === lastNotebookKey) return; lastNotebookKey = key;
      const remote = Boolean(BeastDesktopBridge.parseRemoteRef?.(path));
      host.innerHTML = `<header class="beast-notebook-head"><div><small>JUPYTER NOTEBOOK</small><strong>${escapeHtml(fileName(path))}</strong><span>${document.cells.length} cell${document.cells.length === 1 ? '' : 's'} · ${remote ? 'verified remote save' : 'SourcePlan governed save'}</span></div><div><span class="beast-notebook-kernel ${escapeHtml(state.compatibility?.runtime?.notebook?.kernelStatus || 'idle')}">${escapeHtml((state.compatibility?.runtime?.notebook?.kernelStatus || 'kernel idle').toUpperCase())}</span><button data-notebook-action="run-all">Run all</button><button data-notebook-action="add-code">+ Code</button><button data-notebook-action="add-markdown">+ Markdown</button></div></header>${document.parseError ? `<div class="beast-notebook-warning">${escapeHtml(document.parseError)} — editing will create a valid notebook document.</div>` : ''}<main class="beast-notebook-cells">${document.cells.map((cell, index) => `<article class="beast-notebook-cell ${cell.cell_type}" data-notebook-cell="${escapeHtml(cell.id)}"><header><span><b>In&nbsp;[${cell.execution_count ?? ' '}]</b><em>${cell.cell_type}</em></span><div><button title="Move cell up" data-notebook-action="move-up" data-notebook-cell-id="${escapeHtml(cell.id)}" ${index === 0 ? 'disabled' : ''}>↑</button><button title="Move cell down" data-notebook-action="move-down" data-notebook-cell-id="${escapeHtml(cell.id)}" ${index === document.cells.length - 1 ? 'disabled' : ''}>↓</button>${cell.cell_type === 'code' ? `<button class="run" data-notebook-action="run-cell" data-notebook-cell-id="${escapeHtml(cell.id)}">Run</button>` : ''}<button title="Delete cell" data-notebook-action="delete-cell" data-notebook-cell-id="${escapeHtml(cell.id)}" ${document.cells.length === 1 ? 'disabled' : ''}>×</button></div></header>${cell.cell_type === 'markdown' ? `<div class="beast-notebook-markdown" data-notebook-markdown-preview="${escapeHtml(cell.id)}">${markdownPreview(cell.source)}</div>` : ''}<textarea data-notebook-cell-source="${escapeHtml(cell.id)}" spellcheck="false" aria-label="${cell.cell_type} notebook cell">${escapeHtml(cell.source)}</textarea>${cell.cell_type === 'code' ? `<section class="beast-notebook-outputs">${(cell.outputs || []).map(notebookOutput).join('')}</section>` : ''}</article>`).join('')}</main>`;
    }

    function renderExplorer(state) {
      const query = filter.value.trim().toLowerCase();
      const key = `${state.editor.explorerTab}|${state.editor.explorerMode}|${state.workspace.files.map(file => file.path).join('|')}|${state.editor.collapsedFolders.join('|')}|${state.editor.activePath}|${state.editor.outline.map(row => `${row.name}:${row.line}`).join('|')}|${state.editor.recentFiles.join('|')}|${gitState.status}|${gitState.branch}|${gitState.message}|${gitState.error}|${gitNewBranchOpen}|${gitState.changes.map(row=>`${row.index}:${row.path}`).join('|')}|${gitDetails.loading}|${gitDetails.error}|${gitDetails.history.map(row=>row.hash).join('|')}|${gitDetails.remotes.map(row=>row.name).join('|')}|${searchState.status}|${searchState.query}|${searchState.replacement}|${searchState.message}|${searchState.results.map(row=>`${row.path}:${row.line}`).join('|')}|${searchState.preview.map(row=>`${row.path}:${row.count}`).join('|')}|${query}`;
      if (key === lastExplorerKey) return; lastExplorerKey = key;
      const fragment = document.createDocumentFragment();
      if (state.editor.explorerTab === 'outline') {
        if (!state.editor.outline.length) explorer.innerHTML = '<div class="cortex-empty-list">No symbols detected in the active buffer.</div>';
        else {
          state.editor.outline.forEach(symbol => {
            const row = document.createElement('button'); row.className = 'beast-file-row symbol'; row.dataset.gotoLine = symbol.line;
            row.innerHTML = `<span class="beast-tree-caret">${symbol.kind === 'type' ? '◆' : 'ƒ'}</span><span class="beast-file-copy"><strong>${escapeHtml(symbol.name)}</strong><small>line ${symbol.line}</small></span><em>${escapeHtml(symbol.kind)}</em>`;
            fragment.append(row);
          }); explorer.replaceChildren(fragment);
        }
      } else if (state.editor.explorerTab === 'recent') {
        if (!state.editor.recentFiles.length) explorer.innerHTML = '<div class="cortex-empty-list">No recent files yet.</div>';
        else {
          state.editor.recentFiles.forEach(path => {
            const row = document.createElement('button'); row.className = 'beast-file-row'; row.dataset.filePath = path;
            row.innerHTML = `<span class="beast-tree-caret">↺</span><img src="${iconFor(path, 'file')}" alt=""><span class="beast-file-copy"><strong>${escapeHtml(fileName(path))}</strong><small>${escapeHtml(path)}</small></span>`;
            fragment.append(row);
          }); explorer.replaceChildren(fragment);
        }
      } else if (state.editor.explorerTab === 'changes') {
        if (gitState.status==='idle') { explorer.innerHTML='<div class="cortex-empty-list">Open Changes to inspect this workspace Git state.</div>'; queueMicrotask(()=>refreshGit()); }
        else if (gitState.status==='loading'&&!gitState.changes.length) explorer.innerHTML='<div class="cortex-scm-loading" role="status"><i></i><span>Refreshing Source Control…</span></div>';
        else if (gitState.error) explorer.innerHTML=`<div class="cortex-empty-list">${escapeHtml(gitState.error)}</div>`;
        else {
          const changeRow=(change,mode)=>`<div class="cortex-scm-row ${change.conflict?'conflict':''} ${gitDiffState.path===change.path&&gitDiffState.mode===mode?'active':''}"><button type="button" data-git-diff-path="${escapeHtml(change.path)}" data-git-diff-original="${escapeHtml(change.originalPath||'')}" data-git-diff-mode="${mode}" title="Open ${mode} diff for ${escapeHtml(change.path)}"><span>${escapeHtml(mode==='staged'?(change.index[0]||'M'):(change.index[1]?.trim()||change.index[0]||'M'))}</span><img src="${iconFor(change.path,'file')}" alt=""><i><strong>${escapeHtml(fileName(change.path))}</strong><small>${escapeHtml(change.path)}</small></i></button>${change.conflict?`<button type="button" class="cortex-scm-row-action" data-git-conflict-path="${escapeHtml(change.path)}" aria-label="Resolve ${escapeHtml(change.path)}" title="Open merge resolution">⚑</button>`:`<button type="button" class="cortex-scm-row-action" data-git-file-action="${mode==='staged'?'unstage':'stage'}" data-git-path="${escapeHtml(change.path)}" aria-label="${mode==='staged'?'Unstage':'Stage'} ${escapeHtml(change.path)}" title="${mode==='staged'?'Unstage':'Stage'} change">${mode==='staged'?'−':'＋'}</button>`}</div>`;
          const staged=gitState.changes.filter(change=>change.staged);const unstaged=gitState.changes.filter(change=>change.unstaged);const branches=gitState.branches.map(branch=>`<option value="${escapeHtml(branch.name)}" ${branch.current?'selected':''}>${escapeHtml(branch.name)}</option>`).join('');
          explorer.innerHTML=`<div class="cortex-scm-pane">
            <header><label><span>BRANCH</span><select data-git-branch-select aria-label="Current Git branch">${branches||`<option>${escapeHtml(gitState.branchName||'detached HEAD')}</option>`}</select></label><button type="button" data-git-panel-action="new-branch" title="Create branch" aria-label="Create branch">＋</button><button type="button" data-git-panel-action="refresh" title="Refresh Source Control" aria-label="Refresh Source Control">↻</button></header>
            ${gitNewBranchOpen?`<div class="cortex-scm-new-branch"><input data-git-new-branch value="${escapeHtml(gitNewBranchName)}" placeholder="feature/branch-name" aria-label="New branch name"><button type="button" data-git-panel-action="create-branch">Create</button><button type="button" data-git-panel-action="cancel-branch">Cancel</button></div>`:''}
            <div class="cortex-scm-commit"><textarea rows="2" data-git-commit-message placeholder="Message (Ctrl Enter to commit)" aria-label="Commit message">${escapeHtml(gitCommitMessage)}</textarea><button type="button" data-git-panel-action="commit" ${staged.length?'':'disabled'}>Commit ${staged.length?`(${staged.length})`:''}</button></div>
            <p class="${gitState.error?'error':''}" data-git-feedback>${escapeHtml(gitState.error||gitState.message||(gitState.counts.conflicts?`${gitState.counts.conflicts} conflict(s) require resolution.`:'Working tree ready.'))}</p>
            <section><header><span>STAGED CHANGES</span><b>${staged.length}</b><button type="button" data-git-panel-action="unstage-all" ${staged.length?'':'disabled'}>− ALL</button></header><div>${staged.map(change=>changeRow(change,'staged')).join('')||'<p class="empty">Stage changes to prepare a commit.</p>'}</div></section>
            <section><header><span>CHANGES</span><b>${unstaged.length}</b><button type="button" data-git-panel-action="stage-all" ${unstaged.length?'':'disabled'}>＋ ALL</button></header><div>${unstaged.map(change=>changeRow(change,'worktree')).join('')||'<p class="empty">No unstaged changes.</p>'}</div></section>
            <section class="cortex-scm-advanced"><header><span>HISTORY + REMOTES</span><button type="button" data-git-panel-action="details-refresh">${gitDetails.loading?'…':'↻'}</button></header><div class="cortex-scm-remote-actions"><button type="button" data-git-operation="fetch">Fetch</button><button type="button" data-git-operation="pull">Pull FF</button><button type="button" data-git-operation="push">Push</button></div><div class="cortex-scm-remotes">${gitDetails.remotes.length?gitDetails.remotes.map(remote=>`<small><b>${escapeHtml(remote.name)}</b> ${escapeHtml(remote.fetch||remote.push||'')}</small>`).join(''):'Load to inspect remotes.'}</div><div class="cortex-scm-history">${gitDetails.history.slice(0,12).map(commit=>`<button type="button" data-git-history-commit="${escapeHtml(commit.hash)}" title="Use ${escapeHtml(commit.shortHash)} for cherry-pick"><b>${escapeHtml(commit.shortHash)}</b><span>${escapeHtml(commit.subject)}</span></button>`).join('')||'<small>Load to inspect recent commits.</small>'}</div><label class="cortex-scm-inline"><span>REBASE ON</span><input data-git-rebase-base value="${escapeHtml(gitDetails.rebaseBase)}" placeholder="origin/main"></label><div class="cortex-scm-remote-actions"><button type="button" data-git-operation="rebase-start">Rebase</button><button type="button" data-git-operation="rebase-continue">Continue</button><button type="button" data-git-operation="rebase-abort">Abort</button></div><label class="cortex-scm-inline"><span>CHERRY-PICK SHA</span><input data-git-cherry-pick value="${escapeHtml(gitDetails.cherryPick)}" placeholder="7+ hex SHA"></label><div class="cortex-scm-remote-actions"><button type="button" data-git-operation="cherry-pick">Cherry-pick</button><button type="button" data-git-operation="cherry-pick-abort">Abort pick</button></div>${gitDetails.error?`<p class="error">${escapeHtml(gitDetails.error)}</p>`:''}</section>
          </div>`;
        }
      } else if (state.editor.explorerTab === 'search') {
        explorer.innerHTML=`<div class="cortex-search-pane"><label>FIND<input data-workspace-search-query value="${escapeHtml(searchState.query)}" placeholder="Text across workspace"></label><label>REPLACE<input data-workspace-search-replace value="${escapeHtml(searchState.replacement)}" placeholder="Optional replacement"></label><div><button data-workspace-search-action="search">Search</button><button data-workspace-search-action="preview">Preview</button><button data-workspace-search-action="apply">Apply</button></div><small class="${searchState.error?'error':''}">${escapeHtml(searchState.error||searchState.message)}</small><section>${searchState.results.map(row=>`<button class="beast-file-row" data-file-path="${escapeHtml(row.path)}" data-goto-line="${row.line}"><span class="beast-tree-caret">${row.line}</span><span class="beast-file-copy"><strong>${escapeHtml(fileName(row.path))}</strong><small>${escapeHtml(row.path)}:${row.line}:${row.column} · ${escapeHtml(row.preview)}</small></span></button>`).join('')}${searchState.preview.map(row=>`<button class="beast-file-row" data-file-path="${escapeHtml(row.path)}"><span class="beast-tree-caret">±</span><span class="beast-file-copy"><strong>${escapeHtml(fileName(row.path))}</strong><small>${row.count} replacement(s) · ${escapeHtml(row.path)}</small></span></button>`).join('')}</section></div>`;
      } else if (state.editor.explorerMode === 'flat') {
        state.workspace.files.filter(item => !query || item.path.toLowerCase().includes(query)).slice(0, 1400).forEach(item => {
          const row = document.createElement('button'); row.className = 'beast-file-row'; row.dataset.filePath = item.path;
          if (item.path === state.editor.activePath) row.classList.add('active');
          row.innerHTML = `<span class="beast-tree-caret"></span><img src="${iconFor(item.path, item.type)}" alt=""><span class="beast-file-copy"><strong>${escapeHtml(item.name || fileName(item.path))}</strong><small>${escapeHtml(item.path)}</small></span><em>${formatSize(item.size)}</em>`;
          fragment.append(row);
        }); explorer.replaceChildren(fragment);
      } else {
        renderTreeNode(buildTree(state.workspace.files), fragment, 0, state, query); explorer.replaceChildren(fragment);
      }
    }

    function patch(state) {
      if (disposed) return;
      root.querySelector('[data-workspace-root]').textContent = state.workspace.root || 'No workspace selected';
      const folders=root.querySelector('[data-workspace-folders]');if(folders)folders.innerHTML=(state.workspace.roots||[]).map(folder=>`<span class="${folder.primary?'primary':''}" title="${escapeHtml(folder.path)}">${escapeHtml(folder.name||folder.id)}${folder.primary?'':'<button type="button" data-workspace-folder-remove="'+escapeHtml(folder.id)+'" aria-label="Remove workspace folder">×</button>'}</span>`).join('');
      root.querySelector('[data-workspace-count]').textContent = state.workspace.loading ? 'indexing…' : `${state.workspace.files.length} files`;
      root.querySelector('[data-model-count]').textContent = `${state.editor.modelCount} models`;
      const dirty = root.querySelector('[data-workspace-dirty]'); dirty.textContent = state.editor.dirtyPaths.length ? `● ${state.editor.dirtyPaths.length} unsaved` : 'clean'; dirty.classList.toggle('warn', Boolean(state.editor.dirtyPaths.length));
      root.querySelector('[data-explorer-status]').textContent = state.workspace.error || (state.workspace.loading ? 'indexing' : `${state.editor.explorerMode} mode`);
      const activeNotebook = BeastEditorCortex.isNotebook(state.editor.activePath);
      root.querySelector('[data-editor-status]').textContent = state.workspace.error || (state.editor.activePath ? (activeNotebook ? `Jupyter notebook · ${state.workspace.dirty ? (BeastDesktopBridge.parseRemoteRef?.(state.editor.activePath) ? 'verified remote save ready' : 'SourcePlan required before write') : 'clean notebook document'} · ${state.editor.owner}` : `${state.workspace.language} · ${state.workspace.dirty ? 'SourcePlan required before write' : 'clean buffer'} · ${state.editor.owner}`) : 'No active buffer.');
      root.querySelector('[data-editor-position]').textContent = `Ln ${state.editor.cursor.line}, Col ${state.editor.cursor.column}`;
      root.querySelector('[data-layout-status]').textContent = `${state.diagnostics.viewport || ''} · ${state.diagnostics.horizontalOverflow ? 'overflow!' : 'stable'}`;
      root.querySelector('[data-git-branch]').textContent = `${gitState.branchName||'no repository'}${gitState.changes.length?` · ${gitState.changes.length} change${gitState.changes.length===1?'':'s'}`:''}`;
      root.querySelector('[data-editor-empty]').classList.toggle('hidden', Boolean(state.editor.activePath));
      root.querySelectorAll('[data-explorer-tab]').forEach(button => button.classList.toggle('active', button.dataset.explorerTab === state.editor.explorerTab));
      root.querySelector('[data-editor-action="split"]').classList.toggle('active', state.editor.split);
      const ai = state.aiCoding;
      const scopeCount = new Set([state.editor.activePath, ...ai.contextFiles].filter(Boolean)).size;
      root.querySelector('[data-intel-context]').textContent = scopeCount ? `${scopeCount} FILE${scopeCount === 1 ? '' : 'S'}` : 'READY';
      root.querySelector('[data-intel-context-detail]').textContent = ai.selection?.text ? 'selection attached' : state.editor.activePath ? fileName(state.editor.activePath) : 'open a file';
      root.querySelector('[data-intel-crystal]').textContent = ai.crystal.reused ? 'REUSED' : ai.crystal.recorded ? 'RECORDED' : 'ARMED';
      root.querySelector('[data-intel-crystal-detail]').textContent = ai.crystal.reused ? `${ai.crystal.avoidedTokens || 0} tokens avoided` : ai.crystal.recorded ? 'future reuse ready' : 'preflight first';
      root.querySelector('[data-intel-governance]').textContent = ai.sourcePlanReady ? 'PLAN READY' : state.editor.dirtyPaths.length ? 'REVIEW DUE' : 'ENFORCED';
      root.querySelector('[data-intel-governance-detail]').textContent = ai.sourcePlanReady ? 'inspect proposed patch' : state.editor.dirtyPaths.length ? `${state.editor.dirtyPaths.length} staged buffer${state.editor.dirtyPaths.length === 1 ? '' : 's'}` : 'review before write';
      root.querySelector('[data-intel-agent]').textContent = ai.streaming ? 'WORKING' : ai.sessionId ? 'SESSION LIVE' : 'STANDING BY';
      root.querySelector('[data-intel-agent-detail]').textContent = ai.streaming ? ai.status.replaceAll('-',' ') : ai.sessionId ? ai.mode.toUpperCase() : 'Ctrl I';
      root.querySelectorAll('[data-intel-action]').forEach(node => node.classList.toggle('live', (node.dataset.intelAction === 'crystal' && (ai.crystal.reused || ai.crystal.recorded)) || (node.dataset.intelAction === 'agent' && ai.streaming) || (node.dataset.intelAction === 'governance' && ai.sourcePlanReady)));
      const remoteTab=Boolean(BeastDesktopBridge.parseRemoteRef?.(state.editor.activePath));
      const remoteSave = root.querySelector('[data-editor-action="save-remote"]'); const draftSave = root.querySelector('[data-editor-action="draft"]');
      root.querySelector('[data-editor-action="save-remote"]').disabled=!remoteTab;
      root.querySelector('[data-editor-action="draft"]').disabled=remoteTab;
      remoteSave.textContent=activeNotebook?'Save Notebook':'Save Remote';draftSave.textContent=activeNotebook?'Draft Notebook SourcePlan':'Draft SourcePlan';
      remoteSave.title=remoteTab?(activeNotebook?'Save this verified remote notebook':'Save this verified remote file'):'Available for remote editor tabs only';
      const aiPlan=state.sourcePlan?.plan;const nextAiPlanId=String(aiPlan?.plan_id||'');
      if(ai.sourcePlanReady&&nextAiPlanId&&aiPlan?.kind==='beast_ide_agent_action_ir_sourceplan'&&nextAiPlanId!==aiPreviewPlanId){aiPreviewPlanId=nextAiPlanId;queueMicrotask(()=>openAiDiff(aiPlan,state.editor.activePath));}
      if(!ai.sourcePlanReady&&!ai.streaming)aiPreviewPlanId='';
      renderTabs(state); const groupCount=Object.keys(window.BeastEditorGroups?.snapshot?.().groups||{}).length; const groupLabel=root.querySelector('[data-workbench-group-count]'); if(groupLabel)groupLabel.textContent=`${groupCount} PANE${groupCount===1?'':'S'}`; renderExplorer(state); renderAi(state); renderNotebook(state);renderBreadcrumbs(state);renderGitDiff(state);
    }

    const handleAiProposalReady = event => { const plan=event.detail?.plan; if(plan?.operations?.length) queueMicrotask(()=>openAiDiff(plan, BeastStore.get().editor.activePath)); };
    document.addEventListener('beast:ai-proposal-ready', handleAiProposalReady);
    const unsubscribe = BeastStore.subscribe(patch);
    const selectRepository=event=>{const id=String(event.detail?.rootId||'');if(!(BeastStore.get().workspace.roots||[]).some(folder=>folder.id===id))return;selectedGitRootId=id;refreshGit();refreshGitDetails();};document.addEventListener('beast:source-control-root',selectRepository);
    window.BeastEditorSafety?.mount?.(root);
    queueMicrotask(async () => {
      [editorHost, fallback, splitHost, splitFallback].forEach(node => node?.classList.add('legacy-editor-host'));
      await window.BeastEditorWorkbench.mount(workbenchHost);
      // Group layout is persisted independently from editor buffers.  Hydrate
      // the saved tabs after mounting so an active tab can never render as an
      // empty Monaco pane merely because its file text has not been restored.
      await BeastEditorCortex.restoreTabs();
      refreshGit();refreshGitDetails();restoreViewPreferences();
    });

    root.addEventListener('click', async event => {
      const gitDiffAction=event.target.closest('[data-git-diff-action]')?.dataset.gitDiffAction;
      if(gitDiffAction){
        if(gitDiffAction==='close'){closeGitDiff();return;}
        if(gitDiffAction==='sourceplan'){await BeastAICoding.openSourcePlan();return;}
        try{const path=gitDiffState.path;const action=gitDiffAction==='stage'?'stage':'unstage';await runGitAction(action,path);await openGitDiff(path,action==='stage'?'staged':'worktree',gitDiffState.originalPath);}
        catch(error){gitState={...gitState,error:String(error.message||error)};renderExplorer(BeastStore.get());}
        return;
      }
      const hunkAction=event.target.closest('[data-git-hunk-action]');if(hunkAction){try{await runGitHunkAction(hunkAction.dataset.gitHunkAction,hunkAction.dataset.gitHunkId);}catch(error){gitState={...gitState,error:String(error.message||error)};renderExplorer(BeastStore.get());}return;}
      if(event.target.closest('[data-git-conflict-action]')?.dataset.gitConflictAction==='resolve'){try{await resolveGitConflict();}catch(error){gitConflictState={...gitConflictState,error:String(error.message||error)};patch(BeastStore.get());}return;}
      const gitFileAction=event.target.closest('[data-git-file-action]');
      if(gitFileAction){try{await runGitAction(gitFileAction.dataset.gitFileAction,gitFileAction.dataset.gitPath);}catch(error){gitState={...gitState,error:String(error.message||error)};renderExplorer(BeastStore.get());}return;}
      const gitDiffTarget=event.target.closest('[data-git-diff-path]');
      if(gitDiffTarget){await openGitDiff(gitDiffTarget.dataset.gitDiffPath,gitDiffTarget.dataset.gitDiffMode,gitDiffTarget.dataset.gitDiffOriginal);return;}
      const conflictTarget=event.target.closest('[data-git-conflict-path]');if(conflictTarget){await openGitConflict(conflictTarget.dataset.gitConflictPath);return;}
      const gitPanelAction=event.target.closest('[data-git-panel-action]')?.dataset.gitPanelAction;
      if(gitPanelAction){
        try{
          if(gitPanelAction==='refresh')await refreshGit();
          if(gitPanelAction==='commit')await commitGit();
          if(gitPanelAction==='stage-all')await runGitAction('stage-all');
          if(gitPanelAction==='unstage-all')await runGitAction('unstage-all');
          if(gitPanelAction==='details-refresh')await refreshGitDetails();
          if(gitPanelAction==='new-branch'){gitNewBranchOpen=true;gitState={...gitState,error:''};lastExplorerKey='';renderExplorer(BeastStore.get());queueMicrotask(()=>root.querySelector('[data-git-new-branch]')?.focus());}
          if(gitPanelAction==='cancel-branch'){gitNewBranchOpen=false;gitNewBranchName='';lastExplorerKey='';renderExplorer(BeastStore.get());}
          if(gitPanelAction==='create-branch')await changeGitBranch('create',gitNewBranchName);
        }catch(error){gitState={...gitState,error:String(error.message||error),message:''};renderExplorer(BeastStore.get());}
        return;
      }
      const gitOperation=event.target.closest('[data-git-operation]')?.dataset.gitOperation;
      if(gitOperation){try{await runGitOperation(gitOperation);}catch(error){gitDetails={...gitDetails,error:String(error.message||error)};renderExplorer(BeastStore.get());}return;}
      const historyCommit=event.target.closest('[data-git-history-commit]')?.dataset.gitHistoryCommit;
      if(historyCommit){gitDetails={...gitDetails,cherryPick:historyCommit};lastExplorerKey='';renderExplorer(BeastStore.get());return;}
      const statusAction=event.target.closest('[data-status-action]')?.dataset.statusAction;
      if(statusAction==='changes'){BeastEditorCortex.setExplorerTab('changes');await refreshGit();queueMicrotask(()=>root.querySelector('[data-git-commit-message]')?.focus());return;}
      const breadcrumbFilter=event.target.closest('[data-breadcrumb-filter]');
      if(breadcrumbFilter){BeastEditorCortex.setExplorerTab('files');filter.value=breadcrumbFilter.dataset.breadcrumbFilter;lastExplorerKey='';renderExplorer(BeastStore.get());return;}
      const breadcrumbFile=event.target.closest('[data-breadcrumb-file]');
      if(breadcrumbFile&&gitDiffState.status!=='idle'){const path=breadcrumbFile.dataset.breadcrumbFile;closeGitDiff();await BeastEditorCortex.openFile(path,{signal});return;}
      const notebookAction = event.target.closest('[data-notebook-action]')?.dataset.notebookAction;
      if (notebookAction) {
        const cellId = event.target.closest('[data-notebook-cell-id]')?.dataset.notebookCellId || '';
        try {
          if (notebookAction === 'add-code') BeastEditorCortex.addNotebookCell('code');
          if (notebookAction === 'add-markdown') BeastEditorCortex.addNotebookCell('markdown');
          if (notebookAction === 'delete-cell') BeastEditorCortex.deleteNotebookCell(cellId);
          if (notebookAction === 'move-up') BeastEditorCortex.moveNotebookCell(cellId, 'up');
          if (notebookAction === 'move-down') BeastEditorCortex.moveNotebookCell(cellId, 'down');
          if (notebookAction === 'run-cell') await BeastEditorCortex.runNotebookCell(cellId);
          if (notebookAction === 'run-all') await BeastEditorCortex.runAllNotebookCells();
          BeastFX.trigger('success', event.target, { size: 150 });
        } catch (error) { BeastStore.patch('workspace', { error: String(error.message || error) }); BeastFX.trigger('warning', event.target, { size: 150 }); }
        return;
      }
      const close = event.target.closest('[data-close-tab]');
      if (close) { event.stopPropagation(); await BeastEditorCortex.closeTab(close.dataset.closeTab); return; }
      const tab = event.target.closest('[data-editor-tab]'); if (tab) { if(gitDiffState.status!=='idle')closeGitDiff();BeastEditorCortex.activate(tab.dataset.editorTab); return; }
      const file = event.target.closest('[data-file-path]'); if (file) { if(gitDiffState.status!=='idle')closeGitDiff();await BeastEditorCortex.openFile(file.dataset.filePath, { signal });if(file.dataset.gotoLine)BeastEditorCortex.gotoLine(Number(file.dataset.gotoLine)); BeastMascot.setState('working'); setTimeout(() => BeastMascot.setState('idle'), 650); return; }
      const folder = event.target.closest('[data-folder-path]'); if (folder) { BeastEditorCortex.toggleFolder(folder.dataset.folderPath); return; }
      const symbol = event.target.closest('[data-goto-line]'); if (symbol) { BeastEditorCortex.gotoLine(Number(symbol.dataset.gotoLine)); return; }
      const explorerTab = event.target.closest('[data-explorer-tab]'); if (explorerTab) { BeastEditorCortex.setExplorerTab(explorerTab.dataset.explorerTab); if(explorerTab.dataset.explorerTab==='changes')refreshGit(); return; }
      const searchAction=event.target.closest('[data-workspace-search-action]')?.dataset.workspaceSearchAction;if(searchAction){await runWorkspaceSearch(searchAction==='preview'?'preview':searchAction==='apply'?'apply':'search');return;}
      const action = event.target.closest('[data-workspace-action]')?.dataset.workspaceAction;
      if (action === 'zoom-in') { await applyZoom(zoomLevel + 1); return; }
      if (action === 'zoom-out') { await applyZoom(zoomLevel - 1); return; }
      if (action === 'zoom-reset') { await applyZoom(0,{reset:true}); return; }
      if (action === 'choose') { try { await BeastDesktopBridge.chooseWorkspace(); await BeastDesktopBridge.listFiles({ signal }); await BeastEditorCortex.restoreTabs(); } catch (error) { BeastStore.patch('workspace', { error: String(error.message || error) }); } return; }
      if (action === 'add-folder') { try { const result=await BeastDesktopBridge.addWorkspaceFolder(); if(result?.folders)await BeastDesktopBridge.listFiles({ signal }); } catch (error) { BeastStore.patch('workspace', { error: String(error.message || error) }); } return; }
      if (action === 'refresh') { await BeastDesktopBridge.listFiles({ signal }); return; }
      const emptyAction = event.target.closest('[data-empty-action]')?.dataset.emptyAction;
      if (emptyAction === 'choose') { try { await BeastDesktopBridge.chooseWorkspace(); await BeastDesktopBridge.listFiles({ signal }); await BeastEditorCortex.restoreTabs(); } catch (error) { BeastStore.patch('workspace', { error: String(error.message || error) }); } return; }
      if (emptyAction === 'agent') { BeastAICoding.setOpen(true); root.querySelector('[data-ai-prompt]')?.focus(); return; }
      const removeFolder=event.target.closest('[data-workspace-folder-remove]')?.dataset.workspaceFolderRemove;if(removeFolder){try{const result=await BeastDesktopBridge.removeWorkspaceFolder(removeFolder);if(!result?.ok)throw new Error(result?.error||'Unable to remove workspace folder.');await BeastDesktopBridge.listFiles({signal});}catch(error){BeastStore.patch('workspace',{error:String(error.message||error)});}return;}
      const intelAction = event.target.closest('[data-intel-action]')?.dataset.intelAction;
      if (intelAction === 'context' || intelAction === 'agent') { BeastAICoding.setOpen(true); if (intelAction === 'context') BeastAICoding.addActiveFile(); root.querySelector('[data-ai-prompt]')?.focus(); return; }
      if (intelAction === 'crystal') { await BeastRouter.navigate('crystallization'); return; }
      if (intelAction === 'governance') { await BeastRouter.navigate('source'); return; }
      const editorAction = event.target.closest('[data-editor-action]')?.dataset.editorAction;
      if (editorAction === 'split') { BeastEditorCortex.splitGroup('horizontal'); return; }
      if (editorAction === 'split-vertical') { BeastEditorCortex.splitGroup('vertical'); return; }
      if (editorAction === 'move-group') { BeastEditorCortex.moveActiveToNextGroup(); return; }
      if (editorAction === 'close-group') { BeastEditorCortex.closeActiveGroup(); return; }
      if (editorAction === 'pin') { try { const active=BeastStore.get().editor.activePath; const owner=Object.values(window.BeastEditorGroups.snapshot().groups).find(group=>group.tabs.includes(active)); if(owner?.pinnedDocumentIds.includes(active)) BeastEditorCortex.unpinActive(); else BeastEditorCortex.pinActive(); } catch(error) { BeastStore.patch('workspace',{error:String(error.message||error)}); } return; }
      if (editorAction === 'reopen') { try { await BeastEditorCortex.reopenClosedEditor(); } catch(error) { BeastStore.patch('workspace',{error:String(error.message||error)}); } return; }
      if (editorAction === 'revert') { BeastEditorCortex.revertActive(); return; }
      if (editorAction === 'save-remote') { try { await BeastEditorCortex.saveActive(); BeastFX.trigger('success',event.target,{size:180}); } catch(error) { BeastStore.patch('workspace',{error:String(error.message||error)});BeastFX.trigger('warning',event.target,{size:180}); } return; }
      if (editorAction === 'assist') {
        const path=BeastStore.get().editor.activePath;
        if (!path) { BeastStore.patch('workspace',{error:'Open a file first, then Ask AI can use it as the coding context.'}); return; }
        BeastAICoding.setOpen(true);
        BeastAICoding.addActiveFile();
        root.querySelector('[data-ai-prompt]')?.focus();
        return;
      }
      if (editorAction === 'draft') {
        try { await BeastEditorCortex.draftSourcePlan(); BeastFX.trigger('success', event.target, { size: 240 }); await BeastRouter.navigate('source'); }
        catch (error) { BeastStore.patch('sourcePlan', { status: 'error', message: String(error.message || error), error: String(error.message || error) }); BeastFX.trigger('warning', event.target, { size: 220 }); }
        return;
      }
      const op = event.target.closest('[data-file-op]')?.dataset.fileOp;
      if (!op) return;
      if (op === 'git-refresh') { await refreshGit(); return; }
      if (['git-stage','git-unstage','git-discard'].includes(op)) {
        try { const active=BeastStore.get().editor.activePath;const change=gitState.changes.find(item=>item.path===active);if(!change){BeastStore.patch('workspace',{error:'Open a changed local file before using a Git action.'});return;}
          const action=op.replace('git-');if(action==='discard'&&!(await workspaceConfirm(root,{title:'Discard uncommitted changes?',message:`${active} cannot be restored from BEAST after discard.`,confirmLabel:'Discard'})))return;
          const result=await window.beastDesktop.workspaceGitAction({action,path:active});if(!result.ok)throw new Error(result.error||result.stderr||'Git action failed.');BeastStore.addLedger(`Git ${action}: ${active} · ${result.receipt?.id||''}`);await refreshGit();return;
        } catch(error) { BeastStore.patch('workspace',{error:String(error.message||error)});return; }
      }
      if (op === 'toggle-mode') { BeastEditorCortex.setExplorerMode(BeastStore.get().editor.explorerMode === 'tree' ? 'flat' : 'tree'); return; }
      const activePath = BeastStore.get().editor.activePath;
      let operation = null;
      if (op === 'new-file' || op === 'new-folder') {
        const suggested = op === 'new-folder' ? 'src/new_module' : 'src/new_file.py';
        const path = await workspaceTextDialog(root,{title:op === 'new-folder' ? 'New folder path' : 'New file path',value:suggested,confirmLabel:op === 'new-folder' ? 'Create folder' : 'Create file'}); if (!path) return;
        operation = { op: op === 'new-folder' ? 'create_folder' : 'create_file', path, content: '' };
      }
      if (op === 'rename') { if (!activePath) return; const target = await workspaceTextDialog(root,{title:'Rename active file to',value:activePath,confirmLabel:'Rename'}); if (!target || target === activePath) return; operation = { op: 'rename', path: activePath, target }; }
      if (op === 'delete') { if (!activePath) return; operation = { op: 'delete_file', path: activePath }; }
      if (!operation) return;
      try {
        const receipt = await BeastDesktopBridge.classifyFileOperation(operation, { signal });
        if (receipt.decision === 'block') throw new Error('Safety Governor blocked this operation.');
        if (!(await workspaceConfirm(root,{title:'Confirm governed file operation',message:`${operation.op}: ${operation.path}${operation.target ? ` -> ${operation.target}` : ''}. Safety decision: ${receipt.decision || 'allow'}`,confirmLabel:'Apply'}))) return;
        const result = await BeastDesktopBridge.fileOperation(operation, { signal });
        if (!result?.ok) throw new Error(result?.error || 'File operation failed.');
        if (op === 'delete') BeastEditorCortex.closeTab(activePath);
        await BeastDesktopBridge.listFiles({ signal });
        if (op === 'new-file') await BeastEditorCortex.openFile(result.path || operation.path, { signal });
        if (op === 'rename') { BeastEditorCortex.closeTab(activePath); await BeastEditorCortex.openFile(result.target || operation.target, { signal }); }
        BeastStore.addLedger(`Governed file operation complete: ${operation.op}`);
      } catch (error) { BeastStore.patch('workspace', { error: String(error.message || error) }); }
    });

    root.addEventListener('input', event => {
      if (event.target.matches('[data-ai-prompt]')) BeastAICoding.setPrompt(event.target.value);
      if (event.target.matches('[data-workspace-search-query]')) searchState.query=event.target.value;
      if (event.target.matches('[data-workspace-search-replace]')) searchState.replacement=event.target.value;
      if (event.target.matches('[data-git-commit-message]')) gitCommitMessage=event.target.value;
      if (event.target.matches('[data-git-new-branch]')) gitNewBranchName=event.target.value;
      if (event.target.matches('[data-notebook-cell-source]')) {
        BeastEditorCortex.setNotebookCellSource(event.target.dataset.notebookCellSource, event.target.value);
        const preview = root.querySelector(`[data-notebook-markdown-preview="${CSS.escape(event.target.dataset.notebookCellSource)}"]`);
        if (preview) preview.innerHTML = markdownPreview(event.target.value);
      }
    });
    root.addEventListener('change', event => {
      if (event.target.matches('[data-ai-model]')) BeastAICoding.syncModel(event.target.value);
      if (event.target.matches('[data-git-branch-select]')&&event.target.value&&event.target.value!==gitState.branchName) changeGitBranch('checkout',event.target.value);
      if(event.target.matches('[data-git-rebase-base]'))gitDetails={...gitDetails,rebaseBase:event.target.value};
      if(event.target.matches('[data-git-cherry-pick]'))gitDetails={...gitDetails,cherryPick:event.target.value};
    });
    root.addEventListener('dblclick', event => { const tab=event.target.closest('[data-editor-tab]'); if(tab) window.BeastTabLifecycle?.pin?.(tab.dataset.editorTab, tab.dataset.editorGroup); });
    root.addEventListener('auxclick', event => { const tab=event.target.closest('[data-editor-tab]'); if(tab && event.button===1) BeastEditorCortex.closeTab(tab.dataset.editorTab); });
    root.addEventListener('dragstart', event => { const tab=event.target.closest('[data-editor-tab]'); if(tab){ event.dataTransfer.setData('text/beast-editor-tab', JSON.stringify({documentId:tab.dataset.editorTab,groupId:tab.dataset.editorGroup})); event.dataTransfer.effectAllowed='move'; } });
    root.addEventListener('dragover', event => { if(event.target.closest('[data-editor-tabs]')) event.preventDefault(); });
    root.addEventListener('drop', event => { const host=event.target.closest('[data-editor-tabs]'); if(!host)return; event.preventDefault(); try{ const data=JSON.parse(event.dataTransfer.getData('text/beast-editor-tab')); const target=window.BeastEditorGroups.snapshot().activeGroupId; if(data.groupId===target){ const tabs=[...host.querySelectorAll('[data-editor-tab]')]; const targetTab=event.target.closest('[data-editor-tab]'); const index=targetTab?Math.max(0,tabs.indexOf(targetTab)):tabs.length; window.BeastEditorGroups.reorderDocument(data.documentId,target,index); } else window.BeastEditorGroups.moveDocument(data.documentId,data.groupId,target,{preview:false}); }catch(error){ BeastStore.patch('workspace',{error:String(error.message||error)}); } });

    root.addEventListener('keydown', event => {
      if(event.key==='Escape'&&BeastStore.get().aiCoding.expanded&&event.target.closest('[data-ai-panel]')){event.preventDefault();BeastAICoding.setExpanded(false);return;}
      const mod=event.ctrlKey||event.metaKey;
      if(mod&&!event.altKey&&event.key.toLowerCase()==='s'&&!event.target.matches('input,textarea,[contenteditable="true"]')){event.preventDefault();BeastEditorCortex.saveActive().catch(error=>BeastStore.patch('workspace',{error:String(error.message||error)}));return;}
      if(mod&&!event.altKey&&event.key.toLowerCase()==='w'&&!event.target.matches('input,textarea,[contenteditable="true"]')){event.preventDefault();const active=BeastStore.get().editor.activePath;if(active)BeastEditorCortex.closeTab(active).catch(error=>BeastStore.patch('workspace',{error:String(error.message||error)}));return;}
      if(mod&&!event.altKey&&event.key==='Tab'&&!event.target.matches('input,textarea,[contenteditable="true"]')){event.preventDefault();const tabs=BeastStore.get().editor.openTabs||[];const active=BeastStore.get().editor.activePath;const next=tabs[(Math.max(0,tabs.indexOf(active))+1)%Math.max(1,tabs.length)];if(next)BeastEditorCortex.activate(next);return;}
      if(mod&&event.shiftKey&&event.key.toLowerCase()==='p'&&!event.target.matches('input,textarea,[contenteditable="true"]')){event.preventDefault();window.BeastCommandPalette?.open?.('commands');return;}
      if(event.target.matches('[data-git-commit-message]')&&(event.ctrlKey||event.metaKey)&&event.key==='Enter'){event.preventDefault();commitGit();return;}
      if(event.target.matches('[data-git-new-branch]')&&event.key==='Enter'){event.preventDefault();changeGitBranch('create',gitNewBranchName);return;}
      if((event.ctrlKey||event.metaKey)&&event.shiftKey&&event.key.toLowerCase()==='g'){event.preventDefault();BeastEditorCortex.setExplorerTab('changes');refreshGit().then(()=>root.querySelector('[data-git-commit-message]')?.focus());return;}
      if (event.target.matches('[data-notebook-cell-source]') && (event.ctrlKey || event.metaKey) && event.key === 'Enter') {
        const cell = event.target.closest('[data-notebook-cell]');
        if (cell?.classList.contains('code')) { event.preventDefault(); BeastEditorCortex.runNotebookCell(event.target.dataset.notebookCellSource).catch(error => BeastStore.patch('workspace', { error: String(error.message || error) })); }
        return;
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'i') {
        event.preventDefault();
        BeastAICoding.setOpen(true);
        BeastAICoding.addActiveFile();
        root.querySelector('[data-ai-prompt]')?.focus();
        return;
      }
      if (event.target.matches('[data-ai-prompt]') && event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        BeastAICoding.send(event.target.value, { model:root.querySelector('[data-ai-model]')?.value }).catch(error => BeastStore.patch('aiCoding',{streaming:false,status:'error',error:String(error.message || error)}));
      }
    });
    root.addEventListener('click', async event => {
      const suggestionTarget=event.target.closest('[data-ai-suggestion]');const suggestion=suggestionTarget?.dataset.aiSuggestion;
      if (suggestion) { const suggestedMode=suggestionTarget.dataset.aiSuggestionMode;if(suggestedMode)BeastAICoding.setMode(suggestedMode);BeastAICoding.addActiveFile();BeastAICoding.setPrompt(suggestion); const prompt = root.querySelector('[data-ai-prompt]'); prompt.value = suggestion; prompt.focus(); return; }
      const aiPreviewPath=event.target.closest('[data-ai-preview-path]')?.dataset.aiPreviewPath;
      if(aiPreviewPath){const plan=BeastStore.get().sourcePlan?.plan;if(plan)await openAiDiff(plan,aiPreviewPath);return;}
      const copyId = event.target.closest('[data-ai-copy-id]')?.dataset.aiCopyId;
      if (copyId) {
        const message = BeastStore.get().aiCoding.messages.find(item => item.id === copyId);
        if (message?.content && navigator.clipboard?.writeText) await navigator.clipboard.writeText(message.content);
        return;
      }
      const contextAction = event.target.closest('[data-phase5-context-action]');
      if (contextAction) {
        try {
          await BeastOperationsConsole.decideContext(contextAction.dataset.contextItemId, contextAction.dataset.phase5ContextAction, { provider:'ollama' });
          durableConsoleKey = '';
          await refreshDurableConsole(BeastStore.get(), true);
        } catch (error) { BeastStore.patch('aiCoding', { status:'error', error:String(error.message || error) }); }
        return;
      }
      const mode = event.target.closest('[data-ai-mode]')?.dataset.aiMode;
      if (mode) { BeastAICoding.setMode(mode); return; }
      const contextPath = event.target.closest('[data-ai-context-path]')?.dataset.aiContextPath;
      if (contextPath) { BeastAICoding.toggleContext(contextPath); return; }
      const suggestionPath=event.target.closest('[data-ai-accept-suggestion]')?.dataset.aiAcceptSuggestion;
      if(suggestionPath){BeastAICoding.acceptSuggestedContext(suggestionPath);return;}
      const action = event.target.closest('[data-ai-action]')?.dataset.aiAction;
      if (action === 'jump-latest') { jumpToLatestAiOutput(); return; }
      if (!action) return;
      try {
        if (action === 'close') BeastAICoding.setOpen(false);
        if (action === 'expand') BeastAICoding.setExpanded(!BeastStore.get().aiCoding.expanded);
        if (action === 'active-file') BeastAICoding.addActiveFile();
        if (action === 'selection') BeastAICoding.captureSelection();
        if (action === 'remove-selection') BeastAICoding.removeSelection();
        if (action === 'context-file') {
          const path = await workspaceTextDialog(root,{title:'Attach workspace file',message:'Enter a relative path from the current workspace.',value:BeastStore.get().editor.activePath || '',confirmLabel:'Attach'});
          if (path && BeastStore.get().workspace.files.some(row => row.path === path)) BeastAICoding.toggleContext(path);
          else if (path) throw new Error(`Workspace file not found: ${path}`);
        }
        if (action === 'suggest-context') await BeastAICoding.suggestContext(root.querySelector('[data-ai-prompt]')?.value);
        if (action === 'agent-suggest-context') {
          const latestUser=[...(BeastStore.get().aiCoding.messages||[])].reverse().find(item=>item.role==='user'&&String(item.content||'').trim());
          await BeastAICoding.suggestContext(root.querySelector('[data-ai-prompt]')?.value || latestUser?.content || '');
        }
        if (action === 'agent-open-terminal') {
          const command=event.target.closest('[data-ai-action]')?.dataset.agentCommand || '';
          if(command && window.BeastTerminalToolingDoctorBridge?.setCommand) BeastTerminalToolingDoctorBridge.setCommand(command);
          await BeastRouter.navigate('terminal');
        }
        if (action === 'send') await BeastAICoding.send(root.querySelector('[data-ai-prompt]').value, { model:root.querySelector('[data-ai-model]')?.value });
        if (action === 'agent-repair-packet') await BeastAICoding.recoverInvalidPacket({ model:root.querySelector('[data-ai-model]')?.value });
        if (action === 'retry') await BeastAICoding.retryLastRequest({ model:root.querySelector('[data-ai-model]')?.value });
        if (action === 'worktree-agent') await BeastAICoding.runInWorktree(root.querySelector('[data-ai-prompt]').value, { model:root.querySelector('[data-ai-model]')?.value });
        if (action === 'cancel') BeastAICoding.cancel();
        if (action === 'clear' && await workspaceConfirm(root,{title:'Clear AI coding conversation?',message:'The current conversation messages will be removed from this workspace view.',confirmLabel:'Clear'})) BeastAICoding.clear();
        if (action === 'diff') { const plan=BeastStore.get().sourcePlan?.plan; if(plan) await openAiDiff(plan, BeastStore.get().editor.activePath); return; }
        if (action === 'agent-context') await BeastAICoding.resolveRequestedContext();
        if (action === 'agent-continue-context') await BeastAICoding.continueWithAddedContext({ model:root.querySelector('[data-ai-model]')?.value });
        if (action === 'agent-verify' && await workspaceConfirm(root,{title:'Run agent requested checks?',message:'BEAST will run only allowlisted verifier commands in a temporary isolated workspace. Your working tree will not be modified.',confirmLabel:'Run checks'})) await BeastAICoding.verifyRequestedChecks();
        if (action === 'sourceplan') await BeastAICoding.openSourcePlan();
      } catch (error) { BeastStore.patch('aiCoding',{streaming:false,status:'error',error:String(error.message || error)}); }
    });

    filter.addEventListener('input', () => { lastExplorerKey = ''; patch(BeastStore.get()); });
    BeastAICoding.restore();
    if (!BeastStore.get().models.registry.length) queueMicrotask(() => BeastModelAgentBridge.refreshModels({signal}).catch(() => {}));
    if (!BeastStore.get().workspace.indexedAt && BeastStore.get().workspace.root) queueMicrotask(() => BeastDesktopBridge.listFiles({ signal }));

    return { node: root, dispose() { disposed = true;if(aiScrollFrame)cancelAnimationFrame(aiScrollFrame);window.BeastVisualRuntime?.setWorkload?.('idle');resizeCleanup?.();gitDiffMountToken+=1;gitDiffCleanup?.();unsubscribe();document.removeEventListener('beast:source-control-root',selectRepository);document.removeEventListener('beast:ai-proposal-ready',handleAiProposalReady); window.BeastEditorWorkbench?.unmount?.(); BeastEditorCortex.unmount(); } };
  }

  window.BeastWorkspacePage = { renderer };
})();
