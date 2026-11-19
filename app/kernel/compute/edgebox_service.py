"""Long-running process entrypoint for an EdgeK Compute Forge node."""

from __future__ import annotations

import logging
import os
import signal
import socket
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import Protocol

from app.kernel.compute.compute_forge import ComputeForgeNode
from app.kernel.storage.durable_inference_storage import DurableInferenceStorage


LOG = logging.getLogger("edgebox")


class ForgeNode(Protocol):
    profile: object

    def persist_snapshot(self, path: Path) -> None: ...

    def close(self) -> None: ...


def run_service(
    *,
    node: ForgeNode,
    stop_event: Event,
    snapshot_path: Path,
    interval_seconds: float,
) -> None:
    """Publish node heartbeats until Docker requests shutdown."""
    try:
        while not stop_event.is_set():
            node.profile.last_activity_at = datetime.now(timezone.utc).isoformat()
            node.persist_snapshot(snapshot_path)
            LOG.info("EdgeBox heartbeat written to %s", snapshot_path)
            if stop_event.wait(interval_seconds):
                break
    finally:
        node.close()


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("EDGEBOX_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    data_dir = Path(os.environ.get("EDGEBOX_DATA_DIR", "/data/edgebox"))
    data_dir.mkdir(parents=True, exist_ok=True)
    interval_seconds = max(1.0, float(os.environ.get("EDGEBOX_HEARTBEAT_SECONDS", "30")))
    stop_event = Event()

    def request_stop(signum: int, _frame: object) -> None:
        LOG.info("EdgeBox received signal %s; shutting down", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    node = ComputeForgeNode(
        node_id=os.environ.get("EDGEBOX_NODE_ID", socket.gethostname()),
        node_type=os.environ.get("EDGEBOX_NODE_TYPE", "rtx"),
        storage=DurableInferenceStorage(data_dir / "durable_inference"),
    )
    LOG.info("EdgeBox Compute Forge node started")
    run_service(
        node=node,
        stop_event=stop_event,
        snapshot_path=data_dir / "status.json",
        interval_seconds=interval_seconds,
    )
    LOG.info("EdgeBox Compute Forge node stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
