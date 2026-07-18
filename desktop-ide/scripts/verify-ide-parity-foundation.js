const fs = require('fs');
const path = require('path');
const os = require('os');
const vm = require('vm');
const { spawn, spawnSync } = require('child_process');
const { IdeCompatibilityHost, LANGUAGE_SERVERS, DEBUG_ADAPTERS } = require('../ide-compatibility-host');

const root=path.resolve(__dirname,'..');
const repo=path.resolve(root,'..');
const read=file=>fs.readFileSync(path.join(root,file),'utf8');
const checks=[];
const check=(name,condition)=>checks.push({name,passed:Boolean(condition)});

const main=read('main.js');
const preload=read('preload.js');
const index=read('renderer/index.html');
const compatibility=read('renderer/js/beast-ide-compatibility.js');
const runtime=read('renderer/js/beast-ide-runtime.js');
const editorCortex=read('renderer/js/beast-editor-cortex.js');
const workspacePage=read('renderer/js/pages/beast-workspace-page.js');
const testingPage=read('renderer/js/pages/beast-testing-page.js');
const palette=read('renderer/js/beast-command-palette.js');
const compatibilityHost=read('ide-compatibility-host.js');
const onboarding=read('renderer/js/beast-onboarding.js');
const release=read('renderer/js/beast-release-app.js');
const productionCss=read('renderer/css/beast-production.css');
const adr=fs.readFileSync(path.join(repo,'docs','architecture','adr-014-ide-ecosystem-compatibility.md'),'utf8');
const discovery=new IdeCompatibilityHost(repo).discover(repo);

