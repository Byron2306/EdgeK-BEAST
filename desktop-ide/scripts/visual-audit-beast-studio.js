const { app, BrowserWindow, ipcMain } = require('electron');
const fs = require('fs');
const path = require('path');

const repoRoot = path.resolve(__dirname, '..', '..');
const outDir = path.join(repoRoot, 'desktop-ide', 'visual-audit');
const allPages = [
  'workspace',
  'terminal',
  'mission',
  'models',
  'agents',
  'review',
  'evidence',
  'crystallization',
  'commons',
  'trust',
  'memory',
  'map',
  'source',
  'tooling',
  'system',
  'doctor',
  'compatibility',
];
const requestedPages = String(process.env.BEAST_VISUAL_PAGES || '').split(',').map(value => value.trim()).filter(Boolean);
const pages = requestedPages.length ? allPages.filter(page => requestedPages.includes(page)) : allPages;
const notebookVisualPath = '__beast_notebook_visual__.ipynb';
const notebookVisualDocument = JSON.stringify({ nbformat:4, nbformat_minor:5, metadata:{ kernelspec:{ display_name:'BEAST Python', language:'python', name:'beast-python' } }, cells:[{ id:'intro', cell_type:'markdown', metadata:{}, source:'# Notebook Cortex\nA real BEAST notebook document.' },{ id:'compute', cell_type:'code', metadata:{}, execution_count:1, source:'value = 6 * 7\nprint(value)', outputs:[{ output_type:'stream', name:'stdout', text:'42\\n' }] }] }, null, 2);
function aiVisualFixture() {
  const now=Date.now();
  return {open:true,expanded:false,mode:'agent',sessionId:'visual-pair-7f3a21',streaming:false,status:'ready-to-review',error:'',prompt:'',contextFiles:['desktop-ide/renderer/js/pages/beast-workspace-page.js'],selection:null,crystal:{action:'exact_reuse',source:'verified workspace crystal',confidence:.96,reused:true,avoidedTokens:2840,decisionId:'visual',recorded:false},sourcePlanReady:true,sourcePlanId:'PLAN-VISUAL',trace:[{id:'t1',kind:'context',text:'desktop-ide/renderer/js/pages/beast-workspace-page.js locked',at:now-4000},{id:'t2',kind:'crystal',text:'Exact verified prior work reused',at:now-3000},{id:'t3',kind:'validation',text:'passed · 2 bounded checks',at:now-1800},{id:'t4',kind:'sourceplan',text:'1 governed operation ready',at:now-1000}],messages:[{id:'m1',role:'user',mode:'agent',content:'Make the Pair Programmer easier to use and keep the unique crystal reuse workflow visible.',files:['desktop-ide/renderer/js/pages/beast-workspace-page.js'],at:now-6000},{id:'m2',role:'assistant',mode:'agent',content:'I prepared 1 validated change in 1 file.\n\nThe file has not been written yet. The highlighted Monaco diff is ready for review.',progress:[{phase:'context',label:'Edit scope locked',detail:'desktop-ide/renderer/js/pages/beast-workspace-page.js',state:'done'},{phase:'tools',label:'Repository inspected',detail:'workspace page inspected',state:'done'},{phase:'validate',label:'Proposed files validated',detail:'passed · 2 bounded checks',state:'done'},{phase:'review',label:'Changes ready for review',detail:'1 governed operation',state:'ready'}],proposal:{ready:true,planId:'PLAN-VISUAL',validation:{ok:true,status:'passed',check_count:2,syntax_checked:1},files:['desktop-ide/renderer/js/pages/beast-workspace-page.js'],operations:[{id:'op-1',op:'replace_exact',path:'desktop-ide/renderer/js/pages/beast-workspace-page.js',intent:'Make file labels resilient to surrounding whitespace',old:"function fileName(path) { return String(path || '').split('/').pop() || path; }",new:"function fileName(path) { return String(path || '').trim().split('/').pop() || path; }"}]},at:now-1200}]};
}

