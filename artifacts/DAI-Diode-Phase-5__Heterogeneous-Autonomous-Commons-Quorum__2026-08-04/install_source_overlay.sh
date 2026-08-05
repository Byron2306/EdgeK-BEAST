#!/usr/bin/env bash
set -euo pipefail
TARGET=${1:?usage: install_source_overlay.sh /path/to/EdgeK-BEAST}
[ -f "$TARGET/pyproject.toml" ] || { echo 'not an EdgeK-BEAST checkout' >&2; exit 65; }
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
copy_tree() {
  local src_root=$1
  local dst_root=$2
  [ -d "$src_root" ] || return 0
  (cd "$src_root" && find . -type f -print0) | while IFS= read -r -d '' file; do
    case "$file" in *"/../"*|"../"*|*"/./"*|"./."*) echo "unsafe overlay path: $file" >&2; exit 66;; esac
    src="$src_root/$file"
    dst="$dst_root/$file"
    if [ -e "$dst" ] && ! cmp -s "$src" "$dst"; then
      echo "refusing to overwrite differing file: $dst" >&2
      exit 67
    fi
    mkdir -p "$(dirname "$dst")"
    cp -p "$src" "$dst"
  done
}
copy_tree "$SCRIPT_DIR/source" "$TARGET"
copy_tree "$SCRIPT_DIR/tests" "$TARGET"
copy_tree "$SCRIPT_DIR/dependencies" "$TARGET/reproduction-dependencies"
