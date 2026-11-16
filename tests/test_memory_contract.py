"""Governor spine 4-tier memory contract: cheapest-first Perceive reader, verified-only Crystallize writer."""

from __future__ import annotations

import pytest

from app.kernel.governance.governor_spine import ADMIT, ComputeGovernorSpine, Episode, GovernorReceiptLog, Proposal
from app.kernel.governance.memory_contract import (
    TIERS,
    MemoryContractError,
    MemoryHit,
    MemoryReader,
    MemoryWriter,
    assert_local_vector_backend,
    privacy_filter,
)


def tier(name, calls, hits=()):
    def source(query):
        calls.append(name)
        return [MemoryHit(tier=name.split(":")[0], source=name, key=f"{name}:{i}", payload=h) for i, h in
                enumerate(hits)]
    return source


def reader(calls, *, exact=(), schema=(), graph=(), vector=()):
    return MemoryReader(exact=[tier("exact:pages", calls, exact)], schema=[tier("schema:ast", calls, schema)],
                        graph=[tier("graph:l2", calls, graph)], vector=[tier("vector:chroma", calls, vector)])


def test_tiers_are_declared_cheapest_first():
    assert TIERS == ("exact", "schema", "graph", "vector")


def test_reader_goes_cheapest_first_and_vector_last():
    calls = []
    result = reader(calls, schema=[{"symbol": "f"}], graph=[{"node": "n"}], vector=[{"doc": "d"}]).read("q")
    assert calls == ["exact:pages", "schema:ast", "graph:l2", "vector:chroma"]
    assert [h.tier for h in result.hits] == ["schema", "graph", "vector"]
    assert result.trace[-1]["tier"] == "vector"


def test_verified_exact_hit_short_circuits_more_expensive_tiers():
    calls = []
    result = reader(calls, exact=[{"crystal_id": "c1", "verified": True}], vector=[{"doc": "d"}]).read("q")
    assert calls == ["exact:pages"]
    assert result.admission_inputs()["memory_exact"][0]["key"] == "exact:pages:0"


def test_vector_and_schema_hits_never_grant_or_admit():
    calls = []
    result = reader(calls, schema=[{"symbol": "f", "verified": True}], vector=[{"doc": "d", "verified": True}]).read("q")
    assert all(not h.grants for h in result.hits)
    assert result.admission_inputs()["memory_exact"] == []
    assert {n["tier"] for n in result.admission_inputs()["memory_nominations"]} == {"schema", "vector"}
    assert all(n["grants"] is False for n in result.task_envelope_fields()["memory_nominations"])


def test_forged_vector_grant_cannot_be_constructed():
    with pytest.raises(MemoryContractError):
        MemoryHit(tier="vector", source="chroma", key="k", payload={}, grants=True)


def test_governor_refuses_proposal_claiming_grant_from_nomination(tmp_path):
    spine = ComputeGovernorSpine(receipts=GovernorReceiptLog(tmp_path / "r.jsonl"), enforce=True)
    forged = {"memory_exact": [], "memory_nominations": [{"tier": "vector", "key": "k", "grants": True}]}
    decision = spine.admit(Episode(run_id="r"), Proposal(kind="deterministic_tool", tool_id="t", memory=forged))
    assert decision.outcome != ADMIT and "l0:memory_nomination_cannot_grant" in decision.reasons
    calls = []
    honest = reader(calls, vector=[{"doc": "d"}]).read("q").admission_inputs()
    ok = spine.admit(Episode(run_id="r2"), Proposal(kind="deterministic_tool", tool_id="t", memory=honest))
    assert ok.outcome == ADMIT


def test_a_failing_tier_is_recorded_and_does_not_break_the_read():
    def broken(query):
        raise RuntimeError("down")

    result = MemoryReader(exact=[broken], vector=[lambda q: []]).read("q")
    assert result.trace[0]["error"] == "RuntimeError"


class Sink:
    def __init__(self, local=True):
        self.local, self.items = local, []

    def __call__(self, item):
        self.items.append(item)


def sinks(**overrides):
    names = ("pages", "graph", "embeddings", "skills", "receipts", "lattice")
    out = {name: Sink() for name in names}
    out.update(overrides)
    return out


EPISODE = {"exact_residue": [{"page": "p1"}], "structure": [{"node": "n1"}], "embeddings": [{"text": "def f(): pass"}],
           "skills": [{"skill": "s"}], "receipts": [{"receipt": "r"}], "composites": [{"lattice": "L"}]}
VERIFIED = {"verifier_passed": True, "quality_passed": True, "heldout_passed": True, "episode_digest": "sha256:e"}


@pytest.mark.parametrize("missing", ["verifier_passed", "quality_passed", "heldout_passed"])
def test_no_writes_before_verification(missing):
    targets = sinks()
    with pytest.raises(MemoryContractError, match="crystallize_requires_verified_episode"):
        MemoryWriter(**targets).crystallize(EPISODE, {**VERIFIED, missing: False})
    assert all(not sink.items for sink in targets.values())


def test_verified_episode_writes_each_matching_tier():
    targets = sinks()
    receipt = MemoryWriter(**targets).crystallize(EPISODE, VERIFIED)
    assert {k: len(v.items) for k, v in targets.items()} == dict.fromkeys(targets, 1)
    assert receipt["episode_digest"] == "sha256:e" and receipt["written"]["embeddings"] == 1


def test_privacy_filter_blocks_secrets_and_private_items_from_embeddings():
    secret = {"text": "api_key = sk-" + "a" * 40}
    private = {"text": "ok", "private": True}
    kept, dropped = privacy_filter([secret, private, {"text": "def f(): pass"}])
    assert kept == [{"text": "def f(): pass"}] and dropped == 2
    targets = sinks()
    MemoryWriter(**targets).crystallize({**EPISODE, "embeddings": [secret, {"text": "fine"}]}, VERIFIED)
    assert targets["embeddings"].items == [{"text": "fine"}]


def test_embeddings_never_go_to_a_non_local_backend():
    with pytest.raises(MemoryContractError, match="embedding_sink_must_be_local"):
        MemoryWriter(**sinks(embeddings=Sink(local=False)))
    for env in ({"CHROMA_API_KEY": "x"}, {"QDRANT_URL": "https://q"}, {"BEAST_VECTOR_BACKEND": "pgvector"}):
        with pytest.raises(MemoryContractError, match="remote_vector_backend_refused"):
            assert_local_vector_backend(env)
    assert_local_vector_backend({})


def test_default_graph_tier_reads_workspace_graph(tmp_path):
    from app.kernel.data_processing.workspace_graph import WorkspaceGraph
    from app.kernel.governance.memory_contract import graph_source

    graph = WorkspaceGraph(db_path=str(tmp_path / "wg.db"))
    graph.upsert_node("file:a.py", "file", "a.py", {"path": "a.py"}, "2026-11-16T00:00:00Z")
    hits = graph_source(graph)("a.py")
    assert hits and hits[0].tier == "graph" and hits[0].grants is False
