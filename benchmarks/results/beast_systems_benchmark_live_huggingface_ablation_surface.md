# BEAST Systems Coding-Agent Benchmark

Generated: `2026-06-18T14:36:29Z`

BEAST efficiency is supported when scoped BEAST lanes complete more verified tasks with fewer prompt tokens, and subsystem probes show compression, RAG, interception, tool laziness, MCP governance, provider contracts, and agent-loop verification working.

Local NIM live status: excluded: local NIM requires a local GPU/Jetson container for this run

## Ablation Summary

| Lane | Tasks | Completed | Completion Rate | Median Prompt Tokens | Reduction vs Raw |
| --- | ---: | ---: | ---: | ---: | ---: |
| raw | 3 | 0 | 0.00% | 47725 | 0.00% |
| context_only | 3 | 0 | 0.00% | 41 | 99.91% |
| rag | 3 | 2 | 66.67% | 312 | 99.35% |
| rag_tools | 3 | 3 | 100.00% | 340 | 99.29% |
| full_beast | 3 | 3 | 100.00% | 401 | 99.16% |

## Subsystem Probes

- **compression_and_economizer**: PASS `{"economizer_changed": true, "economizer_final_tokens": 25, "economizer_original_tokens": 54455, "json_reduction_percent": 96.5896, "python_reduction_percent": 93.0394}`
- **rag_vector_retrieval**: PASS `{"indexed_chunks": 87, "indexed_files": 14, "retrieval_mode": "dense_vector", "semantic_available": true, "top_files": ["tests/test_provider_contracts.py", "app/cli/api.py", "tests/test_provider_contracts.py", "tests/test_provider_contracts.py", "app/cli/api.py"]}`
- **tool_interception**: PASS `{"backend": "basic_semantic_grep", "bytes_returned": 349, "raw_bytes": 3536, "reduction_percent": 90.1301}`
- **tool_laziness**: PASS `{"critical_decision": {"average_cost_usd": 0.01, "average_latency_ms": 1383.3333333333333, "average_tokens_spent": 940.0, "average_value_score": 0.3333, "calls": 3, "decision": "call", "expected_value_score": 0.3333, "max_success_value_score": 1.0, "reason": "rare critical success observed", "samples": 3, "scenario": "rare_critical_lookup", "tool_name": "provider_call", "total_cost_usd": 0.03, "total_tokens_spent": 2820, "useful": 1, "usefulness_rate": 0.3333}, "redundant_decision": {"average_cost_usd": 0.01, "average_latency_ms": 1400.0, "average_tokens_spent": 1000.0, "average_value_score": 0.0, "calls": 5, "decision": "skip", "estimated_avoidance": {"cost_usd": 0.01, "latency_ms": 1400.0, "tokens": 1000.0}, "expected_value_score": 0.0, "max_success_value_score": 0.0, "reason": "low learned usefulness", "samples": 5, "scenario": "redundant_context_lookup", "tool_name": "provider_call",`
- **mcp_governance**: PASS `{"dangerous_shell_decision": "deny", "read_decision": "allow", "safe_shell_decision": "require_approval", "token_compressor_decision": "allow"}`
- **vector_adapter_inventory**: PASS `{"active_adapter": "sqlite_local_embeddings", "adapter_count": 5, "rules": ["lexical_fallback_must_work_without_embeddings", "metadata_filters_before_scoring", "dense_vectors_optional", "append_only_truth_before_retrieval_views"]}`
- **provider_contracts**: PASS `{"checked_providers": {"codex": {"backend": "openai_compatible", "model": "gpt-5-codex", "ok": true, "route_provider": "openai_compatible"}, "litellm": {"backend": "litellm", "model": "litellm/ollama", "ok": true, "route_provider": "litellm"}, "nvidia_nim": {"backend": "openai_compatible", "model": "nvidia/nemotron-3-super-120b-a12b", "ok": true, "route_provider": "openai_compatible"}, "ollama": {"backend": "ollama", "model": "llama3.2:3b", "ok": true, "route_provider": "ollama"}, "openai": {"backend": "openai_compatible", "model": "gpt-4o-mini", "ok": true, "route_provider": "openai_compatible"}, "openrouter": {"backend": "litellm", "model": "litellm/openrouter/auto", "ok": true, "route_provider": "litellm"}}, "excluded_from_live_default": ["local_nim"]}`
- **agent_loop**: PASS `{"actions": [{"action": "retrieve_context", "files": ["app/kernel/provider_registry.py", "app/cli/api.py", "tests/test_provider_contracts.py"], "turn": 1}, {"action": "apply_patch", "files": ["app/kernel/provider_registry.py", "app/cli/api.py"], "turn": 2}, {"action": "run_tests", "returncode": 0, "turn": 3}], "stdout_tail": "...                                                                      [100%]\n3 passed in 0.01s\n", "turns": 3}`

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

