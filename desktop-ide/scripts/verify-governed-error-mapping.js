#!/usr/bin/env node
// Ensures agent-client surfaces governed SSE errors instead of "gateway page".
const fs = require('fs');
const path = require('path');
const src = fs.readFileSync(path.join(__dirname, '..', 'renderer/js/ai/agent-client.js'), 'utf8');
if (!src.includes('function parseGovernedExecutionError')) {
  throw new Error('parseGovernedExecutionError missing from agent-client.js');
}
if (!src.includes('transportReceiptIsUseful')) {
  throw new Error('transportReceiptIsUseful missing from agent-client.js');
}

const start = src.indexOf('function parseGovernedExecutionError');
const end = src.indexOf('async function runInWorktree', start);
if (start < 0 || end < 0) throw new Error('could not extract mapping functions');
const fns = src.slice(start, end);
// eslint-disable-next-line no-eval
const boxed = eval('(function(){\n' + fns + '\nreturn { parseGovernedExecutionError, providerTransportFailure };\n})()');

const payload = {
  error: JSON.stringify({
    type: 'governed_execution_error',
    code: 'CONTEXT_BUDGET_EXCEEDED',
    message: 'Protected context exceeds input budget',
  }),
  provider_transport: {},
};
const text = boxed.providerTransportFailure(payload, 'fallback');
if (!text.includes('CONTEXT_BUDGET_EXCEEDED')) {
  throw new Error('governed code not surfaced: ' + text);
}
if (/gateway page/i.test(text) || /unknown content type/i.test(text)) {
  throw new Error('empty transport receipt still produced the gateway-page message: ' + text);
}

const html = boxed.providerTransportFailure({
  provider_transport: {
    http_status: 502,
    content_type: 'text/html',
    requested_url: 'http://127.0.0.1:8101/proxy/v1/chat/completions',
  },
}, 'fallback');
if (!/gateway page/i.test(html)) {
  throw new Error('real HTML transport failure should still mention a gateway page');
}
console.log('verify-governed-error-mapping: ok');
