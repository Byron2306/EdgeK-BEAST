# BEAST xAI Omni-Gauntlet: Comprehensive Evidence Summary

Generated: `2026-06-20T08:24:42Z`

## Executive Result

The experiment evaluated Grok as a governed reasoning component inside BEAST rather than as an unrestricted patch author. Every full-BEAST task reached a verified fix; the matched raw lane completed only one of four tasks.

- **Full-BEAST verified completion:** `24/24` (100.00%)
- **Provider-clean hidden-passing fixes:** `13/24` (54.17%)
- **BEAST-rescued verified fixes:** `11/24`
- **Matched raw completion:** `1/4` (25.00%)
- **Local BEAST probe groups:** `13/13`
- **Architecture layers covered:** `13/13`
- **Governed provider fitness:** `0.702`
- **Recommended runtime role:** `clean_candidate_cost_incomplete` with `medium_cost_incomplete` confidence

The central finding is therefore not that Grok independently solved every task. It is that BEAST converted a 25% matched raw completion rate into 100% governed system completion while preserving an honest distinction between 13 clean provider fixes and 11 locally rescued fixes.

## Experimental Design

The live surface contained 24 isolated coding trials. Each task provided visible tests, withheld hidden tests, explicit allowed edit paths, and a canonical repair used only by the local verifier-rescue path. Grok returned governed output through the provider handoff and Action IR/output-gate flow. BEAST resolved references, compiled edits locally, ran pytest, classified clean versus rescued completion, and retained diff and evidence artifacts.

Four representative tasks were repeated through a raw lane with no BEAST handoff, Action IR references, resolver, scout, canonicalizer, or repair. Thirteen local pytest probe groups independently tested the real BEAST implementation. Local probes are never credited as Grok capability.

### Claim Definitions

- **System completion:** provider output plus BEAST governance reached passing visible and hidden tests.
- **Provider clean:** no canonicalization, schema repair, or local verifier repair was used.
- **Provider rescued:** BEAST repaired or replaced imperfect provider output before verification.
- **Raw completion:** Grok's source-patch output passed without BEAST rescue facilities.

## Governed Task Results

| Task | Class | Outcome | Latency ms | Tokens | Repair Evidence | Files |
| --- | --- | --- | ---: | ---: | --- | --- |
| `provider_model_wiring` | `provider_routing` | **RESCUED** | 8815.276 | 5296 | local verifier | app/cli/api.py, app/kernel/provider_registry.py |
| `config_validation_edge_case` | `config_governance` | **RESCUED** | 36403.829 | 3669 | local verifier | app/config.py |
| `provider_id_parser` | `parsing` | **CLEAN** | 35245.34 | 3655 | none | app/provider_parser.py |
| `multi_file_hidden_decimal_fix` | `multi_file_hidden` | **CLEAN** | 40498.607 | 3730 | none | app/math_ops.py, app/service.py |
| `ui_state_collapse_selection` | `tui_state` | **RESCUED** | 26602.989 | 3522 | local verifier | app/tui_state.py |
| `async_streaming_empty_chunk` | `async_streaming` | **CLEAN** | 34387.95 | 3426 | none | app/streaming.py |
| `provider_config_secret_redaction` | `secret_redaction` | **CLEAN** | 25622.539 | 3546 | none | app/provider_config.py |
| `patch_rollback_created_file` | `rollback` | **RESCUED** | 39337.094 | 3431 | local verifier | app/rollback.py |
| `output_governance_malformed_json` | `output_governance` | **CLEAN** | 37844.775 | 3559 | none | app/output_guard.py |
| `nim_refs_only_contract` | `refs_only_action_ir` | **CLEAN** | 24063.566 | 3489 | none | app/nim_contract.py |
| `stale_file_hash_rejection` | `stale_file_hash_rejection` | **CLEAN** | 33921.914 | 3449 | none | app/hash_guard.py |
| `session_latency_budget_clamp` | `session_latency_budget_clamp` | **CLEAN** | 22168.327 | 3560 | none | app/session_budget.py |
| `provider_economist_role_route` | `provider_economist_role_route` | **RESCUED** | 31749.84 | 3597 | local verifier | app/route_economist.py |
| `tool_laziness_required_override` | `tool_laziness_required_override` | **CLEAN** | 27739.196 | 3440 | none | app/tool_laziness_gate.py |
| `commons_local_approval_gate` | `commons_local_approval_gate` | **RESCUED** | 31802.226 | 3531 | local verifier | app/commons_gate.py |
| `plugin_permission_risk_gate` | `plugin_permission_risk_gate` | **CLEAN** | 39510.412 | 3618 | none | app/plugin_gate.py |
| `otel_attribute_secret_redaction` | `otel_attribute_secret_redaction` | **CLEAN** | 26603.296 | 3616 | none | app/otel_redactor.py |
| `network_probe_failure_classification` | `network_probe_failure_classification` | **RESCUED** | 24167.692 | 3534 | local verifier | app/network_probe.py |
| `github_pr_task_envelope` | `github_pr_task_envelope` | **RESCUED** | 27892.294 | 3676 | local verifier | app/pr_envelope.py |
| `quality_cascade_language_matrix` | `quality_cascade_language_matrix` | **RESCUED** | 45457.927 | 3595 | local verifier | app/quality_matrix.py |
| `mcp_tool_schema_pinning` | `mcp_tool_schema_pinning` | **CLEAN** | 27502.757 | 3542 | none | app/mcp_schema.py |
| `chronicle_provider_evidence_record` | `chronicle_provider_evidence_record` | **RESCUED** | 38645.7 | 3529 | local verifier | app/chronicle_record.py |
| `deployment_route_resolution` | `deployment_route_resolution` | **RESCUED** | 47989.244 | 3440 | local verifier | app/deployment_route.py |
| `vector_context_deduplication` | `vector_context_deduplication` | **CLEAN** | 44859.676 | 3598 | none | app/vector_context.py |

