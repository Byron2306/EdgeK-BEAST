(() => {
  const commandRows = [
    ['Open Workspace', 'Choose a folder and index its files', 'workspace.open'],
    ['Open Editor Cortex', 'Navigate to the multi-tab workspace editor', '/workspace'],
    ['Show Active Workspace Registry', 'Open the multi-worktree workspace registry', '/workspace registry'],
    ['Open IDE Compatibility', 'Inspect LSP, debugging, notebooks, remote, and extensions', '/compatibility'],
    ['Open Remote Development', 'Connect an SSH workspace, terminals, and loopback forwards', '/remote dev'],
    ['Discover Extensions', 'Start the mediated extension host and inspect workspace manifests', '/extensions discover'],
    ['Start Live Coding Session', 'Open the governed coding agent with active-file context', 'ai.active'],
    ['Open Pair Programmer Context Controls', 'Open the governed coding assistant and its context controls', '/context'],
    ['Prepare Provider Handoff', 'Open the coding agent handoff surface', '/handoff'],
    ['Split Editor', 'Toggle the secondary editor pane', '/editor split'],
    ['Draft SourcePlan', 'Stage active local edits for governed review', '/sourceplan draft'],
    ['Upgrade SourcePlan Draft', 'Recompile the active editor change into governed review', '/sourceplan upgrade'],
    ['Preview SourcePlan Hunks', 'Open the patch review and selected-hunk surface', '/sourceplan preview'],
    ['Verify SourcePlan', 'Run SourcePlan lifecycle verification', '/sourceplan verify'],
    ['Apply Verified SourcePlan', 'Apply approved selected operations with evidence and rollback', '/sourceplan apply'],
    ['Rollback Latest SourcePlan', 'Restore the latest captured governed rollback snapshot', '/sourceplan rollback'],
    ['Open Approval Queue', 'Review pending governed decisions', '/approvals'],
    ['Open Terminal', 'Open governed commands, tasks, Git, and search', '/terminal'],
    ['Open Mission Cockpit', 'Return to mission definition and journey', '/mission'],
    ['Open Session Levers', 'Open desktop settings for operator workflow controls', '/session levers'],
    ['Run Diagnostics Refresh', 'Probe the desktop and gateway health surface', '/doctor'],
    ['Reset BEAST Runtime Stack', 'Confirmably restart Guardian, Commons, daemon, gateway, proxy, LiteLLM, MCP, Ollama, and Nginx', '/runtime reset'],
    ['Open Compute Economy', 'Inspect verified savings and provider mix', '/economy'],
    ['Open Provider Fitness', 'Inspect configured model routes and diagnostics', '/providers'],
    ['Import Local Provider Secrets', 'Import a local .env-style provider-secret file into the BEAST vault', '/providers import-secrets'],
    ['Open Intelligence Workbench', 'Open the agent-aware coding workspace', '/intelligence'],
    ['Open Chronicle', 'Inspect operational history and receipts', '/chronicle'],
    ['Open Settings', 'Adjust desktop presentation and governance controls', '/settings'],
    ['Reset Workbench Layout', 'Restore navigation, telemetry, and workspace pane defaults', '/layout reset'],
    ['Open Crystallization', 'Inspect reusable verified compute', '/crystal'],
    ['Refresh Workspace Files', 'Re-index the selected local workspace', '/refresh files'],
    ['Refresh Desktop Surfaces', 'Refresh the current operational state', '/refresh'],
    ['Refresh IDE Capabilities', 'Probe installed LSP, DAP, notebook, and remote support', 'compat.refresh'],
  ];
  let host = null;
  let input = null;
  let list = null;
  let hint = null;
  let closeButton = null;
  let selected = 0;
  let rows = [];
  let lastFocus = null;
  let openMode = 'files';
  const recentsStorageKey = 'beast.command-palette.recents.v1';

  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' })[char]);
  const isTyping = node => Boolean(node?.matches?.('input,textarea,[contenteditable="true"],.monaco-editor textarea'));
  function score(value, query) {
    const source = String(value || '').toLowerCase(); const needle = String(query || '').toLowerCase().trim();
    if (!needle) return 1;
    let index = -1; let total = 0;
    for (const character of needle) { index = source.indexOf(character, index + 1); if (index < 0) return 0; total += Math.max(1, 24 - index); }
    return total + (source.includes(needle) ? 120 : 0);
  }
  function recentCommandIds() {
    try { const ids = JSON.parse(localStorage.getItem(recentsStorageKey) || '[]'); return Array.isArray(ids) ? ids.filter(Boolean).slice(0, 12) : []; } catch (_) { return []; }
  }
  function rememberCommand(id) {
    try { localStorage.setItem(recentsStorageKey, JSON.stringify([id, ...recentCommandIds().filter(item => item !== id)].slice(0, 12))); } catch (_) {}
  }
  function paletteRows(query = '') {
    const state = BeastStore.get(); const commandMode = openMode === 'commands' || query.startsWith('>'); const needle = commandMode ? query.replace(/^>\s*/, '') : query;
    if (commandMode) {
      const extensionCommands=(state.compatibility?.runtime?.extensions?.items||[]).flatMap(extension=>(extension.contributes?.commands||[]).map(command=>({kind:'extension-command',title:command.title||command.id,detail:`${extension.name||extension.id} · extension command`,id:`extension:${extension.id}:${command.id}`,extensionId:extension.id,command:command.id,score:score(`${command.title||command.id} ${extension.name||extension.id} ${command.id}`,needle)}))).filter(row=>row.score);
      const commands=[...commandRows.map(([title, detail, id]) => ({ kind:'command', title, detail, id, score:score(`${title} ${detail} ${id}`, needle) })).filter(row => row.score),...extensionCommands];
      if (needle.trim()) return commands.sort((a,b) => b.score - a.score).slice(0, 12);
      const byId = new Map(commands.map(row => [row.id,row])); const recent = recentCommandIds().map(id => byId.get(id)).filter(Boolean).map(row => ({...row,kind:'recent-command'}));
      return [...recent,...commands.filter(row => !recent.some(item => item.id === row.id))].slice(0,12);
    }
    const files = (state.workspace.files || []).filter(file => file.type !== 'directory').map(file => ({ kind:'file', title:file.name || String(file.path).split('/').pop(), detail:file.path, id:file.path, score:score(`${file.path} ${file.name || ''}`, needle) })).filter(row => row.score);
    if (needle.trim()) return files.sort((a,b) => b.score - a.score || a.detail.localeCompare(b.detail)).slice(0,80);
    const byPath = new Map(files.map(row => [row.id,row])); const recent = (state.editor.recentFiles || []).map(path => byPath.get(path)).filter(Boolean).map(row => ({...row,kind:'recent-file'}));
    return [...recent,...files.filter(row => !recent.some(item => item.id === row.id)).sort((a,b) => a.detail.localeCompare(b.detail))].slice(0,80);
  }
  function render() {
    if (!host || host.hidden) return;
    rows = paletteRows(input.value); selected = Math.max(0, Math.min(selected, Math.max(0, rows.length - 1)));
    const commandMode = openMode === 'commands' || input.value.startsWith('>');
    hint.textContent = commandMode ? 'Commands · ↑↓ navigate · Enter run · Esc close' : 'Files · ↑↓ navigate · Enter open · > commands · Esc close';
    list.innerHTML = rows.length ? rows.map((row,index) => { const file = row.kind.endsWith('file'); const recent = row.kind.startsWith('recent-'); return `<button type="button" class="beast-palette-row ${index === selected ? 'active' : ''}" data-palette-index="${index}" role="option" aria-selected="${index === selected}"><span class="beast-palette-kind">${recent ? 'RECENT' : file ? 'FILE' : 'CMD'}</span><span><b>${esc(row.title)}</b><small>${esc(row.detail)}</small></span><i>${file ? '↵' : '→'}</i></button>`; }).join('') : `<div class="beast-palette-empty">${commandMode ? 'No command matches. Try “> terminal” or “> sourceplan”.' : 'No workspace file matches. Choose a folder, then try again.'}</div>`;
    list.querySelector('.active')?.scrollIntoView({ block:'nearest' });
  }
  async function execute(row) {
    if (!row) return;
    if (row.kind.endsWith('file')) { await BeastEditorCortex.openFile(row.id); await BeastRouter.navigate('workspace'); BeastStore.addLedger(`Quick open: ${row.id}`); close(); return; }
    if (row.id === 'workspace.open') { await BeastDesktopBridge.chooseWorkspace(); await BeastDesktopBridge.listFiles(); await BeastEditorCortex.restoreTabs(); await BeastRouter.navigate('workspace'); close(); return; }
    if (row.id === 'ai.active') { await BeastRouter.navigate('workspace'); BeastAICoding.setOpen(true); BeastAICoding.addActiveFile(); close(); return; }
    if (row.id === 'compat.refresh') { await BeastIDECompatibility.refresh(); await BeastRouter.navigate('compatibility'); close(); return; }
    if (row.kind==='extension-command') { await BeastIDERuntime.executeExtensionCommand(row.extensionId,row.command); BeastStore.addLedger(`Extension command: ${row.extensionId} · ${row.command}`); rememberCommand(row.id); close(); return; }
    rememberCommand(row.id); await window.BeastCommand?.run?.(row.id); close();
  }
  function close() { if (!host || host.hidden) return; host.hidden = true; document.body.classList.remove('beast-palette-open'); lastFocus?.focus?.({ preventScroll:true }); }
  function open(mode = 'files') { if (!host) return; lastFocus = document.activeElement; openMode = mode; selected = 0; host.hidden = false; document.body.classList.add('beast-palette-open'); input.value = mode === 'commands' ? '>' : ''; render(); requestAnimationFrame(() => input.focus()); }
  function bind() {
    host = document.createElement('section'); host.className = 'beast-command-palette'; host.hidden = true; host.setAttribute('role','dialog'); host.setAttribute('aria-modal','true'); host.setAttribute('aria-labelledby','beastPaletteTitle');
    host.innerHTML = `<div class="beast-palette-backdrop" data-palette-close></div><div class="beast-palette-shell"><header><div><small>BEAST QUICK ACCESS</small><h2 id="beastPaletteTitle">Open file or run command</h2></div><button type="button" data-palette-close aria-label="Close quick access">×</button></header><label><span>⌕</span><input data-palette-input autocomplete="off" spellcheck="false" aria-autocomplete="list" aria-controls="beastPaletteResults" placeholder="Search workspace files…"></label><div id="beastPaletteResults" class="beast-palette-results" role="listbox"></div><footer data-palette-hint></footer></div>`;
    document.body.append(host); input = host.querySelector('[data-palette-input]'); list = host.querySelector('#beastPaletteResults'); hint = host.querySelector('[data-palette-hint]'); closeButton = host.querySelector('[data-palette-close]');
    input.addEventListener('input', () => { selected = 0; render(); });
    input.addEventListener('keydown', event => { if (event.key === 'ArrowDown') { event.preventDefault(); selected = Math.min(rows.length - 1, selected + 1); render(); } else if (event.key === 'ArrowUp') { event.preventDefault(); selected = Math.max(0, selected - 1); render(); } else if (event.key === 'Enter') { event.preventDefault(); execute(rows[selected]).catch(error => BeastStore.patch('workspace',{error:String(error.message || error)})); } else if (event.key === 'Escape') close(); });
    host.addEventListener('click', event => { if (event.target.closest('[data-palette-close]')) { close(); return; } const target = event.target.closest('[data-palette-index]'); if (target) execute(rows[Number(target.dataset.paletteIndex)]).catch(error => BeastStore.patch('workspace',{error:String(error.message || error)})); });
    document.addEventListener('keydown', event => { const mod = event.ctrlKey || event.metaKey; if (mod && event.key.toLowerCase() === 'p') { event.preventDefault(); open(event.shiftKey ? 'commands' : 'files'); return; } if (event.key === 'Escape' && !host.hidden) close(); if (event.key === 'F1' && !isTyping(event.target)) { event.preventDefault(); open('commands'); } });
  }
  window.BeastCommandPalette = { open, close, get isOpen() { return Boolean(host && !host.hidden); } };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind, { once:true }); else bind();
})();
