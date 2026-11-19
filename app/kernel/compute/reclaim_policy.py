"""Ordered, bounded reclaim policy for host memory pressure.

The census recorded three separate mechanisms that knew about pressure but
never talked to each other:

* :class:`~app.kernel.compute.residual_pressure_governor.ResidualPressureGovernor`
  classifies PSI into ``low``/``rising``/``high``/``critical``;
* :class:`~app.kernel.compute.crystal_kv_index.CrystalKVIndex` can evict KV
  crystals, but nothing called it under pressure;
* :class:`~app.kernel.execution.cgroup_capsule.CgroupMissionCapsule` can write
  ``memory.reclaim`` and ``cgroup.kill``, but nothing scheduled those either.

This module is the scheduler.  It applies a fixed, escalating order and stops
as soon as the requested bytes have actually been recovered:

1. **KV crystal eviction** — cheapest, reversible, no process impact.
2. **Capsule ``memory.reclaim``** — drops reclaimable page cache inside a
   mission cgroup; a task is never killed.
3. **Capsule freeze** — only under ``critical`` and only with an explicit
   authorization for that mission.
4. **Capsule kill** — only under ``critical``, only with an explicit
   *destructive* authorization, and only when the caller opted in.

Honesty rules encoded here
--------------------------
* Every step reports the bytes the kernel/tier actually observed, never the
  bytes that were requested.  A step that cannot run is recorded as
  ``unavailable`` with its reason; it is never silently skipped.
* Freeze and kill require a per-mission
  :class:`~app.kernel.execution.cgroup_capsule.CgroupAuthorization` supplied by
  the caller.  Without one they are recorded as ``refused``, not performed.
* Request targets are bounded by the policy's own byte caps, never by a
  fraction of host RAM, so a large host cannot trigger an unbounded reclaim.
* ``rising`` pressure is advisory: the policy emits a plan and takes no action.

The receipt is ``beast_object_type: reclaim_receipt`` (larger object 1.0).
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

RECLAIM_AUTHORITY = "ordered_pressure_reclaim_v1"
DEFAULT_MIN_LEVEL = "high"
LEVEL_ORDER = {"low": 0, "rising": 1, "unknown": 1, "high": 2, "critical": 3}

# Per-capsule asks stay small: memory.reclaim is a polite hint, not a cudgel.
DEFAULT_PER_CAPSULE_CAP_BYTES = 64 * 1024 * 1024
DEFAULT_TOTAL_CAP_BYTES = 512 * 1024 * 1024


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class ReclaimStep:
    """Outcome of one rung in the reclaim ladder."""

    step: str
    status: str  # "performed" | "unavailable" | "refused" | "empty"
    requested_bytes: int = 0
    freed_bytes: int = 0
    target: str = ""
    reason: str = ""
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "status": self.status,
            "requested_bytes": int(self.requested_bytes),
            "freed_bytes": int(self.freed_bytes),
            "target": self.target,
            "reason": self.reason,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class ReclaimReceipt:
    """Durable record of one pressure episode."""

    pressure_level: str
    acted: bool
    requested_bytes: int
    freed_bytes: int
    steps: tuple[ReclaimStep, ...]
    stopped_because: str
    snapshot_digest: str = ""
    policy_digest: str = ""
    authority: str = RECLAIM_AUTHORITY
    observed_at_ns: int = field(default_factory=time.time_ns)

    @property
    def satisfied(self) -> bool:
        if self.requested_bytes <= 0:
            return True
        return self.freed_bytes >= self.requested_bytes

    def as_dict(self) -> dict[str, Any]:
        return {
            "beast_object_type": "reclaim_receipt",
            "version": "1.0",
            "pressure_level": self.pressure_level,
            "acted": bool(self.acted),
            "requested_bytes": int(self.requested_bytes),
            "freed_bytes": int(self.freed_bytes),
            "satisfied": self.satisfied,
            "stopped_because": self.stopped_because,
            "snapshot_digest": self.snapshot_digest,
            "policy_digest": self.policy_digest,
            "steps": [step.as_dict() for step in self.steps],
            "authority": self.authority,
            "observed_at_ns": int(self.observed_at_ns),
        }


class ReclaimPolicy:
    """Ordered reclaim ladder over the KV tier and mission capsules.

    ``capsules`` is a mapping of ``mission_id -> CgroupMissionCapsule``.  The
    policy never creates capsules; if cgroup delegation is unavailable that is
    the caller's problem to report, and this policy simply finds no targets.
    """

    def __init__(
        self,
        *,
        kv_tier: Any = None,
        capsules: Mapping[str, Any] | None = None,
        discovery: Any = None,
        min_level: str = DEFAULT_MIN_LEVEL,
        per_capsule_cap_bytes: int = DEFAULT_PER_CAPSULE_CAP_BYTES,
        total_cap_bytes: int = DEFAULT_TOTAL_CAP_BYTES,
        allow_freeze: bool = False,
        allow_kill: bool = False,
    ):
        if min_level not in LEVEL_ORDER:
            raise ValueError(f"unknown min_level: {min_level}")
        if per_capsule_cap_bytes <= 0 or per_capsule_cap_bytes > DEFAULT_TOTAL_CAP_BYTES:
            raise ValueError("per_capsule_cap_bytes must be positive and bounded")
        if total_cap_bytes <= 0:
            raise ValueError("total_cap_bytes must be positive")
        self.kv_tier = kv_tier
        self.capsules: dict[str, Any] = dict(capsules or {})
        self.discovery = discovery
        self.min_level = min_level
        self.per_capsule_cap_bytes = int(per_capsule_cap_bytes)
        self.total_cap_bytes = int(total_cap_bytes)
        self.allow_freeze = bool(allow_freeze)
        self.allow_kill = bool(allow_kill)

    # -- planning ---------------------------------------------------------
    def should_act(self, pressure_level: str) -> bool:
        level = str(pressure_level).strip().lower()
        if level not in LEVEL_ORDER:
            raise ValueError(f"unknown pressure_level: {pressure_level}")
        return LEVEL_ORDER[level] >= LEVEL_ORDER[self.min_level]

    def _requested_bytes(self, pressure_level: str) -> int:
        """Bounded target derived from the tier's own reclaimable bytes."""
        level = str(pressure_level).strip().lower()
        reclaimable = 0
        if self.kv_tier is not None:
            try:
                reclaimable = int(self.kv_tier.stats().get("kv_bytes", 0))
            except Exception:  # noqa: BLE001 - stats failures must not abort reclaim
                reclaimable = 0
        fraction = {"high": 0.15, "critical": 0.35}.get(level, 0.0)
        target = int(round(reclaimable * fraction))
        return max(0, min(target, self.total_cap_bytes))

    # -- execution --------------------------------------------------------
    def run(
        self,
        pressure_level: str,
        *,
        snapshot_digest: str = "",
        authorization_factory: Callable[[str, str], Any] | None = None,
    ) -> ReclaimReceipt:
        """Apply the ladder for ``pressure_level`` and return a receipt.

        ``authorization_factory(mission_id, action)`` must return a
        ``CgroupAuthorization`` scoped to that mission and action, or ``None``.
        ``None`` means "not authorized", and freeze/kill are recorded as
        ``refused``.
        """
        level = str(pressure_level).strip().lower()
        if level not in LEVEL_ORDER:
            raise ValueError(f"unknown pressure_level: {pressure_level}")

        requested = self._requested_bytes(level)
        policy_digest = _digest(
            {
                "authority": RECLAIM_AUTHORITY,
                "min_level": self.min_level,
                "per_capsule_cap_bytes": self.per_capsule_cap_bytes,
                "total_cap_bytes": self.total_cap_bytes,
                "allow_freeze": self.allow_freeze,
                "allow_kill": self.allow_kill,
                "has_kv_tier": self.kv_tier is not None,
                "capsules": sorted(self.capsules),
            }
        )

        if not self.should_act(level):
            return ReclaimReceipt(
                pressure_level=level,
                acted=False,
                requested_bytes=0,
                freed_bytes=0,
                steps=(ReclaimStep(
                    step="advisory_only",
                    status="empty",
                    reason=f"{level} is below the {self.min_level} actuation threshold",
                ),),
                stopped_because="below_threshold",
                snapshot_digest=snapshot_digest,
                policy_digest=policy_digest,
            )

        steps: list[ReclaimStep] = []
        freed = 0

        # Rung 1: KV crystal eviction (reversible, no process impact).
        step, gained = self._kv_step(level)
        steps.append(step)
        freed += gained
        if requested > 0 and freed >= requested:
            return self._finish(level, requested, freed, steps, "target_met", snapshot_digest, policy_digest)

        # Rung 2: cgroup memory.reclaim (drops page cache, keeps tasks alive).
        for mission_id, capsule in self.capsules.items():
            remaining = max(0, requested - freed)
            if requested > 0 and remaining == 0:
                break
            ask = min(self.per_capsule_cap_bytes, remaining or self.per_capsule_cap_bytes)
            step, gained = self._capsule_reclaim(mission_id, capsule, ask, authorization_factory)
            steps.append(step)
            freed += gained
            if requested > 0 and freed >= requested:
                return self._finish(level, requested, freed, steps, "target_met", snapshot_digest, policy_digest)

        # Rung 3/4: freeze and kill, critical only, authorization required.
        if level == "critical":
            for mission_id, capsule in self.capsules.items():
                remaining = max(0, requested - freed)
                if requested > 0 and remaining == 0:
                    break
                if self.allow_freeze:
                    step = self._capsule_freeze(mission_id, capsule, authorization_factory)
                    steps.append(step)
                if self.allow_kill and (requested == 0 or freed < requested):
                    step = self._capsule_kill(mission_id, capsule, authorization_factory)
                    steps.append(step)
                if requested > 0 and freed >= requested:
                    return self._finish(level, requested, freed, steps, "target_met", snapshot_digest, policy_digest)

        stopped = "target_met" if requested > 0 and freed >= requested else "steps_exhausted"
        return self._finish(level, requested, freed, steps, stopped, snapshot_digest, policy_digest)

    # -- rungs ------------------------------------------------------------
    def _kv_step(self, level: str) -> tuple[ReclaimStep, int]:
        if self.kv_tier is None:
            return ReclaimStep(
                step="kv_crystal_eviction",
                status="unavailable",
                reason="no crystal KV tier is bound to this policy",
            ), 0
        try:
            receipt = self.kv_tier.reclaim(level)
        except Exception as error:  # noqa: BLE001 - a failing tier must not abort the ladder
            return ReclaimStep(
                step="kv_crystal_eviction",
                status="unavailable",
                reason=f"tier reclaim raised: {error}",
            ), 0
        if not receipt:
            return ReclaimStep(
                step="kv_crystal_eviction",
                status="empty",
                reason="tier had nothing reclaimable at this pressure level",
            ), 0
        freed = int(receipt.get("freed_bytes", 0))
        if freed <= 0 and not receipt.get("evicted"):
            return ReclaimStep(
                step="kv_crystal_eviction",
                status="empty",
                requested_bytes=int(receipt.get("requested_bytes", 0)),
                reason="tier is empty or every crystal is pinned",
                evidence=dict(receipt),
            ), 0
        return ReclaimStep(
            step="kv_crystal_eviction",
            status="performed",
            requested_bytes=int(receipt.get("requested_bytes", 0)),
            freed_bytes=freed,
            evidence=dict(receipt),
        ), freed

    def _capsule_reclaim(
        self,
        mission_id: str,
        capsule: Any,
        ask: int,
        authorization_factory: Callable[[str, str], Any] | None,
    ) -> tuple[ReclaimStep, int]:
        authorization = authorization_factory(mission_id, "reclaim") if authorization_factory else None
        if authorization is None:
            return ReclaimStep(
                step="cgroup_memory_reclaim",
                status="refused",
                requested_bytes=ask,
                target=mission_id,
                reason="no scoped authorization for memory.reclaim",
            ), 0
        try:
            receipt = capsule.reclaim_memory(ask, authorization)
        except Exception as error:  # noqa: BLE001
            return ReclaimStep(
                step="cgroup_memory_reclaim",
                status="unavailable",
                requested_bytes=ask,
                target=mission_id,
                reason=str(error),
            ), 0
        details = receipt.get("details", {}) if isinstance(receipt, Mapping) else {}
        gained = int(details.get("reclaimed_bytes") or 0)
        return ReclaimStep(
            step="cgroup_memory_reclaim",
            status="performed" if receipt.get("confirmed") else "empty",
            requested_bytes=ask,
            freed_bytes=gained,
            target=mission_id,
            evidence=dict(receipt),
        ), gained

    def _capsule_freeze(
        self,
        mission_id: str,
        capsule: Any,
        authorization_factory: Callable[[str, str], Any] | None,
    ) -> ReclaimStep:
        authorization = authorization_factory(mission_id, "freeze") if authorization_factory else None
        if authorization is None:
            return ReclaimStep(
                step="cgroup_freeze",
                status="refused",
                target=mission_id,
                reason="no scoped authorization for freeze",
            )
        try:
            receipt = capsule.freeze(True, authorization)
        except Exception as error:  # noqa: BLE001
            return ReclaimStep(
                step="cgroup_freeze",
                status="unavailable",
                target=mission_id,
                reason=str(error),
            )
        return ReclaimStep(
            step="cgroup_freeze",
            status="performed" if receipt.get("confirmed") else "empty",
            target=mission_id,
            evidence=dict(receipt),
        )

    def _capsule_kill(
        self,
        mission_id: str,
        capsule: Any,
        authorization_factory: Callable[[str, str], Any] | None,
    ) -> ReclaimStep:
        authorization = authorization_factory(mission_id, "kill") if authorization_factory else None
        if authorization is None:
            return ReclaimStep(
                step="cgroup_kill",
                status="refused",
                target=mission_id,
                reason="no destructive authorization for kill",
            )
        # Defense in depth: the capsule enforces this too, but the policy must
        # not even call ``kill`` on a non-destructive authorization.
        if not bool(getattr(authorization, "destructive", False)):
            return ReclaimStep(
                step="cgroup_kill",
                status="refused",
                target=mission_id,
                reason="authorization is not marked destructive",
            )
        try:
            receipt = capsule.kill(authorization)
        except Exception as error:  # noqa: BLE001
            return ReclaimStep(
                step="cgroup_kill",
                status="unavailable",
                target=mission_id,
                reason=str(error),
            )
        return ReclaimStep(
            step="cgroup_kill",
            status="performed",
            target=mission_id,
            evidence=dict(receipt),
        )

    # -- receipt ----------------------------------------------------------
    def _finish(
        self,
        level: str,
        requested: int,
        freed: int,
        steps: Iterable[ReclaimStep],
        stopped: str,
        snapshot_digest: str,
        policy_digest: str,
    ) -> ReclaimReceipt:
        step_tuple = tuple(steps)
        # "Acted" means something was actually reclaimed or actuated.  An empty
        # tier must not produce acted=true with freed_bytes=0.
        acted = any(
            (step.freed_bytes > 0) or (step.status == "performed" and step.step in {"cgroup_freeze", "cgroup_kill"})
            for step in step_tuple
        )
        return ReclaimReceipt(
            pressure_level=level,
            acted=acted,
            requested_bytes=requested,
            freed_bytes=int(freed),
            steps=step_tuple,
            stopped_because=stopped,
            snapshot_digest=snapshot_digest,
            policy_digest=policy_digest,
        )


__all__ = [
    "RECLAIM_AUTHORITY",
    "ReclaimPolicy",
    "ReclaimReceipt",
    "ReclaimStep",
]
