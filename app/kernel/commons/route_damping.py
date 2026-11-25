"""BGP-inspired instability damping for Commons routes and providers.

Hand-reset a stuck NIM or Ollama planner route by deleting
`{workspace}/.beast/agent_runs/nim_route_damping.json` (and the repo-root
copy if present) or by calling `RouteFlapDampener(path=...).reset()`.
A backend change still needs `bin/beast heal` before the running gateway
picks up new dampener behavior.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import time
import json
from pathlib import Path
from threading import RLock
import os
import fcntl
from contextlib import contextmanager


@dataclass
class RouteScore:
    route_id: str
    penalty: float = 0.0
    updated_at: float = 0.0
    last_failure_at: float = 0.0
    last_probe_at: float = 0.0


def _score_from_dict(route_id: str, value: dict) -> RouteScore:
    if not isinstance(value, dict):
        return RouteScore(route_id)
    allowed = {field.name for field in RouteScore.__dataclass_fields__.values()}
    payload = {key: value[key] for key in value if key in allowed}
    payload.setdefault("route_id", route_id)
    return RouteScore(**payload)


class RouteFlapDampener:
    EVENTS={"timeout":200,"429":100,"schema":250,"attestation":1000,"incorrect":500,"success":-25}
    def __init__(self, *, suppress_at: float = 1000.0, half_life_seconds: float = 300.0, path: str | Path | None = None, strict_load: bool = False):
        if suppress_at<=0 or half_life_seconds<=0: raise ValueError("invalid damping policy")
        self.suppress_at, self.half_life = suppress_at, half_life_seconds
        self.path=Path(path) if path else None; self.routes: dict[str, RouteScore] = {}; self._lock=RLock()
        if self.path and self.path.exists():
            try: self.routes={key: _score_from_dict(key, value) for key,value in json.loads(self.path.read_text(encoding="utf-8")).items()}
            except Exception as exc:
                if strict_load: raise ValueError("corrupt route damping state") from exc
                self.routes={}

    def record(self, route_id: str, event: str, *, now: float | None = None) -> RouteScore:
        if not route_id or event not in self.EVENTS: raise ValueError("unknown route or damping event")
        now = time.time() if now is None else now
        with self._lock:
            with self._state_lock():
                self._reload()
                score = self.routes.setdefault(route_id, RouteScore(route_id, 0.0, now))
                score.penalty *= math.pow(0.5, max(0.0, now - score.updated_at) / self.half_life)
                score.penalty += self.EVENTS[event]
                score.penalty = max(0.0, score.penalty); score.updated_at = now
                if event != "success":
                    score.last_failure_at = now
                self._persist()
                return RouteScore(score.route_id, score.penalty, score.updated_at, score.last_failure_at, score.last_probe_at)

    def score(self, route_id: str, *, now: float | None = None) -> RouteScore:
        """Return a decayed score without requiring a new route event."""
        now = time.time() if now is None else now
        with self._lock:
            with self._state_lock():
                self._reload(); score=self.routes.get(route_id)
                if score is None: return RouteScore(route_id,0.0,now)
                score.penalty *= math.pow(0.5, max(0.0, now - score.updated_at) / self.half_life)
                score.updated_at = now; self._persist()
                return RouteScore(score.route_id, score.penalty, score.updated_at, score.last_failure_at, score.last_probe_at)

    def suppressed(self, route_id: str, *, now: float | None = None) -> bool:
        return self.score(route_id, now=now).penalty >= self.suppress_at

    def allow_probe(self, route_id: str, *, now: float | None = None, cooldown_seconds: float | None = None) -> bool:
        """Half-open circuit: allow one real retry after a cooldown even if still suppressed.

        Checking this does not add a penalty. A caller must not record a timeout
        merely because the route was suppressed.
        """
        now = time.time() if now is None else now
        cooldown = self.half_life if cooldown_seconds is None else max(1.0, float(cooldown_seconds))
        with self._lock:
            with self._state_lock():
                self._reload()
                score = self.routes.get(route_id)
                if score is None:
                    return True
                score.penalty *= math.pow(0.5, max(0.0, now - score.updated_at) / self.half_life)
                score.updated_at = now
                if score.penalty < self.suppress_at:
                    self._persist()
                    return True
                last_event = max(float(score.last_failure_at or 0.0), float(score.last_probe_at or 0.0))
                if last_event and (now - last_event) < cooldown:
                    self._persist()
                    return False
                score.last_probe_at = now
                self._persist()
                return True

    def reset(self, route_id: str | None = None) -> None:
        """Clear persisted damping for one route, or for every route if omitted."""
        with self._lock:
            with self._state_lock():
                self._reload()
                if route_id:
                    self.routes.pop(route_id, None)
                else:
                    self.routes = {}
                self._persist()

    def snapshot(self, *, now: float | None = None) -> dict:
        moment = time.time() if now is None else now
        with self._lock:
            with self._state_lock():
                self._reload(); snapshot = {}
                for route_id, score in self.routes.items():
                    score.penalty *= math.pow(0.5, max(0.0, moment - score.updated_at) / self.half_life)
                    score.updated_at = moment
                    snapshot[route_id] = {
                        "penalty": score.penalty,
                        "suppressed": score.penalty >= self.suppress_at,
                    }
                self._persist()
                return snapshot

    @contextmanager
    def _state_lock(self):
        if not self.path:
            yield; return
        self.path.parent.mkdir(parents=True,exist_ok=True)
        lock_path=self.path.with_suffix(self.path.suffix+".lock")
        with lock_path.open("a+") as handle:
            fcntl.flock(handle.fileno(),fcntl.LOCK_EX)
            try: yield
            finally: fcntl.flock(handle.fileno(),fcntl.LOCK_UN)

    def _reload(self):
        if not self.path or not self.path.exists(): return
        values=json.loads(self.path.read_text(encoding="utf-8"))
        self.routes={key: _score_from_dict(key, value) for key,value in values.items()}

    def _persist(self):
        if not self.path: return
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix(self.path.suffix+".tmp")
        with temp.open("w",encoding="utf-8") as handle:
            handle.write(json.dumps({key:value.__dict__ for key,value in self.routes.items()},sort_keys=True))
            handle.flush(); os.fsync(handle.fileno())
        temp.replace(self.path)
        directory=os.open(self.path.parent,os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