function quickFiles(root, limit = 80) {
  const skip = new Set(['.git', 'node_modules', '.venv', 'venv', 'dist', 'build', '__pycache__', '.pytest_cache', 'data', 'logs']);
  const allowed = new Set(['.py', '.js', '.json', '.md', '.css', '.html', '.yml', '.yaml', '.toml', '.txt']);
  const roots = ['README.md', 'app', 'desktop-ide', 'tests', 'docs', 'catalog'];
  const rows = [];
  const seen = new Set();
  function add(file) {
    if (rows.length >= limit) return true;
    let stat;
    try {
      stat = fs.statSync(file);
    } catch {
      return false;
    }
    if (!stat.isFile() || stat.size > 180000) return false;
    const rel = path.relative(root, file);
    if (seen.has(rel)) return false;
    if (!allowed.has(path.extname(file).toLowerCase()) && !['Dockerfile', 'Makefile', 'requirements.txt'].includes(path.basename(file))) return false;
    seen.add(rel);
    rows.push({ path: rel, size: stat.size, ext: path.extname(file).toLowerCase() || path.basename(file) });
    return rows.length >= limit;
  }
  function walk(dir) {
    let entries = [];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name));
    } catch {
      return false;
    }
    for (const entry of entries) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (!skip.has(entry.name) && walk(full)) return true;
      } else if (add(full)) {
        return true;
      }
    }
    return false;
  }
  for (const item of roots) {
    const target = path.join(root, item);
    if (fs.existsSync(target)) {
      const done = fs.statSync(target).isDirectory() ? walk(target) : add(target);
      if (done) break;
    }
  }
  if (rows.length < limit) walk(root);
  return rows.slice(0, limit);
}

