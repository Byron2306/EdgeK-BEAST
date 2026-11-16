# Step 1 — Deterministic AST/scope-aware rename tool (closure 2026-11-16)

## What was built
- `app/kernel/compute/symbol_rename.py` (new; tool id `code.rename_symbol`). libcst FullRepoManager + FullyQualifiedNameProvider.
  The model only says WHAT to rename, as constrained JSON `{renames:[{symbol,file,new_name}], edits:[{path,old_text,new_text}]}`.
  The tool does the edit:
  - plans every reference (def/class/module assignment, FQN-resolved Names, absolute and relative from-imports with as-names kept,
    `module.attr` access, package re-exports iterated to a fixpoint, `__all__` strings);
  - writes atomically (os.replace), rejects a stale plan, re-scans for leftover references, rolls back on failure;
  - emits a unified diff.
  It refuses keywords, no-op names, and new names already bound at module level.
  It flags but never edits strings, comments, unresolved `obj.attr` and star imports.
  It never edits `test_*.py` (the excluded default). Renames run first; then each free-form edit is rebased onto the renamed text,
  and edits that are pure renames are dropped. The verifier (hidden tests) decides acceptance.
  CLI: `python -m app.kernel.compute.symbol_rename SYMBOL NEW [--file F] [--apply] [--json]` (dry run by default).
- `app/kernel/compute/governed_refactor.py` (new). Wires the tool into the governed path for the families
  `refactor-rename`, `composite-refguard`, `fresh-single2`, `fresh-lattice2` and `multi-file`, plus any failure saying "cannot import name"
  or "module has no attribute". It supplies the action schema, a system prompt with a few-shot, and the actuator.
- `app/kernel/compute/family_crystals.py`: the `resolve_rename` opcode now uses the AST planner instead of a `\bold\b` regex.
  The opcode name is unchanged, so the catalog digest is unchanged. Backup: `*.before-closure-20261116`.
- `scripts/closure_common.py`, `scripts/closure_rename_gauntlet.py` (new): governed chain TGI → Fireworks GLM-5p3-flash → Fireworks
  DeepSeek-v4p1-flash → HF Kimi; spend meter capped at $0.30. Run on temp-workspace copies only.
- `tests/test_symbol_rename.py` (new): **15/15 pass**.

## Results (seed 20261116, 13 rename/refguard/multi-file tasks, governed path, temp workspaces)
| run | accepted | model calls | spend |
|---|---|---|---|
| TGI Qwen2.5-Coder-3B-AWQ alone + tool | **5/13** | 13 | $0 |
| governed chain + tool | **12/13** | 24 | $0.004825 |

- **ren-h1, ren-h2, ren-h3: all pass** in the chain. ren-h1 and ren-h2 went to TGI ($0). ren-h3: TGI produced no JSON, then GLM solved it.
- **refguard-h1 and refguard-h2: pass**, and so do refguard-h3 and refguard-w1. All four went to GLM after TGI's guard edit failed the hidden tests.
- ren-w1, ren-w2, ren-near and fresh-rename pass. fresh-refop went to DeepSeek after GLM produced invalid JSON.
- **The 1 failure is fresh-refguard-6bb5**. All four chain members failed it:
  - TGI: tests_still_failing (wrong guard).
  - GLM: the tool refused it with `edit_not_applicable: edit old_text is not unique in target`. GLM's guard edit anchored on a line that
    appears twice in the generated file, so the exact-replace actuator correctly refused an ambiguous edit.
  - DeepSeek and Kimi: tests_still_failing. They received the earlier rejection as feedback and still produced a wrong guard.
  - Not fixed. Possible fix: give the actuator a "line-anchored edit with context" fallback, or put "old_text must be unique" in the prompt.
  - The rename half was never the problem: every candidate's rename applied cleanly.
- Per-task calls: `solve-20261116T104030.json`. Summary: `solve-summary-20261116T104030.json`. Governor receipts:
  `governor-receipts-solve-*.jsonl`. `solve-20261116T103836.json` is the first run, which I killed: it had renames-after-edits ordering, which was then fixed.

