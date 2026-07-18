#!/usr/bin/env bash
set -euo pipefail

backup_dir="/root/seraph-host-cleanup-backup-$(date +%Y%m%dT%H%M%S)"
purge_opt=false

if [[ "${1:-}" == "--purge-opt" ]]; then
  purge_opt=true
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo: sudo bash $0 [--purge-opt]" >&2
  exit 1
fi

mkdir -p "$backup_dir"

echo "[1/6] Stopping and disabling Seraph host services..."
systemctl disable --now seraph-agent.service 2>/dev/null || true
systemctl disable --now seraph-agent-dashboard.service 2>/dev/null || true
systemctl reset-failed seraph-agent.service seraph-agent-dashboard.service 2>/dev/null || true

echo "[2/6] Backing up Seraph systemd units to $backup_dir ..."
for unit in \
  /etc/systemd/system/seraph-agent.service \
  /etc/systemd/system/seraph-agent.service.off \
  /etc/systemd/system/seraph-agent-dashboard.service \
  /etc/systemd/system/seraph-agent-dashboard.service.off
do
  if [[ -e "$unit" ]]; then
    cp -a "$unit" "$backup_dir/"
    rm -f "$unit"
  fi
done

echo "[3/6] Removing stale systemd wants links..."
rm -f /etc/systemd/system/multi-user.target.wants/seraph-agent.service
rm -f /etc/systemd/system/multi-user.target.wants/seraph-agent-dashboard.service
systemctl daemon-reload
systemctl reset-failed 2>/dev/null || true

echo "[4/6] Removing stale NetworkManager/software interfaces if present..."
nmcli device delete metatron-vpn 2>/dev/null || true
ip link delete metatron-vpn 2>/dev/null || true

echo "[5/6] Removing spoofed software-properties-common dummy package if installed..."
if dpkg-query -W -f='${Version}\n' software-properties-common 2>/dev/null | grep -q '99.9-spoof-trixie'; then
  apt-get remove --purge -y software-properties-common
fi
apt-get autoremove --purge -y
apt-get update

echo "[6/6] Optional /opt cleanup..."
if [[ "$purge_opt" == true ]]; then
  for dir in /opt/seraph-agent; do
    if [[ -e "$dir" ]]; then
      cp -a "$dir" "$backup_dir/"
      rm -rf "$dir"
    fi
  done
  echo "Purged /opt/seraph-agent after backing it up."
else
  echo "Kept /opt/seraph-agent. Re-run with --purge-opt to remove it after backup."
fi

echo
echo "Done. Backup: $backup_dir"
systemctl --no-pager --failed || true
