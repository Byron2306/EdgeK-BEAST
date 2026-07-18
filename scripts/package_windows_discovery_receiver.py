#!/usr/bin/env python3
"""Create a sanitized Windows receiver zip from the current checkout."""
from pathlib import Path
import argparse, zipfile

INCLUDE = ("app/", "scripts/run_discovery_agnostic_receiver.py", "scripts/windows_receiver_local_verifier.py", "scripts/setup_beast_windows_discovery_receiver.ps1", "docs/windows-discovery-receiver-runbook.md", "requirements.txt")
EXCLUDE = (".git", ".beast", "__pycache__", ".pytest_cache", "private", "secret")
def main():
    p=argparse.ArgumentParser(); p.add_argument("--output", default="dist/beast-windows-discovery-receiver.zip"); a=p.parse_args()
    root=Path(__file__).resolve().parents[1]; out=root/a.output; out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for item in INCLUDE:
            path=root/item
            paths=path.rglob("*") if path.is_dir() else [path]
            for f in paths:
                if f.is_file() and not any(x in f.parts for x in EXCLUDE): z.write(f, f.relative_to(root))
    print(out)
if __name__ == "__main__": main()
