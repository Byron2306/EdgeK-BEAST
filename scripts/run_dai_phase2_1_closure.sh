#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"

EVIDENCE="evidence/dai-diode/phase2.1-stale-listener-001/x2-exact-ring"
RUN_ID="dai-phase2-1-x2-exact-ring-local-001"

sudo .venv/bin/python scripts/run_dai_phase2_x2_exact_ring_buffer.py \
  --out "$EVIDENCE" \
  --run-id "$RUN_ID"

PYTHONNOUSERSITE=1 .venv/bin/python scripts/package_dai_phase2_1_artifact.py \
  --evidence "$EVIDENCE"
