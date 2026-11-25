#!/usr/bin/env bash
# Run the existing Coder screen against an isolated, ordinary BEAST gateway.
set +x
set -euo pipefail
umask 077
py="${1:?provide a BEAST runtime Python path}"
trial="${2:?provide an absolute trial directory}"
port="${3:-18171}"
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo"
mkdir -p -- "$trial"
trial="$(cd -- "$trial" && pwd)"
if [[ ! -d "$trial/workspace" ]]; then
  "$py" -m scripts.proof.prepare_coder_crystal_trial --workspace "$trial/workspace"
fi
export BEAST_CODER_CRYSTAL_TRIAL=1
export BEAST_CODING_CRYSTAL_KEY="$trial/ui-trial-authority.pem"
export BEAST_STATE_ROOT="$trial/gateway-state"
export BEAST_COMMONS_ROOT="$trial/commons"
"$py" - "$port" <<'PY'
from pathlib import Path
import os
import socket
import sys
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

port = int(sys.argv[1])
if not 1024 <= port <= 65535:
    raise SystemExit("Choose an unprivileged loopback port.")
with socket.socket() as probe:
    try:
        probe.bind(("127.0.0.1", port))
    except OSError:
        raise SystemExit(f"Gateway port {port} is busy. Choose a different port.") from None
path = Path(os.environ["BEAST_CODING_CRYSTAL_KEY"])
if not path.exists():
    key = Ed25519PrivateKey.generate()
    with path.open("xb") as output:
        output.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
PY

"$py" -m app.kernel.security.local_provider_keys run nvidia_nim -- \
  "$py" bin/beast gateway --host 127.0.0.1 --port "$port" --socket-mode direct \
  >"$trial/gateway.log" 2>&1 &
gateway_pid=$!
trap 'kill "$gateway_pid" 2>/dev/null || true; wait "$gateway_pid" 2>/dev/null || true' EXIT
url="http://127.0.0.1:$port"
"$py" - "$url" "$gateway_pid" <<'PY'
import os
import sys
import time
from urllib.request import ProxyHandler, build_opener

http = build_opener(ProxyHandler({}))
for _ in range(60):
    try:
        os.kill(int(sys.argv[2]), 0)
    except ProcessLookupError:
        break
    try:
        with http.open(sys.argv[1] + "/health", timeout=.5) as response:
            if response.status == 200:
                raise SystemExit(0)
    except OSError:
        time.sleep(.25)
raise SystemExit("Trial gateway did not become ready. Inspect gateway.log in the trial directory.")
PY
printf 'CODER_TRIAL=%s\n' "$trial"
"$py" -m app.cli.coder --workspace "$trial/workspace" --gateway-url "$url"
