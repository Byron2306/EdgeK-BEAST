from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .grand_closure_g9 import Ed25519RootSigner, GrandClosureG9, verify_bundle_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or verify the BEAST Grand Closure G9 evidence bundle")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("evidence_dir")
    build.add_argument("--output-dir")
    build.add_argument("--key-file")
    build.add_argument("--signer-id", default="beast:grand-closure:g9")
    build.add_argument("--ephemeral-sign", action="store_true")
    build.add_argument("--require-signature", action="store_true")
    verify = sub.add_parser("verify")
    verify.add_argument("bundle")
    args = parser.parse_args()

    if args.command == "verify":
        result = verify_bundle_file(args.bundle)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["bundle_valid"] else 2

    signer = None
    if args.key_file:
        signer = Ed25519RootSigner.from_private_key_file(args.key_file, signer_id=args.signer_id)
    elif args.ephemeral_sign:
        signer = Ed25519RootSigner.generate(signer_id=args.signer_id + ":ephemeral")
    plane = GrandClosureG9(evidence_dir=args.evidence_dir, output_dir=args.output_dir)
    bundle = plane.build(signer=signer, require_signature=args.require_signature)
    path = plane.write(bundle)
    print(json.dumps({"path": str(path), **asdict(bundle.validation), "bundle_digest": bundle.bundle_digest,
                      "merkle_root": bundle.merkle_root, "signed": signer is not None}, indent=2, sort_keys=True))
    return 0 if bundle.validation.valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
