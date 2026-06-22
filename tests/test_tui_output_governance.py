from app.cli.api import BackendSnapshot
from app.cli.ui import (
    current_plan_summary,
    governance_table,
    operations_table,
    mascot_frames,
    mascot_state_for,
    provider_fitness_score,
    provider_route_summary,
    provider_route_table,
    requests_table,
    sprite_mascot,
)


def governed_plan():
    return {
        "plan_id": "plan_demo",
        "status": "draft_requires_approval",
        "provider": "nvidia_nim",
        "provider_generated": True,
        "selected_operations": ["op_001"],
        "operations": [
            {
                "op_id": "op_001",
                "path": "app/kernel/provider_registry.py",
                "source_edit": True,
                "selected": True,
                "description": "Add provider record",
            }
        ],
        "non_mutating_requests": [
            {
                "id": "a1",
                "type": "run_verifier",
                "path": "",
                "intent": "run syntax check",
                "parameters": {"command": "python -m py_compile app.py"},
            }
        ],
        "output_evidence": {
            "contract": "beast.action_intent.v1",
            "final_status": "compiled",
            "diff_compiled": True,
        },
        "provider_handoff": {
            "trace": {"input_handoff_hash": "sha256:abc123"},
            "packet_stats": {"estimated_tokens": 1200},
            "output": {"schema": {"kind": "beast.action_intent.v1"}},
        },
    }


def test_current_plan_summary_surfaces_output_governance():
    summary = current_plan_summary(governed_plan())

    assert summary["plan_id"] == "plan_demo"
    assert summary["provider"] == "nvidia_nim"
    assert summary["contract"] == "beast.action_intent.v1"
    assert summary["gate_status"] == "compiled"
    assert summary["source_operations"] == 1
    assert summary["requests"] == 1
    assert summary["handoff_hash"] == "sha256:abc123"


def test_governance_tables_render_without_backend():
    plan = governed_plan()

    assert governance_table(plan).row_count >= 8
    assert operations_table(plan).row_count == 1
    assert requests_table(plan).row_count == 1
    assert requests_table({}).row_count == 1


def test_provider_route_summary_resolves_nim_model_and_route():
    snap = BackendSnapshot(
        base_url="http://gateway",
        provider_registry={
            "providers": [
                {
                    "provider_id": "nvidia_nim",
                    "backend": "openai_compatible",
                    "default_model": "nvidia/nemotron-3-super-120b-a12b",
                    "proxy_path": "/proxy/nvidia-nim",
                    "base_url": "https://integrate.api.nvidia.com/v1",
                    "env": ["NVIDIA_API_KEY"],
                }
            ]
        },
        provider_adapters=[
            {
                "provider_id": "nvidia_nim",
                "backend": "openai_compatible",
                "adapter_class": "openai_compatible",
                "route_provider": "openai_compatible",
                "model": "nvidia/nemotron-3-super-120b-a12b",
                "proxy_path": "/proxy/nvidia-nim",
                "base_url": "https://integrate.api.nvidia.com/v1",
                "env": ["NVIDIA_API_KEY"],
                "governed_by_beast": True,
            }
        ],
    )

    summary = provider_route_summary(snap, "nvidia-nim")

    assert summary["provider_id"] == "nvidia_nim"
    assert summary["route_provider"] == "openai_compatible"
    assert summary["resolved_model"] == "nvidia/nemotron-3-super-120b-a12b"
    assert summary["proxy_path"] == "/proxy/nvidia-nim"
    assert provider_route_table(summary).row_count >= 10


def test_provider_fitness_score_uses_chronicle_output_evidence():
    snap = BackendSnapshot(
        base_url="http://gateway",
        chronicles=[
            {
                "provider": "huggingface",
                "status": "applied_verified_crystallized",
                "validation_status": "compiled",
                "pytest_status": "passed",
                "canonicalized": False,
                "latency_ms": 1000,
                "output_evidence": {"repair_attempted": False},
                "verification": {"ok": True},
            },
            {
                "provider": "huggingface",
                "status": "applied_verified_crystallized",
                "validation_status": "compiled",
                "pytest_status": "passed",
                "canonicalized": True,
                "latency_ms": 2000,
                "output_evidence": {"repair_attempted": False},
                "verification": {"ok": True},
            },
        ],
    )

    score = provider_fitness_score(snap, "huggingface")

    assert score["score"] >= 90
    assert score["sample_size"] == 2
    assert score["clean"] == 1
    assert score["rescued"] == 1


def test_provider_route_summary_keeps_litellm_resolved_model_visible():
    snap = BackendSnapshot(
        base_url="http://gateway",
        provider_registry={
            "providers": [
                {
                    "provider_id": "litellm",
                    "backend": "litellm",
                    "default_model": "ollama",
                    "proxy_path": "/proxy/litellm",
                }
            ]
        },
        provider_adapters=[
            {
                "provider_id": "litellm",
                "backend": "litellm",
                "adapter_class": "litellm",
                "route_provider": "litellm",
                "model": "litellm/ollama",
                "proxy_path": "/proxy/litellm",
                "governed_by_beast": True,
            }
        ],
    )

    summary = provider_route_summary(snap, "litellm")

    assert summary["backend"] == "litellm"
    assert summary["route_provider"] == "litellm"
    assert summary["resolved_model"] == "litellm/ollama"


def test_provider_page_uses_benchmarked_model_fitness():
    snap = BackendSnapshot(
        base_url="http://gateway",
        provider_registry={"providers": [{"provider_id": "groq", "enabled": True}]},
        provider_model_fitness={
            "artifact_path": "/tmp/model_fitness.json",
            "models": [{
                "provider": "groq",
                "model": "llama-3.1-8b-instant",
                "fitness_score": 0.875,
                "samples": 8,
                "completed": 7,
                "clean_completed": 6,
                "rescued_completed": 1,
                "completion_rate": 0.875,
                "clean_completion_rate": 0.75,
                "rescue_rate": 0.125,
                "avg_latency_ms": 320.0,
            }],
        },
    )

    rendered = __import__("app.cli.ui", fromlist=["PageHost"]).PageHost().providers(snap, 0)

    assert rendered.row_count == 2


def test_mascot_sprite_frames_load_for_tui_states():
    frames = mascot_frames()

    assert set(["idle", "working", "alert", "finished"]).issubset(frames)
    assert all(len(frames[state]) == 10 for state in ["idle", "working", "alert", "finished"])
    assert mascot_state_for("streaming") == "working"
    assert mascot_state_for("error") == "alert"
    assert mascot_state_for("completed") == "finished"
    assert sprite_mascot("working", 3).plain.strip()
