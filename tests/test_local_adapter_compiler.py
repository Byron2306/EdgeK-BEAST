"""Experimental Task 2: Local Adapter Compiler (IEI v0.9 §7.12 Table 14) — plan mode, verified data only."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

from app.kernel.compute.coding_crystals import CodingCrystalRegistry
from app.kernel.compute.heldout_replay import ReplayReceipt
from app.kernel.governance.governor_spine import ComputeGovernorSpine
from app.kernel.sensorium.episode_envelope import ENVELOPE_SCHEMA, EpisodeEnvelope, EpisodeEnvelopeStore

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_crystal_lattice_spine import crystal  # noqa: E402

from app.kernel.compute.local_adapter_compiler import COMPILER_ENV, LocalAdapterCompiler  # noqa: E402

FAMILY = "fix-failing-assertion"
ON = {COMPILER_ENV: "1"}


def envelope(run_id: str, *, passed: bool = True, state: str = "completed", family: str = FAMILY) -> EpisodeEnvelope:
    steps = (
        {"index": 0, "tool_id": "workspace.read_range", "status": "completed", "source": "model",
         "arguments_digest": "sha256:" + "a" * 64, "safe_arguments": {"path": "calc.py"},
         "result_digest": "sha256:" + "b" * 64, "returncode": None, "duration_ms": 1.0},
        {"index": 1, "tool_id": "worktree.verify", "status": "completed", "source": "model",
         "arguments_digest": "sha256:" + "c" * 64, "safe_arguments": {},
         "result_digest": "sha256:" + "d" * 64, "returncode": 0 if passed else 1, "duration_ms": 2.0},
    )
    return EpisodeEnvelope(schema=ENVELOPE_SCHEMA, run_id=run_id, origin="agent_run", workspace_digest="sha256:w",
                           objective_digest="sha256:o", task_family=family, mode="agent", provider="simulated",
                           model="scripted", state=state, implementation_target="calc.py", steps=steps,
                           verification={"present": True, "passed": passed, "failures_before_pass": 1,
                                         "final_returncode": 0 if passed else 1, "verify_steps": 1},
                           negative_evidence=(), budget={"model_turns": 2.0}, event_chain_head="h").sealed()


def structured(crystal_id: str) -> ReplayReceipt:
    return ReplayReceipt(crystal_id, 3, 3, True, "held-out replay passed", evidence_root="sha256:" + "e" * 64,
                         structured=True)


@pytest.fixture
def world(tmp_path):
    registry = CodingCrystalRegistry(tmp_path / "registry.sqlite3")
    store = EpisodeEnvelopeStore(tmp_path / "envelopes.sqlite3")
    promoted = crystal("run-p")
    registry.add_candidate(promoted)
    registry.promote(promoted.crystal_id, structured(promoted.crystal_id))
    candidate = crystal("run-c")
    registry.add_candidate(candidate)
    for run_id in ("v1", "v2", "v3"):
        store.put(envelope(run_id))
    store.put(envelope("u1", passed=False))
    store.put(envelope("f1", state="failed"))
    store.put(envelope("other", family="something-else"))
    store.put(envelope("tampered"))
    with sqlite3.connect(store.path) as connection:  # tamper one stored payload after sealing
        row = connection.execute("SELECT payload FROM episode_envelopes WHERE run_id='tampered'").fetchone()
        payload = json.loads(row[0])
        payload["implementation_target"] = "evil.py"
        connection.execute("UPDATE episode_envelopes SET payload=? WHERE run_id='tampered'", (json.dumps(payload),))

    def make(env=ON, models=("qwen3:4b",), governor=None):
        return LocalAdapterCompiler(registry=registry, envelopes=store, out_dir=tmp_path / "adapters",
                                    governor=governor or ComputeGovernorSpine(enforce=True), env=env,
                                    installed_models=lambda: list(models))
    return {"registry": registry, "promoted": promoted, "candidate": candidate, "make": make, "tmp": tmp_path}


def test_flag_default_off(world):
    with pytest.raises(PermissionError, match=COMPILER_ENV):
        world["make"](env={}).compile(world["promoted"].crystal_id)


def test_refuses_unpromoted_and_unstructured_crystals(world, tmp_path):
    with pytest.raises(PermissionError, match="promoted"):
        world["make"]().compile(world["candidate"].crystal_id)
    loose = crystal("run-loose")
    world["registry"].add_candidate(loose)
    world["registry"].promote(loose.crystal_id, ReplayReceipt(loose.crystal_id, 3, 3, True, "ok"))
    with pytest.raises(PermissionError, match="structured"):
        world["make"]().compile(loose.crystal_id)


def test_compiles_plan_package_from_verified_episodes_only(world):
    result = world["make"]().compile(world["promoted"].crystal_id, base_model="qwen3:4b")
    out = Path(result["package_dir"])
    manifest = json.loads((out / "manifest.json").read_text())
    rows = [json.loads(line) for line in (out / "dataset.jsonl").read_text().splitlines()]
    assert sorted(row["run_id"] for row in rows) == ["v1", "v2", "v3"]
    assert manifest["excluded"] == {"unverified": 1, "failed_state": 1, "tampered": 1}
    assert manifest["training_performed"] is False and manifest["mode"] == "plan"
    contract = manifest["runtime_contract"]
    assert contract["adapter_can_execute"] is False and contract["adapter_may_only_propose"] is True
    assert contract["beast_verifiers_decide"] is True
    assert manifest["crystal_id"] == world["promoted"].crystal_id
    assert manifest["governor"]["outcome"] == "admit" and manifest["governor"]["receipt_id"]
    assert manifest["dataset_digest"].startswith("sha256:")
    modelfile = (out / "Modelfile").read_text()
    assert modelfile.startswith("FROM qwen3:4b\n") and "SYSTEM" in modelfile and "PARAMETER temperature 0" in modelfile
    assert "evil.py" not in modelfile + (out / "dataset.jsonl").read_text()
    plan = json.loads((out / "training_plan.json").read_text())
    assert plan["mode"] == "plan" and plan["method"] in {"lora", "ollama_specialist_prompt"}
    assert "peft_available" in plan
    assert result["ollama_create_command"][:2] == ["ollama", "create"]


def test_rejects_random_init_and_uninstalled_bases(world):
    with pytest.raises(ValueError, match="random-init|diagnostic"):
        world["make"](models=("tiny-random-llama",)).compile(world["promoted"].crystal_id,
                                                             base_model="tiny-random-llama")
    with pytest.raises(ValueError, match="not installed"):
        world["make"]().compile(world["promoted"].crystal_id, base_model="llama3:70b")


def test_refuses_when_no_verified_episodes(world, tmp_path):
    registry = world["registry"]
    lonely = crystal("run-x", family="lonely-family")
    registry.add_candidate(lonely)
    registry.promote(lonely.crystal_id, structured(lonely.crystal_id))
    with pytest.raises(PermissionError, match="no verified episodes"):
        world["make"]().compile(lonely.crystal_id)


def test_governor_refusal_blocks_compilation(world):
    class Refuse(ComputeGovernorSpine):
        def admit(self, episode, proposal):
            decision = super().admit(episode, proposal)
            from dataclasses import replace
            return replace(decision, outcome="refuse", reasons=("operator_refused",))

    with pytest.raises(PermissionError):
        world["make"](governor=Refuse(enforce=True)).compile(world["promoted"].crystal_id)
    assert not (world["tmp"] / "adapters").exists() or not any((world["tmp"] / "adapters").rglob("manifest.json"))