function registerIpc() {
  let protocolSequence=0;
  let zoomLevel=0;
  ipcMain.handle('beast:status', async () => ({
    ok: true,
    repoRoot,
    gatewayUrl: 'http://127.0.0.1:8017',
    desktopVersion: 'visual-audit',
    rendererPath: path.join(repoRoot, 'desktop-ide', 'renderer', 'index.html'),
    health: {
      ok: true,
      local_mode: true,
      mode: 'visual_audit',
      capabilities: { ok: true, mode: 'visual_audit', checks: {} },
    },
    gatewayLog: ['visual audit harness'],
  }));
  ipcMain.handle('beast:zoom-get', async () => ({ level: zoomLevel, factor: Math.pow(1.2, zoomLevel) }));
  ipcMain.handle('beast:zoom-set', async (_event, level) => {
    zoomLevel = Math.max(-3, Math.min(5, Math.round(Number(level) || 0)));
    return { level: zoomLevel, factor: Math.pow(1.2, zoomLevel) };
  });
  ipcMain.handle('beast:zoom-reset', async () => {
    zoomLevel = 0;
    return { level: zoomLevel, factor: 1 };
  });
  ipcMain.handle('beast:gateway-request', async (_event, request = {}) => ({
    ok: false,
    status: 503,
    error: `visual audit fixture has no live route for ${request.path || request.url || 'request'}`,
  }));
  ipcMain.handle('beast:list-files', async (_event, root, limit) => [...quickFiles(root || repoRoot, Math.max(1, (limit || 80) - 1)), { path:notebookVisualPath, size:Buffer.byteLength(notebookVisualDocument), ext:'.ipynb' }]);
  ipcMain.handle('beast:read-file', async (_event, root, rel, maxChars) => {
    if (rel === notebookVisualPath) return { ok:true, path:rel, text:notebookVisualDocument.slice(0, maxChars || 200000) };
    const target = path.resolve(root || repoRoot, rel || '');
    const safeRoot = path.resolve(root || repoRoot);
    if (target !== safeRoot && !target.startsWith(safeRoot + path.sep)) return { ok: false, error: 'path escaped workspace' };
    return { ok: true, path: rel, text: fs.readFileSync(target, 'utf8').slice(0, maxChars || 200000) };
  });
  ipcMain.handle('beast:file-operation', async () => ({ ok: true }));
  ipcMain.handle('beast:workspace-git-status', async () => ({ ok:true,branch:'feature/visual-audit...origin/feature/visual-audit [ahead 2]',branchName:'feature/visual-audit',branches:[{name:'feature/visual-audit',current:true},{name:'main',current:false}],changes:[{index:'M ',path:'README.md',originalPath:'',staged:true,unstaged:false,conflict:false,untracked:false},{index:' M',path:'desktop-ide/main.js',originalPath:'',staged:false,unstaged:true,conflict:false,untracked:false},{index:'??',path:'docs/source-control-notes.md',originalPath:'',staged:false,unstaged:true,conflict:false,untracked:true}],counts:{staged:1,unstaged:2,conflicts:0},diffStat:'2 files changed, 18 insertions(+), 4 deletions(-)',stagedDiffStat:'1 file changed, 6 insertions(+)',error:'' }));
  ipcMain.handle('beast:workspace-git-diff', async (_event,payload={}) => ({ ok:true,path:payload.path||'desktop-ide/main.js',originalPath:payload.originalPath||'',mode:payload.mode||'worktree',originalText:'function createWorkbench() {\n  return "baseline";\n}\n',modifiedText:'function createWorkbench() {\n  return "BEAST source control";\n}\n\n// Verified Monaco diff fixture\n',patch:'@@ -1,3 +1,5 @@',truncated:false }));
  ipcMain.handle('beast:workspace-git-action', async (_event,payload={}) => ({ ok:true,action:payload.action,path:payload.path||'',stdout:'',stderr:'',returncode:0,receipt:{id:'GIT-VISUAL-AUDIT',digest:'sha256:fixture',evidence:'operator-initiated'} }));
  ipcMain.handle('beast:workspace-git-commit', async () => ({ ok:true,stdout:'[feature/visual-audit abc1234] Visual audit commit',stderr:'',returncode:0,receipt:{id:'GIT-COMMIT-VISUAL',digest:'sha256:fixture',evidence:'operator-initiated'} }));
  ipcMain.handle('beast:workspace-git-branch', async (_event,payload={}) => ({ ok:true,operation:payload.operation,name:payload.name,stdout:'',stderr:'',returncode:0,receipt:{id:'GIT-BRANCH-VISUAL',digest:'sha256:fixture',evidence:'operator-initiated'} }));
  ipcMain.handle('beast:workspace-git-hunks', async (_event,payload={}) => ({ ok:true,path:payload.path||'',mode:payload.mode||'worktree',hunks:[{id:'HUNK-VISUAL-1',header:'@@ -1,3 +1,4 @@',context:'fixture',added:1,removed:0,oldStart:1,oldLines:3,newStart:1,newLines:4,lines:[' fixture hunk']}],summary:{count:1,added:1,removed:0} }));
  ipcMain.handle('beast:workspace-git-hunk-action', async (_event,payload={}) => ({ ok:true,action:payload.action,path:payload.path||'',receipt:{id:'GIT-HUNK-VISUAL',digest:'sha256:fixture',evidence:'operator-initiated'} }));
  ipcMain.handle('beast:workspace-git-conflict', async (_event,payload={}) => ({ ok:false,error:`${payload.path||'file'} is not currently unmerged.` }));
  ipcMain.handle('beast:workspace-git-resolve', async () => ({ ok:true,receipt:{id:'GIT-RESOLVE-VISUAL',digest:'sha256:fixture',evidence:'operator-initiated'} }));
  ipcMain.handle('beast:workspace-git-history', async () => ({ ok:true,commits:[{hash:'a1b2c3d4e5f6789012345678901234567890abcd',shortHash:'a1b2c3d',author:'BEAST Visual',date:'2026-07-17T00:00:00Z',subject:'Fixture source-control history'}] }));
  ipcMain.handle('beast:workspace-git-remotes', async () => ({ ok:true,remotes:[{name:'origin',fetch:'https://example.invalid/edgek/beast.git',push:'https://example.invalid/edgek/beast.git'}] }));
  ipcMain.handle('beast:workspace-git-operation', async (_event,payload={}) => ({ ok:true,action:payload.action,detail:payload.revision||payload.base||payload.remote||'origin',receipt:{id:'GIT-OP-VISUAL',digest:'sha256:fixture',evidence:'operator-initiated'} }));
  ipcMain.handle('beast:open-workspace-window', async workspace => ({ ok: true, workspace }));
  ipcMain.handle('beast:release-readiness', async () => ({ ok: true, score: 96, checks: 6, passed: 6, blockers: [] }));
  ipcMain.handle('beast:tooling-snapshot', async () => ({ ok: true, tools: [], mcp: { servers: [] } }));
  ipcMain.handle('beast:system-snapshot', async () => ({ ok: true, ports: { ports: [] }, processes: { processes: [] }, catalog: {} }));
  ipcMain.handle('beast:ide-compatibility', async () => ({ ok:true, source:'visual-audit', summary:{available:19,total:19,coverage:100}, extensionHost:{available:true,companion:true,desktopRuntime:true,status:'desktop-runtime-ready',detail:'isolated declarative runtime · explicit workspace grants'}, languages:[{id:'typescript',label:'TypeScript / JavaScript',languages:['typescript','javascript'],command:'typescript-language-server',available:true,detail:'ready'},{id:'pyright',label:'Python (Pyright)',languages:['python'],command:'pyright-langserver',available:true,detail:'ready'},{id:'pylsp',label:'Python (pylsp)',languages:['python'],command:'python3',available:true,detail:'ready'},{id:'go',label:'Go (gopls)',languages:['go'],command:'gopls',available:true,detail:'ready · BEAST managed tool'},{id:'bash',label:'Shell (bash-language-server)',languages:['shell'],command:'bash-language-server',available:true,detail:'ready'},{id:'json',label:'JSON Language Server',languages:['json'],command:'vscode-json-language-server',available:true,detail:'ready'},{id:'html',label:'HTML Language Server',languages:['html'],command:'vscode-html-language-server',available:true,detail:'ready'},{id:'css',label:'CSS Language Server',languages:['css'],command:'vscode-css-language-server',available:true,detail:'ready'},{id:'rust',label:'Rust Analyzer',languages:['rust'],command:'rust-analyzer',available:true,detail:'ready · /usr/bin/rust-analyzer'},{id:'clangd',label:'C / C++ (clangd)',languages:['c','cpp'],command:'clangd',available:true,detail:'ready · /usr/bin/clangd'}], debug:[{id:'debugpy',label:'Python debugpy',available:true,detail:'ready'},{id:'delve',label:'Go Delve DAP',available:true,detail:'ready · BEAST managed tool'},{id:'lldb',label:'LLDB DAP',available:true,detail:'ready · /usr/bin/lldb-dap'}], notebooks:[{id:'jupyter',label:'Jupyter notebooks',available:true,detail:'ready'},{id:'ipykernel',label:'Python kernel',available:true,detail:'ready'},{id:'beast-python',label:'BEAST Python cell runner',available:true,detail:'Python 3'}], remote:[{id:'ssh',label:'Remote SSH',available:true,detail:'OpenSSH'},{id:'ssh-forwarding',label:'SSH forwarding + reverse tunnels',available:true,detail:'strict host key · loopback-only -L/-R'},{id:'docker',label:'Dev containers',available:true,detail:'Docker'}], sessions:[] }));
  ipcMain.handle('beast:ide-capability-install', async (_event,options) => ({ok:true,kind:options.kind,id:options.id,label:options.id,resolved:'/visual-audit/managed-tool',detail:'Installed and verified.'}));
  ipcMain.handle('beast:ide-protocol-start', async event => { const id=`visual-lsp-${++protocolSequence}`;setTimeout(()=>{if(!event.sender.isDestroyed())event.sender.send('beast:ide-protocol-message',{sessionId:id,type:'ready',capabilities:{completionProvider:{},hoverProvider:true,definitionProvider:true}});},10);return {id,status:'running',adapter:'visual-audit'}; });
  ipcMain.handle('beast:ide-protocol-request', async (_event,payload={}) => payload.method==='textDocument/hover'?null:[]);
  ipcMain.handle('beast:ide-protocol-notify', async () => ({ok:true}));
  ipcMain.handle('beast:ide-protocol-stop', async () => ({ok:true,status:'stopped'}));
  ipcMain.handle('beast:notebook-execute', async payload => ({ ok:true, stdout:String(payload?.code || ''), stderr:'', returncode:0, receipt:{id:'NB-VISUAL-AUDIT',digest:'sha256:fixture'} }));
  ipcMain.handle('beast:notebook-kernel-start', async () => ({ status:'running', pid:4242, kernel:'beast-python' }));
  ipcMain.handle('beast:notebook-kernel-request', async payload => ({ ok:true, outputs:[{type:'stream',text:String(payload?.code || '')}], execution_count:1, receipt:{id:'NBK-VISUAL-AUDIT',digest:'sha256:fixture'} }));
  ipcMain.handle('beast:notebook-kernel-stop', async () => ({ ok:true, status:'stopped' }));
  ipcMain.handle('beast:remote-probe', async payload => ({ ok:true, host:payload?.host || 'dev@fixture', remote_root:payload?.path || '~', verification:'strict-known-host' }));
  ipcMain.handle('beast:remote-list-files', async () => ({ ok:true, files:[{path:'/fixture/README.md',size:1200}] }));
  ipcMain.handle('beast:remote-forward-list', async () => ({ ok:true, forwards:[] }));
  ipcMain.handle('beast:remote-forward-start', async (_event, payload) => ({ ok:true, forward:{id:'forward-visual-audit',status:'running',host:payload?.host || 'dev@fixture',direction:payload?.direction || 'local',localPort:Number(payload?.localPort || 3000),remotePort:Number(payload?.remotePort || 3000),targetHost:'127.0.0.1',url:`http://127.0.0.1:${Number(payload?.localPort || 3000)}`,visibility:'loopback-only'} }));
  ipcMain.handle('beast:remote-forward-stop', async () => ({ ok:true, status:'stopped' }));
  ipcMain.handle('beast:extension-host-discover', async () => ({ status:'running',pid:4243,mode:'declarative-manifests',extensions:[{id:'beast.companion',name:'BEAST Companion',version:'1.0.0',capabilities:['workspace.read','language.client'],granted:[],needsApproval:['workspace.read','language.client']}]}));
  ipcMain.handle('beast:extension-host-grant', async () => ({ status:'running',pid:4243,mode:'declarative-manifests',extensions:[{id:'beast.companion',name:'BEAST Companion',version:'1.0.0',capabilities:['workspace.read','language.client'],granted:['workspace.read','language.client'],needsApproval:[]}]}));
  ipcMain.handle('beast:extension-host-stop', async () => ({ ok:true,status:'stopped' }));
  ipcMain.handle('beast:choose-workspace', async () => repoRoot);
  ipcMain.handle('beast:workspace-folders', async () => ({root:repoRoot,folders:[{id:'EdgeK-BEAST',name:'EdgeK-BEAST',path:repoRoot,primary:true}]}));
  ipcMain.handle('beast:workspace-folder-add', async () => ({root:repoRoot,folders:[{id:'EdgeK-BEAST',name:'EdgeK-BEAST',path:repoRoot,primary:true}]}));
  ipcMain.handle('beast:workspace-folder-remove', async () => ({ok:false,error:'Visual audit keeps its primary workspace folder.'}));
  ipcMain.handle('beast:restart-gateway', async () => ({ ok: true }));
  ipcMain.handle('beast:open-gateway', async () => ({ ok: true }));
}

