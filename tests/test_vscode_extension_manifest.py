import json
from pathlib import Path


def test_vscode_extension_manifest_exposes_phase_one_to_three_commands():
    manifest = json.loads(Path("vscode-extension/package.json").read_text(encoding="utf-8"))
    commands = {item["command"] for item in manifest["contributes"]["commands"]}
    expected = {
        "edgekBeast.openMissionControl",
        "edgekBeast.openSourceWorkbench",
        "edgekBeast.showEvidence",
        "edgekBeast.showCodeCortex",
        "edgekBeast.showPolicyGate",
        "edgekBeast.showWorktrees",
        "edgekBeast.startIdeEventBus",
        "edgekBeast.sourcePlanFromSelection",
        "edgekBeast.openSideBySidePreview",
        "edgekBeast.switchSourcePlanSession",
        "edgekBeast.refreshSourcePlanPreview",
        "edgekBeast.jumpRelatedContext",
    }
    assert expected.issubset(commands)
    assert manifest["version"] == "1.6.0"
    assert manifest["icon"] == "media/beast-dragon-extension-icon.png"
    assert manifest["contributes"]["viewsContainers"]["activitybar"][0]["icon"] == "media/beast-dragon-activity.svg"


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
