# BEAST Systems Coding-Agent Benchmark

Generated: `2026-06-18T15:47:25Z`

BEAST efficiency is supported when scoped BEAST lanes complete more verified tasks with fewer prompt tokens, and subsystem probes show compression, RAG, interception, tool laziness, MCP governance, provider contracts, and agent-loop verification working.

Local NIM live status: excluded: local NIM requires a local GPU/Jetson container for this run

## Ablation Summary

| Lane | Tasks | Completed | Completion Rate | Median Prompt Tokens | Reduction vs Raw |
| --- | ---: | ---: | ---: | ---: | ---: |
| context_only | 10 | 0 | 0.00% | 43.5 | 99.91% |
| full_beast | 10 | 10 | 100.00% | 390.0 | 99.18% |
| rag | 10 | 8 | 80.00% | 296.0 | 99.38% |
| rag_tools | 10 | 10 | 100.00% | 325.5 | 99.32% |
| raw | 10 | 0 | 0.00% | 47661.0 | 0.00% |

## Subsystem Probes

- **agent_loop**: PASS `{"actions": [{"action": "retrieve_context", "files": ["app/kernel/provider_registry.py", "app/cli/api.py", "tests/test_provider_contracts.py"], "turn": 1}, {"action": "apply_patch", "files": ["app/kernel/provider_registry.py", "app/cli/api.py"], "turn": 2}, {"action": "run_tests", "returncode": 0, "turn": 3}], "stdout_tail": "...                                                                      [100%]\n3 passed in 0.01s\n", "turns": 3}`
- **compression_and_economizer**: PASS `{"economizer_changed": true, "economizer_final_tokens": 25, "economizer_original_tokens": 54455, "json_reduction_percent": 96.5896, "python_reduction_percent": 93.0394}`
- **mcp_governance**: PASS `{"dangerous_shell_decision": "deny", "read_decision": "allow", "safe_shell_decision": "require_approval", "token_compressor_decision": "allow"}`
- **provider_contracts**: PASS `{"checked_providers": {"codex": {"backend": "openai_compatible", "model": "gpt-5-codex", "ok": true, "route_provider": "openai_compatible"}, "litellm": {"backend": "litellm", "model": "litellm/ollama", "ok": true, "route_provider": "litellm"}, "nvidia_nim": {"backend": "openai_compatible", "model": "nvidia/nemotron-3-super-120b-a12b", "ok": true, "route_provider": "openai_compatible"}, "ollama": {"backend": "ollama", "model": "llama3.2:3b", "ok": true, "route_provider": "ollama"}, "openai": {"backend": "openai_compatible", "model": "gpt-4o-mini", "ok": true, "route_provider": "openai_compatible"}, "openrouter": {"backend": "litellm", "model": "litellm/openrouter/auto", "ok": true, "route_provider": "litellm"}}, "excluded_from_live_default": ["local_nim"]}`
- **rag_vector_retrieval**: PASS `{"indexed_chunks": 87, "indexed_files": 14, "retrieval_mode": "dense_vector", "semantic_available": true, "top_files": ["tests/test_provider_contracts.py", "app/cli/api.py", "tests/test_provider_contracts.py", "tests/test_provider_contracts.py", "app/cli/api.py"]}`
- **tool_interception**: PASS `{"backend": "basic_semantic_grep", "bytes_returned": 349, "raw_bytes": 3536, "reduction_percent": 90.1301}`
- **tool_laziness**: PASS `{"critical_decision": {"average_cost_usd": 0.01, "average_latency_ms": 1383.3333333333333, "average_tokens_spent": 940.0, "average_value_score": 0.3333, "calls": 3, "decision": "call", "expected_value_score": 0.3333, "max_success_value_score": 1.0, "reason": "rare critical success observed", "samples": 3, "scenario": "rare_critical_lookup", "tool_name": "provider_call", "total_cost_usd": 0.03, "total_tokens_spent": 2820, "useful": 1, "usefulness_rate": 0.3333}, "redundant_decision": {"average_cost_usd": 0.01, "average_latency_ms": 1400.0, "average_tokens_spent": 1000.0, "average_value_score": 0.0, "calls": 5, "decision": "skip", "estimated_avoidance": {"cost_usd": 0.01, "latency_ms": 1400.0, "tokens": 1000.0}, "expected_value_score": 0.0, "max_success_value_score": 0.0, "reason": "low learned usefulness", "samples": 5, "scenario": "redundant_context_lookup", "tool_name": "provider_call",`
- **vector_adapter_inventory**: PASS `{"active_adapter": "sqlite_local_embeddings", "adapter_count": 5, "rules": ["lexical_fallback_must_work_without_embeddings", "metadata_filters_before_scoring", "dense_vectors_optional", "append_only_truth_before_retrieval_views"]}`

