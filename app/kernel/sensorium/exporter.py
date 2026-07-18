"""Atomic downstream export for already-admitted Sensorium objects."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

from app.kernel.sensorium.contracts import RuntimeEpisode, SensorEvent
from app.kernel.sensorium.event_sequencer import SequencedEvent


class SensoriumOutboxExporter:
    def __init__(self, root: Path):
        self.root = Path(root)

    def export_entry(self, entry: SequencedEvent, *, external: bool = False) -> Path:
        event = entry.event
        self._check_event(event, external=external)
        return self._write(
            self.root / "events" / f"{entry.offset:020d}_{event.event_id.split(':')[-1][:16]}.json",
            entry.to_dict(include_payload=True),
        )

    def export_episode(self, episode: RuntimeEpisode) -> Path:
        episode.validate()
        return self._write(
            self.root / "episodes" / f"{episode.episode_hash.split(':')[-1]}.json",
            episode.to_dict(),
        )

    @staticmethod
    def _check_event(event: SensorEvent, *, external: bool) -> None:
        event.validate()
        if event.privacy.get("redaction_status") != "passed":
            raise ValueError("only privacy-scanned events may be exported")
        if external and event.privacy.get("export_allowed") is not True:
            raise PermissionError("event privacy policy forbids external export")

    @staticmethod
    def _write(path: Path, payload: Dict[str, Any]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True, default=str) + "\n"
        temporary_name = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_name = handle.name
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
        finally:
            if temporary_name and os.path.exists(temporary_name):
                os.unlink(temporary_name)
        return path
