#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [[ -z "${PREFIX:-}" || "${PREFIX}" != *"com.termux"* ]]; then
  echo "REFUSE: Phase 4 Android gauntlet must run in native Termux." >&2
  exit 2
fi

PYTHON="$ROOT/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="$ROOT/venv/bin/python"
[[ -x "$PYTHON" ]] || { echo "No BEAST venv found." >&2; exit 2; }

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$ROOT/benchmarks/results/beast_phase4_termux_android/$STAMP"
mkdir -p "$OUT"

export PYTHONNOUSERSITE=1
export OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"
export OLLAMA_VULKAN="${OLLAMA_VULKAN:-0}"
export BEAST_OLLAMA_BASE_URL="${BEAST_OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
export BEAST_LIVE_OLLAMA_ACCEPTANCE=1
export BEAST_LIVE_OLLAMA_MODEL="${BEAST_LIVE_OLLAMA_MODEL:-qwen2.5:0.5b}"
export BEAST_OLLAMA_NUM_CTX="${BEAST_OLLAMA_NUM_CTX:-2048}"
export BEAST_OLLAMA_NUM_PREDICT="${BEAST_OLLAMA_NUM_PREDICT:-128}"
export BEAST_OLLAMA_PLANNER_TIMEOUT="${BEAST_OLLAMA_PLANNER_TIMEOUT:-150}"
export BEAST_OLLAMA_PREFLIGHT_TIMEOUT="${BEAST_OLLAMA_PREFLIGHT_TIMEOUT:-10}"
export BEAST_OLLAMA_KEEP_ALIVE="${BEAST_OLLAMA_KEEP_ALIVE:-10m}"

echo "[1/9] Native backend"
"$PYTHON" bin/beast termux-up > "$OUT/runtime-up.json"

echo "[2/9] Canonical Phase 4 subsystem"
"$PYTHON" -m pytest -q --noconftest   tests/phase4/test_phase4_1_approval_contracts.py   tests/phase4/test_phase4_2_durable_approval_store.py   tests/phase4/test_phase4_3_risk_classifier.py   tests/phase4/test_phase4_4_rich_approval_envelope.py   tests/phase4/test_phase4_5_approval_scope_engine.py   tests/phase4/test_phase4_6_request_bound_capability.py   tests/phase4/test_phase4_7_capability_runtime.py   tests/phase4/test_phase4_11_durable_approval_cards.py   tests/phase4/test_phase4_12_revocation_policy_admin.py   tests/phase4/test_phase4_13_end_to_end_closure.py   tests/test_phase4_9_sensitive_data_controls.py   tests/test_phase4_10_external_content_admission.py   tests/phase4/test_agent_selection_fallback.py   --junitxml="$OUT/phase4-canonical.xml"

echo "[3/9] Live durable approval/restart/replan/revocation"
"$PYTHON" -m pytest -q --noconftest   tests/phase4/test_agentrun_durable_approval_integration.py   --junitxml="$OUT/phase4-live-approval.xml"

echo "[4/9] Permission modes + bounded autonomy"
"$PYTHON" -m pytest -q --noconftest   tests/phase4/test_live_permission_modes.py   --junitxml="$OUT/phase4-modes.xml"

echo "[5/9] Sensitive + external content"
"$PYTHON" -m pytest -q --noconftest   tests/phase4/test_live_sensitive_external_controls.py   --junitxml="$OUT/phase4-sensitive-external.xml"

echo "[6/9] Phase 3 regression"
"$PYTHON" -m pytest -q --noconftest   tests/phase3/test_least_authority_runtime.py   tests/phase3/test_run_budget_policy.py   tests/phase3/test_planner_stagnation.py   tests/phase3/test_verification_ladder.py   tests/phase3/test_phase3_seeded_defect_gauntlet.py   tests/routes/test_agent_tool_runtime.py   --junitxml="$OUT/phase3-regression.xml"

echo "[7/9] Native desktop renderer ingress"
"$PYTHON" -m pytest -q --noconftest   tests/phase2/test_live_desktop_agent_ingress.py   --junitxml="$OUT/desktop-ingress.xml"

echo "[8/9] Native local Ollama/Qwen + planner endurance"
"$PYTHON" -m pytest -q --noconftest   tests/phase2/test_live_ollama_provider_acceptance.py   --junitxml="$OUT/live-ollama.xml"
"$PYTHON" -m pytest -q --noconftest tests/test_agent_planner_runtime.py   -k "large_real_repo_endurance or provider_quality_ledger or capability_scored_provider"   --junitxml="$OUT/planner-endurance.xml"

echo "[9/9] Compile Android receipt"
"$PYTHON" scripts/termux/compile_phase4_android_receipt.py   --input-dir "$OUT"   --json-out "$OUT/BEAST_PHASE4_TERMUX_ANDROID_ACCEPTANCE.json"   --md-out "$OUT/BEAST_PHASE4_TERMUX_ANDROID_ACCEPTANCE.md"

cat "$OUT/BEAST_PHASE4_TERMUX_ANDROID_ACCEPTANCE.md"
echo
echo "Receipt directory: $OUT"
