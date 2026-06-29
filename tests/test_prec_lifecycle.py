import pytest
from httpx import ASGITransport, AsyncClient

from app.kernel.storage.prec_lifecycle import PRECLifecycleStore
from app.main import app


def test_prec_lifecycle_records_all_phases(tmp_path):
    store = PRECLifecycleStore(str(tmp_path / "prec.db"))

    record = store.record_artifact_lifecycle(
        kind="task",
        payload={"user_request": "Diagnose provider failure", "provider": "huggingface"},
        artifacts={
            "envelope": {
                "beast_object_type": "task_envelope",
                "task_id": "tsk_demo",
                "task_class": "provider_debugging",
                "inputs": {"provider": "huggingface"},
                "success_criteria": ["root cause categorized"],
            },
            "route_card": {
                "beast_object_type": "route_card",
                "route_id": "route_provider_diagnostic_huggingface",
                "preferred_order": ["provider_policy", "credentials"],
                "promotion_status": "candidate",
            },
            "context_packet": {
                "beast_object_type": "context_packet",
                "packet_id": "pkt_demo",
                "task_id": "tsk_demo",
                "packet_stats": {"included_count": 2},
            },
            "chronicle": {
                "written": True,
                "record": {"task_id": "tsk_demo", "category": "auth_or_credentials", "memory_candidate": True},
            },
        },
    )
    detail = store.get(record["lifecycle_id"])

    assert record["status"] == "completed"
    assert record["current_phase"] == "crystallize"
    assert detail["phase_status"] == {
        "perceive": "completed",
        "reason": "completed",
        "economize": "completed",
        "crystallize": "completed",
    }
    assert [event["phase"] for event in detail["phase_events"]] == ["perceive", "reason", "economize", "crystallize"]
    assert detail["artifact_refs"]["economize"]["context_packet"]["packet_id"] == "pkt_demo"

    snapshot = store.compact_snapshot(record["lifecycle_id"], max_chars=2200, persist=True)
    snapshots = store.list_snapshots(record["lifecycle_id"])

    assert snapshot["beast_object_type"] == "prec_lifecycle_snapshot"
    assert snapshot["ready_for_handoff"] is True
    assert snapshot["route_constraints"]["route_id"] == "route_provider_diagnostic_huggingface"
    assert snapshot["crystallized_memory"]["chronicle"]["category"] == "auth_or_credentials"
    assert snapshot["token_estimate"] > 0
    assert snapshots["count"] == 1
    assert snapshots["snapshots"][0]["snapshot_id"] == snapshot["snapshot_id"]


@pytest.mark.asyncio
async def test_prec_lifecycle_manual_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        started = await client.post(
            "/edgek/prec/start",
            json={"kind": "ide_session", "objective": "Track current IDE task", "scope": "workspace"},
        )
        lifecycle_id = started.json()["lifecycle_id"]
        updated = await client.post(
            "/edgek/prec/update",
            json={
                "lifecycle_id": lifecycle_id,
                "phase": "perceive",
                "summary": "IDE task marked up",
                "artifacts": {"task_markup": {"objective": "Track current IDE task"}},
                "signals": ["ide_current_task"],
            },
        )
        detail = await client.get(f"/edgek/prec/lifecycle/{lifecycle_id}")
        listing = await client.get("/edgek/prec/lifecycle?kind=ide_session")

    assert started.status_code == 200
    assert updated.status_code == 200
    assert detail.status_code == 200
    assert detail.json()["phase_events"][0]["phase"] == "perceive"
    assert listing.status_code == 200
    assert any(item["lifecycle_id"] == lifecycle_id for item in listing.json()["lifecycles"])


@pytest.mark.asyncio
async def test_task_endpoint_attaches_prec_lifecycle():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        envelope = await client.post(
            "/edgek/task/envelope",
            json={"user_request": "Hugging Face provider route is failing"},
        )
        lifecycle_id = envelope.json()["prec_lifecycle"]["lifecycle_id"]
        detail = await client.get(f"/edgek/prec/lifecycle/{lifecycle_id}")

    assert envelope.status_code == 200
    assert envelope.json()["prec_lifecycle"]["status"] == "completed"
    assert detail.status_code == 200
    assert detail.json()["kind"] == "task"
    assert len(detail.json()["phase_events"]) == 4


@pytest.mark.asyncio
async def test_prec_snapshot_endpoint_compacts_and_persists():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        envelope = await client.post(
            "/edgek/task/envelope",
            json={"user_request": "Hugging Face provider route is failing"},
        )
        lifecycle_id = envelope.json()["prec_lifecycle"]["lifecycle_id"]
        snapshot = await client.get(f"/edgek/prec/lifecycle/{lifecycle_id}/snapshot?max_chars=2200")
        snapshots = await client.get(f"/edgek/prec/lifecycle/{lifecycle_id}/snapshots")

    assert snapshot.status_code == 200
    assert snapshot.json()["beast_object_type"] == "prec_lifecycle_snapshot"
    assert snapshot.json()["ready_for_handoff"] is True
    assert snapshot.json()["compaction"]["omits_raw_payloads"] is True
    assert snapshots.status_code == 200
    assert snapshots.json()["count"] >= 1
