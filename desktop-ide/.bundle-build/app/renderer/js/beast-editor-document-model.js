(() => {
  const byPath = new Map();
  const byId = new Map();
  let updateTimers = new Map();

  function desktop() {
    if (!window.beastDesktop?.createEditorDocument) throw new Error('Phase 6.1 editor document bridge is unavailable.');
    return window.beastDesktop;
  }

  function activeRoot() {
    return window.BeastStore?.get?.().workspace?.root || '';
  }

  function targetIdentity() {
    const target = window.BeastStore?.get?.().workspace?.executionTarget || { kind: 'local', id: 'local' };
    return String(target.id || target.kind || 'local');
  }

  async function open(path, options = {}) {
    const key = String(path || '');
    if (!key) throw new Error('A document path is required.');
    if (byPath.has(key)) return byPath.get(key);
    const document = await desktop().createEditorDocument({
      kind: options.kind || 'local',
      root_path: options.rootPath || activeRoot(),
      path: key,
      target_id: options.targetId || targetIdentity(),
      read_only: Boolean(options.readOnly),
      language: options.language || '',
      content: options.content || '',
    });
    byPath.set(key, document);
    byId.set(document.document_id, document);
    return document;
  }

  function remember(document) {
    if (!document?.document_id) return document;
    byId.set(document.document_id, document);
    if (document.path) byPath.set(document.path, document);
    return document;
  }

  async function update(path, content) {
    const document = byPath.get(String(path || ''));
    if (!document) return null;
    const updated = await desktop().updateEditorDocument(document.document_id, { content: String(content ?? '') });
    return remember(updated);
  }

  function scheduleUpdate(path, content, delay = 120) {
    const key = String(path || '');
    clearTimeout(updateTimers.get(key));
    updateTimers.set(key, setTimeout(() => {
      updateTimers.delete(key);
      update(key, content).catch(error => console.warn('[BEAST 6.1] document update failed', error));
    }, delay));
  }

  async function refresh(path) {
    const document = byPath.get(String(path || ''));
    if (!document) return null;
    return remember(await desktop().refreshEditorDocument(document.document_id));
  }

  async function save(path, options = {}) {
    const document = byPath.get(String(path || ''));
    if (!document) throw new Error('Document is not registered.');
    return remember(await desktop().saveEditorDocument(document.document_id, options));
  }

  async function restore() {
    const result = await desktop().listEditorDocuments();
    for (const document of result?.documents || []) remember(document);
    return result?.documents || [];
  }

  function get(path) { return byPath.get(String(path || '')) || null; }
  function getById(id) { return byId.get(String(id || '')) || null; }

  async function binaryPreview(path, options = {}) {
    const document = get(path);
    if (!document?.binary) throw new Error('The active document is not binary.');
    return desktop().previewBinaryDocument(document.document_id, options);
  }

  async function openExternal(path) {
    const document = get(path);
    if (!document) throw new Error('Document is not registered.');
    return desktop().openEditorDocumentExternally(document.document_id);
  }

  window.BeastEditorDocumentModel = { open, update, scheduleUpdate, refresh, save, restore, get, getById, binaryPreview, openExternal };
})();
