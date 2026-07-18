#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
stable_root="${TMPDIR:-/tmp}/edgek-codex-stable"
user_data_dir="$stable_root/user-data"
extensions_dir="$stable_root/extensions"
log_dir="$stable_root/logs"

mkdir -p "$user_data_dir" "$extensions_dir" "$log_dir"

openai_extension="$(
  find "$HOME/.vscode/extensions" -maxdepth 1 -type d -name 'openai.chatgpt-*' \
    | sort -V \
    | tail -n 1
)"

if [[ -z "$openai_extension" ]]; then
  echo "Could not find the OpenAI Codex VS Code extension under $HOME/.vscode/extensions" >&2
  exit 1
fi

openai_extension_link="$extensions_dir/$(basename "$openai_extension")"
if [[ ! -e "$openai_extension_link" ]]; then
  ln -s "$openai_extension" "$openai_extension_link"
fi

exec env VSCODE_LOGS="$log_dir" code \
  --new-window \
  --sync off \
  --disable-gpu \
  --log openai.chatgpt:trace \
  --disable-extension vscode.github \
  --disable-extension vscode.github-authentication \
  --disable-extension vscode.microsoft-authentication \
  --user-data-dir "$user_data_dir" \
  --extensions-dir "$extensions_dir" \
  "$repo_root"
