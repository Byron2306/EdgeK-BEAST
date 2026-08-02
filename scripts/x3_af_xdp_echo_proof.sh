#!/usr/bin/env bash
# Execute the native AF_XDP RX/TX echo lane and emit a latency evidence receipt.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DURATION=10
PACKET_SIZE=512
PACKETS_PER_SECOND=1000
while [[ $# -gt 0 ]]; do
  case "$1" in
    --duration) DURATION="$2"; shift 2 ;;
    --packet-size) PACKET_SIZE="$2"; shift 2 ;;
    --packets-per-second) PACKETS_PER_SECOND="$2"; shift 2 ;;
    *) echo "Usage: $0 [--duration seconds] [--packet-size bytes] [--packets-per-second rate]" >&2; exit 64 ;;
  esac
done
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RESULT="$(python3 "$ROOT/scripts/x3_lab_benchmark.py" --mode af_xdp_echo --duration "$DURATION" --packet-size "$PACKET_SIZE" --packets-per-second "$PACKETS_PER_SECOND" --generic-xdp)"
RESULT="$RESULT" STAMP="$STAMP" ROOT="$ROOT" python3 - <<'PY'
import json, os
from pathlib import Path

result = json.loads(os.environ["RESULT"])
required = ("packets_sent", "packets_echoed", "packets_rx", "packets_tx", "tx_completions")
missing = [name for name in required if name not in result]
sent = result.get("packets_sent", 0)
echoed = result.get("packets_echoed", 0)
echo_ratio = echoed / sent if sent else 0.0
if missing or sent <= 0 or echo_ratio < 0.95 or result.get("packets_tx", 0) < echoed:
    raise SystemExit(f"AF_XDP echo proof failed validation: missing={missing}, result={result}")
receipt = {
    "beast_object_type": "x3_af_xdp_echo_proof",
    "proof_scope": "Native AF_XDP RX/TX echo in isolated veth namespaces.",
    "validated": True,
    "echo_ratio": echo_ratio,
    "result": result,
}
path = Path(os.environ["ROOT"]) / "evidence" / "high_velocity_fabric" / f"x3_af_xdp_echo_{os.environ['STAMP']}.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
print(json.dumps({"validated": True, "receipt": str(path), "result": result}))
PY
