# Step 7 — Final gauntlet through the governed path (closure 2026-11-16, 11:54–12:10 SAST)

Script: `scripts/closure_final_gauntlet.py`. Every task ran on temp-workspace copies. The verifier gated on hidden tests.
Governor receipt chains are valid (chain run 76 receipts, full run 37).
Registry: `.beast/gauntlets/2026-11-16-closure` (gauntlet registry; nothing promoted in this step).
GPU: TGI Qwen2.5-Coder-3B-AWQ held the GPU, with the scheduler on (GPU-Ollama dropped).

Task sets:
- **morning13**: this morning's exact 13 tasks (routed 10 + h2h 3). The hard 5 are a subset.
- **fresh**: 6 unseen seeded harder tasks (seed 20261118): diff, dual, refguard, refop, rename, single.

Runs:
- **chain**: governed chain only (TGI → Fireworks GLM-5p3-flash → Fireworks DeepSeek-v4p1-flash → HF Kimi-K2.7-Code), rename tool, verifier feedback, no crystals.
- **full**: the whole governed path (family crystals → lattice capsules → the same chain; scorecard + receipts).

## Headline (comparable with this morning)
| metric | this morning | **chain (no crystals)** | **full governed path** |
|---|---|---|---|
| routed 10 | 7/10 | **9/10** | **9/10** |
| hardest 5 (ren-h1..h3, refguard-h1/h2) | 1/5 | **5/5** | **5/5** |
| 13-task set (TGI-chain comparator) | 11/13 | **12/13** | **12/13** |
| fresh harder (unseen, seed 20261118) | n/a | **6/6** | **5/6** |
| all 19 | n/a | **18/19** | **17/19** |
| false accepts | — | 0 | 0 |
| model calls | 40 (TGI chain) | 38 | **10** |

**Headline number: 12/13 on this morning's 13-task set through the governed chain (vs 11/13), with hard-5 at 5/5 (vs 1/5).**
Run as the full governed path, the score is the same, with 10 model calls instead of 38: crystals and lattices answered 16 of 19 tasks with 0 calls.

## Honesty notes
- **Contamination:** ren-h1..h3 and refguard-h1..h3 were the held-out tasks used to promote the rename crystal and the refguard lattice in step 1.
  Their crystal or lattice hits in the full run are replays on tasks the crystal has already seen. So the **chain** column is the fair
  model-path comparison, and the **fresh** row is the fair generalization number.
- **Head-to-head (7/21) was not rerun.** It scored 7 single models × 3 tasks with no chain or feedback, so it isn't comparable with a chain
  score. The closest analogue is TGI alone with the tool: 5/13 in step 1, vs TGI alone 2/13 this morning.
- **Failures** (all were verifier rejections, none were transport errors):
  - chain/exc-h1: TGI tests_still_failing, then GLM, DeepSeek and Kimi all hit **`edit old_text is not unique in target`**.
  - full/far-1: TGI and GLM tests_still_failing, then DeepSeek and Kimi hit `old_text not unique`.
    The chain run solved far-1 (DeepSeek), so this is stochastic.
  - full/fresh-diff-6852: GLM `old_text not unique`; the others tests_still_failing. The chain run solved it (DeepSeek).
  - **The dominant remaining failure mode is ambiguous exact-replace anchors** (6 of the 12 failed calls here, and fresh-refguard-6bb5 in step 1).
    Next fix: a line-anchored or context-expanded edit actuator, or reject-with-candidates feedback. Not done in this job.
- "provider:nemotron" in the gauntlet `route`/`by` fields is only the ClosureGauntlet slot name. The real model is in each episode's
  `calls` (fresh-refop-6852 went to Fireworks GLM). No NIM was called here.
- Lanes exercised: TGI (local GPU), Fireworks GLM + DeepSeek (cloud), HF router Kimi via deepinfra (cloud); crystals, lattice capsules,
  scorecard (`.beast/gauntlets/2026-11-16-closure/capability_scorecard.json`), governor receipts.

## Spend
This step: **$0.010089** (48 calls). Job total: **$0.015835** (step 1 $0.005746 + step 7 $0.010089; steps 2–6 $0). Cap $0.30.

Files: `final-20261116T115424.json` (all rows, calls, episodes), `final-summary-20261116T115424.json`, `governor-receipts-{chain,full}-*.jsonl`, `final.log`.
