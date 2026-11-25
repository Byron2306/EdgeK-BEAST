"""Paired acceptance probes. Run explicitly via run_integration_gauntlets.py."""
from __future__ import annotations

import json
from pathlib import Path

from app.kernel.agents.coder_integrations import CoderIntegrationCoordinator
from app.kernel.compute.adaptive_router import CodingCrystalRouter
from app.kernel.security.residue_seal import ResidueSeal
from app.kernel.storage.memory_hull import MemoryHull
from tests.test_crystal_lattice_spine import _admitted, spine  # pytest fixture


def emit(case: str, **result) -> None:
    print("GAUNTLET_EVIDENCE " + json.dumps({"case": case, **result}, sort_keys=True))


def test_flat_vs_lattice_nomination_on_same_registry(spine):
    composite, _, _ = _admitted(spine)
    flat = CodingCrystalRouter(spine["registry"], None, require_source_envelope=False)
    graph = CodingCrystalRouter(spine["registry"], None, lattice=spine["lattice"], require_source_envelope=False)
    rows = []
    for case, fields in (
        ("leaf", {"task_family": "fix-failing-assertion"}),
        ("composite", {"task_family": "fix-two-assertions"}),
        ("near_match", {"task_family": "fix-two-assertions", "route_similarity": 0.9}),
        ("unrelated", {"task_family": "unrelated-fixture"}),
    ):
        request = {"request": fields}
        a, b = flat.route_run(request), graph.route_run(request)
        rows.append({"case": case, "flat": a.route.value, "lattice": b.route.value,
                     "same_candidate": a.crystal_id == b.crystal_id,
                     "flat_composite": a.crystal_id == composite.crystal_id,
                     "lattice_composite": b.crystal_id == composite.crystal_id})
    emit("same_registry_nomination", rows=rows,
         extra_lattice_replay_nominations=sum(row["flat"] != "crystal_replay" and row["lattice"] == "crystal_replay"
                                               for row in rows),
         executed=False)
    assert rows[1]["lattice_composite"]
    assert all(row["flat"] == row["lattice"] == "provider_fallback" for row in rows[2:])


def test_memory_hull_empty_seed_tamper_recall(tmp_path):
    hull = MemoryHull(tmp_path / "vault", seal=ResidueSeal(tmp_path / "keys"))
    coordinator = CoderIntegrationCoordinator(tmp_path, environ={}, memory_hull=hull)
    query = "gauntlet-amber-fact"

    def recall():
        coordinator.advisory_context.clear()
        event = coordinator._memory_recall_events(query)[0]["payload"]
        return event["status"], len(coordinator.advisory_context)

    empty = recall()
    residue = hull.write_residue(task=query, decision="Synthetic answer: amber marker 47.",
                                 evidence={"source": "disposable proof fixture"})
    clean = recall()
    assert coordinator.advisory_context[0]["content"] == "Synthetic answer: amber marker 47."
    markdown, sidecar = Path(residue["markdown_path"]), Path(residue["sidecar_path"])
    markdown.write_text("# Tampered, without resealing\n", encoding="utf-8")
    verified = hull.verify_sidecar(sidecar)["verified"]
    tampered = recall()
    hull.rebuild_index()
    rebuilt = recall()
    emit("memory_hull_recall_controls", empty=empty, intact=clean, tampered=tampered,
         tampered_after_index_rebuild=rebuilt, tampered_sidecar_verified=verified)
    assert empty == ("skipped", 0) and clean == ("fired", 1) and not verified
    assert tampered[1] == rebuilt[1] == 0, "Unverified residue still reached the Coder advisory context."


def test_focused_ask_provider_packet_compression_toggle(tmp_path):
    from app.context.compression_tiers import CompressionTierRouter
    from app.kernel.governance.governor_spine import ComputeGovernorSpine, GovernorReceiptLog
    from app.kernel.agents.file_review import ReviewEvidence
    from app.kernel.agents.planner_provider import CallbackPlannerProvider
    from app.kernel.agents.planner_runtime import AgentPlannerRuntime
    from app.kernel.agents.run_engine import AgentRunEngine

    import asyncio

    async def arm(enabled):
        root = tmp_path / enabled
        root.mkdir()
        path = "demo.py"
        source = "def sample():\n    return 47\n"
        (root / path).write_text(source, encoding="utf-8")
        engine = AgentRunEngine(root)
        run = engine.create_run(
            session_id="gauntlet", objective="Explain sample in demo.py.", mode="analysis",
            provider="fixture", model="same-fixture",
            request={"context_files": [path], "file_answer_style": "explain", "read_only_file_review": True},
        )
        prompts = []

        async def answer(prompt, *_):
            prompts.append(prompt)
            return {"decision_type": "complete", "summary": "Source explanation",
                    "arguments": {"points": [{"ref": "S1L2", "text": "It returns 47."}]}}
        # Explicitly trigger preflight after the source read on a separate turn.
        from app.kernel.agents.planner_models import PlannerState

        flags = {"BEAST_COMPRESSION_TIERS": enabled}
        router = CompressionTierRouter(
            env=flags,
            governor=ComputeGovernorSpine(receipts=GovernorReceiptLog(root / "compression-receipts.jsonl")),
        )
        coordinator = CoderIntegrationCoordinator(root, environ=flags, compression_router=router)
        runtime = AgentPlannerRuntime(engine, CallbackPlannerProvider(answer), integration_coordinator=coordinator)
        run_id = run["run_id"]
        state = PlannerState(run_id=run_id)
        state.observations = [{"status": "completed", "tool_id": "workspace.read_range", "arguments": {"path": path},
                               "result": {"path": path, "content": source}}]
        evidence = ReviewEvidence(
            "", {path: {1, 2}}, {path: 2}, None,
            source_lines={path: {1: "def sample():", 2: "    return 47"}}, symbol_focused=True)
        await runtime._prepare_coder_integrations(run, state)
        result = await runtime._finish_file_review(engine.store.get_run(run_id), state, evidence)
        assert result["state"] == "completed" and len(prompts) == 1
        events = engine.store.events(run_id)
        fired = [e["payload"]["capability"] for e in events if e["event_type"] == "agent.integration.fired"
                 and e["payload"].get("capability", "").startswith("compression.")]
        return prompts[0], fired

    off_prompt, off_tiers = asyncio.run(arm("0"))
    on_prompt, on_tiers = asyncio.run(arm("1"))
    assert not off_tiers and on_tiers, "The on arm did not exercise a compression tier."
    assert off_prompt == on_prompt and "S1L2 |     return 47" in on_prompt
    emit("focused_ask_packet_control", off_bytes=len(off_prompt.encode()), on_bytes=len(on_prompt.encode()),
         packets_identical=True, tiers_fired_on=on_tiers, measurement="fixture_provider_handoff_bytes")
