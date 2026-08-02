"""Medium-sized fixture for governed Pair Programmer provider tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Iterable, Mapping


@dataclass
class WorkItem:
    """A unit of work tracked by the local queue."""

    title: str
    owner: str
    tags: list[str] = field(default_factory=list)
    completed: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def fingerprint(self) -> str:
        payload = f"{self.title}|{self.owner}|{','.join(sorted(self.tags))}"
        return sha256(payload.encode("utf-8")).hexdigest()[:16]


class WorkQueue:
    """Small in-memory queue with filtering and summary operations."""

    def __init__(self, items: Iterable[WorkItem] = ()) -> None:
        self._items: list[WorkItem] = list(items)

    def add(self, title: str, owner: str, *, tags: Iterable[str] = ()) -> WorkItem:
        item = WorkItem(title=title.strip(), owner=owner.strip(), tags=list(tags))
        if not item.title or not item.owner:
            raise ValueError("title and owner are required")
        self._items.append(item)
        return item

    def complete(self, fingerprint: str) -> WorkItem:
        for item in self._items:
            if item.fingerprint() == fingerprint:
                item.completed = True
                return item
        raise KeyError(f"unknown work item: {fingerprint}")

    def pending(self, owner: str | None = None) -> list[WorkItem]:
        return [
            item
            for item in self._items
            if not item.completed and (owner is None or item.owner == owner)
        ]

    def summary(self) -> Mapping[str, int]:
        total = len(self._items)
        completed = sum(item.completed for item in self._items)
        owners = len({item.owner for item in self._items})
        return {"total": total, "completed": completed, "pending": total - completed, "owners": owners}


def build_demo_queue() -> WorkQueue:
    queue = WorkQueue()
    queue.add("Review provider route", "maya", tags=["review", "provider"])
    queue.add("Add focused regression test", "devon", tags=["test"])
    queue.add("Document rollback path", "maya", tags=["docs", "release"])
    return queue

