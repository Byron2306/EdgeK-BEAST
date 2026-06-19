import pytest
from httpx import ASGITransport, AsyncClient

from app.kernel.runtime import RuntimeGovernor
from app.kernel.task_envelope import TaskEnvelopeBuilder
from app.main import app


def test_task_envelope_classifies_provider_debugging():
    builder = TaskEnvelopeBuilder(
        policies={
            "meta_rules": {"max_input_tokens_per_request": 18000},
            "providers": {"huggingface": {"enabled": True, "default_model": "openai/gpt-oss-120b"}},
        }
    )

    envelope = builder.build(
        {"user_request": "Hugging Face route returned 429 quota error"},
        dry_run=True,
    )

    assert envelope["beast_object_type"] == "task_envelope"
    assert envelope["task_class"] == "provider_debugging"
    assert envelope["inputs"]["provider"] == "huggingface"
    assert envelope["context_budget"]["max_tokens"] == 18000
    assert "inspect_runtime_state" in envelope["allowed_actions"]
    assert "root cause category identified" in envelope["success_criteria"]


def test_provider_diagnostic_uses_local_runtime_and_writes_chronicle(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    governor = RuntimeGovernor(
        policies={"meta_rules": {"runtime_provider_timeout_seconds": 10}},
        db_path=str(tmp_path / "runtime.db"),
    )
    attempt = governor.begin_execution(
        "huggingface",
        "openai/gpt-oss-120b",
        metadata={"purpose": "diagnostic-test"},
    )
    governor.complete_execution(
        attempt.attempt_id,
        "huggingface",
        success=False,
        error_type="http_429",
        error_message="429 quota exhausted",
    )
    (tmp_path / "gateway.log").write_text(
        "huggingface provider returned 429 quota exhausted\n",
        encoding="utf-8",
    )
    builder = TaskEnvelopeBuilder(
        policies={
            "providers": {
                "huggingface": {
                    "enabled": True,
                    "base_url": "https://router.huggingface.co/v1",
                    "default_model": "openai/gpt-oss-120b",
                }
            }
        },
        runtime_governor=governor,
        data_dir=str(tmp_path / "data"),
    )

    result = builder.diagnose_provider(
        {"user_request": "Diagnose Hugging Face route failure"},
        workspace_root=str(tmp_path),
        write_chronicle=True,
    )

    assert result["beast_object_type"] == "provider_diagnostic"
    assert result["provider"] == "huggingface"
    assert result["failure_category"] == "quota_or_rate_limit"
    assert result["local_only"] is True
    assert result["route_card"]["route_id"] == "route_provider_diagnostic_huggingface"
    assert result["route_card"]["preferred_order"][0] == "provider_policy"
    assert result["route_execution"]["source"] == "route_card.preferred_order"
    assert result["route_execution"]["executed_order"][:2] == ["provider_policy", "credentials"]
    assert result["quality_report"]["beast_object_type"] == "quality_cascade_report"
    assert result["quality_report"]["route_id"] == "route_provider_diagnostic_huggingface"
    assert result["quality_report"]["summary"]["check_count"] == len(result["checks"])
    assert result["chronicle"]["written"] is True
    assert result["chronicle"]["json_path"].endswith(".json")
    assert result["chronicle"]["record"]["category"] == "quota_or_rate_limit"
    assert "Pause retries" in "\n".join(result["recommendations"])
    assert (tmp_path / "data" / "chronicles").exists()
    chronicles = builder.list_chronicles(provider="huggingface")
    detail = builder.get_chronicle(result["task_id"])
    assert chronicles["count"] == 1
    assert chronicles["chronicles"][0]["task_id"] == result["task_id"]
    assert detail["record"]["task_id"] == result["task_id"]
    assert "Provider Diagnostic" in detail["markdown"]
    routes = builder.list_route_cards(provider="huggingface")
    assert routes["count"] == 1
    assert routes["route_cards"][0]["promotion_status"] == "candidate"


@pytest.mark.asyncio
async def test_task_envelope_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        envelope = await client.post(
            "/edgek/task/envelope",
            json={"user_request": "Hugging Face provider route is failing"},
        )
        diagnostic = await client.post(
            "/edgek/task/provider-diagnostic",
            json={"provider": "huggingface", "chronicle": False},
        )
        cascade = await client.post(
            "/edgek/task/quality-cascade",
            json={"provider": "huggingface", "user_request": "Diagnose Hugging Face route failure"},
        )
        quality_alias = await client.post(
            "/edgek/quality/run",
            json={"provider": "huggingface", "user_request": "Diagnose Hugging Face route failure"},
        )
        forge_alias = await client.post(
            "/edgek/forge/decision",
            json={"provider": "huggingface", "user_request": "Diagnose Hugging Face route failure"},
        )
        conductor_alias = await client.post(
            "/edgek/conductor/workflow-card",
            json={"provider": "huggingface", "user_request": "Diagnose Hugging Face route failure"},
        )

    assert envelope.status_code == 200
    assert envelope.json()["mode"] == "dry_run"
    assert envelope.json()["envelope"]["task_class"] == "provider_debugging"
    assert diagnostic.status_code == 200
    assert diagnostic.json()["provider"] == "huggingface"
    assert diagnostic.json()["route_card"]["task_class"] == "provider_debugging"
    assert diagnostic.json()["chronicle"] is None
    assert cascade.status_code == 200
    assert cascade.json()["beast_object_type"] == "quality_cascade_report"
    assert cascade.json()["route_id"] == "route_provider_diagnostic_huggingface"
    assert cascade.json()["route_execution"]["source"] == "route_card.preferred_order"
    assert quality_alias.status_code == 200
    assert quality_alias.json()["beast_object_type"] == "quality_cascade_report"
    assert forge_alias.status_code == 200
    assert forge_alias.json()["beast_object_type"] == "forge_scorecard"
    assert conductor_alias.status_code == 200
    assert conductor_alias.json()["beast_object_type"] == "conductor_workflow_card"


@pytest.mark.asyncio
async def test_chronicle_endpoints_use_builder_store(tmp_path, monkeypatch):
    import app.main as main_module

    builder = TaskEnvelopeBuilder(
        policies={"providers": {"huggingface": {"enabled": True}}},
        data_dir=str(tmp_path / "data"),
    )
    result = builder.diagnose_provider(
        {"provider": "huggingface", "user_request": "Diagnose Hugging Face auth failure"},
        workspace_root=str(tmp_path),
        write_chronicle=True,
    )
    monkeypatch.setattr(main_module, "task_envelope_builder", builder)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        listing = await client.get("/edgek/chronicle?provider=huggingface")
        detail = await client.get(f"/edgek/chronicle/{result['task_id']}")
        publish = await client.post(
            "/edgek/chronicle/publish",
            json={"task_id": result["task_id"], "targets": ["pr_summary", "mermaid"], "dry_run": True},
        )

    assert listing.status_code == 200
    assert listing.json()["count"] == 1
    assert listing.json()["chronicles"][0]["task_id"] == result["task_id"]
    assert detail.status_code == 200
    assert detail.json()["record"]["task_id"] == result["task_id"]
    assert "Provider Diagnostic" in detail.json()["markdown"]
    assert publish.status_code == 200
    assert publish.json()["beast_object_type"] == "chronicle_projection_packet"
    assert {item["target"] for item in publish.json()["projections"]} == {"pr_summary", "mermaid"}


@pytest.mark.asyncio
async def test_route_card_endpoints_use_builder_store(tmp_path, monkeypatch):
    import app.main as main_module

    builder = TaskEnvelopeBuilder(data_dir=str(tmp_path / "data"))
    monkeypatch.setattr(main_module, "task_envelope_builder", builder)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/edgek/route/provider-diagnostic/huggingface",
            json={"user_request": "Diagnose Hugging Face route failure"},
        )
        alias = await client.post(
            "/edgek/pathfinder/route-card",
            json={"provider": "huggingface", "user_request": "Diagnose Hugging Face route failure"},
        )
        listing = await client.get("/edgek/route/cards?provider=huggingface")
        detail = await client.get("/edgek/route/cards/route_provider_diagnostic_huggingface")

    assert created.status_code == 200
    assert created.json()["route_id"] == "route_provider_diagnostic_huggingface"
    assert alias.status_code == 200
    assert alias.json()["route_id"] == "route_provider_diagnostic_huggingface"
    assert "blind_provider_retries" in created.json()["avoid"]
    assert listing.status_code == 200
    assert listing.json()["count"] == 1
    assert detail.status_code == 200
    assert detail.json()["preferred_order"][0] == "provider_policy"
