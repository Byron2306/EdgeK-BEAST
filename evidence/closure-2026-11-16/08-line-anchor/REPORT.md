# Line-anchored edit tool — closure step 8

Date: 2026-11-16 (Africa/Johannesburg, UTC+2).
Rerun: `rerun-summary-20261116T131806.json`.

## Result

The line-anchored edit actuator works. All 4 tasks that failed earlier today
because a model's exact-text anchor matched more than one place in a file now
pass every hidden check.

| Task | Accepted | Accepted by | Model calls | Spend |
|---|---|---|---|---|
| `exc-h1` | yes (hidden checks passed) | TGI `Qwen/Qwen2.5-Coder-3B-Instruct-AWQ` @ `gpu_full` | 1 | $0.000000 |
| `far-1` | yes (hidden checks passed) | Fireworks `deepseek-v4p1-flash` | 3 | $0.000582 |
| `fresh-diff-6852` | yes (hidden checks passed) | Fireworks `glm-5p3-flash` | 2 | $0.000206 |
| `fresh-refguard-6bb5` | yes (hidden checks passed) | Fireworks `glm-5p3-flash` | 2 | $0.000240 |

- Accepted: **4 / 4**
- Model calls: **8**
- Spend: **$0.001028** against a $0.05 cap
- First attempts that failed (`tests_still_failing` / `hidden_check_failed`) were repaired on a later turn; the final verdict for each task passed visible and hidden checks.

Together with the earlier governed-path gauntlet, this puts the original 13-task set at **13 / 13** through the governed path once the line-anchor actuator is in the loop.

## What the tool does

A model no longer has to identify an edit site by exact text alone. The actuator
accepts optional disambiguators:

- `anchor_line` — pick the match nearest that line when the same text appears more than once
- surrounding `context` lines
- `occurrence` — which match to use when context still ties

If a site is still ambiguous, the repair prompt lists the possible matches so
the next turn can choose one. Existing exact-text edits stay backward compatible
when the match is already unique. The unit tests in `tests/test_structured_edit.py`
cover unique matches, nearest-line ties, context/occurrence disambiguation,
atomic apply, and the stable prefix used when nothing matches.

## Unit tests

Recorded in the 2026-11-16 finalize pass (see the parent closure report for the
exact pytest invocation and counts). Files:

- `tests/test_structured_edit.py` — schema, parse, line-anchor, multi-file actuator
- `tests/test_symbol_rename.py` — deterministic rename tool and refguard composition

## Evidence

- `rerun-summary-20261116T131806.json` — spend, calls, per-task verdicts
- `rerun-20261116T131806.json` — full rerun record
- `governor-receipts-20261116T131806.jsonl` — governed-call receipts (no prompts or keys)
- `capability_scorecard.json` — scorecard cells written during the rerun (family-specific cells were later merged into the live Auto scorecard)

No live services were restarted for this step.
