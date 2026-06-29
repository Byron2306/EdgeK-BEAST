"""Temporal crystal forks and annealing for compute capability channels."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


CHANNELS = {"stable", "candidate", "experimental"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True)
class TemporalCrystalFork:
    fork_id: str
    capability_id: str
    task_class: str
    channel: str
    parent_fork_id: str = ""
    traffic_share: float = 0.0
    clean_completions: int = 0
    failures: int = 0
    rollback_successes: int = 0
    friction_total: float = 0.0
    cost_total_usd: float = 0.0
    confidence: float = 0.0
    state: str = "active"
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["beast_object_type"] = "temporal_crystal_fork"
        payload["version"] = "1.0"
        return payload


class TemporalCrystalForkManager:
    """Persisted stable/candidate/experimental channels with bounded promotion."""

    MAX_TRAFFIC = {
        "stable": 1.0,
        "candidate": 0.25,
        "experimental": 0.05,
    }
    PROMOTION_MIN_CLEAN = 3
    PROMOTION_MIN_CONFIDENCE = 0.80
    PROMOTION_MAX_FAILURE_RATE = 0.05
    PROMOTION_MAX_FRICTION = 0.35

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        self.storage_path = Path(storage_path) if storage_path else None
        self._forks: Dict[str, TemporalCrystalFork] = {}
        self._events: List[Dict[str, Any]] = []
        self._load()

    def create_fork(
        self,
        capability_id: str,
        task_class: str,
        *,
        channel: str = "candidate",
        parent_fork_id: str = "",
        traffic_share: float = 0.0,
        confidence: float = 0.0,
    ) -> TemporalCrystalFork:
        if channel not in CHANNELS:
            raise ValueError("channel must be stable, candidate, or experimental")
        capability_id = str(capability_id).strip()
        task_class = str(task_class or "general").strip()
        if not capability_id:
            raise ValueError("capability_id is required")
        now = _now()
        fork_id = "fork_" + hashlib.sha256(
            _canonical([capability_id, task_class, channel, parent_fork_id, now]).encode()
        ).hexdigest()[:20]
        fork = TemporalCrystalFork(
            fork_id=fork_id,
            capability_id=capability_id,
            task_class=task_class,
            channel=channel,
            parent_fork_id=str(parent_fork_id or ""),
            traffic_share=self._bounded_share(channel, traffic_share),
            confidence=max(0.0, min(1.0, float(confidence or 0.0))),
            created_at=now,
            updated_at=now,
        )
        self._forks[fork_id] = fork
        self._event("fork_created", fork_id=fork_id, channel=channel)
        self._persist()
        return fork

    def allocate_traffic(self, fork_id: str, share: float) -> TemporalCrystalFork:
        fork = self._require(fork_id)
        updated = replace(
            fork,
            traffic_share=self._bounded_share(fork.channel, share),
            updated_at=_now(),
        )
        self._forks[fork_id] = updated
        self._event("traffic_allocated", fork_id=fork_id, share=updated.traffic_share)
        self._persist()
        return updated

    def record_outcome(
        self,
        fork_id: str,
        *,
        clean_completion: bool,
        rollback_success: bool = True,
        friction_score: float = 0.0,
        cost_usd: float = 0.0,
    ) -> TemporalCrystalFork:
        fork = self._require(fork_id)
        clean = fork.clean_completions + int(bool(clean_completion))
        failures = fork.failures + int(not clean_completion)
        rollback = fork.rollback_successes + int(bool(rollback_success))
        friction_total = fork.friction_total + max(0.0, float(friction_score or 0.0))
        total = clean + failures
        clean_rate = clean / max(1, total)
        rollback_rate = rollback / max(1, total)
        avg_friction = friction_total / max(1, total)
        confidence = max(0.0, min(1.0, (0.55 * clean_rate) + (0.25 * rollback_rate) + (0.20 * (1.0 - min(1.0, avg_friction)))))
        state = fork.state
        if fork.channel == "experimental" and failures and failures / max(1, total) > 0.20:
            state = "rolled_back"
        updated = replace(
            fork,
            clean_completions=clean,
            failures=failures,
            rollback_successes=rollback,
            friction_total=friction_total,
            cost_total_usd=fork.cost_total_usd + max(0.0, float(cost_usd or 0.0)),
            confidence=round(confidence, 6),
            state=state,
            traffic_share=0.0 if state == "rolled_back" else fork.traffic_share,
            updated_at=_now(),
        )
        self._forks[fork_id] = updated
        self._event("outcome_recorded", fork_id=fork_id, state=state)
        if state == "rolled_back":
            self._event("automatic_rollback", fork_id=fork_id, reason="experimental_failure_rate")
        self._persist()
        return updated

    def promote(self, fork_id: str, *, approved_by: str = "system") -> TemporalCrystalFork:
        fork = self._require(fork_id)
        eligible, reason, _ = self.promotion_eligibility(fork_id)
        if not eligible:
            raise ValueError(reason)
        updated = replace(
            fork,
            channel="stable",
            traffic_share=1.0,
            state="active",
            updated_at=_now(),
        )
        self._forks[fork_id] = updated
        self._event("promoted_to_stable", fork_id=fork_id, approved_by=approved_by)
        self._persist()
        return updated

    def promotion_eligibility(self, fork_id: str) -> tuple[bool, str, Dict[str, Any]]:
        fork = self._require(fork_id)
        total = fork.clean_completions + fork.failures
        failure_rate = fork.failures / max(1, total)
        avg_friction = fork.friction_total / max(1, total)
        details = {
            "clean_completions": fork.clean_completions,
            "failure_rate": round(failure_rate, 6),
            "avg_friction": round(avg_friction, 6),
            "confidence": fork.confidence,
            "rollback_successes": fork.rollback_successes,
        }
        if fork.state != "active":
            return False, f"fork_{fork.state}", details
        if fork.channel == "experimental":
            return False, "experimental_must_graduate_to_candidate_first", details
        if fork.clean_completions < self.PROMOTION_MIN_CLEAN:
            return False, "insufficient_clean_completions", details
        if failure_rate > self.PROMOTION_MAX_FAILURE_RATE:
            return False, "failure_rate_above_threshold", details
        if avg_friction > self.PROMOTION_MAX_FRICTION:
            return False, "friction_above_threshold", details
        if fork.confidence < self.PROMOTION_MIN_CONFIDENCE:
            return False, "confidence_below_threshold", details
        return True, "eligible_for_stable_promotion", details

    def anneal(self) -> Dict[str, Any]:
        """Merge duplicates, split multimodal failures, and retire stale lineages."""
        merged = 0
        split = 0
        retired = 0
        active = [fork for fork in self._forks.values() if fork.state == "active"]
        by_key: Dict[tuple[str, str, str], List[TemporalCrystalFork]] = {}
        for fork in active:
            by_key.setdefault((fork.capability_id, fork.task_class, fork.channel), []).append(fork)
        for group in by_key.values():
            if len(group) < 2:
                continue
            keeper = max(group, key=lambda item: (item.confidence, item.clean_completions, -item.failures))
            for fork in group:
                if fork.fork_id == keeper.fork_id:
                    continue
                self._forks[fork.fork_id] = replace(fork, state="merged", traffic_share=0.0, updated_at=_now())
                merged += 1
                self._event("anneal_merged_duplicate", fork_id=fork.fork_id, target_fork_id=keeper.fork_id)
        for fork in list(self._forks.values()):
            total = fork.clean_completions + fork.failures
            if fork.state == "active" and fork.failures >= 2 and fork.clean_completions >= 2:
                child = self.create_fork(
                    f"{fork.capability_id}:failure-mode",
                    fork.task_class,
                    channel="experimental",
                    parent_fork_id=fork.fork_id,
                    traffic_share=0.0,
                    confidence=max(0.0, fork.confidence - 0.2),
                )
                split += 1
                self._event("anneal_split_multimodal", fork_id=fork.fork_id, child_fork_id=child.fork_id)
            if fork.state == "active" and total >= 3 and fork.clean_completions == 0:
                self._forks[fork.fork_id] = replace(fork, state="retired", traffic_share=0.0, updated_at=_now())
                retired += 1
                self._event("anneal_retired_stale", fork_id=fork.fork_id)
        self._persist()
        return {
            "beast_object_type": "crystal_annealing_report",
            "version": "1.0",
            "merged_duplicates": merged,
            "split_multimodal": split,
            "retired_stale": retired,
            "fork_count": len(self._forks),
        }

    def state(self) -> Dict[str, Any]:
        channels: Dict[str, int] = {channel: 0 for channel in CHANNELS}
        states: Dict[str, int] = {}
        for fork in self._forks.values():
            channels[fork.channel] = channels.get(fork.channel, 0) + 1
            states[fork.state] = states.get(fork.state, 0) + 1
        return {
            "beast_object_type": "temporal_crystal_fork_state",
            "version": "1.0",
            "channels": channels,
            "states": states,
            "forks": [fork.to_dict() for fork in self._forks.values()],
            "events": list(self._events[-50:]),
        }

    def _require(self, fork_id: str) -> TemporalCrystalFork:
        fork = self._forks.get(fork_id)
        if not fork:
            raise ValueError(f"fork not found: {fork_id}")
        return fork

    def _event(self, event_type: str, **values: Any) -> None:
        self._events.append({"event_type": event_type, "created_at": _now(), **values})

    def _bounded_share(self, channel: str, share: float) -> float:
        return round(max(0.0, min(float(share or 0.0), self.MAX_TRAFFIC[channel])), 6)

    def _persist(self) -> None:
        if self.storage_path is None:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "beast_object_type": "temporal_crystal_fork_store",
            "version": "1.0",
            "forks": {key: value.to_dict() for key, value in self._forks.items()},
            "events": self._events[-500:],
        }
        temp = self.storage_path.with_suffix(self.storage_path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        temp.replace(self.storage_path)

    def _load(self) -> None:
        if self.storage_path is None or not self.storage_path.is_file():
            return
        try:
            payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
            forks = payload.get("forks") if isinstance(payload, dict) else {}
            if isinstance(forks, dict):
                for key, value in forks.items():
                    if isinstance(value, dict):
                        allowed = {field: value.get(field) for field in TemporalCrystalFork.__dataclass_fields__}
                        self._forks[str(key)] = TemporalCrystalFork(**allowed)
            events = payload.get("events") if isinstance(payload, dict) else []
            if isinstance(events, list):
                self._events = [item for item in events if isinstance(item, dict)]
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            self._forks = {}
            self._events = []
