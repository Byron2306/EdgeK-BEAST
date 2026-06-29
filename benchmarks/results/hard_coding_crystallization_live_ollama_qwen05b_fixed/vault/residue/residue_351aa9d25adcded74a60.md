# BEAST Residue: Crystallized inference for ttl_lru_cache_repair

- Residue ID: `residue_351aa9d25adcded74a60`
- Created: `2026-06-29T03:54:46.511794+00:00`
- Section: `residue`
- Caller: `spiffe://beast.local/runtime-governor`
- Provider: `ollama`
- Cost saved: `{'avoided_tokens_estimate': 139}`
- Policy tags: `crystal_reuse, provider_response`

## Files touched

- none

## Decision

Stored provider response as reusable BEAST crystal.

## Evidence

```json
{
  "actual_live_provider_call": true,
  "answer_credit_id": "cache_4b65d103f0493c38",
  "local_eval_gate": {
    "beast_object_type": "local_eval_gate_result",
    "checks": [
      {
        "passed": true,
        "rule": {
          "type": "max_length",
          "value": 200000
        }
      },
      {
        "passed": true,
        "rule": {
          "type": "no_secret_patterns"
        }
      }
    ],
    "passed": true,
    "promotion_allowed": true,
    "version": "1.0"
  },
  "raw_response_sha256": "sha256:c20591f8c1c003dc23cc3276486fc61ddc5134f93fe4053482a71e6c90a48feb",
  "requested_verified": true,
  "semantic_credit_id": "scc_45b89a64680a015e",
  "skill_contract": "pytest_behavior_verifier",
  "tool_contract": "python_ast_function_rewriter",
  "verification": "hard_coding_training_recipe_normalized_and_verified",
  "verified": true
}
```
