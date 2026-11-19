from __future__ import annotations

import ast
import json
import shutil
import tempfile
from pathlib import Path

from app.kernel.agents.coder_integrations import CoderIntegrationCoordinator
from app.kernel.compute.family_crystals import FamilyCrystal, FamilyRegistry, recipe, catalog_digest


class FakeCompressionRouter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def compress(self, tier: str, payload: str, **_kwargs):
        self.calls.append((tier, payload))
        return {
            "content": f"compressed:{tier}",
            "fidelity": {"passed": True},
            "metrics": {"original_tokens": 100, "compressed_tokens": 25, "counted_savings_tokens": 75},
            "governor": {"outcome": "admit", "receipt_id": f"receipt-{tier}"},
        }


class FakeVectorMemory:
    def search(self, query: str, **_kwargs):
        assert query == "repair the parser"
        return {"hits": [{"id": "safe-hit", "score": 0.9, "content": "must not leak"}], "result_count": 1}


class FakeMemoryHull:
    def __init__(self) -> None:
        self.writes = 0

    def search(self, query: str, **_kwargs):
        assert query == "repair the parser"
        return [{"residue_id": "residue-safe", "decision": "must not leak"}]

    def write_residue(self, **_kwargs):
        self.writes += 1
        return {"residue_id": "residue-sealed", "verified": True, "sidecar_path": "/secret/path"}


from dataclasses import dataclass, asdict

@dataclass
class PromotedReceipt:
    promoted: bool = True
    candidate_id: str = ""
    successes: int = 3


def _coordinator(tmp_path: Path, **overrides) -> CoderIntegrationCoordinator:
    # Create a real promoted family crystal for testing governed replay
    crystal_db = tmp_path / ".beast" / "crystals" / "family_crystals.sqlite3"
    crystal_db.parent.mkdir(parents=True, exist_ok=True)
    registry = FamilyRegistry(crystal_db)
    crystal = FamilyCrystal(
        crystal_id="",
        task_family="fix-logic-operator",
        steps=recipe(["fix-logic-operator"]),
        catalog_digest=catalog_digest(),
        source_run_id="source-run",
        source_envelope_digest="sha256:test",
    ).sealed()
    registry.add_candidate(crystal)
    registry.promote(crystal.crystal_id, PromotedReceipt(candidate_id=crystal.crystal_id), approved_by="test-operator")

    defaults = {
        "workspace": tmp_path,
        "environ": {
            "BEAST_COMPRESSION_TIERS": "1",
            "BEAST_CODING_CRYSTALS": "1",
            "BEAST_CONSOLIDATED_CRYSTAL_BUS": "1",
            "BEAST_SWARM_SPECIALIST": "1",
            "BEAST_FAMILY_CRYSTALS_DB": str(crystal_db),
        },
        "compression_router": FakeCompressionRouter(),
        "vector_memory": FakeVectorMemory(),
        "memory_hull": FakeMemoryHull(),
        "crystal_preflight": lambda **_kwargs: {"action": "execute_local_cpu", "reason": "no_reusable_crystal_found"},
        "crystal_status": lambda **_kwargs: {"enabled": True, "reason": "ready", "promoted": False},
        "bus_probe": lambda **_kwargs: {"eligible": True, "reason": "admitted_capsule_available"},
        "swarm_selector": lambda **_kwargs: {"selected": True, "reason": "local_specialist_proposed"},
        "crystal_producer": lambda **_kwargs: {"status": "verified_awaiting_operator_promotion", "crystal_id": "candidate-safe"},
    }
    defaults.update(overrides)
    return CoderIntegrationCoordinator(**defaults)


def test_preflight_invokes_every_coding_path_and_emits_redacted_normalized_events(tmp_path: Path, monkeypatch) -> None:
    # Mock the family crystal replay to return success for the governed replay test
    import app.kernel.compute.family_crystals as family_crystals_module

    def mock_replay_family(crystal, parameters, root, worktree):
        return {
            "ok": True,
            "trace": [{"opcode": "worktree.verify", "expect": "fail"}, {"opcode": "repair.operator_swap"}, {"opcode": "worktree.verify", "expect": "pass"}],
            "tool_calls": 3,
            "changed": ["service.py"],
            "wall_ms": 100.0,
        }

    monkeypatch.setattr(family_crystals_module, "replay_family", mock_replay_family)

    coordinator = _coordinator(tmp_path)

    result = coordinator.prepare(
        objective="repair the parser",
        source_context="def parse(value):\n    return value\n",
        diagnostic_context="FAILED tests/test_parser.py::test_parse\n" * 8,
        task_metadata={"task_family": "fix-logic-operator"},
    )

    events = {event["payload"]["capability"]: event for event in result["events"]}
    assert {
        "compression.reporelay",
        "compression.longcodezip",
        "compression.rtk",
        "compression.sqz",
        "vector_rag",
        "memory_hull.recall",
        "crystal_reuse",
        "family_crystal",
        "coding_crystal.production",
        "crystal_bus",
        "swarm_specialist",
    } <= set(events)
    assert all(event["event_type"].startswith("agent.integration.") for event in events.values())
    assert all(event["payload"]["status"] in {"fired", "skipped", "failed"} for event in events.values())
    assert events["vector_rag"]["payload"]["metrics"]["hits"] == 1
    assert events["family_crystal"]["payload"]["status"] == "fired"
    assert events["crystal_bus"]["payload"]["mode"] == "transfer_eligible"
    rendered = repr(result)
    assert "must not leak" not in rendered
    assert "/secret/path" not in rendered
    assert "BEAST_CODING_CRYSTAL_KEY" not in rendered


