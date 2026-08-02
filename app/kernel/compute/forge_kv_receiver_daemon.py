"""Bounded receiver daemon and scheduled revocation polling."""
from __future__ import annotations

import time
from queue import Empty, Queue
from threading import Event, Thread
from typing import Any, Callable, Mapping

from app.kernel.compute.forge_kv_progress import ProgressStream
from app.kernel.compute.forge_kv_receiver import ForgeKVReceiverWorker, RevocationPoller


class ForgeKVReceiverDaemon:
    def __init__(self, *, worker: ForgeKVReceiverWorker | None = None, progress: ProgressStream | None = None,
                 queue_capacity: int = 64):
        self.worker=worker or ForgeKVReceiverWorker(); self.progress=progress or ProgressStream()
        self.queue: Queue[dict[str,Any]]=Queue(maxsize=queue_capacity)
        self._stop=Event(); self._thread: Thread | None=None; self.completed=[]

    def submit(self, job: Mapping[str,Any]) -> None:
        self.queue.put_nowait(dict(job)); self.progress.publish("receiver.queued",dataset_id=job.get("dataset_id",""))

    def start(self) -> None:
        if self._thread and self._thread.is_alive(): return
        self._stop.clear(); self._thread=Thread(target=self._run,name="beast-forge-receiver",daemon=True); self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread: self._thread.join(timeout)

    def _run(self) -> None:
        while not self._stop.is_set():
            try: job=self.queue.get(timeout=.1)
            except Empty: continue
            try:
                self.progress.publish("receiver.reconstructing",dataset_id=job.get("dataset_id",""))
                receipt=self.worker.run(**job); self.completed.append(receipt)
                self.progress.publish("receiver.verified",dataset_id=receipt.dataset_id,verified=receipt.locally_verified)
            except Exception as exc:
                self.progress.publish("receiver.failed",dataset_id=job.get("dataset_id",""),error_type=type(exc).__name__)
            finally: self.queue.task_done()


class ScheduledRevocationPoller:
    def __init__(self, poller: RevocationPoller, *, interval_seconds: float = 60,
                 progress: ProgressStream | None = None):
        self.poller=poller; self.interval=max(.05,float(interval_seconds)); self.progress=progress or ProgressStream()
        self._stop=Event(); self._thread: Thread|None=None
    def start(self):
        if self._thread and self._thread.is_alive(): return
        self._stop.clear(); self._thread=Thread(target=self._run,name="beast-forge-revocations",daemon=True); self._thread.start()
    def stop(self,timeout:float=2):
        self._stop.set()
        if self._thread: self._thread.join(timeout)
    def _run(self):
        while not self._stop.wait(self.interval):
            state=self.poller.poll(); self.progress.publish("revocation.polled",revoked_count=state["revoked_count"])
