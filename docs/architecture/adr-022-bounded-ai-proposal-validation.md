# ADR-022: Bounded AI proposal validation

## Status

Accepted

## Context

Pair Programmer compiled provider Action IR into exact, workspace-scoped
SourcePlan operations. Exact-anchor compilation proved that an edit could be
applied, but it did not prove that the resulting file still parsed. Presenting
a syntactically broken proposal as "ready" wastes review time and falls short
of a daily-driver coding agent. Action IR can also contain verifier requests,
but executing model-authored commands would cross the IDE's process and trust
boundary.

## Options considered

| Option | Benefits | Costs |
|---|---|---|
| Validate only during final SourcePlan apply | Smallest implementation | Broken proposals reach review; slow feedback |
| Execute model-supplied verifier commands immediately | Broad test coverage | Arbitrary process authority; unclear trust and side effects |
| Validate projected files in memory, then perform one bounded repair | Fast feedback, no workspace mutation, deterministic evidence | Syntax coverage varies by language; full tests remain a later worktree step |
| Run allowlisted verifiers in a temporary projected workspace | Real command evidence without writing the operator workspace | Requires a strict command allowlist and bounded test targets |

## Decision

BEAST validates the projected contents of AI-authored SourcePlans before they
are emitted to the desktop client.

- Operations are replayed against an in-memory snapshot; the working tree is
  never written during proposal validation.
- All projected files reject NUL bytes and unresolved conflict markers.
- Python uses `ast.parse`, JSON uses `json.loads`, and JavaScript uses a bounded
  argument-array `node --check` against a temporary file.
- BEAST creates a temporary verifier workspace for projected files and runs
  allowlisted commands such as `python -m py_compile`, `node --check`, and
  explicit-file `pytest` targets with short timeouts.
- Unsupported, broad, or unsafe verifier commands are retained as skipped
  evidence; they are not executed.
- Unsupported language files receive content-safety checks and an honest
  `partial` status rather than a false syntax-pass claim.
- A failed projection may trigger one diagnostic repair turn. The repair prompt
  is restricted to the original allowed files, prior Action IR, and bounded
  validation messages.
- The repaired Action IR is recompiled and revalidated. A plan is emitted only
  when validation has no failures.
- Validation status and checks travel with the SourcePlan and appear in Pair
  Programmer and the SourcePlan lifecycle panel.

## Trade-offs

- Syntax validation and bounded verifiers are not a substitute for full runtime
  verification.
- JavaScript checking depends on an available Node runtime; TypeScript and
  other languages currently receive content-safety checks until their bounded
  compiler integrations are selected.
- One extra provider turn may be consumed when the initial proposal is invalid.

## Consequences

- Syntactically broken supported-language edits no longer appear as ready.
- The agent gains a real observe → repair → revalidate loop without arbitrary
  shell access.
- Proposal evidence is visible before governed verification and apply, including
  isolated verifier pass/fail/skipped summaries.
- Full dependency-aware test execution remains isolated-worktree work and must
  preserve explicit task selection, trust, timeout, and evidence contracts.
