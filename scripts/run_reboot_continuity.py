#!/usr/bin/env python3
"""Prepare or complete a real BEAST reboot-continuity proof."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.kernel.execution.reboot_continuity import (
    ContinuityPaths, create_preboot_witness, verify_postboot, write_receipt,
)


def defaults() -> dict[str, Path]:
    state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "beast"
    plane = ROOT / "app/data/compute_plane"
    return {
        "tpm": state / "tpm-validation-latest.json",
        "arda": state / "commons-tpm-appraisal-latest.json",
        "guardian": state / "socket-guardian-leases.sqlite3",
        "capabilities": state / "socket-guardian-capabilities.sqlite3",
        "sensorium": plane / "sensorium.jsonl",
        "promotions": plane / "physical_registry.json",
        "private_key": Path.home() / ".config/beast/guardian-receipt-ed25519.pem",
        "public_key": Path.home() / ".config/beast/guardian-receipt-ed25519.pub.pem",
        "preboot": state / "reboot-continuity/preboot.json",
        "receipt": state / "reboot-continuity/receipt.json",
    }


def paths(args) -> ContinuityPaths:
    return ContinuityPaths(args.tpm, args.arda, args.guardian, args.capabilities, args.sensorium, args.promotions)


def parser() -> argparse.ArgumentParser:
    d = defaults(); p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)
    for command in ("prepare", "verify"):
        item = sub.add_parser(command)
        for name in ("tpm", "arda", "guardian", "capabilities", "sensorium", "promotions"):
            item.add_argument(f"--{name}", type=Path, default=d[name])
        item.add_argument("--preboot", type=Path, default=d["preboot"])
        if command == "prepare":
            item.add_argument("--private-key", type=Path, default=d["private_key"])
        else:
            item.add_argument("--public-key", type=Path, default=d["public_key"])
            item.add_argument("--recurrence-receipt", type=Path, required=True)
            item.add_argument("--output", type=Path, default=d["receipt"])
    return p


def main() -> int:
    args = parser().parse_args()
    if args.command == "prepare":
        signer = serialization.load_pem_private_key(args.private_key.read_bytes(), password=None)
        witness = create_preboot_witness(paths(args), signer=signer)
        write_receipt(args.preboot, witness)
        print(json.dumps({"prepared": True, "boot_id": witness["boot_id"], "witness_digest": witness["witness_digest"], "output": str(args.preboot)}, sort_keys=True))
        return 0
    verifier = serialization.load_pem_public_key(args.public_key.read_bytes())
    preboot = json.loads(args.preboot.read_text(encoding="utf-8"))
    recurrence = json.loads(args.recurrence_receipt.read_text(encoding="utf-8"))
    receipt = verify_postboot(preboot, paths(args), verifier=verifier, recurrence_receipt=recurrence)
    write_receipt(args.output, receipt)
    print(json.dumps({"verified": True, "receipt_digest": receipt["receipt_digest"], "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
