"""Real MCP client probe using the official `mcp` SDK (stdio transport)."""
import asyncio, json, sys, os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

async def main(tool: str, args: dict, timeout: float):
    params = StdioServerParameters(command=os.path.join(ROOT, ".venv/bin/python"), args=[os.path.join(ROOT, "bin/beast"), "mcp", "--workspace", ROOT], cwd=ROOT, env={**os.environ, "BEAST_GATEWAY_URL": "http://127.0.0.1:8101"})
    out = {}
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            init = await asyncio.wait_for(s.initialize(), timeout)
            out["initialize"] = {"protocolVersion": init.protocolVersion, "serverInfo": init.serverInfo.model_dump()}
            tools = await asyncio.wait_for(s.list_tools(), timeout)
            out["tools_count"] = len(tools.tools)
            out["tools"] = [t.name for t in tools.tools]
            if tool:
                res = await asyncio.wait_for(s.call_tool(tool, args), timeout * 4)
                out["call"] = {"tool": tool, "isError": res.isError, "text_head": (res.content[0].text if res.content else "")[:800]}
    print(json.dumps(out, indent=1))

if __name__ == "__main__":
    tool = sys.argv[1] if len(sys.argv) > 1 else ""
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    asyncio.run(main(tool, args, float(os.environ.get("PROBE_TIMEOUT", "20"))))
