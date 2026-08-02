import pytest

from app.kernel.networking import invoice_closure


@pytest.mark.asyncio
async def test_recording_provider_preserves_packet_for_live_provider():
    class Provider:
        model = "test-live"

        async def solve_residual(self, payload, *, run=None):
            return {"status": "solved", "fields": {"new": "return 1"}}

    provider = invoice_closure._RecordingResidualProvider(Provider())
    result = await provider.solve_residual({"unresolved_fields": ["new"]})
    assert result["status"] == "solved"
    assert provider.model == "test-live"
    assert provider.packets[0]["unresolved_fields"] == ["new"]
