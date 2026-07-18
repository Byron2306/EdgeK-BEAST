# Inference Compute Governor

The Inference Compute Governor asks one question before every provider call:

> What unresolved semantic work still requires probabilistic computation?

Phase 1 runs in **shadow mode**. It records plans, recommendations, and receipts,
but it does not suppress calls, change providers, alter token limits, or stop
generation.

## Position In The BEAST Cycle

```text
Task Envelope
  -> Provider Handoff / Context Packet
  -> Compute Governor
       |- reuse verified capability
       |- deterministic transform
       |- local inference
       |- cloud inference
       |- escalate
       |- suppress only with proof
       `- require approval
  -> Output Governance
  -> Verifier / Hidden Tests / Chronicle
  -> Capability Promotion + Impact Fingerprint
  `-> future verified reuse
```

Verified outcomes become capabilities. Capabilities receive Impact Fingerprints.
Valid fingerprints permit safe reuse, reuse displaces future inference, and
repository drift sends the capability back to shadow validation.

## Artifacts

### Compute Plan

A plan records task class, provider and model, message and character counts,
estimated input/output tokens, deterministic candidates, reuse candidates,
budgets, and the escalation ladder. Request content is represented only by
SHA-256 fingerprints; prompts and source code are not persisted.

### Compute Gate

The Phase 1 gate always selects the existing provider path and sets:

```json
{
  "mode": "shadow",
  "allowed": true,
  "enforced": false,
  "selected_rung": "selected_provider"
}
```

It may recommend a different rung for later analysis, but that recommendation
cannot affect execution.

The gate records one of seven candidate outcomes: `reuse`, `deterministic`,
`local_inference`, `cloud_inference`, `escalate`, `suppress`, or
`require_approval`. When confidence is ambiguous, its recommendation is always
`escalate`, never `suppress`. Phase 1 still executes the selected provider path.

### Compute Receipt

The receipt links the plan and gate to the runtime attempt. It records provider,
model, status, observed tokens, latency, first-party cost when available, and a
counterfactual estimate of avoidable work.

Counterfactual estimates are hypotheses. They become measured savings only
after a behavior-preserving ablation demonstrates equal or better verification.

Receipts include `avoided_tokens_estimate`. `predicted_savings_usd` is populated
only when the provider response includes first-party cost data; BEAST does not
manufacture dollar estimates from incomplete pricing evidence.

For xAI responses, `cost_in_usd_ticks` is converted using the provider-defined
rate of `10^10` ticks per USD. The raw provider field remains first-party billing
evidence; only the avoided fraction is counterfactual.

`false_suppression_rate` is a red-line metric. Any false suppression sets
`enforcement_pause_required=true`; compute enforcement must not resume until the
incident is understood and the relevant policy is revalidated.

## Phase 1 Evidence

The deterministic preflight preserved behavior across 120 paired attempts. The
live xAI observation verified 24 tasks across 24 task classes, recorded 25/25
provider-attempt receipts, observed 232,081 tokens, achieved 100% first-party
cost coverage, and enforced zero suppressions. Its 33,017 avoidable-token and
$0.052213896 savings values remain counterfactual pending paired displacement
calibration.

See [the deterministic preflight](../benchmarks/results/compute_governor_phase1_closure.md)
and [the xAI live observation](../benchmarks/results/compute_governor_phase1_xai_live.md).

## API

- `GET /edgek/compute`
- `GET /edgek/compute/metrics`
- `GET /edgek/compute/savings-summary`
- `GET /edgek/compute/plans`
- `GET /edgek/compute/receipts`
- `GET /edgek/compute/receipts/{receipt_id}`
- MCP: `beast_compute_shadow`

## Rollout Gates

Phase 2 deterministic displacement should remain disabled until shadow evidence
shows that candidate work can be removed without reducing visible-test,
hidden-test, safety, rollback, or scope performance.

Promoted capabilities use target, dependency, test, AST, symbol, tool-schema,
and policy hashes to detect repository drift. Material drift returns a capability
to shadow revalidation instead of allowing stale deterministic reuse.

See the [phased rollout and safety contract](compute-governor-roadmap.md).
