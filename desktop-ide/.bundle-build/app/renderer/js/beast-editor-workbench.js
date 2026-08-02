(() => {
  const editors = new Map();
  const disposables = new Map();
  let root = null;
  let unsubscribe = null;
  let renderQueued = false;

  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const nameOf = path => String(path || '').split('/').pop() || 'Untitled';
  function dirty(path) { return window.BeastStore?.get?.().editor?.dirtyPaths?.includes(path); }
  function disposeEditors() {
    for (const list of disposables.values()) for (const item of list) try { item.dispose(); } catch (_) {}
    for (const editor of editors.values()) try { editor.dispose(); } catch (_) {}
    disposables.clear(); editors.clear();
  }
  function leaf(group, active) {
    const tabs = group.tabs.map(path => {
      const pinned = group.pinnedDocumentIds.includes(path);
      const preview = group.previewDocumentId === path;
      return `<button type="button" class="beast-group-tab ${group.activeDocumentId===path?'active':''} ${dirty(path)?'dirty':''} ${pinned?'pinned':''} ${preview?'preview':''}" draggable="true" data-workbench-tab="${esc(path)}" data-workbench-group="${esc(group.groupId)}"><span>${esc(nameOf(path))}</span>${pinned?'<em>◆</em>':''}<i data-workbench-close="${esc(path)}">×</i></button>`;
    }).join('');
    return `<section class="beast-editor-group ${active?'active':''}" data-workbench-group-leaf="${esc(group.groupId)}"><header><div class="beast-group-tabs">${tabs || '<span class="beast-group-empty-tab">EMPTY GROUP</span>'}</div><div class="beast-group-actions"><button data-workbench-split="horizontal" title="Split right">⇥</button><button data-workbench-split="vertical" title="Split below">⇩</button><button data-workbench-merge title="Merge group">⊟</button></div></header><div class="beast-group-editor" data-workbench-editor="${esc(group.groupId)}"></div><textarea class="beast-group-fallback hidden" data-workbench-fallback="${esc(group.groupId)}" spellcheck="false"></textarea><div class="beast-group-empty ${group.activeDocumentId?'hidden':''}"><b>EDITOR GROUP</b><span>Drag a tab here or open a file.</span></div></section>`;
  }
  function tree(node, state) {
    if (!node) return '';
    if (node.type === 'group') return leaf(state.groups[node.groupId], state.activeGroupId === node.groupId);
    const direction = node.orientation === 'vertical' ? 'rows' : 'columns';
    const first = Math.round(Number(node.ratio || .5) * 1000) / 10;
    return `<div class="beast-editor-split ${direction}" data-workbench-split-node style="--split-first:${first}%">${tree(node.first,state)}<div class="beast-editor-divider" data-workbench-divider data-orientation="${esc(node.orientation)}" data-first-group="${esc(firstGroup(node.first))}" role="separator" tabindex="0"></div>${tree(node.second,state)}</div>`;
  }
  function firstGroup(node) { return node?.type === 'group' ? node.groupId : firstGroup(node?.first); }
  async function createEditor(groupId, group) {
    const host = root?.querySelector(`[data-workbench-editor="${CSS.escape(groupId)}"]`);
    const fallback = root?.querySelector(`[data-workbench-fallback="${CSS.escape(groupId)}"]`);
    if (!host) return;
    const api = await window.BeastEditorCortex.ensureMonaco();
    if (!root?.isConnected || !host.isConnected) return;
    if (!api) {
      host.classList.add('hidden'); fallback.classList.remove('hidden');
      const snap = window.BeastEditorCortex.documentSnapshot(group.activeDocumentId);
      fallback.value = snap?.text || '';
      fallback.readOnly = !group.activeDocumentId;
      fallback.addEventListener('input', () => window.BeastEditorCortex.commitModelValue(group.activeDocumentId, fallback.value, {groupId}));
      return;
    }
    const editor = api.editor.create(host, {theme:'beast-phase2',automaticLayout:true,minimap:{enabled:false},fontSize:13,fontFamily:'JetBrains Mono, Cascadia Code, monospace',lineNumbers:'on',scrollBeyondLastLine:false,wordWrap:'off',glyphMargin:true,padding:{top:9,bottom:10},cursorBlinking:'phase',bracketPairColorization:{enabled:true},guides:{bracketPairs:true,indentation:true}});
    editors.set(groupId, editor);
    const model = window.BeastEditorCortex.modelFor(group.activeDocumentId);
    editor.setModel(model);
    const ds=[];
    ds.push(editor.onDidFocusEditorText(() => { const current=window.BeastEditorGroups.snapshot(); if(current.activeGroupId!==groupId) window.BeastEditorGroups.setActiveGroup(groupId); if(group.activeDocumentId && window.BeastStore.get().editor.activePath!==group.activeDocumentId) window.BeastEditorCortex.activate(group.activeDocumentId,groupId); }));
    ds.push(editor.onDidChangeModelContent(() => { if(group.activeDocumentId) window.BeastEditorCortex.commitModelValue(group.activeDocumentId, editor.getValue(), {groupId}); }));
    ds.push(editor.onDidChangeCursorPosition(e => { if(window.BeastEditorGroups.snapshot().activeGroupId===groupId) window.BeastEditorCortex.setCursorPosition(e.position); }));
    disposables.set(groupId, ds);
    window.BeastEditorSafety?.apply?.(group.activeDocumentId,[editor]);
  }
  async function render() {
    if (!root?.isConnected) return;
    renderQueued=false; disposeEditors();
    const state=window.BeastEditorGroups.snapshot();
    root.innerHTML=tree(state.tree,state);
    for (const [id,group] of Object.entries(state.groups)) await createEditor(id,group);
  }
  function schedule() { if(renderQueued)return; renderQueued=true; requestAnimationFrame(render); }
  function bindEvents() {
    root.addEventListener('click', async event => {
      const leafNode=event.target.closest('[data-workbench-group-leaf]'); const groupId=leafNode?.dataset.workbenchGroupLeaf;
      const close=event.target.closest('[data-workbench-close]');
      if(close){event.stopPropagation();await window.BeastEditorCortex.closeTab(close.dataset.workbenchClose,{groupId});return;}
      const tab=event.target.closest('[data-workbench-tab]');
      if(tab){window.BeastEditorGroups.setActiveGroup(tab.dataset.workbenchGroup);window.BeastEditorCortex.activate(tab.dataset.workbenchTab,tab.dataset.workbenchGroup);return;}
      const split=event.target.closest('[data-workbench-split]');
      if(split&&groupId){window.BeastEditorGroups.setActiveGroup(groupId);window.BeastEditorGroups.splitGroup(groupId,split.dataset.workbenchSplit);return;}
      if(event.target.closest('[data-workbench-merge]')&&groupId){const state=window.BeastEditorGroups.snapshot();const target=Object.keys(state.groups).find(id=>id!==groupId);if(target)window.BeastEditorGroups.closeGroup(groupId,{moveTabsTo:target});return;}
      if(groupId)window.BeastEditorGroups.setActiveGroup(groupId);
    });
    root.addEventListener('dragstart', event => {const tab=event.target.closest('[data-workbench-tab]');if(!tab)return;event.dataTransfer.effectAllowed='move';event.dataTransfer.setData('application/x-beast-editor-tab',JSON.stringify({documentId:tab.dataset.workbenchTab,groupId:tab.dataset.workbenchGroup}));});
    root.addEventListener('dragover', event => {if(event.target.closest('[data-workbench-group-leaf]')){event.preventDefault();event.dataTransfer.dropEffect='move';}});
    root.addEventListener('drop', event => {const leafNode=event.target.closest('[data-workbench-group-leaf]');if(!leafNode)return;event.preventDefault();try{const data=JSON.parse(event.dataTransfer.getData('application/x-beast-editor-tab'));const to=leafNode.dataset.workbenchGroupLeaf;if(data.groupId!==to)window.BeastEditorGroups.moveDocument(data.documentId,data.groupId,to,{preview:false});else{const tabs=[...leafNode.querySelectorAll('[data-workbench-tab]')];const target=event.target.closest('[data-workbench-tab]');window.BeastEditorGroups.reorderDocument(data.documentId,to,target?tabs.indexOf(target):tabs.length);}}catch(error){window.BeastStore.patch('workspace',{error:String(error.message||error)});}});
    root.addEventListener('pointerdown', event => {const divider=event.target.closest('[data-workbench-divider]');if(!divider)return;event.preventDefault();const split=divider.parentElement;const groupId=divider.dataset.firstGroup;const rect=split.getBoundingClientRect();const orientation=divider.dataset.orientation;let ratio=.5;const move=e=>{ratio=Math.min(.8,Math.max(.2,orientation==='vertical'?(e.clientY-rect.top)/rect.height:(e.clientX-rect.left)/rect.width));split.style.setProperty('--split-first',`${Math.round(ratio*1000)/10}%`);};const up=()=>{window.removeEventListener('pointermove',move);window.removeEventListener('pointerup',up);try{window.BeastEditorGroups.resizeSplit(groupId,ratio);}catch(_){}};window.addEventListener('pointermove',move);window.addEventListener('pointerup',up);});
  }
  async function mount(host) { unmount(); root=host; root.classList.add('beast-editor-workbench'); bindEvents(); unsubscribe=window.BeastEditorGroups.subscribe(schedule); await render(); return unmount; }
  function unmount(){unsubscribe?.();unsubscribe=null;disposeEditors();if(root)root.replaceChildren();root=null;}
  window.BeastEditorWorkbench={mount,unmount,render:schedule,editorCount:()=>editors.size};
})();
