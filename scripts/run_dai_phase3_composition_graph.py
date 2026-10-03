#!/usr/bin/env python3
"""Build the Operational Phase-3 multi-domain composition graph."""
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
    write_phase3_composition_graph,
    write_phase3_composition_receipt,
)


DEFAULT_ROOT = ROOT / "evidence/dai-diode/phase3-composition-001"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    summary = run(root=args.root)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["green"] else 1


def run(*, root: Path) -> dict[str, object]:
    graph = build_phase3_composition_graph(
        fossil_receipt_path=root / "phase3_phase2_fossil_receipt.json",
        lockfile_summary_path=root / "lockfile-domain/phase3_lockfile_domain_summary.json",
        certificate_summary_path=root / "certificate-domain/phase3_certificate_domain_summary.json",
    )
    out = root / "composition-graph"
    out.mkdir(parents=True, exist_ok=True)
    write_phase3_composition_graph(out / "phase3_composition_graph.json", graph)
    receipt = write_phase3_composition_receipt(out / "phase3_composition_graph_receipt.json", graph)
    return {
        "beast_object_type": "dai_phase3_composition_graph_run_summary",
        "green": bool(
            receipt["ordinary_answer_available"]
            and not receipt["residual_required"]
            and receipt["provider_calls_used"] == 0
            and receipt["production_authority_allowed"] is False
            and receipt["execution_authority_allowed"] is False
        ),
        "graph_digest": graph.graph_digest,
        "receipt_digest": receipt["receipt_digest"],
        "fact_count": receipt["fact_count"],
        "edge_count": receipt["edge_count"],
        "derived_claim_ids": receipt["derived_claim_ids"],
        "ordinary_answer_available": receipt["ordinary_answer_available"],
        "residual_required": receipt["residual_required"],
        "provider_calls_used": receipt["provider_calls_used"],
        "production_authority_allowed": receipt["production_authority_allowed"],
        "execution_authority_allowed": receipt["execution_authority_allowed"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
