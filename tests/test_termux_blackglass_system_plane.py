from pathlib import Path


def test_termux_system_inspector_has_cli_fallbacks_and_platform_tag():
    source = Path("app/kernel/workspaces/system_inspector.py").read_text(encoding="utf-8")
    assert 'if not rows:' in source
    assert 'fallback = _processes_via_ps(needle)' in source
    assert 'platform_mode' in source
    assert 'termux_android' in source
    assert 'source": "/proc/loadavg"' in source


def test_blackglass_projects_nested_system_snapshot_contract():
    source = Path("desktop-ide/renderer/js/beast-utility-orchestration-bridge.js").read_text(encoding="utf-8")
    assert "systemInventory?.ports?.ports" in source
    assert "systemInventory?.processes?.processes" in source
    assert "systemTelemetry?.resources || systemPayload?.summary?.resources" in source
    assert "ports,processes" in source
