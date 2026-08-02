#!/usr/bin/env bash
# Run only on a reviewed lab host.  This attaches read-only host-wide tracepoints.
set -euo pipefail

SOURCE_ROOT="${1:-/home/byron/EdgeK-BEAST}"
RUNTIME_ROOT="${2:-/opt/edgek-beast-x2}"
REGISTRY="/etc/edgek-beast/x2-process-leases.json"
STATE_DIR="/var/lib/beast-x2"
EVIDENCE_DIR="$SOURCE_ROOT/evidence/high_velocity_fabric"
CORRELATION_AUDIT="$STATE_DIR/correlation-audit.jsonl"
FIFO="$(mktemp -u /tmp/beast-x2-lab.XXXXXX)"
WORK_FILE="/tmp/beast-x2-lab-event-$$"
WORKER_PID=""
SERVICE_STARTED=0

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo: sudo $0 [source-root] [runtime-root]" >&2
  exit 77
fi
if systemctl is-active --quiet beast-x2-observation.service; then
  echo "Refusing to interrupt an already-running X2 observer service." >&2
  exit 73
fi
if [[ ! -f /etc/edgek-beast/x2-observation-approved ]]; then
  echo "X2 approval is intentionally manual. Review X2_ATTACH_MANIFEST.json, then run:" >&2
  echo "  sudo install -d -m 0750 /etc/edgek-beast && sudo touch /etc/edgek-beast/x2-observation-approved && sudo chmod 0600 /etc/edgek-beast/x2-observation-approved" >&2
  exit 78
fi

cleanup() {
  if [[ "$SERVICE_STARTED" -eq 1 ]]; then systemctl stop beast-x2-observation.service || true; fi
  if [[ -n "$WORKER_PID" ]]; then wait "$WORKER_PID" 2>/dev/null || true; fi
  rm -f "$FIFO" "$WORK_FILE"
  rm -f "$REGISTRY"
}
trap cleanup EXIT

"$SOURCE_ROOT/scripts/install_x2_root_owned_runtime.sh" "$SOURCE_ROOT" "$RUNTIME_ROOT"
mkdir -p "$STATE_DIR"
mkdir -p "$EVIDENCE_DIR"
rm -f "$CORRELATION_AUDIT"
PYTHONPATH="$SOURCE_ROOT" python3 -m app.kernel.sensorium.bpf.x1_cli \
  --receipt "$STATE_DIR/x1_live_preflight_$(date -u +%Y%m%dT%H%M%SZ).json"

mkfifo "$FIFO"
# Generate live, unsampled events after attachment.  The observer records both
# tcp_v4_connect and __sys_bind; unlike sampled write/scheduler paths, these
# repeated probes give the correlation guard a deterministic in-life target.
python3 "$SOURCE_ROOT/scripts/x2_lab_socket_worker.py" "$FIFO" &
WORKER_PID=$!
PYTHONPATH="$SOURCE_ROOT" python3 "$SOURCE_ROOT/scripts/x2_prepare_lab_lease.py" \
  --pid "$WORKER_PID" --registry "$REGISTRY"
chown root:root "$REGISTRY"
chmod 0600 "$REGISTRY"
# Verify the installed, privileged runtime can resolve the live process before
# attachment.  This catches a registry/namespace mismatch without emitting any
# host events.
(
  cd /
  BEAST_X2_CORRELATION_AUDIT=/dev/null PYTHONPATH="$RUNTIME_ROOT" python3 - "$WORKER_PID" <<'PY'
import sys
from app.kernel.sensorium.bpf.live_hooks import resolve_process_lease
pid = int(sys.argv[1])
resolved = resolve_process_lease(pid=pid, tgid=pid, cgroup_id=0)
if not resolved:
    raise SystemExit("installed X2 runtime could not resolve the prepared ProcessLease")
print("X2 ProcessLease registry preflight: ok")
PY
)

systemctl start beast-x2-observation.service
SERVICE_STARTED=1
for _ in $(seq 1 20); do
  systemctl is-active --quiet beast-x2-observation.service && break
  sleep 0.1
