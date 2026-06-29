"""Deterministic and allowlisted verifier replay for BEAST Compute Spaces."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.kernel.networking.commons_privacy import CommonsPrivacyScrubber
from app.kernel.security.crystal_seal import canonical_bytes, seal_crystal_payload


class CommonsReplayEngine:
    def __init__(self, registry: Any, workspace_root: Optional[Path] = None):
        self.registry = registry
        self.workspace_root = (workspace_root or Path(__file__).resolve().parents[2]).resolve()
        self.scrubber = CommonsPrivacyScrubber()
        self.receipts_dir = self.registry.root / "reproductions"

    def replay(
        self,
        space_id: str,
        *,
        target: Optional[Path] = None,
        deterministic_only: bool = True,
        approved: bool = False,
        timeout_seconds: int = 120,
        contributor_id: str = "local",
    ) -> Dict[str, Any]:
        detail = self.registry.get(space_id)
        root = self.registry.root / space_id
        paths = [item["path"] for item in detail["manifest"].get("artifacts") or []]
        privacy = self.scrubber.scan_space(root, paths)
        deterministic = {
            "manifest_valid": bool(detail["manifest_validation"].get("valid")),
            "receipt_valid": bool(detail["receipt_validation"].get("valid")),
            "privacy_safe": bool(privacy.get("safe")),
        }
        commands: List[Dict[str, Any]] = []
        live_passed: Optional[bool] = None
        if not deterministic_only:
            if not approved:
                raise ValueError("live verifier replay requires explicit approval")
            if target is None:
                raise ValueError("live verifier replay requires a local target")
            target = target.resolve()
            if self.workspace_root != target and self.workspace_root not in target.parents:
                raise ValueError("replay target must be inside the local workspace")
            if not target.is_dir():
                raise ValueError("replay target must be an existing directory")
            for bundle in detail["manifest"].get("verifier_bundles") or []:
                expected = int(bundle.get("expected_returncode", 0))
                for command in bundle.get("commands") or []:
                    argv = self._allowlisted_command(str(command))
                    started = time.perf_counter()
                    completed = subprocess.run(
                        argv,
                        cwd=str(target),
                        capture_output=True,
                        text=True,
                        timeout=max(1, min(int(timeout_seconds), 300)),
                        check=False,
                        env=self._minimal_env(),
                    )
                    commands.append({
                        "command": argv,
                        "returncode": completed.returncode,
                        "expected_returncode": expected,
                        "passed": completed.returncode == expected,
                        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                        "stdout_hash": "sha256:" + hashlib.sha256(completed.stdout.encode()).hexdigest(),
                        "stderr_hash": "sha256:" + hashlib.sha256(completed.stderr.encode()).hexdigest(),
                    })
            live_passed = bool(commands) and all(item["passed"] for item in commands)
        deterministic_passed = all(deterministic.values())
        trust_score = 0.0
        trust_score += 0.35 if deterministic["manifest_valid"] else 0.0
        trust_score += 0.25 if deterministic["receipt_valid"] else 0.0
        trust_score += 0.15 if deterministic["privacy_safe"] else 0.0
        trust_score += 0.25 if live_passed is True else 0.0
        result = {
            "beast_object_type": "commons_space_reproduction_receipt",
            "version": "1.0",
            "space_id": space_id,
            "manifest_hash": detail["manifest"].get("manifest_hash"),
            "contributor_id": contributor_id,
            "mode": "deterministic" if deterministic_only else "live_verifier",
            "deterministic": deterministic,
            "privacy": privacy,
            "commands": commands,
            "deterministic_passed": deterministic_passed,
            "live_verifier_passed": live_passed,
            "reproduced": bool(deterministic_passed and (deterministic_only or live_passed)),
            "trust_score": round(trust_score, 6),
            "trust_class": "locally_reproduced" if live_passed else "integrity_reproduced" if deterministic_passed else "untrusted",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        result["reproduction_id"] = "repro_" + hashlib.sha256(canonical_bytes(result)).hexdigest()[:20]
        result["local_seal"] = seal_crystal_payload(result, purpose="commons_space_reproduction")
        self.receipts_dir.mkdir(parents=True, exist_ok=True)
        path = self.receipts_dir / f"{result['reproduction_id']}.json"
        path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        result["receipt_path"] = str(path)
        return result

    def list_reproductions(self, space_id: Optional[str] = None) -> List[Dict[str, Any]]:
        rows = []
        for path in sorted(self.receipts_dir.glob("*.json")) if self.receipts_dir.exists() else []:
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not space_id or row.get("space_id") == space_id:
                rows.append(row)
        return rows

    @staticmethod
    def _allowlisted_command(command: str) -> List[str]:
        argv = shlex.split(command)
        if not argv or any(token in command for token in (";", "&&", "||", "|", ">", "<", "`", "$(")):
            raise ValueError("verifier command contains a forbidden shell construct")
        executable = Path(argv[0]).name
        if executable in {"python", "python3"}:
            if len(argv) < 3 or argv[1:3] not in (["-m", "pytest"], ["-m", "py_compile"]):
                raise ValueError("only python -m pytest and python -m py_compile are allowlisted")
            argv[0] = sys.executable
        elif executable == "pytest":
            argv[0] = sys.executable
            argv[1:1] = ["-m", "pytest"]
        else:
            raise ValueError("verifier executable is not allowlisted")
        for arg in argv[3:]:
            if arg.startswith("/") or ".." in Path(arg).parts:
                raise ValueError("verifier arguments must stay inside the replay target")
        return argv

    @staticmethod
    def _minimal_env() -> Dict[str, str]:
        return {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
            "NO_PROXY": "*",
        }
