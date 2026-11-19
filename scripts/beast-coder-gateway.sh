#!/usr/bin/env bash
# Launch the verified direct-coder gateway on loopback from this checkout.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
beast_python="${BEAST_GATEWAY_PYTHON:-.venv/bin/python}"
"$beast_python" - <<'PY'
from app.kernel.agents.effect_ts_bridge import EffectTSBridge, EffectUnavailable

bridge = EffectTSBridge()
try:
    bridge.check_ready()
except EffectUnavailable as exc:
    raise SystemExit(f"BEAST gateway not started: {exc}") from None
finally:
    bridge.close()
print("BEAST_EFFECT_RUNTIME=READY", flush=True)
PY
if [[ "${1:-}" == "--check" ]]; then exit 0; fi
exec "$beast_python" -m uvicorn app.main:app --host 127.0.0.1 --port "${BEAST_GATEWAY_PORT:-8202}"
