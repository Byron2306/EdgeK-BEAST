# BEAST Mission Console UI Patch

This patch adds the first Textual-based BEAST terminal UI.

## Files added

- `app/cli/ui.py`
- `app/cli/beast.tcss`
- `app/cli/__init__.py`
- updated `bin/beast` with:
  - `beast ui`
  - `beast gateway`
  - `beast mcp`
  - `beast mcp-http`

## Install dependencies

```bash
cd /home/byron/Hivenance/edgek_beast_gateway/edgek-beast
. .venv/bin/activate
python -m pip install textual rich httpx
```

Add to requirements:

```bash
grep -q '^textual' requirements.txt 2>/dev/null || cat >> requirements.txt <<'EOF'
textual>=0.85.0
rich>=13.9.0
httpx>=0.27.0
EOF
```

## Apply patch without rsync

```bash
cd /home/byron/Hivenance/edgek_beast_gateway/edgek-beast
unzip -o /mnt/data/EdgeK_BEAST_Textual_UI_Sessions_Patch.zip -d /tmp/beast_ui_patch
cp -a /tmp/beast_ui_patch/. ./
chmod +x bin/beast
```

## Run

Terminal 1:

```bash
./bin/beast gateway --host 127.0.0.1 --port 8000
```

Terminal 2, preferably inside VS Code terminal:

```bash
export BEAST_WORKSPACE="$PWD"
./bin/beast ui --workspace "$PWD"
```

## Notes

This is the first “1:1 Sessions page” TUI shell. It is intentionally focused on the Sessions page first.
The Providers, Tools, Skills, and Diagnostics pages can be wired into the same visual system next.