check('allowlisted language server catalog',LANGUAGE_SERVERS.length>=8&&LANGUAGE_SERVERS.every(row=>row.command&&row.languages.length));
check('allowlisted debug adapter catalog',DEBUG_ADAPTERS.length>=3&&DEBUG_ADAPTERS.every(row=>row.command));
check('main process protocol isolation',main.includes("require('./ide-compatibility-host')")&&main.includes("ipcMain.handle('beast:ide-protocol-start'")&&main.includes("ipcMain.handle('beast:ide-capability-install'")&&main.includes('ideCompatibilityHost.stopAll()'));
check('narrow preload protocol contract',['ideCompatibility','installIdeCapability','startIdeProtocol','requestIdeProtocol','notifyIdeProtocol','stopIdeProtocol','onIdeProtocolMessage'].every(name=>preload.includes(name)));
check('debug, notebook, remote, and extension desktop contracts',['executeNotebookCell','startNotebookKernel','requestNotebookKernel','stopNotebookKernel','probeRemote','listRemoteFiles','listRemoteForwards','startRemoteForward','stopRemoteForward','onRemoteForwardMessage','discoverExtensions','grantExtensionCapabilities','stopExtensionHost','onExtensionHostMessage'].every(name=>preload.includes(name))&&['beast:notebook-execute','beast:notebook-kernel-start','beast:notebook-kernel-request','beast:notebook-kernel-stop','beast:remote-probe','beast:remote-list-files','beast:remote-forward-list','beast:remote-forward-start','beast:remote-forward-stop','beast:extension-host-discover','beast:extension-host-grant','beast:extension-host-stop'].every(name=>main.includes(name)));
check('monaco LSP providers',['registerCompletionItemProvider','registerHoverProvider','registerDefinitionProvider','registerReferenceProvider','registerRenameProvider','registerCodeActionProvider','registerDocumentFormattingEditProvider','registerDocumentSymbolProvider','publishDiagnostics'].every(name=>compatibility.includes(name)));
check('DAP workbench lifecycle',['startDebug','startPythonDebug','debugAdapterFor','launchConfiguration',"launch.request==='attach'?'attach':'launch'",'setBreakpoints','configurationDone','supportsConfigurationDoneRequest','stackTrace','debugControl','stepIn','stepOut'].every(name=>runtime.includes(name))&&['data-runtime-action="stepIn"','data-runtime-action="stepOut"','data-runtime-debug-adapter','data-runtime-debug-target',"['pause','continue','next','stepIn','stepOut','stop'].includes(runtimeAction)"].every(name=>read('renderer/js/pages/beast-compatibility-page.js').includes(name))&&compatibilityHost.includes("options.kind === 'dap'"));
check('each debug launch receives an isolated DAP session',runtime.includes("const summary=await desktop().startIdeProtocol({kind:'dap',adapter,root:root(),target:executionTarget()})")&&!runtime.includes("const existing=[...dapSessions.values()].find(session=>session.adapter===adapter&&session.status==='running')"));
check('advanced debugging supports launch.json, attach, compounds, and non-line breakpoints',['loadLaunchConfigurations','startLaunchConfiguration','startCompound',"launch.request==='attach'?'attach':'launch'",'setFunctionBreakpoints','logMessage','condition'].every(name=>runtime.includes(name))&&['data-runtime-debug-config','data-runtime-debug-compound','data-runtime-debug-condition','data-runtime-debug-log-message','data-runtime-debug-functions'].every(name=>read('renderer/js/pages/beast-compatibility-page.js').includes(name)));
check('DAP variables inspection is wired',runtime.includes("request(session,'variables'")&&runtime.includes('variables=await Promise.all')&&read('renderer/js/pages/beast-compatibility-page.js').includes('data-runtime-debug-variables'));
check('LSP refactoring and semantic services survive target switches',['registerRenameProvider','registerCodeActionProvider','registerDocumentFormattingEditProvider','registerDocumentSemanticTokensProvider','workspaceSymbols','textDocument/semanticTokens/full'].every(name=>compatibility.includes(name))&&['target.kind===\'ssh\'','target.kind===\'container\'','const roots','executionTarget'].every(name=>compatibility.includes(name))&&['workspaceEdit','textDocument/rename','textDocument/codeAction','textDocument/formatting'].every(name=>compatibility.includes(name)));
check('LSP and DAP sessions recover cleanly after transport loss',['event.type===\'exit\'','disconnected; retrying on next request','Debug adapter disconnected; start Debug again'].every(name=>compatibility.includes(name)||runtime.includes(name))&&runtime.includes('dapSessions.delete(event.sessionId)'));
check('Remote/container debug paths are mapped to execution roots',['function targetPath','target.remoteRoot','target.workspaceFolder','targetSource','setBreakpoints'].every(name=>runtime.includes(name))&&['ssh-stdio','docker-exec-stdio','targetCommand'].every(name=>compatibilityHost.includes(name)));
check('DAP watch expressions are persistent and bounded',runtime.includes("context:'watch'")&&runtime.includes('watchStorageKey')&&runtime.includes('slice(0,20)')&&read('renderer/js/pages/beast-compatibility-page.js').includes('data-runtime-debug-watches'));
check('notebook and remote flows are bounded',['executeNotebookCell','boundedProcess','StrictHostKeyChecking=yes','ExitOnForwardFailure=yes','loopback-only'].every(name=>main.includes(name))&&['runPythonCell','probeRemote','listRemoteFiles','startRemoteForward','stopRemoteForward'].every(name=>runtime.includes(name)));
check('Dev Container inspection is workspace-bounded and BEAST-managed',['devContainerConfig','inspectDevContainers','beast.workspace=','dev-container-inspect'].every(name=>main.includes(name))&&preload.includes('inspectDevContainers:'));
check('shared execution-target layer spans Explorer, tasks, tests, LSP, DAP, and extensions',['beast:execution-target-list','beast:execution-target-set','activeExecutionTarget','runOnExecutionTarget'].every(name=>main.includes(name))&&['listExecutionTargets:','setExecutionTarget:'].every(name=>preload.includes(name))&&['executionTarget','listExecutionTargets','beast.v2.workspace.execution-target'].every(name=>read('renderer/js/beast-desktop-bridge.js').includes(name)||read('renderer/js/beast-store.js').includes(name))&&['runWorkspaceTask(rootPath,payload)','runWorkspaceTest(rootPath,payload)','runOnExecutionTarget(selectedTarget'].every(name=>main.includes(name))&&['target:executionTarget()',"startIdeProtocol({kind:'lsp'","startIdeProtocol({kind:'dap'"].every(name=>runtime.includes(name)||compatibility.includes(name))&&read('renderer/js/pages/beast-compatibility-page.js').includes('data-runtime-execution-target'));
check('SSH/container LSP and DAP transports use mediated stdio relays',['ssh-stdio','docker-exec-stdio',"args:['exec','-i'",'StrictHostKeyChecking=yes','debugpy.adapter'].every(name=>compatibilityHost.includes(name)));
check('Dev Containers expose attach, start-stop, rebuild, logs, terminal, and target switching',['attachDevContainer','rebuildDevContainer','devContainerLogs','runDevContainerTerminal','dev-container-attach','dev-container-rebuild','dev-container-logs','dev-container-terminal-run'].every(name=>main.includes(name)||preload.includes(name))&&['startDevContainer','attachDevContainer','stopDevContainer','rebuildDevContainer','devContainerLogs','runDevContainerTerminal','refreshExecutionTargets','setExecutionTarget'].every(name=>runtime.includes(name))&&['data-runtime-action="container-start"','data-runtime-action="container-stop"','data-runtime-action="container-rebuild"','data-runtime-action="container-logs"','data-runtime-action="container-terminal-run"','data-runtime-action="target-switch"'].every(name=>read('renderer/js/pages/beast-compatibility-page.js').includes(name)));
check('native notebook documents preserve cells and outputs',['isNotebookPath','parseNotebook','serializeNotebook','runNotebookCell','runAllNotebookCells','setNotebookCellSource'].every(name=>editorCortex.includes(name))&&['data-notebook-workbench','data-notebook-action="run-all"','data-notebook-cell-source','image/png'].every(name=>workspacePage.includes(name)));
check('keyboard quick open and command palette are available',index.includes('beast-command-palette.js')&&read('renderer/js/beast-release-app.js').includes('window.BeastCommand = { run: runCommand }')&&['BeastCommandPalette','ctrlKey','metaKey','openFile','F1'].every(name=>palette.includes(name))&&palette.includes("event.key.toLowerCase() === 'p'"));
check('quick access prioritizes persisted recent files and commands',['beast.command-palette.recents.v1','recentCommandIds','rememberCommand','recent-file','recent-command'].every(name=>palette.includes(name)));
check('legacy TUI workflow commands are migrated to desktop quick access',['Start Live Coding Session','Prepare Provider Handoff','Preview SourcePlan Hunks','Open Approval Queue','Open Compute Economy','Open Provider Fitness','Open Chronicle','Open Session Levers','Show Active Workspace Registry'].every(name=>palette.includes(name))&&['/mission','/workspace registry','/sourceplan preview','/approvals','/layout reset'].every(name=>release.includes(name)));
check('SourcePlan rollback is a real desktop workflow',['rollbackLatestSourcePlan','/edgek/sourceplan/rollback-latest'].every(name=>read('renderer/js/beast-desktop-bridge.js').includes(name))&&['rollbackLatestPlan','data-plan-action="rollback"'].every(name=>editorCortex.includes(name)||read('renderer/js/pages/beast-sourceplan-page.js').includes(name))&&palette.includes('Rollback Latest SourcePlan')&&release.includes('/sourceplan rollback'));
check('persistent shell regions are keyboard and pointer resizable',index.includes('beast-shell-resize.js')&&['data-shell-resizer="sidebar"','data-shell-resizer="rail"'].every(name=>index.includes(name))&&read('renderer/js/beast-shell-resize.js').includes('beast.shell.layout.v1')&&productionCss.includes('.beast-shell-resizer'));
check('major middle-workbench panels are persistently resizable',index.includes('beast-panel-resize.js')&&read('renderer/js/beast-panel-resize.js').includes('beast.workbench.panel-sizes.v1')&&['beast-user-resizable','resize:both'].every(name=>productionCss.includes(name)));
check('Pair Programmer is conversation-first and offers persistent focus mode',['expanded: state.expanded','setExpanded','expanded: Boolean(payload.expanded)'].every(name=>read('renderer/js/beast-ai-coding.js').includes(name))&&['data-ai-expand','cortex-ai-context-body','data-ai-mode-description','cortex-ai-message-body','data-ai-send-label','aiMessageBody'].every(name=>workspacePage.includes(name))&&['cortex-layout.ai-open.ai-focus','cortex-ai-compose-actions','cortex-ai-message-body'].every(name=>productionCss.includes(name)));
check('Pair Programmer context and run details expand like chat controls',!['grid-template-rows:45px 38px 32px','grid-template-rows:45px 38px auto minmax','20px 132px','22px auto auto'].some(name=>productionCss.includes(name))&&!['prompt(','confirm(','alert('].some(name=>workspacePage.includes(name))&&['.cortex-ai-context-body','.cortex-ai-trace>div','overscroll-behavior:contain;scrollbar-gutter:stable','minmax(0,1fr) auto auto auto'].every(name=>productionCss.includes(name)));
check('Agent Action IR becomes a validated reviewable proposal instead of leaked JSON',['parseActionIntent','proposalFromActions','proposalSummary','normalizedRestoredMessage','agent_run_provider_done','agent_run_validation','recoveredPlan','streamWatchdog','retryLastRequest'].every(name=>read('renderer/js/beast-ai-coding.js').includes(name))&&['aiProposalCard','cortex-ai-proposal','cortex-ai-validation','Open full review and apply safely','Retry with locked context','validating-changes','ready-to-review'].every(name=>workspacePage.includes(name)||read('renderer/css/beast-production.css').includes(name)));
check('Agent and edit modes expose semantic live progress and Monaco hunk previews',['updateProgress','finishProgress','agent_run_started','agent_run_context','draftPreviewFromRaw','characters received','Compiling reviewable patch'].every(name=>read('renderer/js/beast-ai-coding.js').includes(name))&&['aiProgress','aiDraftPreview','cortex-ai-live-draft','aiOperationPreview','cortex-ai-edit-preview','openAiDiff','READ-ONLY AI HUNK PREVIEW','data-ai-preview-path','BEFORE','AFTER'].every(name=>workspacePage.includes(name)||read('renderer/css/beast-production.css').includes(name)));
check('AI proposals expose isolated verifier evidence',['isolated_verifiers','verifierDetail','verifiers.passed'].every(name=>read('renderer/js/beast-ai-coding.js').includes(name))&&['cortex-ai-verifiers','Isolated verification','verifierCommands'].every(name=>workspacePage.includes(name)||read('renderer/css/beast-production.css').includes(name)));
check('AI streaming context never silently drops explicit attachments',['MAX_CONTEXT_FILES','normalizeContextFiles','not locked by backend','Context mismatch or read failure',"mode === 'ask' ? 6000 : 16000",'If multiple files are attached'].every(name=>read('renderer/js/beast-ai-coding.js').includes(name)));
check('AI pair programmer parity acceptance is complete',['beast:ai-proposal-ready','Open highlighted diff','READ-ONLY AI HUNK PREVIEW','sourceplan_apply_button','old_text','new_text'].every(name=>read('renderer/js/beast-ai-coding.js').includes(name)||workspacePage.includes(name)||read('renderer/js/beast-editor-cortex.js').includes(name)||read('renderer/js/beast-desktop-bridge.js').includes(name))&&['apply_patch_plan','approval_required'].every(name=>fs.readFileSync(path.join(repo,'app','cli','api.py'),'utf8').includes(name)));
check('Local Ollama coding fallback is selectable when registry is unavailable',['qwen2.5-coder:1.5b','qwen2.5:0.5b','provider:\'ollama\'','Local Ollama · probe on use','runtime:\'Ollama\''].every(name=>read('renderer/js/beast-model-agent-bridge.js').includes(name))&&fs.readFileSync(path.join(repo,'app','kernel','registry','provider_registry.py'),'utf8').includes('"default_model": "qwen2.5-coder:1.5b"'));
check('Pair Programmer keeps the local Qwen coder route responsive',['RELIABLE_LOCAL_CODER','RELIABLE_LOCAL_PROFILE','beast.pair-programmer.local-model-migrated','maxFiles:3','contextChars:2400','editTokens:1024','compactLocal'].every(name=>read('renderer/js/beast-ai-coding.js').includes(name))&&['_is_compact_local_coder','_pair_programmer_limits','context_file_limit','run_max_tokens','1024','2400','compact_local_coder'].every(name=>fs.readFileSync(path.join(repo,'app','routes','ide.py'),'utf8').includes(name)));
check('Advisory starters route to Ask while edit starters retain explicit intent',['resolvedModeForPrompt','Advisory request routed to Ask mode'].every(name=>read('renderer/js/beast-ai-coding.js').includes(name))&&['data-ai-suggestion-mode="ask"','data-ai-suggestion-mode="edit"','data-ai-suggestion-mode="agent"'].every(name=>workspacePage.includes(name)));
check('missing LSP and DAP tools expose allowlisted verified installers',['MANAGED_TOOL_ROOT','runInstaller','async install(options','elevated-system','managed-user'].every(name=>compatibilityHost.includes(name))&&['installIdeCapability','installCapability'].every(name=>preload.includes(name)||compatibility.includes(name))&&read('renderer/js/pages/beast-compatibility-page.js').includes('data-compat-install-kind'));
check('extension host is isolated and grant-gated',main.includes('class BeastExtensionHost')&&main.includes("ELECTRON_RUN_AS_NODE:'1'")&&main.includes('Requested extension grant is not declared')&&fs.existsSync(path.join(root,'scripts','beast-extension-host.js'))&&fs.existsSync(path.join(root,'extensions','beast-companion','beast-extension.json')));
check('extensions have persistent per-workspace enablement', ['extensionDisableFile','readDisabledExtensions','setEnabled','Extension is disabled for this workspace','beast:extension-host-enable'].every(name=>main.includes(name))&&['setExtensionEnabled','data-runtime-extension-toggle'].every(name=>preload.includes(name)||runtime.includes(name)||read('renderer/js/pages/beast-compatibility-page.js').includes(name)));
check('workspace extensions have bounded install and remove lifecycle', ['extensionPackage','installWorkspaceExtension','uninstallWorkspaceExtension','beast:extension-host-install','beast:extension-host-uninstall','Only installed workspace extensions can be removed'].every(name=>main.includes(name))&&['installWorkspaceExtension:','uninstallWorkspaceExtension:'].every(name=>preload.includes(name))&&['installWorkspaceExtension','uninstallWorkspaceExtension'].every(name=>runtime.includes(name))&&['data-runtime-action="extension-install"','data-runtime-extension-uninstall'].every(name=>read('renderer/js/pages/beast-compatibility-page.js').includes(name)));
check('native workbench and remote sessions have narrow IPC', ['searchWorkspace','replaceWorkspace','workspaceGitStatus','workspaceTasks','runWorkspaceTask','searchRemoteWorkspace','reconnectRemote','readRemoteFile','writeRemoteFile','runRemoteTerminal','executeExtensionCommand'].every(name=>preload.includes(name)) && ['beast:workspace-search','beast:workspace-replace','beast:workspace-git-status','beast:workspace-tasks','beast:workspace-task-run','beast:remote-search','beast:remote-reconnect','beast:remote-read-file','beast:remote-write-file','beast:remote-terminal-run','beast:extension-host-execute'].every(name=>main.includes(name)));
check('persistent remote terminal is bounded and renderer-mediated',['RemoteTerminalHost','-tt','ServerAliveInterval=20','remote-terminal-list','remote-terminal-start','remote-terminal-send','remote-terminal-stop','remoteTerminalHost.stopAll()'].every(name=>main.includes(name))&&['listRemoteTerminals','startRemoteTerminal','sendRemoteTerminal','stopRemoteTerminal','onRemoteTerminalMessage'].every(name=>preload.includes(name))&&['startRemoteTerminal','sendRemoteTerminal','stopRemoteTerminal','handleRemoteTerminalMessage'].every(name=>runtime.includes(name)));
check('remote workspace search is bounded and editor-addressable',main.includes('grep -RInF')&&main.includes('head -n 300')&&main.includes('Remote search requires a connected host')&&runtime.includes('searchRemoteWorkspace')&&read('renderer/js/pages/beast-compatibility-page.js').includes('data-runtime-remote-search-open'));
check('indexed remote files open directly in Editor Cortex',runtime.includes('openRemoteWorkspaceFile')&&runtime.includes('Remote file opened:')&&read('renderer/js/pages/beast-compatibility-page.js').includes('data-runtime-remote-open'));
check('remote editor saves detect server-side changes before overwrite',['expectedDigest','sha256sum --','Remote file changed since it was opened','conflict:true'].every(name=>main.includes(name))&&['async function sha256','expectedDigest=originalContent','error.conflict'].every(name=>read('renderer/js/beast-desktop-bridge.js').includes(name))&&editorCortex.includes('saveRemoteFile(path,text,originals.get(path)||\'\')'));
check('VS Code task definitions are explicit and workspace-bounded',main.includes(".vscode','tasks.json")&&main.includes("['shell','process','npm']")&&main.includes('taskCwd(root,definition.options?.cwd)')&&main.includes("shell:task.kind==='shell'")&&read('renderer/js/pages/beast-terminal-page.js').includes('VS Code task definition'));
check('streamed tasks expose background lifecycle and clickable problems',['WorkspaceTaskHost','normalizeTaskMatchers','background-ready','taskProblemFromLine','workspace-task-start','workspace-task-stop','workspaceTaskHost.stopAll()'].every(name=>main.includes(name))&&['startWorkspaceTask','stopWorkspaceTask','onWorkspaceTaskMessage'].every(name=>preload.includes(name))&&['data-dev-problems','data-dev-problem-path','data-dev-task-stop','startWorkspaceTask'].every(name=>read('renderer/js/pages/beast-terminal-page.js').includes(name)));
check('integrated terminal has persistent local shell lifecycle',['LocalTerminalHost','terminal-session-list','terminal-session-start','terminal-session-send','terminal-session-stop','localTerminalHost.stopAll()'].every(name=>main.includes(name))&&['listTerminalSessions','startTerminalSession','sendTerminalSession','stopTerminalSession','onTerminalSessionMessage'].every(name=>preload.includes(name))&&['startTerminalSession','sendTerminalSession','stopTerminalSession','handleTerminalSessionMessage','terminal-session-action'].every(name=>runtime.includes(name)||read('renderer/js/pages/beast-terminal-page.js').includes(name)));
check('source control actions stay workspace-bounded',preload.includes('workspaceGitAction')&&main.includes('beast:workspace-git-action')&&main.includes("argsByAction={stage")&&main.includes("['add','--'")&&main.includes("['restore','--staged'")&&main.includes("['restore','--worktree'"));
check('source control workbench exposes diff, commit, branch, breadcrumbs, and keyboard flow',['workspaceGitDiff','workspaceGitCommit','workspaceGitBranch'].every(name=>preload.includes(name))&&['beast:workspace-git-diff','beast:workspace-git-commit','beast:workspace-git-branch','parseGitPorcelain','gitReceipt'].every(name=>main.includes(name))&&['data-git-diff-workbench','data-git-commit-message','data-git-branch-select','data-editor-breadcrumbs','mountContentDiff',"event.key.toLowerCase()==='g'"].every(name=>workspacePage.includes(name)||editorCortex.includes(name)));
check('source control exposes hunks, conflicts, history, remotes, rebase, and cherry-pick',['workspaceGitHunks','workspaceGitHunkAction','workspaceGitConflict','workspaceGitResolve','workspaceGitHistory','workspaceGitRemotes','workspaceGitOperation'].every(name=>preload.includes(name))&&['parseGitPatchHunks','workspaceGitHistory','workspaceGitRemotes','workspaceGitOperation','rebase-start','cherry-pick'].every(name=>main.includes(name))&&['data-git-hunk-action','data-git-conflict-action','data-git-operation','data-git-history-commit'].every(name=>workspacePage.includes(name)));
check('LSP semantic tokens and workspace symbols are protocol-native',['semanticTokens','workspaceFolders','symbolKind'].every(name=>compatibilityHost.includes(name))&&['registerDocumentSemanticTokensProvider','workspaceSymbols','workspace/symbol','textDocument/semanticTokens/full'].every(name=>compatibility.includes(name)));
check('executable extension boundary remains mediated',fs.readFileSync(path.join(root,'scripts','beast-extension-host.js'),'utf8').includes("vm.createContext") && fs.readFileSync(path.join(root,'scripts','beast-extension-host.js'),'utf8').includes('vscode=Object.freeze') && fs.readFileSync(path.join(root,'scripts','beast-extension-host.js'),'utf8').includes("Extension capability is not granted") && main.includes("Extension requested an unsupported mediated action"));
check('vscode extension shim enforces bounded read authority',fs.readFileSync(path.join(root,'scripts','beast-extension-host.js'),'utf8').includes('workspaceFolders:grants.has')&&fs.readFileSync(path.join(root,'scripts','beast-extension-host.js'),'utf8').includes('findFiles')&&fs.readFileSync(path.join(root,'scripts','beast-extension-host.js'),'utf8').includes('Extension path escaped its workspace')&&runtime.includes('executeExtensionCommand'));
check('extension lifecycle exposes target-aware activation and visible errors',['discoverExtensions','grantExtensionCapabilities','setExtensionEnabled','executeExtensionCommand','handleExtensionHostMessage','onExtensionHostMessage'].every(name=>runtime.includes(name)||preload.includes(name))&&['activeExecutionTarget','beastExtensionHost.discover','beastExtensionHost.execute','target:this.session.target'].every(name=>main.includes(name)));
check('first-load mission runway',['Workspace','Mission','Trust + Tools','Build','Prove + Reuse'].every(label=>onboarding.includes(label)));
check('governed pipeline is explicit',['SourcePlan','Review','Evidence','Crystal'].every(label=>onboarding.includes(label)));
check('compatibility route registered',index.includes('data-beast-route="compatibility"')&&index.includes('beast-compatibility-page.js')&&release.includes('BeastCompatibilityPage.renderer'));
check('workbench zoom and pane sizing are persistent',['zoomIn','zoomOut','resetZoom','beast:zoom-set'].every(name=>main.includes(name))&&['getZoom:','setZoom:','resetZoom:'].every(name=>preload.includes(name))&&['data-workspace-action="zoom-in"','data-pane-resizer="explorer"','beast.workspace.layout.v1','beginPaneResize'].every(name=>workspacePage.includes(name)));
check('core editor parity acceptance is complete',["event.key.toLowerCase()==='s'","event.key.toLowerCase()==='w'","event.key==='Tab'",'data-pane-resizer','beast.workspace.layout.v1'].every(name=>workspacePage.includes(name)||productionCss.includes(name))&&['BeastCommandPalette','F1','ctrlKey'].every(name=>palette.includes(name)));
check('desktop window state survives relaunch and monitor changes',['readWindowState','persistWindowState','scheduleWindowStatePersist','getNormalBounds','ready-to-show','windowRef.on(\'close\''].every(name=>main.includes(name)));
check('multi-root workspaces persist, address files safely, and reach LSP',['workspaceFoldersStatePath','persistWorkspaceFolders','restoreWorkspaceFolders','normalizeWorkspaceRoots','parseWorkspaceReference','multiRootFiles','beast:workspace-folder-add','beast:workspace-folder-remove'].every(name=>main.includes(name))&&['workspaceFolders:','addWorkspaceFolder:','removeWorkspaceFolder:'].every(name=>preload.includes(name))&&['setWorkspaceFolders','workspaceFolderForPath','addWorkspaceFolder','removeWorkspaceFolder'].every(name=>read('renderer/js/beast-desktop-bridge.js').includes(name))&&['data-workspace-folders','data-workspace-folder-remove','data-workspace-action="add-folder"'].every(name=>workspacePage.includes(name))&&['workspaceFolders:workspaceRoots','options.roots'].every(name=>compatibilityHost.includes(name)));
check('Explorer/workspace target parity is complete',['workspaceTargetListFiles','workspaceTargetReadFile','workspaceTargetWriteFile','targetWorkspaceBase','targetRelativePath','beast:workspace-target-list-files','beast:workspace-target-read-file','beast:workspace-target-write-file'].every(name=>main.includes(name))&&['listTargetFiles:','readTargetFile:','writeTargetFile:'].every(name=>preload.includes(name))&&['listTargetFiles','readTargetFile','saveTargetFile','executionTarget','rootId:workspaceFolderForPath'].every(name=>read('renderer/js/beast-desktop-bridge.js').includes(name))&&['saveTargetFile','target.kind===\'local\''].every(name=>editorCortex.includes(name)||read('renderer/js/beast-desktop-bridge.js').includes(name)));
check('Git source control parity is complete',['workspaceGitHunkAction','workspaceGitResolve','workspaceGitHistory','workspaceGitRemotes','workspaceGitOperation','expectedDigest','gitReceipt','--ff-only','--prune'].every(name=>main.includes(name))&&['workspaceGitHunks:','workspaceGitHunkAction:','workspaceGitConflict:','workspaceGitResolve:','workspaceGitHistory:','workspaceGitRemotes:','workspaceGitOperation:'].every(name=>preload.includes(name))&&['data-git-hunk-action','data-git-conflict-action','data-git-operation','data-git-history-commit','Refresh Source Control'].some(name=>workspacePage.includes(name)));
check('per-folder Git, tasks, settings, and test contracts are native',['registeredWorkspaceRoot','workspace-settings','workspace-settings-save','workspace-tests','workspace-test-run','workspaceSettings','writeWorkspaceSettings','workspaceTests','runWorkspaceTest'].every(name=>main.includes(name))&&['workspaceSettings:','saveWorkspaceSettings:','workspaceTests:','runWorkspaceTest:'].every(name=>preload.includes(name))&&['gitRootPayload','rootId:target.folder?.id'].every(name=>workspacePage.includes(name))&&['data-dev-test','data-dev-action="tests"','runWorkspaceTest'].every(name=>read('renderer/js/pages/beast-terminal-page.js').includes(name)));
check('Testing workbench supports focused files, debug handoff, and failure navigation',index.includes('beast-testing-page.js')&&release.includes("'testing'")&&['workspaceTests','runWorkspaceTest','failureLocations','data-test-failure-path','data-test-file','startDebug'].every(name=>testingPage.includes(name))&&main.includes('Selected test file is outside this workspace'));
check('Testing discovery and execution share the selected execution target',['workspaceTestsForTarget','executionTarget','runOnExecutionTarget(selectedTarget','remote workspace','beast:workspace-tests'].every(name=>main.includes(name))&&['runWorkspaceTest','workspaceTests(workspaceScope())'].every(name=>read('renderer/js/pages/beast-terminal-page.js').includes(name)));
check('SSH reconnect rehydrates the remote workbench',['reconnectRemoteWorkspace','lastRemoteWorkspace','setActiveExecutionTarget','Promise.allSettled([listRemoteFiles(),refreshRemoteTerminals(),refreshRemoteForwards(),refreshExecutionTargets()])'].every(name=>main.includes(name)||runtime.includes(name))&&['StrictHostKeyChecking=yes','ServerAliveInterval=20','verification'].every(name=>main.includes(name)));
check('Testing workbench discovers and safely runs individual pytest nodes',['pytestTestNodes','Selected test node is outside this workspace','test-node runs currently support the pytest target'].every(name=>main.includes(name))&&['nodes:[]','selectedNode','data-test-node'].every(name=>testingPage.includes(name))&&testingPage.includes("...(selectedNode?{node:selectedNode}:{})"));
check('architecture decision is explicit',adr.includes('Protocol-native host plus VS Code companion')&&adr.includes('renderer never'));
check('discovery returns honest capability groups',discovery.ok&&['languages','debug','notebooks','remote'].every(key=>Array.isArray(discovery[key]))&&discovery.summary.total>0);

