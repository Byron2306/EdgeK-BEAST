#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${BEAST_DEMO_PYTHON:-$HOME/EdgeK-BEAST/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$ROOT/.venv/bin/python"
fi
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "BEAST demo: Python venv not found." >&2
  exit 2
fi

export LD_PRELOAD="${LD_PRELOAD:-$PREFIX/lib/libpython3.14.so}"
export PYTHONNOUSERSITE=1
export PYTHONPATH="$ROOT"
export BEAST_GATEWAY_URL="${BEAST_GATEWAY_URL:-http://127.0.0.1:8101}"
export BEAST_OLLAMA_BASE_URL="${BEAST_OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
export BEAST_OLLAMA_MODEL="${BEAST_OLLAMA_MODEL:-qwen2.5-coder:1.5b}"

PROOF="${BEAST_DEMO_PROOF:-${TMPDIR:-$PREFIX/tmp}/beast-interview-proof.json}"

exec "$PYTHON_BIN" scripts/demo/beast_interview_coding_agent.py \
  --json-out "$PROOF" \
  "$@"
