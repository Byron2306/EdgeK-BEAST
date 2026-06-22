# Tiny Llama Live E2E Orchestration Gauntlet

Generated: `2026-06-21T21:30:41.825617+00:00`
Passed: `True`
Tiny model: `qwen2.5:0.5b`
Live score: `1.0`
Swarm run: `899ac4b9-3ee0-45fa-bbbb-2acb44fd7a16`
CLI plan hash: `sha256:8a10c12e3ba821d24ea19e86b06a5fd6bf69aa03d95aad66e338a37a7850abc7`
Promotion candidate: `commons_7182b15b46a5eb4210f0`
Receipt hash: `sha256:84aa45049b2203df9142bcce1d5024ca8b7f5ebf9f08abbaecff596727494af4`
Report hash: `sha256:876bf648e2a5dea5364701e2c0bdf12f5ba9da88b8701955e62774453d15a534`

## Assertions

| Assertion | Passed |
| --- | --- |
| `live_model_attempted` | `True` |
| `live_route_repaired_or_valid` | `True` |
| `advanced_tools_selected` | `True` |
| `subagents_selected` | `True` |
| `swarm_orchestrated_or_gated` | `True` |
| `cli_plan_ready` | `True` |
| `verification_passed` | `True` |
| `promotion_candidate_staged` | `True` |
| `no_cloud_model_used` | `True` |

## Normalized Route

```json
{
  "gates": [
    "no_cloud_until_local_evidence",
    "approval_before_write",
    "verification_gate",
    "receipt_required"
  ],
  "needs_cloud": false,
  "objective": "Diagnose whether tiny Llama can use BEAST awareness, Commons, Swarm, OpenClaw-style planning, verification, and promotion without a cloud model.",
  "promote": false,
  "required_gates": [
    "no_cloud_until_local_evidence",
    "approval_before_write",
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
    "pytest",
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
  "risk": "medium",
  "route": [
    "meta_tool_commons",
    "capability_registry",
    "fused_crystal",
    "zeroclaw",
    "openclaw",
    "swarm",
    "pytest",
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
  "task_class": "agentic_cli",
  "task_id": "agent_awareness_e2e_debug_and_promote",
  "tier": 6,
  "tier_name": "live_chained_subsystem_orchestration",
  "verify": [
    "verification_receipt"
  ]
}
```

## Boundary

This proves a tiny model can drive an end-to-end BEAST orchestration scaffold when schema repair, subagents, tools, verification, and promotion are externalized. It does not prove the base model has frontier reasoning weights.
