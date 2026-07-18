#!/usr/bin/env python3
"""Collect a fresh, non-persistent TPM validation packet for BEAST."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.integration.tpm_validation import collect_local_tpm_evidence


def _default_output() -> Path:
    state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return state / "beast" / "tpm-validation-latest.json"


def _default_vendor_pcr_baseline() -> str:
    configured = os.environ.get("BEAST_TPM_VENDOR_PCR_BASELINE", "").strip()
    if configured:
        return configured
    candidate = (
        ROOT
        / "docs"
        / "evidence"
        / "tpm"
        / "vendor-baselines"
        / "hp-probook-450-g10-v72-01110000"
        / "History.txt"
    )
    return str(candidate) if candidate.is_file() else ""


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--node-id", default="beast-local-workstation")
    parser.add_argument("--challenge-id", default="")
    parser.add_argument("--nonce", default="")
    parser.add_argument("--root-certificate")
    parser.add_argument("--intermediate-certificate")
    parser.add_argument("--firmware-event-log", default="/sys/kernel/security/tpm0/binary_bios_measurements")
    parser.add_argument("--ima-measurements")
    parser.add_argument("--vendor-pcr-baseline", default=_default_vendor_pcr_baseline())
    parser.add_argument(
        "--makecredential-image",
        default=os.environ.get("BEAST_TPM_MAKECREDENTIAL_IMAGE", "beast-tpm2-makecredential:local-validation"),
    )
    parser.add_argument("--output", type=Path, default=_default_output())
    arguments = parser.parse_args()
    evidence = collect_local_tpm_evidence(
        node_id=arguments.node_id,
        challenge_id=arguments.challenge_id,
        nonce=arguments.nonce,
        root_certificate=arguments.root_certificate,
        intermediate_certificate=arguments.intermediate_certificate,
        firmware_event_log=arguments.firmware_event_log,
        ima_measurements=arguments.ima_measurements,
        vendor_pcr_baseline=arguments.vendor_pcr_baseline,
        makecredential_image=arguments.makecredential_image,
    )
    _write_atomic(arguments.output.expanduser(), (json.dumps(evidence, indent=2, sort_keys=True) + "\n").encode())
    print(json.dumps({
        "output": str(arguments.output.expanduser()),
        "status": evidence["status"],
        "eligible_for_commons": evidence["eligible_for_commons"],
        "evidence_digest": evidence["evidence_digest"],
        "blockers": evidence["blockers"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
