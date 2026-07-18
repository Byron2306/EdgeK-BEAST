#!/usr/bin/env python3
"""Independently verify a sealed discovery-agnostic reuse receipt."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.kernel.compute.discovery_agnostic_reuse import read_corpus_receipt, read_receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt")
    args = parser.parse_args()
    payload = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
    if "case_receipts" in payload:
        receipt = read_corpus_receipt(args.receipt)
        print(json.dumps({
            "verified": True,
            "protocol": receipt.protocol,
            "receipt_digest": receipt.receipt_digest,
            "cases": len(receipt.case_receipts),
            "expected_admissions": receipt.expected_admissions,
            "actual_admissions": receipt.actual_admissions,
            "unsafe_admissions": receipt.unsafe_admissions,
            "provider_calls_avoided": receipt.provider_calls_avoided,
            "measured_economic_cases": receipt.measured_economic_cases,
            "net_latency_saved_ms": receipt.net_latency_saved_ms,
            "claim_boundary": "integrity verification; independent review must still validate corpus provenance and raw local-verifier evidence",
        }, sort_keys=True))
        return 0
    receipt = read_receipt(args.receipt)
    print(json.dumps({
        "verified": True,
        "protocol": receipt.protocol,
        "receipt_digest": receipt.receipt_digest,
        "receiver_host_id": receipt.receiver_host_id,
        "receiver_attestation_verified": receipt.receiver_attestation_verified,
        "receiver_physical_host": receipt.receiver_physical_host,
        "provider_calls_avoided": receipt.provider_calls_avoided,
        "admission_reason": receipt.admission_reason,
        "claim_boundary": "receipt verification proves protocol integrity, not corpus-level discovery-agnostic uplift",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