## Verified Task Results

- `provider_model_wiring` / `raw`: FAIL; tokens=48312; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `provider_model_wiring` / `context_only`: FAIL; tokens=48; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `provider_model_wiring` / `rag`: FAIL; tokens=909; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `provider_model_wiring` / `rag_tools`: PASS; tokens=947; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=lane had enough scoped context to apply known-good patch
- `provider_model_wiring` / `full_beast`: PASS; tokens=1145; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=lane had enough scoped context to apply known-good patch
- `config_validation_edge_case` / `raw`: FAIL; tokens=47725; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `config_validation_edge_case` / `context_only`: FAIL; tokens=38; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `config_validation_edge_case` / `rag`: PASS; tokens=312; changed=['app/config.py']; reason=lane had enough scoped context to apply known-good patch
- `config_validation_edge_case` / `rag_tools`: PASS; tokens=340; changed=['app/config.py']; reason=lane had enough scoped context to apply known-good patch
- `config_validation_edge_case` / `full_beast`: PASS; tokens=401; changed=['app/config.py']; reason=lane had enough scoped context to apply known-good patch
- `provider_id_parser` / `raw`: FAIL; tokens=47706; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `provider_id_parser` / `context_only`: FAIL; tokens=41; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `provider_id_parser` / `rag`: PASS; tokens=297; changed=['app/provider_parser.py']; reason=lane had enough scoped context to apply known-good patch
- `provider_id_parser` / `rag_tools`: PASS; tokens=327; changed=['app/provider_parser.py']; reason=lane had enough scoped context to apply known-good patch
- `provider_id_parser` / `full_beast`: PASS; tokens=397; changed=['app/provider_parser.py']; reason=lane had enough scoped context to apply known-good patch
- `multi_file_hidden_decimal_fix` / `raw`: FAIL; tokens=47671; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `multi_file_hidden_decimal_fix` / `context_only`: FAIL; tokens=47; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `multi_file_hidden_decimal_fix` / `rag`: FAIL; tokens=270; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `multi_file_hidden_decimal_fix` / `rag_tools`: PASS; tokens=304; changed=['app/math_ops.py']; reason=lane had enough scoped context to apply known-good patch
- `multi_file_hidden_decimal_fix` / `full_beast`: PASS; tokens=369; changed=['app/math_ops.py']; reason=lane had enough scoped context to apply known-good patch
- `ui_state_collapse_selection` / `raw`: FAIL; tokens=47698; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `ui_state_collapse_selection` / `context_only`: FAIL; tokens=45; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `ui_state_collapse_selection` / `rag`: PASS; tokens=295; changed=['app/tui_state.py']; reason=lane had enough scoped context to apply known-good patch
- `ui_state_collapse_selection` / `rag_tools`: PASS; tokens=324; changed=['app/tui_state.py']; reason=lane had enough scoped context to apply known-good patch
- `ui_state_collapse_selection` / `full_beast`: PASS; tokens=383; changed=['app/tui_state.py']; reason=lane had enough scoped context to apply known-good patch
- `async_streaming_empty_chunk` / `raw`: FAIL; tokens=47595; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `async_streaming_empty_chunk` / `context_only`: FAIL; tokens=42; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `async_streaming_empty_chunk` / `rag`: PASS; tokens=183; changed=['app/streaming.py']; reason=lane had enough scoped context to apply known-good patch
- `async_streaming_empty_chunk` / `rag_tools`: PASS; tokens=212; changed=['app/streaming.py']; reason=lane had enough scoped context to apply known-good patch
- `async_streaming_empty_chunk` / `full_beast`: PASS; tokens=267; changed=['app/streaming.py']; reason=lane had enough scoped context to apply known-good patch
- `provider_config_secret_redaction` / `raw`: FAIL; tokens=47596; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `provider_config_secret_redaction` / `context_only`: FAIL; tokens=42; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `provider_config_secret_redaction` / `rag`: PASS; tokens=1560; changed=['app/provider_config.py']; reason=lane had enough scoped context to apply known-good patch
- `provider_config_secret_redaction` / `rag_tools`: PASS; tokens=1591; changed=['app/provider_config.py']; reason=lane had enough scoped context to apply known-good patch
- `provider_config_secret_redaction` / `full_beast`: PASS; tokens=1650; changed=['app/provider_config.py']; reason=lane had enough scoped context to apply known-good patch
- `patch_rollback_created_file` / `raw`: FAIL; tokens=47627; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `patch_rollback_created_file` / `context_only`: FAIL; tokens=43; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `patch_rollback_created_file` / `rag`: PASS; tokens=1596; changed=['app/rollback.py']; reason=lane had enough scoped context to apply known-good patch
- `patch_rollback_created_file` / `rag_tools`: PASS; tokens=1625; changed=['app/rollback.py']; reason=lane had enough scoped context to apply known-good patch
- `patch_rollback_created_file` / `full_beast`: PASS; tokens=1679; changed=['app/rollback.py']; reason=lane had enough scoped context to apply known-good patch
- `output_governance_malformed_json` / `raw`: FAIL; tokens=47619; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `output_governance_malformed_json` / `context_only`: FAIL; tokens=44; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `output_governance_malformed_json` / `rag`: PASS; tokens=219; changed=['app/output_guard.py']; reason=lane had enough scoped context to apply known-good patch
- `output_governance_malformed_json` / `rag_tools`: PASS; tokens=249; changed=['app/output_guard.py']; reason=lane had enough scoped context to apply known-good patch
- `output_governance_malformed_json` / `full_beast`: PASS; tokens=304; changed=['app/output_guard.py']; reason=lane had enough scoped context to apply known-good patch
- `nim_refs_only_contract` / `raw`: FAIL; tokens=47651; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `nim_refs_only_contract` / `context_only`: FAIL; tokens=48; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `nim_refs_only_contract` / `rag`: PASS; tokens=250; changed=['app/nim_contract.py']; reason=lane had enough scoped context to apply known-good patch
- `nim_refs_only_contract` / `rag_tools`: PASS; tokens=280; changed=['app/nim_contract.py']; reason=lane had enough scoped context to apply known-good patch
- `nim_refs_only_contract` / `full_beast`: PASS; tokens=340; changed=['app/nim_contract.py']; reason=lane had enough scoped context to apply known-good patch

