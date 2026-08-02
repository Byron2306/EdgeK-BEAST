#!/usr/bin/env bash
set -euo pipefail

ROOT="${BEAST_ROOT:-/opt/edgek-beast-x2}"
RUNTIME_DIR="${RUNTIME_DIRECTORY:-/run/beast-x2}"
STATE_DIR="${STATE_DIRECTORY:-/var/lib/beast-x2}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

cd "$ROOT"
test -f bpf/build/beast_x1_observer.bpf.o
test -f bpf/build/libbeast_x2_loader.so
mkdir -p "$RUNTIME_DIR" "$STATE_DIR"

export BEAST_X2_EVENT_LOG="$RUNTIME_DIR/observations.jsonl"
exec /usr/bin/python3 -s -m app.kernel.sensorium.bpf.x2_cli \
  --manifest "$ROOT/X2_ATTACH_MANIFEST.json" \
  --loader "$ROOT/bpf/build/libbeast_x2_loader.so" \
  --sink app.kernel.sensorium.bpf.live_hooks:append_observation \
  --lease-resolver app.kernel.sensorium.bpf.live_hooks:resolve_process_lease \
  --receipt "$STATE_DIR/x2_observation_${STAMP}.json"
