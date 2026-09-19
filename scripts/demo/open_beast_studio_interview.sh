#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

GATEWAY="${BEAST_GATEWAY_URL:-http://127.0.0.1:8101}"
FIXTURE="${BEAST_INTERVIEW_FIXTURE:-$HOME/beast-interview-invoice-demo}"
STUDIO_PORT="${BEAST_STUDIO_PORT:-8111}"
PYTHON_BIN="${BEAST_DEMO_PYTHON:-$HOME/EdgeK-BEAST/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$ROOT/.venv/bin/python"
fi
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "BEAST Studio interview launcher: Python venv not found." >&2
  exit 2
fi

LIBPYTHON="$PREFIX/lib/libpython3.14.so"
if [[ ! -f "$LIBPYTHON" ]]; then
  echo "BEAST Studio interview launcher: missing $LIBPYTHON" >&2
  exit 4
fi

export LD_PRELOAD="$LIBPYTHON"
export PYTHONNOUSERSITE=1
export PYTHONPATH="$ROOT"

TERMUX_TMP="${TMPDIR:-$PREFIX/tmp}"
mkdir -p "$TERMUX_TMP"

echo "[BEAST] Verifying Termux Python/Rust cryptography ABI..."
if ! LD_PRELOAD="$LIBPYTHON" "$PYTHON_BIN" -c "from cryptography.hazmat.bindings._rust import Encoding; print('cryptography-rust: ready')" >/dev/null; then
  echo "BEAST Studio interview launcher: cryptography Rust binding still cannot load under libpython preload." >&2
  exit 5
fi

echo "[BEAST] Reclaiming the local interview runtime from this checkout..."
LD_PRELOAD="$LIBPYTHON" "$PYTHON_BIN" ./bin/beast heal \
  --restart-all true \
  --kill-address-pids true \
  --with-litellm false \
  --with-nginx false >"$TERMUX_TMP/beast-interview-heal.json"

echo "[BEAST] Starting browser Studio renderer on 127.0.0.1:$STUDIO_PORT..."
STUDIO_PID_FILE="$TERMUX_TMP/beast-studio-preview.pid"
STUDIO_LOG="$TERMUX_TMP/beast-studio-preview.log"
if [[ -f "$STUDIO_PID_FILE" ]]; then
  OLD_PID="$(cat "$STUDIO_PID_FILE" 2>/dev/null || true)"
  if [[ -n "$OLD_PID" ]]; then
    kill "$OLD_PID" >/dev/null 2>&1 || true
  fi
  rm -f "$STUDIO_PID_FILE"
fi

LD_PRELOAD="$LIBPYTHON" "$PYTHON_BIN" -m http.server "$STUDIO_PORT" \
  --bind 127.0.0.1 \
  --directory "$ROOT/desktop-ide/renderer" >"$STUDIO_LOG" 2>&1 &
STUDIO_PID=$!
echo "$STUDIO_PID" >"$STUDIO_PID_FILE"

for _ in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS "http://127.0.0.1:$STUDIO_PORT/index.html" >/dev/null 2>&1; then
    break
  fi
  sleep 0.3
done
curl -fsS "http://127.0.0.1:$STUDIO_PORT/index.html" >/dev/null

echo "[BEAST] Preparing fresh interview fixture..."
rm -rf "$FIXTURE"
LD_PRELOAD="$LIBPYTHON" "$PYTHON_BIN" scripts/demo/beast_interview_coding_agent.py \
  --gateway "$GATEWAY" \
  --fixture "$FIXTURE" \
  --prepare-only

STUDIO_URL="$(
  LD_PRELOAD="$LIBPYTHON" "$PYTHON_BIN" -c '
import sys, urllib.parse
fixture, gateway, port = sys.argv[1], sys.argv[2], sys.argv[3]
query = urllib.parse.urlencode({"workspace": fixture, "route": "agents", "gateway": gateway})
print(f"http://127.0.0.1:{port}/index.html?{query}")
' "$FIXTURE" "$GATEWAY" "$STUDIO_PORT"
)"

echo
echo "[BEAST] Interview workspace: $FIXTURE"
echo "[BEAST] Studio URL: $STUDIO_URL"
echo "[BEAST] Backend gateway: $GATEWAY"
echo "[BEAST] Opening browser..."

if command -v termux-open-url >/dev/null 2>&1; then
  termux-open-url "$STUDIO_URL"
elif command -v am >/dev/null 2>&1; then
  am start -a android.intent.action.VIEW -d "$STUDIO_URL" >/dev/null 2>&1 || true
else
  echo "Open this URL manually:"
  echo "$STUDIO_URL"
fi