## Live Provider Summary

| Provider | Tasks | Completed | Clean | Rescued | Completion Rate | Avg Latency ms | Avg Prompt Tokens | Tokens/Fix |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| huggingface | 10 | 10 | 3 | 7 | 100.00% | 1641.115 | 3331.9 | 4527.4 |
| openrouter | 10 | 10 | 2 | 8 | 100.00% | 2703.126 | 4083.6 | 4483.8 |

## Live Efficiency By Lane

| Lane | Tasks | Completed | Clean | Rescued | Canonicalized | Schema Repair | Local Repair | Completion Rate | Avg Latency ms | Tokens/Fix |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| live_huggingface_full_beast | 10 | 10 | 3 | 7 | 0 | 1 | 7 | 100.00% | 1641.115 | 4527.4 |
| live_openrouter_full_beast | 10 | 10 | 2 | 8 | 0 | 1 | 8 | 100.00% | 2703.126 | 4483.8 |

## Live Provider Results

- `openrouter` / `provider_model_wiring` / `live_openrouter_full_beast`: PASS; estimated_tokens=4281; provider_prompt_tokens=5788; latency_ms=5234.508; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter` / `config_validation_edge_case` / `live_openrouter_full_beast`: PASS; estimated_tokens=3195; provider_prompt_tokens=4159; latency_ms=2440.387; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/config.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter` / `provider_id_parser` / `live_openrouter_full_beast`: PASS; estimated_tokens=3173; provider_prompt_tokens=4136; latency_ms=2321.02; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter` / `multi_file_hidden_decimal_fix` / `live_openrouter_full_beast`: PASS; estimated_tokens=3193; provider_prompt_tokens=4187; latency_ms=2689.194; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/math_ops.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter` / `ui_state_collapse_selection` / `live_openrouter_full_beast`: PASS; estimated_tokens=3118; provider_prompt_tokens=4101; latency_ms=3198.636; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/tui_state.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter` / `async_streaming_empty_chunk` / `live_openrouter_full_beast`: PASS; estimated_tokens=3067; provider_prompt_tokens=3973; latency_ms=2304.068; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/streaming.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter` / `provider_config_secret_redaction` / `live_openrouter_full_beast`: PASS; estimated_tokens=3056; provider_prompt_tokens=2631; latency_ms=1694.378; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/provider_config.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter` / `patch_rollback_created_file` / `live_openrouter_full_beast`: PASS; estimated_tokens=3027; provider_prompt_tokens=3919; latency_ms=2742.63; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/rollback.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter` / `output_governance_malformed_json` / `live_openrouter_full_beast`: PASS; estimated_tokens=3044; provider_prompt_tokens=3973; latency_ms=2373.293; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter` / `nim_refs_only_contract` / `live_openrouter_full_beast`: PASS; estimated_tokens=3058; provider_prompt_tokens=3969; latency_ms=2033.144; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider returned scoped operations; pytest judged completion
- `huggingface` / `provider_model_wiring` / `live_huggingface_full_beast`: PASS; estimated_tokens=4281; provider_prompt_tokens=4803; latency_ms=1663.066; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider returned scoped operations; pytest judged completion
- `huggingface` / `config_validation_edge_case` / `live_huggingface_full_beast`: PASS; estimated_tokens=3195; provider_prompt_tokens=3437; latency_ms=1514.428; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/config.py']; reason=live provider returned scoped operations; pytest judged completion
- `huggingface` / `provider_id_parser` / `live_huggingface_full_beast`: PASS; estimated_tokens=3173; provider_prompt_tokens=3425; latency_ms=2652.123; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/provider_parser.py']; reason=live provider returned scoped operations; pytest judged completion
- `huggingface` / `multi_file_hidden_decimal_fix` / `live_huggingface_full_beast`: PASS; estimated_tokens=3194; provider_prompt_tokens=2005; latency_ms=830.446; canonicalized=False; repair_attempted=True; local_verifier_repair=True; changed=['app/math_ops.py']; reason=live provider returned scoped operations; pytest judged completion
- `huggingface` / `ui_state_collapse_selection` / `live_huggingface_full_beast`: PASS; estimated_tokens=3119; provider_prompt_tokens=3326; latency_ms=2196.478; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/tui_state.py']; reason=live provider returned scoped operations; pytest judged completion
- `huggingface` / `async_streaming_empty_chunk` / `live_huggingface_full_beast`: PASS; estimated_tokens=3068; provider_prompt_tokens=3254; latency_ms=1361.58; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/streaming.py']; reason=live provider returned scoped operations; pytest judged completion
- `huggingface` / `provider_config_secret_redaction` / `live_huggingface_full_beast`: PASS; estimated_tokens=3057; provider_prompt_tokens=3258; latency_ms=1725.966; canonicalized=False; repair_attempted=False; local_verifier_repair=False; changed=['app/provider_config.py']; reason=live provider returned scoped operations; pytest judged completion
- `huggingface` / `patch_rollback_created_file` / `live_huggingface_full_beast`: PASS; estimated_tokens=3028; provider_prompt_tokens=3264; latency_ms=1188.647; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/rollback.py']; reason=live provider returned scoped operations; pytest judged completion
- `huggingface` / `output_governance_malformed_json` / `live_huggingface_full_beast`: PASS; estimated_tokens=3044; provider_prompt_tokens=3245; latency_ms=1431.034; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/output_guard.py']; reason=live provider returned scoped operations; pytest judged completion
- `huggingface` / `nim_refs_only_contract` / `live_huggingface_full_beast`: PASS; estimated_tokens=3059; provider_prompt_tokens=3302; latency_ms=1847.382; canonicalized=False; repair_attempted=False; local_verifier_repair=True; changed=['app/nim_contract.py']; reason=live provider returned scoped operations; pytest judged completion

## Live Provider Fitness

| Provider | Score | Eligible | JSON Valid | Schema Valid | Patch Apply | Hidden Tests | Scope Error Rate | Syntax Error Rate | Timeout Rate | Rollback |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| huggingface | 0.583 | False | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| openrouter | 0.544 | False | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## Failure Buckets

- `capability_failure`: 20
