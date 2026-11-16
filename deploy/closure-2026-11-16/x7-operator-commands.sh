#!/usr/bin/env bash
# BEAST X7 operator commands (closure 2026-11-16). Run by Byron, step by step, as root where marked. BEAST runs NONE of this.
# Order: consumer cgroup -> ARDA policy addendum -> ARDA measured manifest for that cgroup -> X7 load in AUDIT -> admit writer -> enforce.
set -euo pipefail
REPO=$HOME/GitHub/EdgeK-BEAST
exit 0   # safety: remove this line only when executing deliberately, one block at a time

# 1) Consumer cgroup (user unit, no root)
cp $REPO/deploy/closure-2026-11-16/beast-consumer.service ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now beast-consumer
CG=/sys/fs/cgroup$(systemctl --user show -p ControlGroup --value beast-consumer)
CGID=$(stat -c %i "$CG"); echo "consumer cgroup $CG id=$CGID"

# 2) ARDA policy: merge deploy/closure-2026-11-16/arda-addendum-beast-consumer.json ("beast_consumer" category) into
#    /usr/lib/arda/src/arda_os/backend/services/arda_harmony_addendum.json (back it up first). Review the binary list.

# 3) ARDA measured manifest for the consumer cgroup (root). The builder measures the cgroup it RUNS IN, so move a root
#    shell into the consumer cgroup first, then reuse ARDA's own builder + stage/activate/project (same flow as arda-enroll 30).
sudo bash -c "
  set -e; echo \$\$ > '$CG/cgroup.procs'
  cd /usr/lib/arda/src
  NEXT=\$(ls /var/lib/arda/projection/measured-*-v*.json 2>/dev/null | sed -E 's/.*-v([0-9]+)\.json/\1/' | sort -n | tail -1); NEXT=\$((\${NEXT:-0}+1))
  M=/var/lib/arda/projection/measured-beast-consumer-v\$NEXT.json
  ARDA_SOVEREIGN_MODE=1 PYTHONPATH=arda_os .venv/bin/python arda_os/bin/arda_build_measured_manifest.py \
      --profile critical-host --policy-generation ARDA-POLICY-V1@1.1.0 --generation \$NEXT --output \$M
  ARDA_SOVEREIGN_MODE=1 PYTHONPATH=arda_os .venv/bin/python - \$M <<'PY'
import json, sys
from backend.services.os_enforcement_service import OsEnforcementService
m = json.load(open(sys.argv[1])); s = OsEnforcementService(arm=False)
assert s.get_status().get('is_authoritative') and s.get_phase3_map_status().get('all_required_present')
s.stage_measured_manifest(m); s.activate_staged_measured_manifest(m['manifest_id']); print(s.project_staged_measured_manifest(m['manifest_id']))
PY
"
sudo bpftool map lookup pinned /sys/fs/bpf/arda/active_generation_map key hex $(python3 -c "import struct,sys;print(' '.join(f'{b:02x}' for b in struct.pack('<Q',int(sys.argv[1]))))" $CGID)

# 4) Load X7 in AUDIT mode, reusing ARDA's pinned maps read-only (root)
sudo mkdir -p /sys/fs/bpf/beast/x7
sudo bpftool prog load $REPO/bpf/build/beast_x7_model_egress_lsm.bpf.o /sys/fs/bpf/beast/x7/prog type lsm \
  map name arda_active_generation_map pinned /sys/fs/bpf/arda/active_generation_map \
  map name arda_policy_state_map      pinned /sys/fs/bpf/arda/policy_state_map \
  map name arda_lockdown_map          pinned /sys/fs/bpf/arda/lockdown_map \
  pinmaps /sys/fs/bpf/beast/x7 autoattach   # autoattach creates the lsm link (bpftool >= 7.3); the link lives while the prog pin exists
# mode 0 = audit (default). Watch counters:
sudo bpftool map dump pinned /sys/fs/bpf/beast/x7/beast_x7_stats

# 5) Admit writer (root; follows the governed_egress admit queue)
sudo $REPO/.venv/bin/python $REPO/scripts/beast_x7_admit_writer.py --follow --apply &

# 6) After audit shows ST_NO_TOKEN only for real bypasses: enforce
sudo bpftool map update pinned /sys/fs/bpf/beast/x7/beast_x7_mode key hex 00 00 00 00 value hex 01 00 00 00

# Rollback: set mode 0; rm -rf /sys/fs/bpf/beast/x7 (unpins X7 only; ARDA pins untouched);
#           deactivate the consumer manifest: OsEnforcementService(arm=False).deactivate_staged_measured_manifest(<id>, "rollback")
