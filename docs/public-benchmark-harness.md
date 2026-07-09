# Public Benchmark Harness

BEAST's economic thesis should be treated as an open research question until public baselines, blinded grading, and full cost ledgers are published together.

Use [benchmarks/public_economic_thesis_harness.py](/home/byron/EdgeK-BEAST/benchmarks/public_economic_thesis_harness.py) to package existing benchmark result JSON into a public evaluation packet.

The harness produces:

- `blind_grading.jsonl`: shuffled task/output pairs without lane labels.
- `blind_grading_key.json`: the private unblinding map.
- `cost_accounting.json`: tokens, completion counts, and first-party cost fields grouped by lane.
- `manifest.json`: explicit claim status and input provenance.
- `README.md`: the packet summary and publication checklist.

Typical flow:

```bash
python3 benchmarks/public_economic_thesis_harness.py \
  benchmarks/results/beast_xai_omni_gauntlet_live \
  benchmarks/results/beast_xai_omni_gauntlet_preflight \
  --output-dir benchmarks/results/public_economic_thesis_packet
```

Publication bar:

1. Include at least one governed lane and one non-BEAST baseline lane.
2. Grade `blind_grading.jsonl` without lane labels.
3. Publish the graded packet, the unblinding key, and `cost_accounting.json` together.
4. Keep external messaging at `open_research_question` until that packet is public.