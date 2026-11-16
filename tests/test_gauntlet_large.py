"""Offline pieces of scripts/gauntlet_large.py (no model calls)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("gauntlet_large", ROOT / "scripts" / "gauntlet_large.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


G = _load()


def test_context_files_hide_tests_and_hidden_intent(tmp_path):
    root = G.make_repo(tmp_path, "ren-cold")
    files = G.context_files(root)
    assert "ledger/core.py" in files and "ledger/report.py" in files
    assert not any(Path(p).name.startswith("test_") for p in files)


def test_edits_to_tests_are_refused_and_good_edits_verify(tmp_path):
    root = G.make_repo(tmp_path, "const-cold")
    bad = G.apply_and_verify(root, "const-cold", [{"path": "test_billing_contract.py", "old_text": "5", "new_text": "3"}], tmp_path / "a")
    assert bad["reason"] == "edit_touches_tests" and not bad["passed"]
    good = G.apply_and_verify(root, "const-cold", [{"path": "billing/config.py", "old_text": "INVOICE_RETRY_LIMIT = 3",
                                                     "new_text": "INVOICE_RETRY_LIMIT = 5"}], tmp_path / "b")
    assert good["passed"] and G.hidden_check(tmp_path / "b", "const-cold")["passed"]


def test_hidden_check_catches_visible_only_fix(tmp_path):
    root = G.make_repo(tmp_path, "far-1")
    edit = [{"path": "slugs/core.py", "old_text": "    raise NotImplementedError('slugify')",
             "new_text": "    return text.lower().replace(' ', '-')"}]
    check = G.apply_and_verify(root, "far-1", edit, tmp_path / "w")
    assert check["passed"] is True
    assert G.hidden_check(tmp_path / "w", "far-1")["passed"] is False  # 'A  B c' -> 'a--b-c': a false accept


def test_providers_never_embed_keys_and_reasoning_controls_declared():
    for cfg in G.PROVIDERS.values():
        assert "key" not in str(cfg).lower()
        assert cfg["extra"] and cfg["max_tokens"] >= 2048


def test_apply_and_verify_refuses_degenerate_stub_that_passes_weak_visible_test(tmp_path):
    root = G.make_repo(tmp_path, "exc-cold")
    res = G.apply_and_verify(root, "exc-cold", [{"path": "fracs/core.py", "old_text": "return int(num) / int(den)",
                                                  "new_text": "return None"}], tmp_path / "w")
    assert res["passed"] is False and res["reason"].startswith("degenerate_edit")
