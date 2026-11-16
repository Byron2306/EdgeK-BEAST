from __future__ import annotations

from pathlib import Path

from app.kernel.agents.coder_integrations import CoderIntegrationCoordinator


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


def _coordinator(tmp_path: Path, **overrides) -> CoderIntegrationCoordinator:
    defaults = {
        "workspace": tmp_path,
        "environ": {
            "BEAST_COMPRESSION_TIERS": "1",
            "BEAST_CODING_CRYSTALS": "1",
            "BEAST_CONSOLIDATED_CRYSTAL_BUS": "1",
            "BEAST_SWARM_SPECIALIST": "1",
        },
        "compression_router": FakeCompressionRouter(),
        "vector_memory": FakeVectorMemory(),
        "memory_hull": FakeMemoryHull(),
        "crystal_preflight": lambda **_kwargs: {"action": "execute_local_cpu", "reason": "no_reusable_crystal_found"},
        "family_lookup": lambda **_kwargs: {"crystal_id": "family-safe", "task_family": "fix-logic-operator"},
        "crystal_status": lambda **_kwargs: {"enabled": True, "reason": "ready", "promoted": False},
        "bus_probe": lambda **_kwargs: {"eligible": True, "reason": "admitted_capsule_available"},
        "swarm_selector": lambda **_kwargs: {"selected": True, "reason": "local_specialist_proposed"},
        "crystal_producer": lambda **_kwargs: {"status": "verified_awaiting_operator_promotion", "crystal_id": "candidate-safe"},
    }
    defaults.update(overrides)
    return CoderIntegrationCoordinator(**defaults)


def test_preflight_invokes_every_coding_path_and_emits_redacted_normalized_events(tmp_path: Path) -> None:
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
