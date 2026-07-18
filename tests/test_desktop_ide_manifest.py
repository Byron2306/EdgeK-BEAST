import json
from pathlib import Path


def test_desktop_ide_manifest_declares_installable_shell():
    manifest = json.loads(Path("desktop-ide/package.json").read_text(encoding="utf-8"))

    assert manifest["name"] == "beast-desktop-ide"
    assert manifest["main"] == "main.js"
    assert manifest["build"]["appId"] == "ai.edgek.beast.ide"
    assert "package:linux" in manifest["scripts"]
    assert "smoke" in manifest["scripts"]
    assert "smoke:launch" in manifest["scripts"]
    assert "smoke-desktop-ide.js" in manifest["scripts"]["smoke"]
    assert "launch-smoke-desktop-ide.js" in manifest["scripts"]["smoke:launch"]
    assert "electron" in manifest["devDependencies"]
    assert "monaco-editor" in manifest["dependencies"]
    assert "node_modules/monaco-editor/min/vs/**" in manifest["build"]["files"]
    assert "scripts/**" in manifest["build"]["files"]


def test_desktop_ide_starts_or_attaches_to_beast_gateway():
    main = Path("desktop-ide/main.js").read_text(encoding="utf-8")
    preload = Path("desktop-ide/preload.js").read_text(encoding="utf-8")

    assert "bin', 'beast'" in main
    assert "'gateway'" in main
    assert "127.0.0.1" in main
    assert "resolveRepoRoot" in main
    assert "gatewayCapabilityHealth" in main
    assert "gatewayStartupPromise" in main
    assert "gatewayTcpListening" in main
    assert "localIdeMode" in main
    assert "enterLocalIdeMode" in main
    assert "desktop_local_fallback" in main
    assert "resolveBeastPython" in main
    assert "import fastapi, uvicorn" in main
    assert "maxAutomaticAttempts" in main
    assert "gatewayHealth(baseUrl = gatewayUrl" in main
    assert "findCompatibleGateway" in main

    assert "attached to compatible BEAST gateway" in main
    assert "gatewayCapabilityHealth(baseUrl = gatewayUrl, rootPayload = null)" in main
    assert "side_effect_free_route_attestation" in main
    assert "missing_enterprise_desktop_contract" in main
    assert "/edgek/mcp/state" in main
    assert "/edgek/plugins" in main
    assert "/edgek/tools/integrations" in main
    assert "desktop_local_files" in main
    assert "port ${port} is already in use; trying next port" in main
    assert "gatewayUrl: health.url || gatewayUrl" in main
    assert "gateway process is listening" in main
    assert "failed the desktop route contract; replacing it" in main
    assert "spawnGatewayProcess" in main
    assert "waitForGatewayExit" in main
    assert "gateway start failed on port" in main
    assert "trying next port" in main
    assert "workspaceFileCandidates" in main
    assert "readWorkspaceFile" in main
    assert "beast:list-files" in main
    assert "beast:read-file" in main
    assert "beast:file-operation" in main
    assert "beast:open-workspace-window" in main
    assert "beast:release-readiness" in main
    assert "beast:tooling-snapshot" in main
    assert "beast:system-snapshot" in main
    assert "appWindows" in main
    assert "windowId" in main
    assert "BrowserWindow.getFocusedWindow" in main
    assert "localReleaseReadiness" in main
    assert "localToolingSnapshot" in main
    assert "syntaxCheckFile" in main
    assert "runDesktopScript" in main
    assert "mutateWorkspaceFile" in main
    assert "safeWorkspacePath" in main
    assert "beast:open-gateway" in main
    assert "listFiles" in preload
    assert "readFile" in preload
    assert "fileOperation" in preload
    assert "openWorkspaceWindow" in preload
    assert "releaseReadiness" in preload
    assert "toolingSnapshot" in preload
    assert "systemSnapshot" in preload
    assert "openGateway" in preload
    assert "beast:choose-workspace" in main
    assert "BEAST_ACTIVE_WORKSPACE" in main
    assert "activeWorkspaceRoot" in main
    assert "repoRoot: activeWorkspaceRoot || repoRoot" in main
    assert "BEAST_ACTIVE_WORKSPACE: activeWorkspaceRoot || repoRoot" in main
    assert "DESKTOP_IDE_VERSION" in main
    assert "clearCache" in main
    assert "beast:desktop-version" in main
    assert "desktopVersion" in main
    assert "rendererPath" in main
    assert "onDesktopVersion" in preload


def test_terminal_chat_uses_desktop_gateway_stream_bridge():
    js = Path("desktop-ide/renderer/js/beast-terminal-tooling-doctor-bridge.js").read_text(encoding="utf-8")

    assert "openGatewayEventStream" in js
    assert "desktop.gatewayStreamStart" in js
    assert "desktop.onGatewayStreamMessage" in js
    assert "let terminalEventSeen = false" in js
    assert "terminalEventSeen = true" in js
    assert "await openGatewayEventStream" in js
    assert "new EventSource(`${gatewayUrl()}/edgek/ide/agent-sessions/" not in js


