'use strict';

const MAX_MIME_VALUE_BYTES = 512 * 1024;
const MAX_TRACEBACK_LINES = 24;

const MIME_PREFERENCE = [
  'application/vnd.jupyter.widget-view+json',
  'application/vnd.plotly.v1+json',
  'application/vnd.vega.v5+json',
  'application/vnd.vegalite.v5+json',
  'application/javascript',
  'image/png',
  'image/jpeg',
  'image/svg+xml',
  'text/html',
  'text/markdown',
  'application/json',
  'text/plain',
];

function byteLength(value) {
  return Buffer.byteLength(String(value ?? ''), 'utf8');
}

function compactString(value, limit = MAX_MIME_VALUE_BYTES) {
  const text = Array.isArray(value) ? value.join('') : String(value ?? '');
  if (byteLength(text) <= limit) return text;
  let end = text.length;
  while (end > 0 && byteLength(text.slice(end)) < limit) end -= Math.max(1, Math.floor((end || 1) / 4));
  const sliced = text.slice(Math.max(0, end));
  return `...[BEAST notebook output elided to ${limit} bytes]\n${sliced}`;
}

function compactJson(value, limit = MAX_MIME_VALUE_BYTES) {
  if (typeof value === 'string') return compactString(value, limit);
  const text = JSON.stringify(value ?? null, null, 2);
  if (byteLength(text) <= limit) return value;
  return { beast_elided: true, bytes: byteLength(text), preview: compactString(text, limit) };
}

function normalizeMimeBundle(data = {}) {
  const bundle = {};
  if (!data || typeof data !== 'object') return bundle;
  for (const [mime, rawValue] of Object.entries(data)) {
    const key = String(mime || '').toLowerCase();
    if (!key.includes('/')) continue;
    if (/json$|\+json$/.test(key)) bundle[key] = compactJson(rawValue);
    else bundle[key] = compactString(rawValue);
  }
  return bundle;
}

function primaryMime(data = {}) {
  return MIME_PREFERENCE.find(mime => Object.prototype.hasOwnProperty.call(data, mime))
    || Object.keys(data || {})[0]
    || '';
}

function normalizeNotebookOutput(output = {}) {
  const rawType = String(output.output_type || output.type || 'display_data');
  const type = rawType === 'execute_result' || rawType === 'display_data'
    ? rawType
    : rawType === 'stream'
      ? 'stream'
      : rawType === 'error'
        ? 'error'
        : 'display_data';
  if (type === 'stream') {
    const text = compactString(output.text ?? output.data?.['text/plain'] ?? '');
    return {
      output_type: 'stream',
      type: 'stream',
      name: String(output.name || 'stdout'),
      text,
      data: { 'text/plain': text },
      metadata: output.metadata && typeof output.metadata === 'object' ? output.metadata : {},
      primary_mime: 'text/plain',
    };
  }
  if (type === 'error') {
    const traceback = Array.isArray(output.traceback) ? output.traceback.slice(-MAX_TRACEBACK_LINES).map(line => compactString(line, 64 * 1024)) : [];
    const text = `${output.ename || 'Error'}: ${output.evalue || ''}${traceback.length ? `\n${traceback.join('\n')}` : ''}`;
    return {
      output_type: 'error',
      type: 'error',
      ename: String(output.ename || 'Error'),
      evalue: compactString(output.evalue || '', 64 * 1024),
      traceback,
      data: { 'text/plain': compactString(text) },
      metadata: output.metadata && typeof output.metadata === 'object' ? output.metadata : {},
      primary_mime: 'text/plain',
    };
  }
  const data = normalizeMimeBundle(output.data || { 'text/plain': output.text || '' });
  const text = Object.prototype.hasOwnProperty.call(data, 'text/plain') ? data['text/plain'] : compactString(output.text || '');
  if (text && !Object.prototype.hasOwnProperty.call(data, 'text/plain')) data['text/plain'] = text;
  return {
    output_type: type,
    type,
    execution_count: output.execution_count ?? null,
    data,
    metadata: output.metadata && typeof output.metadata === 'object' ? output.metadata : {},
    text,
    primary_mime: primaryMime(data),
  };
}

function normalizeNotebookOutputs(outputs = []) {
  return (Array.isArray(outputs) ? outputs : []).map(normalizeNotebookOutput);
}

function summarizeMimeOutputs(outputs = []) {
  const normalized = normalizeNotebookOutputs(outputs);
  const mimeTypes = [...new Set(normalized.flatMap(output => Object.keys(output.data || {})))];
  const trustedTypes = mimeTypes.filter(mime => /^(?:text\/html|image\/svg\+xml|application\/javascript|application\/vnd\.(?:jupyter\.widget-view|plotly|vega|vegalite))/i.test(mime));
  return {
    outputCount: normalized.length,
    mimeTypes,
    primary: normalized.map(output => output.primary_mime).filter(Boolean),
    hasRichOutput: mimeTypes.some(mime => mime !== 'text/plain'),
    trustedMimeTypes: trustedTypes,
    trustSensitive: trustedTypes.length > 0,
  };
}

module.exports = {
  MAX_MIME_VALUE_BYTES,
  MIME_PREFERENCE,
  normalizeMimeBundle,
  normalizeNotebookOutput,
  normalizeNotebookOutputs,
  summarizeMimeOutputs,
};
