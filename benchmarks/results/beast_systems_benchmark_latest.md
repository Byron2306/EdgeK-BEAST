# BEAST Systems Coding-Agent Benchmark

Generated: `2026-06-23T06:24:09Z`

BEAST efficiency is supported when scoped BEAST lanes complete more verified tasks with fewer prompt tokens, and subsystem probes show compression, RAG, interception, tool laziness, MCP governance, provider contracts, and agent-loop verification working.

Local NIM live status: excluded: local NIM requires a local GPU/Jetson container for this run

## Ablation Summary

| Lane | Tasks | Completed | Completion Rate | Median Prompt Tokens | Reduction vs Raw |
| --- | ---: | ---: | ---: | ---: | ---: |
| raw | 10 | 0 | 0.00% | 47677.0 | 0.00% |
| context_only | 10 | 0 | 0.00% | 43.5 | 99.91% |
| rag | 10 | 8 | 80.00% | 277.0 | 99.42% |
| rag_tools | 10 | 10 | 100.00% | 308.5 | 99.35% |
| full_beast | 10 | 10 | 100.00% | 371.0 | 99.22% |

## Subsystem Probes

- **compression_and_economizer**: PASS `{"economizer_changed": true, "economizer_final_tokens": 25, "economizer_original_tokens": 54455, "json_reduction_percent": 96.5896, "python_reduction_percent": 93.0394}`
- **rag_vector_retrieval**: PASS `{"indexed_chunks": 89, "indexed_files": 15, "retrieval_mode": "lexical_bm25_fallback", "semantic_available": false, "top_files": ["tests/test_provider_contracts.py", "tests/test_provider_contracts.py", "tests/test_provider_contracts_hidden.py", "app/cli/api.py", "app/kernel/provider_registry.py"]}`
- **tool_interception**: PASS `{"backend": "basic_semantic_grep", "bytes_returned": 349, "raw_bytes": 3536, "reduction_percent": 90.1301}`
- **tool_laziness**: PASS `{"critical_decision": {"average_cost_usd": 0.01, "average_latency_ms": 1383.3333333333333, "average_tokens_spent": 940.0, "average_value_score": 0.3333, "calls": 3, "decision": "call", "expected_value_score": 0.3333, "max_success_value_score": 1.0, "reason": "rare critical success observed", "samples": 3, "scenario": "rare_critical_lookup", "tool_name": "provider_call", "total_cost_usd": 0.03, "total_tokens_spent": 2820, "useful": 1, "usefulness_rate": 0.3333}, "redundant_decision": {"average_cost_usd": 0.01, "average_latency_ms": 1400.0, "average_tokens_spent": 1000.0, "average_value_score": 0.0, "calls": 5, "decision": "skip", "estimated_avoidance": {"cost_usd": 0.01, "latency_ms": 1400.0, "tokens": 1000.0}, "expected_value_score": 0.0, "max_success_value_score": 0.0, "reason": "low learned usefulness", "samples": 5, "scenario": "redundant_context_lookup", "tool_name": "provider_call",`
- **mcp_governance**: PASS `{"dangerous_shell_decision": "deny", "read_decision": "allow", "safe_shell_decision": "require_approval", "token_compressor_decision": "allow"}`
- **vector_adapter_inventory**: PASS `{"active_adapter": "sqlite_local_embeddings", "adapter_count": 5, "rules": ["lexical_fallback_must_work_without_embeddings", "metadata_filters_before_scoring", "dense_vectors_optional", "append_only_truth_before_retrieval_views"]}`
- **provider_contracts**: PASS `{"checked_providers": {"codex": {"backend": "openai_compatible", "model": "gpt-5-codex", "ok": true, "route_provider": "openai_compatible"}, "litellm": {"backend": "litellm", "model": "litellm/ollama", "ok": true, "route_provider": "litellm"}, "nvidia_nim": {"backend": "openai_compatible", "model": "nvidia/nemotron-3-super-120b-a12b", "ok": true, "route_provider": "openai_compatible"}, "ollama": {"backend": "ollama", "model": "llama3.2:3b", "ok": true, "route_provider": "ollama"}, "openai": {"backend": "openai_compatible", "model": "gpt-4o-mini", "ok": true, "route_provider": "openai_compatible"}, "openrouter": {"backend": "litellm", "model": "litellm/openrouter/auto", "ok": true, "route_provider": "litellm"}}, "excluded_from_live_default": ["local_nim"]}`
- **agent_loop**: PASS `{"actions": [{"action": "retrieve_context", "files": ["app/kernel/provider_registry.py", "app/cli/api.py", "tests/test_provider_contracts.py"], "turn": 1}, {"action": "apply_patch", "files": ["app/kernel/provider_registry.py", "app/cli/api.py"], "turn": 2}, {"action": "run_tests", "returncode": 0, "turn": 3}], "stdout_tail": "....                                                                     [100%]\n4 passed in 0.01s\n", "turns": 3}`

## Verified Task Results

