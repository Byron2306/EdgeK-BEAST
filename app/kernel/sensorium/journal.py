"""Durable, hash-chained Sensorium event journal."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Iterable

from app.kernel.sensorium.contracts import SensorEvent
from app.kernel.sensorium.event_sequencer import SequencedEvent


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def event_from_dict(value: dict) -> SensorEvent:
    ordering = value.get("ordering") or {}
    confidence = value.get("confidence") or {}
    event = SensorEvent(
        event_type=str(value.get("event_type") or ""), source=str(value.get("source") or ""),
        source_instance=str(value.get("source_instance") or ""), boot_id=str(ordering.get("boot_id") or ""),
        source_sequence=int(ordering.get("source_sequence") or 0), cpu_sequence=int(ordering.get("cpu_sequence") or 0),
        monotonic_ns=int(ordering.get("monotonic_ns") or 0), wall_time=str(ordering.get("wall_time") or ""),
        attribution=dict(value.get("attribution") or {}), confidence=float(confidence.get("value") or 0),
        confidence_method=str(confidence.get("method") or ""), gaps_before=int(confidence.get("gaps_before") or 0),
        loss_counter=int(confidence.get("loss_counter") or 0), privacy=dict(value.get("privacy") or {}),
        payload_schema=str(value.get("payload_schema") or ""), payload=dict(value.get("payload") or {}),
        payload_sha256=str(value.get("payload_sha256") or ""), event_id=str(value.get("event_id") or ""),
    )
    event.validate()
    return event


class SensoriumJournal:
    """SQLite durability plus an application-level hash chain for audit replay."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.integrity_ok = True
        self.integrity_fracture: dict | None = None
        self._initialize()
        self.verify()

    def _connect(self):
        connection = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _initialize(self):
        connection = self._connect()
        try:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS sensor_events (offset INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL, "
                "admitted_at TEXT NOT NULL, event_json TEXT NOT NULL, previous_hash TEXT NOT NULL, record_hash TEXT NOT NULL)"
            )
        finally:
            connection.close()

    def append(self, entry: SequencedEvent) -> str:
        if not self.integrity_ok:
            raise RuntimeError("refusing Sensorium append after journal integrity fracture")
        entry.event.validate()
        event_json = json.dumps(entry.event.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT offset,record_hash FROM sensor_events ORDER BY offset DESC LIMIT 1").fetchone()
            previous_offset, previous_hash = (int(row[0]), str(row[1])) if row else (0, "")
            if entry.offset != previous_offset + 1:
                raise ValueError("Sensorium journal offset is not contiguous")
            body = {"offset": entry.offset, "event_id": entry.event.event_id,
                    "admitted_at": entry.admitted_at, "event": json.loads(event_json)}
            record_hash = "sha256:" + hashlib.sha256(previous_hash.encode() + _canonical(body)).hexdigest()
            connection.execute(
                "INSERT INTO sensor_events(offset,event_id,admitted_at,event_json,previous_hash,record_hash) VALUES(?,?,?,?,?,?)",
                (entry.offset, entry.event.event_id, entry.admitted_at, event_json, previous_hash, record_hash),
            )
            connection.execute("COMMIT")
            return record_hash
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def verify(self) -> bool:
        self.integrity_ok = True
        self.integrity_fracture = None
        previous_hash = ""
        expected_offset = 1
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT offset,event_id,admitted_at,event_json,previous_hash,record_hash FROM sensor_events ORDER BY offset"
            ).fetchall()
        finally:
            connection.close()
        for offset, event_id, admitted_at, event_json, supplied_previous, supplied_hash in rows:
            try:
                event_value = json.loads(event_json)
                event = event_from_dict(event_value)
                body = {"offset": offset, "event_id": event_id, "admitted_at": admitted_at, "event": event_value}
                calculated = "sha256:" + hashlib.sha256(previous_hash.encode() + _canonical(body)).hexdigest()
                valid = (
                    offset == expected_offset and event.event_id == event_id
                    and supplied_previous == previous_hash and supplied_hash == calculated
                )
            except Exception:
                valid = False
            if not valid:
                self.integrity_ok = False
                self.integrity_fracture = {"offset": offset, "reason": "journal_chain_or_contract_mismatch"}
                return False
            previous_hash = supplied_hash
            expected_offset += 1
        return True

    def replay(self, *, tail: int | None = None) -> list[SequencedEvent]:
        if not self.verify():
            raise RuntimeError("Sensorium journal integrity verification failed")
        connection = self._connect()
        try:
            if tail is None:
                rows = connection.execute(
                    "SELECT offset,admitted_at,event_json FROM sensor_events ORDER BY offset"
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT offset,admitted_at,event_json FROM sensor_events ORDER BY offset DESC LIMIT ?", (max(0, tail),)
                ).fetchall()[::-1]
        finally:
            connection.close()
        return [SequencedEvent(int(offset), event_from_dict(json.loads(raw)), str(admitted)) for offset, admitted, raw in rows]

    def metrics(self) -> dict:
        connection = self._connect()
        try:
            row = connection.execute("SELECT COUNT(*),COALESCE(MAX(offset),0) FROM sensor_events").fetchone()
            head = connection.execute("SELECT record_hash FROM sensor_events ORDER BY offset DESC LIMIT 1").fetchone()
        finally:
            connection.close()
        return {"durable_events": int(row[0]), "durable_offset": int(row[1]),
                "head_hash": str(head[0]) if head else "", "integrity_ok": self.integrity_ok,
                "integrity_fracture": self.integrity_fracture}
