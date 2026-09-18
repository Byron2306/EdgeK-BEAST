#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python)"
fi

MODEL="${BEAST_PHASE4_ANDROID_MODEL:-qwen2.5:0.5b}"
OLLAMA_BASE="${BEAST_OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
GATEWAY_BASE="${BEAST_GATEWAY_BASE_URL:-http://127.0.0.1:8101}"
OUT="$ROOT/.beast/phase4-android"
mkdir -p "$OUT"

echo "BEAST Phase 4 Android / Termux gauntlet"
echo "root=$ROOT"
echo "python=$("$PYTHON" --version 2>&1)"
echo "model=$MODEL"

echo "== local Ollama =="
curl -fsS "$OLLAMA_BASE/api/tags" > "$OUT/ollama-tags.json"
"$PYTHON" - "$OUT/ollama-tags.json" "$MODEL" <<'PY'
import json, sys
path, requested = sys.argv[1:3]
payload = json.load(open(path, encoding="utf-8"))
names = {
    str(item.get("name") or item.get("model") or "")
    for item in payload.get("models", [])
    if isinstance(item, dict)
}
if requested not in names:
    raise SystemExit(f"required local model not present: {requested}; found={sorted(names)}")
print(f"OLLAMA_MODEL_PRESENT {requested}")
PY

echo "== live gateway system snapshot =="
ROOT_Q="$("$PYTHON" - <<'PY'
from pathlib import Path
from urllib.parse import quote
print(quote(str(Path.cwd()), safe=""))
PY
)"
curl -fsS   "$GATEWAY_BASE/edgek/ide/system-snapshot?root_path=$ROOT_Q&port_limit=5&process_limit=5"   > "$OUT/system-snapshot.json"
"$PYTHON" - "$OUT/system-snapshot.json" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
assert payload.get("ok") is True, payload
assert payload.get("beast_object_type") == "beast_ide_system_snapshot", payload
print("TERMUX_SYSTEM_SNAPSHOT_VERIFIED")
PY

export OLLAMA_HOST="$OLLAMA_BASE"
export BEAST_OLLAMA_BASE_URL="$OLLAMA_BASE"
export BEAST_LIVE_OLLAMA_ACCEPTANCE=1
export BEAST_LIVE_OLLAMA_MODEL="$MODEL"
export BEAST_OLLAMA_PLANNER_TIMEOUT="${BEAST_OLLAMA_PLANNER_TIMEOUT:-180}"
export BEAST_OLLAMA_PREFLIGHT_TIMEOUT="${BEAST_OLLAMA_PREFLIGHT_TIMEOUT:-10}"
export BEAST_OLLAMA_KEEP_ALIVE="${BEAST_OLLAMA_KEEP_ALIVE:-10m}"

echo "== native local model provider =="
"$PYTHON" -m pytest -q --noconftest   tests/phase2/test_live_ollama_provider_acceptance.py   --junitxml="$OUT/live-ollama.xml"

echo "== Android system-plane resilience =="
"$PYTHON" -m pytest -q --noconftest   tests/test_ide_system_plane.py   -k 'restricted_procfs_inode_scan_degrades_gracefully or read_only_system_routes_return_ok or system_snapshot_advertises_capabilities'   --junitxml="$OUT/system-plane.xml"

echo "== canonical Phase 4 subsystem =="
"$PYTHON" -m pytest -q --noconftest   tests/phase4/test_phase4_1_approval_contracts.py   tests/phase4/test_phase4_2_durable_approval_store.py   tests/phase4/test_phase4_3_risk_classifier.py   tests/phase4/test_phase4_4_rich_approval_envelope.py   tests/phase4/test_phase4_5_approval_scope_engine.py   tests/phase4/test_phase4_6_request_bound_capability.py   tests/phase4/test_phase4_7_capability_runtime.py   tests/phase4/test_phase4_11_durable_approval_cards.py   tests/phase4/test_phase4_12_revocation_policy_admin.py   tests/phase4/test_phase4_13_end_to_end_closure.py   tests/test_phase4_9_sensitive_data_controls.py   tests/test_phase4_10_external_content_admission.py   tests/phase4/test_agent_selection_fallback.py   --junitxml="$OUT/canonical.xml"

