(() => {
  const VERSION = '6.4';
  const STORAGE_PREFIX = 'beast.phase6.editor-groups.v2';
  const MAX_GROUPS = 8;
  const listeners = new Set();

  let state = null;

  function now() { return Date.now(); }
  function clone(value) { return value == null ? value : JSON.parse(JSON.stringify(value)); }
  function rootKey() {
    const root = window.BeastStore?.get?.().workspace?.root || 'workspace';
    return encodeURIComponent(root);
  }
  function storageKey() { return `${STORAGE_PREFIX}:${rootKey()}`; }
  function uid(prefix = 'group') {
    return `${prefix}_${now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
  }
  function groupNode(groupId) { return { type: 'group', groupId }; }
  function splitNode(orientation, first, second, ratio = 0.5) {
    return { type: 'split', orientation, ratio: clampRatio(ratio), first, second };
  }
  function clampRatio(value) {
    const number = Number(value);
    return Number.isFinite(number) ? Math.min(0.8, Math.max(0.2, number)) : 0.5;
  }
  function createGroup(id = uid()) {
    return {
      groupId: id,
      tabs: [],
      activeDocumentId: '',
      previewDocumentId: '',
      pinnedDocumentIds: [],
      createdAt: now(),
      updatedAt: now()
    };
  }
  function defaultState() {
    const group = createGroup('group_primary');
    return {
      version: VERSION,
      layoutVersion: 1,
      activeGroupId: group.groupId,
      groups: { [group.groupId]: group },
      tree: groupNode(group.groupId),
      recentlyClosedGroups: [],
      recentlyClosedEditors: [],
      updatedAt: now()
    };
  }
  function normalizeGroup(raw, id) {
    const tabs = Array.isArray(raw?.tabs) ? [...new Set(raw.tabs.filter(Boolean).map(String))] : [];
    const pinned = Array.isArray(raw?.pinnedDocumentIds)
      ? [...new Set(raw.pinnedDocumentIds.filter(item => tabs.includes(item)).map(String))]
      : [];
    const active = tabs.includes(raw?.activeDocumentId) ? raw.activeDocumentId : (tabs.at(-1) || '');
    const preview = tabs.includes(raw?.previewDocumentId) && !pinned.includes(raw.previewDocumentId)
      ? raw.previewDocumentId
      : '';
    return {
      groupId: id,
      tabs,
      activeDocumentId: active,
      previewDocumentId: preview,
      pinnedDocumentIds: pinned,
      createdAt: Number(raw?.createdAt || now()),
      updatedAt: Number(raw?.updatedAt || now())
    };
  }
  function collectGroupIds(node, output = []) {
    if (!node) return output;
    if (node.type === 'group') output.push(node.groupId);
    else if (node.type === 'split') {
      collectGroupIds(node.first, output);
      collectGroupIds(node.second, output);
    }
    return output;
  }
  function normalizeTree(node, groups) {
    if (!node || typeof node !== 'object') return null;
    if (node.type === 'group' && groups[node.groupId]) return groupNode(node.groupId);
    if (node.type === 'split') {
      const first = normalizeTree(node.first, groups);
      const second = normalizeTree(node.second, groups);
      if (!first) return second;
      if (!second) return first;
      return splitNode(node.orientation === 'vertical' ? 'vertical' : 'horizontal', first, second, node.ratio);
    }
    return null;
  }
  function hasTabs(group) {
    return Boolean(group && Array.isArray(group.tabs) && group.tabs.length);
  }
  function firstNonEmptyGroupId(groups) {
    return Object.values(groups).find(hasTabs)?.groupId || Object.keys(groups)[0] || '';
  }
  function pruneEmptyGroups(node, groups, keepGroupId = '') {
    if (!node) return null;
    if (node.type === 'group') {
      const current = groups[node.groupId];
      if (!current) return null;
      if (hasTabs(current) || node.groupId === keepGroupId) return groupNode(node.groupId);
      return null;
    }
    if (node.type !== 'split') return null;
    const first = pruneEmptyGroups(node.first, groups, keepGroupId);
    const second = pruneEmptyGroups(node.second, groups, keepGroupId);
    if (!first) return second;
    if (!second) return first;
    return splitNode(node.orientation === 'vertical' ? 'vertical' : 'horizontal', first, second, node.ratio);
  }
  function normalize(raw) {
    const groups = {};
    for (const [id, value] of Object.entries(raw?.groups || {})) {
      if (id && Object.keys(groups).length < MAX_GROUPS) groups[id] = normalizeGroup(value, id);
    }
    if (!Object.keys(groups).length) return defaultState();
    const preferredActiveGroupId = groups[raw?.activeGroupId] ? raw.activeGroupId : firstNonEmptyGroupId(groups);
    let tree = normalizeTree(raw?.tree, groups);
    if (!tree) tree = groupNode(Object.keys(groups)[0]);
    tree = pruneEmptyGroups(tree, groups, preferredActiveGroupId) || groupNode(preferredActiveGroupId || Object.keys(groups)[0]);
    const referenced = new Set(collectGroupIds(tree));
    for (const id of Object.keys(groups)) {
      if (!referenced.has(id)) delete groups[id];
    }
    const ids = Object.keys(groups);
    if (!ids.length) return defaultState();
    const activeGroupId = groups[preferredActiveGroupId] ? preferredActiveGroupId : firstNonEmptyGroupId(groups);
    return {
      version: VERSION,
      layoutVersion: Math.max(1, Number(raw?.layoutVersion || 1)),
      activeGroupId,
      groups,
      tree,
      recentlyClosedGroups: Array.isArray(raw?.recentlyClosedGroups) ? raw.recentlyClosedGroups.slice(0, 20) : [],
      recentlyClosedEditors: Array.isArray(raw?.recentlyClosedEditors) ? raw.recentlyClosedEditors.slice(0, 50) : [],
      updatedAt: Number(raw?.updatedAt || now())
    };
  }
  function load() {
    let raw = null;
    try { raw = JSON.parse(localStorage.getItem(storageKey()) || 'null'); } catch (_) {}
    state = normalize(raw);
    persist(false);
    return snapshot();
  }
  function persist(emit = true) {
    state.updatedAt = now();
    try { localStorage.setItem(storageKey(), JSON.stringify(state)); } catch (_) {}
    syncLegacyStore();
    if (emit) notify();
  }
  function notify() {
    const current = snapshot();
    for (const listener of listeners) {
      try { listener(current); } catch (error) { console.warn('[BEAST 6.2] group listener failed', error); }
    }
  }
  function snapshot() { if (!state) load(); return clone(state); }
  function group(id = state?.activeGroupId) {
    if (!state) load();
    return state.groups[id] || null;
  }
  function ensureGroup(id) {
    const value = group(id);
    if (!value) throw new Error(`Unknown editor group: ${id}`);
    return value;
  }
  function findNode(node, groupId, parent = null, side = '') {
    if (!node) return null;
    if (node.type === 'group') return node.groupId === groupId ? { node, parent, side } : null;
    return findNode(node.first, groupId, node, 'first') || findNode(node.second, groupId, node, 'second');
  }
  function replaceNode(match, replacement) {
    if (!match.parent) state.tree = replacement;
    else match.parent[match.side] = replacement;
  }
  function bump() { state.layoutVersion += 1; persist(); return snapshot(); }
  function setActiveGroup(groupId) {
    ensureGroup(groupId);
    state.activeGroupId = groupId;
    persist();
    return snapshot();
  }
  function splitGroup(groupId, orientation = 'horizontal', options = {}) {
    if (Object.keys(state.groups).length >= MAX_GROUPS) throw new Error(`Editor group limit reached (${MAX_GROUPS})`);
    const source = ensureGroup(groupId);
    const match = findNode(state.tree, groupId);
    if (!match) throw new Error(`Layout does not contain group: ${groupId}`);
    const next = createGroup(options.groupId || uid());
    state.groups[next.groupId] = next;
    const sourceNode = groupNode(source.groupId);
    const nextNode = groupNode(next.groupId);
    const replacement = options.place === 'before'
      ? splitNode(orientation === 'vertical' ? 'vertical' : 'horizontal', nextNode, sourceNode, options.ratio)
      : splitNode(orientation === 'vertical' ? 'vertical' : 'horizontal', sourceNode, nextNode, options.ratio);
    replaceNode(match, replacement);
    state.activeGroupId = next.groupId;
    bump();
    return clone(next);
  }
  function resizeSplit(groupId, ratio) {
    const match = findNode(state.tree, groupId);
    if (!match?.parent || match.parent.type !== 'split') throw new Error('Group is not directly contained by a split');
    match.parent.ratio = clampRatio(ratio);
    bump();
    return snapshot();
  }
  function closeGroup(groupId, options = {}) {
    const source = ensureGroup(groupId);
    if (Object.keys(state.groups).length === 1) throw new Error('The final editor group cannot be closed');
    if (source.tabs.length && !options.moveTabsTo && !options.discard) throw new Error('Group contains editors; move or explicitly discard them before closing');
    if (options.moveTabsTo) {
      const target = ensureGroup(options.moveTabsTo);
      for (const documentId of source.tabs) {
        if (!target.tabs.includes(documentId)) target.tabs.push(documentId);
        if (source.pinnedDocumentIds.includes(documentId) && !target.pinnedDocumentIds.includes(documentId)) target.pinnedDocumentIds.push(documentId);
      }
      if (!target.activeDocumentId) target.activeDocumentId = source.activeDocumentId || target.tabs.at(-1) || '';
      target.updatedAt = now();
    }
    const match = findNode(state.tree, groupId);
    if (!match?.parent) throw new Error('Cannot remove root group without a sibling');
    const sibling = match.side === 'first' ? match.parent.second : match.parent.first;
    const parentMatch = findParentNode(state.tree, match.parent);
    if (!parentMatch || !parentMatch.parent) state.tree = sibling;
    else parentMatch.parent[parentMatch.side] = sibling;
    state.recentlyClosedGroups.unshift({ group: clone(source), closedAt: now() });
    state.recentlyClosedGroups = state.recentlyClosedGroups.slice(0, 20);
    delete state.groups[groupId];
    if (state.activeGroupId === groupId) state.activeGroupId = options.moveTabsTo || collectGroupIds(state.tree)[0];
    bump();
    return snapshot();
  }
  function findParentNode(node, target, parent = null, side = '') {
    if (!node) return null;
    if (node === target) return { node, parent, side };
    if (node.type === 'split') return findParentNode(node.first, target, node, 'first') || findParentNode(node.second, target, node, 'second');
    return null;
  }
  function mergeGroup(groupId, targetGroupId) {
    if (groupId === targetGroupId) return snapshot();
    return closeGroup(groupId, { moveTabsTo: targetGroupId });
  }
  function openDocument(documentId, options = {}) {
    const target = ensureGroup(options.groupId || state.activeGroupId);
    const id = String(documentId || '');
    if (!id) throw new Error('documentId is required');
    const preview = options.preview !== false && !options.pinned;
    if (preview && target.previewDocumentId && target.previewDocumentId !== id && !target.pinnedDocumentIds.includes(target.previewDocumentId)) {
      target.tabs = target.tabs.filter(item => item !== target.previewDocumentId);
    }
    if (!target.tabs.includes(id)) {
      const index = Number.isInteger(options.index) ? Math.max(0, Math.min(target.tabs.length, options.index)) : target.tabs.length;
      target.tabs.splice(index, 0, id);
    }
    if (options.pinned && !target.pinnedDocumentIds.includes(id)) target.pinnedDocumentIds.push(id);
    target.previewDocumentId = preview ? id : (target.previewDocumentId === id ? '' : target.previewDocumentId);
    target.activeDocumentId = id;
    target.updatedAt = now();
    state.activeGroupId = target.groupId;
    persist();
    return clone(target);
  }
  function pinDocument(documentId, groupId = state.activeGroupId) {
    const target = ensureGroup(groupId);
    if (!target.tabs.includes(documentId)) throw new Error('Document is not open in the group');
    if (!target.pinnedDocumentIds.includes(documentId)) target.pinnedDocumentIds.push(documentId);
    if (target.previewDocumentId === documentId) target.previewDocumentId = '';
    target.updatedAt = now(); persist(); return clone(target);
  }
  function unpinDocument(documentId, groupId = state.activeGroupId) {
    const target = ensureGroup(groupId);
    target.pinnedDocumentIds = target.pinnedDocumentIds.filter(item => item !== documentId);
    if (target.tabs.includes(documentId)) target.previewDocumentId = documentId;
    target.updatedAt = now(); persist(); return clone(target);
  }
  function activateDocument(documentId, groupId = state.activeGroupId) {
    const target = ensureGroup(groupId);
    if (!target.tabs.includes(documentId)) throw new Error('Document is not open in the group');
    target.activeDocumentId = documentId;
    target.updatedAt = now(); state.activeGroupId = groupId; persist(); return clone(target);
  }
  function closeDocument(documentId, groupId = state.activeGroupId, options = {}) {
    const target = ensureGroup(groupId);
    const index = target.tabs.indexOf(documentId);
    if (index < 0) return clone(target);
    const record = {
      documentId,
      groupId,
      index,
      pinned: target.pinnedDocumentIds.includes(documentId),
      preview: target.previewDocumentId === documentId,
      closedAt: now(),
      reason: String(options.reason || 'user')
    };
    target.tabs.splice(index, 1);
    target.pinnedDocumentIds = target.pinnedDocumentIds.filter(item => item !== documentId);
    if (target.previewDocumentId === documentId) target.previewDocumentId = '';
    if (target.activeDocumentId === documentId) target.activeDocumentId = target.tabs[Math.min(index, target.tabs.length - 1)] || target.tabs[index - 1] || '';
    if (options.recordHistory !== false) {
      state.recentlyClosedEditors.unshift(record);
      state.recentlyClosedEditors = state.recentlyClosedEditors.slice(0, 50);
    }
    target.updatedAt = now(); persist(); return clone(target);
  }
  function reopenClosedEditor(options = {}) {
    if (!state.recentlyClosedEditors.length) return null;
    const record = state.recentlyClosedEditors.shift();
    const requestedGroup = options.groupId || record.groupId;
    const groupId = state.groups[requestedGroup] ? requestedGroup : state.activeGroupId;
    openDocument(record.documentId, {
      groupId,
      index: Number.isInteger(record.index) ? record.index : undefined,
      pinned: options.pinned ?? record.pinned,
      preview: options.preview ?? record.preview
    });
    persist();
    return { ...clone(record), restoredGroupId: groupId };
  }
  function clearClosedEditorHistory() { state.recentlyClosedEditors = []; persist(); return snapshot(); }
  function setDocumentDirty(documentId, dirty = true, groupId = '') {
    const owner = groupId ? ensureGroup(groupId) : Object.values(state.groups).find(item => item.tabs.includes(documentId));
    if (!owner) return snapshot();
    if (dirty && owner.previewDocumentId === documentId) {
      owner.previewDocumentId = '';
      if (!owner.pinnedDocumentIds.includes(documentId)) owner.pinnedDocumentIds.push(documentId);
      owner.updatedAt = now();
      persist();
    }
    return snapshot();
  }
  function moveDocument(documentId, fromGroupId, toGroupId, options = {}) {
    const source = ensureGroup(fromGroupId);
    const target = ensureGroup(toGroupId);
    if (!source.tabs.includes(documentId)) throw new Error('Document is not open in the source group');
    const pinned = source.pinnedDocumentIds.includes(documentId);
    closeDocument(documentId, fromGroupId);
    openDocument(documentId, { groupId: toGroupId, pinned: options.pinned ?? pinned, preview: options.preview ?? false, index: options.index });
    return snapshot();
  }
  function reorderDocument(documentId, groupId, index) {
    const target = ensureGroup(groupId);
    const current = target.tabs.indexOf(documentId);
    if (current < 0) throw new Error('Document is not open in the group');
    target.tabs.splice(current, 1);
    target.tabs.splice(Math.max(0, Math.min(target.tabs.length, Number(index) || 0)), 0, documentId);
    target.updatedAt = now(); persist(); return clone(target);
  }
  function restoreLayout(layout) {
    state = normalize(layout);
    bump();
    return snapshot();
  }
  function reset() { state = defaultState(); persist(); return snapshot(); }
  function syncLegacyStore() {
    const store = window.BeastStore;
    if (!store?.patch || !state) return;
    const active = state.groups[state.activeGroupId] || Object.values(state.groups)[0];
    const allTabs = [...new Set(Object.values(state.groups).flatMap(item => item.tabs))];
    store.patch('editor', {
      editorGroups: snapshot(),
      openTabs: allTabs,
      activePath: active?.activeDocumentId || '',
      split: Object.keys(state.groups).length > 1,
      activeGroupId: state.activeGroupId
    });
  }
  function subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); }
  function resetForWorkspace() { return load(); }

  window.BeastEditorGroups = {
    VERSION,
    MAX_GROUPS,
    load,
    snapshot,
    subscribe,
    setActiveGroup,
    splitGroup,
    resizeSplit,
    closeGroup,
    mergeGroup,
    openDocument,
    pinDocument,
    unpinDocument,
    activateDocument,
    closeDocument,
    reopenClosedEditor,
    clearClosedEditorHistory,
    setDocumentDirty,
    moveDocument,
    reorderDocument,
    restoreLayout,
    reset,
    resetForWorkspace,
    collectGroupIds: () => collectGroupIds(snapshot().tree)
  };
  load();
})();
