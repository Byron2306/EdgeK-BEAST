#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

GATEWAY="${BEAST_GATEWAY_URL:-http://127.0.0.1:8101}"
FIXTURE="${BEAST_INTERVIEW_FIXTURE:-$HOME/beast-interview-invoice-demo}"
PYTHON_BIN="${BEAST_DEMO_PYTHON:-$HOME/EdgeK-BEAST/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$ROOT/.venv/bin/python"
fi
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "BEAST Studio interview launcher: Python venv not found." >&2
  exit 2
fi

export LD_PRELOAD="${LD_PRELOAD:-$PREFIX/lib/libpython3.14.so}"
export PYTHONNOUSERSITE=1
export PYTHONPATH="$ROOT"

TERMUX_TMP="${TMPDIR:-$PREFIX/tmp}"
mkdir -p "$TERMUX_TMP"

echo "[BEAST] Reclaiming the local interview runtime from this checkout..."
./bin/beast heal \
  --restart-all true \
  --kill-address-pids true \
  --with-litellm false \
  --with-nginx false >"$TERMUX_TMP/beast-interview-heal.json"

echo "[BEAST] Verifying browser Studio route..."
curl -fsS "$GATEWAY/beast-studio/renderer/index.html" >/dev/null

echo "[BEAST] Preparing fresh interview fixture..."
rm -rf "$FIXTURE"
OUTPUT="$("$PYTHON_BIN" scripts/demo/beast_interview_coding_agent.py   --gateway "$GATEWAY"   --fixture "$FIXTURE"   --prepare-only)"
printf '%s\n' "$OUTPUT"

STUDIO_URL="$(printf '%s\n' "$OUTPUT" | sed -n 's/^Studio  : //p' | tail -n 1)"
if [[ -z "$STUDIO_URL" ]]; then
  echo "BEAST Studio interview launcher: failed to obtain Studio URL." >&2
  exit 3
fi

echo
echo "[BEAST] Interview workspace: $FIXTURE"
echo "[BEAST] Studio URL: $STUDIO_URL"
echo "[BEAST] Opening browser..."

if command -v termux-open-url >/dev/null 2>&1; then
  termux-open-url "$STUDIO_URL"
elif command -v am >/dev/null 2>&1; then
  am start -a android.intent.action.VIEW -d "$STUDIO_URL" >/dev/null 2>&1 || true
else
  echo "Open this URL manually:"
  echo "$STUDIO_URL"
fi