async function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function main() {
  fs.mkdirSync(outDir, { recursive: true });
  registerIpc();
  await app.whenReady();
  const win = new BrowserWindow({
    width: 1920,
    height: 1080,
    show: false,
    webPreferences: {
      preload: path.join(repoRoot, 'desktop-ide', 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });
  const messages = [];
  const results = [];
  win.webContents.on('console-message', (_event, level, message, line, sourceId) => {
    messages.push({ level, message, line, sourceId });
  });
  await win.loadFile(path.join(repoRoot, 'desktop-ide', 'renderer', 'index.html'));
  // Dynamic fixed overlays are not guaranteed to reach Chromium's compositor
  // surface while a BrowserWindow has never been shown. Render inactive so the
  // audit exercises the same paint path as the packaged desktop application.
  win.showInactive();
  await delay(2500);
  const onboardingVisible = await win.webContents.executeJavaScript(`Boolean(document.querySelector('[data-onboarding]:not(.hidden)'))`);
  if (onboardingVisible) {
    // The first-run journey is mounted after the initial store hydration. Give
    // Chromium two committed frames before capture so a hidden BrowserWindow
    // does not return the pre-overlay compositor surface.
    await win.webContents.executeJavaScript(`new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))`);
    await delay(350);
    const onboardingScreenshot=path.join(outDir,'00-onboarding.png');
    fs.writeFileSync(onboardingScreenshot,(await win.webContents.capturePage()).toPNG());
    const onboardingDiag=await win.webContents.executeJavaScript(`(() => { const host=document.querySelector('[data-onboarding]'); const shell=host?.querySelector('.beast-onboarding-shell'); const h=host?.getBoundingClientRect(); const s=shell?.getBoundingClientRect(); const style=shell?getComputedStyle(shell):null; const top=s?document.elementFromPoint(s.x+20,s.y+20):null; return {host:h?{x:Math.round(h.x),y:Math.round(h.y),w:Math.round(h.width),h:Math.round(h.height),display:getComputedStyle(host).display,z:getComputedStyle(host).zIndex}:null,shell:s?{x:Math.round(s.x),y:Math.round(s.y),w:Math.round(s.width),h:Math.round(s.height),display:style.display,z:style.zIndex,opacity:style.opacity,visibility:style.visibility,background:style.backgroundColor,text:shell.innerText.length,top:top?.className||top?.tagName}:null}; })()`);
    results.push({page:'onboarding',bodyPage:await win.webContents.executeJavaScript(`document.body.dataset.beastPage || ''`),screenshot:onboardingScreenshot,...onboardingDiag});
    await win.webContents.executeJavaScript(`window.BeastOnboarding && window.BeastOnboarding.close()`);
  }
  await win.webContents.executeJavaScript(`
    (async () => {
      if (window.refreshSnapshot) await window.refreshSnapshot({ force: true }).catch(() => {});
      if (window.refreshFiles) await window.refreshFiles({ force: true }).catch(() => {});
    })()
  `);
  await delay(1000);

  for (const page of pages) {
    // RC4 uses the contract router; the old setDesktopPage helper no longer
    // exists and caused every audit capture to remain on Studio.
    await win.webContents.executeJavaScript(`window.BeastRouter && window.BeastRouter.navigate(${JSON.stringify(page)}, { force: true });`);
    await win.webContents.executeJavaScript(`
      new Promise(resolve => {
        const started = Date.now();
        const tick = () => {
          const page = document.body.dataset.beastPage || '';
          if (page === ${JSON.stringify(page)} || Date.now() - started > 1500) resolve();
          else setTimeout(tick, 50);
        };
        tick();
      })
    `);
    if (page === 'workspace' || page === 'source') {
      await win.webContents.executeJavaScript(`window.refreshFiles && window.refreshFiles({ force: true }).catch(() => {});`);
    }
    await win.webContents.executeJavaScript(`
      new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
    `);
    await delay(900);
    const screenshot = path.join(outDir, `${String(pages.indexOf(page) + 1).padStart(2, '0')}-${page}.png`);
    const diag = await win.webContents.executeJavaScript(`
      (() => {
        const visible = [...document.querySelectorAll('[data-page-panel]')].filter(el => {
          const style = getComputedStyle(el);
          const rect = el.getBoundingClientRect();
          return !el.classList.contains('hidden') && style.display !== 'none' && rect.width > 1 && rect.height > 1;
        }).map(el => ({
          page: el.dataset.pagePanel,
          cls: el.className,
          text: el.textContent.replace(/\\s+/g, ' ').trim().slice(0, 80),
          rect: (() => { const r = el.getBoundingClientRect(); return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }; })()
        }));
        const content = document.querySelector('.content-panel')?.getBoundingClientRect();
        const centerText = document.querySelector('.content-panel')?.textContent.replace(/\\s+/g, ' ').trim() || '';
        const fileBody = document.querySelector('#fileExplorerBody')?.getBoundingClientRect();
        const fileRows = document.querySelectorAll('#fileList .file-item, #fileList .mini-card, #fileList .tree-file').length;
        return {
          page: ${JSON.stringify(page)},
          bodyPage: document.body.dataset.beastPage || '',
          dashboard: document.querySelector('.app-shell')?.dataset.dashboardPage || '',
          visible,
          visibleCount: visible.length,
          contentRect: content ? { x: Math.round(content.x), y: Math.round(content.y), w: Math.round(content.width), h: Math.round(content.height) } : null,
          contentChars: centerText.length,
          fileExplorer: fileBody ? { x: Math.round(fileBody.x), y: Math.round(fileBody.y), w: Math.round(fileBody.width), h: Math.round(fileBody.height), rows: fileRows } : null,
          horizontalOverflow: document.documentElement.scrollWidth - window.innerWidth,
          verticalOverflow: document.documentElement.scrollHeight - window.innerHeight
        };
      })()
    `);
    await win.webContents.executeJavaScript(`
      new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
    `);
    const image = await win.webContents.capturePage();
    fs.writeFileSync(screenshot, image.toPNG());
    diag.screenshot = screenshot;
    results.push(diag);
    if (page === 'compatibility') {
      await win.webContents.executeJavaScript(`(() => { const viewport=document.getElementById('beastMainViewport'); if(viewport) viewport.scrollTop=viewport.scrollHeight; })()`);
      await win.webContents.executeJavaScript(`new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))`);
      await delay(250);
      const runtimeScreenshot = path.join(outDir, '01-compatibility-runtime.png');
      const runtimeImage = await win.webContents.capturePage();
      fs.writeFileSync(runtimeScreenshot, runtimeImage.toPNG());
      const runtimeDiag = await win.webContents.executeJavaScript(`(() => { const workbench=document.querySelector('.compat-runtime-grid')?.getBoundingClientRect(); return { workbench:workbench?{x:Math.round(workbench.x),y:Math.round(workbench.y),w:Math.round(workbench.width),h:Math.round(workbench.height)}:null, horizontalOverflow:document.documentElement.scrollWidth-window.innerWidth, verticalOverflow:document.documentElement.scrollHeight-window.innerHeight }; })()`);
      results.push({ page:'compatibility-runtime', bodyPage:'compatibility', screenshot:runtimeScreenshot, ...runtimeDiag });
    }
    if (page === 'workspace') {
      const aiFixture=aiVisualFixture();
      await win.webContents.executeJavaScript(`(async () => { const fixture=${JSON.stringify(aiFixture)};const model=window.BeastStore.get().models.registry[0]||{};const proposal=fixture.messages.find(message=>message.proposal)?.proposal;await window.BeastEditorCortex?.openFile(proposal.files[0]);window.BeastStore?.patch('sourcePlan',{status:'draft',plan:{plan_id:proposal.planId,kind:'beast_ide_agent_action_ir_sourceplan',objective:'Visual AI hunk audit',validation:proposal.validation,operations:proposal.operations.map(item=>({op_id:item.id,op:item.op,path:item.path,old:item.old,new:item.new,description:item.intent}))},selectedOperationIds:proposal.operations.map(item=>item.id)});window.BeastStore?.patch('aiCoding',{...fixture,model:model.id||'',provider:model.provider||''});})()`);
      await win.webContents.executeJavaScript(`new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))`);
      await delay(500);
      const aiScreenshot = path.join(outDir, '01-workspace-ai.png');
      const aiImage = await win.webContents.capturePage();
      fs.writeFileSync(aiScreenshot, aiImage.toPNG());
      const aiDiag = await win.webContents.executeJavaScript(`(() => {
        const panel = document.querySelector('[data-ai-panel]')?.getBoundingClientRect();
        const editor = document.querySelector('.cortex-editor')?.getBoundingClientRect();
        return {
          panel: panel ? { x:Math.round(panel.x), y:Math.round(panel.y), w:Math.round(panel.width), h:Math.round(panel.height) } : null,
          editor: editor ? { x:Math.round(editor.x), y:Math.round(editor.y), w:Math.round(editor.width), h:Math.round(editor.height) } : null,
          messageFont: getComputedStyle(document.querySelector('.cortex-ai-message-body')).fontSize,
          composerHeight: Math.round(document.querySelector('[data-ai-prompt]')?.getBoundingClientRect().height||0),
          contextCollapsed: !document.querySelector('.cortex-ai-context')?.open,
          aiDiffMode: document.querySelector('[data-git-diff-mode]')?.textContent||'',
          aiDiffVisible: !document.querySelector('[data-git-diff-workbench]')?.classList.contains('hidden'),
          activeDiffEditors: window.BeastStore.get().diagnostics.activeDiffEditors||0,
          horizontalOverflow: document.documentElement.scrollWidth - window.innerWidth,
          verticalOverflow: document.documentElement.scrollHeight - window.innerHeight
        };
      })()`);
      results.push({ page:'workspace-ai', bodyPage:'workspace', screenshot:aiScreenshot, ...aiDiag });
      await win.webContents.executeJavaScript(`window.BeastAICoding && window.BeastAICoding.setExpanded(true);`);
      await win.webContents.executeJavaScript(`new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))`);
      await delay(300);
      const aiFocusScreenshot=path.join(outDir,'01-workspace-ai-focus.png');
      fs.writeFileSync(aiFocusScreenshot,(await win.webContents.capturePage()).toPNG());
      const aiFocusDiag=await win.webContents.executeJavaScript(`(() => { const layout=document.querySelector('.cortex-layout');const panel=document.querySelector('[data-ai-panel]')?.getBoundingClientRect();const editor=document.querySelector('.cortex-editor')?.getBoundingClientRect();return {focus:layout?.classList.contains('ai-focus')||false,panel:panel?{x:Math.round(panel.x),y:Math.round(panel.y),w:Math.round(panel.width),h:Math.round(panel.height)}:null,editor:editor?{x:Math.round(editor.x),y:Math.round(editor.y),w:Math.round(editor.width),h:Math.round(editor.height)}:null,explorerHidden:getComputedStyle(document.querySelector('.cortex-explorer')).display==='none',horizontalOverflow:document.documentElement.scrollWidth-window.innerWidth};})()`);
      results.push({page:'workspace-ai-focus',bodyPage:'workspace',screenshot:aiFocusScreenshot,...aiFocusDiag});
      await win.webContents.executeJavaScript(`window.BeastAICoding && window.BeastAICoding.setExpanded(false);`);
      await win.webContents.executeJavaScript(`window.BeastAICoding && window.BeastAICoding.setOpen(false);`);
      await win.webContents.executeJavaScript(`document.querySelector('[data-git-diff-action="close"]')?.click();`);
      await win.webContents.executeJavaScript(`document.querySelector('[data-explorer-tab="changes"]')?.click();`);
      await win.webContents.executeJavaScript(`new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))`);
      await delay(300);
      const scmScreenshot = path.join(outDir, '01-workspace-source-control.png');
      fs.writeFileSync(scmScreenshot,(await win.webContents.capturePage()).toPNG());
      const scmDiag=await win.webContents.executeJavaScript(`(() => { const pane=document.querySelector('.cortex-scm-pane'); const rect=pane?.getBoundingClientRect(); return {pane:rect?{x:Math.round(rect.x),y:Math.round(rect.y),w:Math.round(rect.width),h:Math.round(rect.height)}:null,rows:document.querySelectorAll('.cortex-scm-row').length,groups:document.querySelectorAll('.cortex-scm-pane>section').length,commit:Boolean(document.querySelector('[data-git-commit-message]')),branch:document.querySelector('[data-git-branch-select]')?.value||'',horizontalOverflow:document.documentElement.scrollWidth-window.innerWidth}; })()`);
      results.push({page:'workspace-source-control',bodyPage:'workspace',screenshot:scmScreenshot,...scmDiag});
      await win.webContents.executeJavaScript(`document.querySelector('[data-git-diff-mode="worktree"]')?.click();`);
      await win.webContents.executeJavaScript(`new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))`);
      await delay(500);
      const gitDiffScreenshot=path.join(outDir,'01-workspace-git-diff.png');
      fs.writeFileSync(gitDiffScreenshot,(await win.webContents.capturePage()).toPNG());
      const gitDiffDiag=await win.webContents.executeJavaScript(`(() => { const workbench=document.querySelector('[data-git-diff-workbench]'); const rect=workbench?.getBoundingClientRect(); return {workbench:rect?{x:Math.round(rect.x),y:Math.round(rect.y),w:Math.round(rect.width),h:Math.round(rect.height)}:null,visible:Boolean(workbench&&!workbench.classList.contains('hidden')),monacoDiffs:document.querySelectorAll('.monaco-diff-editor').length,breadcrumbs:document.querySelector('[data-editor-breadcrumbs]')?.textContent.trim()||'',horizontalOverflow:document.documentElement.scrollWidth-window.innerWidth}; })()`);
      results.push({page:'workspace-git-diff',bodyPage:'workspace',screenshot:gitDiffScreenshot,...gitDiffDiag});
      await win.webContents.executeJavaScript(`document.querySelector('[data-git-diff-action="close"]')?.click();`);
      await win.webContents.executeJavaScript(`window.BeastEditorCortex && window.BeastEditorCortex.openFile(${JSON.stringify(notebookVisualPath)});`);
      await win.webContents.executeJavaScript(`new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))`);
      await delay(350);
      const notebookScreenshot = path.join(outDir, '01-workspace-notebook.png');
      const notebookImage = await win.webContents.capturePage();
      fs.writeFileSync(notebookScreenshot, notebookImage.toPNG());
      const notebookDiag = await win.webContents.executeJavaScript(`(() => { const workbench=document.querySelector('[data-notebook-workbench]'); const cells=[...document.querySelectorAll('[data-notebook-cell]')]; const rect=workbench?.getBoundingClientRect(); return {workbench:rect?{x:Math.round(rect.x),y:Math.round(rect.y),w:Math.round(rect.width),h:Math.round(rect.height)}:null,cells:cells.length,outputs:document.querySelectorAll('.beast-notebook-output').length,horizontalOverflow:document.documentElement.scrollWidth-window.innerWidth,verticalOverflow:document.documentElement.scrollHeight-window.innerHeight}; })()`);
      results.push({ page:'workspace-notebook', bodyPage:'workspace', screenshot:notebookScreenshot, ...notebookDiag });
      await win.webContents.executeJavaScript(`window.BeastCommandPalette && window.BeastCommandPalette.open('files');`);
      await win.webContents.executeJavaScript(`new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))`);
      await delay(220);
      const paletteScreenshot = path.join(outDir, '01-command-palette.png');
      const paletteImage = await win.webContents.capturePage();
      fs.writeFileSync(paletteScreenshot, paletteImage.toPNG());
      const paletteDiag = await win.webContents.executeJavaScript(`(() => { const host=document.querySelector('.beast-command-palette'); const input=host?.querySelector('[data-palette-input]'); const rect=host?.querySelector('.beast-palette-shell')?.getBoundingClientRect(); return {open:Boolean(host&&!host.hidden),focused:document.activeElement===input,rows:host?.querySelectorAll('[data-palette-index]').length||0,shell:rect?{x:Math.round(rect.x),y:Math.round(rect.y),w:Math.round(rect.width),h:Math.round(rect.height)}:null,horizontalOverflow:document.documentElement.scrollWidth-window.innerWidth}; })()`);
      results.push({ page:'command-palette', bodyPage:'workspace', screenshot:paletteScreenshot, ...paletteDiag });
      await win.webContents.executeJavaScript(`window.BeastCommandPalette && window.BeastCommandPalette.close();`);
    }
  }
  fs.writeFileSync(path.join(outDir, 'report.json'), JSON.stringify({ results, console: messages }, null, 2));
  console.log(JSON.stringify({ outDir, results, consoleErrors: messages.filter(item => item.level >= 2).slice(0, 20) }, null, 2));
  await win.close();
  app.quit();
}

main().catch(error => {
  console.error(error);
  app.exit(1);
});
