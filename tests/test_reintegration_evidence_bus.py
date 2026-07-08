import json
from pathlib import Path

from app.cli.api import BeastApiClient
from app.kernel.compute.agent_scheduler import AgentScheduler
from app.kernel.evidence.evidence_bus import EvidenceBus
from app.kernel.workspaces.mission_cockpit import MissionCockpit
from app.mcp.runtime import BeastToolRuntime


COMPAT_SHIMS = [
    Path("app/kernel/task_envelope.py"),
    Path("app/kernel/ollama_scout.py"),
    Path("app/kernel/commons_spaces.py"),
    Path("app/kernel/canon_registry.py"),
    Path("app/kernel/forensic_memory.py"),
    Path("app/kernel/insight_compiler.py"),
    Path("app/kernel/beast_cli_executor.py"),
]


def _hash_text(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def test_compatibility_shims_are_marked():
    for path in COMPAT_SHIMS:
        text = path.read_text(encoding="utf-8")
        assert "DEPRECATED_COMPAT_IMPORT" in text


def test_new_code_does_not_import_deprecated_kernel_shims():
    shim_modules = {
        "app.kernel.task_envelope",
        "app.kernel.ollama_scout",
        "app.kernel.commons_spaces",
        "app.kernel.canon_registry",
        "app.kernel.forensic_memory",
        "app.kernel.insight_compiler",
        "app.kernel.beast_cli_executor",
    }
    ignored = {path.resolve() for path in COMPAT_SHIMS}
    offenders = []
    for root in (Path("app"), Path("tests")):
        for path in root.rglob("*.py"):
            if path.resolve() in ignored:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for module in shim_modules:
                if f"from {module} import" in text or f"import {module}" in text:
                    offenders.append(f"{path}:{module}")

    assert offenders == []


def test_evidence_bus_registers_sourceplan_packet(tmp_path):
    target = tmp_path / "app.py"
    original = "value = 1\n"
    target.write_text(original, encoding="utf-8")
    client = BeastApiClient("http://offline", workspace=tmp_path)
    plan = {
        "plan_id": "bus_success",
        "objective": "Update value",
        "provider": "local",
        "files_allowed": ["app.py"],
        "operations": [{
            "op_id": "op_001",
            "op": "replace_exact",
            "path": "app.py",
            "old": "value = 1",
            "new": "value = 2",
            "expected_hash": _hash_text(original),
            "selected": True,
            "source_edit": True,
        }],
    }

    result = client.apply_patch_plan(plan, approved=True)
    packet = json.loads((tmp_path / ".beast/evidence/sourceplan/bus_success.json").read_text(encoding="utf-8"))
    summary = EvidenceBus(tmp_path).summary()

    assert result.ok is True
    assert packet["evidence_bus"]["beast_object_type"] == "beast_evidence_bus_receipt"
    assert packet["evidence_bus"]["artifact_type"] == "sourceplan_unified_evidence_packet"
    assert summary["by_type"]["sourceplan_unified_evidence_packet"] == 1
    assert summary["by_type"]["beast_agent_scheduler_receipt"] == 1
    assert any(item["task_id"] == "bus_success" for item in summary["recent"])


def test_evidence_bus_registers_negative_sourceplan_packet(tmp_path):
    target = tmp_path / "app.py"
    original = "value = 1\n"
    target.write_text(original, encoding="utf-8")
    client = BeastApiClient("http://offline", workspace=tmp_path)
    plan = {
        "plan_id": "bus_negative",
        "objective": "Update stale value",
        "provider": "local",
        "files_allowed": ["app.py"],
        "operations": [{
            "op_id": "op_001",
            "op": "replace_exact",
            "path": "app.py",
            "old": "value = 1",
            "new": "value = 2",
            "expected_hash": _hash_text(original),
            "selected": True,
            "source_edit": True,
        }],
    }
    target.write_text("value = 10\n", encoding="utf-8")

    result = client.apply_patch_plan(plan, approved=True)
    packet = json.loads((tmp_path / ".beast/evidence/sourceplan/bus_negative.negative.json").read_text(encoding="utf-8"))
    summary = EvidenceBus(tmp_path).summary()

    assert result.ok is False
    assert packet["evidence_bus"]["artifact_type"] == "sourceplan_negative_evidence_packet"
    assert summary["by_status"]["negative"] == 1


def test_evidence_bus_registers_agent_scheduler_receipt(tmp_path):
    scheduler = AgentScheduler(tmp_path)
    plan = scheduler.plan(objective="Review reintegration state", phase="reviewer", risk="medium")
    summary = EvidenceBus(tmp_path).summary()

    assert summary["receipt_count"] == 1
    assert summary["by_type"]["beast_agent_scheduler_receipt"] == 1
    assert summary["by_source"]["agent_scheduler"] == 1
    assert summary["recent"][0]["task_id"] == plan["receipt"]["route_id"]


def test_mission_cockpit_includes_evidence_bus_summary(tmp_path):
    bus = EvidenceBus(tmp_path)
    bus.register(
        artifact_type="sourceplan_unified_evidence_packet",
        artifact_path=tmp_path / ".beast/evidence/sourceplan/demo.json",
        artifact_hash="sha256:demo",
        source="sourceplan",
        task_id="demo",
        status="verified",
        summary="demo receipt",
    )

    summary = MissionCockpit(tmp_path).summary(objective="Review", phase="reviewer", risk="low")
    cards = {card["card_id"]: card for card in summary["cards"]}

    assert summary["evidence_bus"]["receipt_count"] == 1
    assert cards["evidence_bus"]["value"] == 1


def test_mission_cockpit_reports_reintegration_health_for_repo():
    summary = MissionCockpit(Path.cwd()).summary(objective="Audit reintegration", phase="reviewer", risk="medium")
    health = summary["reintegration_health"]
    cards = {card["card_id"]: card for card in summary["cards"]}

    assert cards["reintegration"]["title"] == "Reintegration"
    assert health["beast_object_type"] == "beast_reintegration_health"
    assert health["duplicate_shim_import_count"] == 0
    assert isinstance(health["evidence_coverage"]["coverage_ratio"], float)
    assert "route_ownership" in health


def test_mcp_exposes_evidence_bus_summary(tmp_path):
    bus = EvidenceBus(tmp_path)
    bus.register(
        artifact_type="sourceplan_unified_evidence_packet",
        artifact_path="demo.json",
        artifact_hash="sha256:demo",
        source="sourceplan",
        task_id="demo",
        status="verified",
    )
    runtime = BeastToolRuntime()
    names = {tool["name"] for tool in runtime.tool_definitions()}
    result = runtime.call_tool("beast_evidence_bus_summary", {"workspace_root": str(tmp_path)})

    assert "beast_evidence_bus_summary" in names
    assert result["beast_object_type"] == "beast_evidence_bus_summary"
    assert result["receipt_count"] == 1


def test_evidence_bus_query_and_related_filters(tmp_path):
    bus = EvidenceBus(tmp_path)
    bus.register(
        artifact_type="sourceplan_unified_evidence_packet",
        artifact_path=".beast/evidence/sourceplan/plan_1.json",
        artifact_hash="sha256:plan",
        source="sourceplan",
        task_id="plan_1",
        status="verified",
        summary="plan one",
        relationships={"chronicle": {"chronicle_id": "chr_plan_1"}},
        metadata={"provider": "local"},
    )
    bus.register(
        artifact_type="patch_apply_crystallization",
        artifact_path=".beast/chronicle/plan_1.json",
        artifact_hash="sha256:chron",
        source="chronicle",
        task_id="plan_1",
        status="applied_verified_crystallized",
        relationships={"sourceplan": {"plan_id": "plan_1"}},
    )

    by_source = bus.query(source="sourceplan")
    by_type = bus.query(artifact_type="patch_apply_crystallization")
    related = bus.related("plan_1")

    assert by_source["beast_object_type"] == "beast_evidence_bus_query"
    assert by_source["match_count"] == 1
    assert by_type["receipts"][0]["source"] == "chronicle"
    assert related["beast_object_type"] == "beast_evidence_bus_related"
    assert related["match_count"] == 2
    assert related["by_type"]["sourceplan_unified_evidence_packet"] == 1


def test_mcp_exposes_evidence_bus_query_and_related(tmp_path):
    EvidenceBus(tmp_path).register(
        artifact_type="sourceplan_unified_evidence_packet",
        artifact_path="demo.json",
        artifact_hash="sha256:demo",
        source="sourceplan",
        task_id="demo_plan",
        status="verified",
    )
    runtime = BeastToolRuntime()
    names = {tool["name"] for tool in runtime.tool_definitions()}
    query = runtime.call_tool("beast_evidence_bus_query", {"workspace_root": str(tmp_path), "source": "sourceplan"})
    related = runtime.call_tool("beast_evidence_bus_related", {"workspace_root": str(tmp_path), "key": "demo_plan"})

    assert "beast_evidence_bus_query" in names
    assert "beast_evidence_bus_related" in names
    assert query["match_count"] == 1
    assert related["match_count"] == 1