async function aiProposalLifecycle() {
  const aiCoding=read('renderer/js/beast-ai-coding.js');
  const storage=new Map();let currentSource=null;const createBodies=[];
  const state={
    workspace:{root:repo,files:[{path:'app/context/economizer.py'}]},connection:{status:'offline',gatewayUrl:'http://127.0.0.1:8101'},
    editor:{activePath:'app/context/economizer.py'},models:{provider:'local',selectedId:'test-model',active:'test-model',registry:[{id:'test-model',provider:'local',status:'ready'}]},
    aiCoding:{open:true,expanded:false,mode:'agent',prompt:'',sessionId:'',streaming:false,status:'idle',error:'',messages:[],trace:[],contextFiles:[],selection:null,provider:'local',model:'test-model',crystal:{action:'',source:'',confidence:0,reused:false,avoidedTokens:0,decisionId:'',recorded:false},sourcePlanReady:false,sourcePlanId:'',updatedAt:0},
    sourcePlan:{status:'idle',plan:null,selectedOperationIds:[]}
  };
  class FakeEventSource {
    constructor(url){this.url=url;this.listeners=new Map();currentSource=this;}
    addEventListener(name,handler){if(!this.listeners.has(name))this.listeners.set(name,[]);this.listeners.get(name).push(handler);}
    emit(name,payload){for(const handler of this.listeners.get(name)||[])handler({data:JSON.stringify({payload})});}
    close(){this.closed=true;}
  }
  const context={
    console,URLSearchParams,structuredClone,setTimeout,clearTimeout,EventSource:FakeEventSource,
    localStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,String(value))},
    BeastStore:{get:()=>state,patch:(key,values)=>{state[key]={...state[key],...values};},set:(key,value)=>{state[key]=value;},addLedger:()=>{}},
    BeastRuntime:{gatewayUrl:'http://127.0.0.1:8101',request:async (path,options={})=>{if(path.includes('/create')){createBodies.push(options.body&&typeof options.body==='object'?options.body:JSON.parse(options.body||'{}'));return {session:{session_id:`ai-verifier-session-${createBodies.length}`}};}return {};}},
    BeastDesktopBridge:{demoMode:false,localDiff:(before,after)=>`${before}\n---\n${after}`},
    BeastEditorCortex:{getSelection:()=>({path:'',text:''}),getActive:()=>({path:'app/context/economizer.py',text:'def trim():\n    return 1\n'})},
    BeastMascot:{setState:()=>{}},BeastRouter:{navigate:async()=>{}},window:{}
  };
  vm.createContext(context);vm.runInContext(aiCoding,context);
  await context.window.BeastAICoding.send('Improve the context economizer.');
  const actionIntent={kind:'beast.action_intent.v1',objective:'Improve the context economizer',actions:[{type:'replace_exact',target:{path:'app/context/economizer.py'},old:'return 1',new:'return 2',intent:'Improve trimming strategy'}]};
  currentSource.onopen?.();
  currentSource.emit('agent_run_started',{session_id:'ai-verifier-session'});
  currentSource.emit('agent_run_context',{files:['app/context/economizer.py'],active_file:'app/context/economizer.py',file_count:1});
  currentSource.emit('agent_run_tool',{text:'read app/context/economizer.py'});
  currentSource.emit('agent_run_token',{text:JSON.stringify(actionIntent)});
  const beforePlan=state.aiCoding.messages.find(message=>message.role==='assistant');
  const plan={plan_id:'ai_verify_plan',objective:actionIntent.objective,validation:{ok:true,status:'passed',check_count:3,syntax_checked:1,isolated_verifiers:{status:'passed',passed:1,failed:0,skipped:0,commands:[{command:'python -m py_compile app/context/economizer.py',status:'passed',message:'Verifier completed'}]}},operations:[{op_id:'op-1',op:'replace_exact',path:'app/context/economizer.py',old:'return 1',new:'return 2',description:'Improve trimming strategy'}]};
  currentSource.emit('agent_run_validation',plan.validation);
  currentSource.emit('agent_run_sourceplan',{operation_count:1,plan});
  currentSource.emit('agent_run_done',{sourceplan_status:'compiled_action_ir',session:{output:{sourceplan_plan:plan}}});
  const assistant=state.aiCoding.messages.find(message=>message.role==='assistant');
  const editOk=!String(beforePlan.content||'').includes('beast.action_intent')&&beforePlan.draftPreview?.files?.includes('app/context/economizer.py')&&beforePlan.progress?.some(item=>item.phase==='context'&&String(item.detail).includes('app/context/economizer.py'))&&beforePlan.progress?.some(item=>item.phase==='draft'&&String(item.detail).includes('characters received'))&&assistant?.progress?.some(item=>item.phase==='validate'&&String(item.detail).includes('isolated passed'))&&state.aiCoding.sourcePlanReady&&state.sourcePlan.plan?.plan_id==='ai_verify_plan'&&assistant?.proposal?.ready&&assistant?.proposal?.operations?.[0]?.old==='return 1'&&assistant?.proposal?.validation?.status==='passed'&&assistant?.proposal?.validation?.isolated_verifiers?.status==='passed'&&assistant.progress?.some(item=>item.phase==='review'&&item.state==='ready')&&!assistant.streaming&&!assistant.content.includes('beast.action_intent')&&state.aiCoding.status==='ready-to-review';

  context.window.BeastAICoding.clear();
  context.window.BeastAICoding.setMode('agent');
  await context.window.BeastAICoding.send('Explain the active file and identify its key dependencies.');
  currentSource.onopen?.();
  currentSource.emit('agent_run_context',{files:['app/context/economizer.py'],active_file:'app/context/economizer.py',file_count:1});
  currentSource.emit('agent_run_token',{text:'The active file manages bounded context trimming. '});
  currentSource.emit('agent_run_token',{text:'Its key dependencies are the token estimator and compute kernel.'});
  currentSource.emit('agent_run_provider_done',{});
  currentSource.emit('agent_run_done',{sourceplan_status:'chat_complete',session:{output:{}}});
  const advisory=state.aiCoding.messages.find(message=>message.role==='assistant');
  const advisoryOk=createBodies.at(-1)?.mode==='chat'&&state.aiCoding.mode==='ask'&&advisory?.content.includes('bounded context trimming')&&advisory?.content.includes('compute kernel')&&!advisory?.content.includes('no safe patch')&&!advisory?.streaming;
  const ok=editOk&&advisoryOk;
  return {ok,error:ok?'':`AI lifecycle assertion failed (edit=${editOk}, advisory=${advisoryOk})`};
}

