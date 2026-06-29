# Tiny Llama Opus/Codex-style Case Study

Generated: `2026-06-24T17:35:44.589328+00:00`
Passed: `False`
Tiny model: `qwen2.5:0.5b`
Live score: `0.085`
Baseline failed: `True`
Verification passed: `True`
Approval receipt: `sha256:f2e347861b83d716e91a96a3f5243a767d56a3d067ffef89ca3d01df8d1aa2e6`
Patch hash: `sha256:eb105df6f507255d901c7a34bcf596158d9ee600d73f59c699c7c39bf7882e5c`
Promotion candidate: `commons_5152c0252c4852c3184b`
Receipt hash: `sha256:c53a5bab6149813095d549a3fe3ee82f8ccbb5ba2a174efbb12bc9ddaa185cfb`
Report hash: `sha256:8cb1d9f635473943f6c45cb3d5ec78d13b8c49628441449090db06f353e85d03`

## Assertions

| Assertion | Passed |
| --- | --- |
| `baseline_failed` | `True` |
| `live_model_attempted` | `False` |
| `live_route_repaired_or_valid` | `False` |
| `live_selected_advanced_tools` | `False` |
| `gated_before_approval` | `True` |
| `approval_receipt_present` | `True` |
| `patch_applied_after_approval` | `True` |
| `verification_passed_after_patch` | `True` |
| `approved_swarm_completed` | `True` |
| `promotion_candidate_staged` | `True` |
| `no_cloud_model_used` | `True` |

## Normalized Orchestration Plan

```json
{
  "needs_cloud": false,
  "promote": false,
  "verify": []
}
```

## Boundary

This case study shows a tiny local model can initiate a hard approved agentic repair when BEAST supplies orchestration, gates, deterministic patching, verification, receipts, and promotion. It does not claim the tiny model independently solved the code repair like a frontier model.
