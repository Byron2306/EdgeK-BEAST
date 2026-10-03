#!/usr/bin/env python3
"""Talk to the Phase-7 constitutional BEAST runtime."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.deterministic_intelligence import canonical_json
from app.kernel.dai.constitutional_runtime_router import (
    BeastRuntimeContext,
    BeastRuntimeRequest,
    load_default_runtime_context,
    route_beast_runtime_request,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Speak to/draw with BEAST through the constitutional runtime router.")
    parser.add_argument("question", nargs="*", help="Question to ask BEAST. If omitted, stdin is used.")
    parser.add_argument("--mode", choices=("auto", "speak", "draw"), default="auto")
    parser.add_argument("--source-service", default="")
    parser.add_argument("--target-service", default="")
    parser.add_argument("--out", type=Path, default=ROOT / "evidence/dai-diode/phase7-runtime/dai_phase7_runtime_latest.json")
    parser.add_argument("--svg-out", type=Path, default=None)
    parser.add_argument("--style-capsule", type=Path, default=None, help="Optional visual style capsule produced by teach_beast_visual_style.py.")
    parser.add_argument("--json", action="store_true", help="Print the full runtime response JSON.")
    args = parser.parse_args()

    question = " ".join(args.question).strip() or sys.stdin.read().strip()
    request = BeastRuntimeRequest(
        question=question,
        mode=args.mode,
        source_service=args.source_service,
        target_service=args.target_service,
    )
    context = load_default_runtime_context(ROOT)
    if args.style_capsule:
        import json as _json

        context = BeastRuntimeContext(
            ledger=context.ledger,
            phase6_4_constitutional_receipt=context.phase6_4_constitutional_receipt,
            phase6_5_formal_receipt=context.phase6_5_formal_receipt,
            visual_style_capsule=_json.loads(args.style_capsule.read_text(encoding="utf-8")),
            root=context.root,
        )
    response = route_beast_runtime_request(request, context)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(canonical_json(response) + "\n", encoding="utf-8")
    if args.svg_out and response.get("svg"):
        args.svg_out.parent.mkdir(parents=True, exist_ok=True)
        args.svg_out.write_text(str(response["svg"]), encoding="utf-8")

    if args.json:
        print(canonical_json(response))
    else:
        print(response["answer_text"])
        print()
        print(f"action: {response['action']}")
        print(f"visual_present: {response['visual_present']}")
        print(f"semantic_digest: {response['semantic_digest']}")
        print(f"runtime_receipt_digest: {response['runtime_receipt_digest']}")
        if args.svg_out and response.get("svg"):
            print(f"svg: {args.svg_out}")
        print(f"receipt: {args.out}")
    return 0 if response["runtime_receipt"]["green"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
