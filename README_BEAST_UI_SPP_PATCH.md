# BEAST Textual UI Skills + Plugins + Policies + Sprite Patch

Adds:
- Skills page
- Plugins page
- Policies page
- Better terminal-native BEAST mascot in the header
- PNG sprite assets in `app/cli/assets/`
- `a` and `b` action hooks for promote/approve and reject/block

## Apply

```bash
cd /home/byron/Hivenance/edgek_beast_gateway/edgek-beast
unzip -o /mnt/data/EdgeK_BEAST_Textual_UI_Skills_Plugins_Policies_Sprite_Patch.zip -d /tmp/beast_ui_spp_patch
cp -a /tmp/beast_ui_spp_patch/. ./
chmod +x bin/beast
```

## Run

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
t        Test selected item
e        Edit selected item
v        View selected schema/details
a        Approve/promote depending on page
b        Block/reject depending on page
ctrl+k   Command palette placeholder
```

## Sprite note

The TUI header uses a terminal-safe pixel/block mascot so it works reliably in VS Code terminals.
The original PNG-style sprite sheet is included at:

```text
app/cli/assets/cybernetic_beast_sprite_sheet_in_pixels.png
```

That asset can later be used in a VS Code webview, dashboard splash, README artwork, or optional terminal image renderer.