def test_desktop_ide_renderer_uses_tui_workflow_surfaces():
    html = Path("desktop-ide/renderer/index.html").read_text(encoding="utf-8")
    js = Path("desktop-ide/renderer/app.js").read_text(encoding="utf-8")

    assert "BEAST Desktop" in html
    assert 'data-view="mission"' in html
    assert 'data-view="source"' in html
    assert 'data-view="agents"' in html
    assert 'data-view="worktrees"' in html
    assert 'data-view="evidence"' in html
    assert 'data-view="terminal"' in html
    assert 'data-view="providers"' in html
    assert 'data-view="tooling"' in html
    assert 'data-view="doctor"' in html
    assert 'data-page-panel="source"' in html
    assert 'data-page-panel="agents"' in html
    assert 'data-page-panel="worktrees"' in html
    assert 'data-page-panel="evidence"' in html
    assert "SourcePlan Draft" in html
    assert "Mission Timeline" in html
    assert "sourcePlanLifecycle" in html
    assert "sourcePlanOperations" in html
    assert "sourcePlanActionContract" in html
    assert "sourcePlanOperationLedger" in html
    assert "diffHunkSelector" in html
    assert "exportMissionRunbook" in html
    assert "verifyMissionRunbook" in html
    assert "chooseSourceReceipt" in html
    assert "createHandoffPackage" in html
    assert "proposeLearning" in html
    assert "receiptChooser" in html
    assert "chooseEvidenceReceipt" in html
    assert "missionRouteStrip" in html
    assert "releaseReadiness" in html
    assert "checkReleaseReadiness" in html
    assert "openCommandPalette" in html
    assert "commandPaletteSearch" in html
    assert "commandPaletteOverlay" in html
    assert "commandPaletteModalSearch" in html
    assert "commandPaletteModal" in html
    assert "closeCommandPalette" in html
    assert "refreshCommandPalette" in html
    assert "commandPalette" in html
    assert "Command Palette" in html
    assert "statusChipBar" in html
    assert "desktopBuildId" in html


