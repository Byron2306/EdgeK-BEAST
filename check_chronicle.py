import asyncio
from app.cli.api import BeastApiClient

async def test_chronicle():
    client = BeastApiClient()
    try:
        data = await client.get_json('/edgek/chronicle', {'limit': 30})
        print(data)
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(test_chronicle())
