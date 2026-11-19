from pathlib import Path


def test_ui_entrypoint_defaults_to_conversation_coder(monkeypatch, tmp_path: Path):
    from app.cli import coder, ui

    calls = []
    monkeypatch.setattr(coder, "run", lambda **kwargs: calls.append(kwargs))

    ui.run(workspace=tmp_path)

    assert calls == [{"workspace": tmp_path, "base_url": None}]


def test_ui_entrypoint_preserves_explicit_classic_console(monkeypatch):
    from app.cli import ui

    calls = []
    monkeypatch.setattr(ui.BeastMissionConsole, "run", lambda self: calls.append("classic"))

    ui.run(classic=True)

    assert calls == ["classic"]
