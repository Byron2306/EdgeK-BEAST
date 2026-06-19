"""
EdgeK BEAST Gateway - Team and Enterprise Mode
Local-first enterprise controls: users, teams, virtual keys, per-team budgets,
centralized observability, policy packs, and sealed trace storage.
"""

import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import uuid
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


@dataclass
class AuthContext:
    team_id: str
    user_id: str
    key_id: str
    scopes: List[str]


class EnterpriseManager:
    """Durable local enterprise control plane."""

    def __init__(self, policies: Optional[Dict[str, Any]] = None, db_path: Optional[str] = None):
        self.policies = policies or {}
        if db_path is None:
            db_path = Path(__file__).resolve().parents[2] / "data" / "enterprise.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(str(self.db_path))

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS teams (
                    team_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    daily_request_limit INTEGER NOT NULL,
                    daily_cost_limit_usd REAL NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    team_id TEXT NOT NULL,
                    email TEXT NOT NULL,
                    role TEXT NOT NULL,
                    active INTEGER NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_enterprise_users_team ON users(team_id)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS virtual_keys (
                    key_id TEXT PRIMARY KEY,
                    team_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    key_hash TEXT NOT NULL,
                    scopes TEXT NOT NULL,
                    active INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT
                )
            """)
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_enterprise_key_hash ON virtual_keys(key_hash)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS team_usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    team_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    key_id TEXT DEFAULT '',
                    provider TEXT DEFAULT '',
                    model TEXT DEFAULT '',
                    request_count INTEGER NOT NULL,
                    estimated_cost_usd REAL NOT NULL,
                    total_tokens INTEGER NOT NULL,
                    day TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_enterprise_usage_team_day ON team_usage_events(team_id, day)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS observability_events (
                    event_id TEXT PRIMARY KEY,
                    team_id TEXT NOT NULL,
                    user_id TEXT DEFAULT '',
                    event_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    trace_id TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_enterprise_observability_team ON observability_events(team_id, created_at)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS policy_packs (
                    pack_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    policy_overlay TEXT NOT NULL,
                    active INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS team_policy_packs (
                    team_id TEXT NOT NULL,
                    pack_id TEXT NOT NULL,
                    assigned_at TEXT NOT NULL,
                    PRIMARY KEY (team_id, pack_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS encrypted_traces (
                    trace_id TEXT PRIMARY KEY,
                    team_id TEXT NOT NULL,
                    user_id TEXT DEFAULT '',
                    nonce TEXT NOT NULL,
                    ciphertext TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

    def create_team(
        self,
        name: str,
        team_id: Optional[str] = None,
        daily_request_limit: Optional[int] = None,
        daily_cost_limit_usd: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        team_id = team_id or f"team_{uuid.uuid4().hex[:12]}"
        now = _utc_now()
        enterprise_policy = self.policies.get("enterprise", {})
        daily_request_limit = int(daily_request_limit or enterprise_policy.get("default_daily_request_limit", 1000))
        daily_cost_limit_usd = float(daily_cost_limit_usd or enterprise_policy.get("default_daily_cost_limit_usd", 25.0))
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO teams
                (team_id, name, daily_request_limit, daily_cost_limit_usd, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                team_id,
                name,
                daily_request_limit,
                daily_cost_limit_usd,
                json.dumps(metadata or {}, sort_keys=True),
                now,
                now,
            ))
        return self.get_team(team_id)

    def get_team(self, team_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("""
                SELECT team_id, name, daily_request_limit, daily_cost_limit_usd, metadata, created_at, updated_at
                FROM teams
                WHERE team_id = ?
            """, (team_id,)).fetchone()
        if not row:
            raise ValueError(f"Team not found: {team_id}")
        return {
            "team_id": row[0],
            "name": row[1],
            "daily_request_limit": row[2],
            "daily_cost_limit_usd": row[3],
            "metadata": json.loads(row[4] or "{}"),
            "created_at": row[5],
            "updated_at": row[6],
        }

    def list_teams(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT team_id, name, daily_request_limit, daily_cost_limit_usd, metadata, created_at, updated_at
                FROM teams
                ORDER BY created_at DESC
            """).fetchall()
        return [
            {
                "team_id": row[0],
                "name": row[1],
                "daily_request_limit": row[2],
                "daily_cost_limit_usd": row[3],
                "metadata": json.loads(row[4] or "{}"),
                "created_at": row[5],
                "updated_at": row[6],
            }
            for row in rows
        ]

    def create_user(
        self,
        team_id: str,
        email: str,
        role: str = "member",
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self.get_team(team_id)
        user_id = user_id or f"user_{uuid.uuid4().hex[:12]}"
        now = _utc_now()
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO users
                (user_id, team_id, email, role, active, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, ?, ?, ?)
            """, (
                user_id,
                team_id,
                email,
                role,
                json.dumps(metadata or {}, sort_keys=True),
                now,
                now,
            ))
        return self.get_user(user_id)

    def get_user(self, user_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("""
                SELECT user_id, team_id, email, role, active, metadata, created_at, updated_at
                FROM users
                WHERE user_id = ?
            """, (user_id,)).fetchone()
        if not row:
            raise ValueError(f"User not found: {user_id}")
        return {
            "user_id": row[0],
            "team_id": row[1],
            "email": row[2],
            "role": row[3],
            "active": bool(row[4]),
            "metadata": json.loads(row[5] or "{}"),
            "created_at": row[6],
            "updated_at": row[7],
        }

    def issue_virtual_key(
        self,
        team_id: str,
        user_id: str,
        scopes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        self.get_team(team_id)
        user = self.get_user(user_id)
        if user["team_id"] != team_id:
            raise ValueError("User does not belong to team")
        key_id = f"vk_{uuid.uuid4().hex[:12]}"
        secret = f"ek_{secrets.token_urlsafe(32)}"
        key_hash = self._hash_key(secret)
        scopes = scopes or ["gateway:use"]
        now = _utc_now()
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO virtual_keys
                (key_id, team_id, user_id, key_hash, scopes, active, created_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)
            """, (
                key_id,
                team_id,
                user_id,
                key_hash,
                json.dumps(scopes, sort_keys=True),
                now,
            ))
        return {
            "key_id": key_id,
            "team_id": team_id,
            "user_id": user_id,
            "scopes": scopes,
            "virtual_key": secret,
            "created_at": now,
        }

    def authenticate_virtual_key(self, virtual_key: str, required_scope: Optional[str] = None) -> AuthContext:
        key_hash = self._hash_key(virtual_key)
        with self._connect() as conn:
            row = conn.execute("""
                SELECT key_id, team_id, user_id, scopes, active
                FROM virtual_keys
                WHERE key_hash = ?
            """, (key_hash,)).fetchone()
            if not row or not row[4]:
                raise ValueError("Invalid or inactive virtual key")
            scopes = json.loads(row[3] or "[]")
            if required_scope and required_scope not in scopes and "*" not in scopes:
                raise ValueError(f"Virtual key missing required scope: {required_scope}")
            conn.execute("UPDATE virtual_keys SET last_used_at = ? WHERE key_id = ?", (_utc_now(), row[0]))
        return AuthContext(team_id=row[1], user_id=row[2], key_id=row[0], scopes=scopes)

    def record_team_usage(
        self,
        team_id: str,
        user_id: str,
        key_id: str = "",
        provider: str = "",
        model: str = "",
        request_count: int = 1,
        estimated_cost_usd: float = 0.0,
        total_tokens: int = 0,
    ) -> Dict[str, Any]:
        self.get_team(team_id)
        now = _utc_now()
        day = now[:10]
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO team_usage_events
                (team_id, user_id, key_id, provider, model, request_count, estimated_cost_usd,
                 total_tokens, day, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                team_id,
                user_id,
                key_id,
                provider,
                model,
                int(request_count),
                float(estimated_cost_usd),
                int(total_tokens),
                day,
                now,
            ))
        return self.team_budget_summary(team_id, day=day)

    def team_budget_summary(self, team_id: str, day: Optional[str] = None) -> Dict[str, Any]:
        team = self.get_team(team_id)
        day = day or _utc_now()[:10]
        with self._connect() as conn:
            row = conn.execute("""
                SELECT COALESCE(SUM(request_count), 0), COALESCE(SUM(estimated_cost_usd), 0.0),
                       COALESCE(SUM(total_tokens), 0)
                FROM team_usage_events
                WHERE team_id = ? AND day = ?
            """, (team_id, day)).fetchone()
        requests = int(row[0] or 0)
        cost = float(row[1] or 0.0)
        tokens = int(row[2] or 0)
        return {
            "team_id": team_id,
            "day": day,
            "requests": requests,
            "estimated_cost_usd": cost,
            "total_tokens": tokens,
            "daily_request_limit": team["daily_request_limit"],
            "daily_cost_limit_usd": team["daily_cost_limit_usd"],
            "within_budget": requests <= team["daily_request_limit"] and cost <= team["daily_cost_limit_usd"],
            "remaining_requests": max(0, team["daily_request_limit"] - requests),
            "remaining_cost_usd": max(0.0, team["daily_cost_limit_usd"] - cost),
        }

    def check_team_budget(self, team_id: str, projected_requests: int = 1, projected_cost_usd: float = 0.0) -> Dict[str, Any]:
        summary = self.team_budget_summary(team_id)
        allowed = (
            summary["requests"] + projected_requests <= summary["daily_request_limit"]
            and summary["estimated_cost_usd"] + projected_cost_usd <= summary["daily_cost_limit_usd"]
        )
        return {
            **summary,
            "projected_requests": projected_requests,
            "projected_cost_usd": projected_cost_usd,
            "allowed": allowed,
            "reason": "Team budget allows request" if allowed else "Team budget would be exceeded",
        }

    def record_observability_event(
        self,
        team_id: str,
        event_type: str,
        severity: str = "info",
        payload: Optional[Dict[str, Any]] = None,
        user_id: str = "",
        trace_id: str = "",
    ) -> Dict[str, Any]:
        self.get_team(team_id)
        event_id = f"obs_{uuid.uuid4().hex[:12]}"
        now = _utc_now()
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO observability_events
                (event_id, team_id, user_id, event_type, severity, payload, trace_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event_id,
                team_id,
                user_id,
                event_type,
                severity,
                json.dumps(payload or {}, sort_keys=True),
                trace_id,
                now,
            ))
        return {
            "event_id": event_id,
            "team_id": team_id,
            "user_id": user_id,
            "event_type": event_type,
            "severity": severity,
            "payload": payload or {},
            "trace_id": trace_id,
            "created_at": now,
        }

    def observability_events(self, team_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        params: List[Any] = []
        where = ""
        if team_id:
            where = "WHERE team_id = ?"
            params.append(team_id)
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(f"""
                SELECT event_id, team_id, user_id, event_type, severity, payload, trace_id, created_at
                FROM observability_events
                {where}
                ORDER BY created_at DESC
                LIMIT ?
            """, params).fetchall()
        return [
            {
                "event_id": row[0],
                "team_id": row[1],
                "user_id": row[2],
                "event_type": row[3],
                "severity": row[4],
                "payload": json.loads(row[5] or "{}"),
                "trace_id": row[6],
                "created_at": row[7],
            }
            for row in rows
        ]

    def otel_export(self, team_id: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
        events = self.observability_events(team_id=team_id, limit=limit)
        return {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "edgek-beast-gateway"}},
                            {"key": "edgek.team_id", "value": {"stringValue": event["team_id"]}},
                        ]
                    },
                    "scopeSpans": [
                        {
                            "scope": {"name": "edgek.enterprise"},
                            "spans": [
                                {
                                    "traceId": hashlib.sha256((event["trace_id"] or event["event_id"]).encode()).hexdigest()[:32],
                                    "spanId": hashlib.sha256(event["event_id"].encode()).hexdigest()[:16],
                                    "name": event["event_type"],
                                    "attributes": [
                                        {"key": "severity", "value": {"stringValue": event["severity"]}},
                                        {"key": "user_id", "value": {"stringValue": event["user_id"]}},
                                    ],
                                }
                            ],
                        }
                    ],
                }
                for event in events
            ]
        }

    def register_policy_pack(
        self,
        name: str,
        policy_overlay: Dict[str, Any],
        version: str = "1.0.0",
        pack_id: Optional[str] = None,
        active: bool = True,
    ) -> Dict[str, Any]:
        pack_id = pack_id or f"pack_{uuid.uuid4().hex[:12]}"
        now = _utc_now()
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO policy_packs
                (pack_id, name, version, policy_overlay, active, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                pack_id,
                name,
                version,
                json.dumps(policy_overlay, sort_keys=True),
                1 if active else 0,
                now,
            ))
        return self.get_policy_pack(pack_id)

    def get_policy_pack(self, pack_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("""
                SELECT pack_id, name, version, policy_overlay, active, created_at
                FROM policy_packs
                WHERE pack_id = ?
            """, (pack_id,)).fetchone()
        if not row:
            raise ValueError(f"Policy pack not found: {pack_id}")
        return {
            "pack_id": row[0],
            "name": row[1],
            "version": row[2],
            "policy_overlay": json.loads(row[3] or "{}"),
            "active": bool(row[4]),
            "created_at": row[5],
        }

    def list_policy_packs(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT pack_id, name, version, policy_overlay, active, created_at
                FROM policy_packs
                ORDER BY created_at DESC
            """).fetchall()
        return [
            {
                "pack_id": row[0],
                "name": row[1],
                "version": row[2],
                "policy_overlay": json.loads(row[3] or "{}"),
                "active": bool(row[4]),
                "created_at": row[5],
            }
            for row in rows
        ]

    def assign_policy_pack(self, team_id: str, pack_id: str) -> Dict[str, Any]:
        self.get_team(team_id)
        self.get_policy_pack(pack_id)
        now = _utc_now()
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO team_policy_packs
                (team_id, pack_id, assigned_at)
                VALUES (?, ?, ?)
            """, (team_id, pack_id, now))
        return {"team_id": team_id, "pack_id": pack_id, "assigned_at": now}

    def effective_policy(self, team_id: str, base_policy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.get_team(team_id)
        effective = dict(base_policy if base_policy is not None else self.policies)
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT p.policy_overlay
                FROM team_policy_packs tp
                JOIN policy_packs p ON p.pack_id = tp.pack_id
                WHERE tp.team_id = ? AND p.active = 1
                ORDER BY tp.assigned_at ASC
            """, (team_id,)).fetchall()
        for row in rows:
            effective = _deep_merge(effective, json.loads(row[0] or "{}"))
        return effective

    def store_encrypted_trace(
        self,
        team_id: str,
        trace: Dict[str, Any],
        user_id: str = "",
        trace_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self.get_team(team_id)
        trace_id = trace_id or str(trace.get("trace_id") or f"trace_{uuid.uuid4().hex[:12]}")
        nonce = secrets.token_bytes(16)
        plaintext = json.dumps(_json_safe(trace), sort_keys=True).encode("utf-8")
        ciphertext = self._xor_stream(plaintext, self._trace_key(team_id), nonce)
        digest = hmac.new(self._trace_key(team_id), plaintext, hashlib.sha256).hexdigest()
        now = _utc_now()
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO encrypted_traces
                (trace_id, team_id, user_id, nonce, ciphertext, digest, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trace_id,
                team_id,
                user_id,
                base64.b64encode(nonce).decode("ascii"),
                base64.b64encode(ciphertext).decode("ascii"),
                digest,
                json.dumps(metadata or {}, sort_keys=True),
                now,
            ))
        return {
            "trace_id": trace_id,
            "team_id": team_id,
            "user_id": user_id,
            "encrypted": True,
            "digest": digest,
            "metadata": metadata or {},
            "created_at": now,
        }

    def retrieve_encrypted_trace(self, team_id: str, trace_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("""
                SELECT trace_id, team_id, user_id, nonce, ciphertext, digest, metadata, created_at
                FROM encrypted_traces
                WHERE trace_id = ? AND team_id = ?
            """, (trace_id, team_id)).fetchone()
        if not row:
            raise ValueError(f"Encrypted trace not found: {trace_id}")
        nonce = base64.b64decode(row[3])
        ciphertext = base64.b64decode(row[4])
        plaintext = self._xor_stream(ciphertext, self._trace_key(team_id), nonce)
        digest = hmac.new(self._trace_key(team_id), plaintext, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(digest, row[5]):
            raise ValueError("Encrypted trace integrity check failed")
        return {
            "trace_id": row[0],
            "team_id": row[1],
            "user_id": row[2],
            "trace": json.loads(plaintext.decode("utf-8")),
            "digest": row[5],
            "metadata": json.loads(row[6] or "{}"),
            "created_at": row[7],
        }

    def state(self) -> Dict[str, Any]:
        with self._connect() as conn:
            teams = conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
            users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            keys = conn.execute("SELECT COUNT(*) FROM virtual_keys WHERE active = 1").fetchone()[0]
            events = conn.execute("SELECT COUNT(*) FROM observability_events").fetchone()[0]
            packs = conn.execute("SELECT COUNT(*) FROM policy_packs").fetchone()[0]
            traces = conn.execute("SELECT COUNT(*) FROM encrypted_traces").fetchone()[0]
        return {
            "enabled": bool(self.policies.get("enterprise", {}).get("enabled", False)),
            "teams": teams,
            "users": users,
            "active_virtual_keys": keys,
            "observability_events": events,
            "policy_packs": packs,
            "encrypted_traces": traces,
            "db": str(self.db_path),
        }

    def _hash_key(self, virtual_key: str) -> str:
        return hashlib.sha256(virtual_key.encode("utf-8")).hexdigest()

    def _trace_key(self, team_id: str) -> bytes:
        configured = str(self.policies.get("enterprise", {}).get("trace_encryption_secret", "edgek-local-dev-secret"))
        return hmac.new(configured.encode("utf-8"), team_id.encode("utf-8"), hashlib.sha256).digest()

    def _xor_stream(self, data: bytes, key: bytes, nonce: bytes) -> bytes:
        output = bytearray()
        counter = 0
        while len(output) < len(data):
            block = hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
            output.extend(block)
            counter += 1
        return bytes(item ^ output[index] for index, item in enumerate(data))


enterprise_manager = EnterpriseManager()
