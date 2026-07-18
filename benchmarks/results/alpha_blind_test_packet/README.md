# Public Economic Thesis Packet

Generated: `2026-07-09T17:44:56Z`

This packet standardizes public evaluation. It does not claim the thesis is proven.

- Claim status: `open_research_question`
- Rows included: `8`
- Blind grading packet: `blind_grading.jsonl` (8 items)
- Grader template: `grade_template.jsonl`
- Cost accounting: `cost_accounting.json`

## Lane Summary

| Lane | Rows | Completed | Tokens | Cost Rows |
| --- | ---: | ---: | ---: | ---: |
| `baseline` | 4 | 1 | 23719 | 0 |
| `governed` | 4 | 4 | 36382 | 0 |

## Required Next Step

Run blinded human or verifier grading against `blind_grading.jsonl`, fill `grade_template.jsonl`, then rerun this harness with `--grades` to generate `verdict.json` and `verdict.md`. Until then, external claims should stay framed as an open research question.