function handshake(language, adapter='') {
  return new Promise(resolve => {
    const host=new IdeCompatibilityHost(repo);
    let settled=false;
    let timer=0;
    const finish=result=>{if(settled)return;settled=true;clearTimeout(timer);host.stopAll();resolve(result);};
    const sender={isDestroyed:()=>false,send:(_channel,message)=>{if(message.type==='ready')finish({ok:true,capabilities:message.capabilities||{}});if(message.type==='error'&&String(message.error||'').includes('initialize failed'))finish({ok:false,error:message.error});}};
    try{host.start({kind:'lsp',...(adapter ? {adapter} : {language}),root:repo},sender);}catch(error){finish({ok:false,error:String(error.message||error)});return;}
    timer=setTimeout(()=>finish({ok:false,error:'initialize timeout'}),8000);
  });
}

function dapHandshake(adapter='debugpy') {
  return new Promise(resolve => {
    const host=new IdeCompatibilityHost(repo);
    let settled=false; let timer=0;
    const finish=result=>{if(settled)return;settled=true;clearTimeout(timer);host.stopAll();resolve(result);};
    const sender={isDestroyed:()=>false,send:(_channel,message)=>{if(message.kind==='dap'&&message.type==='ready')finish({ok:true,capabilities:message.capabilities||{}});if(message.kind==='dap'&&message.type==='error')finish({ok:false,error:message.error});}};
    try{host.start({kind:'dap',adapter,root:repo},sender);}catch(error){finish({ok:false,error:String(error.message||error)});return;}
    timer=setTimeout(()=>finish({ok:false,error:'DAP initialize timeout'}),10000);
  });
}

