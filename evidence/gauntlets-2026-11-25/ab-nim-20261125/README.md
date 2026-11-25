# NIM crystal economics baseline — 2026-11-25

Head-to-head rerun of the 2026-11-25 lattice-gauntlet reuse tasks on the hosted NVIDIA NIM trial.
Arm A reuses already-admitted coding crystals. Arm B disables crystal lookup/reuse.
Prompts, verifier, model, temperature (0) and seed formula (`731947 + turn`) are identical.

## Headline

| item | result |
|---|---|
| Model | `nvidia/nemotron-3.5-super-vl-120b-a12b` (hosted NIM trial, `https://integrate.api.nvidia.com/v1`) |
| Tasks | 5 reuse packages from the prior gauntlets |
| Repeats | 3 per arm per task |
| Arm A pass rate | 15/15 (100.0%), crystal hits 15 |
| Arm B pass rate | 15/15 (100.0%), crystal hits 0 |
| Prompt tokens A / B | 0 / 238622 (saved 100.0%) |
| Completion tokens A / B | 0 / 8253 (saved 100.0%) |
| Model calls A / B | 0 / 166 (saved 100.0%) |
| Wall time A / B | 17.348s / 452.964s (saved 96.2%) |
| Billed | $0.00 (free NIM trial) |
| Commercial equivalent | $0.017206 (list prices, not a charge) |

## Per-task totals (all repeats)

| task | A calls | B calls | A prompt | B prompt | A wall s | B wall s | A pass | B pass | A crystal hits |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `default-open` | 0 | 39 | 0 | 55399 | 3.825 | 103.608 | 3/3 | 3/3 | 3 |
| `quota-limit` | 0 | 54 | 0 | 82874 | 3.444 | 151.572 | 3/3 | 3/3 | 3 |
| `status-label` | 0 | 27 | 0 | 37111 | 3.392 | 80.684 | 3/3 | 3/3 | 3 |
| `voice-salute` | 0 | 26 | 0 | 35430 | 3.116 | 79.382 | 3/3 | 3/3 | 3 |
| `window-budget` | 0 | 20 | 0 | 27808 | 3.571 | 37.718 | 3/3 | 3/3 | 3 |

## Caveats

- Sample is small: 5 same-author reuse tasks, 3 repeat(s) per arm.
- Tasks were designed by the same authors to match already-admitted crystals from the 2026-11-25 lattice gauntlets; this is not independent-user reuse.
- Formation cost of those crystals is excluded. This baseline measures reuse economics given an already-admitted lattice, not the payback period including first-time formation.
- Arm B is the governed AgentRun loop with crystal lookup disabled, not a raw chat-completions 'write me a fix' prompt, so the cold cost includes tool-loop overhead.
- Temperature is 0 and the provider seed is 731947+turn; the hosted endpoint may or may not honour seed.
- Spend was billed at $0.00 on the NVIDIA hosted trial; commercial_equivalent_usd is a list-price footnote only ($0.06 / $0.35 per 1M for this model, checked Nov 2026).
- Composite held-out tasks are not in this A/B: the original composite path is model-free replay, which is not an identical controller prompt to a cold multi-defect repair.
- Cold-arm call counts varied across repeats even with temperature 0 and a fixed seed formula, so the hosted endpoint did not produce identical traces.

## Notes

Credential files (`trial-key.pem` and similar) were excluded from this tracked copy. See `SKIPPED.md`.
Raw per-run receipts are under `receipts/`. The live workspace used for execution is not fully mirrored.
