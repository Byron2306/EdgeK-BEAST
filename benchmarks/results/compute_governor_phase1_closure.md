# Compute Governor Phase 1 Closure Preflight

- Paired attempts: `120`
- Provider calls accounting off/on: `120/120`
- Provider-call path unchanged: `True`
- Verified behavior preservation: `100.0%`
- Provider path / patch / verifier equivalence: `100.0%` / `100.0%` / `100.0%`
- Behavior differences: `0`
- Receipt coverage: `100.0%`
- Candidate calls avoidable: `100` (counterfactual)
- Estimated avoidable tokens: `4380` (counterfactual)
- Estimated avoidable USD: `None` (no cost inference)
- Enforced suppressions: `0`
- False suppression rate: `0.0%`
- Phase 1 deterministic preflight: `PASS`

## Task Classes

| Task class | Attempts | Behavior | Candidate detection | Candidate calls | Avoidable tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| `schema_validation` | 20 | 100.0% | 100.0% | 100.0% | 880 |
| `provider_routing` | 20 | 100.0% | 100.0% | 100.0% | 880 |
| `patch_compilation` | 20 | 100.0% | 100.0% | 100.0% | 880 |
| `test_selection` | 20 | 100.0% | 100.0% | 100.0% | 880 |
| `secret_redaction` | 20 | 100.0% | 100.0% | 100.0% | 860 |
| `semantic_reasoning` | 20 | 100.0% | 100.0% | 0.0% | 0 |

## Claim Boundary

This deterministic paired preflight measures instrumentation equivalence and counterfactual opportunity. It does not prove realized production savings or displaced live provider calls.
