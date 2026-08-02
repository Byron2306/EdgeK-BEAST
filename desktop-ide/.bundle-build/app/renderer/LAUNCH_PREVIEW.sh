#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${1:-8765}"
echo "BEAST IDE preview: http://127.0.0.1:$PORT/index.html"
echo "Acceptance runner: http://127.0.0.1:$PORT/acceptance/release-runner.html"
cd "$ROOT" && python3 -m http.server "$PORT" --bind 127.0.0.1
