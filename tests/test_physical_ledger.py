"""Acceptance tests for the unified physical byte ledger.

The census complaint was that VRAM, RAM, swap, NVMe and memfd were accounted
separately, so a placement could "fit" everywhere and still overflow the host.
These tests pin the single-budget behaviour:

1. a pool whose capacity is unknown denies rather than assumes;
2. admission is all-or-nothing and reports the shortfall;
3. releases return exactly the reserved bytes;
4. expiry sweeps free only unpinned leases;
5. a restart replays the journal, so committed bytes survive;
6. capacities can be refreshed without losing live reservations;
7. receipts validate against the canon registry.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.kernel.compute.physical_ledger import (
    PhysicalLedger,
    probe_pools,
)


def ledger(tmp_path: Path | None = None, **caps) -> PhysicalLedger:
    values = {"gpu_vram": 6 * 1024**3, "host_ram": 16 * 1024**3}
    values.update(caps)
    journal = (tmp_path / "journal.jsonl") if tmp_path is not None else None
    return PhysicalLedger(values, journal_path=journal)


def test_unknown_capacity_denies() -> None:
    book = ledger(swap=None)
    receipt = book.admit("kv", "swap", 1024, privacy_domain="test")
    assert receipt.ok is False
    assert receipt.denied_reason == "capacity_unknown"
    assert receipt.shortfall_bytes == 1024
    assert book.committed_bytes("swap") == 0


def test_admission_is_all_or_nothing_with_shortfall() -> None:
    book = ledger(gpu_vram=1000)
    assert book.admit("a", "gpu_vram", 600, privacy_domain="test").ok is True
    denied = book.admit("b", "gpu_vram", 600, privacy_domain="test")
    assert denied.ok is False
    assert denied.denied_reason == "insufficient_capacity"
    assert denied.shortfall_bytes == 200
    assert book.committed_bytes("gpu_vram") == 600, "a denied lease must not be partially committed"


def test_release_returns_exact_bytes() -> None:
    book = ledger(gpu_vram=1000)
    lease = book.admit("a", "gpu_vram", 400, privacy_domain="test")
    release = book.release(lease.lease_id)
    assert release.ok is True
    assert release.released_bytes == 400
    assert book.committed_bytes("gpu_vram") == 0
    assert book.release(lease.lease_id).ok is False


def test_sweep_releases_expired_unpinned_only() -> None:
    clock = {"now": 1000.0}
    book = PhysicalLedger(
        {"host_ram": 10_000},
        clock=lambda: clock["now"],
    )
    short = book.admit("a", "host_ram", 1000, ttl_seconds=10, privacy_domain="test")
    pinned = book.admit("b", "host_ram", 2000, ttl_seconds=10, pinned=True, privacy_domain="test")
    clock["now"] = 2000.0
    released = book.sweep()
    assert [item.lease_id for item in released] == [short.lease_id]
    assert book.committed_bytes("host_ram") == 2000
    assert pinned.lease_id in {lease.lease_id for lease in book.leases()}


def test_restart_replays_journal(tmp_path: Path) -> None:
    book = ledger(tmp_path, host_ram=10_000)
    first = book.admit("crystal", "host_ram", 4096, privacy_domain="test")
    assert first.ok is True

    reopened = ledger(tmp_path, host_ram=10_000)
    assert reopened.committed_bytes("host_ram") == 4096
    assert first.lease_id in {lease.lease_id for lease in reopened.leases()}

    reopened.release(first.lease_id, reason="done")
    again = ledger(tmp_path, host_ram=10_000)
    assert again.committed_bytes("host_ram") == 0


def test_resize_preserves_committed_bytes() -> None:
    book = ledger(gpu_vram=1000)
    book.admit("a", "gpu_vram", 400, privacy_domain="test")
    change = book.resize("gpu_vram", 2000)
    assert change["previous_capacity_bytes"] == 1000
    assert change["capacity_bytes"] == 2000
    assert book.committed_bytes("gpu_vram") == 400
    assert book.available_bytes("gpu_vram") == 1600


def test_shrink_below_commit_reports_zero_available_not_negative() -> None:
    book = ledger(gpu_vram=1000)
    book.admit("a", "gpu_vram", 800, privacy_domain="test")
    book.resize("gpu_vram", 500)
    assert book.available_bytes("gpu_vram") == 0
    assert book.state()["pools"]["gpu_vram"]["utilization"] == pytest.approx(1.6)


def test_reclaim_digest_is_carried_on_the_lease() -> None:
    book = ledger(host_ram=10_000)
    digest = "sha256:" + "d" * 64
    receipt = book.admit("after-reclaim", "host_ram", 1024, privacy_domain="test", reclaim_receipt_digest=digest)
    assert receipt.reclaim_receipt_digest == digest
    assert book.leases()[0].reclaim_receipt_digest == digest


def test_bounds_and_validation() -> None:
    book = ledger()
    with pytest.raises(ValueError):
        book.admit("a", "gpu_vram", 0, privacy_domain="test")
    with pytest.raises(ValueError):
        book.admit("a", "gpu_vram", (1 << 40) + 1, privacy_domain="test")
    with pytest.raises(ValueError):
        book.admit("", "gpu_vram", 1, privacy_domain="test")
    with pytest.raises(ValueError):
        book.admit("a", "gpu_vram", 1, privacy_domain="")
    with pytest.raises(ValueError):
        book.admit("a", "not_a_pool", 1, privacy_domain="test")


def test_receipts_validate_against_canon() -> None:
    from app.kernel.registry.canon_registry import CanonRegistry

    book = ledger(host_ram=10_000)
    admission = book.admit("a", "host_ram", 100, privacy_domain="test").as_dict()
    release = book.release(book.leases()[0].lease_id).as_dict()
    state = book.state()
    canon = CanonRegistry()
    for obj in (admission, release, state):
        report = canon.validate_object(obj)
        assert report["valid"] is True, report["errors"]


def test_probe_pools_reports_real_host_sources() -> None:
    pools = probe_pools(kv_root=Path("/"))
    assert set(pools) == {"gpu_vram", "host_ram", "swap", "nvme_kv", "memfd"}
    assert pools["host_ram"].capacity_bytes and pools["host_ram"].capacity_bytes > 0
    assert pools["nvme_kv"].capacity_bytes and pools["nvme_kv"].capacity_bytes > 0
    assert pools["host_ram"].source == "/proc/meminfo:MemAvailable"
    assert pools["nvme_kv"].source == "statvfs"


def test_unbounded_unpinned_lease_is_refused() -> None:
    book = ledger()
    with pytest.raises(ValueError, match="pinned or carry a ttl"):
        book.admit("a", "gpu_vram", 1024, ttl_seconds=None, privacy_domain="test")
    # Pinning makes the unbounded intent explicit and is allowed.
    pinned = book.admit("a", "gpu_vram", 1024, ttl_seconds=None, pinned=True, privacy_domain="test")
    assert pinned.ok is True
