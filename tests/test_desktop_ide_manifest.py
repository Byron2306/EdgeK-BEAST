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
    assert "maxAutomaticAttempts" in main
    assert "gatewayHealth(baseUrl = gatewayUrl, rootTimeoutMs = 8000)" in main
    assert "findCompatibleGateway" in main
    assert "attached to compatible BEAST gateway" in main
    assert "gatewayCapabilityHealth(baseUrl = gatewayUrl, rootPayload = null)" in main
    assert "declared_by_root_info" in main
    assert "mode: 'route_manifest'" in main
    assert "port ${port} is already in use; trying next port" in main
    assert "gatewayUrl: health.url || gatewayUrl" in main
    assert "gateway process is listening" in main
    assert "leaving process alive for diagnosis" in main
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
    assert "openGateway" in preload
    assert "beast:choose-workspace" in main
    assert "BEAST_ACTIVE_WORKSPACE" in main
    assert "DESKTOP_IDE_VERSION" in main
    assert "clearCache" in main
    assert "beast:desktop-version" in main
    assert "desktopVersion" in main
    assert "rendererPath" in main
    assert "onDesktopVersion" in preload


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
    assert "nextActionInspector" in html
    assert "assets/beast-dragon-mascot.png" in html
    assert "127.0.0.1:8000/beast-assets" not in html
    assert "expandExplorer" in html
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
    assert "window.beastDesktop.listFiles" in js
    assert "window.beastDesktop.readFile" in js
    assert "window.beastDesktop.fileOperation" in js
    assert "window.beastDesktop.openWorkspaceWindow" in js
    assert "refreshMcpOps" in js
    assert "resolveMcpApproval" in js
    assert "refreshPluginOps" in js
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
    assert "fallback_used" in js
    assert "renderSourcePlanActionContract" in js
    assert "renderSourcePlanOperationLedger" in js
    assert "chooseReceiptsForAction" in js
    assert "exportMissionRunbook" in js
    assert "verifyMissionRunbook" in js
    assert "createHandoffPackage" in js
    assert "proposeLearning" in js
    assert "checkReleaseReadiness" in js
    assert "Gateway readiness route unavailable" in js
    assert "window.beastDesktop.releaseReadiness" in js
    assert "refreshMissionRoute" in js
    assert "refreshToolingSnapshot" in js
    assert "runSyntaxToolingCheck" in js
    assert "showLintToolingContract" in js
    assert "focusMcpTooling" in js
    assert "focusPluginTooling" in js
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
