# Migration guide

1. Close BEAST and all preview tabs.
2. Identify the current renderer folder containing `index.html`, `css/`, `js/`, and `assets/`.
3. Run `INSTALL_BEAST_IDE_RC3.sh /path/to/renderer` from the extracted release root.
4. The installer creates a timestamped sibling backup before replacing the renderer.
5. Fully restart Electron.
6. Run `VERIFY_BEAST_IDE_RC3.sh /path/to/renderer`.
7. Complete `docs/RUNTIME_ACCEPTANCE_CHECKLIST.md`.

Rollback uses `ROLLBACK_BEAST_IDE_RC3.sh /path/to/renderer`. By default it restores the newest backup.
