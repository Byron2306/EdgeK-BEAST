#!/usr/bin/env bash
# Launch the Electron IDE against a gateway running the current source.
#
#   bash scripts/start_beast_ide.sh                 # IDE + dev gateway on 8200
#   BEAST_PORT=8080 bash scripts/start_beast_ide.sh # IDE against an existing gateway
#   BEAST_IDE_AUDIT=1 bash scripts/start_beast_ide.sh  # headless-ish visual audit instead
#
# The production gateways are not restarted.  If nothing is listening on
# BEAST_PORT, the dev gateway is started for you with all local features on.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${BEAST_PORT:-8200}"
GATEWAY="http://127.0.0.1:$PORT"

# Automatically load provider secrets (NVIDIA_API_KEY, etc.) for NIM planner routing
SECRETS_FILE="$REPO/.beast/provider_secrets.env"
if [[ -f "$SECRETS_FILE" ]]; then
  set -a
  . "$SECRETS_FILE"
  set +a
  echo "secrets: loaded $SECRETS_FILE"
fi

if ! curl -sf --max-time 3 "$GATEWAY/edgek/physical/ledger" >/dev/null 2>&1; then
  echo "starting dev gateway on $PORT …"
  mkdir -p /tmp/opencode
  nohup bash "$REPO/scripts/start_beast_stack.sh" >/tmp/opencode/stack-$PORT.out 2>&1 &
  for _ in $(seq 1 40); do
    sleep 2
    curl -sf --max-time 3 "$GATEWAY/edgek/physical/ledger" >/dev/null 2>&1 && break
  done
fi

export BEAST_DESKTOP_GATEWAY="$GATEWAY"
export BEAST_ALLOW_GATEWAY_OVERRIDE=1
export BEAST_CDP_ENABLED="${BEAST_CDP_ENABLED:-1}"

cd "$REPO/desktop-ide"
if [[ "${BEAST_IDE_AUDIT:-0}" == "1" ]]; then
  export BEAST_VISUAL_GATEWAY="$GATEWAY"
  export BEAST_VISUAL_PAGES="${BEAST_VISUAL_PAGES:-physical-plane,terminal}"
  export BEAST_VISUAL_EXERCISE="${BEAST_VISUAL_EXERCISE:-1}"
  exec npm run visual:audit
fi
exec npm start
