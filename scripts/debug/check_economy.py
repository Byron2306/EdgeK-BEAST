import asyncio
from app.cli.api import BeastApiClient

async def test_economy():
    client = BeastApiClient()
    try:
        data = await client.get_json('/edgek/commons-economy')
        print(data)
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(test_economy())
