"""
EdgeK BEAST Gateway - Runtime Governance
Controls provider execution with stasis walls, circuit breakers, timeouts, and attempt logs.
"""

import sqlite3
import threading
import time
import uuid
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.kernel.storage.forensic_memory import ForensicMemory
from app.kernel.networking.interception_events import InterceptionEventFactory


@dataclass
class RuntimeAdmission:
    allowed: bool
    attempt_id: str
    provider: str
    reason: str
    timeout_seconds: int
    retry_after_seconds: Optional[int] = None


class RuntimeGovernor:
    """SQLite-backed runtime controls for provider execution."""

    def __init__(
        self,
        policies: Optional[Dict[str, Any]] = None,
        db_path: Optional[str] = None,
        forensic_memory: Optional[ForensicMemory] = None,
    ):
        self.policies = policies or {}
        if db_path is None:
            db_path = Path(__file__).resolve().parents[2] / "data" / "runtime.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._active_counts: Dict[str, int] = {}
        self._lock = threading.Lock()
        self.interception_events = InterceptionEventFactory(self.policies)
        self.forensic_memory = forensic_memory or ForensicMemory(str(self.db_path.with_name("forensic_l4.db")))
        self._db_initialized = False

    def _connect(self):
        if not self._db_initialized:
            self._init_db()
            self._db_initialized = True
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS runtime_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    duration_ms INTEGER,
                    error_type TEXT DEFAULT '',
                    error_message TEXT DEFAULT '',
                    metadata TEXT DEFAULT '{}'
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_runtime_attempts_provider ON runtime_attempts(provider)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_runtime_attempts_status ON runtime_attempts(status)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS runtime_circuits (
                    provider TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    failure_count INTEGER DEFAULT 0,
                    opened_until REAL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    last_error TEXT DEFAULT ''
                )
            """)

    def begin_execution(
        self,
        provider: str,
        model: str,
        session_id: str = "default",
        metadata: Optional[Dict[str, Any]] = None
    ) -> RuntimeAdmission:
        self.sweep_stale_attempts()
        attempt_id = str(uuid.uuid4())
        runtime_config = self._runtime_config(provider)
        meta_rules = self.policies.get("meta_rules", {})
        timeout_seconds = runtime_config["timeout_seconds"]

        circuit = self.circuit_state(provider)
        if meta_rules.get("circuit_breaker_enabled", True) and circuit["state"] == "open":
            retry_after = max(1, int(circuit["opened_until"] - time.time()))
            self._record_attempt(
                attempt_id, provider, model, session_id, "rejected",
                metadata={**(metadata or {}), "reason": "circuit_open"}
            )
            self._record_forensic_event({
                "event_kind": "circuit",
                "event_id": attempt_id,
                "source_uri": f"runtime://attempt/{attempt_id}",
                "scope": "provider",
                "provider": provider,
                "status": "rejected",
                "summary": f"Circuit breaker open for provider {provider}",
                "signals": ["runtime_rejected", "circuit_open"],
                "relationships": [{"type": "model", "id": model}, {"type": "session", "id": session_id}],
            })
            return RuntimeAdmission(
                allowed=False,
                attempt_id=attempt_id,
                provider=provider,
                reason=f"Circuit breaker open for provider {provider}",
                timeout_seconds=timeout_seconds,
                retry_after_seconds=retry_after,
            )

        if meta_rules.get("stasis_wall_enabled", True):
            max_concurrent = runtime_config["max_concurrent"]
            with self._lock:
                active = self._active_counts.get(provider, 0)
                if active >= max_concurrent:
                    self._record_attempt(
                        attempt_id, provider, model, session_id, "rejected",
                        metadata={**(metadata or {}), "reason": "stasis_wall_full"}
                    )
                    self._record_forensic_event({
                        "event_kind": "throttle",
                        "event_id": attempt_id,
                        "source_uri": f"runtime://attempt/{attempt_id}",
                        "scope": "provider",
                        "provider": provider,
                        "status": "rejected",
                        "summary": f"Stasis wall full for provider {provider}",
                        "signals": ["runtime_rejected", "stasis_wall_full"],
                        "relationships": [{"type": "model", "id": model}, {"type": "session", "id": session_id}],
                    })
                    return RuntimeAdmission(
                        allowed=False,
                        attempt_id=attempt_id,
                        provider=provider,
                        reason=f"Stasis wall full for provider {provider}",
                        timeout_seconds=timeout_seconds,
                        retry_after_seconds=1,
                    )
                self._active_counts[provider] = active + 1

        self._record_attempt(attempt_id, provider, model, session_id, "started", metadata=metadata or {})
        return RuntimeAdmission(
            allowed=True,
            attempt_id=attempt_id,
            provider=provider,
            reason="Runtime admission granted",
            timeout_seconds=timeout_seconds,
        )

    def complete_execution(
        self,
        attempt_id: str,
        provider: str,
        success: bool,
        error_type: str = "",
        error_message: str = ""
    ):
        completed_at = self._utc_now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT started_at FROM runtime_attempts WHERE attempt_id = ?",
                (attempt_id,)
            ).fetchone()
            started_at = self._parse_time(row[0]) if row else time.time()
            duration_ms = int((time.time() - started_at) * 1000)
            conn.execute("""
                UPDATE runtime_attempts
                SET status = ?, completed_at = ?, duration_ms = ?, error_type = ?, error_message = ?
                WHERE attempt_id = ?
            """, (
                "succeeded" if success else "failed",
                completed_at,
                duration_ms,
                error_type,
                error_message[:1000],
                attempt_id,
            ))

        with self._lock:
            self._active_counts[provider] = max(0, self._active_counts.get(provider, 0) - 1)

        if success:
            self._record_provider_success(provider)
        else:
            self._record_provider_failure(provider, error_message or error_type)
        self._record_forensic_event({
            "event_kind": "latency" if success else "error",
            "event_id": attempt_id,
            "source_uri": f"runtime://attempt/{attempt_id}",
            "scope": "provider",
            "provider": provider,
            "status": "succeeded" if success else "failed",
            "duration_ms": duration_ms,
            "summary": "Runtime execution succeeded" if success else (error_message or error_type or "Runtime execution failed"),
            "signals": [f"runtime_{'succeeded' if success else 'failed'}"],
        })

    def circuit_state(self, provider: str) -> Dict[str, Any]:
        now = time.time()
        with self._connect() as conn:
            row = conn.execute("""
                SELECT provider, state, failure_count, opened_until, updated_at, last_error
                FROM runtime_circuits
                WHERE provider = ?
            """, (provider,)).fetchone()
            if not row:
                return {
                    "provider": provider,
                    "state": "closed",
                    "failure_count": 0,
                    "opened_until": 0,
                    "retry_after_seconds": 0,
                    "updated_at": None,
                    "last_error": "",
                }
            state = row[1]
            opened_until = float(row[3] or 0)
            if state == "open" and opened_until <= now:
                state = "half_open"
                conn.execute("""
                    UPDATE runtime_circuits
                    SET state = ?, updated_at = ?
                    WHERE provider = ?
                """, (state, self._utc_now(), provider))
        return {
            "provider": row[0],
            "state": state,
            "failure_count": row[2],
            "opened_until": opened_until,
            "retry_after_seconds": max(0, int(opened_until - now)),
            "updated_at": row[4],
            "last_error": row[5],
        }

    def reset_circuit(self, provider: str) -> Dict[str, Any]:
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO runtime_circuits (provider, state, failure_count, opened_until, updated_at, last_error)
                VALUES (?, 'closed', 0, 0, ?, '')
                ON CONFLICT(provider) DO UPDATE SET
                    state = 'closed',
                    failure_count = 0,
                    opened_until = 0,
                    updated_at = excluded.updated_at,
                    last_error = ''
            """, (provider, self._utc_now()))
        return self.circuit_state(provider)

    def state(self) -> Dict[str, Any]:
        providers = ["openai", "anthropic", "google", "huggingface", "tgi", "litellm", "ollama", "openai_compatible", "nvidia_nim"]
        with self._connect() as conn:
            attempts = conn.execute("SELECT status, COUNT(*) FROM runtime_attempts GROUP BY status").fetchall()
            recent = conn.execute("""
                SELECT attempt_id, provider, model, session_id, status, started_at, completed_at,
                       duration_ms, error_type, error_message
                FROM runtime_attempts
                ORDER BY started_at DESC
                LIMIT 20
            """).fetchall()
        return {
            "active_counts": dict(self._active_counts),
            "attempts": {row[0]: row[1] for row in attempts},
            "circuits": {provider: self.circuit_state(provider) for provider in providers},
            "recent_attempts": [self._row_to_attempt(row) for row in recent],
            "integrity": self.integrity_report(),
            "runtime_db": str(self.db_path),
        }

    def metrics(self, limit: int = 500) -> Dict[str, Any]:
        limit = max(1, min(int(limit or 500), 2000))
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT provider, model, status, duration_ms, error_type, error_message, started_at
                FROM runtime_attempts
                ORDER BY started_at DESC
                LIMIT ?
            """, (limit,)).fetchall()
        provider_counts: Dict[str, Counter] = {}
        durations: list[int] = []
        failures = []
        started_count = 0
        failure_count = 0
        success_count = 0
        for provider, model, status, duration_ms, error_type, error_message, started_at in rows:
            provider_counts.setdefault(provider, Counter())[status] += 1
            if status == "started":
                started_count += 1
            elif status == "succeeded":
                success_count += 1
            elif status in {"failed", "rejected", "abandoned"}:
                failure_count += 1
            if isinstance(duration_ms, int) and duration_ms >= 0:
                durations.append(duration_ms)
            if status in {"failed", "rejected", "abandoned"}:
                failures.append({
                    "provider": provider,
                    "model": model,
                    "status": status,
                    "error_type": error_type,
                    "error_message": error_message,
                    "started_at": started_at,
                })
        durations_sorted = sorted(durations)
        completed_count = success_count + failure_count
        failure_rate = round(failure_count / completed_count, 4) if completed_count else 0.0
        health_status = "healthy"
        if started_count:
            health_status = "active"
        if failure_count:
            health_status = "degraded"
        if failure_rate >= 0.5 and failure_count >= 5:
            health_status = "unhealthy"
        return {
            "sample_size": len(rows),
            "health": {
                "status": health_status,
                "success_count": success_count,
                "failure_count": failure_count,
                "started_count": started_count,
                "failure_rate": failure_rate,
            },
            "provider_counts": {provider: dict(counts) for provider, counts in provider_counts.items()},
            "latency_ms": self._duration_stats(durations_sorted),
            "recent_failures": failures[:12],
        }

    def recent_attempts(
        self,
        provider: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20
    ) -> list[Dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if provider:
            clauses.append("provider = ?")
            params.append(provider)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(f"""
                SELECT attempt_id, provider, model, session_id, status, started_at, completed_at,
                       duration_ms, error_type, error_message
                FROM runtime_attempts
                {where}
                ORDER BY started_at DESC
                LIMIT ?
            """, params).fetchall()
        return [self._row_to_attempt(row) for row in rows]

    def get_attempt(self, attempt_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("""
                SELECT attempt_id, provider, model, session_id, status, started_at, completed_at,
                       duration_ms, error_type, error_message, metadata
                FROM runtime_attempts
                WHERE attempt_id = ?
            """, (attempt_id,)).fetchone()
        if not row:
            raise ValueError(f"Runtime attempt not found: {attempt_id}")
        attempt = self._row_to_attempt(row[:10])
        attempt["metadata"] = json.loads(row[10] or "{}")
        return attempt

    def integrity_report(self) -> Dict[str, Any]:
        ttl_seconds = self._lease_ttl_seconds()
        cutoff = time.time() - ttl_seconds
        with self._connect() as conn:
            stale_rows = conn.execute("""
                SELECT attempt_id, provider, model, session_id, status, started_at, completed_at,
                       duration_ms, error_type, error_message
                FROM runtime_attempts
                WHERE status = 'started'
                ORDER BY started_at ASC
                LIMIT 20
            """).fetchall()
        stale_attempts = [
            self._row_to_attempt(row)
            for row in stale_rows
            if self._parse_time(row[5]) < cutoff
        ]
        db_active_counts = Counter(row["provider"] for row in self.recent_attempts(status="started", limit=1000))
        return {
            "ok": not stale_attempts,
            "lease_ttl_seconds": ttl_seconds,
            "stale_started_attempt_count": len(stale_attempts),
            "stale_started_attempts": stale_attempts,
            "memory_active_counts": dict(self._active_counts),
            "db_started_counts": dict(db_active_counts),
        }

    def sweep_stale_attempts(self, max_age_seconds: Optional[int] = None) -> Dict[str, Any]:
        max_age_seconds = int(max_age_seconds or self._lease_ttl_seconds())
        cutoff = time.time() - max_age_seconds
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT attempt_id, provider, started_at
                FROM runtime_attempts
                WHERE status = 'started'
            """).fetchall()
            stale = [row for row in rows if self._parse_time(row[2]) < cutoff]
            for attempt_id, _provider, started_at in stale:
                duration_ms = int((time.time() - self._parse_time(started_at)) * 1000)
                conn.execute("""
                    UPDATE runtime_attempts
                    SET status = 'abandoned',
                        completed_at = ?,
                        duration_ms = ?,
                        error_type = 'runtime_abandoned',
                        error_message = 'Runtime attempt exceeded lease TTL before completion'
                    WHERE attempt_id = ? AND status = 'started'
                """, (self._utc_now(), duration_ms, attempt_id))
                self._record_forensic_event({
                    "event_kind": "throttle",
                    "event_id": attempt_id,
                    "source_uri": f"runtime://attempt/{attempt_id}",
                    "scope": "provider",
                    "provider": _provider,
                    "status": "abandoned",
                    "duration_ms": duration_ms,
                    "summary": "Runtime attempt exceeded lease TTL before completion",
                    "signals": ["runtime_abandoned", "lease_ttl_exceeded"],
                })

        by_provider = Counter(row[1] for row in stale)
        if by_provider:
            with self._lock:
                for provider, count in by_provider.items():
                    self._active_counts[provider] = max(0, self._active_counts.get(provider, 0) - count)

        return {
            "max_age_seconds": max_age_seconds,
            "swept_attempts": len(stale),
            "providers": dict(by_provider),
        }

    def _record_attempt(
        self,
        attempt_id: str,
        provider: str,
        model: str,
        session_id: str,
        status: str,
        metadata: Dict[str, Any]
    ):
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO runtime_attempts
                (attempt_id, provider, model, session_id, status, started_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                attempt_id,
                provider,
                model,
                session_id,
                status,
                self._utc_now(),
                json.dumps(metadata, sort_keys=True),
            ))

    def _record_provider_success(self, provider: str):
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO runtime_circuits (provider, state, failure_count, opened_until, updated_at, last_error)
                VALUES (?, 'closed', 0, 0, ?, '')
                ON CONFLICT(provider) DO UPDATE SET
                    state = 'closed',
                    failure_count = 0,
                    opened_until = 0,
                    updated_at = excluded.updated_at,
                    last_error = ''
            """, (provider, self._utc_now()))

    def _record_provider_failure(self, provider: str, error: str):
        meta_rules = self.policies.get("meta_rules", {})
        threshold = int(meta_rules.get("circuit_breaker_failure_threshold", 5))
        timeout_seconds = int(meta_rules.get("circuit_breaker_timeout_seconds", 60))
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT failure_count FROM runtime_circuits WHERE provider = ?",
                (provider,)
            ).fetchone()
            failure_count = (row[0] if row else 0) + 1
            state = "open" if failure_count >= threshold else "closed"
            opened_until = now + timeout_seconds if state == "open" else 0
            conn.execute("""
                INSERT INTO runtime_circuits
                (provider, state, failure_count, opened_until, updated_at, last_error)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider) DO UPDATE SET
                    state = excluded.state,
                    failure_count = excluded.failure_count,
                    opened_until = excluded.opened_until,
                    updated_at = excluded.updated_at,
                    last_error = excluded.last_error
            """, (provider, state, failure_count, opened_until, self._utc_now(), error[:1000]))
        if state == "open":
            self._record_forensic_event({
                "event_kind": "circuit",
                "event_id": f"circuit_{provider}_{int(now)}",
                "source_uri": f"runtime://circuit/{provider}",
                "scope": "provider",
                "provider": provider,
                "status": "open",
                "summary": error[:1000] or f"Circuit opened for {provider}",
                "signals": ["circuit_open", "runtime_failure_threshold"],
                "repeat_count": failure_count,
            })

    def _runtime_config(self, provider: str) -> Dict[str, int]:
        meta_rules = self.policies.get("meta_rules", {})
        provider_config = self.policies.get("providers", {}).get(provider, {})
        max_by_provider = meta_rules.get("stasis_wall_max_concurrent_by_provider", {})
        return {
            "timeout_seconds": int(
                provider_config.get(
                    "runtime_timeout_seconds",
                    meta_rules.get("runtime_provider_timeout_seconds", 120),
                )
            ),
            "max_concurrent": int(
                provider_config.get(
                    "runtime_max_concurrent",
                    max_by_provider.get(provider, meta_rules.get("stasis_wall_max_concurrent", 5)),
                )
            ),
        }

    def _lease_ttl_seconds(self) -> int:
        meta_rules = self.policies.get("meta_rules", {})
        return int(meta_rules.get("runtime_attempt_lease_ttl_seconds", 900))

    def _row_to_attempt(self, row) -> Dict[str, Any]:
        return {
            "attempt_id": row[0],
            "provider": row[1],
            "model": row[2],
            "session_id": row[3],
            "status": row[4],
            "started_at": row[5],
            "completed_at": row[6],
            "duration_ms": row[7],
            "error_type": row[8],
            "error_message": row[9],
        }

    def _duration_stats(self, durations: list[int]) -> Dict[str, Any]:
        if not durations:
            return {"count": 0, "avg": 0, "min": 0, "max": 0, "p95": 0}
        index_95 = min(len(durations) - 1, int(round((len(durations) - 1) * 0.95)))
        return {
            "count": len(durations),
            "avg": int(sum(durations) / len(durations)),
            "min": durations[0],
            "max": durations[-1],
            "p95": durations[index_95],
        }

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _parse_time(self, value: str) -> float:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except Exception:
            return time.time()

    def _record_forensic_event(self, payload: Dict[str, Any]):
        try:
            evidence = self.interception_events.build(payload)
            self.forensic_memory.append(payload, evidence=evidence)
        except Exception:
            return None


runtime_governor = RuntimeGovernor()