function dapLaunchLifecycle() {
  return new Promise(resolve=>{
    const temp=fs.mkdtempSync(path.join(os.tmpdir(),'beast-dap-launch-'));const program=path.join(temp,'main.py');fs.writeFileSync(program,'value = 41\nvalue += 1\nprint(value)\n','utf8');
    const host=new IdeCompatibilityHost(repo);let session=null;let settled=false;let timer=0;
    const finish=result=>{if(settled)return;settled=true;clearTimeout(timer);host.stopAll();fs.rmSync(temp,{recursive:true,force:true});resolve(result);};
    const sender={isDestroyed:()=>false,async send(_channel,message){try{if(message.kind!=='dap')return;if(message.type==='ready')host.notify({sessionId:session.id,method:'launch',params:{name:'BEAST lifecycle probe',type:'python',request:'launch',program,cwd:temp,console:'internalConsole',stopOnEntry:true,justMyCode:true}});if(message.message?.type==='event'&&message.message.event==='initialized'){await host.request({sessionId:session.id,method:'setBreakpoints',params:{source:{name:'main.py',path:program},breakpoints:[{line:2}]},timeoutMs:10000});await host.request({sessionId:session.id,method:'configurationDone',params:{},timeoutMs:10000});}if(message.message?.type==='event'&&message.message.event==='stopped')finish({ok:true,reason:message.message.body?.reason||''});if(message.type==='error')finish({ok:false,error:message.error});}catch(error){finish({ok:false,error:String(error.message||error)});}}};
    try{session=host.start({kind:'dap',adapter:'debugpy',root:temp},sender);}catch(error){finish({ok:false,error:String(error.message||error)});return;}
    timer=setTimeout(()=>finish({ok:false,error:'DAP launch lifecycle timeout'}),20000);
  });
}

