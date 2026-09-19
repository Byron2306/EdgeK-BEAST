from types import SimpleNamespace

from app.kernel.agents.memory_runtime import AgentMemoryRuntime, render_memory_context


class Hull:
    def search(self, query, limit=4):
        return [{"residue_id": "r1", "task": query}]


class Graph:
    def search_nodes(self, query, limit=4):
        return [{"id": "node:1", "label": query}]


class Skills:
    def list_skills(self, limit=4):
        return [{"skill_id": "s1", "name": "verified repair", "category": "meta_tool"}]


class Bus:
    def query(self, **kwargs):
        return {"receipts": [{"receipt_id": "e1", "artifact_path": "proof.json"}]}

    def related(self, *args, **kwargs):
        return {"receipts": []}


class Forensics:
    def query(self, query="", limit=4):
        return {"results": [{"event_id": "f1", "summary": "prior failed attempt"}]}


def runtime():
    item = AgentMemoryRuntime.__new__(AgentMemoryRuntime)
    item.memory_hull = Hull()
    item.workspace_graph = Graph()
    item.skill_tree = Skills()
    item.evidence_bus = Bus()
    item.forensic_memory = Forensics()
    return item


def test_existing_memory_organs_feed_one_bounded_projection_without_authority_escalation():
    state = SimpleNamespace(
        run_id="resume-1",
        observations=[{"tool_id": "worktree.verify", "status": "failed", "evidence_digest": "sha256:v"}],
    )
    packet = runtime().project({"run_id": "resume-1", "objective": "repair planner"}, state, limit=2)

    assert packet["episodic"][0]["residue_id"] == "r1"
    assert packet["durable"][0]["id"] == "node:1"
    assert packet["evidence"][0]["receipt_id"] == "e1"
    assert packet["forensic"][0]["event_id"] == "f1"
    for role in ("episodic", "durable", "evidence", "forensic"):
        assert all(item["grants_mutation_authority"] is False for item in packet[role])
        assert all(item["grants_exact_source_authority"] is False for item in packet[role])


def test_resume_working_memory_is_rebuilt_from_durable_planner_state():
    state = SimpleNamespace(
        run_id="resume-2",
        observations=[
            {"tool_id": "workspace.read_range", "status": "completed", "evidence_digest": "sha256:a"},
            {"tool_id": "worktree.bind", "status": "completed", "evidence_digest": "sha256:b"},
        ],
    )
    packet = runtime().project({"run_id": "resume-2", "objective": "continue"}, state, limit=4)
    assert [item["tool_id"] for item in packet["working"]["items"]] == ["workspace.read_range", "worktree.bind"]
    assert packet["working"]["authority"] == "advisory_continuity_only"


def test_compacted_memory_context_preserves_authority_boundary():
    state = SimpleNamespace(run_id="x", observations=[])
    packet = runtime().project({"run_id": "x", "objective": "x"}, state, limit=2)
    rendered = render_memory_context(packet, char_limit=700)
    assert "MEMORY_CONTEXT:" in rendered
    assert "promotion_boundary" in rendered
    assert "memory_contract_digest" in rendered