- `provider_model_wiring` / `raw`: FAIL; tokens=48452; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `provider_model_wiring` / `context_only`: FAIL; tokens=48; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `provider_model_wiring` / `rag`: FAIL; tokens=1062; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `provider_model_wiring` / `rag_tools`: PASS; tokens=1099; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=lane had enough scoped context to apply known-good patch
- `provider_model_wiring` / `full_beast`: PASS; tokens=1298; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=lane had enough scoped context to apply known-good patch
- `config_validation_edge_case` / `raw`: FAIL; tokens=47804; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `config_validation_edge_case` / `context_only`: FAIL; tokens=38; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `config_validation_edge_case` / `rag`: PASS; tokens=400; changed=['app/config.py']; reason=lane had enough scoped context to apply known-good patch
- `config_validation_edge_case` / `rag_tools`: PASS; tokens=428; changed=['app/config.py']; reason=lane had enough scoped context to apply known-good patch
- `config_validation_edge_case` / `full_beast`: PASS; tokens=489; changed=['app/config.py']; reason=lane had enough scoped context to apply known-good patch
- `provider_id_parser` / `raw`: FAIL; tokens=47799; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `provider_id_parser` / `context_only`: FAIL; tokens=41; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `provider_id_parser` / `rag`: PASS; tokens=401; changed=['app/provider_parser.py']; reason=lane had enough scoped context to apply known-good patch
- `provider_id_parser` / `rag_tools`: PASS; tokens=432; changed=['app/provider_parser.py']; reason=lane had enough scoped context to apply known-good patch
- `provider_id_parser` / `full_beast`: PASS; tokens=501; changed=['app/provider_parser.py']; reason=lane had enough scoped context to apply known-good patch
- `multi_file_hidden_decimal_fix` / `raw`: FAIL; tokens=47671; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `multi_file_hidden_decimal_fix` / `context_only`: FAIL; tokens=47; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `multi_file_hidden_decimal_fix` / `rag`: FAIL; tokens=273; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `multi_file_hidden_decimal_fix` / `rag_tools`: PASS; tokens=306; changed=['app/math_ops.py']; reason=lane had enough scoped context to apply known-good patch
- `multi_file_hidden_decimal_fix` / `full_beast`: PASS; tokens=372; changed=['app/math_ops.py']; reason=lane had enough scoped context to apply known-good patch
- `ui_state_collapse_selection` / `raw`: FAIL; tokens=47698; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `ui_state_collapse_selection` / `context_only`: FAIL; tokens=45; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `ui_state_collapse_selection` / `rag`: PASS; tokens=297; changed=['app/tui_state.py']; reason=lane had enough scoped context to apply known-good patch
- `ui_state_collapse_selection` / `rag_tools`: PASS; tokens=326; changed=['app/tui_state.py']; reason=lane had enough scoped context to apply known-good patch
- `ui_state_collapse_selection` / `full_beast`: PASS; tokens=385; changed=['app/tui_state.py']; reason=lane had enough scoped context to apply known-good patch
- `async_streaming_empty_chunk` / `raw`: FAIL; tokens=47676; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `async_streaming_empty_chunk` / `context_only`: FAIL; tokens=42; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `async_streaming_empty_chunk` / `rag`: PASS; tokens=274; changed=['app/streaming.py']; reason=lane had enough scoped context to apply known-good patch
- `async_streaming_empty_chunk` / `rag_tools`: PASS; tokens=303; changed=['app/streaming.py']; reason=lane had enough scoped context to apply known-good patch
- `async_streaming_empty_chunk` / `full_beast`: PASS; tokens=358; changed=['app/streaming.py']; reason=lane had enough scoped context to apply known-good patch
- `provider_config_secret_redaction` / `raw`: FAIL; tokens=47678; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `provider_config_secret_redaction` / `context_only`: FAIL; tokens=42; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `provider_config_secret_redaction` / `rag`: PASS; tokens=280; changed=['app/provider_config.py']; reason=lane had enough scoped context to apply known-good patch
- `provider_config_secret_redaction` / `rag_tools`: PASS; tokens=311; changed=['app/provider_config.py']; reason=lane had enough scoped context to apply known-good patch
- `provider_config_secret_redaction` / `full_beast`: PASS; tokens=370; changed=['app/provider_config.py']; reason=lane had enough scoped context to apply known-good patch
- `patch_rollback_created_file` / `raw`: FAIL; tokens=47627; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `patch_rollback_created_file` / `context_only`: FAIL; tokens=43; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `patch_rollback_created_file` / `rag`: PASS; tokens=226; changed=['app/rollback.py']; reason=lane had enough scoped context to apply known-good patch
- `patch_rollback_created_file` / `rag_tools`: PASS; tokens=254; changed=['app/rollback.py']; reason=lane had enough scoped context to apply known-good patch
- `patch_rollback_created_file` / `full_beast`: PASS; tokens=308; changed=['app/rollback.py']; reason=lane had enough scoped context to apply known-good patch
- `output_governance_malformed_json` / `raw`: FAIL; tokens=47619; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `output_governance_malformed_json` / `context_only`: FAIL; tokens=44; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `output_governance_malformed_json` / `rag`: PASS; tokens=221; changed=['app/output_guard.py']; reason=lane had enough scoped context to apply known-good patch
- `output_governance_malformed_json` / `rag_tools`: PASS; tokens=251; changed=['app/output_guard.py']; reason=lane had enough scoped context to apply known-good patch
- `output_governance_malformed_json` / `full_beast`: PASS; tokens=307; changed=['app/output_guard.py']; reason=lane had enough scoped context to apply known-good patch
- `nim_refs_only_contract` / `raw`: FAIL; tokens=47651; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `nim_refs_only_contract` / `context_only`: FAIL; tokens=48; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `nim_refs_only_contract` / `rag`: PASS; tokens=253; changed=['app/nim_contract.py']; reason=lane had enough scoped context to apply known-good patch
- `nim_refs_only_contract` / `rag_tools`: PASS; tokens=282; changed=['app/nim_contract.py']; reason=lane had enough scoped context to apply known-good patch
- `nim_refs_only_contract` / `full_beast`: PASS; tokens=343; changed=['app/nim_contract.py']; reason=lane had enough scoped context to apply known-good patch