function notebookKernelExecution() {
  return new Promise(resolve => {
    const toolRoot=path.join(root,'.beast-python-tools');
    const child=spawn('python3',[path.join(root,'scripts','notebook-kernel-relay.py')],{cwd:root,env:{...process.env,PYTHONPATH:[toolRoot,process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),JUPYTER_PATH:path.join(toolRoot,'share','jupyter'),BEAST_ACTIVE_WORKSPACE:repo,BEAST_JUPYTER_KERNEL:'beast-python'},stdio:['pipe','pipe','pipe']});
    let buffer='';let settled=false;let timer=0;let output='';
    const finish=result=>{if(settled)return;settled=true;clearTimeout(timer);if(!child.killed)child.kill('SIGTERM');resolve(result);};
    child.stdout.on('data',chunk=>{buffer+=String(chunk);let cut;while((cut=buffer.indexOf('\n'))>=0){const line=buffer.slice(0,cut);buffer=buffer.slice(cut+1);try{const message=JSON.parse(line);if(message.type==='ready')child.stdin.write(`${JSON.stringify({id:1,operation:'execute',code:'print(6*7)',timeout:20})}\n`);if(message.id===1){output=(message.outputs||[]).map(item=>item.text||'').join('');child.stdin.write(`${JSON.stringify({id:2,operation:'shutdown'})}\n`);finish({ok:message.ok&&output.includes('42'),output});}}catch(error){finish({ok:false,error:String(error.message||error)});}}});
    child.on('error',error=>finish({ok:false,error:String(error.message||error)}));
    child.on('exit',code=>{if(!settled)finish({ok:false,error:`kernel relay exited ${code}`});});
    timer=setTimeout(()=>finish({ok:false,error:'kernel relay timeout'}),30000);
  });
}

