from httpx import ASGITransport, AsyncClient
import pytest

from app.main import app
from app.kernel.compute.residual_contracts import sha256_digest


@pytest.mark.asyncio
async def test_operator_language_api_resolves_beast_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/edgek/compute/operator-language",
            json={"utterance": "what endpoint is beast on?", "tone": "concise"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["receipt"]["state"] == "resolved"
    assert payload["receipt"]["intent"] == "read_service_endpoint"
    assert payload["receipt"]["service_names"] == ["beast"]
    assert payload["receipt"]["provider_called"] is False
    assert payload["receipt"]["action_taken"] is False
    assert "127.0.0.1:8101" in payload["output"]


@pytest.mark.asyncio
async def test_operator_language_api_requires_utterance():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/edgek/compute/operator-language", json={})

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_scene_capsule_api_composes_render_only_svg():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/edgek/compute/scene-capsule",
            json={
                "capsule_id": "scene-capsule:api-test",
                "scene": {
                    "scene_id": "scene:api-status",
                    "canvas": {"width": 180, "height": 100, "background": "#07110d"},
                    "opcodes": [
                        {"kind": "place_asset", "args": {"asset_id": "beast.mascot.idle", "x": 8, "y": 14, "width": 56, "height": 56}},
                        {"kind": "draw_text", "args": {"x": 72, "y": 44, "text": "BEAST", "font_size": 16}},
                    ],
                },
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["beast_object_type"] == "scene_capsule_result"
    assert payload["svg"].startswith("<svg")
    assert payload["composition_receipt"]["verified"] is True
    assert payload["capsule"]["maximum_authority"] == "render_only"
    assert payload["capsule"]["network_scope"] == "none"
    assert payload["capsule"]["provider_scope"] == "none"
    assert payload["capsule"]["physical_scope"] == "none"
    assert payload["capsule"]["capsule_digest"].startswith("sha256:")


@pytest.mark.asyncio
async def test_visual_residual_api_runs_region_bound_generation():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/edgek/compute/visual-residual",
            json={
                "capsule_id": "scene-capsule:visual-api-test",
                "scene": {
                    "scene_id": "scene:visual-api",
                    "canvas": {"width": 180, "height": 100, "background": "#07110d"},
                    "opcodes": [
                        {"kind": "place_asset", "args": {"asset_id": "beast.mascot.idle", "x": 8, "y": 14, "width": 56, "height": 56}},
                        {"kind": "draw_text", "args": {"x": 72, "y": 44, "text": "BEAST", "font_size": 16}},
                    ],
                },
                "mask": {"mask_id": "mask:api-status-light", "x": 120, "y": 24, "width": 16, "height": 16},
                "prompt": "green status light",
                "seed": 5,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["beast_object_type"] == "visual_residual_result"
    assert payload["output_base64"]
    assert payload["receipt"]["scene_capsule_digest"] == payload["scene_capsule"]["capsule_digest"]
    assert payload["receipt"]["verified"] is True
    assert payload["receipt"]["network_used"] is False
    assert payload["receipt"]["details"]["region_only"] is True


@pytest.mark.asyncio
async def test_provider_reduction_api_returns_scorecard():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/edgek/compute/provider-reduction")

    assert response.status_code == 200
    payload = response.json()
    assert payload["beast_object_type"] == "provider_reduction_scorecard"
    assert "observed_channels" in payload
    assert payload["scorecard_digest"].startswith("sha256:")


@pytest.mark.asyncio
async def test_capability_learning_api_returns_ledger_report():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/edgek/compute/capability-learning")

    assert response.status_code == 200
    payload = response.json()
    assert payload["beast_object_type"] == "capability_learning_report"
    assert "capabilities" in payload
    assert payload["ledger_digest"].startswith("sha256:")


@pytest.mark.asyncio
async def test_capability_composition_api_refuses_missing_causal_rule():
    facts = [
        {
            "fact_id": "fact:health:beast",
            "fact_type": "service_health",
            "subject": "beast",
            "predicate": "health",
            "value": {"state": "healthy"},
            "evidence_digest": sha256_digest({"fact": "health", "service": "beast"}),
        },
        {
            "fact_id": "fact:health:commons",
            "fact_type": "service_health",
            "subject": "commons",
            "predicate": "health",
            "value": {"state": "healthy"},
            "evidence_digest": sha256_digest({"fact": "health", "service": "commons"}),
        },
        {
            "fact_id": "fact:topology:commons:beast",
            "fact_type": "dependency_topology",
            "subject": "commons",
            "predicate": "depends_on",
            "object": "beast",
            "value": {"relation": "depends_on"},
            "evidence_digest": sha256_digest({"fact": "topology", "source": "beast", "target": "commons"}),
        },
        {
            "fact_id": "fact:restart:beast",
            "fact_type": "restart_policy",
            "subject": "beast",
            "predicate": "restart_policy",
            "value": {"mode": "rolling_with_healthcheck"},
            "evidence_digest": sha256_digest({"fact": "restart_policy", "service": "beast"}),
        },
        {
            "fact_id": "fact:evidence:runtime",
            "fact_type": "current_evidence",
            "subject": "runtime",
            "predicate": "current_evidence",
            "value": {"state": "stable"},
            "evidence_digest": sha256_digest({"fact": "current_evidence"}),
        },
    ]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/edgek/compute/capability-composition/restart-risk",
            json={
                "question": {
                    "question_id": "question:api",
                    "source_service": "beast",
                    "target_service": "commons",
                    "utterance": "Could restarting BEAST destabilize Commons?",
                },
                "facts": facts,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unsupported"
    assert payload["unsupported_causal_gaps"] == ["restart_destabilization_causal_rule"]
    assert payload["residual_payload"]["residual_scope"] == "causal_gap_only"


@pytest.mark.asyncio
async def test_capability_composition_api_composes_traffic_shift():
    facts = [
        _composition_fact("service_health", "beast", "health", {"state": "degraded"}),
        _composition_fact("service_health", "commons", "health", {"state": "healthy"}),
        _composition_fact("traffic_route", "beast", "can_shift_to", {"route": "weighted"}, object="commons"),
        _composition_fact("resource_headroom", "commons", "headroom", {"available_percent": 40}),
        _composition_fact("current_evidence", "beast", "current_evidence", {"state": "stable", "traffic_to_shift_percent": 15}),
        _composition_fact(
            "traffic_shift_policy",
            "beast",
            "shift_policy",
            {"max_shift_percent": 25, "requires_target_healthy": True},
            object="commons",
        ),
    ]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/edgek/compute/capability-composition/traffic-shift",
            json={
                "question": {
                    "question_id": "question:api-traffic",
                    "source_service": "beast",
                    "target_service": "commons",
                    "question_type": "traffic_shift_safety",
                },
                "facts": facts,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "composed"
    assert payload["answer"]["risk_class"] == "low"
    assert payload["provider_calls_used"] == 0


@pytest.mark.asyncio
async def test_capability_composition_api_refuses_deployment_gap():
    facts = [
        _composition_fact("service_health", "beast", "health", {"state": "healthy"}),
        _composition_fact("deployment_policy", "beast", "deployment_policy", {"strategy": "canary"}),
        _composition_fact("rollback_policy", "beast", "rollback_policy", {"automatic": True, "max_rollback_seconds": 60}),
        _composition_fact("slo_budget", "production", "slo_budget", {"remaining_error_budget_percent": 83}),
        _composition_fact("current_evidence", "runtime", "current_evidence", {"state": "stable", "active_incidents": 0}),
    ]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/edgek/compute/capability-composition/deployment-safety",
            json={
                "question": {
                    "question_id": "question:api-deployment",
                    "source_service": "beast",
                    "target_service": "production",
                    "question_type": "deployment_safety",
                },
                "facts": facts,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unsupported"
    assert payload["unsupported_causal_gaps"] == ["deployment_blast_radius_rule"]
    assert payload["residual_payload"]["residual_scope"] == "deployment_gap_only"


@pytest.mark.asyncio
async def test_visual_composition_api_composes_status_card():
    facts = [
        _visual_composition_fact("scene_capsule", "scene:beast-status", "capsule", {"capsule_digest": sha256_digest("scene-capsule")}),
        _visual_composition_fact("asset_manifest", "scene:beast-status", "manifest", {"manifest_digest": sha256_digest("manifest")}),
        _visual_composition_fact("visual_intent", "region:status-light", "intent", {"color": "green", "object": "status_light"}),
        _visual_composition_fact("layout_anchor", "region:status-light", "anchor", {"anchor": "top_right", "x": 120, "y": 24, "width": 16, "height": 16}),
        _visual_composition_fact(
            "promoted_visual_asset",
            "region:status-light",
            "asset",
            {"asset_id": "visual.promoted.status_light.green", "asset_digest": sha256_digest("green-status-light-rgba"), "width": 16, "height": 16},
        ),
    ]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/edgek/compute/visual-composition/status-card",
            json={
                "question": {
                    "question_id": "visual-question:api-status",
                    "scene_id": "scene:beast-status",
                    "region_id": "region:status-light",
                    "visual_goal": "green status light on BEAST status card",
                },
                "facts": facts,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "composed"
    assert payload["render_authority"] == "render_only"
    assert payload["provider_calls_used"] == 0


@pytest.mark.asyncio
async def test_visual_composition_api_refutes_layout_overflow():
    facts = [
        _visual_composition_fact("canvas_contract", "scene:beast-status", "canvas", {"width": 180, "height": 100}),
        _visual_composition_fact("layout_anchor", "region:status-light", "anchor", {"x": 170, "y": 24, "width": 16, "height": 16}),
        _visual_composition_fact(
            "promoted_visual_asset",
            "region:status-light",
            "asset",
            {"asset_id": "visual.promoted.status_light.green", "asset_digest": sha256_digest("green-status-light-rgba"), "width": 16, "height": 16},
        ),
    ]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/edgek/compute/visual-composition/layout-safety",
            json={
                "question": {
                    "question_id": "visual-question:api-layout",
                    "scene_id": "scene:beast-status",
                    "region_id": "region:status-light",
                    "visual_goal": "place status light inside the status card canvas",
                    "question_type": "visual_layout_safety",
                },
                "facts": facts,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "refuted"
    assert payload["answer"]["layout_class"] == "unsafe"
    assert payload["render_authority"] == "render_only"


@pytest.mark.asyncio
async def test_cross_modal_composition_api_binds_restart_answer_and_visuals():
    text_question = {
        "question_id": "question:api-cross-restart",
        "source_service": "beast",
        "target_service": "commons",
        "utterance": "Could restarting BEAST destabilize Commons?",
    }
    visual_question = {
        "question_id": "visual-question:api-cross-status",
        "scene_id": "scene:beast-status",
        "region_id": "region:status-light",
        "visual_goal": "green status light on BEAST status card",
    }
    payload = {
        "question": {
            "question_id": "cross-modal:api",
            "text_question_digest": sha256_digest(text_question),
            "visual_question_digest": sha256_digest(visual_question),
            "operator_goal": "Show restart risk and visualize the dependency status.",
        },
        "text": {
            "question": text_question,
            "facts": [
                _composition_fact("service_health", "beast", "health", {"state": "healthy"}),
                _composition_fact("service_health", "commons", "health", {"state": "healthy"}),
                _composition_fact("dependency_topology", "commons", "depends_on", {"relation": "depends_on"}, object="beast"),
                _composition_fact("restart_policy", "beast", "restart_policy", {"mode": "rolling_with_healthcheck"}),
                _composition_fact("current_evidence", "runtime", "current_evidence", {"state": "stable", "restart_count": 0}),
                _composition_fact("restart_causal_rule", "service_restart", "causal_rule", {"rule": "rolling_restart_compatible_with_dependents"}, object="dependent_service"),
            ],
        },
        "visual": {
            "status_card": {
                "question": visual_question,
                "facts": [
                    _visual_composition_fact("scene_capsule", "scene:beast-status", "capsule", {"capsule_digest": sha256_digest("scene-capsule")}),
                    _visual_composition_fact("asset_manifest", "scene:beast-status", "manifest", {"manifest_digest": sha256_digest("manifest")}),
                    _visual_composition_fact("visual_intent", "region:status-light", "intent", {"color": "green", "object": "status_light"}),
                    _visual_composition_fact("layout_anchor", "region:status-light", "anchor", {"anchor": "top_right", "x": 120, "y": 24, "width": 16, "height": 16}),
                    _visual_composition_fact("promoted_visual_asset", "region:status-light", "asset", {"asset_id": "visual.promoted.status_light.green", "asset_digest": sha256_digest("green-status-light-rgba"), "width": 16, "height": 16}),
                ],
            },
            "promoted_region_reuse": {
                "question": {
                    **visual_question,
                    "question_id": "visual-question:api-cross-reuse",
                    "question_type": "visual_promoted_region_reuse",
                    "visual_goal": "reuse verified green status light region",
                },
                "facts": [
                    _visual_composition_fact("scene_capsule", "scene:beast-status", "capsule", {"capsule_digest": sha256_digest("scene-capsule")}),
                    _visual_composition_fact("region_mask", "region:status-light", "mask", {"x": 120, "y": 24, "width": 16, "height": 16}),
                    _visual_composition_fact("visual_intent", "region:status-light", "intent", {"color": "green", "object": "status_light"}),
                    _visual_composition_fact("promoted_visual_asset", "region:status-light", "asset", {"asset_id": "visual.promoted.status_light.green", "asset_digest": sha256_digest("green-status-light-rgba"), "width": 16, "height": 16}),
                    _visual_composition_fact("quality_receipt", "region:status-light", "quality", {"passed": True}),
                    _visual_composition_fact("intent_receipt", "region:status-light", "intent_receipt", {"passed": True}),
                    _visual_composition_fact("perceptual_receipt", "region:status-light", "perceptual", {"passed": True}),
                    _visual_composition_fact("feature_embedding", "region:status-light", "embedding", {"bins": [1, 4, 2, 8]}),
                    _visual_composition_fact("equivalence_receipt", "region:status-light", "equivalence", {"equivalent": True}),
                ],
            },
            "layout_safety": {
                "question": {
                    **visual_question,
                    "question_id": "visual-question:api-cross-layout",
                    "question_type": "visual_layout_safety",
                    "visual_goal": "place status light inside the status card canvas",
                },
                "facts": [
                    _visual_composition_fact("canvas_contract", "scene:beast-status", "canvas", {"width": 180, "height": 100}),
                    _visual_composition_fact("layout_anchor", "region:status-light", "anchor", {"x": 120, "y": 24, "width": 16, "height": 16}),
                    _visual_composition_fact("promoted_visual_asset", "region:status-light", "asset", {"asset_id": "visual.promoted.status_light.green", "asset_digest": sha256_digest("green-status-light-rgba"), "width": 16, "height": 16}),
                ],
            },
        },
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/edgek/compute/cross-modal/restart-risk-visual", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "composed"
    assert body["render_authority"] == "render_only"
    assert body["provider_calls_used"] == 0
    assert set(body["visual_receipt_digests"]) == {"status_card", "promoted_region_reuse", "layout_safety"}


@pytest.mark.asyncio
async def test_generation_provider_adapter_api_reports_stub_and_live_readiness():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/edgek/compute/provider-adapters")

    assert response.status_code == 200
    payload = response.json()
    assert payload["beast_object_type"] == "generation_provider_adapter_inventory"
    assert payload["inventory_digest"].startswith("sha256:")
    assert any(item["mode"] == "stub" and item["live_execution_allowed"] is False for item in payload["providers"])
    assert any(item["mode"] == "live" and item["requires_approval"] is True for item in payload["providers"])


@pytest.mark.asyncio
async def test_generation_provider_adapter_execute_api_uses_stub_by_default():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/edgek/compute/provider-adapters/execute",
            json={"provider": "gemini", "modality": "text", "prompt": "hello"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["beast_object_type"] == "generation_provider_result"
    assert payload["receipt"]["provider_id"] == "gemini"
    assert payload["receipt"]["mode"] == "stub"


def _composition_fact(fact_type, subject, predicate, value, *, object=""):
    return {
        "fact_id": f"fact:{fact_type}:{subject}:{predicate}:{object}",
        "fact_type": fact_type,
        "subject": subject,
        "predicate": predicate,
        "object": object,
        "value": value,
        "evidence_digest": sha256_digest({"fact": fact_type, "subject": subject, "predicate": predicate, "object": object, "value": value}),
    }


def _visual_composition_fact(fact_type, subject, predicate, value, *, object=""):
    return {
        "fact_id": f"visual-fact:{fact_type}:{subject}:{predicate}:{object}",
        "fact_type": fact_type,
        "subject": subject,
        "predicate": predicate,
        "object": object,
        "value": value,
        "evidence_digest": sha256_digest({"fact": fact_type, "subject": subject, "predicate": predicate, "object": object, "value": value}),
    }
    assert payload["output_text"]


@pytest.mark.asyncio
async def test_reduction_evidence_api_rejects_raw_prompt_payloads():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/edgek/compute/reduction-evidence",
            json={
                "source_system": "forge_kv_prompt_cache",
                "receipt": {
                    "raw_prompt": "do not ingest me",
                    "prompt_tokens_avoided": 10,
                },
            },
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_reduction_evidence_discovery_api_rejects_out_of_scope_paths():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/edgek/compute/reduction-evidence/discover",
            json={"paths": ["/tmp"], "max_files": 10},
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_visual_assets_api_returns_registry_view():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/edgek/compute/visual-assets")

    assert response.status_code == 200
    payload = response.json()
    assert payload["beast_object_type"] == "visual_asset_registry"
    assert "assets" in payload
    assert payload["registry_digest"].startswith("sha256:")
