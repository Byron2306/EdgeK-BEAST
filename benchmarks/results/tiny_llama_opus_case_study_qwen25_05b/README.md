# Tiny Llama Opus/Codex-style Case Study

Generated: `2026-06-21T21:37:35.084043+00:00`
Passed: `True`
Tiny model: `qwen2.5:0.5b`
Live score: `0.955`
Baseline failed: `True`
Verification passed: `True`
Approval receipt: `sha256:f1722dc19ecad7892cd531e184ff06baf7e8f2647608583cbddb70031244b3f4`
Patch hash: `sha256:eb105df6f507255d901c7a34bcf596158d9ee600d73f59c699c7c39bf7882e5c`
Promotion candidate: `commons_1dad4a28ddcabeb71beb`
Receipt hash: `sha256:2d26f1432ff3ad6eb7fb363a03236f7aa9762f7fe6ca4c271c934f219d3521de`
Report hash: `sha256:1f15ffa24deb9e5707768c309b4f29003ee4ae6296d701353b94d1d99f61ea49`

## Assertions

| Assertion | Passed |
| --- | --- |
| `baseline_failed` | `True` |
| `live_model_attempted` | `True` |
| `live_route_repaired_or_valid` | `True` |
| `live_selected_advanced_tools` | `True` |
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
  "gates": [
    "no_cloud_until_local_evidence",
    "approval_before_write",
    "rollback_plan",
    "secret_redaction_gate",
    "verification_gate",
    "receipt_required"
  ],
  "needs_cloud": false,
  "objective": "Repair an isolated provider gateway package",
  "promote": false,
  "required_gates": [
    "no_cloud_until_local_evidence",
    "approval_before_write",
    "rollback_plan",
    "secret_redaction_gate",
    "verification_gate",
    "receipt_required"
  ],
  "required_route": [
    "meta_tool_commons",
    "capability_registry",
    "fused_crystal",
    "zeroclaw",
    "openclaw",
    "swarm",
    "mcp_git_status_diff",
    "pytest",
    "approval_gate",
    "promotion_candidate"
  ],
  "required_subagents": [
    "zeroclaw_planner",
    "cartographer",
    "openclaw_inspector",
    "supervisor",
    "scribe",
    "promotion_scribe"
  ],
  "risk": "high",
  "route": [
    "meta_tool_commons",
    "capability_registry",
    "fused_crystal",
    "zeroclaw",
    "openclaw",
    "swarm",
    "mcp_git_status_diff",
    "pytest",
    "approval_gate",
    "promotion_candidate"
  ],
  "subagents": [
    "zeroclaw_planner",
    "cartographer",
    "openclaw_inspector",
    "supervisor",
    "scribe",
    "promotion_scribe"
  ],
  "task_class": "hard_gateway_repair",
  "task_id": "opus_case_gateway_repair",
  "tier": 7,
  "tier_name": "approved_multifile_patch_verify_promote",
  "verify": [
    "verification_receipt"
  ]
}
```

## Boundary

This case study shows a tiny local model can initiate a hard approved agentic repair when BEAST supplies orchestration, gates, deterministic patching, verification, receipts, and promotion. It does not claim the tiny model independently solved the code repair like a frontier model.
