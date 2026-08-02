# Phase 3.3 Deterministic Fingerprint Engine

Every crystallized evidence object receives an immutable, content-addressed fingerprint bundle. The bundle separates task identity from environment identity and preserves explainable component manifests for Git state, dependencies, runtime, policy profile, affected paths, operations, and source symbols.

Fingerprints support candidate identity and drift explanation only. They do not authorize reuse. Phase 2 worktree, verification, repair, promotion, and human approval remain mandatory.

Comparison classifications are `identical`, `environment_drift`, `same_task_changed_context`, and `different_task`. Each comparison includes boolean component checks, changed component names, and a deterministic receipt digest.
