"""Durable fail-closed custody for untrusted built-in MCP transport calls.

External server registrations remain governed by MCPBroker separately.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "mcp_builtin_custody.db"


def _digest(arguments: dict[str, Any]) -> str:
    # Store digest only, not sensitive tool arguments.
    canonical = json.dumps(arguments, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


def _write(db: Path, receipt: dict[str, Any]) -> None:
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db), timeout=5) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS builtin_tool_events (
            receipt_id TEXT PRIMARY KEY, timestamp REAL NOT NULL,
            tool_name TEXT NOT NULL, argument_digest TEXT NOT NULL,
            decision TEXT NOT NULL, outcome TEXT NOT NULL,
            error_type TEXT NOT NULL DEFAULT '')""")
        conn.execute("""INSERT INTO builtin_tool_events
            (receipt_id, timestamp, tool_name, argument_digest, decision, outcome, error_type)
            VALUES (:receipt_id, :timestamp, :tool_name, :argument_digest, :decision, :outcome, :error_type)""", receipt)


def dispatch_with_custody(runtime: Any, name: str, arguments: dict[str, Any] | None,
                          db_path: Path | None = None) -> dict[str, Any]:
    """Transport entrypoint: authorize, durably record, then dispatch.

    There is deliberately no trust in client-supplied `approved`. Until a
    request-bound approval verifier is integrated, mutation is refused.
    """
    args = arguments if isinstance(arguments, dict) else {}
    db = db_path or DB_PATH
    receipt = {
        "receipt_id": str(uuid.uuid4()), "timestamp": time.time(),
        "tool_name": str(name), "argument_digest": _digest(args),
        "decision": "deny", "outcome": "blocked", "error_type": "",
    }
    try:
        visible = {str(x.get("name")) for x in runtime.tool_definitions()}
        if name not in visible:
            reason = "tool not visible in active MCP profile"
        elif name in runtime._mutating_tools():
            reason = "mutation requires trusted, request-bound approval; client-supplied approved is insufficient"
        else:
            reason = None
            receipt["decision"] = "allow"
            receipt["outcome"] = "pending"
        # Fail closed if initial receipt cannot be persisted.
        _write(db, receipt)
        if reason is not None:
            return {"ok": False, "isError": True, "reason": reason,
                    "custody_receipt_id": receipt["receipt_id"]}
        try:
            result = runtime.call_tool(name, args)
            if not isinstance(result, dict):
                result = {"result": result}
            receipt["outcome"] = "failed" if result.get("ok") is False else "completed"
            _update(db, receipt)
            result.setdefault("custody_receipt_id", receipt["receipt_id"])
            return result
        except Exception as exc:
            receipt["outcome"] = "failed"
            receipt["error_type"] = type(exc).__name__
            _update(db, receipt)
            return {"ok": False, "isError": True, "reason": "tool execution failed",
                    "error_type": type(exc).__name__, "custody_receipt_id": receipt["receipt_id"]}
    except (OSError, sqlite3.Error) as exc:
        return {"ok": False, "isError": True, "reason": "MCP custody unavailable: execution refused",
                "error_type": type(exc).__name__}


def _update(db: Path, receipt: dict[str, Any]) -> None:
    with sqlite3.connect(str(db), timeout=5) as conn:
        conn.execute("""UPDATE builtin_tool_events SET outcome=:outcome,
                    error_type=:error_type WHERE receipt_id=:receipt_id""", receipt)


def read_custody_summary(db_path: Path | None = None) -> dict[str, Any]:
    db = db_path or DB_PATH
    if not db.exists():
        return {"total": 0, "status": "empty", "database": str(db)}
    with sqlite3.connect(str(db), timeout=5) as conn:
        rows = conn.execute("SELECT decision, outcome, COUNT(*) FROM builtin_tool_events GROUP BY decision, outcome").fetchall()
        return {"total": sum(x[2] for x in rows), "decisions": [
            {"decision": a, "outcome": b, "count": c} for a,b,c in rows], "database": str(db)}
