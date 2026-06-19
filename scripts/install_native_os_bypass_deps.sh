#!/usr/bin/env bash
set -euo pipefail

if ! command -v apt-get >/dev/null 2>&1; then
  echo "This installer currently supports Debian/Ubuntu apt systems." >&2
  exit 1
fi

if [[ "${EUID}" -ne 0 ]]; then
  exec sudo "$0" "$@"
fi

apt-get update
apt-get install -y \
  dpdk \
  libdpdk-dev \
  libxdp1 \
  libxdp-dev \
  libbpf-dev

ldconfig

echo "Native OS-bypass dependencies installed."
echo "Note: DPDK still requires hugepages and a vfio/uio-bound NIC for packet IO."
echo "Note: AF_XDP still requires kernel/NIC support and CAP_NET_ADMIN/CAP_BPF or equivalent permissions."