done
systemctl is-active --quiet beast-x2-observation.service
printf x >"$FIFO"
wait "$WORKER_PID"
WORKER_PID=""
sleep 2
systemctl stop beast-x2-observation.service
SERVICE_STARTED=0

RECEIPT="$(ls -1t "$STATE_DIR"/x2_observation_*.json 2>/dev/null | head -n1)"
if [[ -z "$RECEIPT" ]]; then
  echo "X2 did not write a receipt; inspect $STATE_DIR/x2-service.log" >&2
  exit 1
fi
python3 - "$RECEIPT" "$STATE_DIR" "$CORRELATION_AUDIT" <<'PY'
import hashlib, json, sys, time
receipt = json.load(open(sys.argv[1], encoding="utf-8"))["result"]
health = receipt["health"]
correlation = health.get("correlation", {})
loss_fields = ("kernel_reserve_failures", "userspace_decode_failures", "sequence_gaps", "ring_poll_errors", "loss_total")
loss_reconciled = all(name in health for name in loss_fields)
valid = (
    receipt["backend"].get("backend") == "libbpf"
    and receipt["backend"].get("bpf_object_loaded") is True
    and len(receipt["backend"].get("programs_attached", [])) >= 4
    and receipt["detach"].get("detached") is True
    and correlation.get("observations_consumed", 0) > 0
    and correlation.get("process_lease_correlation_performed") is True
    and loss_reconciled
)
proof = {
    "validated": valid,
    "authority": "controlled_host_observation_lab",
    "x1": {"live_bpf_loaded": receipt["backend"].get("bpf_object_loaded", False),
           "bpf_object": receipt["backend"].get("bpf_object"),
           "bpf_object_digest": receipt["backend"].get("bpf_object_digest")},
    "x2": {"programs_attached": receipt["backend"].get("programs_attached", []),
           "events_consumed": correlation.get("observations_consumed", 0),
           "process_lease_correlation_performed": correlation.get("process_lease_correlation_performed", False),
           "loss_counters_reconciled": loss_reconciled,
           "loss_total": health.get("loss_total"),
           "links_detached_cleanly": receipt["detach"].get("detached") is True},
    "x2_runtime_receipt": sys.argv[1],
    "correlation_audit": sys.argv[3],
    "created_at_ns": time.time_ns(),
}
proof["receipt_digest"] = "sha256:" + hashlib.sha256(
    json.dumps(proof, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()
output = f"{sys.argv[2]}/x1_x2_live_proof_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"
with open(output, "w", encoding="utf-8") as handle:
    json.dump(proof, handle, indent=2, sort_keys=True)
    handle.write("\n")
print(json.dumps({"validated": valid, "receipt": output, "result": proof}, sort_keys=True))
raise SystemExit(0 if valid else 1)
PY
PROOF_RECEIPT="$(ls -1t "$STATE_DIR"/x1_x2_live_proof_*.json 2>/dev/null | head -n1)"
if [[ -n "$PROOF_RECEIPT" ]]; then
  install -m 0644 "$PROOF_RECEIPT" "$EVIDENCE_DIR/$(basename "$PROOF_RECEIPT")"
  if command -v stat >/dev/null 2>&1; then
    OWNER_USER="$(stat -c '%U' "$SOURCE_ROOT" 2>/dev/null || true)"
    OWNER_GROUP="$(stat -c '%G' "$SOURCE_ROOT" 2>/dev/null || true)"
    if [[ -n "$OWNER_USER" && -n "$OWNER_GROUP" && "$OWNER_USER" != "UNKNOWN" && "$OWNER_GROUP" != "UNKNOWN" ]]; then
      chown "$OWNER_USER:$OWNER_GROUP" "$EVIDENCE_DIR/$(basename "$PROOF_RECEIPT")" 2>/dev/null || true
    fi
  fi
  echo "Promoted X2 proof to $EVIDENCE_DIR/$(basename "$PROOF_RECEIPT")"
fi