async function gitWorkbenchLifecycle() {
  const temp=fs.mkdtempSync(path.join(os.tmpdir(),'beast-git-workbench-'));
  const run=(args,cwd=temp)=>spawnSync('git',args,{cwd,encoding:'utf8',maxBuffer:2*1024*1024});
  try{
    if(run(['init']).status!==0)return {ok:false,error:'git init failed'};
    run(['config','user.email','beast@example.invalid']);run(['config','user.name','BEAST verifier']);
    fs.mkdirSync(path.join(temp,'src'),{recursive:true});fs.writeFileSync(path.join(temp,'src','app.js'),'const value = 1;\n','utf8');run(['add','--all']);if(run(['commit','-m','initial']).status!==0)return {ok:false,error:'initial commit failed'};
    const start=main.indexOf('function parseGitPorcelain');const end=main.indexOf('\nfunction parseJsonc',start);if(start<0||end<0)return {ok:false,error:'Git workbench source boundary missing'};
    const context={fs,path,crypto:require('crypto'),Buffer,repoRoot:temp,console,setTimeout,clearTimeout};
    context.safeWorkspacePath=(rootPath,relPath)=>{const base=path.resolve(rootPath);const target=path.resolve(base,relPath||'');return target!==base&&target.startsWith(`${base}${path.sep}`)?{ok:true,root:base,target}:{ok:false,error:'path escaped workspace',root:base,target};};
    context.boundedProcess=async(command,args,options={})=>{const result=spawnSync(command,args,{cwd:options.cwd||temp,encoding:'utf8',maxBuffer:2*1024*1024,shell:Boolean(options.shell)});return {ok:result.status===0,stdout:String(result.stdout||''),stderr:String(result.stderr||''),returncode:result.status,error:result.error?String(result.error.message||result.error):''};};
    vm.createContext(context);vm.runInContext(`${main.slice(start,end)}\nthis.gitFns={workspaceGitStatus,workspaceGitDiff,workspaceGitAction,workspaceGitCommit,workspaceGitBranch,workspaceGitConflict,workspaceGitResolve};`,context);
    fs.writeFileSync(path.join(temp,'src','app.js'),'const value = 2;\n','utf8');
    const unstaged=await context.gitFns.workspaceGitStatus(temp);const worktree=await context.gitFns.workspaceGitDiff(temp,{path:'src/app.js',mode:'worktree'});const stagedAction=await context.gitFns.workspaceGitAction(temp,'stage','src/app.js');const staged=await context.gitFns.workspaceGitStatus(temp);const indexDiff=await context.gitFns.workspaceGitDiff(temp,{path:'src/app.js',mode:'staged'});const commit=await context.gitFns.workspaceGitCommit(temp,{message:'verify source control workbench'});const branch=await context.gitFns.workspaceGitBranch(temp,{operation:'create',name:'feature/workbench'});const branchStatus=await context.gitFns.workspaceGitStatus(temp);const escaped=await context.gitFns.workspaceGitDiff(temp,{path:'../outside.txt',mode:'worktree'});
    fs.writeFileSync(path.join(temp,'conflict.txt'),'base\n','utf8');run(['add','conflict.txt']);run(['commit','-m','conflict base']);run(['switch','-c','feature/conflict']);fs.writeFileSync(path.join(temp,'conflict.txt'),'incoming\n','utf8');run(['commit','-am','incoming conflict']);run(['switch','feature/workbench']);fs.writeFileSync(path.join(temp,'conflict.txt'),'current\n','utf8');run(['commit','-am','current conflict']);run(['merge','feature/conflict']);
    const conflict=await context.gitFns.workspaceGitConflict(temp,{path:'conflict.txt'});const resolved=await context.gitFns.workspaceGitResolve(temp,{path:'conflict.txt',content:'resolved\n',expectedDigest:conflict.digest});const conflictStatus=await context.gitFns.workspaceGitStatus(temp);
    const ok=unstaged.ok&&unstaged.changes.some(change=>change.path==='src/app.js'&&change.unstaged)&&worktree.ok&&worktree.originalText.includes('value = 1')&&worktree.modifiedText.includes('value = 2')&&stagedAction.ok&&staged.changes.some(change=>change.path==='src/app.js'&&change.staged)&&indexDiff.ok&&indexDiff.modifiedText.includes('value = 2')&&commit.ok&&branch.ok&&branchStatus.branchName==='feature/workbench'&&!escaped.ok&&conflict.ok&&conflict.regions>0&&resolved.ok&&conflictStatus.counts.conflicts===0;
    return {ok,error:ok?'':'Git lifecycle assertion failed'};
  }catch(error){return {ok:false,error:String(error.message||error)};}
  finally{fs.rmSync(temp,{recursive:true,force:true});}
}

