#!/usr/bin/env python3
"""Compile and independently verify Phase-3 text and visual expression."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.dai.phase3_composition import build_phase3_composition_graph, prune_phase3_composition_graph, route_phase3_residuals
from app.kernel.dai.phase3_expression import (
    compile_phase3_expression,
    verify_phase3_text_entailment,
    verify_phase3_visual_entailment,
    write_phase3_expression_artifacts,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT / "evidence/dai-diode/phase3-composition-001")
    args = parser.parse_args()
    root = args.root
    graph = build_phase3_composition_graph(
        fossil_receipt_path=root / "phase3_phase2_fossil_receipt.json",
        lockfile_summary_path=root / "lockfile-domain/phase3_lockfile_domain_summary.json",
        certificate_summary_path=root / "certificate-domain/phase3_certificate_domain_summary.json",
    )
    route = route_phase3_residuals(graph, prune_phase3_composition_graph(graph))
    bundle = compile_phase3_expression(graph, route)
    text = verify_phase3_text_entailment(graph, route, bundle)
    visual = verify_phase3_visual_entailment(graph, route, bundle)
    receipt = write_phase3_expression_artifacts(root / "composition-graph", bundle, text, visual)
    summary = {
        "beast_object_type": "dai_phase3_expression_summary",
        "green": receipt["joined_verification"] is True and receipt["ordinary_answer_available"] is True,
        "receipt_digest": receipt["receipt_digest"],
        "bundle_digest": receipt["bundle_digest"],
        "semantic_digest": receipt["semantic_digest"],
        "expressed_fact_count": len(receipt["expressed_fact_ids"]),
        "provider_calls_used": 0,
        "production_authority_allowed": False,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["green"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