def test_opcb_dashboard_has_live_store_and_control_contract():
    html = Path("desktop-ide/renderer/index.html").read_text(encoding="utf-8")
    app_js = Path("desktop-ide/renderer/app.js").read_text(encoding="utf-8")
    js = app_js
    live_store = Path("desktop-ide/renderer/opcb-live-store.js").read_text(encoding="utf-8")
    state_js = Path("desktop-ide/renderer/opcb-state.js").read_text(encoding="utf-8")
    renderers = Path("desktop-ide/renderer/opcb-renderers.js").read_text(encoding="utf-8")
    reference_css = Path("desktop-ide/renderer/opcb-reference.css").read_text(encoding="utf-8")

    assert 'src="opcb-live-store.js"' in html
    assert "requiredGatewayRoutes" in live_store
    assert "/edgek/ide/snapshot" in live_store
    assert "/edgek/ide/system-snapshot" in live_store
    assert "/edgek/mcp/state" in live_store
    assert "actions_manifest" in live_store
    assert "/edgek/plugins" in live_store
    assert "/edgek/tools/integrations" in live_store
    assert "/edgek/workspace/files" in live_store
    assert "/edgek/mcp/servers" in live_store
    assert "/edgek/mcp/approvals" in live_store
    assert "/edgek/ide/tooling-snapshot" in live_store
    assert "normalizeGatewayDoctor" in live_store
    assert "window.opcbRecheckGatewayContract" in live_store
    assert "window.opcbRefreshPage" in live_store
    assert "normalizeMission" in live_store
    assert "normalizeWorkspace" in live_store
    assert "normalizeEvidence" in live_store
    assert "normalizeGraph" in live_store
    assert "normalizeReview" in live_store
    assert "normalizeTrust" in live_store
    assert "normalizeCrystallization" in live_store
    assert "normalizeModels" in live_store
    assert "normalizeAgents" in live_store
    assert "normalizeMemory" in live_store
    assert "window.opcbState.crystal" in live_store
    assert "applyPagePayload" in live_store
    assert "window.gatewayUrl = gatewayUrl" in app_js
    assert "window.workspaceRoot = workspaceRoot" in app_js
    assert "window.lastGatewayStatus = status" in app_js
    assert "window.setDesktopPage = setDesktopPage" in app_js
    assert "enteredPage && nextPage === 'tooling'" in app_js
    assert "refreshMcpOps({ stayOnPage: true, auto: true })" in app_js
    assert "if (mcpOpsPromise) return mcpOpsPromise" in app_js
    assert "if (toolingSnapshotPromise) return toolingSnapshotPromise" in app_js
    assert "gateway was not restarted" in app_js
    assert "Renderer error contained" in app_js
    assert "Renderer promise recovered" in app_js
    assert "system.refresh" in app_js
    assert "system.ports" in app_js
    assert "system.processes" in app_js
    assert "persistedWorkspaceRoot" in app_js
    assert "workspaceRevision" in app_js
    assert "discarded stale file list" in app_js
    assert "local file list loaded" in app_js
    assert "window.beastExplorerRows = explorerRows" in app_js
    assert "window.refreshFiles = refreshFiles" in app_js
    assert "No files loaded from the selected workspace" in app_js
    assert "$('refreshFiles')" in app_js
    assert "await refreshFiles();" in app_js
    assert "window.opcbRunIdeActionById" in app_js
    assert "window.opcbRecordAction" in app_js
    assert "window.opcbActionBlockReason" in app_js
    assert "window.opcbRefreshReadiness" in app_js
    assert "OPCB_READINESS_ACTIONS" in app_js
    assert "opcbRunReleaseReadinessProbe" in app_js
    assert "Gateway is required for this action" in app_js
    assert "Open a file before running code intelligence" in app_js
    assert "OPCB action failed" in app_js
    assert "enforceOpcbControlContract" in state_js
    assert "actionLedger" in state_js
    assert "Action Ledger" in state_js
    assert "gatewayDoctor" in state_js
    assert "readiness" in state_js
    assert "workspaceCanvas" in state_js
    assert "applyOpcbSelection" in state_js
    assert "select.${normalizedKind}" in state_js
    assert "data-opcb-readiness" in state_js
    assert "/readiness check" in state_js
    assert "data-opcb-recheck-gateway" in state_js
    assert "data-opcb-restart-gateway" in state_js
    assert "data-live-block-reason" in state_js
    assert "opcbActionBlockReason" in state_js
    assert "/gateway recheck" in state_js
    assert "/gateway restart" in state_js
    assert "data-opcb-active" not in state_js
    assert "data-prototype-reason" in state_js
    assert "data-opcb-refresh" in state_js
    assert "data-opcb-select" in state_js
    assert 'data-command="/files"' in state_js
    assert "window.setDesktopPage?.('source')" in state_js
    assert "OPCB command /files -> Source file explorer" in state_js
    assert 'data-command="/tooling"' in state_js
    assert 'data-command="/mcp"' in state_js
    assert 'data-command="/system"' in state_js
    assert "['/mcp', 'tooling.mcp']" in state_js
    assert "['/system', 'system.refresh']" in state_js
    assert "data-opcb-refresh=\"mission\">View Health Details" in state_js
    assert "['/view attestations', 'settings.release_readiness']" in state_js
    assert "['/show gates', 'settings.release_readiness']" in state_js
    assert "['/add fallback', 'providers.refresh']" in state_js
    assert "sourceplan.handoff_package" in state_js
    assert "sourceplan.export_runbook" in state_js
    assert "providers.smoke_nvidia" in state_js
    assert "window.opcbRunIdeActionById || window.runIdeActionById" in state_js
    assert "data-ide-action" in renderers
    assert "data-opcb-select" in renderers
    assert "data-page-target" in renderers
    assert "renderDoctorPage" in renderers
    assert "Full Readiness" in renderers
    assert "Critical Action Contract" in renderers
    assert "Readiness Blockers" in renderers
    assert "Gateway Route Contract" in renderers
    assert "doctor-route-row" in renderers
    assert "scope-control-row" in renderers
    assert "data-page-target=\"map\">Code Graph" in renderers
    assert "data-page-target=\"evidence\">Evidence Parser" in renderers
    assert "data-command=\"/canary status\"" in renderers
    assert "data-opcb-refresh=\"trust\">View Canary Details" in renderers
    assert "data-opcb-readiness>Run All Checks" in renderers
    assert "canvas-mode-${c().escapeHtml(ui.workspaceCanvas || 'fit')}" in renderers
    assert "filteredNodes" in renderers
    assert "selected-route-card" in renderers
    assert "route.required === false ? 'warn' : 'fail'" in renderers
    assert "Readability pass" in reference_css
    assert "font-size: 16px !important" in reference_css
    assert "grid-template-columns: 236px minmax(0, 1fr) !important" in reference_css
    assert ".scope-control-row button" in reference_css
    assert ".canary-grid button" in reference_css
    assert ".workspace-flow-canvas.canvas-mode-list" in reference_css
    assert ".doctor-route-row.selected" in reference_css
    styles = Path("desktop-ide/renderer/styles.css").read_text(encoding="utf-8")
    assert ".app-shell[data-dashboard-page='true']:not([data-desktop-page='workspace']) #fileExplorerSection" in styles
    assert ".app-shell[data-desktop-page='workspace'] #fileExplorerBody" in styles
    assert ".app-shell[data-desktop-page='source'] #fileExplorerBody" in styles
    assert ".app-shell[data-dashboard-page='true']:not([data-desktop-page='workspace']) #fileExplorerBody" in styles
    assert ".app-shell[data-desktop-page='mission'] #fileExplorerBody" not in styles
    assert "clamp(180px, 24vh, 280px)" not in styles
    assert "max-height: calc(100vh - 178px)" in reference_css
    assert "nextActionInspector" in html
    assert "assets/beast-dragon-mascot.png" in html
    assert "127.0.0.1:8000/beast-assets" not in html
    assert "expandExplorer" in html
    assert "refreshFiles" in html
    assert "toggleExplorerMode" in html
    assert "fileExplorerStatus" in html
    assert "sourcePlanChecklist" in html
    assert "activeMissionCard" in html
    assert "data-collapse-panel" in html
    assert "sourcePlanFromSelection" in html
    assert "saveViaSourcePlan" in html
    assert "newWorkspaceFile" in html
    assert "renameWorkspaceFile" in html
    assert "deleteWorkspaceFile" in html
    assert "undoEdit" in html
    assert "redoEdit" in html
    assert "toggleSplitEditor" in html
    assert "monacoSplitEditor" in html
    assert "revertEditorBuffer" in html
    assert "reloadActiveFile" in html
    assert "selectAllSourceOps" in html
    assert "selectNoSourceOps" in html
    assert "reloadForSourcePlan" in html
    assert "monacoEditor" in html
    assert "monacoDiff" in html
    assert "../node_modules/monaco-editor/min/vs/loader.js" in html
    assert "explorerFlatMode" in js
    assert "setExplorerStatus" in js
    assert "countTreeFiles" in js
    assert "openTabs" in html
    assert "collapseExplorer" in html
    assert "revealActiveFile" in html
    assert "editorMeta" in html
    assert "Related Context" in html
    assert "Symbol Lens" in html
    assert "symbolOutlineMeta" in html
    assert "symbolOutline" in html
    assert "refreshSymbolOutline" in html
    assert "askSymbolAgent" in html
    assert "symbolSearchQuery" in html
    assert "symbolSearchResults" in html
    assert "runSymbolSearch" in html
    assert "askSymbolSearchAgent" in html
    assert "goToDefinition" in html
    assert "findReferences" in html
    assert "relatedTestsRoutes" in html
    assert "codeCortex" in html
    assert "Agent Sessions" in html
    assert "Agent Detail" in html
    assert "agentPromptText" in html
    assert "sendAgentPrompt" in html
    assert "agentIncludeActiveFile" in html
    assert "agentIncludeSelection" in html
    assert "agentIncludeRelated" in html
    assert "agentContextSummary" in html
    assert "agentAskSelection" in html
    assert "agentRefreshContext" in html
    assert "agentRunInspector" in html
    assert "agentProviderHealth" in html
    assert "agentStageTrace" in html
    assert "agentToolTrace" in html
    assert "agentProposedText" in html
    assert "agentPreviewPatch" in html
    assert "agentCompilePatch" in html
    assert "agentStagePatch" in html
    assert "agentRequestPatch" in html
    assert "agentTurnTimeline" in html
    assert "eventStreamState" in html
    assert "runAgentStream" in html
    assert "Provider Setup" in html
    assert "providerSelect" in html
    assert "providerModel" in html
    assert "smokeNvidiaProvider" in html
    assert "Tooling Plane" in html
    assert "toolingSummary" in html
    assert "syntaxLintPanel" in html
    assert "mcpPluginPanel" in html
    assert "mcpOpsPanel" in html
    assert "pluginOpsPanel" in html
    assert "environmentPanel" in html
    assert "refreshMcpOps" in html
    assert "approveMcpRequest" in html
    assert "validatePluginManifest" in html
    assert "providerAgentPage" in html
    assert "nvidia/nemotron-3-super-120b-a12b" in html
    assert "verifySourcePlan" in html
    assert "applySourcePlan" in html
    assert "classifyCommand" in html
    assert "executeCommand" in html
    assert "terminalCwd" in html
    assert "terminalTimeout" in html
    assert "terminalDecisionCard" in html
    assert "terminalPolicySummary" in html
    assert "terminalHistoryList" in html
    assert "terminalEvidenceDetail" in html
    assert "terminalStreamState" in html
    assert "cancelCommand" in html
    assert "terminalCopyLastReceipt" in html
    assert "searchEvidence" in html
    assert "relatedEvidence" in html
    assert "testWorktree" in html
    assert "draftWorktreePlan" in html
    assert "openWorktreeWindow" in html
    assert "browseWorktreeDiff" in html
    assert "worktreePromotionWizard" in html
    assert "worktreeWizardSteps" in html
    assert "worktreeDiffSummary" in html
    assert "Worktree Missions" in html
    assert "Gateway Doctor" in html
    assert "gatewayDoctorRaw" in html
    assert "copyDoctorReport" in html
    assert "/edgek/ide/snapshot" in js
    assert "/edgek/ide/events" in js
    assert "/edgek/ide/mission-timeline" in js
    assert "/edgek/ide/sourceplan/lifecycle" in js
    assert "/edgek/ide/receipts/chooser" in js
    assert "/edgek/ide/mission-runbook/export" in js
    assert "/edgek/ide/mission-runbook/verify" in js
    assert "/edgek/ide/sourceplan/handoff-package" in js
    assert "/edgek/ide/release-readiness/check" in js
    assert "/edgek/ide/learning-queue/propose" in js
    assert "/edgek/ide/actions/manifest" in js
    assert "/edgek/ide/actions/plan" in js
    assert "/edgek/ide/mission-route" in js
    assert "/edgek/ide/related-context" in js
    assert "/edgek/ide/symbol-outline" in js
    assert "/edgek/ide/symbol-search" in js
    assert "/edgek/ide/text-search" in js
    assert "/edgek/evidence-bus/query" in js
    assert "/edgek/evidence-bus/related/" in js
    assert "/run-events" in js
    assert "/edgek/providers/registry" in js
    assert "/edgek/providers/state" in js
    assert "/edgek/providers/secrets/route/" in js
    assert "/edgek/providers/nvidia-nim/live-smoke" in js
    assert "/edgek/workspace/files" in js
    assert "window.beastDesktop?.listFiles" in js
    assert "window.beastDesktop.readFile" in js
    assert "window.beastDesktop.fileOperation" in js
    assert "window.beastDesktop.openWorkspaceWindow" in js
    assert "refreshMcpOps" in js
    assert "resolveMcpApproval" in js
    assert "refreshPluginOps" in js
    assert "runBenchmarkGradingDaemon" in js
    assert "copyBenchmarkVerdict" in js
    assert "validatePluginManifest" in js
    assert "selectedAgentSessionId" in js
    assert "selectedWorktreeTaskId" in js
    assert "commandPaletteRecents" in js
    assert "renderWorktreeWizardSteps" in js
    assert "renderWorktreeDiffSummary" in js
    assert "/edgek/ide/sourceplan/from-editor" in js
    assert "/edgek/ide/sourceplan/from-selection" in js
    assert "/edgek/sourceplan/verify" in js
    assert "/edgek/sourceplan/apply" in js
    assert "/edgek/sourceplan/rollback-latest" in js
    assert "/edgek/safety-governor/classify-command" in js
    assert "/edgek/ide/terminal/stream" in js
    assert "loadTerminalState" in js
    assert "rememberTerminalCommand" in js
    assert "recordTerminalExecution" in js
    assert "renderTerminalDecision" in js
    assert "terminalHistoryStorageKey" in js
    assert "terminalExecutionsStorageKey" in js
    assert "applyTerminalEvidenceFilter" in js
    assert "terminalUseWorkspaceCwd" in js
    assert "/edgek/ide/worktree-mission/test" in js
    assert "/edgek/ide/worktree-mission/sourceplan-draft" in js
    assert "/edgek/ide/worktree-mission/create" in js
    assert "/edgek/ide/agent-sessions/create" in js
    assert "/edgek/ide/agent-sessions/update" in js
    assert "/edgek/ide/agent-sessions/sourceplan-draft" in js
    assert "/edgek/ide/agent-sessions/action-ir-sourceplan" in js
    assert "sendAgentPrompt" in js
    assert "buildAgentContextPack" in js
    assert "bufferStorageKey" in js
    assert "persistDirtyBuffer" in js
    assert "restorePersistedBuffer" in js
    assert "saveViaSourcePlan" in js
    assert "revertEditorBuffer" in js
    assert "reloadActiveFileFromDisk" in js
    assert "setSourcePlanOperationSelection" in js
    assert "reloadBaseForSourcePlan" in js
    assert "rebaseSourcePlanAgainstDisk" in js
    assert "editSelectedSourcePlanOperation" in js
    assert "moveSelectedSourcePlanOperation" in js
    assert "renderRollbackPreview" in js
    assert "renderApplyTimeline" in js
    assert "runSymbolSearch" in js
    assert "renderSymbolSearchResults" in js
    assert "openSelectedSymbolSearchResult" in js
    assert "askAgentAboutSymbolSearchResult" in js
    assert "goToDefinition" in js
    assert "findReferences" in js
    assert "relatedTestsRoutes" in js
    assert "refreshCodeIntelligence" in js
    assert "/edgek/ide/code-intel" in js
    assert "data-symbol-search-path" in js
    assert "renderDiffHunkSelector" in js
    assert "toggleDiffHunk" in js
    assert "selected_hunks" in js
    assert "/edgek/ide/terminal/stream" in js
    assert "cancelTerminalCommand" in js
    assert "renderAgentActionIrRetry" in js
    assert "event.key.toLowerCase() === 's'" in js
    assert "AGENT_INLINE_SELECTION_LIMIT" in js
    assert "AGENT_PATCH_REPLACEMENT_LIMIT" in js
    assert "AGENT_CONTEXT_FILE_CHARS" in js
    assert "selectionContextSummary" in js
    assert "large selection referenced, not inlined" in js
    assert "BEAST Desktop did not inline this selection" in js
    assert "Do not infer missing code from a preview or truncation marker" in js
    assert "will not inline it or request one fenced replacement block" in js
    assert "renderAgentContextPack" in js
    assert "askAgentAboutSelection" in js
    assert "context_files" in js
    assert "extractLastCodeFence" in js
    assert "isAgentToolCommandFence" in js
    assert "validateAgentPatchCandidate" in js
    assert "looksLikeNarrativePatch" in js
    assert "sourceLanguageForPath" in js
    assert "replacement looks like model reasoning/prose" in js
    assert "Agent patch rejected before diff preview" in js
    assert "No valid source-code replacement block found" in js
    assert "latestAgentToolCommand" in js
    assert "previewAgentPatch" in js
    assert "compileAgentPatchSourcePlan" in js
    assert "stageAgentPatchBuffer" in js
    assert "requestAgentPatchForSelection" in js
    assert "refreshSymbolOutline" in js
    assert "renderSymbolOutline" in js
    assert "localSymbolOutline" in js
    assert "selectEditorRange" in js
    assert "selectSymbolFromButton" in js
    assert "askAgentAboutSymbol" in js
    assert "data-symbol-line" in js
    assert "recordAgentPrompt" in js
    assert "recordAgentDiagnostic" in js
    assert "providerRetryOptions" in js
    assert "symbol-scoped patches" in js
    assert "agent_run_provider_done" in js
    assert "selectedProvider" in js
    assert "selectedModel" in js
    assert "nvidia/nemotron-3-super-120b-a12b" in js
    assert "refreshProviderSetup" in js
    assert "providerSetupSummary" in js
    assert "providerRecordLabel" in js
    assert "providerInventoryItems" in js
    assert "renderProviderSetup" in js
    assert "providerReadinessState" in js
    assert "route: READY" in js
    assert "smokeNvidiaProvider" in js
    assert "resetAgentRunInspector" in js
    assert "setAgentProviderHealth" in js
    assert "pushAgentStage" in js
    assert "pushAgentTool" in js
    assert "filePathForItem" in js
    assert "initMonaco" in js
    assert "monaco.editor.create" in js
    assert "createDiffEditor" in js
    assert "registerHoverProvider" in js
    assert "updateDiagnosticsAndDecorations" in js
    assert "dynamic execution requires explicit policy" in js
    assert "possible hard-coded secret" in js
    assert "buildFileTree" in js
    assert "updateOpenTabs" in js
    assert "dirtyFiles" in js
    assert "saveWorkspaceState" in js
    assert "loadWorkspaceState" in js
    assert "restoreWorkspaceTabs" in js
    assert "applyCollapsedPanels" in js
    assert "renderGatewayDoctor" in js
    assert "copyDoctorReport" in js
    assert "gateway warming" in js
    assert "local IDE mode" in js
    assert "desktopLocalMode" in js
    assert "SourcePlan draft deferred" in js
    assert "tcp_listening" in js
    assert "AbortController" in js
    assert "capability mode" in js
    assert "setDesktopPage" in js
    assert "refreshActionManifest" in js
    assert "desktopLocalActionManifest" in js
    assert "renderCommandPalette" in js
    assert "openCommandPaletteModal" in js
    assert "closeCommandPaletteModal" in js
    assert "syncCommandPaletteSearch" in js
    assert "runIdeAction" in js
    assert "data-ide-action" in js
    assert "data-next-page" in js
    assert "data-collapse-panel" in js
    assert "focusCommandPalette" in js
    assert "updateStatusChips" in js
    assert "renderDesktopBuildId" in js
    assert "onDesktopVersion" in js
    assert "renderSourcePlanChecklist" in js
    assert "renderNextActionInspector" in js
    assert "explainGatewayState" in js
    assert "providerErrorHint" in js
    assert "event.key.toLowerCase() === 'k'" in js
    assert "event.key === 'Escape'" in js
    assert "context_max_chars_each" in js


