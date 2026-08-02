#!/usr/bin/env python3
"""Generate one release identity for backend, desktop, renderer, and evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DESKTOP = ROOT / "desktop-ide"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def regex_value(path: Path, pattern: str, default: str) -> str:
    match = re.search(pattern, path.read_text(encoding="utf-8"))
    return match.group(1) if match else default


def git_value(*args: str, default: str = "unavailable") -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), *args],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        value = result.stdout.strip()
        return value if result.returncode == 0 and value else default
    except (OSError, subprocess.SubprocessError):
        return default


def build_timestamp() -> str:
    source_date_epoch = os.environ.get("SOURCE_DATE_EPOCH", "").strip()
    if source_date_epoch.isdigit():
        instant = datetime.fromtimestamp(int(source_date_epoch), tz=timezone.utc)
    else:
        instant = datetime.now(timezone.utc)
    return instant.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_digest(payload: dict[str, Any]) -> str:
    stable = {key: value for key, value in payload.items() if key not in {"build_timestamp", "identity_digest"}}
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def create_identity() -> dict[str, Any]:
    package = read_json(DESKTOP / "package.json")
    declared = read_json(ROOT / "release" / "RELEASE_VERSION.json")
    if declared.get("schema") != "beast.release-version.v1":
        raise ValueError("release/RELEASE_VERSION.json has an unsupported schema")
    desktop_build = str(declared["desktop_runtime_build"])
    product_version = str(declared["product_version"])
    release_id = str(declared["release_id"])
    codename = str(declared["codename"])
    desktop_runtime_version = str(declared["desktop_runtime_version"])
    backend_gateway_version = str(declared["backend_gateway_version"])
    if str(package.get("version")) != desktop_runtime_version:
        raise ValueError(
            f"desktop-ide/package.json version {package.get('version')} does not match declared "
            f"desktop runtime version {desktop_runtime_version}"
        )
    git_commit = git_value("rev-parse", "HEAD")
    dirty = git_value("status", "--porcelain", default="")
    branch = git_value("branch", "--show-current")
    identity: dict[str, Any] = {
        "schema": "beast.build-identity.v1",
        "product": str(declared["product"]),
        "product_version": product_version,
        "codename": codename,
        "release_id": release_id,
        "desktop_package_version": package.get("version", "unavailable"),
        "desktop_runtime_version": desktop_runtime_version,
        "desktop_runtime_build": desktop_build,
        "backend_gateway_version": backend_gateway_version,
        "backend_api_version": str(declared["backend_api_version"]),
        "agent_contract_version": str(declared["agent_contract_version"]),
        "sourceplan_schema_version": str(declared["sourceplan_schema_version"]),
        "sensorium_schema_version": str(declared["sensorium_schema_version"]),
        "parity_contract_version": str(declared["parity_contract_version"]),
        "git_commit": git_commit,
        "git_short_commit": git_commit[:12] if git_commit != "unavailable" else "unavailable",
        "git_branch": branch,
        "git_dirty": bool(dirty),
        "build_timestamp": build_timestamp(),
    }
    identity["identity_digest"] = stable_digest(identity)
    return identity


def renderer_module(identity: dict[str, Any]) -> str:
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return (
        "(() => {\n"
        "  'use strict';\n"
        f"  const identity = Object.freeze({encoded});\n"
        "  window.BEAST_BUILD_IDENTITY = identity;\n"
        "})();\n"
    )


def write_identity(identity: dict[str, Any]) -> list[Path]:
    targets = [ROOT / "build" / "BUILD_IDENTITY.json", DESKTOP / "BUILD_IDENTITY.json"]
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(identity, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    renderer_target = DESKTOP / "renderer" / "js" / "generated" / "beast-build-identity.js"
    renderer_target.parent.mkdir(parents=True, exist_ok=True)
    renderer_target.write_text(renderer_module(identity), encoding="utf-8")
    return [*targets, renderer_target]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Validate existing generated identities without rewriting them.")
    args = parser.parse_args()
    expected = create_identity()
    if not args.check:
        targets = write_identity(expected)
        print(json.dumps({"ok": True, "identity": expected, "written": [str(path.relative_to(ROOT)) for path in targets]}, indent=2))
        return 0

    failures: list[str] = []
    for target in [ROOT / "build" / "BUILD_IDENTITY.json", DESKTOP / "BUILD_IDENTITY.json"]:
        if not target.exists():
            failures.append(f"missing {target.relative_to(ROOT)}")
            continue
        actual = read_json(target)
        for key in (
            "schema", "product", "product_version", "release_id", "desktop_runtime_build",
            "parity_contract_version", "identity_digest",
        ):
            if actual.get(key) != expected.get(key):
                failures.append(f"{target.relative_to(ROOT)}: {key} is stale")
    renderer_target = DESKTOP / "renderer" / "js" / "generated" / "beast-build-identity.js"
    if not renderer_target.exists():
        failures.append(f"missing {renderer_target.relative_to(ROOT)}")
    print(json.dumps({"ok": not failures, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
