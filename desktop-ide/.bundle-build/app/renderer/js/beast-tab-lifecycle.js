(() => {
  const VERSION = '6.3';
  const MAX_HISTORY = 50;

  function groups() {
    if (!window.BeastEditorGroups) throw new Error('Phase 6.2 editor groups are unavailable.');
    return window.BeastEditorGroups;
  }
  function owner(documentId) {
    const layout = groups().snapshot();
    return Object.values(layout.groups || {}).find(group => group.tabs.includes(documentId)) || null;
  }
  function documentState(documentId) {
    return window.BeastEditorDocumentModel?.get?.(documentId) || null;
  }
  function isDirty(documentId) {
    const canonical = documentState(documentId);
    if (canonical) return Boolean(canonical.dirty);
    return Boolean(window.BeastStore?.get?.().editor?.dirtyPaths?.includes(documentId));
  }
  function fileName(value) { return String(value || '').split(/[\\/]/).pop() || 'Untitled'; }

  function chooseDirtyClose(documentId) {
    return new Promise(resolve => {
      const prior = document.querySelector('[data-beast-dirty-close]');
      prior?.remove();
      const overlay = document.createElement('div');
      overlay.dataset.beastDirtyClose = 'true';
      overlay.className = 'beast-tab-close-overlay';
      overlay.innerHTML = `<section class="beast-tab-close-dialog" role="dialog" aria-modal="true" aria-label="Unsaved editor">
        <header><b>Unsaved changes</b><span>${fileName(documentId)}</span></header>
        <p>This editor contains changes that have not been saved or promoted. Choose what BEAST should do.</p>
        <footer>
          <button type="button" data-tab-close-choice="cancel">Keep open</button>
          <button type="button" data-tab-close-choice="discard">Discard changes</button>
          <button type="button" class="primary" data-tab-close-choice="recover">Close and keep recovery buffer</button>
        </footer>
      </section>`;
      const finish = choice => { overlay.remove(); resolve(choice); };
      overlay.addEventListener('click', event => {
        const button = event.target.closest('[data-tab-close-choice]');
        if (button) finish(button.dataset.tabCloseChoice);
        else if (event.target === overlay) finish('cancel');
      });
      overlay.addEventListener('keydown', event => { if (event.key === 'Escape') finish('cancel'); });
      document.body.appendChild(overlay);
      overlay.querySelector('[data-tab-close-choice="recover"]')?.focus();
    });
  }

  async function requestClose(documentId, options = {}) {
    const group = owner(documentId);
    if (!group) return { closed: false, reason: 'not_open' };
    let choice = options.choice || '';
    if (isDirty(documentId) && !choice) choice = await chooseDirtyClose(documentId);
    if (choice === 'cancel') return { closed: false, reason: 'cancelled' };
    if (choice === 'discard') window.BeastEditorCortex?.revertPath?.(documentId);
    groups().closeDocument(documentId, group.groupId, { reason: choice || options.reason || 'user' });
    return { closed: true, groupId: group.groupId, recoveryPreserved: choice !== 'discard' };
  }

  function pin(documentId, groupId = '') {
    const group = groupId ? groups().snapshot().groups[groupId] : owner(documentId);
    if (!group) throw new Error('Document is not open.');
    return groups().pinDocument(documentId, group.groupId);
  }
  function unpin(documentId, groupId = '') {
    const group = groupId ? groups().snapshot().groups[groupId] : owner(documentId);
    if (!group) throw new Error('Document is not open.');
    if (isDirty(documentId)) throw new Error('Dirty editors remain pinned until saved or reverted.');
    return groups().unpinDocument(documentId, group.groupId);
  }
  function markEdited(documentId) { return groups().setDocumentDirty(documentId, true); }

  async function reopenClosed() {
    const layout = groups().snapshot();
    const record = layout.recentlyClosedEditors?.[0];
    if (!record) return null;
    const restored = groups().reopenClosedEditor({ groupId: record.groupId });
    await window.BeastEditorCortex?.openFile?.(record.documentId, {
      activate: true,
      groupId: restored.restoredGroupId,
      preview: record.preview,
      pinned: record.pinned,
      restore: true
    });
    return restored;
  }

  function history() { return (groups().snapshot().recentlyClosedEditors || []).slice(0, MAX_HISTORY); }
  window.BeastTabLifecycle = { VERSION, requestClose, pin, unpin, markEdited, reopenClosed, history, isDirty };
})();
