#!/usr/bin/env python3
"""Run the C4-X physical truth certificate matrix.

The default run intentionally emits a pending certificate.  Supply a JSON
sidecar with independently generated receipts to unlock gates.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.kernel.compute.c4x_physical_truth_certificate import (  # noqa: E402
    build_c4x_physical_truth_certificate,
    empty_pending_sidecar,
)
from app.kernel.compute.deterministic_intelligence import sha256_digest, utc_now_iso  # noqa: E402


DEFAULT_EVIDENCE_ROOT = REPO_ROOT / "evidence" / "c4x-physical-truth-certificate"


def run_physical_truth_certificate(
    *,
    sidecar: str | Path | None = None,
    evidence_root: str | Path = DEFAULT_EVIDENCE_ROOT,
    run_id: str | None = None,
    write_template: bool = False,
) -> dict[str, Any]:
    run_id = run_id or utc_now_iso().replace(":", "").replace("+", "z")
    root = Path(evidence_root) / run_id
    root.mkdir(parents=True, exist_ok=True)
    if write_template:
        template = empty_pending_sidecar()
        template_path = root / "physical_truth_sidecar_template.json"
        template_path.write_text(json.dumps(template, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    payload = _load_sidecar(sidecar)
    receipt = build_c4x_physical_truth_certificate(
        c4x_receipt=payload.get("c4x_receipt"),
        sensorium_receipt=payload.get("sensorium_receipt"),
        bpf_receipt=payload.get("bpf_receipt"),
        crystal_bus_receipt=payload.get("crystal_bus_receipt"),
        memfd_receipt=payload.get("memfd_receipt"),
        guardian_receipt=payload.get("guardian_receipt"),
        reuse_receipt=payload.get("reuse_receipt"),
        pq_transport_receipt=payload.get("pq_transport_receipt"),
        commons_receipt=payload.get("commons_receipt"),
        route_receipt=payload.get("route_receipt"),
        psi_receipt=payload.get("psi_receipt"),
        xdp_receipt=payload.get("xdp_receipt"),
        run_id=run_id,
    )
    (root / "physical_truth_certificate.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (root / "physical_truth_certificate.md").write_text(_markdown(receipt), encoding="utf-8")
    _write_checksums(root)
    latest_root = Path(evidence_root)
    latest_root.mkdir(parents=True, exist_ok=True)
    (latest_root / "latest.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {**receipt, "evidence_root": str(root)}


def _load_sidecar(path: str | Path | None) -> Mapping[str, Any]:
    if not path:
        return empty_pending_sidecar()
    sidecar = Path(path)
    if not sidecar.is_absolute():
        sidecar = REPO_ROOT / sidecar
    value = json.loads(sidecar.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("physical truth sidecar must be a JSON object")
    return value


def _write_checksums(root: Path) -> None:
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            rows.append(f"{_file_sha256(path).removeprefix('sha256:')}  {path.relative_to(root)}")
    (root / "SHA256SUMS.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")


def _file_sha256(path: Path) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _markdown(receipt: Mapping[str, Any]) -> str:
    lines = [
        f"# C4-X physical truth certificate · {receipt['run_id']}",
        "",
        f"- Receipt: `{receipt['receipt_digest']}`",
        f"- Public credit allowed: `{receipt['public_credit_allowed']}`",
        f"- Truth claim allowed: `{receipt['truth_claim_allowed']}`",
        f"- Critical failures: `{len(receipt['critical_failures'])}`",
        "",
        "## Certificate gates",
        "",
    ]
    for layer, passed in receipt["certificate_gates"].items():
        lines.append(f"- `{layer}`: `{passed}`")
    lines.extend(["", "## Boundary", "", str(receipt["claim_boundary"]), ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the C4-X physical truth certificate matrix.")
    parser.add_argument("--sidecar", default=None)
    parser.add_argument("--evidence-root", default=str(DEFAULT_EVIDENCE_ROOT))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--write-template", action="store_true")
    args = parser.parse_args()
    receipt = run_physical_truth_certificate(
        sidecar=args.sidecar,
        evidence_root=args.evidence_root,
        run_id=args.run_id,
        write_template=args.write_template,
    )
    print(json.dumps({
        "evidence_root": receipt["evidence_root"],
        "receipt_digest": receipt["receipt_digest"],
        "public_credit_allowed": receipt["public_credit_allowed"],
        "critical_failures": receipt["critical_failures"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
