#!/usr/bin/env bash
# Start the BEAST gateway with every local capability enabled.
#
#   bash scripts/start_beast_stack.sh              # gateway on 8200 (dev, no production restart)
#   BEAST_PORT=8080 bash scripts/start_beast_stack.sh
#   BEAST_STACK_PYTHON=/path/to/python bash scripts/start_beast_stack.sh
#
# A dedicated development port is the default on purpose: the production
# gateways on 8101/8080/8199 are left alone unless you explicitly override
# BEAST_PORT.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${BEAST_PORT:-8200}"
PYTHON="${BEAST_STACK_PYTHON:-$REPO/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  for candidate in /home/byron/dio-audit-evidence-20261027/venv/bin/python python3; do
    if command -v "$candidate" >/dev/null 2>&1; then PYTHON="$candidate"; break; fi
  done
fi

export BEAST_ENABLE_LOCAL_EMBEDDINGS=1
export BEAST_VECTOR_MEMORY_LOCAL_PROJECTION_ENABLED=1
export BEAST_VECTOR_DIMENSIONS=384
export BEAST_LANCEDB_URI="${BEAST_LANCEDB_URI:-$REPO/.beast/lancedb}"
export BEAST_CONSOLIDATED_CRYSTAL_BUS=1
export BEAST_FAMILY_CRYSTALS=1
export BEAST_CODING_CRYSTALS=1
export BEAST_ZERO_COPY_KV=1
export BEAST_SWARM_SPECIALIST=1
export BEAST_COMPRESSION_TIERS=1
export BEAST_QUALITY_CASCADE=1
export BEAST_CDP_ENABLED=1
export BEAST_GPU_SCHEDULER=1
export BEAST_KV_CRYSTAL_TTL_SECONDS="${BEAST_KV_CRYSTAL_TTL_SECONDS:-86400}"

# Automatically load provider secrets (NVIDIA_API_KEY, etc.) for NIM planner routing
SECRETS_FILE="$REPO/.beast/provider_secrets.env"
if [[ -f "$SECRETS_FILE" ]]; then
  set -a
  . "$SECRETS_FILE"
  set +a
  echo "secrets: loaded $SECRETS_FILE"
fi

echo "repo:   $REPO"
echo "python: $PYTHON"
echo "port:   $PORT"
echo "log:    ${BEAST_STACK_LOG:-/tmp/opencode/gateway-$PORT.log}"
cd "$REPO"
exec "$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" \
  >> "${BEAST_STACK_LOG:-/tmp/opencode/gateway-$PORT.log}" 2>&1
