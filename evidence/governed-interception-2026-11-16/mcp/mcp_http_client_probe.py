"""Real MCP client probe over Streamable HTTP using the official `mcp` SDK."""
import asyncio, json, sys
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main(url):
    out = {"url": url}
    async with streamablehttp_client(url) as (r, w, _sid):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            out["initialize"] = {"protocolVersion": init.protocolVersion, "server": init.serverInfo.name}
            tools = await s.list_tools()
            out["tools_count"] = len(tools.tools)
            res = await s.call_tool("beast_mcp_status", {})
            out["call"] = {"tool": "beast_mcp_status", "isError": res.isError, "text_head": res.content[0].text[:300]}
    print(json.dumps(out, indent=1))

asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8766/mcp"))
