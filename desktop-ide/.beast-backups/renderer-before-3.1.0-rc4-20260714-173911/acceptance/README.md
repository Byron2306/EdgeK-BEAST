# BEAST IDE RC3 acceptance runner

Serve the release root over HTTP and open `acceptance/release-runner.html`.

```bash
python3 -m http.server 8765
```

Run the complete matrix and download `BEAST_IDE_RC3_RUNTIME_MATRIX.json`. The matrix covers 22 routes across 5 viewport profiles (110 structural scenarios).
