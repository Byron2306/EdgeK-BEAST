#!/usr/bin/env bash
# Loopback-only proof gateway. Existing provider and authority settings are inherited.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

export BEAST_COMPRESSION_TIERS=1
export BEAST_ZERO_COPY_KV=1
export BEAST_CODING_CRYSTALS=1
export BEAST_SWARM_SPECIALIST=1
export BEAST_QUALITY_CASCADE=1
export BEAST_NIM_PLANNER_STREAM=1
export BEAST_CONSOLIDATED_CRYSTAL_BUS=1
# Bus eligibility does not admit a capsule or grant promotion authority.
if [[ -z "${BEAST_STATE_ROOT:-}" ]]; then
  export BEAST_STATE_ROOT="$(mktemp -d -t beast-coder-learning.XXXXXX)"
fi
# Keep provider attempts and circuit state separate from the normal gateway.
export BEAST_RUNTIME_GOVERNOR_DB="$BEAST_STATE_ROOT/runtime-governor.db"
printf 'BEAST learning gateway state: %s\n' "$BEAST_STATE_ROOT" >&2
exec "${BEAST_PROOF_PYTHON:-.venv/bin/python}" -m uvicorn app.main:app \
  --host 127.0.0.1 --port "${BEAST_PROOF_PORT:-8199}"
