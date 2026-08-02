'use strict';

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { normalizeNotebookOutputs, summarizeMimeOutputs } = require('./notebook-output-contract');

function createNotebookExecutionHost({ repoRoot, boundedProcess, getActiveWorkspaceRoot }) {
  if (!repoRoot || typeof boundedProcess !== 'function' || typeof getActiveWorkspaceRoot !== 'function') {
    throw new Error('createNotebookExecutionHost requires repoRoot, boundedProcess, and getActiveWorkspaceRoot');
  }

  async function executeNotebookCell(rootPath, payload = {}) {
    const root = path.resolve(rootPath || getActiveWorkspaceRoot() || repoRoot);
    const code = String(payload.code || '');
    const language = String(payload.language || 'python').toLowerCase();
    if (!fs.existsSync(root) || !fs.statSync(root).isDirectory()) return { ok:false, error:'workspace root does not exist' };
    if (language !== 'python') return { ok:false, error:'Only the isolated Python cell runner is available in this build.' };
    if (!code.trim()) return { ok:false, error:'Notebook cell is empty.' };
    if (Buffer.byteLength(code,'utf8') > 64 * 1024) return { ok:false, error:'Notebook cell exceeds the 64 KiB safety limit.' };
    const startedAt = Date.now();
    const result = await boundedProcess('python3',['-I','-c',code],{
      cwd:root, timeoutMs:payload.timeoutMs || 30000,
      env:{ PATH:process.env.PATH || '', PYTHONNOUSERSITE:'1', BEAST_NOTEBOOK_EXECUTION:'1', BEAST_ACTIVE_WORKSPACE:root },
    });
    const digest = crypto.createHash('sha256').update(`${root}\n${code}\n${result.stdout}\n${result.stderr}\n${result.returncode}`).digest('hex');
    const codeValue = result.returncode ?? result.code ?? 0;
    const outputs = normalizeNotebookOutputs([
      ...(result.stdout ? [{ output_type:'stream', name:'stdout', text:result.stdout }] : []),
      ...(result.stderr ? [{ output_type:codeValue ? 'error' : 'stream', name:'stderr', ename:'PythonCellError', evalue:result.stderr, text:result.stderr }] : []),
    ]);
    return {
      ...result, language, root, started_at:startedAt, duration_ms:Date.now()-startedAt,
      outputs,
      output_mime_summary:summarizeMimeOutputs(outputs),
      receipt:{ id:`NB-${digest.slice(0,16).toUpperCase()}`, digest:`sha256:${digest}`, mode:'explicit-local-cell', evidence:'operator-initiated' },
    };
  }

  return { executeNotebookCell };
}

module.exports = { createNotebookExecutionHost };
