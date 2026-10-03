#!/usr/bin/env python3
"""Normalize existing witness evidence into Phase-4 Commons adapter reports."""
from __future__ import annotations

from dataclasses import asdict
import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.deterministic_intelligence import canonical_json, sha256_digest
from app.kernel.dai.dio_commons_adapters import (
    DIOCommonsAdapterKind,
    adapt_arda_receipt_to_commons_space,
    adapt_cloud_harvest_to_commons_space,
    adapt_github_actions_verification_to_commons_space,
)


DEFAULT_OUT = ROOT / "evidence/dai-diode/phase4-commons-adapters"
GCP_HARVEST = ROOT / "evidence/dai-diode/phase2.1-cloud-witness/gcp-africa-south1-witness-02-repair-20260804T190327Z/harvest/dio_gcp_tee_attestation_harvest.json"
AWS_HARVEST = ROOT / "evidence/dai-diode/phase2.1-cloud-witness/aws-af-south-1-live-008/dio_aws_tee_attestation_harvest.json"
GITHUB_PACKET = ROOT / "evidence/dai-diode/phase2.1-github-witness/run-30937227770/dio_github_actions_witness_packet.json"
GITHUB_VERIFICATION = ROOT / "evidence/dai-diode/phase2.1-github-witness/run-30937227770/dio_github_actions_witness_verification.json"
ARDA_RECEIPT = ROOT / "evidence/dai-diode/phase1-synthesis-001/dai_arda_execution_receipt.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    summary = run(out=args.out)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["green"] else 1


def run(*, out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    adapters = (
        ("gcp_confidential_space", adapt_cloud_harvest_to_commons_space(_read(GCP_HARVEST), adapter_kind=DIOCommonsAdapterKind.GCP_CONFIDENTIAL_SPACE)),
        ("aws_nitro", adapt_cloud_harvest_to_commons_space(_read(AWS_HARVEST), adapter_kind=DIOCommonsAdapterKind.AWS_NITRO_TPM)),
        ("github_actions", adapt_github_actions_verification_to_commons_space(_read(GITHUB_PACKET), _read(GITHUB_VERIFICATION))),
        ("arda_local", adapt_arda_receipt_to_commons_space(_read(ARDA_RECEIPT))),
    )
    for name, (manifest, report) in adapters:
        payload = {"manifest": asdict(manifest), "manifest_digest": manifest.manifest_digest, "adapter_report": asdict(report), "adapter_report_digest": report.report_digest}
        path = out / f"{name}_commons_adapter.json"
        path.write_text(canonical_json(payload) + "\n", encoding="utf-8")
        rows.append({
            "name": name,
            "manifest_digest": manifest.manifest_digest,
            "adapter_report_digest": report.report_digest,
            "adapted": report.adapted,
            "persistent_service": report.persistent_service,
            "online_protocol_ready": report.online_protocol_ready,
            "attestation_class": report.attestation_class,
            "red_gates": report.red_gates,
        })
    summary = {
        "beast_object_type": "dio_phase4_commons_adapter_summary",
        "adapter_count": len(rows),
        "adapted_count": sum(1 for row in rows if row["adapted"]),
        "online_ready_count": sum(1 for row in rows if row["online_protocol_ready"]),
        "persistent_service_count": sum(1 for row in rows if row["persistent_service"]),
        "adapters": tuple(rows),
        "green": all(row["adapted"] for row in rows),
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }
    summary["summary_digest"] = sha256_digest(summary)
    (out / "dio_phase4_commons_adapter_summary.json").write_text(canonical_json(summary) + "\n", encoding="utf-8")
    return summary


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
