# BEAST IDE RC4 acceptance

The folder contains two evidence layers:

1. Pre-generated RC4 visual metrics and contact sheets from the automated CDP harness.
2. `release-runner.html` for a fresh browser/Electron-adjacent operator run.

Serve the release root:

```bash
python3 -m http.server 8765
```

Open `http://127.0.0.1:8765/acceptance/release-runner.html`, run all pages and retain `BEAST_IDE_RC4_RUNTIME_MATRIX.json`.
