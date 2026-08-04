#!/usr/bin/env python3
"""Freeze C4-X core and BEAST Truth Stack identities."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.kernel.compute.deterministic_intelligence import sha256_digest, utc_now_iso  # noqa: E402


DEFAULT_EVIDENCE_ROOT = REPO_ROOT / "evidence" / "c4x-freeze-identities"

CORE_FILES = (
    "app/kernel/compute/deterministic_intelligence.py",
)

TRUTH_STACK_FILES = (
    "benchmarks/c4x_truth_arena.py",
    "benchmarks/c4x_existing_evidence_sidecar.py",
    "benchmarks/c4x_freeze_identities.py",
    "benchmarks/c4x_document_truth_arena.py",
    "scripts/run_c4x_external_breakthrough_benchmark.py",
    "scripts/run_c4x_rds_rag_adapter.py",
    "scripts/seed_c4x_pgvector_rag_corpus.py",
    "scripts/run_commons_ml_kem_gauntlet.py",
    "scripts/run_forge_kv_ml_kem_transport_gauntlet.py",
    "app/kernel/execution/socket_guardian.py",
    "app/kernel/compute/forge_kv_ml_kem_transport.py",
)

CERTIFICATES = (
    "truth",
    "observation",
    "protocol_integrity",
    "custody",
    "reuse",
    "resilience",
    "replication",
)


def freeze_identities(
    *,
    evidence_root: str | Path = DEFAULT_EVIDENCE_ROOT,
    run_id: str | None = None,
) -> dict[str, Any]:
    run_id = run_id or utc_now_iso().replace(":", "").replace("+", "z")
    core_manifest = _manifest("c4x-core-v1.0", CORE_FILES)
    stack_manifest = _manifest("beast-truth-stack-v1.0", TRUTH_STACK_FILES)
    receipt_core = {
        "beast_object_type": "c4x_freeze_identity_receipt",
        "version": "1.0",
        "run_id": run_id,
        "observed_at": utc_now_iso(),
        "claim_boundary": (
            "c4x-core-v1.0 freezes proof-composition semantic logic. "
            "beast-truth-stack-v1.0 may observe, transport, protect, reuse, "
            "and reproduce the frozen core outputs but may not alter core "
            "semantic logic after challenge disclosure."
        ),
        "identities": {
            "c4x-core-v1.0": core_manifest,
            "beast-truth-stack-v1.0": stack_manifest,
        },
        "certificate_contract": {
            certificate: "pending_external_challenge_execution"
            for certificate in CERTIFICATES
        },
    }
    receipt = {**receipt_core, "receipt_digest": sha256_digest(receipt_core)}
    run_root = Path(evidence_root) / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "freeze_identities.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (run_root / "freeze_identities.md").write_text(_markdown(receipt), encoding="utf-8")
    (Path(evidence_root) / "latest.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {**receipt, "evidence_root": str(run_root)}


def _manifest(identity: str, files: tuple[str, ...]) -> dict[str, Any]:
    entries = []
    for rel in files:
        path = REPO_ROOT / rel
        if path.exists():
            entries.append({
                "path": rel,
                "sha256": _file_sha256(path),
                "bytes": path.stat().st_size,
                "present": True,
            })
        else:
            entries.append({
                "path": rel,
                "sha256": "",
                "bytes": 0,
                "present": False,
            })
    return {
        "identity": identity,
        "files": entries,
        "all_files_present": all(entry["present"] for entry in entries),
        "identity_digest": sha256_digest(entries),
    }


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _markdown(receipt: dict[str, Any]) -> str:
    lines = [
        f"# C4-X freeze identities · {receipt['run_id']}",
        "",
        f"- Receipt: `{receipt['receipt_digest']}`",
        f"- Core digest: `{receipt['identities']['c4x-core-v1.0']['identity_digest']}`",
        f"- Stack digest: `{receipt['identities']['beast-truth-stack-v1.0']['identity_digest']}`",
        "",
        "## Certificate contract",
        "",
    ]
    for name, status in receipt["certificate_contract"].items():
        lines.append(f"- `{name}`: {status}")
    lines.extend(["", "## Boundary", "", receipt["claim_boundary"]])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze C4-X core and BEAST Truth Stack identities.")
    parser.add_argument("--evidence-root", default=str(DEFAULT_EVIDENCE_ROOT))
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()
    receipt = freeze_identities(evidence_root=args.evidence_root, run_id=args.run_id)
    print(json.dumps({
        "evidence_root": receipt["evidence_root"],
        "receipt_digest": receipt["receipt_digest"],
        "core_digest": receipt["identities"]["c4x-core-v1.0"]["identity_digest"],
        "stack_digest": receipt["identities"]["beast-truth-stack-v1.0"]["identity_digest"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