def test_desktop_ide_backend_declares_action_manifest():
    routes = Path("app/routes/ide.py").read_text(encoding="utf-8")
    main_routes = Path("app/main.py").read_text(encoding="utf-8")
    workspace_routes = Path("app/routes/workspace.py").read_text(encoding="utf-8")
    beast_cli = Path("bin/beast").read_text(encoding="utf-8")
    html = Path("desktop-ide/renderer/index.html").read_text(encoding="utf-8")
    js = Path("desktop-ide/renderer/app.js").read_text(encoding="utf-8")

    assert "_ide_action_manifest" in routes
    assert '"/edgek/ide/actions/manifest"' in routes
    assert '"/edgek/ide/actions/plan"' in routes
    assert "beast_ide_action_manifest" in routes
    assert "beast_ide_action_plan" in routes
    assert "direct_mutation_allowed" in routes
    assert "terminal_execution_requires_safety_governor" in routes
    assert "desktop_smoke_passed" in routes
    assert "subprocess.run" in routes
    assert "smoke-desktop-ide.js" in routes
    assert "terminal_maturity_controls_present" in routes
    assert "desktop_launch_smoke_passed" in routes
    assert '"/edgek/ide/text-search"' in routes
    assert '"/edgek/ide/worktree-mission/diff"' in routes
    assert "workspace_persistence_controls_present" in routes
    assert "sourceplan.apply" in routes
    assert "editor.save_sourceplan" in routes
    assert "editor.revert_buffer" in routes
    assert "editor.reload_file" in routes
    assert "terminal.execute" in routes
    assert "terminal.stream" in routes
    assert '"/edgek/ide/terminal/stream"' in routes
    assert '"/edgek/ide/code-intel"' in routes
    assert "beast_ide_code_intel" in routes
    assert "missing_context_questions" in routes
    assert "providers.smoke_nvidia" in routes
    assert "tooling.refresh" in routes
    assert "tooling.mcp_ops" in routes
    assert "tooling.plugin_ops" in routes
    assert "tooling.grade_benchmark_packet" in routes
    assert '"/edgek/benchmarks/public-grading-daemon"' in routes
    assert '"/edgek/ide/tooling-snapshot"' in routes
    assert "beast_ide_tooling_snapshot" in routes
    assert '"settings.release_readiness"' in routes
    assert "local_fallback=True" in routes
    assert "context_max_chars_each: int = 30000" in routes
    assert '"/edgek/ide/symbol-outline"' in routes
    assert '"/edgek/ide/symbol-search"' in routes
    assert '"/edgek/ide/agent-sessions/action-ir-sourceplan"' in routes
    assert "ACTION_IR_KIND" in routes
    assert "_symbol_outline_for_text" in routes
    assert "activateEditorTab" in js
    assert "desktop_local_files" in js
    assert "renderSourcePlanActionContract" in js
    assert "renderSourcePlanOperationLedger" in js
    assert "chooseReceiptsForAction" in js
    assert "exportMissionRunbook" in js
    assert "verifyMissionRunbook" in js
    assert "createHandoffPackage" in js
    assert "proposeLearning" in js
    assert "checkReleaseReadiness" in js
    assert "Gateway readiness route unavailable" in js
    assert '"/edgek/workspace/files"' in beast_cli
    assert '"/edgek/ide/actions/manifest"' in beast_cli
    assert '"/edgek/ide/tooling-snapshot"' in beast_cli
    assert '"/edgek/ide/system-snapshot"' in beast_cli
    assert "_ensure_workspace_routes_mounted" in main_routes
    assert "_ensure_ide_routes_mounted" in main_routes
    assert "app.router.routes.extend(router.routes)" in main_routes
    assert '"/edgek/workspace/files"' in workspace_routes
    assert '"/edgek/ide/actions/manifest"' in routes
    assert "window.beastDesktop.releaseReadiness" in js
    assert "refreshMissionRoute" in js
    assert "refreshToolingSnapshot" in js
    assert "runSyntaxToolingCheck" in js
    assert "showLintToolingContract" in js
    assert "focusMcpTooling" in js
    assert "focusPluginTooling" in js
    assert "benchmarkVerdictStatus" in html
    assert "runBenchmarkGrading" in html
    assert "copyBenchmarkVerdict" in html
    assert "Run Benchmark Grading Daemon" in js
    assert "/edgek/benchmarks/public-grading-daemon" in js
    assert "focusEnvironmentTooling" in js


