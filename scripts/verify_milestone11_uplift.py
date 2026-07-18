#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.kernel.compute.milestone11_uplift import verify_packet


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("packet", type=Path)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    packet = json.loads(args.packet.read_text())
    verify_packet(packet, require_complete=args.require_complete)
    print(json.dumps({"verified": True, "evidence_digest": packet["evidence_digest"], "gates": packet["gates"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

