from pathlib import Path

from app.kernel.deployment.plugin_marketplace import PluginMarketplace


def test_marketplace_falls_back_when_implicit_state_is_unwritable(monkeypatch, tmp_path):
    unwritable = tmp_path / "state"
    monkeypatch.setenv("XDG_STATE_HOME", str(unwritable))
    monkeypatch.setattr(PluginMarketplace, "_can_write_state", staticmethod(lambda _: False))

    marketplace = PluginMarketplace()

    assert marketplace.registry_dir == Path(__file__).resolve().parents[1] / ".beast" / "state" / "plugins"
