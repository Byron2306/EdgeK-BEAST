"""Offline tests for scripts/gauntlet_memfd_replay.py (no live models, no network)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("gauntlet_memfd_replay", ROOT / "scripts" / "gauntlet_memfd_replay.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_matcher_bands_are_deterministic(tmp_path):
    g = _load()
    expect = {"warm-ingest": 1.0, "warm-notify": 1.0, "near-miss-pricing": 0.88, "far-parser": 0.38}
    for name, score in expect.items():
        root = g.make_repo(tmp_path, name)
        first = g.match(root, g.TASKS[name])
        assert first["similarity"] == score, name
        assert g.match(root, g.TASKS[name])["similarity"] == first["similarity"]


def test_make_repo_label_isolates_dirs(tmp_path):
    g = _load()
    a = g.make_repo(tmp_path, "warm-ingest", label="warm-ingest-a")
    b = g.make_repo(tmp_path, "warm-ingest", label="warm-ingest-b")
    assert a != b and a.exists() and b.exists()


def test_parse_edit_requires_json_and_strips_think():
    g = _load()
    assert g.parse_edit('<think>x {"old_text": 1}</think>{"old_text": "A = 1", "new_text": "A = 2"}') == {
        "old_text": "A = 1", "new_text": "A = 2"}
    assert g.parse_edit("Okay, let's see. Change 0.14 to 0.15.") is None
    assert g.parse_edit('{"old_text": "A = 1"}') is None


def test_flags_are_not_set_at_import():
    import os
    _load()
    assert os.environ.get("BEAST_CRYSTAL_CAPSULE") in (None, "", "0")
