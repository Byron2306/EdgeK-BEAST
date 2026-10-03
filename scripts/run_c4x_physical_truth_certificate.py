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
from typing import Any, Iterable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.kernel.compute.c4x_physical_truth_certificate import (  # noqa: E402
    build_c4x_physical_truth_certificate,
    empty_pending_sidecar,
)
from app.kernel.compute.deterministic_intelligence import sha256_digest, utc_now_iso  # noqa: E402


DEFAULT_EVIDENCE_ROOT = REPO_ROOT / "evidence" / "c4x-physical-truth-certificate"
SIDECAR_RECEIPT_KEYS = tuple(empty_pending_sidecar().keys())


def scoped_gate_summary(
    certificate: Mapping[str, Any],
    *,
    claimed_gates: Iterable[str],
    dependency_gates: Iterable[str] = (),
) -> dict[str, Any]:
    """Return a component-scoped gate summary.

    Component runners must not echo the certificate's full expected-green list.
    They may report only the gate(s) they directly claim and the explicit gates
    they depend on.  The full twelve-gate view belongs to the final certificate
    or one-shot umbrella, not to individual gate receipts.
    """
    gates = certificate.get("certificate_gates")
    if not isinstance(gates, Mapping):
        gates = {}
    claimed = tuple(dict.fromkeys(str(item) for item in claimed_gates))
    deps = tuple(dict.fromkeys(str(item) for item in dependency_gates if str(item) not in claimed))
    scope = claimed + deps
    return {
        "certificate_gate_scope": "component_scoped",
        "claimed_gates": list(claimed),
        "dependency_gates": list(deps),
        "gate_results": {key: gates.get(key) is True for key in scope},
        "claimed_gates_green": all(gates.get(key) is True for key in claimed),
        "dependency_gates_green": all(gates.get(key) is True for key in deps),
    }


def write_scoped_sidecar(
    *,
    source_payload: Mapping[str, Any],
    destination: str | Path,
    run_id: str,
    claimed_receipts: Iterable[str],
    dependency_receipts: Iterable[str] = (),
    source_sidecar: str | Path | None = None,
) -> Path:
    """Write a per-run sidecar containing only claimed/dependency receipts.

    This prevents component smoke runs from inheriting unrelated green gates
    from the shared physical_truth_sidecar_harvested.json file.
    """
    claimed = _unique_receipts(claimed_receipts)
    deps = tuple(key for key in _unique_receipts(dependency_receipts) if key not in claimed)
    scoped = empty_pending_sidecar()
    for key in claimed + deps:
        value = source_payload.get(key)
        if isinstance(value, Mapping) and value:
            scoped[key] = dict(value)
    excluded = [key for key in SIDECAR_RECEIPT_KEYS if key not in set(claimed + deps)]
    provenance = {
        "beast_object_type": "c4x_component_scoped_sidecar_provenance",
        "version": "1.0",
        "run_id": run_id,
        "created_at": utc_now_iso(),
        "source_sidecar": str(_resolve_sidecar(source_sidecar)) if source_sidecar else "",
        "source_sidecar_digest": _file_sha256(_resolve_sidecar(source_sidecar)) if source_sidecar else "",
        "claimed_receipts": list(claimed),
        "dependency_receipts": list(deps),
        "excluded_receipts": excluded,
        "freshness_contract": (
            "Only claimed receipts and explicit dependencies are present. "
            "Unrelated receipts from the shared sidecar are reset to pending "
            "for this component certificate run."
        ),
    }
    provenance["provenance_digest"] = sha256_digest(provenance)
    scoped["_sidecar_provenance"] = provenance
    out = _resolve_sidecar(destination)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(scoped, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def initialize_run_sidecar(
    *,
    destination: str | Path,
    run_id: str,
    source_sidecar: str | Path | None = None,
    inherited_receipts: Iterable[str] = (),
) -> Path:
    """Create a run-local sidecar, optionally inheriting explicit receipts only."""
    inherited = _unique_receipts(inherited_receipts)
    source_payload = _load_sidecar(source_sidecar) if source_sidecar else {}
    sidecar = empty_pending_sidecar()
    for key in inherited:
        value = source_payload.get(key)
        if isinstance(value, Mapping) and value:
            sidecar[key] = dict(value)
    provenance = {
        "beast_object_type": "c4x_run_local_sidecar_provenance",
        "version": "1.0",
        "run_id": run_id,
        "created_at": utc_now_iso(),
        "source_sidecar": str(_resolve_sidecar(source_sidecar)) if source_sidecar else "",
        "source_sidecar_digest": _file_sha256(_resolve_sidecar(source_sidecar)) if source_sidecar else "",
        "inherited_receipts": list(inherited),
        "freshness_contract": (
            "This full-gauntlet sidecar starts from pending receipts unless an "
            "operator explicitly names receipts to inherit. Component runners "
            "then update this run-local sidecar for the final certificate."
        ),
    }
    provenance["provenance_digest"] = sha256_digest(provenance)
    sidecar["_sidecar_provenance"] = provenance
    out = _resolve_sidecar(destination)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(sidecar, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


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


def _unique_receipts(keys: Iterable[str]) -> tuple[str, ...]:
    unique = tuple(dict.fromkeys(str(key) for key in keys))
    unknown = [key for key in unique if key not in SIDECAR_RECEIPT_KEYS]
    if unknown:
        raise ValueError(f"unknown sidecar receipt key(s): {unknown}")
    return unique


def _resolve_sidecar(path: str | Path | None) -> Path:
    if path is None:
        raise ValueError("sidecar path is required")
    sidecar = Path(path)
    return sidecar if sidecar.is_absolute() else REPO_ROOT / sidecar


def _file_sha256(path: Path) -> str:
    import hashlib

    if not path.is_file():
        return ""
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_checksums(root: Path) -> None:
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            rows.append(f"{_file_sha256(path).removeprefix('sha256:')}  {path.relative_to(root)}")
    (root / "SHA256SUMS.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")


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
