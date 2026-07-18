# BEAST IDE 3.1.0-rc3 quick start

## Preview in a browser

```bash
cd BEAST_IDE_v3.1.0_RC3
python3 -m http.server 8765
```

Open `http://127.0.0.1:8765/index.html`.

## Electron renderer

Point the BEAST `BrowserWindow` at this folder's `index.html`. The renderer expects Monaco at `../node_modules/monaco-editor/min/vs/loader.js`; keep the renderer one directory below the project root or adjust that script path.

## Useful keys

- `Ctrl/Cmd + K`: focus the command dock
- `Ctrl/Cmd + Shift + L`: display and motion controls
- `Ctrl/Cmd + Shift + D`: download release diagnostics
- `F6`: cycle major interface regions
- `Alt + Left/Right`: navigate pages