echo "== live durable approval / restart / one-use capability =="
"$PYTHON" -m pytest -q --noconftest   tests/phase4/test_agentrun_durable_approval_integration.py   --junitxml="$OUT/live-approval.xml"

echo "== live permission modes =="
"$PYTHON" -m pytest -q --noconftest   tests/phase4/test_live_permission_modes.py   --junitxml="$OUT/modes.xml"

echo "== sensitive-data and external-content controls =="
"$PYTHON" -m pytest -q --noconftest   tests/phase4/test_live_sensitive_external_controls.py   --junitxml="$OUT/sensitive-external.xml"

echo "== Phase 3 regression spine =="
"$PYTHON" -m pytest -q --noconftest   tests/phase3/test_least_authority_runtime.py   tests/phase3/test_run_budget_policy.py   tests/phase3/test_planner_stagnation.py   tests/phase3/test_verification_ladder.py   tests/phase3/test_phase3_seeded_defect_gauntlet.py   tests/routes/test_agent_tool_runtime.py   --junitxml="$OUT/phase3-regression.xml"

echo "== compile native Android receipt =="
"$PYTHON" - "$OUT" "$MODEL" <<'PY'
from __future__ import annotations
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

out = Path(sys.argv[1])
model = sys.argv[2]

def sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

def junit(path: Path) -> dict:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall(".//testsuite"))
    def total(key: str) -> int:
        return sum(int(float(s.attrib.get(key, "0") or 0)) for s in suites)
    row = {
        "path": path.name,
        "digest": sha(path),
        "tests": total("tests"),
        "failures": total("failures"),
        "errors": total("errors"),
        "skipped": total("skipped"),
    }
    row["passed"] = row["tests"] > 0 and row["failures"] == 0 and row["errors"] == 0 and row["skipped"] == 0
    return row

files = {
    "live_local_model_provider": out / "live-ollama.xml",
    "termux_system_plane": out / "system-plane.xml",
    "canonical_phase4_subsystem": out / "canonical.xml",
    "live_durable_approval_and_restart": out / "live-approval.xml",
    "permission_modes_and_bounded_autonomy": out / "modes.xml",
    "sensitive_and_external_content_controls": out / "sensitive-external.xml",
    "phase3_behavior_preserved": out / "phase3-regression.xml",
}
gates = {name: junit(path) for name, path in files.items()}
head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
receipt = {
    "schema": "beast.coding_agent.phase4.android.closure.v1",
    "phase": 4,
    "platform": "termux-android",
    "architecture": platform.machine(),
    "python": platform.python_version(),
    "git_head": head,
    "model": model,
    "ollama_transport": "local_native_api",
    "system_snapshot_digest": sha(out / "system-snapshot.json"),
    "ollama_tags_digest": sha(out / "ollama-tags.json"),
    "gates": gates,
    "phase4_android_exit_met": all(item["passed"] for item in gates.values()),
    "captured_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "boundaries": {
        "packaged_electron_android": "not_claimed",
        "vulkan_gpu": "not_claimed",
        "sourceplan_promotion": "not_model_authorized",
    },
}
path = out / "BEAST_PHASE4_ANDROID_COMPLETION.json"
path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps({
    "phase4_android_exit_met": receipt["phase4_android_exit_met"],
    "git_head": head,
    "model": model,
    "receipt": str(path),
    "receipt_digest": sha(path),
    "gates": {name: item["passed"] for name, item in gates.items()},
}, indent=2, sort_keys=True))
if not receipt["phase4_android_exit_met"]:
    raise SystemExit(2)
PY

echo "BEAST_PHASE4_ANDROID_VERIFIED"
