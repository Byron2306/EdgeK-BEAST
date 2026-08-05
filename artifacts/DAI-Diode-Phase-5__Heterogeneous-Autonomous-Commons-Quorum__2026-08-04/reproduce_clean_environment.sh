#!/usr/bin/env bash
set -euo pipefail
TARGET=${1:?usage: reproduce_clean_environment.sh /path/to/clean/EdgeK-BEAST}
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON_BIN=${PYTHON:-"$TARGET/.venv/bin/python"}
[ -x "$PYTHON_BIN" ] || { echo "missing executable Python: $PYTHON_BIN" >&2; exit 68; }
[ -f "$TARGET/pyproject.toml" ] || { echo "not an EdgeK-BEAST checkout: $TARGET" >&2; exit 65; }

copy_tree() {
  local src_root=$1
  local dst_root=$2
  [ -d "$src_root" ] || return 0
  (cd "$src_root" && find . -type f -print0) | while IFS= read -r -d '' file; do
    case "$file" in *"/../"*|"../"*|*"/./"*|"./."*) echo "unsafe reproduction path: $file" >&2; exit 66;; esac
    local src="$src_root/$file"
    local dst="$dst_root/$file"
    if [ -e "$dst" ] && ! cmp -s "$src" "$dst"; then
      echo "refusing to overwrite differing reproduction file: $dst" >&2
      exit 67
    fi
    mkdir -p "$(dirname "$dst")"
    cp -p "$src" "$dst"
  done
}

python3 "$SCRIPT_DIR/verify_phase5_bundle.py"
bash "$SCRIPT_DIR/install_source_overlay.sh" "$TARGET"
copy_tree "$SCRIPT_DIR/evidence/dai-diode/phase5-shared-quorum" "$TARGET/evidence/dai-diode/phase5-shared-quorum"
copy_tree "$SCRIPT_DIR/evidence/dai-diode/phase5-remote-witness-packet" "$TARGET/evidence/dai-diode/phase5-remote-witness-packet"

cd "$TARGET"
PYTHONNOUSERSITE=1 "$PYTHON_BIN" scripts/verify_dio_azure_maa_token.py   evidence/dai-diode/phase5-shared-quorum/azure/dio_azure_maa_token.jwt   --vm-description-file evidence/dai-diode/phase5-shared-quorum/azure/dio_azure_tee_governance_01_vm_description.json   --verify-signature   --jwks-file evidence/dai-diode/phase5-shared-quorum/azure/azure-maa-jwks.json >/tmp/dio_phase5_azure_offline_verify.json
PYTHONNOUSERSITE=1 "$PYTHON_BIN" scripts/run_dai_phase5_shared_quorum_replay.py >/tmp/dio_phase5_shared_quorum_replay.json
printf '{"verified":true,"phase":"5","provider_calls_used":0,"production_authority_allowed":false,"execution_authority_allowed":false}\n'
