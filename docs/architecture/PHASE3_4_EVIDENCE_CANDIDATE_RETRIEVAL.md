# Phase 3.4 Evidence Candidate Retrieval

Phase 3.4 introduces deterministic, explainable candidate retrieval over immutable evidence crystals.

## Authority boundary

Retrieval is discovery, not compatibility and not reuse authority. Every receipt returns `reuse_authorized: false`; candidates must pass the future compatibility engine and the full Phase 2 worktree, verification, promotion workflow.

## Pipeline

1. Load immutable crystals and their fingerprint bundles.
2. Project append-only ledger state.
3. Exclude revoked and expired evidence; exclude superseded evidence unless explicitly requested.
4. Apply hard filters for language, framework and policy profile.
5. Rank survivors using explicit weighted components: objective, symbols, affected paths, error terms, operation kinds, mode, language and framework.
6. Return a digest-bound retrieval receipt with component scores and rejection counts.

No embedding or opaque learned score is used in this phase.
