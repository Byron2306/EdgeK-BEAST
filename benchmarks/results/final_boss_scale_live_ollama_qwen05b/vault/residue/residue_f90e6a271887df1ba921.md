# BEAST Residue: Crystallized inference for gateway_provider_hardening

- Residue ID: `residue_f90e6a271887df1ba921`
- Created: `2026-06-29T04:09:24.954912+00:00`
- Section: `residue`
- Caller: `spiffe://beast.local/runtime-governor`
- Provider: `ollama`
- Cost saved: `{'avoided_tokens_estimate': 143}`
- Policy tags: `crystal_reuse, provider_response`

## Files touched

- none

## Decision

Stored provider response as reusable BEAST crystal.

## Evidence

```json
{
  "actual_live_provider_call": true,
  "answer_credit_id": "cache_501ad904cfd351c2",
  "files_changed": [
    "gateway/providers.py",
    "gateway/auth.py",
    "gateway/streaming.py",
    "gateway/client.py"
  ],
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
  "raw_response_sha256": "sha256:1504239820020eeb6f706b6211d07368b59db8ef58ff91e7abf3a63f21dd310e",
  "requested_verified": true,
  "semantic_credit_id": "scc_d194914b8bf17507",
  "skill_contract": "gateway_integration_pytest",
  "tool_contract": "approved_multifile_patch_tool",
  "verification": "multi_file_patch_plan_verified_by_integration_tests",
  "verified": true
}
```
