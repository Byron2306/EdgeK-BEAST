#!/usr/bin/env bash
# Execute the real AF_XDP copy worker and emit a validated evidence receipt.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DURATION=10
PACKET_SIZE=512
PACKETS_PER_SECOND=1000
SETUP=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --duration) DURATION="$2"; shift 2 ;;
    --packet-size) PACKET_SIZE="$2"; shift 2 ;;
    --packets-per-second) PACKETS_PER_SECOND="$2"; shift 2 ;;
    --setup) SETUP=1; shift ;;
    *) echo "Usage: $0 [--setup] [--duration seconds] [--packet-size bytes] [--packets-per-second rate]" >&2; exit 64 ;;
  esac
done
if [[ "$SETUP" == 1 ]]; then "$ROOT/scripts/x3_lab_netns.sh" up; fi
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RESULT="$(python3 "$ROOT/scripts/x3_lab_benchmark.py" --mode af_xdp_copy --duration "$DURATION" --packet-size "$PACKET_SIZE" --packets-per-second "$PACKETS_PER_SECOND" --generic-xdp)"
RESULT="$RESULT" STAMP="$STAMP" ROOT="$ROOT" python3 - <<'PY'
import json, os
from pathlib import Path

result = json.loads(os.environ["RESULT"])
required = ("packets_rx", "bytes_rx", "xdp_packets_seen", "xdp_socket_misses", "fill_starvation")
missing = [name for name in required if name not in result]
sent = result.get("packets_tx", 0)
delivery_ratio = result.get("packets_rx", 0) / sent if sent else 0.0
xdp_observation_ratio = result.get("xdp_packets_seen", 0) / sent if sent else 0.0
if missing or sent <= 0 or delivery_ratio < 0.95 or xdp_observation_ratio < 0.95:
    raise SystemExit(f"AF_XDP proof failed validation: missing={missing}, result={result}")
receipt = {
    "beast_object_type": "x3_af_xdp_copy_proof",
    "proof_scope": "Native AF_XDP receive in isolated veth namespaces; UDP is traffic generation only.",
    "validated": True,
    "delivery_ratio": delivery_ratio,
    "xdp_observation_ratio": xdp_observation_ratio,
    "result": result,
}
path = Path(os.environ["ROOT"]) / "evidence" / "high_velocity_fabric" / f"x3_af_xdp_copy_{os.environ['STAMP']}.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
print(json.dumps({"validated": True, "receipt": str(path), "result": result}))
PY
