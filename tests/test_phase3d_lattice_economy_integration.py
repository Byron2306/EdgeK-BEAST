from __future__ import annotations

import json
import tempfile
from pathlib import Path

from app.kernel.agents.coder_integrations import CoderIntegrationCoordinator


def test_coder_complete_adds_crystal_to_lattice_and_records_economy(tmp_path: Path, monkeypatch) -> None:
    """Phase 3D: CoderIntegrationCoordinator.complete() should add the crystal to the lattice,
    attempt composite admission, and record economy events."""
    from dataclasses import dataclass, asdict
    from app.kernel.compute.coding_crystals import CodingCrystalRegistry, CodingCrystalCandidate, coding_catalog_digest, CRYSTAL_PARAMETERS
    from app.kernel.compute.crystal_lattice_spine import default_lattice
    from app.kernel.compute.crystal_economy import CrystalShadowLedger, CrystalReuseEconomy
    from app.kernel.sensorium.episode_envelope import EpisodeEnvelopeStore
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    @dataclass
    class PromotedReceipt:
        promoted: bool = True
        candidate_id: str = ""
        successes: int = 3
        attempts: int = 3

    # Create a promoted crystal in the registry
    registry = CodingCrystalRegistry(tmp_path / ".beast" / "crystals" / "coding_crystals.sqlite3")
    candidate = CodingCrystalCandidate(
        crystal_id="",
        task_family="fix-failing-assertion",
        steps=(
            {"opcode": "worktree.inspect", "tool_id": "workspace.read_range", "expect": ""},
            {"opcode": "worktree.bind", "tool_id": "worktree.bind", "expect": ""},
            {"opcode": "worktree.verify", "tool_id": "worktree.verify", "expect": "fail"},
            {"opcode": "repair.resolve_constant", "tool_id": "", "expect": ""},
            {"opcode": "worktree.replace_exact", "tool_id": "worktree.replace_exact", "expect": ""},
            {"opcode": "worktree.verify", "tool_id": "worktree.verify", "expect": "pass"},
            {"opcode": "crystal.complete", "tool_id": "", "expect": ""},
        ),
        parameters=CRYSTAL_PARAMETERS,
        opcode_catalog_digest=coding_catalog_digest(),
        source_run_id="source-run",
        source_envelope_digest="sha256:test",
        learned_budget={"model_turns": 7.0, "tool_calls": 9.0, "tokens_total": 8400.0, "wall_ms": 1100.0},
    ).sealed()

    # Create the coordinator with proper environment
    env = {
        "BEAST_CODING_CRYSTALS": "1",
    }
    coordinator = CoderIntegrationCoordinator(
        workspace=tmp_path,
        environ=env,
        crystal_producer=lambda **kwargs: {"status": "verified_awaiting_operator_promotion", "crystal_id": candidate.crystal_id},
    )

    # Call complete with verified=True
    result = coordinator.complete(
        run_id="test-run-3d",
        objective="Fix the failing assertion",
        verified=True,
    )

    # Verify the events include lattice and economy events
    events = result["events"]
    event_caps = {e["payload"]["capability"] for e in events}
    
    # Should have memory_hull.seal, coding_crystal.production, crystal_lattice, crystal_economy
    assert "memory_hull.seal" in event_caps
    assert "coding_crystal.production" in event_caps
    assert "crystal_lattice" in event_caps
    assert "crystal_economy" in event_caps

    # Verify lattice leaf admission event
    lattice_events = [e for e in events if e["payload"]["capability"] == "crystal_lattice"]
    leaf_events = [e for e in lattice_events if e["payload"]["mode"] == "leaf_admission"]
    assert len(leaf_events) == 1
    assert leaf_events[0]["payload"]["reason"] == "crystal_admitted_to_lattice"
    assert leaf_events[0]["payload"]["artifacts"]["crystal_id"] == candidate.crystal_id

    # Verify economy production recorded event
    economy_events = [e for e in events if e["payload"]["capability"] == "crystal_economy"]
    production_events = [e for e in economy_events if e["payload"]["mode"] == "production_recorded"]
    assert len(production_events) == 1
    assert production_events[0]["payload"]["reason"] == "crystal_production_recorded_in_economy"

    # Verify the crystal was actually added to the lattice
    from app.kernel.compute.crystal_lattice_spine import default_lattice
    lattice = default_lattice(tmp_path, registry)
    lattice_node = lattice.node(candidate.crystal_id)
    assert lattice_node["status"] == "admitted"
    assert lattice_node["publisher_id"] == "agent_coder"
    assert lattice_node["kind"] == "crystal"

    # Verify the shadow ledger has the reproduction entry
    from app.kernel.compute.crystal_economy import CrystalShadowLedger
    ledger = CrystalShadowLedger(
        tmp_path / ".beast" / "crystals" / "shadow_ledger.sqlite3",
        local_node_id="agent_coder",
        local_publisher_id="agent_coder"
    )
    entries = ledger.entries(crystal_id=candidate.crystal_id)
    reproduction_entries = [e for e in entries if e["kind"] == "reproduction"]
    assert len(reproduction_entries) >= 1
    assert reproduction_entries[0]["reason"] == "reproduction_evidence_only"
    assert reproduction_entries[0]["units"] == 0.0


