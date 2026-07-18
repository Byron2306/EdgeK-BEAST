"""End-to-end proof that a desktop editor proposal becomes a real, verified edit."""

import hashlib

import pytest
from httpx import ASGITransport, AsyncClient

from app.cli.api import BeastApiClient
from app.main import app


@pytest.mark.asyncio
async def test_editor_proposal_to_verified_file_edit(tmp_path):
    target = tmp_path / "calculator.py"
    original = "def answer():\n    return 41\n"
    proposed = "def answer():\n    return 42\n"
    target.write_text(original, encoding="utf-8")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        draft_response = await http.post(
            "/edgek/ide/sourceplan/from-editor",
            json={
                "root_path": str(tmp_path),
                "path": "calculator.py",
                "original_text": original,
                "new_text": proposed,
                "objective": "Make the calculator answer the verified value",
                "provider": "ollama",
                "model": "qwen2.5:0.5b",
            },
        )

    assert draft_response.status_code == 200
    draft = draft_response.json()
    assert draft["ok"] is True
    plan = draft["plan"]
    operation = plan["operations"][0]
    assert operation["op"] == "replace_exact"
    assert operation["path"] == "calculator.py"
    assert operation["old_text"] == original
    assert operation["new_text"] == proposed
    assert "return 42" in draft["preview_text"]

    client = BeastApiClient("http://offline", workspace=tmp_path)
    verification = client.verify_patch_plan(plan)
    assert verification.ok is True
    assert verification.data["errors"] == []
    assert verification.data["verified"][0]["ok"] is True

    applied = client.apply_patch_plan(plan, approved=True)
    assert applied.ok is True
    assert target.read_text(encoding="utf-8") == proposed
    assert applied.data["verification"]["ok"] is True
    assert applied.data["rollback_path"]
    assert applied.data["evidence_packet"]["evidence_hash"]
    assert applied.data["evidence_packet"]["path"].endswith(".beast/evidence/sourceplan/" + plan["plan_id"] + ".json")
    assert applied.data["chronicle"]["record"]["status"] == "applied_verified_crystallized"

    # The write must be the exact governed operation, not merely a changed file.
    expected_hash = hashlib.sha256(proposed.encode("utf-8")).hexdigest()
    packet_operation = applied.data["chronicle"]["record"]["operation_summaries"][0]
    assert packet_operation["new_hash"] == expected_hash
    assert packet_operation["path"] == "calculator.py"
