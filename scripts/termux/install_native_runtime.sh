#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [[ -z "${PREFIX:-}" || "${PREFIX}" != *"com.termux"* ]]; then
  echo "REFUSE: this installer is for native Termux." >&2
  exit 2
fi

echo "[BEAST] Installing native Termux runtime prerequisites..."
pkg update -y
pkg install -y git python nodejs-lts curl openssh clang make cmake pkg-config rust libc++ openssl libffi termux-api

if [[ "$(uname -m)" == "aarch64" ]]; then
  pkg install -y rust-std-aarch64-linux-android || true
fi

if [[ ! -d .venv ]]; then
  python -m venv .venv
fi
source .venv/bin/activate
python -m pip install -U pip setuptools wheel
python -m pip install -r requirements.txt

chmod +x bin/beast
ln -sfn "$ROOT/bin/beast" "$PREFIX/bin/beast"

if ! command -v ollama >/dev/null 2>&1; then
  cat >&2 <<'EOF'
[BEAST] Ollama is not installed in Termux.
The Android Phase 2/4 local-model path expects a working native Ollama binary.
Install/restore the verified Termux Ollama runtime before running the model gauntlet.
EOF
fi

echo "[BEAST] CLI installed: $(command -v beast)"
echo "[BEAST] Starting Android-native backend..."
export OLLAMA_VULKAN="${OLLAMA_VULKAN:-0}"
export OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"
export BEAST_OLLAMA_BASE_URL="${BEAST_OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
beast termux-up
echo
echo "[BEAST] Native backend ready. TUI: beast ui"