def test_coder_complete_records_lattice_composite_attempt(tmp_path: Path) -> None:
    """Phase 3D: When multiple crystals of same family exist, complete() should attempt composite admission."""
    from dataclasses import dataclass
    from app.kernel.compute.coding_crystals import CodingCrystalRegistry, CodingCrystalCandidate, coding_catalog_digest, CRYSTAL_PARAMETERS
    from app.kernel.compute.crystal_lattice_spine import default_lattice

    @dataclass
    class PromotedReceipt:
        promoted: bool = True
        candidate_id: str = ""
        successes: int = 3
        attempts: int = 3

    registry = CodingCrystalRegistry(tmp_path / ".beast" / "crystals" / "coding_crystals.sqlite3")

    # Create two promoted crystals of the same family
    candidates = []
    for i in range(2):
        candidate = CodingCrystalCandidate(
            crystal_id="",
            task_family="fix-failing-assertion",
            steps=(
                {"opcode": "worktree.inspect", "tool_id": "workspace.read_range", "expect": ""},
                {"opcode": "worktree.bind", "tool_id": "worktree.bind", "expect": ""},
                {"opcode": "worktree.verify", "tool_id": "worktree.verify", "expect": "fail"},
                {"opcode": "repair.resolve_constant", "tool_id": "", "expect": ""},
                {"opcode": "worktree.replace_exact", "tool_id": "worktree.replace_exact", "expect": ""},
                {"opcode": "worktree.verify", "tool_id": "worktree.verify", "expect": "pass"},
                {"opcode": "crystal.complete", "tool_id": "", "expect": ""},
            ),
            parameters=CRYSTAL_PARAMETERS,
            opcode_catalog_digest=coding_catalog_digest(),
            source_run_id=f"source-run-{i}",
            source_envelope_digest="sha256:test",
            learned_budget={"model_turns": 7.0, "tool_calls": 9.0, "tokens_total": 8400.0, "wall_ms": 1100.0},
        ).sealed()
        registry.add_candidate(candidate)
        registry.promote(candidate.crystal_id, type("Receipt", (), {"promoted": True, "candidate_id": candidate.crystal_id, "successes": 3, "attempts": 3})())
        candidates.append(candidate)

    env = {"BEAST_CODING_CRYSTALS": "1"}
    coordinator = CoderIntegrationCoordinator(workspace=tmp_path, environ=env)

    def mock_crystal_producer(**kwargs):
        return {"status": "verified_awaiting_operator_promotion", "crystal_id": candidates[1].crystal_id}

    result = coordinator.complete(
        run_id="test-run-composite",
        objective="Fix two assertions",
        verified=True,
        crystal_producer=mock_crystal_producer,
    )

    events = result["events"]
    lattice_events = [e for e in events if e["payload"]["capability"] == "crystal_lattice"]
    
    # Should have leaf admission for the new crystal
    leaf_events = [e for e in lattice_events if e["payload"]["mode"] == "leaf_admission"]
    assert len(leaf_events) >= 1

    # Should attempt composite admission
    composite_events = [e for e in lattice_events if e["payload"]["mode"] == "composite_admission"]
    assert len(composite_events) >= 1
    # The composite admission may succeed or be skipped (depending on verifier), but the attempt is recorded
    composite_event = composite_events[0]
    assert composite_event["payload"]["mode"] == "composite_admission"
    assert "composite_id" in composite_event["payload"]["artifacts"]


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])