from app.kernel.networking.swarm import SwarmKernel
from app.kernel.networking.swarm_services import SwarmKernelServices


def test_runtime_service_container_binds_safe_phase_a_services(tmp_path):
    services = SwarmKernelServices.from_runtime(workspace_graph="graph")

    assert services.economist is not None
    assert services.context_economizer is not None
    assert services.compression_pipeline is not None
    assert services.ast_compressor is not None
    assert services.workspace_graph == "graph"
    assert services.inventory()["count"] >= 5
    assert "interceptor" in services.inventory()["missing"]


def test_swarm_records_service_inventory_without_changing_plan(tmp_path):
    swarm = SwarmKernel(db_path=str(tmp_path / "swarm.db"))

    result = swarm.run({"objective": "Inspect the provider route", "local_only": True})

    inventory = result["metadata"]["service_inventory"]
    assert inventory["beast_object_type"] == "swarm_kernel_service_inventory"
    assert "economist" in inventory["bound"]
    assert result["objective"] == "Inspect the provider route"


def test_phase_b_read_only_roles_emit_typed_packets(tmp_path):
    swarm = SwarmKernel(db_path=str(tmp_path / "swarm.db"))

    result = swarm.run({
        "objective": "Fix the percentage discount failure",
        "task_type": "test_repair",
        "files": ["pricing.py"],
        "failure": "expected 170.0, got 185.0",
        "tools": ["read_file"] * 10,
        "use_ollama": False,
    })

    events = {event["role"]: event for event in result["events"]}
    assert {"hermes", "cartographer", "failure_analyst", "compressor", "crystalist"} <= events.keys()
    assert events["failure_analyst"]["details"]["failure_signature"].startswith("sha256:")
    assert events["compressor"]["details"]["exact_model_payload"]["target"]["path"] == "pricing.py"
    assert events["compressor"]["details"]["discarded_tool_schemas"] == 6
    assert events["crystalist"]["details"]["mutation_authorized"] is False


def test_hermes_uses_provider_economist_when_candidates_are_supplied(tmp_path):
    swarm = SwarmKernel(db_path=str(tmp_path / "swarm.db"))

    result = swarm.run({
        "objective": "Route a local repair",
        "provider_candidates": [{
            "provider": "ollama",
            "recommended_role": "primary_patch_provider",
            "quality_score": 0.9,
            "latency_ms": 40,
            "auth_confidence": 1.0,
            "hidden_clean_rate": 1.0,
            "verified_fixes_per_usd": 1.0,
            "hidden_clean_per_usd": 1.0,
            "rescue_rate": 0.8,
            "cost_observed": True,
        }],
    })

    hermes = next(event for event in result["events"] if event["role"] == "hermes")
    assert hermes["details"]["route_decision"]["route"] == "ollama"
    assert hermes["details"]["route_decision"]["read_only"] is True
