"""In-process execution handles for prompt BEAST agent cancellation."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentRunHandle:
    run_id: str
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    tasks: set[asyncio.Task[Any]] = field(default_factory=set)
    processes: set[Any] = field(default_factory=set)
    reason: str = ""


class AgentRunCancellationRegistry:
    def __init__(self) -> None:
        self._handles: dict[str, AgentRunHandle] = {}
        self._lock = threading.RLock()

    def register(self, run_id: str) -> AgentRunHandle:
        with self._lock:
            handle = self._handles.get(run_id)
            if handle is None:
                handle = AgentRunHandle(run_id=run_id)
                self._handles[run_id] = handle
            return handle

    def get(self, run_id: str) -> AgentRunHandle | None:
        with self._lock:
            return self._handles.get(run_id)

    def attach_task(self, run_id: str, task: asyncio.Task[Any]) -> None:
        handle = self.register(run_id)
        handle.tasks.add(task)
        task.add_done_callback(lambda completed: handle.tasks.discard(completed))

    def attach_process(self, run_id: str, process: Any) -> None:
        self.register(run_id).processes.add(process)

    def is_cancelled(self, run_id: str) -> bool:
        handle = self.get(run_id)
        return bool(handle and handle.cancel_event.is_set())

    async def cancel(self, run_id: str, reason: str = "") -> dict[str, Any]:
        handle = self.register(run_id)
        handle.reason = str(reason or "operator_cancelled")
        handle.cancel_event.set()
        task_count = 0
        process_count = 0
        current = asyncio.current_task()
        for task in list(handle.tasks):
            if task is not current and not task.done():
                task.cancel()
                task_count += 1
        for process in list(handle.processes):
            try:
                if getattr(process, "returncode", None) is None:
                    terminate = getattr(process, "terminate", None)
                    if callable(terminate):
                        terminate()
                        process_count += 1
            except Exception:
                continue
        return {
            "ok": True,
            "run_id": run_id,
            "reason": handle.reason,
            "tasks_cancelled": task_count,
            "processes_signalled": process_count,
        }

    def unregister(self, run_id: str) -> None:
        with self._lock:
            self._handles.pop(run_id, None)


AGENT_RUN_CANCELLATIONS = AgentRunCancellationRegistry()
