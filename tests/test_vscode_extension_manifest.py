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
