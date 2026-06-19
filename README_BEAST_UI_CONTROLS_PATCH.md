# BEAST Textual UI Controls + Providers + Tools Patch

Adds:
- Keyboard controls
- Help overlay on `?` or `h`
- Page switching with `1-0`
- Providers page
- Tools page
- Action hooks for `s`, `p`, `d`, `g`, `m`, `x`, `t`, `e`, `v`
- Updated bottom command strip

## Apply

```bash
cd /home/byron/Hivenance/edgek_beast_gateway/edgek-beast
unzip -o /mnt/data/EdgeK_BEAST_Textual_UI_Controls_Providers_Tools_Patch.zip -d /tmp/beast_ui_controls_patch
cp -a /tmp/beast_ui_controls_patch/. ./
chmod +x bin/beast
```

## Dependencies

```bash
. .venv/bin/activate
python -m pip install textual rich httpx
```

## Run

Terminal 1:
```bash
./bin/beast gateway --host 127.0.0.1 --port 8000
```

Terminal 2:
```bash
export BEAST_WORKSPACE="$PWD"
./bin/beast ui --workspace "$PWD"
```

## Controls

```text
? / h    Help overlay
q        Quit
r        Refresh health

1        Sessions
2        Providers
3        Tools
4        Skills
5        Plugins
6        Policies
7        Routes
8        Chronicle
9        Diagnostics
0        Settings

s        Start session hook
p        Prepare handoff hook
d        Run diagnostics hook
g        Check gateway
m        Check MCP
x        Check proxy
t        Test selected provider/tool hook
e        Edit selected provider/tool hook
v        View selected schema/details hook
ctrl+k   Command palette placeholder
```
