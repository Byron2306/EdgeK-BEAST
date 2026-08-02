(() => {
  const completionKey='beast.v2.onboarding.completed';
  const dismissedKey='beast.v2.onboarding.dismissed';
  let host=null;
  let unsubscribe=null;

  function template(){
    const node=document.createElement('section');node.className='beast-onboarding hidden';node.dataset.onboarding='';node.setAttribute('role','dialog');node.setAttribute('aria-modal','true');node.setAttribute('aria-labelledby','beastOnboardingTitle');node.innerHTML=`
      <div class="beast-onboarding-backdrop" data-onboarding-action="dismiss"></div>
      <div class="beast-onboarding-shell">
        <header><div class="beast-onboarding-brand"><span><img src="${BeastAssets.icon('agent-premium')}" alt=""></span><div><small>BEAST IDE // FIRST MISSION</small><h2 id="beastOnboardingTitle">From repository to governed result</h2><p>One guided runway connects workspace, mission, language intelligence, trust, tools, AI edits, review, evidence, and reusable compute.</p></div></div><button type="button" data-onboarding-action="dismiss" aria-label="Close setup journey">×</button></header>
        <div class="beast-onboarding-body">
          <ol class="beast-onboarding-steps" aria-label="Setup progress">
            <li data-onboarding-step="workspace"><b>1</b><span><strong>Workspace</strong><small data-onboarding-workspace>Choose a repository</small></span><i>○</i></li>
            <li data-onboarding-step="mission"><b>2</b><span><strong>Mission</strong><small>Define the outcome</small></span><i>○</i></li>
            <li data-onboarding-step="preflight"><b>3</b><span><strong>Trust + Tools</strong><small>Verify boundaries and capabilities</small></span><i>○</i></li>
            <li data-onboarding-step="build"><b>4</b><span><strong>Build</strong><small>Edit with Monaco + BEAST AI</small></span><i>→</i></li>
            <li data-onboarding-step="prove"><b>5</b><span><strong>Prove + Reuse</strong><small>Review, evidence, crystallise</small></span><i>→</i></li>
          </ol>
          <main class="beast-onboarding-main">
            <section class="beast-onboarding-workspace"><div><span class="tiny">ACTIVE REPOSITORY</span><strong data-onboarding-root>None selected</strong><small data-onboarding-file-count>0 indexed files</small></div><button type="button" class="beast-button secondary" data-onboarding-action="workspace">Choose Folder</button></section>
            <label class="beast-onboarding-objective"><span><b>What are we building?</b><small>State the outcome. BEAST will carry this mission through context, edits, verification, and evidence.</small></span><textarea data-onboarding-objective rows="4" placeholder="Example: Add workspace-wide symbol search with keyboard navigation and focused tests."></textarea></label>
            <section class="beast-onboarding-preflight">
              <article><img src="${BeastAssets.icon('trust-core')}" alt=""><span><b>Trust boundary</b><small data-onboarding-trust>Not checked</small></span></article>
              <article><img src="${BeastAssets.icon('tooling')}" alt=""><span><b>Tooling forge</b><small data-onboarding-tools>Not checked</small></span></article>
              <article><img src="${BeastAssets.icon('plugins')}" alt=""><span><b>IDE compatibility</b><small data-onboarding-compat>Not checked</small></span></article>
              <button type="button" class="beast-button" data-onboarding-action="preflight">Run Preflight</button>
            </section>
            <div class="beast-onboarding-path"><span>Mission</span><i>→</i><span>Files + AI</span><i>→</i><span>SourcePlan</span><i>→</i><span>Review</span><i>→</i><span>Evidence</span><i>→</i><span>Crystal</span></div>
          </main>
        </div>
        <footer><span data-onboarding-status>Nothing changes until you begin the mission.</span><div><button type="button" class="beast-button secondary" data-onboarding-action="mission">Open Mission Control</button><button type="button" class="beast-button hot" data-onboarding-action="start">Begin in Editor Cortex <span>→</span></button></div></footer>
      </div>`;return node;
  }

  function patch(state){if(!host)return;const objective=host.querySelector('[data-onboarding-objective]');if(document.activeElement!==objective&&objective.value!==String(state.mission.draftObjective||''))objective.value=String(state.mission.draftObjective||'');host.querySelector('[data-onboarding-root]').textContent=state.workspace.root||'None selected';host.querySelector('[data-onboarding-workspace]').textContent=state.workspace.root?state.workspace.root.split(/[\\/]/).pop():'Choose a repository';host.querySelector('[data-onboarding-file-count]').textContent=state.workspace.loading?'Indexing…':`${state.workspace.files.length} indexed files`;
    host.querySelector('[data-onboarding-trust]').textContent=state.trust.updatedAt?`${state.trust.status} · ${state.trust.score}%`:'Not checked';host.querySelector('[data-onboarding-tools]').textContent=state.tooling.updatedAt?`${state.tooling.status} · ${(state.tooling.capabilities||[]).length} capabilities`:'Not checked';host.querySelector('[data-onboarding-compat]').textContent=state.compatibility.updatedAt?`${state.compatibility.summary.available}/${state.compatibility.summary.total} local capabilities`:'Not checked';
    const complete={workspace:Boolean(state.workspace.root),mission:Boolean(String(state.mission.draftObjective||'').trim()),preflight:Boolean(state.trust.updatedAt&&state.tooling.updatedAt&&state.compatibility.updatedAt)};Object.entries(complete).forEach(([key,ok])=>{const step=host.querySelector(`[data-onboarding-step="${key}"]`);step?.classList.toggle('complete',ok);if(step&&step.querySelector('i'))step.querySelector('i').textContent=ok?'✓':'○';});
  }

  function open(){if(!host)return;host.classList.remove('hidden');document.body.classList.add('onboarding-open');host.querySelector('[data-onboarding-objective]')?.focus();}
  function close(){if(!host)return;host.classList.add('hidden');document.body.classList.remove('onboarding-open');}

  async function act(action,target){const status=host.querySelector('[data-onboarding-status]');try{
    if(action==='dismiss'){localStorage.setItem(dismissedKey,'1');close();return;}
    if(action==='workspace'){status.textContent='Selecting and indexing the workspace…';await BeastDesktopBridge.chooseWorkspace();await BeastDesktopBridge.listFiles();status.textContent='Workspace ready. Define the mission outcome.';return;}
    if(action==='preflight'){status.textContent='Checking trust, tools, and IDE protocol capabilities…';target.disabled=true;const results=await Promise.allSettled([BeastTrustMemoryBridge.refreshTrust(),BeastTerminalToolingDoctorBridge.refreshTooling(),BeastIDECompatibility.refresh()]);const failed=results.filter(x=>x.status==='rejected').length;status.textContent=failed?`Preflight completed with ${failed} unavailable live service${failed===1?'':'s'}. Local capabilities remain visible.`:'Preflight complete. Trust and tools are ready.';target.disabled=false;return;}
    if(action==='mission'){close();await BeastRouter.navigate('mission');return;}
    if(action==='start'){const objective=(host.querySelector('[data-onboarding-objective]').value||'').trim();if(!objective){status.textContent='Describe the mission outcome before entering the editor.';host.querySelector('[data-onboarding-objective]').focus();return;}if(!BeastStore.get().workspace.root){status.textContent='Choose a workspace before beginning the mission.';return;}localStorage.setItem('beast.mission.draft',objective);localStorage.setItem(completionKey,new Date().toISOString());BeastStore.patch('mission',{draftObjective:objective,title:objective,status:'In Progress'});BeastAICoding.setPrompt(objective);close();await BeastRouter.navigate('workspace');BeastAICoding.setOpen(true);BeastAICoding.addActiveFile();setTimeout(()=>document.querySelector('[data-ai-prompt]')?.focus(),80);BeastStore.addLedger(`Mission runway started: ${objective}`);}
  }catch(error){target.disabled=false;status.textContent=`Setup action failed: ${String(error.message||error)}`;}}

  function init(){if(host)return;host=template();document.body.append(host);const launcher=document.createElement('button');launcher.type='button';launcher.className='beast-journey-launcher';launcher.dataset.onboardingOpen='';launcher.innerHTML=`<img src="${BeastAssets.icon('mission')}" alt=""><span><b>Mission Journey</b><small>Setup · build · prove</small></span>`;document.body.append(launcher);unsubscribe=BeastStore.subscribe(patch);host.addEventListener('input',event=>{if(!event.target.matches('[data-onboarding-objective]'))return;localStorage.setItem('beast.mission.draft',event.target.value);BeastStore.patch('mission',{draftObjective:event.target.value});});host.addEventListener('click',event=>{const action=event.target.closest('[data-onboarding-action]')?.dataset.onboardingAction;if(action)act(action,event.target.closest('button')||event.target);});launcher.addEventListener('click',open);document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!host.classList.contains('hidden'))close();});if(!localStorage.getItem(completionKey)&&!localStorage.getItem(dismissedKey))setTimeout(open,180);}
  function destroy(){unsubscribe?.();host?.remove();host=null;document.querySelector('.beast-journey-launcher')?.remove();}
  window.BeastOnboarding={init,open,close,destroy};
})();
