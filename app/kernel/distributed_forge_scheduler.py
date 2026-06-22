"""Durable file-coordinated scheduler for CPU-first Forge nodes."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

try:  # POSIX process coordination; thread lock remains the portable fallback.
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

from app.kernel.compute_forge import ForgeWorkItem


class NodeStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


@dataclass
class ScheduledWork:
    schedule_id: str
    work_item: ForgeWorkItem
    assigned_node: str
    priority: int = 5
    deadline: Optional[str] = None
    status: str = "assigned"
    result: Optional[Dict[str, Any]] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    lease_expires_at: Optional[str] = None
    attempt: int = 1
    result_digest: Optional[str] = None


@dataclass
class NodeHealth:
    node_id: str
    status: NodeStatus
    last_heartbeat: str
    consecutive_failures: int = 0
    total_work_completed: int = 0
    total_work_failed: int = 0
    current_load: int = 0
    capabilities: List[str] = field(default_factory=list)


class DistributedForgeScheduler:
    """File-based scheduler with atomic state, leases, and restart recovery."""

    STATE_VERSION = "2.0"

    def __init__(self, scheduler_dir: Optional[Path] = None, *, lease_seconds: int = 300):
        self.scheduler_dir = scheduler_dir or Path(__file__).resolve().parents[2] / "data" / "scheduler"
        self.scheduler_dir.mkdir(parents=True, exist_ok=True)
        self.lease_seconds = max(1, int(lease_seconds))
        self.nodes: Dict[str, NodeHealth] = {}
        self.scheduled_work: Dict[str, ScheduledWork] = {}
        self.work_queue: List[ForgeWorkItem] = []
        self._thread_lock = threading.RLock()
        self._load_state()
        self.recover_expired_leases()

    def _work_path(self, schedule_id: str) -> Path:
        return self.scheduler_dir / f"work_{schedule_id}.json"

    def _node_path(self, node_id: str) -> Path:
        return self.scheduler_dir / f"node_{node_id}.json"

    def _state_path(self) -> Path:
        return self.scheduler_dir / "scheduler_state.json"

    @contextmanager
    def _locked(self) -> Iterator[None]:
        with self._thread_lock:
            lock_path = self.scheduler_dir / ".scheduler.lock"
            with lock_path.open("a+b") as lock:
                if fcntl is not None:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                try:
                    self._load_state(reset=True)
                    yield
                finally:
                    if fcntl is not None:
                        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _atomic_json(path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
            dir_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass

    @staticmethod
    def _work_to_dict(item: ForgeWorkItem) -> Dict[str, Any]:
        return asdict(item)

    @staticmethod
    def _work_from_dict(payload: Dict[str, Any]) -> ForgeWorkItem:
        allowed = ForgeWorkItem.__dataclass_fields__
        return ForgeWorkItem(**{key: value for key, value in payload.items() if key in allowed})

    def _scheduled_to_dict(self, item: ScheduledWork) -> Dict[str, Any]:
        payload = asdict(item)
        payload["work_item"] = self._work_to_dict(item.work_item)
        return payload

    def _persist_state(self) -> None:
        payload = {
            "beast_object_type": "distributed_forge_scheduler_state",
            "version": self.STATE_VERSION,
            "lease_seconds": self.lease_seconds,
            "nodes": {key: {**asdict(value), "status": value.status.value} for key, value in self.nodes.items()},
            "work_queue": [self._work_to_dict(item) for item in self.work_queue],
            "scheduled_work": {key: self._scheduled_to_dict(value) for key, value in self.scheduled_work.items()},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._atomic_json(self._state_path(), payload)

    def _load_state(self, *, reset: bool = False) -> None:
        path = self._state_path()
        if not path.is_file():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if reset:
                self.nodes.clear()
                self.work_queue.clear()
                self.scheduled_work.clear()
            for node_id, row in (payload.get("nodes") or {}).items():
                row = dict(row)
                row["status"] = NodeStatus(row.get("status", NodeStatus.UNKNOWN.value))
                self.nodes[node_id] = NodeHealth(**row)
            self.work_queue = [self._work_from_dict(row) for row in payload.get("work_queue") or []]
            for schedule_id, row in (payload.get("scheduled_work") or {}).items():
                row = dict(row)
                row["work_item"] = self._work_from_dict(row.get("work_item") or {})
                self.scheduled_work[schedule_id] = ScheduledWork(**row)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            # Preserve the corrupt snapshot for diagnosis and start safely empty.
            corrupt = path.with_name(f"scheduler_state.corrupt.{int(time.time())}.json")
            try:
                os.replace(path, corrupt)
            except OSError:
                pass

    def _persist_node(self, health: NodeHealth) -> None:
        self._atomic_json(self._node_path(health.node_id), {**asdict(health), "status": health.status.value})

    def _persist_claim(self, scheduled: ScheduledWork) -> None:
        self._atomic_json(self._work_path(scheduled.schedule_id), self._scheduled_to_dict(scheduled))

    @staticmethod
    def _result_digest(success: bool, result: Optional[Dict[str, Any]]) -> str:
        canonical = json.dumps({"success": bool(success), "result": result or {}}, sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def _expired(iso_value: Optional[str]) -> bool:
        if not iso_value:
            return False
        try:
            return datetime.fromisoformat(iso_value) <= datetime.now(timezone.utc)
        except ValueError:
            return True

    def register_node(self, node_id: str, capabilities: List[str] = None) -> NodeHealth:
        with self._locked():
            previous = self.nodes.get(node_id)
            health = NodeHealth(
                node_id=node_id,
                status=NodeStatus.HEALTHY,
                last_heartbeat=datetime.now(timezone.utc).isoformat(),
                capabilities=list(capabilities or (previous.capabilities if previous else [])),
                total_work_completed=previous.total_work_completed if previous else 0,
                total_work_failed=previous.total_work_failed if previous else 0,
                consecutive_failures=previous.consecutive_failures if previous else 0,
                current_load=previous.current_load if previous else 0,
            )
            self.nodes[node_id] = health
            self._persist_node(health)
            self._persist_state()
            return health

    def heartbeat(self, node_id: str, current_load: int = 0) -> bool:
        with self._locked():
            if node_id not in self.nodes:
                return False
            health = self.nodes[node_id]
            health.last_heartbeat = datetime.now(timezone.utc).isoformat()
            health.current_load = max(0, int(current_load))
            health.status = NodeStatus.HEALTHY
            health.consecutive_failures = 0
            self._persist_node(health)
            self._persist_state()
            return True

    def submit_work(self, work_type: str, repo_path: str, priority: int = 5, deadline_seconds: Optional[int] = None) -> ForgeWorkItem:
        with self._locked():
            item = ForgeWorkItem(
                work_id=f"work_{uuid.uuid4().hex[:12]}", work_type=work_type, repo_path=repo_path,
                priority=priority, created_at=datetime.now(timezone.utc).isoformat(),
            )
            if deadline_seconds is not None:
                item.result = {"deadline": (datetime.now(timezone.utc) + timedelta(seconds=deadline_seconds)).isoformat()}
            self.work_queue.append(item)
            self.work_queue.sort(key=lambda work: work.priority)
            self._persist_state()
            return item

    def assign_work(self, node_id: str, max_items: int = 3) -> List[ScheduledWork]:
        with self._locked():
            self._recover_expired_leases_locked()
            health = self.nodes.get(node_id)
            if not health or health.status != NodeStatus.HEALTHY:
                return []
            assigned: List[ScheduledWork] = []
            for _ in range(min(max_items, max(0, 5 - health.current_load))):
                compatible_index = next((i for i, item in enumerate(self.work_queue) if not health.capabilities or item.work_type in health.capabilities), None)
                if compatible_index is None:
                    break
                work_item = self.work_queue.pop(compatible_index)
                now = datetime.now(timezone.utc)
                scheduled = ScheduledWork(
                    schedule_id=f"sched_{uuid.uuid4().hex[:12]}", work_item=work_item,
                    assigned_node=node_id, priority=work_item.priority, status="assigned",
                    lease_expires_at=(now + timedelta(seconds=self.lease_seconds)).isoformat(),
                )
                self.scheduled_work[scheduled.schedule_id] = scheduled
                self._persist_claim(scheduled)
                assigned.append(scheduled)
                health.current_load += 1
            self._persist_node(health)
            self._persist_state()
            return assigned

    def claim_work(self, schedule_id: str, node_id: str, *, lease_seconds: Optional[int] = None) -> bool:
        with self._locked():
            self._recover_expired_leases_locked()
            scheduled = self.scheduled_work.get(schedule_id)
            if not scheduled or scheduled.assigned_node != node_id or scheduled.status not in {"assigned", "running"}:
                return False
            scheduled.status = "running"
            scheduled.started_at = scheduled.started_at or datetime.now(timezone.utc).isoformat()
            scheduled.lease_expires_at = (datetime.now(timezone.utc) + timedelta(seconds=max(1, int(lease_seconds or self.lease_seconds)))).isoformat()
            self._persist_claim(scheduled)
            self._persist_state()
            return True

    def report_work_result(self, schedule_id: str, node_id: str, success: bool, result: Optional[Dict[str, Any]] = None) -> bool:
        with self._locked():
            scheduled = self.scheduled_work.get(schedule_id)
            if not scheduled or scheduled.assigned_node != node_id:
                return False
            digest = self._result_digest(success, result)
            if scheduled.status in {"completed", "failed"}:
                return scheduled.result_digest == digest
            if scheduled.status == "expired":
                return False
            scheduled.status = "completed" if success else "failed"
            scheduled.result = result or {}
            scheduled.result_digest = digest
            scheduled.completed_at = datetime.now(timezone.utc).isoformat()
            scheduled.lease_expires_at = None
            health = self.nodes.get(node_id)
            if health:
                if success:
                    health.total_work_completed += 1
                    health.consecutive_failures = 0
                else:
                    health.total_work_failed += 1
                    health.consecutive_failures += 1
                    if health.consecutive_failures >= 3:
                        health.status = NodeStatus.DEGRADED
                health.current_load = max(0, health.current_load - 1)
                self._persist_node(health)
            self._persist_state()
            try:
                self._work_path(schedule_id).unlink()
            except FileNotFoundError:
                pass
            return True

    def _recover_expired_leases_locked(self) -> List[str]:
        recovered: List[str] = []
        queued_ids = {item.work_id for item in self.work_queue}
        for scheduled in self.scheduled_work.values():
            if scheduled.status in {"assigned", "running"} and self._expired(scheduled.lease_expires_at):
                scheduled.status = "expired"
                scheduled.lease_expires_at = None
                if scheduled.work_item.work_id not in queued_ids:
                    self.work_queue.append(scheduled.work_item)
                    queued_ids.add(scheduled.work_item.work_id)
                health = self.nodes.get(scheduled.assigned_node)
                if health:
                    health.current_load = max(0, health.current_load - 1)
                    self._persist_node(health)
                try:
                    self._work_path(scheduled.schedule_id).unlink()
                except FileNotFoundError:
                    pass
                recovered.append(scheduled.schedule_id)
        if recovered:
            self.work_queue.sort(key=lambda item: item.priority)
        return recovered

    def recover_expired_leases(self) -> List[str]:
        with self._locked():
            recovered = self._recover_expired_leases_locked()
            if recovered:
                self._persist_state()
            return recovered

    def get_pending_work_for_node(self, node_id: str) -> List[Dict[str, Any]]:
        with self._locked():
            self._recover_expired_leases_locked()
            pending = []
            for scheduled in self.scheduled_work.values():
                if scheduled.assigned_node == node_id and scheduled.status in {"assigned", "running"}:
                    pending.append({
                        "schedule_id": scheduled.schedule_id,
                        "work_item": self._work_to_dict(scheduled.work_item),
                        "status": scheduled.status,
                        "lease_expires_at": scheduled.lease_expires_at,
                        "attempt": scheduled.attempt,
                    })
            return pending

    def mark_node_offline(self, node_id: str) -> None:
        with self._locked():
            health = self.nodes.get(node_id)
            if not health:
                return
            health.status = NodeStatus.OFFLINE
            for scheduled in self.scheduled_work.values():
                if scheduled.assigned_node == node_id and scheduled.status in {"assigned", "running"}:
                    scheduled.lease_expires_at = datetime.now(timezone.utc).isoformat()
            self._recover_expired_leases_locked()
            try:
                self._node_path(node_id).unlink()
            except FileNotFoundError:
                pass
            self._persist_state()

    def get_system_status(self) -> Dict[str, Any]:
        self.recover_expired_leases()
        return {
            "beast_object_type": "distributed_forge_scheduler_status",
            "version": self.STATE_VERSION,
            "nodes": {
                "total": len(self.nodes),
                "healthy": sum(1 for node in self.nodes.values() if node.status == NodeStatus.HEALTHY),
                "degraded": sum(1 for node in self.nodes.values() if node.status == NodeStatus.DEGRADED),
                "offline": sum(1 for node in self.nodes.values() if node.status == NodeStatus.OFFLINE),
            },
            "work": {
                "queued": len(self.work_queue),
                "pending": sum(1 for item in self.scheduled_work.values() if item.status in {"assigned", "running"}),
                "completed": sum(1 for item in self.scheduled_work.values() if item.status == "completed"),
                "failed": sum(1 for item in self.scheduled_work.values() if item.status == "failed"),
                "expired": sum(1 for item in self.scheduled_work.values() if item.status == "expired"),
            },
            "scheduler_dir": str(self.scheduler_dir),
        }
