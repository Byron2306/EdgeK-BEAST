# BEAST Residue: Crystallized inference for bounded_discount_math_repair

- Residue ID: `residue_332ffc170bffa0b38b69`
- Created: `2026-07-22T10:10:53.554904+00:00`
- Section: `residue`
- Caller: `spiffe://beast.local/runtime-governor`
- Provider: `nvidia_nim`
- Cost saved: `{'avoided_tokens_estimate': 189}`
- Policy tags: `crystal_reuse, provider_response`

## Files touched

- none

## Decision

Stored provider response as reusable BEAST crystal.

## Evidence

```json
{
  "answer_credit_id": "cache_527406ff31a943ea",
  "latency_ms": 1201.0,
  "local_eval_gate": {
    "beast_object_type": "local_eval_gate_result",
    "checks": [
      {
        "passed": true,
        "rule": {
          "type": "must_contain",
          "value": "CRYSTAL_CODE_RECIPE"
        }
      },
      {
        "passed": true,
        "rule": {
          "type": "must_contain",
          "value": "python_ast_function_rewriter"
        }
      },
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
  "local_eval_rules": [
    {
      "type": "must_contain",
      "value": "CRYSTAL_CODE_RECIPE"
    },
    {
      "type": "must_contain",
      "value": "python_ast_function_rewriter"
    }
  ],
  "provider_result_id": "code_repair_cloud_result_1",
  "requested_verified": true,
  "runtime_engine": "beast_local_semantic_cache",
  "semantic_credit_id": "scc_4c91f36da8e0ed25",
  "teacher_engine": "nvidia_nim_or_external_teacher",
  "usage": {
    "total_tokens": 189
  },
  "verification": "code_recipe_passed_hidden_and_visible_tests",
  "verified": true
}
```
