#!/usr/bin/env python3
"""Teach BEAST a deterministic visual style capsule from a reference image."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.dai.visual_style_capsule import teach_visual_style_from_reference, write_visual_style_capsule


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract a bounded BEAST visual style capsule from a reference image.")
    parser.add_argument("reference_image", type=Path)
    parser.add_argument("--capsule-id", default="phase7:visual-style:reference")
    parser.add_argument("--out", type=Path, default=ROOT / "evidence/dai-diode/phase7-runtime/visual_style_capsule.json")
    args = parser.parse_args()

    capsule = teach_visual_style_from_reference(args.reference_image, capsule_id=args.capsule_id)
    write_visual_style_capsule(args.out, capsule)
    print(json.dumps({
        "beast_object_type": capsule.beast_object_type,
        "capsule_id": capsule.capsule_id,
        "capsule_digest": capsule.capsule_digest,
        "reference_image_digest": capsule.reference_image_digest,
        "palette": capsule.palette,
        "out": str(args.out),
        "nonclaims": capsule.nonclaims,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
