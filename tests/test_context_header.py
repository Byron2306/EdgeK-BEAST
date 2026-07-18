import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_context_header_suggestions_require_explicit_acceptance(tmp_path):
    (tmp_path / "service.py").write_text("def calculate_total():\n    return 1\n", encoding="utf-8")
    (tmp_path / "service_test.py").write_text("from service import calculate_total\n", encoding="utf-8")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/edgek/workspace/context-header",
            json={"root_path": str(tmp_path), "objective": "test calculate_total", "selected_files": ["service.py"]},
        )
    payload = response.json()
    assert response.status_code == 200
    assert payload["beast_object_type"] == "beast_context_header.v1"
    assert payload["selected_files"] == ["service.py"]
    assert all(item["selected"] is False and item["requires_operator_acceptance"] is True for item in payload["suggestions"])
