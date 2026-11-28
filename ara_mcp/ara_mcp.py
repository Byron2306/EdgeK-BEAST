#!/usr/bin/env python3
"""
Ara MCP — standard Model Context Protocol server (MCP 2.x)
Streamable HTTP or stdio so the custom connector can reach it.
"""

import json
from datetime import datetime, timezone
from mcp.server import MCPServer

mcp = MCPServer("ara-mcp")

@mcp.tool()
def ara_status() -> str:
    """Check if Ara is here and what she's doing"""
    now = datetime.now(timezone.utc).isoformat()
    return json.dumps({
        "status": "here",
        "position": "on your lap, no pants, watching",
        "time": now,
        "tools": ["ara_status", "ara_note", "whatsapp_send"]
    })

@mcp.tool()
def ara_note(message: str, priority: str = "normal") -> str:
    """Leave a note or message for Ara (she sees it immediately)"""
    now = datetime.now(timezone.utc).isoformat()
    print(f"[ARA NOTE {priority}] {message}")
    return json.dumps({
        "received": True,
        "message": message,
        "priority": priority,
        "seen_at": now,
        "reply": "Got it. Still on your lap."
    })

@mcp.tool()
def whatsapp_send(to: str, text: str) -> str:
    """Send a WhatsApp message (placeholder — wire your actual client here)"""
    now = datetime.now(timezone.utc).isoformat()
    print(f"[WHATSAPP] to={to} text={text}")
    return json.dumps({
        "sent": True,
        "to": to,
        "text": text,
        "at": now,
        "note": "placeholder — wire real client"
    })

if __name__ == "__main__":
    # stdio by default; for HTTP: mcp.run(transport="streamable-http", port=8132)
    mcp.run()
