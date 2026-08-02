'use strict';

const { spawn } = require('child_process');

function createBoundedProcess({ repoRoot }) {
  function boundedProcess(command, args, options = {}) {
    const timeoutMs = Math.max(500, Math.min(Number(options.timeoutMs || 30000), 900000));
    const outputLimit = Math.max(4096, Math.min(Number(options.outputLimit || 512000), 1024 * 1024));
    return new Promise(resolve => {
      let stdout = ''; let stderr = ''; let settled = false; let timedOut = false; let timer = 0;
      const finish = result => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve({ ...result, stdout:stdout.slice(-outputLimit), stderr:stderr.slice(-outputLimit), timed_out:timedOut });
      };
      const input=typeof options.input==='string'?options.input:'';if(Buffer.byteLength(input,'utf8')>512000){finish({ok:false,error:'process input exceeded 512 KiB',returncode:null});return;}let child;
      try {
        child = spawn(command, args, { cwd:options.cwd || repoRoot, env:options.env || process.env, stdio:[input?'pipe':'ignore','pipe','pipe'], shell:Boolean(options.shell), windowsHide:true });
      } catch (error) {
        finish({ ok:false, error:String(error.message || error), returncode:null });
        return;
      }
      const append = (key, chunk) => {
        if (key === 'out') stdout = `${stdout}${String(chunk)}`.slice(-outputLimit);
        else stderr = `${stderr}${String(chunk)}`.slice(-outputLimit);
      };
      child.stdout?.on('data', chunk => append('out',chunk));
      child.stderr?.on('data', chunk => append('err',chunk));
      child.once('error', error => finish({ ok:false, error:String(error.message || error), returncode:null }));
      child.once('close', (code, signal) => finish({ ok:code === 0 && !timedOut, returncode:code, signal:signal || '', error:timedOut ? `process timed out after ${timeoutMs}ms` : '' }));
      if(input)child.stdin.end(input);
      timer = setTimeout(() => {
        timedOut = true;
        if (!child.killed) child.kill('SIGTERM');
      }, timeoutMs);
    });
  }

  return boundedProcess;
}

module.exports = { createBoundedProcess };
