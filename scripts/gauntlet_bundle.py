#!/usr/bin/env python3
"""Bundle gauntlet evidence into a tar.gz with a sha256 MANIFEST and a secret scan (never includes keys)."""
from __future__ import annotations

import argparse
import hashlib
import io
import os
import re
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DENY_NAMES = re.compile(r"(^\.env|\.env$|secret|token|\.pem$|\.key$|id_rsa|id_ed25519|credentials)", re.I)
DENY_CONTENT = [re.compile(p) for p in (rb"-----BEGIN [A-Z ]*PRIVATE KEY-----", rb"nvapi-[A-Za-z0-9_\-]{20,}",
                                        rb"\bhf_[A-Za-z0-9]{30,}", rb"\bsk-[A-Za-z0-9]{32,}", rb"ghp_[A-Za-z0-9]{30,}")]
CODE_ALLOW = {"app/kernel/security/secret_vault.py"}  # code that names secret files but holds no secret


def secret_values() -> list[bytes]:
    try:
        sys.path.insert(0, str(ROOT))
        from app.kernel.security.secret_vault import SecretVault
        SecretVault().load(override=False)
    except Exception:  # noqa: BLE001
        pass
    vals = [os.environ.get(k, "") for k in os.environ if re.search(r"(API_KEY|TOKEN|SECRET)$", k)]
    return [v.encode() for v in vals if len(v) >= 12]


def collect(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        path = (ROOT / p)
        if not path.exists():
            raise SystemExit(f"missing: {p}")
        files = [path] if path.is_file() else sorted(x for x in path.rglob("*") if x.is_file())
        out += [f for f in files if "__pycache__" not in f.parts]
    return sorted(set(out))


def scan(files: list[Path], values: list[bytes]) -> list[str]:
    hits = []
    for f in files:
        rel = str(f.relative_to(ROOT))
        if rel.startswith(".config") or "/.config/beast" in str(f):
            hits.append(f"{rel}: private config path")
        if DENY_NAMES.search(f.name) and rel not in CODE_ALLOW:
            hits.append(f"{rel}: denied filename")
        data = f.read_bytes()
        hits += [f"{rel}: secret pattern" for rx in DENY_CONTENT if rx.search(data)]
        hits += [f"{rel}: live secret value" for v in values if v in data]
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--readme", required=True)
    ap.add_argument("paths", nargs="+")
    a = ap.parse_args()
    files = collect(a.paths)
    readme = Path(a.readme).read_bytes()
    hits = scan(files, secret_values())
    if hits:
        print("REFUSED:\n" + "\n".join(hits))
        return 3
    manifest = "".join(f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.relative_to(ROOT)}\n" for f in files)
    manifest = f"{hashlib.sha256(readme).hexdigest()}  BUNDLE_README.md\n" + manifest
    prefix = Path(a.out).name.removesuffix(".tar.gz")
    with tarfile.open(a.out, "w:gz") as tar:
        for name, data in (("BUNDLE_README.md", readme), ("MANIFEST.sha256", manifest.encode())):
            info = tarfile.TarInfo(f"{prefix}/{name}"); info.size = len(data); info.mtime = int(time.time()); info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
        for f in files:
            tar.add(f, arcname=f"{prefix}/{f.relative_to(ROOT)}", recursive=False)
    digest = hashlib.sha256(Path(a.out).read_bytes()).hexdigest()
    print(f"files={len(files) + 2} size={Path(a.out).stat().st_size} sha256={digest} secret_scan=clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
