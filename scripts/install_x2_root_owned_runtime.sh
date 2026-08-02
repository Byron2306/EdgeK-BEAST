#!/usr/bin/env bash
set -euo pipefail

SOURCE_ROOT="${1:-/home/byron/EdgeK-BEAST}"
TARGET_ROOT="${2:-/opt/edgek-beast-x2}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo: sudo $0 [source-root] [target-root]" >&2
  exit 77
fi

BUILD_ROOT="$(mktemp -d /tmp/edgek-beast-x2-build.XXXXXX)"
trap 'rm -rf "$BUILD_ROOT"' EXIT
make -C "$SOURCE_ROOT/bpf" BUILD_DIR="$BUILD_ROOT" all
install -d -o root -g root -m 0755 "$TARGET_ROOT"

copy_file() {
  local relative="$1"
  install -D -o root -g root -m 0644 "$SOURCE_ROOT/$relative" "$TARGET_ROOT/$relative"
}

for relative in \
  app/__init__.py \
  app/kernel/__init__.py \
  app/kernel/sensorium/bpf/__init__.py \
  app/kernel/sensorium/bpf/x1_runtime.py \
  app/kernel/sensorium/bpf/x2_cli.py \
  app/kernel/sensorium/bpf/x2_runtime.py \
  app/kernel/sensorium/bpf/live_hooks.py \
  app/kernel/sensorium/bpf_event_contracts.py \
  app/kernel/sensorium/bpf_loss_receipts.py \
  app/kernel/sensorium/bpf_ring_adapter.py \
  X2_ATTACH_MANIFEST.json; do
  copy_file "$relative"
done
install -D -o root -g root -m 0644 "$BUILD_ROOT/beast_x1_observer.bpf.o" "$TARGET_ROOT/bpf/build/beast_x1_observer.bpf.o"
install -D -o root -g root -m 0644 "$BUILD_ROOT/libbeast_x2_loader.so" "$TARGET_ROOT/bpf/build/libbeast_x2_loader.so"

# The regular Sensorium package imports the full BEAST runtime.  The privileged
# observer uses only the narrow X2 subset copied above.
install -D -o root -g root -m 0644 /dev/null "$TARGET_ROOT/app/kernel/sensorium/__init__.py"
install -o root -g root -m 0755 "$SOURCE_ROOT/scripts/run_x2_observer.sh" "$TARGET_ROOT/run_x2_observer.sh"
install -o root -g root -m 0644 "$SOURCE_ROOT/deploy/systemd/beast-x2-observation.service" /etc/systemd/system/beast-x2-observation.service
install -d -o root -g root -m 0750 /etc/edgek-beast
systemctl daemon-reload

echo "Installed root-owned X2 runtime at $TARGET_ROOT."
echo "Review the manifest and then create /etc/edgek-beast/x2-observation-approved before starting the service."
