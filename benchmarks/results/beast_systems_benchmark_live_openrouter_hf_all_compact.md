# BEAST Systems Coding-Agent Benchmark

Generated: `2026-06-17T10:49:30Z`

BEAST efficiency is supported when scoped BEAST lanes complete more verified tasks with fewer prompt tokens, and subsystem probes show compression, RAG, interception, tool laziness, MCP governance, provider contracts, and agent-loop verification working.

Local NIM live status: excluded: local NIM requires a local GPU/Jetson container for this run

## Ablation Summary

| Lane | Tasks | Completed | Completion Rate | Median Prompt Tokens | Reduction vs Raw |
| --- | ---: | ---: | ---: | ---: | ---: |
| raw | 3 | 0 | 0.00% | 47725 | 0.00% |
| context_only | 3 | 0 | 0.00% | 41 | 99.91% |
| rag | 3 | 2 | 66.67% | 314 | 99.34% |
| rag_tools | 3 | 3 | 100.00% | 343 | 99.28% |
| full_beast | 3 | 3 | 100.00% | 403 | 99.16% |

## Subsystem Probes

- **compression_and_economizer**: PASS `{"economizer_changed": true, "economizer_final_tokens": 25, "economizer_original_tokens": 54455, "json_reduction_percent": 96.5896, "python_reduction_percent": 93.0394}`
- **rag_vector_retrieval**: PASS `{"indexed_chunks": 87, "indexed_files": 14, "retrieval_mode": "lexical_bm25_fallback", "semantic_available": false, "top_files": ["tests/test_provider_contracts.py", "tests/test_provider_contracts.py", "app/cli/api.py", "app/kernel/provider_registry.py", "app/kernel/provider_registry.py"]}`
- **tool_interception**: PASS `{"backend": "basic_semantic_grep", "bytes_returned": 349, "raw_bytes": 3536, "reduction_percent": 90.1301}`
- **tool_laziness**: PASS `{"critical_decision": {"average_cost_usd": 0.01, "average_latency_ms": 1383.3333333333333, "average_tokens_spent": 940.0, "average_value_score": 0.3333, "calls": 3, "decision": "call", "expected_value_score": 0.3333, "max_success_value_score": 1.0, "reason": "rare critical success observed", "samples": 3, "scenario": "rare_critical_lookup", "tool_name": "provider_call", "total_cost_usd": 0.03, "total_tokens_spent": 2820, "useful": 1, "usefulness_rate": 0.3333}, "redundant_decision": {"average_cost_usd": 0.01, "average_latency_ms": 1400.0, "average_tokens_spent": 1000.0, "average_value_score": 0.0, "calls": 5, "decision": "skip", "estimated_avoidance": {"cost_usd": 0.01, "latency_ms": 1400.0, "tokens": 1000.0}, "expected_value_score": 0.0, "max_success_value_score": 0.0, "reason": "low learned usefulness", "samples": 5, "scenario": "redundant_context_lookup", "tool_name": "provider_call",`
- **mcp_governance**: PASS `{"dangerous_shell_decision": "deny", "read_decision": "allow", "safe_shell_decision": "require_approval", "token_compressor_decision": "allow"}`
- **vector_adapter_inventory**: PASS `{"active_adapter": "sqlite_local_embeddings", "adapter_count": 5, "rules": ["lexical_fallback_must_work_without_embeddings", "metadata_filters_before_scoring", "dense_vectors_optional", "append_only_truth_before_retrieval_views"]}`
- **provider_contracts**: PASS `{"checked_providers": {"codex": {"backend": "openai_compatible", "model": "gpt-5-codex", "ok": true, "route_provider": "openai_compatible"}, "litellm": {"backend": "litellm", "model": "litellm/ollama", "ok": true, "route_provider": "litellm"}, "nvidia_nim": {"backend": "openai_compatible", "model": "meta/llama-3.1-70b-instruct", "ok": true, "route_provider": "openai_compatible"}, "ollama": {"backend": "ollama", "model": "llama3.2:3b", "ok": true, "route_provider": "ollama"}, "openai": {"backend": "openai_compatible", "model": "gpt-4o-mini", "ok": true, "route_provider": "openai_compatible"}, "openrouter": {"backend": "litellm", "model": "litellm/openrouter/auto", "ok": true, "route_provider": "litellm"}}, "excluded_from_live_default": ["local_nim"]}`
- **agent_loop**: PASS `{"actions": [{"action": "retrieve_context", "files": ["app/kernel/provider_registry.py", "app/cli/api.py", "tests/test_provider_contracts.py"], "turn": 1}, {"action": "apply_patch", "files": ["app/kernel/provider_registry.py", "app/cli/api.py"], "turn": 2}, {"action": "run_tests", "returncode": 0, "turn": 3}], "stdout_tail": "...                                                                      [100%]\n3 passed in 0.01s\n", "turns": 3}`