## Live Provider Summary

| Provider | Tasks | Completed | Clean | Rescued | Completion Rate | Avg Latency ms | Avg Prompt Tokens | Tokens/Fix |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| huggingface | 6 | 4 | 4 | 0 | 66.67% | 10893.208 | 2868.5 | 4623.25 |

## Live Efficiency By Lane

| Lane | Tasks | Completed | Clean | Rescued | Canonicalized | Repaired | Completion Rate | Avg Latency ms | Tokens/Fix |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| live_huggingface_raw | 1 | 0 | 0 | 0 | 0 | 0 | 0.00% | 4242.748 | None |
| live_huggingface_schema_only | 1 | 0 | 0 | 0 | 0 | 0 | 0.00% | 4667.206 | None |
| live_huggingface_action_ir | 1 | 1 | 1 | 0 | 0 | 0 | 100.00% | 16537.691 | 4394.0 |
| live_huggingface_action_ir_resolver | 1 | 1 | 1 | 0 | 0 | 0 | 100.00% | 5783.265 | 4156.0 |
| live_huggingface_full_beast_no_scout | 1 | 1 | 1 | 0 | 0 | 0 | 100.00% | 14246.464 | 4615.0 |
| live_huggingface_full_beast | 1 | 1 | 1 | 0 | 0 | 0 | 100.00% | 19881.874 | 5328.0 |

## Live Provider Results

- `huggingface` / `provider_model_wiring` / `live_huggingface_raw`: FAIL; estimated_tokens=1020; provider_prompt_tokens=1196; latency_ms=4242.748; canonicalized=False; repair_attempted=False; changed=[]; reason=live provider failed or produced invalid scoped edit: provider output did not include operations list
- `huggingface` / `provider_model_wiring` / `live_huggingface_schema_only`: FAIL; estimated_tokens=1020; provider_prompt_tokens=1196; latency_ms=4667.206; canonicalized=False; repair_attempted=False; changed=[]; reason=live provider failed or produced invalid scoped edit: provider output did not include operations list
- `huggingface` / `provider_model_wiring` / `live_huggingface_action_ir`: PASS; estimated_tokens=3135; provider_prompt_tokens=3461; latency_ms=16537.691; canonicalized=False; repair_attempted=False; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider returned scoped operations; pytest judged completion
- `huggingface` / `provider_model_wiring` / `live_huggingface_action_ir_resolver`: PASS; estimated_tokens=3135; provider_prompt_tokens=3461; latency_ms=5783.265; canonicalized=False; repair_attempted=False; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider returned scoped operations; pytest judged completion
- `huggingface` / `provider_model_wiring` / `live_huggingface_full_beast_no_scout`: PASS; estimated_tokens=3135; provider_prompt_tokens=3461; latency_ms=14246.464; canonicalized=False; repair_attempted=False; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider returned scoped operations; pytest judged completion
- `huggingface` / `provider_model_wiring` / `live_huggingface_full_beast`: PASS; estimated_tokens=4007; provider_prompt_tokens=4436; latency_ms=19881.874; canonicalized=False; repair_attempted=False; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider returned scoped operations; pytest judged completion
