#!/usr/bin/env bash
# Unlock cgroup v2 mission capsules for the current user.
#
# What this changes (and nothing else):
#   * enables memory/cpu/io/pids controllers on the cgroup v2 root subtree
#   * creates /sys/fs/cgroup/beast.slice with the same controllers delegated
#   * chowns beast.slice to the invoking user so CgroupMissionCapsule can mkdir
#
# It does NOT create, freeze, or kill any cgroup, does not change ARDA/LSM
# admission, and does not touch any running process.
#
# Run:   sudo bash scripts/unlock_cgroup_delegation.sh
# Undo:  sudo rmdir /sys/fs/cgroup/beast.slice   (only when empty)
set -euo pipefail

TARGET_USER="${SUDO_USER:-$(id -un)}"
ROOT="/sys/fs/cgroup"
SLICE="$ROOT/beast.slice"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "must run as root: sudo bash $0" >&2
  exit 1
fi
if [[ ! -f "$ROOT/cgroup.controllers" ]]; then
  echo "cgroup v2 unified hierarchy not mounted at $ROOT" >&2
  exit 1
fi

echo "== before =="
echo "root controllers:      $(cat "$ROOT/cgroup.controllers")"
echo "root subtree_control:  $(cat "$ROOT/cgroup.subtree_control" 2>/dev/null || echo '<none>')"
echo "beast.slice exists:    $([[ -d $SLICE ]] && echo yes || echo no)"

echo
echo "== delegating controllers =="
for ctrl in memory cpu io pids; do
  if ! grep -qw "$ctrl" "$ROOT/cgroup.controllers"; then
    echo "  skip $ctrl (not available on this kernel)"
    continue
  fi
  # Idempotent: an already-enabled controller is a no-op.
  if [[ -w "$ROOT/cgroup.subtree_control" ]]; then
    echo "+$ctrl" > "$ROOT/cgroup.subtree_control" 2>/dev/null \
      || echo "  note: +$ctrl already enabled or refused at root"
  fi
done
echo "root subtree_control:  $(cat "$ROOT/cgroup.subtree_control")"

echo
echo "== creating beast.slice =="
mkdir -p "$SLICE"
for ctrl in memory cpu io pids; do
  [[ -f "$SLICE/cgroup.controllers" ]] || continue
  grep -qw "$ctrl" "$SLICE/cgroup.controllers" || continue
  echo "+$ctrl" > "$SLICE/cgroup.subtree_control" 2>/dev/null || true
done
chown -R "$TARGET_USER":"$(id -gn "$TARGET_USER")" "$SLICE"
chmod 755 "$SLICE"

echo
echo "== verify =="
echo "owner:                 $(stat -c '%U:%G' "$SLICE")"
echo "controllers:           $(cat "$SLICE/cgroup.controllers")"
echo "subtree_control:       $(cat "$SLICE/cgroup.subtree_control" 2>/dev/null || echo '<none>')"
for f in memory.max memory.reclaim memory.current cgroup.freeze cgroup.kill cgroup.events; do
  [[ -e "$SLICE/$f" ]] && echo "  present: $f"
done

echo
echo "Delegation complete for user '$TARGET_USER'."
echo "Mission capsules can now be created under $SLICE/<mission_id>."
