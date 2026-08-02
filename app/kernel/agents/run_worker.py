"""In-process ownership for durable BEAST AgentRun execution workers.

The durable SQLite ledger is the source of truth. This registry owns only live
asyncio task handles for the current backend process and deliberately keeps no
business state that cannot be reconstructed after restart.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from app.kernel.agents.run_cancel import AGENT_RUN_CANCELLATIONS


WorkerFactory = Callable[[], Awaitable[Any]]


@dataclass
class AgentRunWorkerHandle:
    run_id: str
    task: asyncio.Task[Any]


class AgentRunWorkerRegistry:
    def __init__(self) -> None:
        self._workers: dict[str, AgentRunWorkerHandle] = {}
        self._lock = threading.RLock()

    def get(self, run_id: str) -> AgentRunWorkerHandle | None:
        with self._lock:
            handle = self._workers.get(str(run_id or ""))
            if handle and handle.task.done():
                self._workers.pop(str(run_id or ""), None)
                return None
            return handle

    def active(self, run_id: str) -> bool:
        return self.get(run_id) is not None

    def launch(self, run_id: str, factory: WorkerFactory) -> AgentRunWorkerHandle:
        identifier = str(run_id or "").strip()
        if not identifier:
            raise ValueError("run_id is required")
        existing = self.get(identifier)
        if existing:
            return existing

        async def _runner() -> Any:
            return await factory()

        task = asyncio.create_task(_runner(), name=f"beast-agent-run:{identifier}")
        AGENT_RUN_CANCELLATIONS.attach_task(identifier, task)
        handle = AgentRunWorkerHandle(run_id=identifier, task=task)
        with self._lock:
            competing = self._workers.get(identifier)
            if competing and not competing.task.done():
                task.cancel()
                return competing
            self._workers[identifier] = handle

        def _release(completed: asyncio.Task[Any]) -> None:
            with self._lock:
                current = self._workers.get(identifier)
                if current and current.task is completed:
                    self._workers.pop(identifier, None)

        task.add_done_callback(_release)
        return handle

    async def cancel(self, run_id: str) -> bool:
        handle = self.get(run_id)
        if not handle:
            return False
        if not handle.task.done():
            handle.task.cancel()
        try:
            await handle.task
        except (asyncio.CancelledError, Exception):
            pass
        return True

    def status(self, run_id: str) -> dict[str, Any]:
        handle = self.get(run_id)
        if not handle:
            return {"active": False, "task_name": "", "done": True}
        return {
            "active": not handle.task.done(),
            "task_name": handle.task.get_name(),
            "done": handle.task.done(),
            "cancelled": handle.task.cancelled(),
        }


AGENT_RUN_WORKERS = AgentRunWorkerRegistry()
