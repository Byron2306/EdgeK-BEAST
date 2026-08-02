#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
/home/byron/EdgeK-BEAST/.venv/bin/python3.14 "$ROOT/tools/validate_release.py" "$ROOT"
