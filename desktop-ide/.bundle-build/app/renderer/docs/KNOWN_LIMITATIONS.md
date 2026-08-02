# Known limitations

- Monaco is referenced from the parent project's `node_modules`; it is not bundled in this renderer.
- Hacker-style web fonts load from Google Fonts. Offline mode uses technical local fallbacks; no font files are included.
- Automated CDP visual acceptance validates renderer geometry and animations but not live Electron preload or gateway mutations.
- Live IPC, terminal streaming, SourcePlan apply, provider actions and worktree operations require the actual BEAST desktop environment.
- Browser capture mode uses seeded local state and cannot validate destructive or mutating operations.
