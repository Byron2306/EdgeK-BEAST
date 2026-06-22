# Compute Governor Free-Provider Live Evidence

- Selected providers: `nvidia_nim`
- Provider calls: `3`
- Successful calls: `3`
- Compute receipts: `3`
- Receipt coverage: `100.0%`
- Observed tokens: `421`
- Candidate avoidable tokens: `123` (counterfactual)
- Phase 1 free live: `PASS`
- Phase 2 free live shadow: `PASS`

## Rows

| Provider | Task class | Status | Verified | Agreement | Tokens | Latency ms |
| --- | --- | --- | --- | --- | ---: | ---: |
| `nvidia_nim` | `schema_validation` | `succeeded` | True | True | 139 | 3208.739 |
| `nvidia_nim` | `syntax_check` | `succeeded` | True | True | 141 | 17299.882 |
| `nvidia_nim` | `test_execution` | `succeeded` | True | True | 141 | 1944.319 |

## Claim Boundary

Free-provider live evidence proves receipt coverage and Phase 2 shadow transform agreement beside real provider calls. It does not claim deterministic displacement of live calls.
