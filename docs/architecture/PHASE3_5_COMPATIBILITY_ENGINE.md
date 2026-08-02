# Phase 3.5 Compatibility Engine

Phase 3.5 converts a retrieved evidence candidate into a deterministic compatibility classification without granting reuse authority.

## Verdicts

- `EXACT`: task and environment fingerprints match.
- `ADAPTABLE`: task matches but current environment has drift.
- `REFERENCE`: task differs, but deterministic retrieval relevance exceeds policy threshold.
- `REJECTED`: hard policy/runtime/language gate failed or similarity is insufficient.
- `REVOKED`: ledger state is revoked or expired.

## Authority boundary

Every receipt is classification-only. `reuse_authorized` remains false. Exact and adaptable evidence still require fresh verification, Phase 2 governance and human promotion.

## Bound checks

Receipts bind ledger state, candidate/current fingerprint digests, policy profile, runtime system, architecture, dependencies, symbols, Git head, language overlap, retrieval score and retrieval receipt digest.
