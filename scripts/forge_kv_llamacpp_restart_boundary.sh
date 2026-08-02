#!/usr/bin/env bash
set -euo pipefail
exec python3 "$(dirname "$0")/forge_kv_llamacpp_restart_boundary.py" "$@"
