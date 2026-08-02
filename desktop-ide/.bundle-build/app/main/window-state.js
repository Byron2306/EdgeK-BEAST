'use strict';

const fs = require('fs');
const path = require('path');

const DEFAULT_WINDOW_BOUNDS = Object.freeze({ width: 1560, height: 980, minWidth: 1180, minHeight: 760 });

function createWindowStateStore({ app, screen, appendLog = () => {}, debounceMs = 220, defaults = DEFAULT_WINDOW_BOUNDS }) {
  let writeTimer = null;
  const statePath = () => path.join(app.getPath('userData'), 'beast-desktop-window-state.json');

  function read() {
    try {
      const raw = JSON.parse(fs.readFileSync(statePath(), 'utf8'));
      const width = Math.max(defaults.minWidth, Number(raw.width) || defaults.width);
      const height = Math.max(defaults.minHeight, Number(raw.height) || defaults.height);
      const candidate = { width, height, x: Number.isFinite(raw.x) ? raw.x : undefined, y: Number.isFinite(raw.y) ? raw.y : undefined, maximized: Boolean(raw.maximized) };
      const visible = screen.getAllDisplays().some(display => {
        const area = display.workArea; const x = candidate.x ?? area.x; const y = candidate.y ?? area.y;
        return x + Math.min(width, 80) > area.x && x < area.x + area.width && y + Math.min(height, 80) > area.y && y < area.y + area.height;
      });
      return visible ? candidate : { width, height, maximized: candidate.maximized };
    } catch (_) { return { ...defaults, maximized: false }; }
  }

  function persist(windowRef) {
    if (!windowRef || windowRef.isDestroyed()) return;
    const bounds = windowRef.isMaximized() ? windowRef.getNormalBounds() : windowRef.getBounds();
    const state = { x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height, maximized: windowRef.isMaximized() };
    try {
      fs.mkdirSync(path.dirname(statePath()), { recursive: true });
      fs.writeFileSync(statePath(), JSON.stringify(state));
    } catch (error) { appendLog(`window state persistence failed: ${error.message || error}`); }
  }

  function schedule(windowRef) {
    clearTimeout(writeTimer);
    writeTimer = setTimeout(() => persist(windowRef), debounceMs);
  }

  function dispose() { clearTimeout(writeTimer); writeTimer = null; }
  return { defaults, path: statePath, read, persist, schedule, dispose };
}

module.exports = { DEFAULT_WINDOW_BOUNDS, createWindowStateStore };
