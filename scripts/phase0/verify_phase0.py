#!/usr/bin/env python3
"""One-command Phase 0 verification entrypoint."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_CONTRACTS = [
    "beast-parity-contract.v1.yaml",
    "execution-target-matrix.v1.yaml",
    "extension-compatibility.v1.yaml",
    "language-adapter-matrix.v1.yaml",
    "debugger-adapter-matrix.v1.yaml",
    "test-adapter-matrix.v1.yaml",
    "agent-tool-policy.v1.yaml",
]


def call(*args: str) -> dict[str, object]:
    result = subprocess.run(args, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return {"ok": result.returncode == 0, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}


def main() -> int:
    failures: list[str] = []
    loaded: list[str] = []
    for name in REQUIRED_CONTRACTS:
        path = ROOT / "contracts" / name
        if not path.exists():
            failures.append(f"missing contracts/{name}")
            continue
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or not payload.get("schema_version"):
                failures.append(f"contracts/{name} has no schema_version")
            else:
                loaded.append(name)
        except Exception as exc:  # YAML diagnostics belong in the report.
            failures.append(f"contracts/{name}: {exc}")

    identity = call(sys.executable, "scripts/phase0/generate_build_identity.py", "--check")
    imports = call(sys.executable, "scripts/phase0/check_canonical_imports.py")
    if not identity["ok"]:
        failures.append("generated build identity is stale")
    if not imports["ok"]:
        failures.append("deprecated compatibility import used by production code")

    result = {
        "ok": not failures,
        "contracts_loaded": loaded,
        "build_identity": identity,
        "canonical_imports": imports,
        "failures": failures,
    }
    print(json.dumps(result, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
