# Mascot Sprite QA

## Verdict on the previous sheet

The mascot pose itself was visually consistent, but the previous exported runtime frames were **not all production-correct**.

Observed problems:

- detached tail/body slivers in several columns
- source-cell edges included in the extracted frame
- working and alert states sat roughly 7–9 pixels above the idle baseline
- effect particles influenced automatic centring
- state transitions could therefore look like a sideways or upward jump

## Phase 1 correction

All 40 runtime frames were regenerated from the original 10-pose source using a body-anchor workflow. Effects no longer determine the anchor.

Runtime contract:

```json
{
  "canvas": [256, 256],
  "bodyAnchor": {
    "centerX": 128,
    "baselineY": 238
  },
  "frameCount": 10
}
```

Working, alert and finished effects are added after body alignment, preserving the mascot’s position.

## Review image

Open:

```text
assets/mascot/ALIGNMENT_TEST_PHASE1.png
```

The vertical and horizontal guide lines mark the common body centre and foot baseline.