def test_compressed_context_is_returned_for_the_model_packet(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path)
    result = coordinator.prepare(
        objective="repair the parser",
        source_files={"a.py": "def a():\n    return 1\n", "b.py": "def b():\n    return 2\n"},
        diagnostic_context="FAILED test_parser",
    )

    assert result["repo_map"] == "compressed:repo_map"
    assert result["source_files"] == {
        "a.py": "compressed:longcodezip",
        "b.py": "compressed:longcodezip",
    }
    assert result["source_context"] == "compressed:longcodezip\n\ncompressed:longcodezip"
    assert result["diagnostic_context"] == "compressed:sqz"
    events = {event["payload"]["capability"]: event for event in result["events"]}
    assert events["compression.longcodezip"]["payload"]["status"] == "fired"
    assert events["compression.reporelay"]["payload"]["status"] == "fired"


def test_real_native_compression_tiers_bind_output_to_model_packet(tmp_path: Path) -> None:
    from app.context.compression_tiers import CompressionTierRouter
    from app.kernel.governance.governor_spine import ComputeGovernorSpine

    env = {"BEAST_COMPRESSION_TIERS": "1"}
    router = CompressionTierRouter(governor=ComputeGovernorSpine(), env=env)
    coordinator = _coordinator(tmp_path, environ=env, compression_router=router)
    code = (
        "def alpha(value):\n"
        "    return value + 1\n\n\n"
        "def beta(value):\n"
        "    hidden = value * 2\n"
        "    hidden = hidden + 3\n"
        "    return hidden\n"
    )

    result = coordinator.prepare(
        objective="tune alpha arithmetic",
        source_files={"service.py": code},
    )

    transformed = result["source_files"]["service.py"]
    assert transformed != code
    assert "def alpha" in transformed
    assert "def beta" in transformed
    assert "beast-lcz: body elided" in transformed
    ast.parse(transformed)
    events = {event["payload"]["capability"]: event for event in result["events"]}
    assert events["compression.longcodezip"]["payload"]["status"] == "fired"
    assert events["compression.longcodezip"]["payload"]["metrics"]["fidelity_passed"] is True
    assert events["compression.longcodezip"]["payload"]["metrics"]["counted_savings_tokens"] > 0


def test_empty_retrieval_and_recall_do_not_claim_fired(tmp_path: Path) -> None:
    coordinator = _coordinator(
        tmp_path,
        vector_memory=type("EmptyVector", (), {"search": lambda *_a, **_k: {"hits": [], "result_count": 0}})(),
        memory_hull=type("EmptyHull", (), {"search": lambda *_a, **_k: []})(),
    )
    result = coordinator.prepare(objective="repair the parser")
    events = {event["payload"]["capability"]: event for event in result["events"]}

    assert events["vector_rag"]["payload"]["status"] == "skipped"
    assert events["vector_rag"]["payload"]["reason"] == "no_retrieval_hits"
    assert events["memory_hull.recall"]["payload"]["status"] == "skipped"
    assert events["memory_hull.recall"]["payload"]["reason"] == "no_recall_records"


def test_kv_hook_never_claims_metadata_only_or_foreign_engine_reuse(tmp_path: Path) -> None:
    from app.kernel.compute.kv_transport import (
        CacheEngine,
        CacheLocation,
        CrossEngineKVCacheTransport,
        bind_default_transport,
    )

    transport = CrossEngineKVCacheTransport(storage_dir=tmp_path / "kv")
    bind_default_transport(transport)
    block = transport.register_block(
        model="qwen2.5:3b",
        tokenizer="qwen2.5:3b",
        prompt_prefix="repair the parser",
        system_prompt="beast-agent-coder",
        engine=CacheEngine.OLLAMA,
        location=CacheLocation.CPU,
        precision="fp16",
        num_layers=0,
        num_heads=0,
        head_dim=0,
        seq_len=16,
        size_bytes=16,
    )
    coordinator = _coordinator(
        tmp_path,
        environ={"BEAST_ZERO_COPY_KV": "1"},
    )
    metadata = {"provider": "ollama", "model": "qwen2.5:3b"}

    metadata_only = coordinator.prepare(
        objective="repair the parser", task_metadata=metadata
    )
    event = next(e for e in metadata_only["events"] if e["payload"]["capability"] == "kv_transport")
    assert event["payload"]["status"] == "skipped"
    assert event["payload"]["reason"] == "metadata_block_has_no_engine_native_payload"

    transport.import_tensor_payload(block.block_id, b"engine-native-kv")
    reusable = coordinator.prepare(
        objective="repair the parser", task_metadata=metadata
    )
    event = next(e for e in reusable["events"] if e["payload"]["capability"] == "kv_transport")
    assert event["payload"]["status"] == "fired"
    assert event["payload"]["mode"] == "prefix_reuse"

    foreign = coordinator.prepare(
        objective="repair the parser",
        task_metadata={"provider": "tgi", "model": "Qwen/Qwen2.5-Coder-3B"},
    )
    event = next(e for e in foreign["events"] if e["payload"]["capability"] == "kv_transport")
    assert event["payload"]["status"] == "skipped"
    assert event["payload"]["reason"] == "provider_does_not_expose_transportable_kv"


