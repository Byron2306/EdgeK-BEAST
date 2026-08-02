#!/usr/bin/env python3
"""Generate a truthful Phase 0 capability and contract status report."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "contracts" / "beast-parity-contract.v1.yaml"
OUTPUT = ROOT / "build" / "PHASE0_STATUS.json"


def run(command: list[str], timeout: int = 45) -> dict[str, Any]:
    stdout_file = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
    stderr_file = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=stdout_file,
            stderr=stderr_file,
            timeout=timeout,
            check=False,
        )
        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout_text = stdout_file.read()
        stderr_text = stderr_file.read()
        payload: Any = None
        text = stdout_text.strip()
        if text:
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = text[-8000:]
        return {
            "status": "passed" if completed.returncode == 0 else "failed",
            "returncode": completed.returncode,
            "payload": payload,
            "stderr": stderr_text.strip()[-4000:],
        }
    finally:
        stdout_file.close()
        stderr_file.close()


def report_artifact(path: Path, command: str) -> dict[str, Any]:
    if not path.exists():
        return {"status": "not_run", "reason": f"Run `{command}` to generate {path.relative_to(ROOT)}."}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {"status": "failed", "reason": f"invalid report artifact: {exc}"}
    return {
        "status": "passed" if payload.get("ok") is True else "failed",
        "returncode": 0 if payload.get("ok") is True else 1,
        "payload": payload,
        "artifact": str(path.relative_to(ROOT)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    identity = json.loads((ROOT / "build" / "BUILD_IDENTITY.json").read_text(encoding="utf-8"))
    capabilities = contract.get("capabilities", [])
    status_counts: dict[str, int] = {}
    for capability in capabilities:
        status = str(capability.get("status", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1

    checks: dict[str, Any] = {
        "build_identity": run([sys.executable, "scripts/phase0/generate_build_identity.py", "--check"]),
        "canonical_imports": run([sys.executable, "scripts/phase0/check_canonical_imports.py"]),
        "enterprise_runtime_contract": run(["node", "desktop-ide/scripts/verify-enterprise-runtime-contract.js"]),
        "execution_target_contract": report_artifact(
            ROOT / "build" / "EXECUTION_TARGET_PARITY.json",
            "cd desktop-ide && npm run smoke:targets",
        ),
        "local_parity_foundation": report_artifact(
            ROOT / "build" / "PARITY_FOUNDATION.json",
            "cd desktop-ide && npm run smoke:parity:foundation",
        ),
        "full_local_parity": {
            "status": "not_run",
            "reason": "Run `cd desktop-ide && BEAST_VERIFY_LSP=1 BEAST_VERIFY_DAP=1 BEAST_VERIFY_KERNEL=1 npm run smoke:parity` on a provisioned runtime.",
        },
    }

    failed = [name for name, result in checks.items() if result.get("status") in {"failed", "timeout"}]
    report = {
        "schema": "beast.phase0-status.v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "release_id": identity["release_id"],
        "identity_digest": identity["identity_digest"],
        "contract_id": contract["contract_id"],
        "contract_schema_version": contract["schema_version"],
        "capabilities": {"total": len(capabilities), "by_status": status_counts},
        "checks": checks,
        "failed_checks": failed,
        "status": "PASS" if not failed else "FAIL",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