## Verified Task Results

- `provider_model_wiring` / `raw`: FAIL; tokens=48309; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `provider_model_wiring` / `context_only`: FAIL; tokens=48; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `provider_model_wiring` / `rag`: FAIL; tokens=909; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `provider_model_wiring` / `rag_tools`: PASS; tokens=946; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=lane had enough scoped context to apply known-good patch
- `provider_model_wiring` / `full_beast`: PASS; tokens=1143; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=lane had enough scoped context to apply known-good patch
- `config_validation_edge_case` / `raw`: FAIL; tokens=47725; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `config_validation_edge_case` / `context_only`: FAIL; tokens=38; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `config_validation_edge_case` / `rag`: PASS; tokens=314; changed=['app/config.py']; reason=lane had enough scoped context to apply known-good patch
- `config_validation_edge_case` / `rag_tools`: PASS; tokens=343; changed=['app/config.py']; reason=lane had enough scoped context to apply known-good patch
- `config_validation_edge_case` / `full_beast`: PASS; tokens=403; changed=['app/config.py']; reason=lane had enough scoped context to apply known-good patch
- `provider_id_parser` / `raw`: FAIL; tokens=47706; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `provider_id_parser` / `context_only`: FAIL; tokens=41; changed=[]; reason=lane lacked enough scoped evidence or exceeded useful raw-context budget
- `provider_id_parser` / `rag`: PASS; tokens=299; changed=['app/provider_parser.py']; reason=lane had enough scoped context to apply known-good patch
- `provider_id_parser` / `rag_tools`: PASS; tokens=330; changed=['app/provider_parser.py']; reason=lane had enough scoped context to apply known-good patch
- `provider_id_parser` / `full_beast`: PASS; tokens=399; changed=['app/provider_parser.py']; reason=lane had enough scoped context to apply known-good patch

## Live Provider Summary

| Provider | Tasks | Completed | Completion Rate | Avg Latency ms | Avg Provider Prompt Tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| openrouter | 3 | 1 | 33.33% | 3271.95 | 1571.333 |
| huggingface | 3 | 3 | 100.00% | 1532.956 | 1439.0 |

## Live Provider Results

- `openrouter` / `provider_model_wiring` / `live_openrouter_full_beast`: PASS; estimated_tokens=2275; provider_prompt_tokens=2774; latency_ms=4305.793; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter` / `config_validation_edge_case` / `live_openrouter_full_beast`: FAIL; estimated_tokens=818; provider_prompt_tokens=980; latency_ms=3137.841; changed=['app/config.py']; reason=live provider returned scoped operations; pytest judged completion
- `openrouter` / `provider_id_parser` / `live_openrouter_full_beast`: FAIL; estimated_tokens=800; provider_prompt_tokens=960; latency_ms=2372.217; changed=['app/provider_parser.py']; reason=live provider returned scoped operations; pytest judged completion
- `huggingface` / `provider_model_wiring` / `live_huggingface_full_beast`: PASS; estimated_tokens=2275; provider_prompt_tokens=2515; latency_ms=1468.777; changed=['app/cli/api.py', 'app/kernel/provider_registry.py']; reason=live provider returned scoped operations; pytest judged completion
- `huggingface` / `config_validation_edge_case` / `live_huggingface_full_beast`: PASS; estimated_tokens=818; provider_prompt_tokens=913; latency_ms=889.349; changed=['app/config.py']; reason=live provider returned scoped operations; pytest judged completion
- `huggingface` / `provider_id_parser` / `live_huggingface_full_beast`: PASS; estimated_tokens=800; provider_prompt_tokens=889; latency_ms=2240.742; changed=['app/provider_parser.py']; reason=live provider returned scoped operations; pytest judged completion
