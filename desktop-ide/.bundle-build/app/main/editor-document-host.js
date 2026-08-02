'use strict';

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const DOCUMENT_KINDS = new Set(['local', 'remote', 'virtual', 'readonly', 'untitled', 'diff', 'binary', 'large_file']);
const EXTERNAL_STATES = new Set(['CLEAN', 'EXTERNALLY_MODIFIED', 'CONFLICTED', 'DELETED_EXTERNALLY', 'MOVED_EXTERNALLY']);
const BINARY_SAMPLE_BYTES = 8192;
const DEFAULT_LARGE_FILE_BYTES = 5 * 1024 * 1024;
const DEFAULT_MAX_TEXT_BYTES = 16 * 1024 * 1024;
const DEFAULT_HEX_PREVIEW_BYTES = 512;
const DEFAULT_LONG_LINE_CHARS = 20000;
const GENERATED_PATH_PATTERN = /(^|\/)(dist|build|coverage|node_modules|vendor|generated|__generated__|.next|target)(\/|$)|\.(min\.js|map|lock)$/i;

function sha256(value) {
  return `sha256:${crypto.createHash('sha256').update(value).digest('hex')}`;
}

function stableJson(value) {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${stableJson(value[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

function normalizeLineEndings(text) {
  return String(text || '').includes('\r\n') ? 'CRLF' : 'LF';
}

function detectBinary(buffer) {
  const sample = buffer.subarray(0, Math.min(buffer.length, BINARY_SAMPLE_BYTES));
  if (!sample.length) return false;
  let suspicious = 0;
  for (const byte of sample) {
    if (byte === 0) return true;
    if (byte < 7 || (byte > 13 && byte < 32)) suspicious += 1;
  }
  return suspicious / sample.length > 0.1;
}

function inferEncoding(buffer) {
  if (buffer.length >= 3 && buffer[0] === 0xef && buffer[1] === 0xbb && buffer[2] === 0xbf) return 'utf8-bom';
  return 'utf8';
}


function fileSignature(buffer) {
  const signatures = [
    { name: 'PNG image', bytes: [0x89,0x50,0x4e,0x47] },
    { name: 'JPEG image', bytes: [0xff,0xd8,0xff] },
    { name: 'GIF image', bytes: [0x47,0x49,0x46,0x38] },
    { name: 'PDF document', bytes: [0x25,0x50,0x44,0x46] },
    { name: 'ZIP archive', bytes: [0x50,0x4b,0x03,0x04] },
    { name: 'ELF executable', bytes: [0x7f,0x45,0x4c,0x46] },
    { name: 'Windows executable', bytes: [0x4d,0x5a] },
  ];
  const match = signatures.find(item => item.bytes.every((value, index) => buffer[index] === value));
  return match?.name || (detectBinary(buffer) ? 'Binary data' : 'Text');
}

function decodeText(buffer) {
  if (buffer.length >= 2 && buffer[0] === 0xff && buffer[1] === 0xfe) {
    return { encoding: 'utf16le', content: buffer.subarray(2).toString('utf16le'), valid: true };
  }
  if (buffer.length >= 2 && buffer[0] === 0xfe && buffer[1] === 0xff) {
    return { encoding: 'utf16be', content: '', valid: false };
  }
  try {
    const decoder = new TextDecoder('utf-8', { fatal: true });
    const content = decoder.decode(buffer.subarray(0, DEFAULT_MAX_TEXT_BYTES));
    return { encoding: inferEncoding(buffer), content: content.replace(/^\uFEFF/, ''), valid: true };
  } catch (_) {
    return { encoding: 'unknown', content: '', valid: false };
  }
}

function safetyProfile({ documentPath, sizeBytes, binary, encoding, content, largeFileBytes }) {
  const lines = String(content || '').split(/\r?\n/);
  const longestLine = lines.reduce((maximum, line) => Math.max(maximum, line.length), 0);
  const generated = GENERATED_PATH_PATTERN.test(String(documentPath || '').replace(/\\/g, '/'));
  const large = sizeBytes >= largeFileBytes;
  const veryLongLines = longestLine >= DEFAULT_LONG_LINE_CHARS;
  const unknownEncoding = encoding === 'unknown' || encoding === 'utf16be';
  return {
    mode: binary ? 'BINARY' : (large ? 'LARGE_FILE' : (veryLongLines ? 'LONG_LINE' : (generated ? 'GENERATED' : (unknownEncoding ? 'UNKNOWN_ENCODING' : 'NORMAL')))),
    generated,
    very_long_lines: veryLongLines,
    longest_line_chars: longestLine,
    unknown_encoding: unknownEncoding,
    disable_semantic_tokens: large || generated || veryLongLines,
    disable_minimap: large || generated || veryLongLines,
    disable_code_folding: large || veryLongLines,
    disable_diagnostics: large || generated,
    disable_format_on_save: large || generated || unknownEncoding,
    disable_expensive_decorations: large || generated || veryLongLines,
    word_wrap: veryLongLines ? 'bounded' : 'off',
    max_tokenization_line_length: veryLongLines ? 2000 : 20000,
  };
}

function canonicalUri(kind, targetId, rootPath, documentPath, documentId) {
  if (kind === 'untitled') return `untitled:${documentId}`;
  if (kind === 'virtual') return `beast-virtual://${targetId}/${documentId}`;
  if (kind === 'diff') return `beast-diff://${targetId}/${documentId}`;
  const normalized = String(documentPath || '').replace(/\\/g, '/').replace(/^\/+/, '');
  if (kind === 'remote') return `beast-remote://${targetId}/${normalized}`;
  if (kind === 'readonly') return `beast-readonly://${targetId}/${normalized}`;
  if (kind === 'binary') return `beast-binary://${targetId}/${normalized}`;
  if (kind === 'large_file') return `beast-large://${targetId}/${normalized}`;
  return `file://${path.resolve(rootPath, documentPath).replace(/\\/g, '/')}`;
}

function createEditorDocumentHost({ app, repoRoot, safeWorkspacePath, getActiveWorkspaceRoot, largeFileBytes = DEFAULT_LARGE_FILE_BYTES }) {
  if (!app || typeof safeWorkspacePath !== 'function' || typeof getActiveWorkspaceRoot !== 'function') {
    throw new Error('createEditorDocumentHost requires app, safeWorkspacePath, and getActiveWorkspaceRoot');
  }

  const stateDir = path.join(app.getPath('userData'), 'editor-documents');
  const statePath = path.join(stateDir, 'documents.json');
  const documents = new Map();

  function persist() {
    fs.mkdirSync(stateDir, { recursive: true });
    const payload = {
      version: '6.1',
      documents: [...documents.values()].map(document => ({
        ...document,
        content: document.dirty ? document.content : undefined,
      })),
    };
    const tempPath = `${statePath}.tmp`;
    fs.writeFileSync(tempPath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
    fs.renameSync(tempPath, statePath);
  }

  function restore() {
    documents.clear();
    if (!fs.existsSync(statePath)) return { ok: true, restored: 0 };
    const payload = JSON.parse(fs.readFileSync(statePath, 'utf8'));
    for (const item of Array.isArray(payload.documents) ? payload.documents : []) {
      if (!item || !item.document_id || !DOCUMENT_KINDS.has(item.kind)) continue;
      documents.set(item.document_id, item);
    }
    return { ok: true, restored: documents.size };
  }

  function inspectLocal(payload = {}) {
    const rootPath = path.resolve(payload.root_path || getActiveWorkspaceRoot() || repoRoot);
    const check = safeWorkspacePath(rootPath, payload.path || '');
    if (!check.ok) throw new Error(check.error);
    const stat = fs.statSync(check.target);
    if (!stat.isFile()) throw new Error('Document target is not a file');
    const buffer = fs.readFileSync(check.target);
    const binary = detectBinary(buffer);
    const large = stat.size >= Math.max(1024, Number(payload.large_file_bytes || largeFileBytes));
    const decoded = binary ? { encoding: 'binary', content: '', valid: false } : decodeText(buffer);
    const kind = binary ? 'binary' : (large ? 'large_file' : (payload.read_only || !decoded.valid ? 'readonly' : 'local'));
    const content = decoded.content;
    const profile = safetyProfile({ documentPath: payload.path || '', sizeBytes: stat.size, binary, encoding: decoded.encoding, content, largeFileBytes: Math.max(1024, Number(payload.large_file_bytes || largeFileBytes)) });
    return { rootPath, targetPath: check.target, stat, buffer, binary, large, kind, content, encoding: decoded.encoding, profile };
  }

  function create(payload = {}) {
    let kind = String(payload.kind || 'local').toLowerCase();
    if (!DOCUMENT_KINDS.has(kind)) throw new Error(`Unsupported document kind: ${kind}`);
    const documentId = String(payload.document_id || crypto.randomUUID());
    const targetId = String(payload.target_id || 'local');
    let rootPath = path.resolve(payload.root_path || getActiveWorkspaceRoot() || repoRoot);
    let documentPath = String(payload.path || '');
    let content = String(payload.content || '');
    let diskHash = null;
    let sizeBytes = Buffer.byteLength(content, 'utf8');
    let encoding = String(payload.encoding || 'utf8');
    let lineEndings = normalizeLineEndings(content);
    let readOnly = Boolean(payload.read_only || ['readonly', 'virtual', 'diff', 'binary'].includes(kind));
    let binary = kind === 'binary';
    let largeFileMode = kind === 'large_file';
    let statToken = null;

    if (['local', 'readonly', 'binary', 'large_file'].includes(kind)) {
      const inspected = inspectLocal(payload);
      ({ rootPath, content, binary, kind } = inspected);
      documentPath = path.relative(rootPath, inspected.targetPath);
      sizeBytes = inspected.stat.size;
      encoding = inspected.encoding;
      lineEndings = normalizeLineEndings(content);
      diskHash = sha256(inspected.buffer);
      largeFileMode = inspected.large;
      readOnly = Boolean(payload.read_only || binary || kind === 'readonly' || inspected.profile.unknown_encoding);
      statToken = `${inspected.stat.dev}:${inspected.stat.ino}:${inspected.stat.size}:${inspected.stat.mtimeMs}`;
      payload.safety_profile = inspected.profile;
      payload.file_signature = fileSignature(inspected.buffer);
      payload.partial_content = !binary && inspected.stat.size > DEFAULT_MAX_TEXT_BYTES;
    }

    const document = {
      version: '6.1',
      beast_object_type: 'beast_editor_document',
      document_id: documentId,
      uri: canonicalUri(kind, targetId, rootPath, documentPath, documentId),
      kind,
      target_id: targetId,
      root_path: rootPath,
      path: documentPath,
      language: String(payload.language || ''),
      encoding,
      line_endings: lineEndings,
      document_version: 1,
      dirty: false,
      read_only: readOnly,
      content_hash: sha256(Buffer.from(content, 'utf8')),
      disk_hash: diskHash,
      last_saved_version: diskHash ? 1 : 0,
      external_change_state: 'CLEAN',
      large_file_mode: largeFileMode,
      binary,
      size_bytes: sizeBytes,
      stat_token: statToken,
      file_signature: String(payload.file_signature || (binary ? 'Binary data' : 'Text')),
      partial_content: Boolean(payload.partial_content),
      safety_profile: payload.safety_profile || safetyProfile({ documentPath, sizeBytes, binary, encoding, content, largeFileBytes }),
      content,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      authority: 'editor_document_state_only',
      grants_workspace_mutation: false,
    };
    document.document_digest = sha256(Buffer.from(stableJson({ ...document, content: undefined, document_digest: undefined }), 'utf8'));
    documents.set(documentId, document);
    persist();
    return publicDocument(document, { includeContent: !binary });
  }

  function publicDocument(document, { includeContent = false } = {}) {
    const value = { ...document };
    if (!includeContent) delete value.content;
    return value;
  }

  function get(documentId, options = {}) {
    const document = documents.get(String(documentId || ''));
    if (!document) throw new Error(`Unknown editor document: ${documentId}`);
    return publicDocument(document, options);
  }

  function update(documentId, payload = {}) {
    const document = documents.get(String(documentId || ''));
    if (!document) throw new Error(`Unknown editor document: ${documentId}`);
    if (document.read_only || document.binary) throw new Error('Document is read-only');
    const content = String(payload.content ?? document.content ?? '');
    document.content = content;
    document.document_version += 1;
    document.content_hash = sha256(Buffer.from(content, 'utf8'));
    document.line_endings = normalizeLineEndings(content);
    document.dirty = document.disk_hash ? document.content_hash !== document.disk_hash : true;
    document.updated_at = new Date().toISOString();
    if (document.external_change_state === 'EXTERNALLY_MODIFIED' && document.dirty) document.external_change_state = 'CONFLICTED';
    document.document_digest = sha256(Buffer.from(stableJson({ ...document, content: undefined, document_digest: undefined }), 'utf8'));
    persist();
    return publicDocument(document, { includeContent: true });
  }

  function refresh(documentId) {
    const document = documents.get(String(documentId || ''));
    if (!document) throw new Error(`Unknown editor document: ${documentId}`);
    if (!['local', 'readonly', 'binary', 'large_file'].includes(document.kind)) return publicDocument(document);
    const check = safeWorkspacePath(document.root_path, document.path);
    if (!check.ok) throw new Error(check.error);
    if (!fs.existsSync(check.target)) {
      document.external_change_state = 'DELETED_EXTERNALLY';
    } else {
      const buffer = fs.readFileSync(check.target);
      const nextHash = sha256(buffer);
      if (nextHash !== document.disk_hash) {
        document.external_change_state = document.dirty ? 'CONFLICTED' : 'EXTERNALLY_MODIFIED';
      } else {
        document.external_change_state = 'CLEAN';
      }
      const stat = fs.statSync(check.target);
      document.stat_token = `${stat.dev}:${stat.ino}:${stat.size}:${stat.mtimeMs}`;
      document.size_bytes = stat.size;
    }
    document.updated_at = new Date().toISOString();
    document.document_digest = sha256(Buffer.from(stableJson({ ...document, content: undefined, document_digest: undefined }), 'utf8'));
    persist();
    return publicDocument(document);
  }

  function save(documentId, payload = {}) {
    const document = documents.get(String(documentId || ''));
    if (!document) throw new Error(`Unknown editor document: ${documentId}`);
    if (document.read_only || document.binary || !['local', 'large_file'].includes(document.kind)) throw new Error('Document cannot be saved');
    refresh(documentId);
    if (document.external_change_state === 'CONFLICTED' && !payload.overwrite_external) throw new Error('External change conflict requires explicit overwrite');
    const check = safeWorkspacePath(document.root_path, document.path);
    if (!check.ok) throw new Error(check.error);
    fs.writeFileSync(check.target, document.content || '', document.encoding === 'utf8-bom' ? 'utf8' : document.encoding);
    const buffer = fs.readFileSync(check.target);
    const stat = fs.statSync(check.target);
    document.disk_hash = sha256(buffer);
    document.content_hash = sha256(Buffer.from(document.content || '', 'utf8'));
    document.last_saved_version = document.document_version;
    document.dirty = false;
    document.external_change_state = 'CLEAN';
    document.stat_token = `${stat.dev}:${stat.ino}:${stat.size}:${stat.mtimeMs}`;
    document.updated_at = new Date().toISOString();
    document.document_digest = sha256(Buffer.from(stableJson({ ...document, content: undefined, document_digest: undefined }), 'utf8'));
    persist();
    return publicDocument(document);
  }

  function binaryPreview(documentId, payload = {}) {
    const document = documents.get(String(documentId || ''));
    if (!document) throw new Error(`Unknown editor document: ${documentId}`);
    if (!document.binary) throw new Error('Hex preview is available only for binary documents');
    const check = safeWorkspacePath(document.root_path, document.path);
    if (!check.ok) throw new Error(check.error);
    const offset = Math.max(0, Number(payload.offset || 0));
    const length = Math.max(16, Math.min(4096, Number(payload.length || DEFAULT_HEX_PREVIEW_BYTES)));
    const descriptor = fs.openSync(check.target, 'r');
    try {
      const buffer = Buffer.alloc(length);
      const bytesRead = fs.readSync(descriptor, buffer, 0, length, offset);
      const view = buffer.subarray(0, bytesRead);
      const rows = [];
      for (let index = 0; index < view.length; index += 16) {
        const chunk = view.subarray(index, index + 16);
        rows.push({
          offset: offset + index,
          hex: [...chunk].map(value => value.toString(16).padStart(2, '0')).join(' '),
          ascii: [...chunk].map(value => value >= 32 && value <= 126 ? String.fromCharCode(value) : '.').join(''),
        });
      }
      return { ok: true, document_id: document.document_id, offset, bytes_read: bytesRead, total_bytes: document.size_bytes, rows, authority: 'binary_preview_read_only' };
    } finally { fs.closeSync(descriptor); }
  }

  function externalOpenTarget(documentId) {
    const document = documents.get(String(documentId || ''));
    if (!document) throw new Error(`Unknown editor document: ${documentId}`);
    if (!['local', 'readonly', 'binary', 'large_file'].includes(document.kind)) throw new Error('Document has no external filesystem target');
    const check = safeWorkspacePath(document.root_path, document.path);
    if (!check.ok) throw new Error(check.error);
    return check.target;
  }

  function list() {
    return [...documents.values()].map(document => publicDocument(document));
  }

  restore();
  return { create, get, update, refresh, save, binaryPreview, externalOpenTarget, list, restore, statePath };
}

module.exports = { createEditorDocumentHost, DOCUMENT_KINDS, EXTERNAL_STATES, detectBinary, safetyProfile, fileSignature, sha256 };
