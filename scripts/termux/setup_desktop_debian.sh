#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ -z "${PREFIX:-}" || "${PREFIX}" != *"com.termux"* ]]; then
  echo "REFUSE: run this from native Termux." >&2
  exit 2
fi

pkg update -y
pkg install -y proot-distro x11-repo
pkg install -y termux-x11-nightly rsync

if ! proot-distro list 2>/dev/null | grep -qE '^.*debian.*installed'; then
  proot-distro install debian
fi

echo "[BEAST] Installing Debian Electron runtime..."
proot-distro login debian --shared-tmp --bind "$ROOT:/mnt/beast-source" -- bash -lc '
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y   git rsync nodejs npm dbus-x11 openbox   libgtk-3-0 libnss3 libxss1 libasound2 libatk-bridge2.0-0   libdrm2 libgbm1 libxkbcommon0 libxcomposite1 libxdamage1   libxrandr2 libxfixes3 libcups2 libpango-1.0-0 libcairo2
mkdir -p /root/EdgeK-BEAST-desktop
rsync -a --delete   --exclude .git   --exclude .venv   --exclude venv   --exclude node_modules   --exclude .beast   --exclude deploy/run   /mnt/beast-source/ /root/EdgeK-BEAST-desktop/
cd /root/EdgeK-BEAST-desktop/desktop-ide
npm ci
'

echo
echo "[BEAST] Debian desktop runtime prepared."
echo "Install/open the Termux:X11 Android app, then run:"
echo "  scripts/termux/launch_desktop_ide.sh"
