#!/usr/bin/env python3
"""Verify the live ARDA Guardian endpoint without exposing credentials."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.execution.guardian_uvicorn import GuardianOperationCapabilityProvider
from app.kernel.execution.process_identity import LinuxProcessIdentityCollector
from app.kernel.integration.arda_metatron_bridge import SignedJsonHttpAuthorizer
from app.kernel.networking.service_registry import ServiceRegistry


def main() -> int:
    config_root = Path(os.environ.get("BEAST_GUARDIAN_CONFIG_ROOT") or "~/.config/beast").expanduser()
    guardian = yaml.safe_load((config_root / "socket-guardian.yaml").read_text())["guardian"]
    binding = guardian["systemd_bindings"]["beast"]
    registry = ServiceRegistry.from_file(guardian["service_registry"])
    token = (config_root / "guardian-authorization.token").read_text().strip()
    authorizer = SignedJsonHttpAuthorizer(
        "http://127.0.0.1:18401/authorize/socket-guardian",
        str(config_root / "arda-operation-ed25519.pub.pem"),
        authority="arda",
        expected_audience="beast-socket-guardian",
        expected_policy_generation=binding["policy_generation"],
        expected_appraisal_ref=binding["appraisal_ref"],
        headers={"Authorization": f"Bearer {token}"},
    )
    request = {
        "op": "recover",
        "lease_id": "portlease:" + "0" * 64,
        "workspace_id": binding["workspace_id"],
        "capability_ref": binding["capability_ref"],
        "appraisal_ref": binding["appraisal_ref"],
        "policy_generation": binding["policy_generation"],
        "registry_digest": registry.digest(),
        "process_lease": LinuxProcessIdentityCollector().collect(
            os.getpid(), owner_scope="beast-guardian-socket-consumer"
        ).to_dict(),
    }
    decision = GuardianOperationCapabilityProvider(authorizer)(request)
    print(json.dumps({
        "allowed": True,
        "authority": decision.get("authority"),
        "audience": decision.get("audience"),
        "appraisal_ref": decision.get("appraisal_ref"),
        "capability_id": decision.get("capability_id"),
        "expires_at": decision.get("expires_at"),
        "request_digest": decision.get("request_digest"),
    }, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
