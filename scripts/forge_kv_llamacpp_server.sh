#!/usr/bin/env bash
# Start the locally installed, isolated llama.cpp prompt-cache proof server.
set -eo pipefail
PORT="$1"
if [[ -z "$PORT" ]]; then PORT=11435; fi
set -u
LLAMA_ROOT="/home/byron/.local/lib/beast/llama.cpp-a582222"
MODEL="/home/byron/.ollama/models/blobs/sha256-c5396e06af294bd101b30dce59131a76d2b773e76950acc870eda801d3ab0515"
export LD_LIBRARY_PATH="$LLAMA_ROOT/lib"
exec "$LLAMA_ROOT/bin/llama-server" --model "$MODEL" --host 127.0.0.1 --port "$PORT" \
  --ctx-size 4096 --parallel 1 --cache-prompt --cache-reuse 64
