# Public Benchmark Harness

BEAST's economic thesis should be treated as an open research question until public baselines, blinded grading, and full cost ledgers are published together.

Use [benchmarks/public_economic_thesis_harness.py](/home/byron/EdgeK-BEAST/benchmarks/public_economic_thesis_harness.py) to package existing benchmark result JSON into a public evaluation packet.

The harness produces:

- `blind_grading.jsonl`: shuffled task/output pairs without lane labels.
- `blind_grading_key.json`: the private unblinding map.
- `grade_template.jsonl`: blank grader rows keyed by `blind_id`.
- `grade_rubric.json`: the grading field contract.
- `cost_accounting.json`: tokens, completion counts, and first-party cost fields grouped by lane.
- `manifest.json`: explicit claim status and input provenance.
- `README.md`: the packet summary and publication checklist.
- `verdict.json` and `verdict.md`: generated after completed grades are supplied back to the harness.

Typical flow:

```bash
python3 benchmarks/public_economic_thesis_harness.py \
  benchmarks/results/beast_xai_omni_gauntlet_live \
  benchmarks/results/beast_xai_omni_gauntlet_preflight \
  --output-dir benchmarks/results/public_economic_thesis_packet

# fill grade_template.jsonl, then rerun with completed grades
python3 benchmarks/public_economic_thesis_harness.py \
  benchmarks/results/beast_xai_omni_gauntlet_live \
  benchmarks/results/beast_xai_omni_gauntlet_preflight \
  --output-dir benchmarks/results/public_economic_thesis_packet \
  --grades benchmarks/results/public_economic_thesis_packet/grade_template.jsonl
```

Short alpha blind test:

```bash
python3 benchmarks/public_economic_thesis_harness.py \
  benchmarks/results/beast_xai_omni_gauntlet_live/omni_report.json \
  benchmarks/results/beast_xai_omni_gauntlet_preflight/omni_report.json \
  --output-dir benchmarks/results/alpha_blind_test_packet \
  --alpha-lane-size 4
```

That produces a short balanced packet with up to `4` governed rows and `4`
baseline rows, filtered to human-gradable items with non-empty provider output
excerpts.

Publication bar:

1. Include at least one governed lane and one non-BEAST baseline lane.
2. Grade `blind_grading.jsonl` without lane labels and record the results in `grade_template.jsonl`.
3. Rerun the harness with `--grades` to generate `verdict.json` and `verdict.md`.
4. Publish the graded packet, the unblinding key, the verdict, and `cost_accounting.json` together.
5. Keep external messaging at `open_research_question` until that packet is public.