# BEAST Residue: Crystallized compute evidence: bounded_discount_math_repair

- Residue ID: `residue_944d0d0cab77e7cb349b`
- Created: `2026-07-22T10:10:54.449118+00:00`
- Section: `residue`
- Caller: `spiffe://beast.local/runtime-governor/crystal-evidence-bridge`
- Provider: `nvidia_nim_or_external_teacher`
- Cost saved: `191`
- Policy tags: `crystallized_compute, unified_evidence_packet, cloud_disabled_replay`

## Files touched

- none

## Decision

reuse_semantic_credit

## Evidence

```json
{
  "chronicle_written": [
    true,
    true
  ],
  "evidence_ids": [
    "ev_4c2b7a5feb47c267",
    "ev_2adeaa1d155350e4"
  ],
  "metrics": {
    "actual_reuse_count": 1,
    "cloud_calls_during_completion": 0,
    "fused_crystal_estimate": 2975,
    "reuse_observations": 1,
    "runtime_tokens_avoided": 191,
    "training_tokens_observed": 570,
    "unique_crystals": 1
  },
  "negative_case_count": 0,
  "packet_hash": "sha256:a4d7c270177a22dec50486274f424c34ef3dc38152cec6bf306f3176800d9bee",
  "runtime": {
    "cloud_used": false,
    "decision_action": "reuse_semantic_credit",
    "engine": "beast_local_semantic_cache",
    "execution_mode": "local_reuse"
  },
  "semantic_credit": {
    "confidence": 0.88,
    "credit_id": "scc_4c91f36da8e0ed25",
    "replay_type": "semantic_credit"
  },
  "task_class": "bounded_discount_math_repair",
  "teacher": {
    "cloud_used": true,
    "engine": "nvidia_nim_or_external_teacher",
    "training_cloud_calls": 3
  }
}
```