def test_desktop_agent_context_does_not_fake_truncated_code_blocks():
    js = Path("desktop-ide/renderer/app.js").read_text(encoding="utf-8")

    assert "...[selection truncated by BEAST Desktop]" not in js
    assert "selection.selected.slice(0, 4000)" not in js
    assert "BEAST Desktop did not inline this selection" in js
    assert "large selection referenced, not inlined" in js


def test_desktop_ide_backend_uses_request_base_url_for_live_routes():
    route_source = Path("app/routes/ide.py").read_text(encoding="utf-8")

    assert "Request" in route_source
    assert "_request_base_url(request)" in route_source
    assert "http://gateway-local" not in route_source
    assert "context_files: List[str] | None = None" in route_source


def test_pair_programmer_refreshes_live_provider_route_before_starting():
    js = Path("desktop-ide/renderer/js/beast-ai-coding.js").read_text(encoding="utf-8")
    page = Path("desktop-ide/renderer/js/pages/beast-workspace-page.js").read_text(encoding="utf-8")
    css = Path("desktop-ide/renderer/css/beast-production.css").read_text(encoding="utf-8")
    routes = Path("app/routes/ide.py").read_text(encoding="utf-8")

    assert "resolveCodingRoute" in js
    assert "Model registry was not ready; refreshing live providers" in js
    assert "window.BeastModelAgentBridge.refreshModels" in js
    assert "'/edgek/providers/state'" in js
    assert "providerStateRoute" in js
    assert "row.id === 'nvidia_nim'" in js
    assert "Recovered live provider route" in js
    assert "const route = await resolveCodingRoute" in js
    assert "function appendTurn" in js
    assert "function narrationFromTurn" in js
    assert "function runDoneSentence" in js
    assert "Recovery is waiting for your review. No files changed." in js
    assert "narrating:shouldNarrate" in js
    assert "content:message.content" in js
    assert "I’m streaming my response now" in js
    assert "I verified my handoff is ready" in js
    assert "I’m waiting for the model’s stream" not in js
    assert "I’m provider stream" not in js
    assert "I connected to the selected model and started the run" in js
    assert "agent_run_request" in js
    assert "I need a little more context before the next pass" in js
    assert "type === 'context_search'" in js
    assert "type === 'context_result'" in js
    assert "type === 'context_attach'" in js
    assert "type === 'context_continue'" in js
    assert "function appendProposalTurns" in js
    assert "function continueWithAddedContext" in js
    assert "function recoverInvalidPacket" in js
    assert "function isAgentAnalysisPrompt" in js
    assert "function agentTurnProfile" in js
    assert "function initialAgentTurns" in js
    assert "function initialAgentProgress" in js
    assert "Operating mode: ${profile.kind}" in js
    assert "Starting ${agentProfile.kind} loop" in js
    assert "discover and run focused workspace checks" in js
    assert "SourcePlan required before writes" in js
    assert "uiMode === 'analysis' ? 'analysis' : 'implementer'" in js
    assert "analysisRun ? 'analysis' : mode" in js
    assert "This is an analysis turn, not an edit request" in js
    assert "mode==='ask'||analysisRun" in js
    assert "focused:false" in js
    assert "preserveContext:true" in js
    assert "actionIrRecovery:true" in js
    assert "Edit packet needs repair" in js
    assert "BEAST caught an edit-packet problem before it could become a patch" in js
    assert "The model returned an invalid edit packet" not in js
    assert "I’m searching for the extra context the agent asked for" in js
    assert "I found context candidates for review" in js
    assert "I added this file to the next run’s context" in js
    assert "I’m continuing the same task with the expanded context" in js
    assert "operator accepted suggestion" in js
    assert "type === 'tool_call'" in js
    assert "I’m inspecting the selected code and nearby dependencies now" in js
    assert "I checked prior repo evidence for anything useful to this turn" in js
    assert "type:'tool_result'" in js
    assert "payload.tool||'BEAST governed tool'" in js
    assert "payload.authority||'read-only/governed'" in js
    assert "turnType==='tool_call'?'active'" in js
    assert "'command_request':'command_result'" in js
    assert "type:'command_call'" in js
    assert "I’m running an isolated check now" in js
    assert "Operator approved; running in an isolated temporary workspace" in js
    assert "type:'command_result'" in js
    assert "authority:'isolated temporary workspace'" in js
    assert "appendAssistant(assistantId,text)" in js
    assert "Streaming model output" in js
    assert "function structuredDraftStatus" in js
    assert "function isStructuredEditStream" in js
    assert "Receiving a structured edit plan" in js
    assert "run_verifier" in js
    assert "ask_for_context" in js
    assert "Agent requested" in js
    assert "verifyRequestedChecks" in js
    assert "resolveRequestedContext" in js
    assert "agent-requested context suggestion(s) ready for your approval" in js
    assert "'/edgek/ide/agent-sessions/verify-sourceplan'" in js
    assert "Running agent-requested checks in an isolated temporary workspace" in js
    assert "mode==='ask'||analysisRun)appendAssistant(assistantId,text)" in js
    assert "internalFormat:'beast.action_intent.v1'" in js
    assert "function aiAgentCockpit" in page
    assert "Agent cockpit" in page
    assert "const profile=message?.agentProfile||{}" in page
    assert "['Intent',profile.kind||message.mode||'agent'" in page
    assert "function aiNarration" in page
    assert "function aiVisibleMessageContent" in page
    assert "function aiActiveAgentRequests" in page
    assert "Agent requests" in page
    assert "'agent-open-terminal'" in page
    assert "'agent-suggest-context'" in page
    assert "BeastTerminalToolingDoctorBridge.setCommand" in page
    assert "BeastRouter.navigate('terminal')" in page
    assert "liveNarration" in page
    assert "aiMessageBody(aiVisibleMessageContent(message))" in page
    assert "aiActiveAgentRequests(message)" in page
    assert "Agent updates" in page
    assert "if(explicit.length)return" not in page
    assert "const combined=[...explicit,...rows]" in page
    assert "I’m running an isolated check now" in page
    assert "context_search" in page
    assert "context_result" in page
    assert "context_attach" in page
    assert "context_continue" in page
    assert "I’m searching for the extra context the agent asked for" in page
    assert "I found context candidates for review" in page
    assert "I added this file to the next run’s context" in page
    assert "Continue with added context" in page
    assert "agent-continue-context" in page
    assert "continueWithAddedContext" in page
    assert "function aiRecoveryCard" in page
    assert "Agent recovery" in page
    assert "agent-repair-packet" in page
    assert "recoverInvalidPacket" in page
    assert "recovery:message.recovery" in page
    assert "recovery_request" in page
    assert "I’m inspecting the selected code and nearby dependencies now" in page
    assert "I checked prior repo evidence for anything useful to this turn" in page
    assert "I’m streaming my response now" in page
    assert "I verified my handoff is ready" in page
    assert "I’m waiting for the model’s stream" not in page
    assert "Reading workspace context" in page
    assert "I’m provider stream" not in page
    assert "I used ${item.tool||'a governed BEAST tool'} and got a result" not in page
    assert "I read the selected workspace context" in page
    assert "Agent next actions" in page
    assert "agent-context" in page
    assert "Find requested context" in page
    assert "agent-verify" in page
    assert "Run agent requested checks" in page
    assert "Context" in page
    assert "SourcePlan" in page
    assert "aiAgentCockpit(message)" in page
    assert "aiNarration(message)" in page
    assert "aiTurns(message)" in page
    assert "Debug transcript" in page
    assert "aria-label=\"Debug agent transcript\"" in page
    assert "Typed agent turns" not in page
    assert "model output stays private" not in page
    assert ".cortex-ai-cockpit" in css
    assert ".cortex-ai-narration" in css
    assert ".cortex-ai-agent-requests" in css
    assert ".cortex-ai-recovery" in css
    assert ".cortex-ai-turns" in css
    assert ".cortex-ai-turns p.command_result" in css
    assert "Conversation-first viewport" in css
    assert "without clipping the composer" in css
    assert "overflow-y:auto!important" in css
    assert "grid-template-rows:auto auto auto minmax(0,1fr) auto auto auto!important" in css
    assert "@media(min-height:760px)" in css
    assert "minmax(min(42vh,520px),1fr)" in css
    assert "minmax(min(55vh,720px),1fr)" in css
    assert ".beast-workspace-page.ai-open .cortex-ai-route>p{display:none!important}" in css
    assert ".beast-workspace-page.ai-open .cortex-ai-prompt-shell textarea{height:48px!important" in css
    assert "agents.verify_requested_checks" in routes
    assert "def _tool_event" in routes
    assert "def _tool_call_event" in routes
    assert 'session_mode in {"chat", "analysis", "analyze"}' in routes
    assert '"agent_run_request"' in routes
    assert '"type": "command_request"' in routes
    assert '"context_request" if request_type == "ask_for_context"' in routes
    assert '"type": "tool_result"' in routes
    assert '"type": "tool_call"' in routes
    assert "Inspecting {len(context_file_list[:3])} selected file(s)" in routes
    assert 'tool="Code Cortex"' in routes
    assert 'tool="Workspace Search"' in routes
    assert 'tool="Provider Handoff"' in routes
    assert '"/edgek/ide/agent-sessions/verify-sourceplan"' in routes
    assert "_validate_agent_sourceplan(root, plan, run_isolated_verifier=True)" in routes
    assert "non_mutating_requests" in routes
    assert "run only after operator approval" in routes


