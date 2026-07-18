# Known limitations

- Monaco is referenced from the parent project's `node_modules`; it is not bundled in this renderer.
- Hacker-style web fonts are loaded from Google Fonts. When offline, the renderer uses technical local fallbacks; no font files are included in this package.
- Live IPC and gateway acceptance requires the actual BEAST Electron main/preload environment.
- Browser capture mode uses seeded local state and cannot validate mutating gateway operations.
