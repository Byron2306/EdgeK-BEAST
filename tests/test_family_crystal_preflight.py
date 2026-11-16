"""IDE crystal-reuse preflight should hit a promoted family (rename) crystal."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from app.kernel.compute.crystal_reuse_gateway import CrystalReuseGateway, CrystalReuseRequest
from app.kernel.compute.family_crystals import infer_task_family, lookup_promoted_family_crystal
from app.kernel.security.residue_seal import ResidueSeal
from app.kernel.storage.durable_inference_storage import DurableInferenceStorage


RENAME_ID = "family-crystal:a54695a14f648efdd70f6620"
RENAME_FAMILY = "refactor-rename-symbol"


def _make_db(tmp_path: Path, crystal_id: str = RENAME_ID, family: str = RENAME_FAMILY) -> Path:
    path = tmp_path / "family_crystals.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE family_crystals (crystal_id TEXT PRIMARY KEY, task_family TEXT NOT NULL,"
        " status TEXT NOT NULL, payload TEXT NOT NULL, record_digest TEXT NOT NULL, updated_at REAL NOT NULL)"
    )
    payload = json.dumps({"crystal_id": crystal_id, "task_family": family, "status": "promoted"})
    conn.execute(
        "INSERT INTO family_crystals VALUES (?,?,?,?,?,?)",
        (crystal_id, family, "promoted", payload, "sha256:test", time.time()),
    )
    conn.commit()
    conn.close()
    return path


def test_infer_task_family_rename_prompt():
    assert infer_task_family("Rename greet to say_hello in src/hello.py") == RENAME_FAMILY
    assert infer_task_family("what does increment() do?") == "chat_completion"
    assert infer_task_family("please help", {"tool": "code.rename_symbol"}) == RENAME_FAMILY
    assert infer_task_family("chat", {"family": RENAME_FAMILY}, "chat_completion") == RENAME_FAMILY
    assert infer_task_family("chat", {}, "ide_coding_completion") == "ide_coding_completion"


def test_lookup_promoted_rename_from_env_db(tmp_path, monkeypatch):
    db = _make_db(tmp_path)
    before = db.stat().st_mtime
    monkeypatch.setenv("BEAST_FAMILY_CRYSTALS_DB", str(db))
    hit = lookup_promoted_family_crystal(RENAME_FAMILY)
    assert hit is not None
    assert hit["crystal_id"] == RENAME_ID
    assert hit["tool"] == "code.rename_symbol"
    assert hit["status"] == "promoted"
    assert db.stat().st_mtime == before


def test_decide_hits_promoted_rename_crystal(tmp_path, monkeypatch):
    db = _make_db(tmp_path)
    monkeypatch.setenv("BEAST_FAMILY_CRYSTALS_DB", str(db))
    gateway = CrystalReuseGateway(
        storage=DurableInferenceStorage(tmp_path / "durable"),
        seal=ResidueSeal(tmp_path / "keys"),
    )
    decision = gateway.decide(
        CrystalReuseRequest(
            prompt="Rename the function greet to say_hello in src/hello.py using code.rename_symbol.",
            model="accounts/fireworks/models/glm-5p3-flash",
            task_class=RENAME_FAMILY,
            provider="fireworks",
        ),
        seal_decision=False,
    )
    assert decision.action == "reuse_family_crystal"
    assert decision.reason == "promoted_family_crystal_hit"
    assert decision.payload["family_crystal"]["crystal_id"] == RENAME_ID
    assert decision.payload["family_crystal"]["tool"] == "code.rename_symbol"
    # Must not look like a cached answer that would skip the provider with stale text.
    assert decision.payload.get("reuse") is None


def test_decide_rename_prompt_without_explicit_family(tmp_path, monkeypatch):
    db = _make_db(tmp_path)
    monkeypatch.setenv("BEAST_FAMILY_CRYSTALS_DB", str(db))
    gateway = CrystalReuseGateway(
        storage=DurableInferenceStorage(tmp_path / "durable"),
        seal=ResidueSeal(tmp_path / "keys"),
    )
    decision = gateway.decide(
        CrystalReuseRequest(
            prompt="Rename greet to say_hello in hello.py",
            model="local",
            task_class="ide_coding_completion",
        ),
        seal_decision=False,
    )
    assert decision.action == "reuse_family_crystal"
    assert decision.payload["family_crystal"]["crystal_id"] == RENAME_ID


def test_decide_plain_chat_does_not_claim_rename_crystal(tmp_path, monkeypatch):
    db = _make_db(tmp_path)
    monkeypatch.setenv("BEAST_FAMILY_CRYSTALS_DB", str(db))
    gateway = CrystalReuseGateway(
        storage=DurableInferenceStorage(tmp_path / "durable"),
        seal=ResidueSeal(tmp_path / "keys"),
    )
    decision = gateway.decide(
        CrystalReuseRequest(prompt="In one sentence, what does increment() do?", model="local"),
        seal_decision=False,
    )
    assert decision.action == "execute_local_cpu"
    assert decision.reason == "no_reusable_crystal_found"


def test_exact_cached_answer_still_wins(tmp_path, monkeypatch):
    db = _make_db(tmp_path)
    monkeypatch.setenv("BEAST_FAMILY_CRYSTALS_DB", str(db))
    storage = DurableInferenceStorage(tmp_path / "durable")
    gateway = CrystalReuseGateway(storage=storage, seal=ResidueSeal(tmp_path / "keys"))
    request = CrystalReuseRequest(prompt="same prompt", model="local", parameters={"temperature": 0})
    storage.store_answer(request.prompt_hash, request.model, request.parameters, "cached answer")
    decision = gateway.decide(request, seal_decision=False)
    assert decision.action == "reuse_answer"
    assert decision.payload["reuse"]["payload"]["response"] == "cached answer"


def test_default_store_includes_promoted_closure_rename_crystal():
    """If the closure gauntlet registry is on disk, default discovery should see it."""
    root = Path(__file__).resolve().parents[1] / ".beast" / "gauntlets" / "2026-11-16-closure" / "family_crystals.sqlite3"
    if not root.is_file():
        return
    hit = lookup_promoted_family_crystal(RENAME_FAMILY)
    assert hit is not None
    assert hit["crystal_id"] == RENAME_ID
