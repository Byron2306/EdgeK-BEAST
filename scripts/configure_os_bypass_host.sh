#!/usr/bin/env bash
set -euo pipefail

APPLY=0
HUGEPAGES="${HUGEPAGES:-1024}"
PCI_ADDR="${PCI_ADDR:-}"
DRIVER="${DRIVER:-vfio-pci}"

usage() {
  cat <<'USAGE'
Configure host prerequisites for BEAST DPDK/AF_XDP experiments.

Dry-run by default. Use --apply to make host changes.

Environment:
  HUGEPAGES=1024          Number of 2 MiB hugepages to reserve.
  PCI_ADDR=0000:03:00.0   Optional NIC PCI address to bind for DPDK.
  DRIVER=vfio-pci         DPDK driver to bind, usually vfio-pci.
  PYTHON_BIN=./venv/bin/python
                          Python binary to grant packet experiment caps.

Examples:
  ./scripts/configure_os_bypass_host.sh
  HUGEPAGES=2048 ./scripts/configure_os_bypass_host.sh --apply
  PCI_ADDR=0000:03:00.0 ./scripts/configure_os_bypass_host.sh --apply

Warning:
  Binding the wrong NIC can disconnect this host. Do not bind your active
  management interface.
USAGE
}

for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; usage; exit 2 ;;
  esac
done

run() {
  if [[ "$APPLY" == "1" ]]; then
    echo "+ $*"
    "$@"
  else
    printf '[dry-run] %q ' "$@"
    echo
  fi
}

echo "== BEAST OS-bypass host setup =="
echo "Mode: $([[ "$APPLY" == "1" ]] && echo apply || echo dry-run)"

echo
echo "== Kernel/modules =="
run sudo modprobe vfio-pci
run sudo modprobe xsk_diag

echo
echo "== Hugepages =="
run sudo sysctl -w "vm.nr_hugepages=${HUGEPAGES}"
if [[ "$APPLY" == "1" ]]; then
  grep -E 'HugePages_Total|HugePages_Free|Hugepagesize' /proc/meminfo || true
else
  echo "[dry-run] grep -E 'HugePages_Total|HugePages_Free|Hugepagesize' /proc/meminfo"
fi

echo
echo "== Capabilities for Python/uvicorn process =="
PYTHON_BIN="$(readlink -f "${PYTHON_BIN:-$(command -v python3)}")"
echo "Python interpreter: ${PYTHON_BIN}"
if command -v setcap >/dev/null 2>&1; then
  SETCAP_BIN="$(command -v setcap)"
elif [[ -x /usr/sbin/setcap ]]; then
  SETCAP_BIN="/usr/sbin/setcap"
elif [[ -x /sbin/setcap ]]; then
  SETCAP_BIN="/sbin/setcap"
else
  echo "setcap not found; install libcap2-bin or run the gateway with sudo for packet experiments." >&2
  exit 1
fi
run sudo "$SETCAP_BIN" cap_net_raw,cap_net_admin,cap_bpf,cap_sys_admin+ep "$PYTHON_BIN"
if [[ "$APPLY" == "1" ]]; then
  "$SETCAP_BIN" -v cap_net_raw,cap_net_admin,cap_bpf,cap_sys_admin+ep "$PYTHON_BIN" || true
fi

echo
echo "== DPDK NIC binding =="
if [[ -n "$PCI_ADDR" ]]; then
  DPDK_BIND="$(command -v dpdk-devbind.py || true)"
  if [[ -z "$DPDK_BIND" ]]; then
    echo "dpdk-devbind.py not found; install dpdk package first." >&2
    exit 1
  fi
  run sudo "$DPDK_BIND" --bind="$DRIVER" "$PCI_ADDR"
else
  echo "No PCI_ADDR set. Listing devices only:"
  if command -v dpdk-devbind.py >/dev/null 2>&1; then
    dpdk-devbind.py --status || true
  else
    echo "dpdk-devbind.py not found."
  fi
fi

echo
echo "== AF_XDP interface prep =="
echo "Attach XDP programs per interface/workload. For generic smoke tests, BEAST can probe libxdp without attaching a program."

echo
echo "Done."
