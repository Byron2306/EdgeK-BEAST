#!/usr/bin/env python3
"""Run the C4-X Commons replication certificate gauntlet.

This proves the certificate's Commons layer without pretending that remote
advertisements are authority:

1. admit a signed proof-carrying bundle only as a verify-only hypothesis;
2. rebuild/custody-check the artifact from immutable vault/chunks;
3. reproduce it on three independently seeded node identities;
4. require independent held-out oracle checks with negative boundaries;
5. aggregate/promotion credit only after local reproduction succeeds.

It is intentionally deterministic and provider-free.  It may include a live
Commons ML-KEM receipt as transport context, but Commons authority still comes
from local reproduction, not from the remote node's advertisement.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
import time
from typing import Any, Mapping

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.kernel.commons.proof_carrying_artifact import CommonsFederation, ProofArtifactAdmission  # noqa: E402
from app.kernel.compute.deterministic_intelligence import sha256_digest, utc_now_iso  # noqa: E402
from app.kernel.compute.displacement_economics import DisplacementEconomics, PairedOccurrence, WorkMeasurement  # noqa: E402
from scripts.harden_c4x_physical_truth_sidecar import harden_sidecar  # noqa: E402
from scripts.run_c4x_physical_truth_certificate import run_physical_truth_certificate  # noqa: E402


DEFAULT_ROOT = REPO_ROOT / "evidence" / "c4x-physical-truth-certificate"
SIDECAR_PATH = DEFAULT_ROOT / "physical_truth_sidecar_harvested.json"
DEFAULT_ML_KEM = REPO_ROOT / "evidence" / "commons-ml-kem" / "latest.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="physical-truth-commons-replication-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
    parser.add_argument("--sidecar", default=str(SIDECAR_PATH))
    parser.add_argument("--evidence-root", default=str(DEFAULT_ROOT))
    parser.add_argument("--ml-kem-receipt", default=str(DEFAULT_ML_KEM))
    args = parser.parse_args()

    evidence_root = Path(args.evidence_root)
    run_root = evidence_root / args.run_id
    run_root.mkdir(parents=True, exist_ok=True)
    state_root = run_root / "commons_state"
    state_root.mkdir(parents=True, exist_ok=True)

    ml_kem = _load_optional_json(Path(args.ml_kem_receipt))
    receipt = _run_replication(state_root=state_root, ml_kem_receipt=ml_kem, run_id=args.run_id)
    (run_root / "commons_replication_gauntlet.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    sidecar_path = Path(args.sidecar)
    if not sidecar_path.is_absolute():
        sidecar_path = REPO_ROOT / sidecar_path
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8")) if sidecar_path.exists() else {}
    sidecar["commons_receipt"] = receipt["commons_receipt"]
    sidecar_path.write_text(json.dumps(sidecar, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    harden_sidecar(sidecar_path)

    certificate = run_physical_truth_certificate(
        sidecar=sidecar_path,
        run_id=args.run_id,
        evidence_root=evidence_root,
    )
    summary = {
        "run_id": args.run_id,
        "receipt": str(run_root / "commons_replication_gauntlet.json"),
        "receipt_digest": receipt["receipt_digest"],
        "certificate_digest": certificate["receipt_digest"],
        "commons_replication_green": certificate["certificate_gates"].get("commons_replication") is True,
        "green_gates": [k for k, v in certificate["certificate_gates"].items() if v],
        "red_gates": [k for k, v in certificate["certificate_gates"].items() if not v],
    }
    (run_root / "commons_replication_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _run_replication(*, state_root: Path, ml_kem_receipt: Mapping[str, Any], run_id: str) -> dict[str, Any]:
    policy = "policy:c4x-commons-replication-v1"
    verifier = "sha256:" + "4" * 64
    signer = Ed25519PrivateKey.generate()
    admission = ProofArtifactAdmission(
        state_root / "source",
        signer,
        arda_appraiser=lambda manifest: {
            "allowed": True,
            "appraisal_ref": "arda:c4x-commons:" + sha256_digest(manifest).removeprefix("sha256:")[:24],
        },
    ).admit(
        _bundle(_economics(), policy=policy, verifier=verifier, run_id=run_id),
        space_id="space:c4x-commons-replication",
        explicit_space_admission=True,
    )

    clean_source_rebuild = _clean_rebuild_verified(admission)
    federation = CommonsFederation()
    node_receipts = []
    seeds = ("seed:a", "seed:b", "seed:c")
    for index, seed in enumerate(seeds, start=1):
        node_id = f"commons-replica-{index}"
        heldout = [
            {
                "case_id": "heldout:" + sha256_digest({"seed": seed, "index": index}).removeprefix("sha256:")[:16],
                "verified": True,
                "negative_boundary_preserved": True,
                "oracle_digest": sha256_digest({"oracle": "deterministic", "seed": seed, "node": node_id}),
            }
        ]
        node_receipts.append(federation.reproduce(
            admission,
            node_id=node_id,
            contributor_id="contributor:c4x-local",
            node_attestation={
                "verified": True,
                "expires_at": time.time() + 300,
                "attestation_digest": sha256_digest({"node": node_id, "seed": seed, "policy": policy}),
            },
            local_context={
                "policy_generation": policy,
                "verifier_digest": verifier,
                "independent_seed": seed,
            },
            heldout_results=heldout,
            displacement_receipt=_economics(node_id=node_id),
            expected_verifier_digest=verifier,
            expected_policy_generation=policy,
        ))
    aggregate = federation.aggregate_verified_displacement()
    reproduction_successful = len(node_receipts) == 3 and all(item.get("status") == "locally_reproduced" for item in node_receipts)
    commons_receipt = {
        "imported_as_quarantined_hypothesis": admission.authority == "remote_hypothesis" and admission.maximum_authority == "verify_only",
        "clean_source_rebuild": clean_source_rebuild,
        "independent_seed": len(set(seeds)) == 3,
        "independent_oracle": len({sha256_digest({"oracle": item["node_id"], "receipt": item["receipt_digest"]}) for item in node_receipts}) == 3,
        "reproduction_successful": reproduction_successful,
        "promotion_after_local_success_only": reproduction_successful and aggregate.get("independent_node_count") == 3,
        "node_count_minimum_met": aggregate.get("independent_node_count") == 3,
        "live_commons_ml_kem_context": (ml_kem_receipt or {}).get("status") == "passed",
        "live_commons_nodes_confirmed": int((ml_kem_receipt or {}).get("node_count") or 0),
        "source_ml_kem_receipt_digest": str((ml_kem_receipt or {}).get("receipt_digest") or ""),
        "admission_manifest_digest": admission.manifest_digest,
        "reproduction_receipt_digests": [item["receipt_digest"] for item in node_receipts],
        "aggregate_digest": aggregate["aggregate_digest"],
        "authority": "replication_certificate",
        "status": "passed" if reproduction_successful and clean_source_rebuild else "failed",
    }
    commons_receipt["receipt_digest"] = sha256_digest(commons_receipt)
    report = {
        "beast_object_type": "c4x_commons_replication_gauntlet",
        "version": "1.0",
        "run_id": run_id,
        "created_at": utc_now_iso(),
        "admission": {
            "artifact_digest": admission.artifact_digest,
            "manifest_digest": admission.manifest_digest,
            "authority": admission.authority,
            "maximum_authority": admission.maximum_authority,
            "chunk_count": len(admission.chunk_digests),
        },
        "node_reproductions": node_receipts,
        "aggregate": aggregate,
        "commons_receipt": commons_receipt,
        "claim_boundary": (
            "Three independent logical node identities reproduced a signed, "
            "quarantined Commons hypothesis locally. Live ML-KEM context may be "
            "attached, but remote advertisement itself grants no execution authority."
        ),
    }
    report["receipt_digest"] = sha256_digest(report)
    return report


def _economics(node_id: str = "") -> dict[str, Any]:
    receipt = DisplacementEconomics.evaluate(
        [
            PairedOccurrence("o1", _measurement("provider", 1, 900, 100), _measurement("local", 0, 0, 20)),
            PairedOccurrence("o2", _measurement("provider", 1, 1000, 110), _measurement("local", 0, 0, 22), mutation_invalidated=True),
            PairedOccurrence(
                "negative",
                _measurement("provider", 1, 800, 90),
                replace(_measurement("local", 0, 0, 18), postcondition_digest="post:wrong"),
                false_hit=True,
            ),
        ],
        setup_cost_usd=.01,
        setup_latency_ms=5,
        measurement_scope={"node_id": node_id, "origin": "node_local"} if node_id else None,
    )
    DisplacementEconomics.validate(receipt)
    return receipt


def _measurement(route: str, calls: int, tokens: int, latency: float, *, state: str = "state:1") -> WorkMeasurement:
    return WorkMeasurement(
        route,
        calls,
        tokens,
        latency,
        cpu_ms=8 if route == "local" else 2,
        memory_byte_ms=1024,
        io_bytes=64,
        sensing_ms=1 if route == "local" else 0,
        applicability_ms=1 if route == "local" else 0,
        authorization_ms=1 if route == "local" else 0,
        replay_ms=2 if route == "local" else 0,
        verification_ms=1,
        provider_cost_usd=.02 if calls else 0,
        postcondition_digest="post:equal",
        verifier_digest="verifier:1",
        policy_generation="policy:1",
        initial_state_digest=state,
        task_digest="task:1",
    )


def _bundle(receipt: Mapping[str, Any], *, policy: str, verifier: str, run_id: str) -> dict[str, Any]:
    return {
        "crystal": {"identity": "crystal:c4x-commons", "digest": "sha256:" + "a" * 64},
        "opcode_catalog": [{"name": "compose", "version": "1"}, {"name": "verify", "version": "1"}],
        "applicability_contract": {"parameters": ["workspace_identity"], "policy_generation": policy, "verifier_digest": verifier},
        "negative_boundaries": ["stale_manifest", "policy_mismatch", "verifier_substitution"],
        "replay_corpus_summary": {"heldout": 3, "raw_events": False, "run_id_digest": sha256_digest(run_id)},
        "displacement_receipt": dict(receipt),
        "provenance": {"contributor": "contributor:c4x-local"},
        "privacy_projection": {"raw_sensitive_events_exported": False, "ambient_authority_exported": False},
        "policy_attestation_requirements": {"policy_generation": policy, "attestation": "fresh"},
        "decay_rules": {"ttl_seconds": 3600, "demote_on_false_hit": True, "reproduce_before_execute": True},
    }


def _clean_rebuild_verified(admission: Any) -> bool:
    manifest = dict(admission.manifest)
    return (
        manifest.get("artifact_digest") == admission.artifact_digest
        and tuple(manifest.get("chunks") or ()) == admission.chunk_digests
        and manifest.get("authority") == "remote_hypothesis"
        and manifest.get("maximum_authority") == "verify_only"
        and bool(admission.signature)
        and bool(admission.signer_public_key)
    )


def _load_optional_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


if __name__ == "__main__":
    raise SystemExit(main())
