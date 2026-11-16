"""Per-(provider, model, task_family, placement) capability scorecard (step 6: learn).

Every governed model call ends in a verifier verdict.  This module turns
those verdicts into a persistent map of what each model is actually good at,
and ranks candidates for the next call:

* pass rate: Beta(1,1)-smoothed, exponentially decayed (half-life in events),
  so old evidence fades and a model that improves can win back traffic;
* JSON validity rate (did the constrained decode produce a schema-valid action);
* tokens per accepted patch, latency EWMA, spend, failure kinds;
* placement: where the weights ran ("cloud", "gpu_full", "hybrid:<n>",
  "cpu"), so local models are scored per offload split;
* shift on failure: ``consecutive_failures >= demote_after`` demotes a cell
  for ``cooldown`` subsequent rankings (circuit-like, but learned per family);
* exploration: deterministic UCB1 bonus so unseen/under-sampled candidates get
  tried without randomness (tests are reproducible).

Unseen families fall back to the candidate's cross-family aggregate ("*").
Persisted atomically as JSON under ``.beast/``; never stores prompts, outputs
or credentials, only counters.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

DEFAULT_PATH = Path(__file__).resolve().parents[3] / ".beast" / "capability_scorecard.json"


def enabled(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return str(env.get("BEAST_CAPABILITY_ROUTER", "0")).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Cell:
    attempts: float = 0.0
    passes: float = 0.0
    json_valid: float = 0.0
    tokens_accepted: float = 0.0
    accepted: float = 0.0
    latency_ms_ewma: float = 0.0
    spend_usd: float = 0.0
    consecutive_failures: int = 0
    cooldown_left: int = 0
    failures: Dict[str, int] = field(default_factory=dict)
    raw_attempts: int = 0
    last_ts: float = 0.0

    def pass_rate(self) -> float:
        return (self.passes + 1.0) / (self.attempts + 2.0)

    def json_rate(self) -> float:
        return (self.json_valid + 1.0) / (self.attempts + 2.0)

    def tokens_per_accept(self) -> Optional[float]:
        return self.tokens_accepted / self.accepted if self.accepted else None


def cell_key(provider: str, model: str, family: str, placement: str) -> str:
    return f"{provider}|{model}|{family}|{placement or 'cloud'}"


class CapabilityScorecard:
    def __init__(self, path: str | Path | None = None, *, half_life: float = 20.0, demote_after: int = 2,
                 cooldown: int = 3, explore_c: float = 0.35, token_weight: float = 0.08,
                 latency_weight: float = 0.05, persist: bool = True):
        self.path = Path(path) if path is not None else DEFAULT_PATH
        self.decay = 0.5 ** (1.0 / max(1.0, half_life))
        self.demote_after = max(1, int(demote_after))
        self.cooldown = max(0, int(cooldown))
        self.explore_c = float(explore_c)
        self.token_weight = float(token_weight)
        self.latency_weight = float(latency_weight)
        self.persist = persist
        self.cells: Dict[str, Cell] = {}
        self._lock = threading.RLock()
        if persist and self.path.exists():
            self.load()

    # -- persistence ---------------------------------------------------------------------------
    def load(self) -> None:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.cells = {k: Cell(**v) for k, v in (data.get("cells") or {}).items()}

    def save(self) -> None:
        if not self.persist:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema": "beast.capability_scorecard.v1", "updated": time.time(),
                   "cells": {k: asdict(v) for k, v in sorted(self.cells.items())}}
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".scorecard.", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=1, sort_keys=True)
        os.replace(tmp, self.path)

    # -- updates -------------------------------------------------------------------------------
    def _cell(self, key: str) -> Cell:
        return self.cells.setdefault(key, Cell())

    def record(self, *, provider: str, model: str, family: str, placement: str = "cloud", passed: bool,
               json_valid: bool, tokens: int = 0, latency_ms: float = 0.0, spend_usd: float = 0.0,
               failure_kind: str = "", now: float | None = None) -> Dict[str, Any]:
        now = time.time() if now is None else now
        with self._lock:
            touched = []
            # liveness probes (family "smoke*") prove a route answers; they are not capability evidence,
            # so they never feed the cross-family "*" aggregate used as the fallback score.
            fams = (family,) if str(family).startswith("smoke") else (family, "*")
            for fam in fams:
                cell = self._cell(cell_key(provider, model, fam, placement))
                cell.attempts = cell.attempts * self.decay + 1.0
                cell.passes = cell.passes * self.decay + (1.0 if passed else 0.0)
                cell.json_valid = cell.json_valid * self.decay + (1.0 if json_valid else 0.0)
                cell.raw_attempts += 1
                if passed:
                    cell.accepted = cell.accepted * self.decay + 1.0
                    cell.tokens_accepted = cell.tokens_accepted * self.decay + float(tokens)
                    cell.consecutive_failures = 0
                    cell.cooldown_left = 0
                else:
                    cell.consecutive_failures += 1
                    kind = failure_kind or ("json_invalid" if not json_valid else "verifier_reject")
                    cell.failures[kind] = cell.failures.get(kind, 0) + 1
                    if cell.consecutive_failures >= self.demote_after:
                        cell.cooldown_left = self.cooldown
                alpha = 0.3
                cell.latency_ms_ewma = latency_ms if cell.raw_attempts == 1 else (
                    alpha * latency_ms + (1 - alpha) * cell.latency_ms_ewma)
                cell.spend_usd += float(spend_usd)
                cell.last_ts = now
                touched.append(cell_key(provider, model, fam, placement))
            self.save()
            return {"cells": touched}

    # -- ranking -------------------------------------------------------------------------------
    def score(self, provider: str, model: str, family: str, placement: str = "cloud", *,
              total_attempts: float = 1.0) -> Dict[str, Any]:
        key = cell_key(provider, model, family, placement)
        cell = self.cells.get(key)
        source = "family"
        if cell is None or cell.attempts < 0.5:
            agg = self.cells.get(cell_key(provider, model, "*", placement))
            if agg is not None and agg.attempts >= 0.5:
                cell, source = agg, "aggregate"
            else:
                cell, source = Cell(), "prior"
        quality = cell.pass_rate() * (0.5 + 0.5 * cell.json_rate())
        tpa = cell.tokens_per_accept()
        cost = self.token_weight * math.log10(1.0 + (tpa or 1500.0) / 100.0)
        cost += self.latency_weight * math.log10(1.0 + (cell.latency_ms_ewma or 5000.0) / 1000.0)
        # UCB-style exploration, capped at explore_c: with 30+ candidates log(total) otherwise lets every unseen
        # (often paid) lane outrank cells with real family evidence before any exploitation happens.
        bonus = min(self.explore_c, self.explore_c * math.sqrt(math.log(max(2.0, total_attempts)) / (cell.attempts + 1.0)))
        demoted = cell.cooldown_left > 0 and source == "family"
        value = quality - cost + bonus - (1.0 if demoted else 0.0)
        return {"key": key, "value": round(value, 6), "quality": round(quality, 6), "cost": round(cost, 6),
                "explore_bonus": round(bonus, 6), "demoted": demoted, "source": source,
                "pass_rate": round(cell.pass_rate(), 4), "json_rate": round(cell.json_rate(), 4),
                "attempts": round(cell.attempts, 3)}

    def rank(self, candidates: Iterable[Mapping[str, Any]], family: str, *, consume_cooldown: bool = True) -> List[Dict[str, Any]]:
        cands = list(candidates)
        with self._lock:
            total = sum((self.cells.get(cell_key(c["provider"], c["model"], family, c.get("placement", "cloud"))) or Cell()).attempts
                        for c in cands) + 1.0
            scored = []
            for index, cand in enumerate(cands):
                s = self.score(cand["provider"], cand["model"], family, cand.get("placement", "cloud"), total_attempts=total)
                # Stable tie-break on the caller's static preference order (cheapest first).
                scored.append({**dict(cand), "score": s, "_order": index})
            scored.sort(key=lambda x: (-x["score"]["value"], x["_order"]))
            if consume_cooldown:
                for item in scored:
                    cell = self.cells.get(item["score"]["key"])
                    if cell is not None and cell.cooldown_left > 0:
                        cell.cooldown_left -= 1
                self.save()
            for item in scored:
                item.pop("_order", None)
            return scored

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            rows = []
            for key, cell in sorted(self.cells.items()):
                provider, model, family, placement = key.split("|", 3)
                rows.append({"provider": provider, "model": model, "family": family, "placement": placement,
                             "attempts": cell.raw_attempts, "pass_rate": round(cell.pass_rate(), 3),
                             "json_rate": round(cell.json_rate(), 3), "tokens_per_accept": cell.tokens_per_accept(),
                             "latency_ms_ewma": round(cell.latency_ms_ewma, 1), "spend_usd": round(cell.spend_usd, 6),
                             "failures": dict(cell.failures), "consecutive_failures": cell.consecutive_failures,
                             "cooldown_left": cell.cooldown_left})
            return {"cells": rows}


__all__ = ["CapabilityScorecard", "Cell", "cell_key", "enabled", "DEFAULT_PATH"]
