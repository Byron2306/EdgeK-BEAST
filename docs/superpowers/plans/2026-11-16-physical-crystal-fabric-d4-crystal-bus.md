# Delivery 4: Consolidated Crystal Bus — Plan

Spec: `docs/superpowers/specs/2026-11-15-physical-crystal-fabric-spine-design.md` (delivery 4).
Roadmap: `docs/superpowers/plans/2026-11-15-physical-crystal-fabric-roadmap.md` (Delivery 4).

## Goal

One Crystal Bus API over `AF_UNIX/SOCK_SEQPACKET` + `SCM_RIGHTS` that unifies the two existing
implementations (`app/kernel/compute/crystal_bus.py` message transport and `app/kernel/crystal_bus/`
capsule-offer endpoint) behind: peer credentials, sequence ledger, capsule verify, one-use authority —
and emits a signed, hash-chained custody receipt on every descriptor transfer.

## Constraints

- Default-off: `BEAST_CONSOLIDATED_CRYSTAL_BUS=1` enables `crystal_bus_from_environment()`; unset → `None`
  and every existing caller (grand_closure g4/g5/g6, generation_synthesis_plane, Socket Guardian) is unchanged.
- No behaviour change to the existing modules; both legacy suites stay green.
- Never weaker than either legacy path: strict SO_PEERCRED (no sandbox fallback), exactly one descriptor,
  size + content digest + seals verified, expiry enforced, capability lease consumed once (optionally durable).
- Capsules never grant authority; the lease digest is the authority and is single-use.
- Custody receipts carry digests only (no capsule bytes, no keys).

## Tasks

1. RED tests `tests/test_consolidated_crystal_bus.py`: flag default-off; round-trip with receipts on both
   ends; chain verification + tamper detection; refusals (uid mismatch, stale lease, replayed lease,
   expired offer, size mismatch, digest mismatch, unsealed when seals required, sequence replay,
   oversize frame); durable one-use authority across instances; legacy API re-exported.
2. GREEN `app/kernel/crystal_bus/bus.py`: `ConsolidatedCrystalBus`, `OneUseAuthority`, `CustodyChain`,
   `verify_custody_chain`, `strict_peer_credentials`, `content_digest`, `crystal_bus_from_environment`.
   Re-export from `app/kernel/crystal_bus/__init__.py` alongside the compute-bus API.
3. Regression: `tests/test_crystal_bus_capsule.py`, grand-closure/generation users, Guardian suites.

## Exit

One module path (`app.kernel.crystal_bus`) exposes both APIs; both legacy suites green; custody receipts
on every consolidated descriptor transfer; flag off by default. Migrating g4/g5/g6 callers onto the
consolidated bus is a follow-up behind the same flag (operator decision).
