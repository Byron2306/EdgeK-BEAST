#!/usr/bin/env bash
# Create or inspect the isolated X3 veth topology. The down action removes only it.
set -eo pipefail
ACTION="$1"
if [[ -z "$ACTION" ]]; then ACTION=status; fi
set -u
RX_NS="beast-x3-rx"
TX_NS="beast-x3-tx"
RX_LINK="beast-x3-rx0"
TX_LINK="beast-x3-tx0"

namespace_exists() { ip netns list | awk '{print $1}' | grep -Fxq "$1"; }

case "$ACTION" in
  status)
    ip netns list
    ip -n "$RX_NS" -br addr 2>/dev/null || true
    ip -n "$TX_NS" -br addr 2>/dev/null || true
    ;;
  up)
    if namespace_exists "$RX_NS" || namespace_exists "$TX_NS"; then
      echo "Refusing partial or existing X3 topology; inspect with: $0 status" >&2
      exit 73
    fi
    ip netns add "$RX_NS"
    ip netns add "$TX_NS"
    ip link add "$RX_LINK" type veth peer name "$TX_LINK"
    ip link set "$RX_LINK" netns "$RX_NS"
    ip link set "$TX_LINK" netns "$TX_NS"
    ip -n "$RX_NS" link set lo up
    ip -n "$TX_NS" link set lo up
    ip -n "$RX_NS" link set "$RX_LINK" name eth0
    ip -n "$TX_NS" link set "$TX_LINK" name eth0
    ip -n "$RX_NS" addr add 10.203.0.2/24 dev eth0
    ip -n "$TX_NS" addr add 10.203.0.1/24 dev eth0
    ip -n "$RX_NS" link set eth0 up
    ip -n "$TX_NS" link set eth0 up
    echo "X3 veth lab ready: beast-x3-tx (10.203.0.1) -> beast-x3-rx (10.203.0.2)"
    ;;
  down)
    # ip netns delete removes only the explicitly named isolated namespaces.
    namespace_exists "$RX_NS" && ip netns delete "$RX_NS" || true
    namespace_exists "$TX_NS" && ip netns delete "$TX_NS" || true
    ;;
  *) echo "Usage: $0 {up|down|status}" >&2; exit 64 ;;
esac
