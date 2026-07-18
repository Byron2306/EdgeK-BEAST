#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
python3 "$ROOT/tools/validate_release.py" "$ROOT"