## Crystallization (gauntlet registry only: `.beast/gauntlets/2026-11-16-closure/family_crystals.sqlite3`, approve-by Byron)
- ren-cold (seed 20261117) was solved by TGI ($0). It distilled byte-identically to **family-crystal:a54695a14f648efdd70f6620**
  (resolve_rename recipe). Held-out ren-h1..h3 replayed **3/3 with 0 model calls**, so it was promoted (approved_by Byron).
- Lattice composite rename + fix-unhandled-exception → **family-crystal:b782ade90da59ee99e8877fd**. Held-out refguard-h1..h3 **3/3** → promoted.
  Authority A_L = workspace.read_range, worktree.bind, worktree.replace_exact, worktree.verify.
- **Reuse on fresh tasks (seed 4a92)**:
  - fresh-rename-4a92: crystal replay, 0 calls, 0.6 s.
  - fresh-refguard-4a92: lattice replay, 0 calls, 1.4 s.
  - fresh-refop-4a92 (negative control): the lattice correctly refused, and DeepSeek solved it in 3 calls ($0.000921).
  - 0 false accepts; governor chain valid.
- The first crystallize attempt failed (PermissionError: BEAST_CRYSTAL_CAPSULE unset). Its registry was kept as `*.run1-capsule-env-missing`.
- Crystals made: 2 (both promoted). Crystal reuses: 2 fresh tasks plus 6 held-out replays.

## Labelling notes
- **"provider:nemotron" in the gauntlet log is only a slot name.** ClosureGauntlet runs the whole governed chain in that slot.
  The models that actually ran are in each episode's `calls` (TGI / Fireworks GLM / Fireworks DeepSeek / HF Kimi). No NIM Nemotron was called in step 1.
- **far-1 is under-specified, not mislabelled.** The visible test is `slugify('Hello World')`; the hidden test needs `'A  B c' -> 'a-b-c'`
  (whitespace collapse). A naive `.replace(' ', '-')` passes visible and fails hidden; `'-'.join(s.split())` passes both.
  This morning's false accept came from visible-only acceptance. Fix: hidden-test gating (already the default on the governed path),
  or add a whitespace case to the visible spec.
- exc-cold's false accept this morning was genuine (the model's guard was wrong). A correct guard passes both visible and hidden tests.

## Test residue in live stores (found and fixed)
- Cause: `tests/conftest.py` initialises services at import, and default stores are built at import time:
  - `DurableInferenceStorage` → `app/data/durable_inference` (crystal_chain.jsonl);
  - `default_outcome_store` → `app/.beast/crystal_compute_evidence.json`.
- **Test residue in the live stores (NOT deleted):**
  - crystal_chain.jsonl entries at 09:42 SAST (jetson_unit) and 10:02 SAST (jetson_defender, fusion_node, commons_feeder, snapshot_feeder).
  - crystal_compute_evidence.json outcomes scoped to model gpt-3.5-turbo / provider openai with ~1.7 ms latency (synthetic).
- Likely also test-regenerated, with no override yet:
  - deploy/generated/litellm.config.yaml and nginx.edgek.conf (10:03 SAST);
  - .beast/local_trace_ledger, local_semantic_cache, local_route_optimizer (10:04–10:05 SAST).
- Fix:
  - new env overrides `BEAST_DURABLE_INFERENCE_DIR` (durable_inference_storage.py) and `BEAST_CRYSTAL_COMPUTE_EVIDENCE` (outcome_evidence.py);
  - conftest sets both to a `tempfile.mkdtemp("beast-test-state-")` dir before any app import.
  - Verified: running test_compute_forge, test_gateway, test_governor_execution_wiring and test_provider_registry leaves the live files'
    sha256 unchanged.
- Known gap: `.beast/capability_scorecard.json` (default path) received real outcomes from my 8199 test-gateway call in step 3.
  Those are real, not synthetic.

## Files changed
New: symbol_rename.py, governed_refactor.py, tests/test_symbol_rename.py, scripts/closure_common.py, scripts/closure_rename_gauntlet.py.
Modified (backed up `*.before-closure-20261116`): family_crystals.py, durable_inference_storage.py, outcome_evidence.py, tests/conftest.py.

## Spend
Solve run $0.004825 (24 calls) + crystallize $0.000921 (4 calls) = **$0.005746**.
