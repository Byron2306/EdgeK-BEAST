# Candidate template

Copy this directory to `candidate/`, then replace every template or unassessed value with evidence from the frozen DAI-Diode archives.

## Required actions

1. Copy the original Phase 1 through Phase 6.2 ZIP files into `artifacts/` unchanged.
2. Run `discover-lineage` and merge the discovered nodes/edges into `lineage/LINEAGE_LEDGER.json`.
3. Resolve the Phase 2/2.1 mismatch explicitly. Do not delete either historical object.
4. Set `review_required` to `false` only after two named reviewers inspect the exact digests and predecessor edges.
5. Freeze the solver, then obtain independently authored arena cases and oracle.
6. Adapt `arena/BASELINE_INPUT.json` and `arena/ABLATION_PLAN.json` to the actual final runner.
7. Run system-specific mutations and ablations; store signed reports under `reports/`.
8. Run the final arena with egress denied and preserve `reports/NETWORK_DENIAL_WITNESS.json`.
9. Collect at least two independent reproduction reports and at least three independent quorum packets.
10. Change every supported claim status from `unassessed` to `pass`; leave unsupported claims withheld.
11. Run `validate-candidate --stage final` before building.

The template is intentionally not publishable as-is.
