"""
EdgeK BEAST Gateway - MCP Broker
Evaluates MCP/tool requests against trust, approval, and command policies.
"""

import fnmatch
import hashlib
import json
import os
import shlex
import sqlite3
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import httpx

from app.kernel.tool_integrations import ToolCallInterceptor


class MCPDecision(Enum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


@dataclass
class MCPBrokerResult:
    request_id: str
    decision: MCPDecision
    server_class: str
    trust_level: str
    reason: str
    requires_approval: bool
    budget_multiplier: float
    policies_applied: list[str]
    approval_status: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "decision": self.decision.value,
            "server_class": self.server_class,
            "trust_level": self.trust_level,
            "reason": self.reason,
            "requires_approval": self.requires_approval,
            "budget_multiplier": self.budget_multiplier,
            "policies_applied": self.policies_applied,
            "approval_status": self.approval_status,
        }


class MCPBroker:
    """Policy-enforcing MCP broker with constrained local execution."""

    def __init__(
        self,
        policies: Optional[Dict[str, Any]] = None,
        db_path: Optional[str] = None,
        workspace_graph: Optional[Any] = None,
    ):
        self.policies = policies or {}
        if db_path is None:
            db_path = Path(__file__).resolve().parents[2] / "data" / "mcp_broker.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.workspace_graph = workspace_graph
        self._init_db()

    def _connect(self):
        return sqlite3.connect(str(self.db_path))

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mcp_servers (
                    name TEXT PRIMARY KEY,
                    server_class TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    metadata TEXT DEFAULT '{}',
                    registered_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mcp_audit_events (
                    request_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    server_class TEXT NOT NULL,
                    trust_level TEXT NOT NULL,
                    tool_name TEXT DEFAULT '',
                    action TEXT DEFAULT '',
                    target TEXT DEFAULT '',
                    command TEXT DEFAULT '',
                    reason TEXT NOT NULL,
                    requires_approval INTEGER NOT NULL,
                    budget_multiplier REAL NOT NULL,
                    policies_applied TEXT NOT NULL,
                    request TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mcp_audit_decision ON mcp_audit_events(decision)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mcp_audit_time ON mcp_audit_events(timestamp)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mcp_approvals (
                    request_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    requested_at TEXT NOT NULL,
                    resolved_at TEXT,
                    resolved_by TEXT,
                    resolution_reason TEXT DEFAULT '',
                    server_class TEXT NOT NULL,
                    trust_level TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    request TEXT NOT NULL,
                    result TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mcp_approvals_status ON mcp_approvals(status)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mcp_execution_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    executed INTEGER NOT NULL,
                    decision TEXT NOT NULL,
                    server_class TEXT NOT NULL,
                    tool_name TEXT DEFAULT '',
                    action TEXT DEFAULT '',
                    target TEXT DEFAULT '',
                    command TEXT DEFAULT '',
                    reason TEXT DEFAULT '',
                    returncode INTEGER,
                    request TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mcp_execution_request ON mcp_execution_events(request_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mcp_execution_time ON mcp_execution_events(timestamp)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mcp_tool_schema_pins (
                    server_name TEXT NOT NULL,
                    server_class TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    schema_hash TEXT NOT NULL,
                    schema TEXT NOT NULL,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    observation_count INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (server_name, server_class, tool_name)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mcp_schema_pins_tool ON mcp_tool_schema_pins(tool_name)")

    def register_server(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Register or update a known MCP server."""
        name = str(payload.get("name", "")).strip()
        server_class = str(payload.get("server_class", "")).strip()
        if not name:
            raise ValueError("MCP server name is required")
        if server_class not in self.policies.get("mcp_server_classes", {}):
            raise ValueError(f"Unknown MCP server class: {server_class}")

        now = self._utc_now()
        metadata = payload.get("metadata") or {}
        description = payload.get("description") or ""
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO mcp_servers (name, server_class, description, metadata, registered_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    server_class = excluded.server_class,
                    description = excluded.description,
                    metadata = excluded.metadata,
                    updated_at = excluded.updated_at
            """, (name, server_class, description, json.dumps(metadata, sort_keys=True), now, now))

        return {
            "name": name,
            "server_class": server_class,
            "description": description,
            "metadata": metadata,
            "registered_at": now,
            "updated_at": now
        }

    def list_servers(self) -> list[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT name, server_class, description, metadata, registered_at, updated_at
                FROM mcp_servers
                ORDER BY name
            """).fetchall()
        return [
            {
                "name": row[0],
                "server_class": row[1],
                "description": row[2],
                "metadata": json.loads(row[3] or "{}"),
                "registered_at": row[4],
                "updated_at": row[5]
            }
            for row in rows
        ]

    def evaluate(self, request: Dict[str, Any], audit: bool = True) -> MCPBrokerResult:
        """Evaluate a tool request against MCP governance policy."""
        request_id = str(request.get("request_id") or uuid.uuid4())
        server_class = request.get("server_class") or self._server_class_from_registration(request) or self._infer_server_class(request)
        server_policies = self.policies.get("mcp_server_classes", {})
        config = server_policies.get(server_class)

        if not config:
            result = MCPBrokerResult(
                request_id=request_id,
                decision=MCPDecision.DENY,
                server_class=server_class,
                trust_level="unknown",
                reason=f"Unknown MCP server class: {server_class}",
                requires_approval=True,
                budget_multiplier=10.0,
                policies_applied=["mcp_server_class_known"],
            )
            if audit:
                self._audit(request, result)
            return result

        policies_applied = [
            "mcp_server_class_known",
            f"mcp_{server_class}_trust_level",
            f"mcp_{server_class}_approval_policy",
            f"mcp_{server_class}_budget_multiplier",
        ]

        tool_name = request.get("tool_name")
        if tool_name:
            tool_schema = request.get("tool_schema")
            if tool_schema:
                is_valid, reason = self._pin_or_validate_tool_schema(request, server_class, str(tool_name), tool_schema)
                policies_applied.append("mcp_tool_schema_hash_pinning")
                if not is_valid:
                    result = MCPBrokerResult(
                        request_id=request_id,
                        decision=MCPDecision.DENY,
                        server_class=server_class,
                        trust_level=config.get("trust_level", "unknown"),
                        reason=reason,
                        requires_approval=True,
                        budget_multiplier=float(config.get("budget_multiplier", 1.0)),
                        policies_applied=policies_applied,
                    )
                    if audit:
                        self._audit(request, result)
                    return result

        if server_class == "shell":
            command_decision = self._evaluate_shell_command(request, config)
            policies_applied.extend(command_decision["policies_applied"])
            if command_decision["denied"]:
                result = MCPBrokerResult(
                    request_id=request_id,
                    decision=MCPDecision.DENY,
                    server_class=server_class,
                    trust_level=config.get("trust_level", "high"),
                    reason=command_decision["reason"],
                    requires_approval=True,
                    budget_multiplier=float(config.get("budget_multiplier", 5.0)),
                    policies_applied=policies_applied,
                )
                if audit:
                    self._audit(request, result)
                return result

        file_decision = self._evaluate_file_policy(request, server_class)
        policies_applied.extend(file_decision["policies_applied"])
        if file_decision["denied"]:
            result = MCPBrokerResult(
                request_id=request_id,
                decision=MCPDecision.DENY,
                server_class=server_class,
                trust_level=config.get("trust_level", "unknown"),
                reason=file_decision["reason"],
                requires_approval=True,
                budget_multiplier=float(config.get("budget_multiplier", 1.0)),
                policies_applied=policies_applied,
            )
            if audit:
                self._audit(request, result)
            return result
        if file_decision["requires_approval"]:
            config = dict(config)
            config["requires_approval"] = True

        if config.get("secrets_handling") == "never_log_or_transmit":
            policies_applied.append("mcp_secrets_never_log_or_transmit")

        requires_approval = bool(config.get("requires_approval", True))
        if requires_approval:
            decision = MCPDecision.REQUIRE_APPROVAL
            reason = f"MCP server class {server_class} requires approval"
            approval_status = "pending"
        else:
            decision = MCPDecision.ALLOW
            reason = f"MCP server class {server_class} allowed"
            approval_status = None

        result = MCPBrokerResult(
            request_id=request_id,
            decision=decision,
            server_class=server_class,
            trust_level=config.get("trust_level", "unknown"),
            reason=reason,
            requires_approval=requires_approval,
            budget_multiplier=float(config.get("budget_multiplier", 1.0)),
            policies_applied=policies_applied,
            approval_status=approval_status,
        )
        if audit:
            if result.decision == MCPDecision.REQUIRE_APPROVAL:
                self._create_pending_approval(request, result)
            self._audit(request, result)
        return result

    def execute(self, request: Dict[str, Any], workspace_root: Optional[str] = None) -> Dict[str, Any]:
        """Execute a narrowly supported MCP request after policy/approval checks."""
        result = self.evaluate(request)
        if result.decision == MCPDecision.DENY:
            return self._record_execution(request, result, {
                "request_id": result.request_id,
                "executed": False,
                "decision": result.decision.value,
                "reason": result.reason,
            })
        if result.decision == MCPDecision.REQUIRE_APPROVAL:
            approval = self.get_approval(result.request_id)
            if approval["status"] != "approved":
                return self._record_execution(request, result, {
                    "request_id": result.request_id,
                    "executed": False,
                    "decision": result.decision.value,
                    "approval_status": approval["status"],
                    "reason": "MCP request requires approval before execution",
                })

        server_class = result.server_class
        try:
            if server_class == "local_read_only":
                return self._record_execution(request, result, self._execute_read_file(request, result, workspace_root))
            if server_class == "shell":
                return self._record_execution(request, result, self._execute_shell(request, result, workspace_root))
            if server_class == "github":
                return self._record_execution(request, result, self._execute_github(request, result))
            if server_class == "postgres":
                return self._record_execution(request, result, self._execute_postgres(request, result))
            if server_class == "token_compressor":
                return self._record_execution(request, result, self._execute_token_compressor(request, result, workspace_root))
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            return self._record_execution(request, result, {
                "request_id": result.request_id,
                "executed": False,
                "decision": result.decision.value,
                "reason": str(exc),
            })
        return self._record_execution(request, result, {
            "request_id": result.request_id,
            "executed": False,
            "decision": result.decision.value,
            "reason": f"Execution not implemented for MCP server class {server_class}",
        })

    def stats(self) -> Dict[str, Any]:
        with self._connect() as conn:
            total_servers = conn.execute("SELECT COUNT(*) FROM mcp_servers").fetchone()[0]
            total_events = conn.execute("SELECT COUNT(*) FROM mcp_audit_events").fetchone()[0]
            total_execution_events = conn.execute("SELECT COUNT(*) FROM mcp_execution_events").fetchone()[0]
            total_schema_pins = conn.execute("SELECT COUNT(*) FROM mcp_tool_schema_pins").fetchone()[0]
            decisions = conn.execute("SELECT decision, COUNT(*) FROM mcp_audit_events GROUP BY decision").fetchall()
            classes = conn.execute("SELECT server_class, COUNT(*) FROM mcp_audit_events GROUP BY server_class").fetchall()
            executions = conn.execute("""
                SELECT executed, COUNT(*) FROM mcp_execution_events GROUP BY executed
            """).fetchall()
        return {
            "registered_servers": total_servers,
            "audit_events": total_events,
            "execution_events": total_execution_events,
            "schema_pins": total_schema_pins,
            "pending_approvals": self._approval_count("pending"),
            "decisions": {row[0]: row[1] for row in decisions},
            "server_classes": {row[0]: row[1] for row in classes},
            "executions": {
                "executed": sum(row[1] for row in executions if row[0] == 1),
                "blocked": sum(row[1] for row in executions if row[0] == 0),
            },
            "audit_db": str(self.db_path)
        }

    def list_schema_pins(self, limit: int = 100) -> list[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT server_name, server_class, tool_name, schema_hash, first_seen, last_seen, observation_count
                FROM mcp_tool_schema_pins
                ORDER BY last_seen DESC
                LIMIT ?
            """, (max(1, min(limit, 500)),)).fetchall()
        return [
            {
                "server_name": row[0],
                "server_class": row[1],
                "tool_name": row[2],
                "schema_hash": row[3],
                "first_seen": row[4],
                "last_seen": row[5],
                "observation_count": row[6],
            }
            for row in rows
        ]

    def list_approvals(self, status: Optional[str] = None, limit: int = 20) -> list[Dict[str, Any]]:
        params: list[Any] = []
        where = ""
        if status:
            where = "WHERE status = ?"
            params.append(status)
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(f"""
                SELECT request_id, status, requested_at, resolved_at, resolved_by,
                       resolution_reason, server_class, trust_level, reason, request, result
                FROM mcp_approvals
                {where}
                ORDER BY requested_at DESC
                LIMIT ?
            """, params).fetchall()
        return [
            {
                "request_id": row[0],
                "status": row[1],
                "requested_at": row[2],
                "resolved_at": row[3],
                "resolved_by": row[4],
                "resolution_reason": row[5],
                "server_class": row[6],
                "trust_level": row[7],
                "reason": row[8],
                "request": json.loads(row[9] or "{}"),
                "result": json.loads(row[10] or "{}"),
            }
            for row in rows
        ]

    def resolve_approval(
        self,
        request_id: str,
        approved: bool,
        resolved_by: str = "system",
        reason: str = ""
    ) -> Dict[str, Any]:
        status = "approved" if approved else "denied"
        now = self._utc_now()
        with self._connect() as conn:
            row = conn.execute("""
                SELECT request_id, status FROM mcp_approvals WHERE request_id = ?
            """, (request_id,)).fetchone()
            if not row:
                raise ValueError(f"Approval request not found: {request_id}")
            if row[1] != "pending":
                raise ValueError(f"Approval request already resolved: {request_id}")
            conn.execute("""
                UPDATE mcp_approvals
                SET status = ?, resolved_at = ?, resolved_by = ?, resolution_reason = ?
                WHERE request_id = ?
            """, (status, now, resolved_by, reason, request_id))
        return self.get_approval(request_id)

    def get_approval(self, request_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("""
                SELECT request_id, status, requested_at, resolved_at, resolved_by,
                       resolution_reason, server_class, trust_level, reason, request, result
                FROM mcp_approvals
                WHERE request_id = ?
            """, (request_id,)).fetchone()
        if not row:
            raise ValueError(f"Approval request not found: {request_id}")
        return {
            "request_id": row[0],
            "status": row[1],
            "requested_at": row[2],
            "resolved_at": row[3],
            "resolved_by": row[4],
            "resolution_reason": row[5],
            "server_class": row[6],
            "trust_level": row[7],
            "reason": row[8],
            "request": json.loads(row[9] or "{}"),
            "result": json.loads(row[10] or "{}"),
        }

    def recent_audit_events(self, limit: int = 20) -> list[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT request_id, timestamp, decision, server_class, trust_level,
                       tool_name, action, target, command, reason, requires_approval,
                       budget_multiplier, policies_applied
                FROM mcp_audit_events
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,)).fetchall()
        return [
            {
                "request_id": row[0],
                "timestamp": row[1],
                "decision": row[2],
                "server_class": row[3],
                "trust_level": row[4],
                "tool_name": row[5],
                "action": row[6],
                "target": row[7],
                "command": row[8],
                "reason": row[9],
                "requires_approval": bool(row[10]),
                "budget_multiplier": row[11],
                "policies_applied": json.loads(row[12] or "[]")
            }
            for row in rows
        ]

    def recent_execution_events(self, limit: int = 20) -> list[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT request_id, timestamp, executed, decision, server_class,
                       tool_name, action, target, command, reason, returncode
                FROM mcp_execution_events
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
            """, (limit,)).fetchall()
        return [
            {
                "request_id": row[0],
                "timestamp": row[1],
                "executed": bool(row[2]),
                "decision": row[3],
                "server_class": row[4],
                "tool_name": row[5],
                "action": row[6],
                "target": row[7],
                "command": row[8],
                "reason": row[9],
                "returncode": row[10],
            }
            for row in rows
        ]

    def _infer_server_class(self, request: Dict[str, Any]) -> str:
        tool_name = str(request.get("tool_name", "")).lower()
        action = str(request.get("action", "")).lower()
        command = str(request.get("command", "")).lower()
        target = str(request.get("target", "")).lower()

        text = " ".join([tool_name, action, command, target])
        if "secret" in text or "credential" in text or "keyvault" in text:
            return "secrets"
        if command or "shell" in text or "terminal" in text:
            return "shell"
        if "github" in text or "gh " in text or "pull_request" in text or "issue" in text:
            return "github"
        if "postgres" in text or "postgresql" in text or "psql" in text:
            return "postgres"
        if any(word in text for word in ["rtk", "sqz", "longcodezip", "reporelay", "compress", "prune"]):
            return "token_compressor"
        if "sql" in text or "database" in text or "db" in text:
            return "database"
        if "http" in target or "network" in text or "fetch" in text:
            return "network"
        if any(word in text for word in ["write", "edit", "patch", "delete", "create"]):
            return "local_write"
        return "local_read_only"

    def _server_class_from_registration(self, request: Dict[str, Any]) -> Optional[str]:
        server_name = request.get("server_name")
        if not server_name:
            return None
        with self._connect() as conn:
            row = conn.execute("SELECT server_class FROM mcp_servers WHERE name = ?", (server_name,)).fetchone()
        return row[0] if row else None

    def _evaluate_shell_command(self, request: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        command = str(request.get("command") or request.get("input") or "").strip()
        denied_patterns = config.get("denied_commands", [])
        allowed_patterns = config.get("allowed_commands", [])
        policies_applied = ["mcp_shell_denied_commands", "mcp_shell_allowed_commands"]

        for pattern in denied_patterns:
            if self._command_matches(command, pattern):
                return {
                    "denied": True,
                    "reason": f"Shell command denied by policy: {pattern}",
                    "policies_applied": policies_applied,
                }

        if allowed_patterns and not any(self._command_matches(command, pattern) for pattern in allowed_patterns):
            return {
                "denied": True,
                "reason": "Shell command is not in the allowed command policy",
                "policies_applied": policies_applied,
            }

        return {
            "denied": False,
            "reason": "Shell command passed command policy",
            "policies_applied": policies_applied,
        }

    def _command_matches(self, command: str, pattern: str) -> bool:
        return command == pattern or command.startswith(pattern + " ") or fnmatch.fnmatch(command, pattern)

    def _evaluate_file_policy(self, request: Dict[str, Any], server_class: str) -> Dict[str, Any]:
        target = str(request.get("target", "")).strip()
        if not target or server_class not in ("local_read_only", "local_write"):
            return {"denied": False, "requires_approval": False, "policies_applied": []}

        policies = self.policies.get("file_operations", {})
        blocked = policies.get("blocked_patterns", [])
        approval_required = policies.get("approval_required_patterns", [])
        safe_reads = policies.get("safe_read_patterns", [])
        policies_applied = ["file_blocked_patterns", "file_approval_required_patterns"]

        for pattern in blocked:
            if fnmatch.fnmatch(target, pattern):
                return {
                    "denied": True,
                    "requires_approval": True,
                    "reason": f"File target denied by policy: {pattern}",
                    "policies_applied": policies_applied,
                }

        requires_approval = server_class == "local_write"
        for pattern in approval_required:
            if fnmatch.fnmatch(target, pattern):
                requires_approval = True
                break

        if server_class == "local_read_only" and safe_reads:
            policies_applied.append("file_safe_read_patterns")

        return {
            "denied": False,
            "requires_approval": requires_approval,
            "reason": "File target passed policy",
            "policies_applied": policies_applied,
        }

    def _compute_tool_schema_hash(self, tool_schema: Dict[str, Any]) -> str:
        """Compute SHA256 hash of a tool schema for pinning."""
        # Sort keys for deterministic hashing
        schema_json = json.dumps(tool_schema, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(schema_json.encode('utf-8')).hexdigest()

    def _pin_or_validate_tool_schema(
        self,
        request: Dict[str, Any],
        server_class: str,
        tool_name: str,
        tool_schema: Dict[str, Any],
    ) -> Tuple[bool, str]:
        """Pin first schema observation, then enforce immutable schema hash."""
        mcp_policy = self.policies.get("meta_rules", {})
        if not mcp_policy.get("mcp_schema_pinning_enabled", True):
            return True, "MCP schema pinning disabled"
        server_name = str(request.get("server_name") or request.get("server_class") or server_class)
        schema_hash = self._compute_tool_schema_hash(tool_schema)
        now = self._utc_now()
        schema_json = json.dumps(tool_schema, sort_keys=True, separators=(",", ":"))
        with self._connect() as conn:
            existing = conn.execute("""
                SELECT schema_hash FROM mcp_tool_schema_pins
                WHERE server_name = ? AND server_class = ? AND tool_name = ?
            """, (server_name, server_class, tool_name)).fetchone()
            if existing:
                pinned_hash = existing[0]
                if pinned_hash != schema_hash:
                    return (
                        False,
                        f"MCP tool schema hash mismatch for {server_name}.{tool_name}: "
                        f"expected {pinned_hash[:16]}..., got {schema_hash[:16]}..."
                    )
                conn.execute("""
                    UPDATE mcp_tool_schema_pins
                    SET last_seen = ?, observation_count = observation_count + 1
                    WHERE server_name = ? AND server_class = ? AND tool_name = ?
                """, (now, server_name, server_class, tool_name))
                return True, f"MCP tool schema hash matched pin {schema_hash[:16]}..."

            if not mcp_policy.get("mcp_schema_trust_on_first_use", True):
                return False, f"No pinned MCP schema exists for {server_name}.{tool_name}"
            conn.execute("""
                INSERT INTO mcp_tool_schema_pins
                (server_name, server_class, tool_name, schema_hash, schema, first_seen, last_seen, observation_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """, (server_name, server_class, tool_name, schema_hash, schema_json, now, now))
        return True, f"MCP tool schema pinned for {server_name}.{tool_name}: {schema_hash[:16]}..."

    def _audit(self, request: Dict[str, Any], result: MCPBrokerResult):
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO mcp_audit_events
                (request_id, timestamp, decision, server_class, trust_level, tool_name, action,
                 target, command, reason, requires_approval, budget_multiplier, policies_applied, request)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result.request_id,
                self._utc_now(),
                result.decision.value,
                result.server_class,
                result.trust_level,
                str(request.get("tool_name", "")),
                str(request.get("action", "")),
                str(request.get("target", "")),
                str(request.get("command", "")),
                result.reason,
                1 if result.requires_approval else 0,
                result.budget_multiplier,
                json.dumps(result.policies_applied),
                json.dumps(self._redact_request(request), sort_keys=True),
            ))

    def _create_pending_approval(self, request: Dict[str, Any], result: MCPBrokerResult):
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT status FROM mcp_approvals WHERE request_id = ?",
                (result.request_id,)
            ).fetchone()
            if existing:
                return
            conn.execute("""
                INSERT INTO mcp_approvals
                (request_id, status, requested_at, server_class, trust_level, reason, request, result)
                VALUES (?, 'pending', ?, ?, ?, ?, ?, ?)
            """, (
                result.request_id,
                self._utc_now(),
                result.server_class,
                result.trust_level,
                result.reason,
                json.dumps(self._redact_request(request), sort_keys=True),
                json.dumps(result.to_dict(), sort_keys=True),
            ))

    def _record_execution(
        self,
        request: Dict[str, Any],
        result: MCPBrokerResult,
        response: Dict[str, Any],
    ) -> Dict[str, Any]:
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO mcp_execution_events
                (request_id, timestamp, executed, decision, server_class, tool_name, action,
                 target, command, reason, returncode, request)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result.request_id,
                self._utc_now(),
                1 if response.get("executed") else 0,
                str(response.get("decision", result.decision.value)),
                result.server_class,
                str(request.get("tool_name", "")),
                str(request.get("action", "")),
                str(request.get("target", "")),
                str(request.get("command", "")),
                str(response.get("reason", "")),
                response.get("returncode"),
                json.dumps(self._redact_request(request), sort_keys=True),
            ))
        return response

    def _approval_count(self, status: str) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM mcp_approvals WHERE status = ?", (status,)).fetchone()
        return row[0] or 0

    def _redact_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        redacted = {}
        for key, value in request.items():
            if any(secret_word in key.lower() for secret_word in ("secret", "token", "password", "api_key")):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = value
        return redacted

    def _execute_read_file(
        self,
        request: Dict[str, Any],
        result: MCPBrokerResult,
        workspace_root: Optional[str]
    ) -> Dict[str, Any]:
        target = self._resolve_workspace_path(request.get("target", ""), workspace_root)
        if not target.exists() or not target.is_file():
            return {
                "request_id": result.request_id,
                "executed": False,
                "decision": result.decision.value,
                "reason": "File target does not exist or is not a file",
            }
        max_bytes = int(request.get("max_bytes", 20000))
        query_text = request.get("query") or request.get("objective") or request.get("reason")
        cached = None
        if self.workspace_graph is not None:
            cached = self.workspace_graph.get_file_content_cached(
                str(target),
                max_bytes=max_bytes,
                query_text=str(query_text) if query_text else None,
                semantic_limit=int(request.get("semantic_limit", 3)),
            )
        if cached:
            data = cached["content"]
            cache_hit = bool(cached["cache_hit"])
            cache_source = cached["source"]
            content_hash = cached["content_hash"]
        else:
            data = target.read_text(encoding="utf-8", errors="replace")[:max_bytes]
            cache_hit = False
            cache_source = "disk_uncached"
            content_hash = hashlib.sha256(data.encode("utf-8")).hexdigest()
        return {
            "request_id": result.request_id,
            "executed": True,
            "decision": result.decision.value,
            "server_class": result.server_class,
            "target": str(target),
            "bytes_returned": len(data.encode("utf-8")),
            "cache_hit": cache_hit,
            "cache_source": cache_source,
            "content_hash": content_hash,
            "content": data,
            "semantic_related": cached.get("semantic_related", []) if cached else [],
        }

    def _execute_shell(
        self,
        request: Dict[str, Any],
        result: MCPBrokerResult,
        workspace_root: Optional[str]
    ) -> Dict[str, Any]:
        command = str(request.get("command") or request.get("input") or "").strip()
        cwd = self._resolve_workspace_path(request.get("cwd", "."), workspace_root)
        if not cwd.exists() or not cwd.is_dir():
            cwd = Path(workspace_root or ".").resolve()
        completed = subprocess.run(
            shlex.split(command),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=int(request.get("timeout_seconds", 30)),
            check=False,
        )
        return {
            "request_id": result.request_id,
            "executed": True,
            "decision": result.decision.value,
            "server_class": result.server_class,
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-20000:],
            "stderr": completed.stderr[-20000:],
        }

    def _execute_github(self, request: Dict[str, Any], result: MCPBrokerResult) -> Dict[str, Any]:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            return {
                "request_id": result.request_id,
                "executed": False,
                "decision": result.decision.value,
                "reason": "GITHUB_TOKEN is required for GitHub tool calls",
            }
        action = str(request.get("action") or request.get("tool_name") or "repo").lower()
        repo = str(request.get("repo") or request.get("repository") or "").strip()
        if not repo or "/" not in repo:
            raise ValueError("GitHub repo must be owner/name")
        path = str(request.get("path") or "").strip()
        if "content" in action or path:
            endpoint = f"https://api.github.com/repos/{repo}/contents/{path}"
        elif "issue" in action:
            endpoint = f"https://api.github.com/repos/{repo}/issues"
        elif "pull" in action or "pr" in action:
            endpoint = f"https://api.github.com/repos/{repo}/pulls"
        else:
            endpoint = f"https://api.github.com/repos/{repo}"
        response = httpx.get(
            endpoint,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=20.0,
        )
        return {
            "request_id": result.request_id,
            "executed": response.status_code < 400,
            "decision": result.decision.value,
            "server_class": result.server_class,
            "endpoint": endpoint,
            "status_code": response.status_code,
            "content": response.text[:20000],
            "reason": "GitHub request completed" if response.status_code < 400 else "GitHub request failed",
        }

    def _execute_postgres(self, request: Dict[str, Any], result: MCPBrokerResult) -> Dict[str, Any]:
        dsn = os.environ.get("POSTGRES_DSN")
        query = str(request.get("query") or request.get("sql") or "").strip()
        if not query.lower().startswith(("select", "with", "show", "explain")):
            raise ValueError("Only read-only Postgres queries are allowed")
        try:
            import psycopg  # type: ignore
        except ImportError:
            return {
                "request_id": result.request_id,
                "executed": False,
                "decision": result.decision.value,
                "reason": "psycopg is required for Postgres tool calls",
            }
        limit = max(1, min(int(request.get("limit", 100)), 1000))
        connect_kwargs = {"connect_timeout": 10}
        if not dsn:
            connect_kwargs.update({"host": "/var/run/postgresql", "dbname": request.get("database") or "postgres"})
        with psycopg.connect(dsn or "", **connect_kwargs) as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                columns = [desc.name for desc in cur.description] if cur.description else []
                rows = cur.fetchmany(limit) if columns else []
        return {
            "request_id": result.request_id,
            "executed": True,
            "decision": result.decision.value,
            "server_class": result.server_class,
            "columns": columns,
            "rows": [list(row) for row in rows],
            "row_count": len(rows),
            "reason": "Postgres read-only query completed",
        }

    def _execute_token_compressor(
        self,
        request: Dict[str, Any],
        result: MCPBrokerResult,
        workspace_root: Optional[str],
    ) -> Dict[str, Any]:
        interceptor = ToolCallInterceptor(self.workspace_graph, self.policies)
        text = request.get("text") or request.get("content") or request.get("source")
        if not isinstance(text, str) and request.get("target"):
            read_result = interceptor.intercept_read_file(request, workspace_root or ".")
            text = read_result.get("content", "")
        if not isinstance(text, str):
            raise ValueError("Token compressor requires text/content/source or target")
        compressed = interceptor.compress_text(text, algorithm=str(request.get("algorithm") or request.get("tool_name") or "edgek_prune"))
        compressed.update({
            "request_id": result.request_id,
            "executed": True,
            "decision": result.decision.value,
            "server_class": result.server_class,
        })
        return compressed

    def _resolve_workspace_path(self, target: str, workspace_root: Optional[str]) -> Path:
        root = Path(workspace_root or ".").resolve()
        path = Path(str(target))
        if path.is_absolute():
            resolved = path.resolve()
        else:
            resolved = (root / path).resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            raise ValueError("Target path escapes workspace root")
        return resolved

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
