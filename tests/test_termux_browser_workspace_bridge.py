from pathlib import Path


def test_termux_browser_workspace_bridge_contract():
    source = Path("desktop-ide/renderer/js/beast-desktop-bridge.js").read_text(encoding="utf-8")

    assert "validateBrowserWorkspace" in source
    assert "BEAST workspace path" in source
    assert "/edgek/workspace/files?" in source
    assert "browser-workspace" in source
    assert "Workspace chooser is available only inside the BEAST desktop shell." not in source
    assert "localStorage.getItem('beast.v2.workspace.root')" in source
