# Compute Governor Phase 1 Shadow Benchmark

- Scenarios: `5`
- Behavior preserved: `True`
- Candidate detection rate: `100.00%`
- Observed tokens: `615`
- Counterfactual avoidable-token estimate: `176`

Avoidable-token values are counterfactual estimates, not measured savings.

| Scenario | Candidates | Selected | Recommended | Enforced | Preserved |
| --- | --- | --- | --- | --- | --- |
| `deterministic_test` | syntax_check, test_execution | selected_provider | escalate | False | True |
| `schema_contract` | schema_validation | selected_provider | escalate | False | True |
| `route_diagnostic` | route_diagnostics | selected_provider | escalate | False | True |
| `patch_compile` | patch_compilation, syntax_check | selected_provider | escalate | False | True |
| `semantic_only` | none | selected_provider | selected_provider | False | True |
