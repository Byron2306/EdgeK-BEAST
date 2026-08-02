#!/usr/bin/env bash
set -euo pipefail

ROOT="${BEAST_ROOT:-/home/byron/EdgeK-BEAST}"
INTERFACE="${BEAST_BPF_LAB_INTERFACE:-lo}"
RUNTIME_DIR="${RUNTIME_DIRECTORY:-/run/beast-bpf-lab}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

if [[ "$INTERFACE" != "lo" ]]; then
  echo "Refusing non-loopback interface: $INTERFACE" >&2
  exit 64
fi

cd "$ROOT"
mkdir -p "$RUNTIME_DIR" "$ROOT/evidence/high_velocity_fabric"

PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" \
  "$ROOT/.venv/bin/python" -m app.kernel.sensorium.bpf.x1_cli \
  --receipt "$ROOT/evidence/high_velocity_fabric/x1_loopback_preflight_${STAMP}.json"

PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" \
  "$ROOT/.venv/bin/python" -c '
import json
from app.kernel.networking.os_bypass import af_xdp_probe
print(json.dumps(af_xdp_probe(interface="lo", queue_id=0), sort_keys=True))
' > "$RUNTIME_DIR/af_xdp_loopback_probe.json"

cp "$RUNTIME_DIR/af_xdp_loopback_probe.json" \
  "$ROOT/evidence/high_velocity_fabric/af_xdp_loopback_probe_${STAMP}.json"

echo "BEAST loopback BPF laboratory preflight passed; no BPF/XDP program was attached."
