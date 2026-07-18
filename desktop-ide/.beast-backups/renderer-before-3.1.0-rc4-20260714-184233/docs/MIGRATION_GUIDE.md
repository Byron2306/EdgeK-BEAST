# RC4 migration guide

1. Close BEAST and all renderer preview tabs.
2. Identify the current renderer folder containing `index.html`, `css/`, `js/` and `assets/`.
3. Run `INSTALL_BEAST_IDE_RC4.sh /path/to/renderer` from the extracted full release, or use the smaller RC4 patch installer.
4. The installer creates a timestamped sibling backup before replacement.
5. Fully restart Electron so old CSS and animation loops cannot survive in memory.
6. Run `VERIFY_BEAST_IDE_RC4.sh /path/to/renderer`.
7. Complete `docs/RUNTIME_ACCEPTANCE_CHECKLIST.md`.

Rollback uses `ROLLBACK_BEAST_IDE_RC4.sh /path/to/renderer`. Without an explicit backup path it restores the newest RC4 backup.
