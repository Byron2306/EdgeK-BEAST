# BEAST visual proof-provider gate gauntlet — 2026-08-03T000000-visual-proof-provider-gate-a

- Receipt digest: `sha256:b2de7e18d9ac0baa50329e20eb1ca5821a705e64d4f30aa2e7e2cdc64de04d53`
- Cases: `4`
- Trusted for promotion: `1`
- Quarantined: `3`
- Prompt tamper rejected: `1`
- Wrong pixels rejected: `1`
- Stale claim blocked: `1`
- Raw text answer used in prompts: `0`
- Provider calls used: `4`
- Live provider calls used: `0`
- Failure classes: `('non_current_claim', 'prompt_proof_mismatch', 'visual_intent_failure')`

## Claim boundary

Proof-bound image-provider gate. The provider prompt is built from the canonical proof graph and visual proof primitive, not from the text answer. Provider pixels remain quarantined unless the request prompt digest, provider receipt, output digest, region boundary, visual intent, perceptual checks, and current supported proof claim all verify.

