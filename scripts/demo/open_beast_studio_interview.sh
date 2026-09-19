#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

GATEWAY="${BEAST_GATEWAY_URL:-http://127.0.0.1:8101}"
FIXTURE="${BEAST_INTERVIEW_FIXTURE:-$HOME/beast-interview-invoice-demo}"
STUDIO_PORT="${BEAST_STUDIO_PORT:-}"
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

STUDIO_ROOT="$ROOT/desktop-ide/renderer"
STUDIO_INDEX="$STUDIO_ROOT/index.html"
if [[ ! -f "$STUDIO_INDEX" ]]; then
  echo "BEAST Studio interview launcher: missing renderer index: $STUDIO_INDEX" >&2
  exit 6
fi

if [[ -z "$STUDIO_PORT" ]]; then
  STUDIO_PORT="$(
    LD_PRELOAD="$LIBPYTHON" "$PYTHON_BIN" -c '
import socket
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    print(s.getsockname()[1])
'
  )"
fi

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

: >"$STUDIO_LOG"
LD_PRELOAD="$LIBPYTHON" "$PYTHON_BIN" -m http.server "$STUDIO_PORT" \
  --bind 127.0.0.1 \
  --directory "$STUDIO_ROOT" >"$STUDIO_LOG" 2>&1 &
STUDIO_PID=$!
echo "$STUDIO_PID" >"$STUDIO_PID_FILE"

STUDIO_READY=false
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  if ! kill -0 "$STUDIO_PID" >/dev/null 2>&1; then
    break
  fi
  if curl -fsS "http://127.0.0.1:$STUDIO_PORT/index.html" >/dev/null 2>&1; then
    STUDIO_READY=true
    break
  fi
  sleep 0.25
done

if [[ "$STUDIO_READY" != "true" ]]; then
  echo "BEAST Studio interview launcher: renderer did not become ready." >&2
  echo "Renderer root: $STUDIO_ROOT" >&2
  echo "Renderer port: $STUDIO_PORT" >&2
  echo "Server log:" >&2
  tail -40 "$STUDIO_LOG" >&2 || true
  exit 7
fi

echo "[BEAST] Browser Studio renderer ready."

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
query = urllib.parse.urlencode({"workspace": fixture, "page": "agents", "gateway": gateway})
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
