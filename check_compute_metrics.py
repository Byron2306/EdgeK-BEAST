import asyncio
from app.cli.api import BeastApiClient

async def test_compute_metrics():
    client = BeastApiClient()
    try:
        data = await client.get_json('/edgek/compute/metrics', {'limit': 500})
        print(data)
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(test_compute_metrics())
