# Tiny Llama Opus/Codex-style Case Study

Generated: `2026-06-24T18:13:42.799772+00:00`
Passed: `False`
Tiny model: `qwen2.5:0.5b`
Live score: `0.085`
Baseline failed: `True`
Verification passed: `True`
Approval receipt: `sha256:a67e6c6ee9a0a9569e481ce70d7272ae9956e0c2e10f920aa22ab7479165e90c`
Patch hash: `sha256:eb105df6f507255d901c7a34bcf596158d9ee600d73f59c699c7c39bf7882e5c`
Promotion candidate: `commons_5152c0252c4852c3184b`
Receipt hash: `sha256:59e1be1fec97f61b21388a6cfe040fe9e66a49d235dbafc2e11e04aec6d7082a`
Report hash: `sha256:61fd38800faafe1574870f4a7d98cd197bcef3bc2a3e702607cfb8629c182723`

## Assertions

| Assertion | Passed |
| --- | --- |
| `baseline_failed` | `True` |
| `live_model_attempted` | `False` |
| `live_route_repaired_or_valid` | `False` |
| `live_selected_advanced_tools` | `False` |
| `gated_before_approval` | `False` |
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
