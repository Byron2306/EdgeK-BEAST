#!/usr/bin/env python3
"""Create the unified signed Sophia/Integritas -> BEAST lineage certificate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.deterministic_intelligence import canonical_json
from app.kernel.dai.phase6_sophia_integritas_lineage import (
    build_sophia_integritas_lineage_certificate,
    sign_sophia_export,
    verify_lineage_certificate,
)


DEFAULT_SOPHIA = Path("/home/byron/Integritas-Mechanicus/evidence/sophia_writing_desk_phase3_export_semantic_latest.json")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(payload) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sophia", type=Path, default=DEFAULT_SOPHIA)
    parser.add_argument("--phase1-root", type=Path, default=ROOT / "evidence/dai-diode/phase1-synthesis-001")
    parser.add_argument("--phase6-1", type=Path, default=ROOT / "evidence/dai-diode/phase6-sophia-transfer-arena/dai_phase6_sophia_transfer_arena_receipt.json")
    parser.add_argument("--phase6-2-ledger", type=Path, default=ROOT / "evidence/dai-diode/phase6-truth-arena/dai_capability_ledger.json")
    parser.add_argument("--phase6-2-truth", type=Path, default=ROOT / "evidence/dai-diode/phase6-truth-arena/dai_phase6_truth_arena_receipt.json")
    parser.add_argument("--out-root", type=Path, default=ROOT / "evidence/dai-diode/phase6-sophia-integritas-lineage")
    args = parser.parse_args()

    signature = sign_sophia_export(args.sophia)
    phase1 = args.phase1_root
    packet = _read_json(phase1 / "dai_phase1_packet.json")
    seraph_assessment = packet.get("seraph_assessment") if isinstance(packet.get("seraph_assessment"), dict) else {}
    certificate = build_sophia_integritas_lineage_certificate(
        signed_sophia=signature,
        phase1_packet=packet,
        phase1_validation=_read_json(phase1 / "dai_phase1_validation_receipt.json"),
        evidence_resolution=_read_json(phase1 / "dai_evidence_resolution_receipt.json"),
        seraph_assessment_packet=seraph_assessment,
        commons_admission=_read_json(phase1 / "dai_commons_admission_receipt.json"),
        quorum_decision=_read_json(phase1 / "dai_quorum_decision_receipt.json"),
        promotion=_read_json(phase1 / "dai_capability_promotion_receipt.json"),
        neural_mesh=_read_json(phase1 / "dai_neural_mesh_activation_receipt.json"),
        arda_execution=_read_json(phase1 / "dai_arda_execution_receipt.json"),
        phase6_1=_read_json(args.phase6_1),
        phase6_2_ledger=_read_json(args.phase6_2_ledger),
        phase6_2_truth=_read_json(args.phase6_2_truth),
    )
    verification = verify_lineage_certificate(certificate)

    signature_path = args.out_root / "sophia_integritas_lineage_signature.json"
    certificate_path = args.out_root / "sophia_integritas_unified_lineage_certificate.json"
    verification_path = args.out_root / "sophia_integritas_unified_lineage_verification.json"
    _write_json(signature_path, json.loads(canonical_json(signature)))
    _write_json(certificate_path, certificate)
    _write_json(verification_path, verification)

    print(json.dumps({
        "green": certificate["green"],
        "verified": verification["verified"],
        "certificate_digest": certificate["certificate_digest"],
        "verification_digest": verification["verification_digest"],
        "signed_export_digest": certificate["signed_sophia_export_digest"],
        "signature_packet_digest": certificate["signed_sophia_signature_packet_digest"],
        "red_gates": certificate["red_gates"],
        "signature": str(signature_path),
        "certificate": str(certificate_path),
        "verification": str(verification_path),
    }, indent=2, sort_keys=True))
    return 0 if certificate["green"] and verification["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