def test_disabled_paths_emit_skipped_events_without_calling_optional_backends(tmp_path: Path) -> None:
    coordinator = _coordinator(
        tmp_path,
        environ={},
        compression_router=None,
        crystal_status=lambda **_kwargs: {"enabled": False, "reason": "disabled"},
        bus_probe=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("bus must not run")),
        swarm_selector=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("swarm must not run")),
    )

    result = coordinator.prepare(objective="repair the parser")
    events = {event["payload"]["capability"]: event for event in result["events"]}

    assert events["compression.tiers"]["event_type"] == "agent.integration.skipped"
    assert events["coding_crystal.production"]["payload"]["reason"] == "disabled"
    assert events["crystal_bus"]["payload"]["reason"] == "feature_flag_disabled"
    assert events["swarm_specialist"]["payload"]["reason"] == "feature_flag_disabled"


def test_failed_optional_backend_is_contained_and_reported(tmp_path: Path) -> None:
    coordinator = _coordinator(
        tmp_path,
        vector_memory=type("BrokenVector", (), {"search": lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("secret backend detail"))})(),
    )

    result = coordinator.prepare(objective="repair the parser")
    vector = next(event for event in result["events"] if event["payload"]["capability"] == "vector_rag")

    assert vector["event_type"] == "agent.integration.failed"
    assert vector["payload"]["reason"] == "RuntimeError"
    assert "secret backend detail" not in repr(vector)


def test_postflight_seals_memory_and_produces_only_an_unpromoted_crystal_candidate(tmp_path: Path) -> None:
    hull = FakeMemoryHull()
    coordinator = _coordinator(tmp_path, memory_hull=hull)

    skipped = coordinator.complete(run_id="run-1", objective="repair the parser", verified=False)
    assert all(event["payload"]["status"] == "skipped" for event in skipped["events"])
    assert hull.writes == 0

    completed = coordinator.complete(run_id="run-1", objective="repair the parser", verified=True)
    events = {event["payload"]["capability"]: event for event in completed["events"]}
    assert events["memory_hull.seal"]["payload"]["status"] == "fired"
    assert events["coding_crystal.production"]["payload"]["status"] == "fired"
    assert events["coding_crystal.production"]["payload"]["mode"] == "verified_awaiting_operator_promotion"
    assert hull.writes == 1


def test_integration_receipts_distinguish_eligibility_from_execution(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path)

    prepared = coordinator.prepare(
        objective="repair the parser",
        source_context="def parse(value): return value",
        diagnostic_context="FAILED test_parser",
    )
    events = {event["payload"]["capability"]: event for event in prepared["events"]}

    bus = events["crystal_bus"]["payload"]
    assert bus["status"] == "fired"
    assert bus["stage"] == "eligibility"
    assert bus["operation"] == "transfer_preflight"
    assert bus["effect_committed"] is False

    crystal = events["coding_crystal.production"]["payload"]
    assert crystal["status"] == "fired"
    assert crystal["stage"] == "eligibility"
    assert crystal["operation"] == "production_readiness"
    assert crystal["effect_committed"] is False

    compression = events["compression.longcodezip"]["payload"]
    assert compression["stage"] == "execution"
    assert compression["effect_committed"] is False


def test_postflight_receipts_distinguish_seal_from_candidate(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path)

    result = coordinator.complete(
        run_id="verified-run",
        objective="repair the parser",
        verified=True,
    )
    events = {event["payload"]["capability"]: event for event in result["events"]}

    seal = events["memory_hull.seal"]["payload"]
    assert seal["stage"] == "postflight"
    assert seal["operation"] == "residue_seal"
    assert seal["effect_committed"] is True

    candidate = events["coding_crystal.production"]["payload"]
    assert candidate["stage"] == "postflight"
    assert candidate["operation"] == "candidate_extraction"
    assert candidate["effect_committed"] is False
