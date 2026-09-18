#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
NATIVE_WORKSPACE="$ROOT"
DISPLAY_ID="${BEAST_TERMUX_X11_DISPLAY:-:1}"

if [[ -z "${PREFIX:-}" || "${PREFIX}" != *"com.termux"* ]]; then
  echo "REFUSE: run this launcher from native Termux." >&2
  exit 2
fi

if ! curl -fsS http://127.0.0.1:8101/edgek/control-plane/desktop-compatibility >/dev/null; then
  echo "[BEAST] Native gateway is not ready; starting it first..."
  "$ROOT/bin/beast" termux-up >/dev/null
fi

if ! pgrep -f "termux-x11 ${DISPLAY_ID}" >/dev/null 2>&1; then
  echo "[BEAST] Starting Termux:X11 on ${DISPLAY_ID}..."
  termux-x11 "$DISPLAY_ID" >/tmp/beast-termux-x11.log 2>&1 &
  sleep 2
fi

# Bring the Android X11 activity to the foreground when the installed
# Termux:X11 app exposes the standard activity.
am start --user 0 -n com.termux.x11/com.termux.x11.MainActivity >/dev/null 2>&1 || true

echo "[BEAST] Launching Electron shell in Debian proot against native backend..."
proot-distro login debian \
  --shared-tmp \
  --bind "$NATIVE_WORKSPACE:$NATIVE_WORKSPACE" \
  --bind "$NATIVE_WORKSPACE:/mnt/beast-source" \
  --env DISPLAY="$DISPLAY_ID" \
  -- bash -lc "
set -e
export DISPLAY='$DISPLAY_ID'
export BEAST_DESKTOP_GATEWAY='http://127.0.0.1:8101'
export BEAST_ALLOW_GATEWAY_OVERRIDE='1'
export BEAST_WORKSPACE='$NATIVE_WORKSPACE'
export BEAST_ACTIVE_WORKSPACE='$NATIVE_WORKSPACE'
export BEAST_CONTEXT_WORKSPACE='$NATIVE_WORKSPACE'
export BEAST_ELECTRON_SANDBOX='0'

# Refresh the glibc desktop copy from the native checkout while preserving its
# Debian node_modules. Never share native Termux/Bionic node_modules here.
rsync -a --delete \
  --exclude .git \
  --exclude .venv \
  --exclude venv \
  --exclude node_modules \
  --exclude .beast \
  --exclude deploy/run \
  /mnt/beast-source/ /root/EdgeK-BEAST-desktop/

if ! pgrep -x openbox >/dev/null 2>&1; then
  openbox >/tmp/beast-openbox.log 2>&1 &
fi
cd /root/EdgeK-BEAST-desktop/desktop-ide
npm start
"