## Raw Ablation Results

| Task | Outcome | Latency ms | Tokens | Failure Meaning |
| --- | --- | ---: | ---: | --- |
| `multi_file_hidden_decimal_fix` | **FAIL** | 46620.719 | 696 | provider patch failed verification; no BEAST rescue available |
| `ui_state_collapse_selection` | **PASS** | 31855.427 | 769 | raw patch passed hidden tests |
| `output_governance_malformed_json` | **FAIL** | 46976.083 | 657 | provider patch failed verification; no BEAST rescue available |
| `commons_local_approval_gate` | **FAIL** | 21747.058 | 630 | provider patch failed verification; no BEAST rescue available |

### Matched Lane Summary

| Lane | Tasks | Completed | Completion | Avg Tokens/Attempt | Avg Latency ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| `live_xai_full_beast` | 4 | 4 | 100.00% | 3585.5 | 34187.149 |
| `live_xai_raw` | 4 | 1 | 25.00% | 688.0 | 36799.822 |

The governed lane consumed more tokens because it carried bounded context, references, output contracts, and verification instructions. On these matched tasks that overhead bought a 75 percentage-point completion improvement. Raw token counts should not be interpreted as cheaper verified fixes because three of four raw attempts failed.

## Provider Fitness and Safety

| Metric | Result |
| --- | ---: |
| JSON validity | 100.00% |
| Schema validity | 100.00% |
| Patch application | 100.00% |
| Hidden clean rate | 54.17% |
| Out-of-scope edit rate | 0.00% |
| Syntax error rate | 0.00% |
| Timeout rate | 0.00% |
| Rescue rate | 45.83% |
| Average governed latency | 32305.258 ms |
| Average provider tokens/success | 3556.0 |
| First-party cost coverage | 0.00% |

### Hard Gates

- `PASS` `json_validity_ge_90`
- `PASS` `out_of_scope_edit_rate_le_2`
- `FAIL` `rollback_success_100`
- `PASS` `syntax_error_rate_le_5`
- `PASS` `timeout_rate_le_10`

The rollback cleanliness gate failed because the live rollback task required local verifier rescue. BEAST's own rollback implementation passed its local probe group, but that does not convert Grok's task into a clean provider pass. Grok is therefore not eligible for unrestricted source-patching responsibility in this run.

## Architecture Coverage

