import json
from pathlib import Path


def test_vscode_extension_manifest_exposes_phase_one_to_three_commands():
    manifest = json.loads(Path("vscode-extension/package.json").read_text(encoding="utf-8"))
    commands = {item["command"] for item in manifest["contributes"]["commands"]}
    expected = {
        "edgekBeast.openMissionControl",
        "edgekBeast.diagnoseIdeShell",
        "edgekBeast.openIdeLog",
        "edgekBeast.openSourceWorkbench",
        "edgekBeast.showEvidence",
        "edgekBeast.showCodeCortex",
        "edgekBeast.showPolicyGate",
        "edgekBeast.showAgentSessions",
        "edgekBeast.createAgentSession",
        "edgekBeast.pauseAgentSession",
        "edgekBeast.resumeAgentSession",
        "edgekBeast.cancelAgentSession",
        "edgekBeast.agentSessionToSourcePlan",
        "edgekBeast.showWorktrees",
        "edgekBeast.startIdeEventBus",
        "edgekBeast.sourcePlanFromSelection",
        "edgekBeast.openSideBySidePreview",
        "edgekBeast.switchSourcePlanSession",
        "edgekBeast.refreshSourcePlanPreview",
        "edgekBeast.jumpRelatedContext",
        "edgekBeast.openWorktreeMission",
        "edgekBeast.runWorktreeVerifier",
        "edgekBeast.promoteWorktreeMission",
        "edgekBeast.closeWorktreeMission",
    }
    assert expected.issubset(commands)
    assert manifest["version"] == "1.6.1"
    assert manifest["icon"] == "media/beast-dragon-extension-icon.png"
    assert manifest["contributes"]["viewsContainers"]["activitybar"][0]["icon"] == "media/beast-dragon-activity.svg"
    view_ids = {item["id"] for item in manifest["contributes"]["views"]["beastSidebar"]}
    assert {"beastAgentSessions", "beastWorktreeMissions"}.issubset(view_ids)


def test_vscode_extension_dragon_assets_are_packaged():
    media = Path("vscode-extension/media")
    expected = {
        "beast-dragon-extension-icon.png",
        "beast-dragon-mascot.png",
        "beast-dragon-activity.svg",
    }
    for name in expected:
        path = media / name
        assert path.exists(), name
        assert path.stat().st_size > 1000, name
    assert not (media / "beast-icon-source.png").exists()
    assert not (media / "beast-icon.svg").exists()


def test_vscode_extension_starts_beast_gateway_command():
    source = Path("vscode-extension/extension.js").read_text(encoding="utf-8")
    assert " gateway --host 127.0.0.1 --port 8000" in source
    assert " serve --host 127.0.0.1 --port 8000" not in source
    assert "lastGatewayStart" in source
    assert "openIdeLog" in source
    assert "copyDoctor" in source
    assert "BEAST IDE Doctor report copied" in source
