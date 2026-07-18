# Public Economic Thesis Packet

Generated: `2026-07-09T18:58:00Z`

This packet standardizes public evaluation. It does not claim the thesis is proven.

- Claim status: `open_research_question`
- Rows included: `96`
- Blind grading packet: `blind_grading.jsonl` (96 items)
- Grader template: `grade_template.jsonl`
- Cost accounting: `cost_accounting.json`

## Lane Summary

| Lane | Rows | Completed | Tokens | Cost Rows |
| --- | ---: | ---: | ---: | ---: |
| `baseline` | 36 | 3 | 30042 | 0 |
| `candidate` | 24 | 2 | 20502 | 0 |
| `governed` | 36 | 36 | 135297 | 0 |

## Required Next Step

Run blinded human or verifier grading against `blind_grading.jsonl`, fill `grade_template.jsonl`, then rerun this harness with `--grades` to generate `verdict.json` and `verdict.md`. Until then, external claims should stay framed as an open research question.
