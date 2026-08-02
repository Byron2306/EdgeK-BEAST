# Phase 3.2: Append-only Evidence Ledger

Phase 3.2 adds a lifecycle ledger beside immutable Phase 3.1 evidence crystals. Evidence object bytes remain content-addressed and unchanged. Usage, metrics, verification, supersession, expiry, and revocation are represented as separate sequence-bound, hash-chained facts.

## Invariants

1. Evidence crystals are never updated in place.
2. Each ledger event binds its evidence ID, sequence, actor, payload, timestamp, and previous event hash.
3. Revoked or expired evidence cannot be adopted by a future run.
4. Supersession links only to an existing evidence crystal.
5. Ledger verification is independent of object verification.
6. Metrics rank and measure evidence; they do not authorize reuse.

## Routes

- `GET /edgek/evidence/{evidence_id}/ledger`
- `GET /edgek/evidence/{evidence_id}/ledger/verify`
- `POST /edgek/evidence/{evidence_id}/usage`
- `POST /edgek/evidence/{evidence_id}/revoke`
- `POST /edgek/evidence/{evidence_id}/supersede`
- `POST /edgek/evidence/{evidence_id}/metrics`

## State projection

The ledger projects `active`, `superseded`, `revoked`, or `expired` without changing the underlying evidence crystal. Usage count, latest metrics, successor identity, reason, event count, and ledger head are computed from append-only facts.
