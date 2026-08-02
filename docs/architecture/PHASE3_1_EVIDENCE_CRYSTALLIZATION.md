# Phase 3.1: Evidence Crystallization Foundation

Phase 3.1 converts a governed Phase 2 commit candidate into an immutable, content-addressed evidence crystal.

## Invariants

- Only promoted commit candidates may crystallize.
- One AgentRun maps to at most one immutable crystal.
- Canonical JSON and SHA-256 bind the crystal and each supporting artifact.
- Artifact writes are create-once and collision checked.
- The captured AgentRun event chain is independently replay-verifiable.
- Reuse is marked `adapt_and_reverify`; no Phase 2 governance bypass exists.
- Crystallization is idempotent and emits `agent.evidence.crystallized` only after durable storage.

## Storage

SQLite WAL indexes objects under `.beast/evidence/evidence.sqlite3`. Canonical JSON payloads live under a content-addressed `.beast/evidence/objects/<digest>` tree.
