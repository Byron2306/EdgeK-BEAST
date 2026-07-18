# ADR-020: Mediated source-control workbench

## Status

Accepted

## Context

BEAST could enumerate Git changes and run stage, unstage, and discard for the
active file, but that did not form a daily-driver source-control journey. A
developer still had to leave the workbench to compare the index and worktree,
write a commit, or change branches. Giving the renderer a shell would close
that UX gap at the cost of bypassing BEAST's workspace, evidence, and process
boundaries.

## Options considered

| Option | Benefits | Costs |
|---|---|---|
| Renderer-owned Git or shell | Fastest to expose arbitrary Git features | Broad process authority, weak path control, difficult evidence capture |
| Embed a third-party Git client | Mature feature breadth | Large dependency and styling surface; duplicates Monaco and BEAST governance |
| Main-process Git operations with structured IPC | Reuses the existing workbench, keeps argv/process authority bounded, supports receipts | Each supported operation needs an explicit contract |

## Decision

BEAST uses explicit main-process Git operations and a structured preload
contract for status, file diff, staging, commit, and branch switch/create.

- Every file operation resolves inside the active workspace.
- Git is spawned with argument arrays rather than renderer-provided shell text.
- Process duration and output are bounded.
- Text diff sides are limited to 1 MB and binary files are rejected from the
  Monaco text-diff path.
- Commit messages and branch names are bounded; branch names also pass
  `git check-ref-format --branch`.
- Mutating operations return SHA-256 evidence receipts for the BEAST ledger.
- The renderer receives structured status and bounded file content, never a
  process handle or repository-wide shell capability.

The Source Control panel groups index and worktree changes, opens the correct
comparison in Monaco, offers per-file and all-file staging, commits with an
adjacent message/error surface, and changes branches through the mediated
contract. Editor breadcrumbs and the status bar preserve orientation while a
diff temporarily occupies the editor stage.

## Trade-offs

- Advanced workflows such as interactive rebase, merge conflict editing,
  remotes, and graph history remain explicit future contracts rather than
  falling through to an unrestricted shell.
- File-level staging is provided first; hunk-level staging needs a bounded
  patch-application contract.
- Large and binary files require an alternate preview rather than the Monaco
  text-diff editor.

## Consequences

- Source control now supports a complete inspect → stage → commit → branch
  journey without leaving BEAST.
- The Git boundary is testable against a disposable real repository.
- Future Git capabilities must preserve the same workspace, argv, bounds, and
  receipt invariants.

