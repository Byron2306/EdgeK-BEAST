#!/usr/bin/env python3
"""Compile the query-scoped relevance receipt for Phase-3 composition."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.dai.phase3_composition import (
    build_phase3_composition_graph,
    prune_phase3_composition_graph,
    write_phase3_relevance_receipt,
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
    slice_ = prune_phase3_composition_graph(graph)
    receipt = write_phase3_relevance_receipt(root / "composition-graph/phase3_relevance_receipt.json", slice_)
    summary = {
        "beast_object_type": "dai_phase3_relevance_pruning_summary",
        "green": receipt["ordinary_answer_available"] and not receipt["residual_required"],
        "receipt_digest": receipt["receipt_digest"],
        "slice_digest": receipt["slice_digest"],
        "selected_fact_count": len(receipt["selected_fact_ids"]),
        "excluded_fact_count": len(receipt["excluded_fact_ids"]),
        "selected_edge_count": len(receipt["selected_edge_ids"]),
        "excluded_edge_count": len(receipt["excluded_edge_ids"]),
        "provider_calls_used": 0,
        "production_authority_allowed": False,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["green"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