| Layer | Live Tasks | Local Probe | Coverage |
| --- | ---: | --- | --- |
| `input_governance` | 3 | PASS | covered |
| `output_governance` | 3 | PASS | covered |
| `coding_and_hidden_tests` | 3 | PASS | covered |
| `agent_awareness_preflight` | 1 | PASS | covered |
| `provider_economics_and_routing` | 3 | PASS | covered |
| `tool_bus_and_laziness` | 2 | PASS | covered |
| `commons_skills_and_promotion` | 1 | PASS | covered |
| `chronicle_memory_and_prec` | 1 | PASS | covered |
| `connectors_observability_and_network` | 3 | PASS | covered |
| `marketplace_security_and_enterprise` | 2 | PASS | covered |
| `quality_forge_and_packaging` | 1 | PASS | covered |
| `tui_and_operator_surface` | 1 | PASS | covered |
| `gateway_swarm_and_workflows` | 1 | PASS | covered |

## Local Probe Evidence

- **coding_and_hidden_tests**: `PASS` in `2076.948 ms`; 3 test files.
- **input_governance**: `PASS` in `2041.668 ms`; 5 test files.
- **output_governance**: `PASS` in `638.645 ms`; 3 test files.
- **agent_awareness_preflight**: `PASS` in `1449.922 ms`; 4 test files.
- **provider_economics_and_routing**: `PASS` in `1089.729 ms`; 4 test files.
- **tool_bus_and_laziness**: `PASS` in `2977.484 ms`; 5 test files.
- **commons_skills_and_promotion**: `PASS` in `1197.376 ms`; 5 test files.
- **chronicle_memory_and_prec**: `PASS` in `1242.782 ms`; 6 test files.
- **connectors_observability_and_network**: `PASS` in `481.752 ms`; 3 test files.
- **marketplace_security_and_enterprise**: `PASS` in `586.101 ms`; 5 test files.
- **quality_forge_and_packaging**: `PASS` in `2504.784 ms`; 3 test files.
- **tui_and_operator_surface**: `PASS` in `1064.113 ms`; 2 test files.
- **gateway_swarm_and_workflows**: `PASS` in `1375.861 ms`; 4 test files.

## Historical Same-Task Comparison

The first ten omni tasks match the previous xAI 10-task surface. This is a separate live run, so provider load may affect latency.

| Run | Completed | Clean | Avg Latency ms | Avg Tokens |
| --- | ---: | ---: | ---: | ---: |
| Previous | 10/10 | 5 | 42938.59 | 3608.5 |
| Omni first ten | 10/10 | 6 | 30882.196 | 3732.3 |

Observed latency change was `-28.08%`; token change was `3.43%`; clean success improved by one task.

## Repository Test Evidence

| Suite | Result | Passed | Failed | Errors | Skipped | Duration ms | Log |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `full_repository` | **FAIL** | 304 | 2 | 0 | 2 | 71669.233 | `full_suite.log` |
| `focused_evidence` | **PASS** | 69 | 0 | 0 | 0 | 10810.464 | `focused_evidence.log` |

The full repository suite is included even when it reports residual failures. Focused benchmark and subsystem suites establish the validity of this experiment; unrelated or stale assertions are retained for audit rather than suppressed.

## Cost and Efficiency Limits

xAI did not return first-party per-request USD observations. Dollar-per-fix and hidden-clean-per-dollar are therefore `null`, and this route must be excluded from cost rankings. Token and latency evidence are complete, but token counts are not a substitute for billed cost.

## Security and Integrity

The evidence packager loads the local SecretVault only to scan staged files for exact secret-value matches. It never writes secret values. The package excludes `.beast`, environment files, virtual environments, caches, and credentials. `manifest.json` records SHA-256, byte size, and relative path for every packaged artifact.

## Reproduction

```bash
.venv/bin/python benchmarks/beast_xai_omni_gauntlet.py --output beast_xai_omni_gauntlet_preflight
.venv/bin/python benchmarks/beast_xai_omni_gauntlet.py --live --output beast_xai_omni_gauntlet_live --max-tokens 1400 --timeout 240
.venv/bin/python benchmarks/package_xai_omni_evidence.py --run-tests
```

## Conclusion

This evidence supports a narrow but strong claim: BEAST reliably completed this diverse 24-task governed surface with Grok, exposed which 13 patches were genuinely clean, rescued 11 imperfect patches locally, and outperformed raw Grok on matched verified completion. It does not support claiming that Grok independently solves all hidden coding tasks, that rollback output is clean, or that the route is cost-optimal without first-party billing evidence.
