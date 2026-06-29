# BEAST Residue: Crystallized inference for retry_after_parser_repair

- Residue ID: `residue_32eabd7c4c371419801e`
- Created: `2026-06-29T04:24:17.946696+00:00`
- Section: `residue`
- Caller: `spiffe://beast.local/runtime-governor`
- Provider: `ollama`
- Cost saved: `{'avoided_tokens_estimate': 259}`
- Policy tags: `crystal_reuse, provider_response`

## Files touched

- none

## Decision

Stored provider response as reusable BEAST crystal.

## Evidence

```json
{
  "actual_live_provider_call": true,
  "answer_credit_id": "cache_68ecf22589ab96ef",
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
  "raw_response_sha256": "sha256:4efa25ad2cd8cf99802b90890e116c2dbd60138871682d92a66adc028e1649be",
  "requested_verified": true,
  "semantic_credit_id": "scc_6b6bed222104b438",
  "skill_contract": "pytest_behavior_verifier",
  "tool_contract": "python_ast_function_rewriter",
  "verification": "hard_coding_training_recipe_normalized_and_verified",
  "verified": true
}
```
