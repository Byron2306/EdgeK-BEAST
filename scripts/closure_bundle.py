#!/usr/bin/env python3
"""Secret-scanned tar of closure evidence (+ the closure source/deploy files), with sha256.

Scan = (1) known token formats, (2) EXACT values of the keys BEAST holds on disk (.beast/provider_secrets.env,
~/.cache/huggingface/token), compared in memory, never printed. Any hit aborts the bundle and reports file + key NAME.
Never includes .env files, ~/.config/beast, keys/, or *.before-closure-* backups.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / ".beast" / "exports"
PATTERNS = {
    "nvidia": r"nvapi-[A-Za-z0-9_\-]{20,}", "openai": r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{20,}", "hf": r"\bhf_[A-Za-z0-9]{20,}",
    "fireworks": r"\bfw_[A-Za-z0-9]{16,}", "replicate": r"\br8_[A-Za-z0-9]{20,}", "github": r"\bgh[pousr]_[A-Za-z0-9]{30,}",
    "aws": r"\bAKIA[0-9A-Z]{16}\b", "xai": r"\bxai-[A-Za-z0-9]{20,}", "google": r"\bAIza[0-9A-Za-z_\-]{30,}",
    "anthropic": r"\bsk-ant-[A-Za-z0-9_\-]{20,}", "private_key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "bearer": r"Bearer\s+(?!<|\$|\{|xxx|\.\.\.)[A-Za-z0-9_\-\.]{32,}",
}
EXCLUDE = re.compile(r"(^|/)(\.env[^/]*|keys/|.*\.before-closure-\d+.*|__pycache__/)")


def known_values() -> dict[str, str]:
    vals = {}
    env = ROOT / ".beast" / "provider_secrets.env"
    if env.exists():
        for line in env.read_text(errors="replace").splitlines():
            m = re.match(r"\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=\s*['\"]?([^'\"\s]+)", line)
            if m and len(m.group(2)) >= 12:
                vals[m.group(1)] = m.group(2)
    tok = Path.home() / ".cache" / "huggingface" / "token"
    if tok.exists() and len(tok.read_text().strip()) >= 12:
        vals["HF_TOKEN"] = tok.read_text().strip()
    return vals


def collect(paths: list[str]) -> list[Path]:
    files = []
    for p in paths:
        q = ROOT / p
        for f in ([q] if q.is_file() else sorted(q.rglob("*"))):
            rel = f.relative_to(ROOT).as_posix()
            if f.is_file() and not EXCLUDE.search(rel):
                files.append(f)
    return files


def main() -> int:
    paths = sys.argv[1:]
    files = collect(paths)
    secrets = known_values()
    hits = []
    for f in files:
        data = f.read_bytes()
        text = data.decode("utf-8", errors="ignore")
        for name, pat in PATTERNS.items():
            if re.search(pat, text):
                hits.append({"file": f.relative_to(ROOT).as_posix(), "pattern": name})
        for name, val in secrets.items():
            if val in text:
                hits.append({"file": f.relative_to(ROOT).as_posix(), "known_value_of": name})
    report = {"files": len(files), "known_values_checked": sorted(secrets), "patterns": sorted(PATTERNS), "hits": hits}
    if hits:
        print(json.dumps(report, indent=1))
        print("ABORT: secret-scan hits; bundle not written", file=sys.stderr)
        return 3
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"closure-2026-11-16-evidence-{time.strftime('%Y%m%dT%H%M%S')}.tar.gz"
    with tarfile.open(out, "w:gz") as tar:
        for f in files:
            tar.add(f, arcname=f.relative_to(ROOT).as_posix())
        blob = json.dumps({**report, "manifest": {f.relative_to(ROOT).as_posix(): hashlib.sha256(f.read_bytes()).hexdigest() for f in files}}, indent=1).encode()
        info = tarfile.TarInfo("SECRET_SCAN_AND_MANIFEST.json"); info.size = len(blob); info.mtime = int(time.time())
        tar.addfile(info, io.BytesIO(blob))
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    Path(str(out) + ".sha256").write_text(f"{digest}  {out.name}\n")
    print(json.dumps({"tar": str(out), "sha256": digest, "files": len(files), "hits": 0, "known_values_checked": sorted(secrets)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
