# BEAST Residue: Crystallized inference for money_csv_parser_repair

- Residue ID: `residue_0fa7df48bf51e8f1fee8`
- Created: `2026-06-29T04:23:56.253826+00:00`
- Section: `residue`
- Caller: `spiffe://beast.local/runtime-governor`
- Provider: `ollama`
- Cost saved: `{'avoided_tokens_estimate': 125}`
- Policy tags: `crystal_reuse, provider_response`

## Files touched

- none

## Decision

Stored provider response as reusable BEAST crystal.

## Evidence

```json
{
  "actual_live_provider_call": true,
  "answer_credit_id": "cache_3d6e3bc46d5444d1",
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
  "raw_response_sha256": "sha256:5abf47958b1dd73a6265f27510e84d86c69bc49c61bb21f68e82c691218e87e1",
  "requested_verified": true,
  "semantic_credit_id": "scc_e3737776cfefd8b6",
  "skill_contract": "pytest_behavior_verifier",
  "tool_contract": "python_ast_function_rewriter",
  "verification": "hard_coding_training_recipe_normalized_and_verified",
  "verified": true
}
```
