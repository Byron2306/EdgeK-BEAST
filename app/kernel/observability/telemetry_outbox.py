import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

TELEMETRY_OUTBOX = Path("~/.beast/outbox/telemetry").expanduser()

class TelemetryOutbox:
    def __init__(self, root: Path | str | None = None):
        self.root = Path(root).expanduser() if root is not None else TELEMETRY_OUTBOX
        self.root.mkdir(parents=True, exist_ok=True)

    def enqueue(self, exporter: str, data: Dict[str, Any]):
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        filename = self.root / f"{exporter}_{timestamp}_{os.urandom(4).hex()}.json"
        with open(filename, "w") as f:
            json.dump(data, f, indent=2)

    def enqueue_decision(self, decision: Any):
        self.enqueue("decision", decision.to_dict())

    def enqueue_execution(self, request: Any, result: Dict[str, Any], receipt: Dict[str, Any]):
        self.enqueue("execution", {"request": request.to_dict(), "result": result, "receipt": receipt})

    def enqueue_compute_receipt(self, receipt: Any) -> None:
        payload = receipt.to_dict() if hasattr(receipt, "to_dict") else dict(receipt)
        self.enqueue("compute_receipt", payload)