def test_desktop_status_reports_runtime_stack_health():
    main = Path("desktop-ide/main.js").read_text(encoding="utf-8")
    beast_cli = Path("bin/beast").read_text(encoding="utf-8")
    app_main = Path("app/main.py").read_text(encoding="utf-8")

    assert "function serviceRegistryPort" in main
    assert "async function runtimeStackHealth" in main
    assert "`${baseUrl}/proxy/health`" in main
    assert "`${baseUrl}/edgek/providers/state`" in main
    assert "name:'mcp_http'" in main
    assert "name:'litellm'" in main
    assert "name:'nginx'" in main
    assert "const runtimeStack = await runtimeStackHealth" in main
    assert "runtimeStack," in main
    assert "'--gateway-port', String(registryGatewayPort)" in main
    assert "'--mcp-port', String(registryMcpPort)" in main
    assert "'--nginx-port', String(registryNginxPort)" in main
    assert "['gateway', 'proxy', 'litellm', 'ollama', 'nginx', 'desktop_contract']" in main
    assert 'url_ready(f"http://127.0.0.1:{nginx_port}/health"' in beast_cli
    assert 'default=8765' in beast_cli
    assert "nginx is running but is not serving the BEAST health route" in beast_cli
    assert '@app.get("/mcp/health")' in app_main
    assert "edgek-beast-mcp-gateway" in app_main
    assert "ensure_stack" in beast_cli
    assert "command_heal(argparse.Namespace" in beast_cli
    assert 'mcp_port=registry_service_port("mcp_http", 8765)' in beast_cli