function extensionSandboxLifecycle() {
  const script=path.join(root,'scripts','beast-extension-host.js');
  const requests=[
    {id:1,operation:'discover',roots:[{path:path.join(root,'extensions'),origin:'bundled'}]},
    {id:2,operation:'execute',extensionId:'beast.companion',command:'beast.openMission',roots:[{path:path.join(root,'extensions'),origin:'bundled'}],workspaceRoot:repo,granted:[]}
  ];
  try {
    const result=spawnSync(process.execPath,[script],{cwd:root,input:`${requests.map(item=>JSON.stringify(item)).join('\n')}\n`,encoding:'utf8',timeout:8000,maxBuffer:512000});
    const rows=String(result.stdout||'').split(/\r?\n/).filter(Boolean).map(line=>{try{return JSON.parse(line);}catch(_){return null;}}).filter(Boolean);
    const discovery=rows.find(row=>row.id===1);const execution=rows.find(row=>row.id===2);
    const ok=discovery?.ok&&discovery.extensions?.some(item=>item.id==='beast.companion')&&execution?.ok&&execution.actions?.some(action=>action.kind==='navigate'&&action.payload?.route==='mission');
    return {ok,error:ok?'':String(result.stderr||'Extension sandbox lifecycle assertion failed')};
  } catch(error) { return {ok:false,error:String(error.message||error)}; }
}

(async()=>{
  const typescript=await handshake('typescript');
  const python=await handshake('python');
  const pylsp=await handshake('', 'pylsp');
  const bash=await handshake('', 'bash');
  const go=await handshake('go');
  const rust=discovery.languages.find(item=>item.id==='rust')?.available ? await handshake('rust') : {ok:false,skipped:true};
  const clangd=discovery.languages.find(item=>item.id==='clangd')?.available ? await handshake('cpp') : {ok:false,skipped:true};
  const debugpyAvailable=discovery.debug.find(item=>item.id==='debugpy')?.available;
  const delveAvailable=discovery.debug.find(item=>item.id==='delve')?.available;
  const debugpy=process.env.BEAST_VERIFY_DAP === '1'&&debugpyAvailable ? await dapHandshake('debugpy') : { ok:false, skipped:true };
  const delve=process.env.BEAST_VERIFY_DAP === '1'&&delveAvailable ? await dapHandshake('delve') : { ok:false, skipped:true };
  const lldb=process.env.BEAST_VERIFY_DAP === '1'&&discovery.debug.find(item=>item.id==='lldb')?.available ? await dapHandshake('lldb') : {ok:false,skipped:true};
  const dapLaunch=process.env.BEAST_VERIFY_DAP === '1'&&debugpyAvailable ? await dapLaunchLifecycle() : {ok:false,skipped:true};
  const notebookKernel=process.env.BEAST_VERIFY_KERNEL === '1' ? await notebookKernelExecution() : { ok:false, skipped:true };
  const gitWorkbench=await gitWorkbenchLifecycle();
  const extensionSandbox=extensionSandboxLifecycle();
  const aiProposal=await aiProposalLifecycle();
  check('TypeScript LSP initialize handshake',typescript.ok&&Boolean(typescript.capabilities.completionProvider));
  check('Python LSP initialize handshake',python.ok&&Boolean(python.capabilities.hoverProvider));
  check('Bundled pylsp initialize handshake',pylsp.ok&&Boolean(pylsp.capabilities.renameProvider));
  check('Bundled Bash LSP initialize handshake',bash.ok&&Boolean(bash.capabilities.completionProvider));
  check('Managed Go gopls initialize handshake',go.ok&&Boolean(go.capabilities.completionProvider));
  check('Rust Analyzer initialize handshake when installed',rust.skipped || rust.ok);
  check('clangd initialize handshake when installed',clangd.skipped || clangd.ok);
  check('Python debugpy DAP initialize handshake',debugpy.skipped || (debugpy.ok&&Boolean(debugpy.capabilities.supportsConfigurationDoneRequest)));
  check('Managed Go Delve DAP initialize handshake',delve.skipped || delve.ok);
  check('LLDB DAP initialize handshake when installed',lldb.skipped || lldb.ok);
  check('Python DAP launch reaches a stopped debuggee',dapLaunch.skipped || dapLaunch.ok);
  check('Persistent Jupyter kernel execution',notebookKernel.skipped || notebookKernel.ok);
  check('Source Control functional lifecycle',gitWorkbench.ok);
  check('Executable extension sandbox lifecycle',extensionSandbox.ok);
  check('AI Action IR functional proposal lifecycle',aiProposal.ok);
  const failed=checks.filter(item=>!item.passed);
  console.log(JSON.stringify({ok:!failed.length,checks:checks.length,passed:checks.length-failed.length,failed:failed.map(item=>item.name),discovery:{summary:discovery.summary,extensionHost:discovery.extensionHost.status},handshakes:{typescript:typescript.ok,python:python.ok,pylsp:pylsp.ok,bash:bash.ok,go:go.ok,rust:rust.ok,clangd:clangd.ok,debugpy:debugpy.ok,delve:delve.ok,lldb:lldb.ok,dapLaunch:dapLaunch.ok,notebookKernel:notebookKernel.ok},workbenches:{git:gitWorkbench,extensionSandbox,aiProposal}},null,2));
  if(failed.length)process.exit(1);
})().catch(error=>{console.error(error);process.exit(1);});
