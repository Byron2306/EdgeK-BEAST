"""One physical byte budget for every tier a BEAST workload can occupy.

The census found the opposite: VRAM, host RAM, swap, the crystal KV store and
memfd crystals were each measured in a different place, and nothing refused a
placement because the *sum* did not fit.  This ledger is the single admission
point.

Pools
-----
``gpu_vram``   RTX 3050 free VRAM (``nvidia-smi``), the scarcest pool
``host_ram``   ``MemAvailable`` from ``/proc/meminfo``
``swap``       ``SwapFree`` from ``/proc/swaps``
``nvme_kv``    free bytes under the crystal KV root (``statvfs``)
``memfd``      anonymous in-memory crystals; shares host RAM, capped separately

Honesty rules
-------------
* A pool whose capacity cannot be probed is ``None``.  Admissions against an
  unknown pool are **denied** with ``capacity_unknown``; they are never assumed
  to fit.
* ``committed_bytes`` only counts live, unexpired leases.  ``available_bytes``
  is derived, not cached, so an out-of-band change cannot be hidden.
* Every admission and release is appended to a JSONL journal before it is
  acknowledged, and the journal is replayed on construction.  A restart cannot
  silently forget committed bytes.
* A lease may record the ``reclaim_receipt_digest`` that freed its space, so a
  placement can be traced back to the pressure episode that made it possible.

Receipts are ``physical_admission_receipt``, ``physical_release_receipt`` and
``physical_ledger_state`` (larger object 1.0).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

LEDGER_AUTHORITY = "physical_byte_budget_v1"
MAX_LEASE_BYTES = 1 << 40
POOL_NAMES = ("gpu_vram", "host_ram", "swap", "nvme_kv", "memfd")


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


# -- capacity probes -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PoolCapacity:
    pool: str
    capacity_bytes: int | None
    source: str
    observed_at_ns: int = field(default_factory=time.time_ns)

    def as_dict(self) -> dict[str, Any]:
        return {
            "pool": self.pool,
            "capacity_bytes": self.capacity_bytes,
            "source": self.source,
            "observed_at_ns": int(self.observed_at_ns),
        }


def _meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, _, raw = line.partition(":")
            parts = raw.split()
            if parts:
                try:
                    values[key.strip()] = int(parts[0]) * 1024
                except ValueError:
                    continue
    except OSError:
        pass
    return values


def _swap_free() -> int | None:
    try:
        lines = Path("/proc/swaps").read_text(encoding="utf-8").splitlines()[1:]
    except OSError:
        return None
    total = 0
    found = False
    for line in lines:
        parts = line.split()
        if len(parts) >= 4:
            try:
                total += int(parts[3]) * 1024
                found = True
            except ValueError:
                continue
    return total if found else None


def _gpu_free() -> int | None:
    binary = shutil.which("nvidia-smi")
    if not binary:
        return None
    try:
        out = subprocess.run(
            [binary, "--query-gpu=memory.total,memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    total_mib = used_mib = 0
    for line in out.strip().splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) >= 2:
            try:
                total_mib += int(parts[0])
                used_mib += int(parts[1])
            except ValueError:
                continue
    if total_mib <= 0:
        return None
    return max(0, total_mib - used_mib) * 1024 * 1024


def _disk_free(path: Path) -> int | None:
    try:
        usage = shutil.disk_usage(str(path))
    except OSError:
        return None
    return int(usage.free)


def probe_pools(
    *,
    kv_root: Path | str = "/",
    memfd_cap_bytes: int | None = None,
) -> dict[str, PoolCapacity]:
    """Best-effort live capacity for each pool.  ``None`` means unknown."""
    meminfo = _meminfo()
    host_available = meminfo.get("MemAvailable")
    return {
        "gpu_vram": PoolCapacity("gpu_vram", _gpu_free(), "nvidia-smi"),
        "host_ram": PoolCapacity("host_ram", host_available, "/proc/meminfo:MemAvailable"),
        "swap": PoolCapacity("swap", _swap_free(), "/proc/swaps:SwapFree"),
        "nvme_kv": PoolCapacity("nvme_kv", _disk_free(Path(kv_root)), "statvfs"),
        "memfd": PoolCapacity(
            "memfd",
            memfd_cap_bytes if memfd_cap_bytes is not None else host_available,
            "declared_memfd_cap" if memfd_cap_bytes is not None else "derived_from_MemAvailable",
        ),
    }


# -- leases ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Lease:
    lease_id: str
    owner: str
    pool: str
    bytes: int
    created_at: float
    expires_at: float | None
    pinned: bool
    privacy_domain: str
    reclaim_receipt_digest: str = ""

    def active(self, now: float) -> bool:
        return self.expires_at is None or self.expires_at > now

    def as_dict(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "owner": self.owner,
            "pool": self.pool,
            "bytes": int(self.bytes),
            "created_at": float(self.created_at),
            "expires_at": self.expires_at,
            "pinned": bool(self.pinned),
            "privacy_domain": self.privacy_domain,
            "reclaim_receipt_digest": self.reclaim_receipt_digest,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Lease":
        return cls(
            lease_id=str(value["lease_id"]),
            owner=str(value["owner"]),
            pool=str(value["pool"]),
            bytes=int(value["bytes"]),
            created_at=float(value["created_at"]),
            expires_at=None if value.get("expires_at") is None else float(value["expires_at"]),
            pinned=bool(value.get("pinned", False)),
            privacy_domain=str(value.get("privacy_domain", "")),
            reclaim_receipt_digest=str(value.get("reclaim_receipt_digest", "")),
        )


@dataclass(frozen=True, slots=True)
class AdmissionReceipt:
    ok: bool
    lease_id: str
    owner: str
    pool: str
    requested_bytes: int
    capacity_bytes: int | None
    available_before_bytes: int | None
    shortfall_bytes: int
    denied_reason: str = ""
    reclaim_receipt_digest: str = ""
    authority: str = LEDGER_AUTHORITY

    def as_dict(self) -> dict[str, Any]:
        return {
            "beast_object_type": "physical_admission_receipt",
            "version": "1.0",
            "ok": bool(self.ok),
            "lease_id": self.lease_id,
            "owner": self.owner,
            "pool": self.pool,
            "requested_bytes": int(self.requested_bytes),
            "capacity_bytes": self.capacity_bytes,
            "available_before_bytes": self.available_before_bytes,
            "shortfall_bytes": int(self.shortfall_bytes),
            "denied_reason": self.denied_reason,
            "reclaim_receipt_digest": self.reclaim_receipt_digest,
            "authority": self.authority,
        }


@dataclass(frozen=True, slots=True)
class ReleaseReceipt:
    ok: bool
    lease_id: str
    pool: str
    released_bytes: int
    reason: str
    authority: str = LEDGER_AUTHORITY

    def as_dict(self) -> dict[str, Any]:
        return {
            "beast_object_type": "physical_release_receipt",
            "version": "1.0",
            "ok": bool(self.ok),
            "lease_id": self.lease_id,
            "pool": self.pool,
            "released_bytes": int(self.released_bytes),
            "reason": self.reason,
            "authority": self.authority,
        }


class PhysicalLedgerError(Exception):
    def __init__(self, code: str, message: str, *, shortfall_bytes: int = 0):
        super().__init__(message)
        self.code = code
        self.shortfall_bytes = int(shortfall_bytes)


class PhysicalLedger:
    """Byte-budget admission across every physical tier."""

    def __init__(
        self,
        capacities: Mapping[str, int | None],
        *,
        journal_path: Path | str | None = None,
        clock: Callable[[], float] = time.time,
        lease_id_factory: Callable[[], str] | None = None,
    ):
        unknown = set(capacities) - set(POOL_NAMES)
        if unknown:
            raise ValueError(f"unknown physical pools: {sorted(unknown)}")
        self._capacities: dict[str, int | None] = {}
        for pool in POOL_NAMES:
            value = capacities.get(pool)
            if value is not None:
                value = int(value)
                if value < 0 or value > (1 << 63):
                    raise ValueError(f"capacity for {pool} out of range")
            self._capacities[pool] = value
        self._clock = clock
        self._leases: dict[str, Lease] = {}
        self._journal_path = Path(journal_path) if journal_path is not None else None
        self._lease_id_factory = lease_id_factory or (lambda: "lease_" + os.urandom(12).hex())
        if self._journal_path is not None:
            self._journal_path.parent.mkdir(parents=True, exist_ok=True)
            self._replay()

    # -- journal ----------------------------------------------------------
    def _append(self, record: Mapping[str, Any]) -> None:
        if self._journal_path is None:
            return
        line = json.dumps(dict(record), sort_keys=True, separators=(",", ":")) + "\n"
        with self._journal_path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())

    def _replay(self) -> None:
        if self._journal_path is None or not self._journal_path.is_file():
            return
        for line in self._journal_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            kind = record.get("kind")
            if kind == "admit":
                try:
                    lease = Lease.from_dict(record["lease"])
                except (KeyError, TypeError, ValueError):
                    continue
                self._leases[lease.lease_id] = lease
            elif kind == "release":
                self._leases.pop(str(record.get("lease_id", "")), None)

    # -- accounting -------------------------------------------------------
    def committed_bytes(self, pool: str) -> int:
        now = self._clock()
        return sum(
            lease.bytes
            for lease in self._leases.values()
            if lease.pool == pool and self._is_committed(lease, now)
        )

    @staticmethod
    def _is_committed(lease: Lease, now: float) -> bool:
        # A pinned lease is deliberately exempt from expiry; counting it as
        # inactive would let the ledger hand the same bytes out twice.
        return lease.pinned or lease.active(now)

    def available_bytes(self, pool: str) -> int | None:
        capacity = self._capacities.get(pool)
        if capacity is None:
            return None
        return max(0, capacity - self.committed_bytes(pool))

    def _validate(self, owner: str, pool: str, size: int, privacy_domain: str) -> None:
        if pool not in POOL_NAMES:
            raise ValueError(f"unknown physical pool: {pool}")
        if not owner or not owner.strip():
            raise ValueError("lease owner cannot be empty")
        if not privacy_domain or not privacy_domain.strip():
            raise ValueError("privacy_domain cannot be empty")
        if not isinstance(size, int) or size <= 0 or size > MAX_LEASE_BYTES:
            raise ValueError("lease size must be a positive integer within the 1 TiB bound")

    def admit(
        self,
        owner: str,
        pool: str,
        bytes: int,
        *,
        ttl_seconds: float | None = 86400.0,
        pinned: bool = False,
        privacy_domain: str,
        reclaim_receipt_digest: str = "",
    ) -> AdmissionReceipt:
        """Reserve ``bytes`` in ``pool`` or deny.  Never partially admits."""
        size = int(bytes)
        self._validate(owner, pool, size, privacy_domain)
        if ttl_seconds is not None and ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive when supplied")
        if ttl_seconds is None and not pinned:
            # An unbounded, unpinned lease would keep bytes committed forever
            # after a restart.  Make that an explicit operator decision.
            raise ValueError("an unbounded lease must be pinned or carry a ttl")
        capacity = self._capacities.get(pool)
        available = self.available_bytes(pool)
        if capacity is None or available is None:
            return AdmissionReceipt(
                ok=False,
                lease_id="",
                owner=owner,
                pool=pool,
                requested_bytes=size,
                capacity_bytes=None,
                available_before_bytes=None,
                shortfall_bytes=size,
                denied_reason="capacity_unknown",
                reclaim_receipt_digest=reclaim_receipt_digest,
            )
        if size > available:
            return AdmissionReceipt(
                ok=False,
                lease_id="",
                owner=owner,
                pool=pool,
                requested_bytes=size,
                capacity_bytes=capacity,
                available_before_bytes=available,
                shortfall_bytes=size - available,
                denied_reason="insufficient_capacity",
                reclaim_receipt_digest=reclaim_receipt_digest,
            )
        now = self._clock()
        lease = Lease(
            lease_id=self._lease_id_factory(),
            owner=owner,
            pool=pool,
            bytes=size,
            created_at=now,
            expires_at=None if ttl_seconds is None else now + float(ttl_seconds),
            pinned=bool(pinned),
            privacy_domain=privacy_domain,
            reclaim_receipt_digest=reclaim_receipt_digest,
        )
        self._leases[lease.lease_id] = lease
        self._append({"kind": "admit", "lease": lease.as_dict()})
        return AdmissionReceipt(
            ok=True,
            lease_id=lease.lease_id,
            owner=owner,
            pool=pool,
            requested_bytes=size,
            capacity_bytes=capacity,
            available_before_bytes=available,
            shortfall_bytes=0,
            reclaim_receipt_digest=reclaim_receipt_digest,
        )

    def release(self, lease_id: str, *, reason: str = "") -> ReleaseReceipt:
        lease = self._leases.pop(lease_id, None)
        if lease is None:
            return ReleaseReceipt(ok=False, lease_id=lease_id, pool="", released_bytes=0, reason="not_resident")
        self._append({"kind": "release", "lease_id": lease_id, "reason": reason})
        return ReleaseReceipt(ok=True, lease_id=lease_id, pool=lease.pool, released_bytes=lease.bytes, reason=reason)

    def sweep(self, *, now: float | None = None) -> list[ReleaseReceipt]:
        """Release expired, unpinned leases.  Pinned leases never expire."""
        moment = self._clock() if now is None else float(now)
        released: list[ReleaseReceipt] = []
        for lease in list(self._leases.values()):
            if lease.pinned:
                continue
            if lease.expires_at is not None and lease.expires_at <= moment:
                released.append(self.release(lease.lease_id, reason="expired"))
        return released

    def resize(self, pool: str, capacity_bytes: int | None, *, source: str = "reprobe") -> dict[str, Any]:
        """Update a pool capacity from a fresh probe, keeping committed bytes."""
        if pool not in POOL_NAMES:
            raise ValueError(f"unknown physical pool: {pool}")
        if capacity_bytes is not None and int(capacity_bytes) < 0:
            raise ValueError("capacity cannot be negative")
        previous = self._capacities.get(pool)
        self._capacities[pool] = None if capacity_bytes is None else int(capacity_bytes)
        return {
            "pool": pool,
            "previous_capacity_bytes": previous,
            "capacity_bytes": self._capacities[pool],
            "committed_bytes": self.committed_bytes(pool),
            "source": source,
        }

    def leases(self) -> tuple[Lease, ...]:
        return tuple(sorted(self._leases.values(), key=lambda item: item.created_at))

    def state(self) -> dict[str, Any]:
        now = self._clock()
        pools = {}
        for pool in POOL_NAMES:
            capacity = self._capacities.get(pool)
            committed = self.committed_bytes(pool)
            pools[pool] = {
                "capacity_bytes": capacity,
                "committed_bytes": committed,
                "available_bytes": None if capacity is None else max(0, capacity - committed),
                "utilization": None if not capacity else round(committed / capacity, 6),
                "capacity_known": capacity is not None,
            }
        return {
            "beast_object_type": "physical_ledger_state",
            "version": "1.0",
            "pools": pools,
            "lease_count": len(self._leases),
            "active_lease_count": sum(1 for lease in self._leases.values() if self._is_committed(lease, now)),
            # Bounded projection for the API/UI; never the whole journal.
            "leases": [
                {**lease.as_dict(), "active": self._is_committed(lease, now)}
                for lease in self.leases()[-200:]
            ],
            "authority": LEDGER_AUTHORITY,
            "journal": str(self._journal_path) if self._journal_path else None,
        }

    def digest(self) -> str:
        return _digest(self.state())


__all__ = [
    "LEDGER_AUTHORITY",
    "AdmissionReceipt",
    "Lease",
    "PhysicalLedger",
    "PhysicalLedgerError",
    "PoolCapacity",
    "ReleaseReceipt",
    "probe_pools",
]
